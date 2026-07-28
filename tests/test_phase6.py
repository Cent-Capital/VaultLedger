"""Phase 6 privacy-switch acceptance criteria."""

from __future__ import annotations

import json
import socket

import pytest

from vaultledger.generate.ollama import GenerationError
from vaultledger.retrieve.types import ScoredChunk
from vaultledger.route import CloudConsentRequired, answer_with_privacy
from vaultledger.schemas import Chunk


class _Retriever:
    variant = "B_hybrid"

    def retrieve(self, query: str, k: int = 20) -> list[ScoredChunk]:
        text = "The March closing balance was $4,207.55."
        return [
            ScoredChunk(
                chunk=Chunk(
                    chunk_id="c0", doc_id="d0", text=text, page=1,
                    char_start=0, char_end=len(text),
                ),
                score=0.9, rank=1, source="hybrid",
            )
        ]


class _Generator:
    def __init__(self, model: str) -> None:
        self.model = model
        self.calls = 0

    def generate_json(self, prompt: str, schema: dict, *, temperature: float = 0.0) -> str:
        self.calls += 1
        return json.dumps(
            {
                "answer_text": "The balance was $4,207.55.",
                "abstained": False,
                "citations": [
                    {"chunk_id": "c0", "snippet": "March closing balance was $4,207.55"}
                ],
            }
        )


class _Unavailable:
    def generate_json(self, prompt: str, schema: dict, *, temperature: float = 0.0) -> str:
        raise GenerationError("provider offline")


def test_local_mode_never_touches_cloud_or_socket(monkeypatch: pytest.MonkeyPatch):
    local = _Generator("local")
    cloud = _Generator("cloud")

    def blocked_socket(*args, **kwargs):
        raise AssertionError("local routing attempted a network call")

    monkeypatch.setattr(socket, "socket", blocked_socket)
    result = answer_with_privacy(
        "balance?", _Retriever(), local,
        local_model="ollama/qwen3:8b", mode="local",
        cloud_generator=cloud, cloud_model="hosted/kimi",
    )
    assert local.calls == 1
    assert cloud.calls == 0
    assert result.answer.data_left_machine is False
    assert result.answer.privacy_mode == "local"
    assert result.answer.model_used == "ollama/qwen3:8b"


def test_cloud_requires_session_consent():
    with pytest.raises(CloudConsentRequired):
        answer_with_privacy(
            "balance?", _Retriever(), _Generator("local"),
            local_model="local", mode="cloud",
            cloud_generator=_Generator("cloud"), cloud_model="hosted/kimi",
        )


def test_cloud_flips_badge_model_and_routing_record():
    result = answer_with_privacy(
        "balance?", _Retriever(), _Generator("local"),
        local_model="local", mode="cloud", cloud_consent=True,
        cloud_generator=_Generator("cloud"), cloud_model="hosted/kimi",
    )
    answer = result.answer
    assert answer.data_left_machine is True
    assert answer.privacy_mode == "cloud"
    assert answer.model_used == "hosted/kimi"
    assert answer.tier == "T2"
    assert answer.routing.chosen_model == "hosted/kimi"


def test_cloud_failure_after_attempt_preserves_egress_status():
    local = _Generator("local")
    result = answer_with_privacy(
        "balance?", _Retriever(), local,
        local_model="ollama/qwen3:8b", mode="cloud", cloud_consent=True,
        cloud_generator=_Unavailable(), cloud_model="hosted/kimi",
    )
    assert result.degraded
    assert result.notice == (
        "Cloud request failed — answered locally; data may have left your machine"
    )
    assert result.answer.data_left_machine is True
    assert result.answer.privacy_mode == "cloud"
    assert result.answer.model_used == "ollama/qwen3:8b"
    assert result.answer.routing.chosen_tier == "T1"
    assert result.answer.routing.allowed_tiers == ["T0", "T1", "T2"]
    assert "after egress attempt" in result.answer.routing.reason
    assert any(e.guard == "cloud_availability" for e in result.answer.guardrail_events)


def test_cloud_unconfigured_degrades_before_egress_with_no_badge():
    result = answer_with_privacy(
        "balance?", _Retriever(), _Generator("local"),
        local_model="ollama/qwen3:8b", mode="cloud", cloud_consent=True,
        cloud_generator=None, cloud_model="hosted/kimi",
    )
    assert result.degraded
    assert result.notice == "Cloud unavailable — answered locally"
    assert result.answer.data_left_machine is False
    assert result.answer.privacy_mode == "local"
    assert result.answer.model_used == "ollama/qwen3:8b"
    assert "before egress" in result.answer.routing.reason
