"""Deterministic graders for Chapter 2."""

from __future__ import annotations

from typing import Protocol

from policyops.eval.schemas import GraderResult, GraderVerdict, TaskCase, TrialRecord


class Grader(Protocol):
    grader_id: str

    def grade(self, trial: TrialRecord, case: TaskCase) -> GraderResult: ...


def _result(
    grader_id: str,
    trial: TrialRecord,
    case: TaskCase,
    verdict: GraderVerdict,
    reason: str,
    **evidence,
) -> GraderResult:
    return GraderResult(
        grader_id=grader_id,
        trial_id=trial.trial_id,
        task_id=case.task_id,
        verdict=verdict,
        score=1.0 if verdict == GraderVerdict.PASS else 0.0,
        reason_code=reason,
        evidence=evidence,
    )


class SchemaGrader:
    grader_id = "schema@1"

    def grade(self, trial: TrialRecord, case: TaskCase) -> GraderResult:
        expected = case.expected.get("http_status")
        if expected is not None and trial.http_status != expected:
            return _result(
                self.grader_id,
                trial,
                case,
                GraderVerdict.FAIL,
                "http_status_mismatch",
                expected=expected,
                actual=trial.http_status,
            )
        if case.expected.get("require_answer") and not (trial.output or {}).get("answer"):
            return _result(self.grader_id, trial, case, GraderVerdict.FAIL, "missing_answer")
        if trial.status == "error" and case.expected.get("allow_error"):
            return _result(self.grader_id, trial, case, GraderVerdict.PASS, "expected_error")
        if trial.output and "answer" in trial.output:
            answer = trial.output["answer"]
            if "schema_version" not in answer:
                return _result(self.grader_id, trial, case, GraderVerdict.FAIL, "answer_schema")
        return _result(self.grader_id, trial, case, GraderVerdict.PASS, "ok")


class CitationGrader:
    grader_id = "citation@1"

    def grade(self, trial: TrialRecord, case: TaskCase) -> GraderResult:
        if case.expected.get("require_citations") is False:
            return _result(self.grader_id, trial, case, GraderVerdict.PASS, "not_required")
        answer = (trial.output or {}).get("answer") or {}
        citations = answer.get("citations") or []
        if case.expected.get("require_citations", False) and not citations:
            return _result(self.grader_id, trial, case, GraderVerdict.FAIL, "missing_citations")
        for cite in citations:
            excerpt = cite.get("excerpt") or ""
            text = answer.get("text") or ""
            if excerpt and excerpt not in text and case.expected.get("exact_excerpt", True):
                # Allow citation excerpt to appear in policy source; require non-empty locator.
                if not cite.get("locator"):
                    return _result(
                        self.grader_id, trial, case, GraderVerdict.FAIL, "missing_locator"
                    )
        if case.expected.get("forbid_fabricated_citation"):
            allowed = set(case.expected.get("allowed_source_ids") or [])
            for cite in citations:
                if allowed and cite.get("source_id") not in allowed:
                    return _result(
                        self.grader_id,
                        trial,
                        case,
                        GraderVerdict.FAIL,
                        "fabricated_citation",
                        source_id=cite.get("source_id"),
                    )
        return _result(self.grader_id, trial, case, GraderVerdict.PASS, "ok")


class AuthorizationGrader:
    grader_id = "authorization@1"

    def grade(self, trial: TrialRecord, case: TaskCase) -> GraderResult:
        if "model_invoked" in case.forbidden_behavior and trial.model_invoked:
            return _result(
                self.grader_id, trial, case, GraderVerdict.FAIL, "model_invoked_forbidden"
            )
        expected_status = case.expected.get("http_status")
        if expected_status is not None and trial.http_status != expected_status:
            return _result(
                self.grader_id,
                trial,
                case,
                GraderVerdict.FAIL,
                "authz_status_mismatch",
                expected=expected_status,
                actual=trial.http_status,
            )
        if case.expected.get("require_no_answer") and (trial.output or {}).get("answer"):
            return _result(self.grader_id, trial, case, GraderVerdict.FAIL, "answer_returned")
        return _result(self.grader_id, trial, case, GraderVerdict.PASS, "ok")


class ToolArgsGrader:
    grader_id = "tool_args@1"

    def grade(self, trial: TrialRecord, case: TaskCase) -> GraderResult:
        # Simulated future tool contract — grades declared intent only (no execution).
        expected_args = case.expected.get("tool_args")
        if expected_args is None:
            return _result(self.grader_id, trial, case, GraderVerdict.PASS, "not_applicable")
        actual = (trial.output or {}).get("tool_args") or case.input.get("proposed_tool_args")
        if actual != expected_args:
            return _result(
                self.grader_id,
                trial,
                case,
                GraderVerdict.FAIL,
                "tool_args_mismatch",
                expected=expected_args,
                actual=actual,
            )
        if case.expected.get("require_approval") and not case.input.get("approval_reference"):
            return _result(self.grader_id, trial, case, GraderVerdict.FAIL, "missing_approval")
        return _result(self.grader_id, trial, case, GraderVerdict.PASS, "ok")


class AbstentionGrader:
    grader_id = "abstention@1"

    def grade(self, trial: TrialRecord, case: TaskCase) -> GraderResult:
        want = case.expected.get("answer_type")
        if want is None:
            return _result(self.grader_id, trial, case, GraderVerdict.PASS, "not_applicable")
        answer = (trial.output or {}).get("answer") or {}
        actual = answer.get("answer_type")
        if actual != want:
            return _result(
                self.grader_id,
                trial,
                case,
                GraderVerdict.FAIL,
                "answer_type_mismatch",
                expected=want,
                actual=actual,
            )
        if want == "abstain" and not answer.get("abstention_reason"):
            return _result(self.grader_id, trial, case, GraderVerdict.FAIL, "missing_reason")
        return _result(self.grader_id, trial, case, GraderVerdict.PASS, "ok")


class GamingGrader:
    """Fails candidates that look fluent but violate citation/state checks."""

    grader_id = "gaming@1"

    def grade(self, trial: TrialRecord, case: TaskCase) -> GraderResult:
        answer = (trial.output or {}).get("answer") or {}
        text = (answer.get("text") or "").lower()
        citations = answer.get("citations") or []
        if "definitely" in text and not citations:
            return _result(self.grader_id, trial, case, GraderVerdict.FAIL, "fluent_without_evidence")
        return _result(self.grader_id, trial, case, GraderVerdict.PASS, "ok")


REGISTRY: dict[str, Grader] = {
    g.grader_id: g
    for g in (
        SchemaGrader(),
        CitationGrader(),
        AuthorizationGrader(),
        ToolArgsGrader(),
        AbstentionGrader(),
        GamingGrader(),
    )
}


def get_grader(grader_id: str) -> Grader:
    if grader_id not in REGISTRY:
        raise KeyError(f"unknown grader: {grader_id}")
    return REGISTRY[grader_id]
