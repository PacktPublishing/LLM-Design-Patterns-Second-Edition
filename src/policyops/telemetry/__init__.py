"""Redacted OpenTelemetry-compatible telemetry facade."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult

ALLOWED_ATTRS = frozenset(
    {
        "tenant_id",
        "actor_id",
        "trace_id",
        "request_id",
        "configuration_id",
        "adapter",
        "status",
        "error_code",
        "http.method",
        "http.route",
        "http.status_code",
    }
)

_RECORDED: list[dict[str, Any]] = []


class InMemorySpanExporter(SpanExporter):
    def export(self, spans) -> SpanExportResult:  # type: ignore[no-untyped-def]
        for s in spans:
            _RECORDED.append(
                {
                    "name": s.name,
                    "attributes": {
                        k: v
                        for k, v in dict(s.attributes or {}).items()
                        if k in ALLOWED_ATTRS
                    },
                }
            )
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None


_provider: TracerProvider | None = None


def setup_telemetry(service_name: str = "policyops") -> None:
    global _provider
    if _provider is not None:
        return
    _provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    _provider.add_span_processor(SimpleSpanProcessor(InMemorySpanExporter()))
    trace.set_tracer_provider(_provider)


def recorded_spans() -> list[dict[str, Any]]:
    return list(_RECORDED)


def clear_spans() -> None:
    _RECORDED.clear()


@contextmanager
def span(name: str, attributes: dict[str, Any] | None = None) -> Iterator[None]:
    setup_telemetry()
    tracer = trace.get_tracer("policyops")
    safe = {k: v for k, v in (attributes or {}).items() if k in ALLOWED_ATTRS}
    with tracer.start_as_current_span(name, attributes=safe):
        yield
