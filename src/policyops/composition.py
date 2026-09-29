"""Composition root — wire settings to adapters and services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from policyops.adapters import LocalModelClient, ReplayModelClient
from policyops.config import Settings, load_settings
from policyops.contracts.ports import ModelClient
from policyops.services import AnswerService


@dataclass
class AppContainer:
    settings: Settings
    client: ModelClient
    answer_service: AnswerService


def build_container(settings: Settings | None = None) -> AppContainer:
    settings = settings or load_settings()
    fixture_pack = Path(settings.fixture_pack)
    fault = settings.fault_scenario
    if settings.adapter == "local":
        client: ModelClient = LocalModelClient(fixture_pack, fault_scenario=fault)
    else:
        client = ReplayModelClient(
            fixture_pack,
            fault_scenario=fault,
            configuration_id=settings.fingerprint(),
        )
    return AppContainer(
        settings=settings,
        client=client,
        answer_service=AnswerService(client),
    )
