"""Regression tests for the 2026-09-26 high findings, plus Keziah calls."""

from __future__ import annotations

import builtins
from datetime import date, datetime, timezone

import httpx
from sqlalchemy import func, select

from serah.engines.base import DecisionRequest
from serah.engines.keziah_engine import KeziahDecisionEngine
from serah.engines.mock import MockDecisionEngine
from serah.errors import EngineError
from serah.ingest import import_conversations
from serah.manual import add_concept, merge_concepts, set_candidate_status
from serah.models import EpisodeRelevance, InferenceCache, Message, ModelObservation, TaxonomyConcept
from serah.pipeline import open_session, run_demo, run_extract, run_score, run_taxonomy
from serah.scoring import score_engine
from serah.synthetic import to_chatgpt_export
from serah.taxonomy import reconstruct
from serah.temporal import ObservationPoint, replay_concept
from serah.config import get_settings


def _conversation(external_id: str, turns: list[tuple[str, str, float, str]]) -> dict:
    mapping: dict[str, dict] = {}
    parent = None
    for message_id, role, stamp, text in turns:
        node_id = f"node-{message_id}"
        mapping[node_id] = {
            "id": node_id,
            "parent": parent,
            "children": [],
            "message": {
                "id": message_id,
                "author": {"role": role},
                "create_time": stamp,
                "content": {"content_type": "text", "parts": [text]},
            },
        }
        if parent:
            mapping[parent]["children"].append(node_id)
        parent = node_id
    return {
        "id": external_id,
        "conversation_id": external_id,
        "title": "later",
        "create_time": turns[0][2],
        "current_node": parent,
        "mapping": mapping,
    }


def _ts(day: int, hour: int) -> float:
    return datetime(2024, 3, day, hour, tzinfo=timezone.utc).timestamp()


def test_later_import_does_not_leak_future_taxonomy_and_scores_new_anger():
    session = open_session()
    run_demo(session)
    later = _conversation(
        "conv-later",
        [
            (
                "x7",
                "user",
                _ts(7, 9),
                "I have to sort it today. My stomach is tight, it is urgent, and relief comes once it is done.",
            ),
            ("x3", "user", _ts(3, 20), "Still furious tonight. The anger has not gone."),
        ],
    )
    import_conversations(session, [later])
    session.commit()
    run_extract(session)
    run_taxonomy(session)
    run_score(session, "mock")
    episodes = {episode.user_text[:12]: episode.id for episode in session.scalars(select(serah_episode())).all()}
    relevant = {
        (row.episode_id, row.concept_id) for row in session.scalars(select(EpisodeRelevance)).all()
    }
    obligation = "compression.obligation_pressure"
    assert reconstruct(session, "2024-03-07")[obligation]["status"] == "proposed"
    assert (episodes["I have to so"], obligation) not in relevant
    anger_id = episodes["Still furiou"]
    assert any(episode_id == anger_id for episode_id, _concept in relevant)
    scored = session.scalar(
        select(func.count()).select_from(ModelObservation).where(ModelObservation.episode_id == anger_id)
    )
    assert scored and scored > 0
    session.close()


def serah_episode():
    from serah.models import Episode

    return Episode


def test_systemone_state_is_user_text_only():
    session = open_session()
    run_demo(session)
    seen: list[object] = []

    class Recording(MockDecisionEngine):
        def evaluate_batch(self, requests):
            seen.extend(request.state for request in requests)
            return super().evaluate_batch(requests)

    score_engine(session, Recording("recorder", 1.0, "Recorder"), get_settings(), "relevant", "run")
    assert seen
    assert all(isinstance(state, str) for state in seen)
    assert all("You sound" not in state and "Judge only" not in state for state in seen)
    session.close()


def test_scoring_keeps_completed_chunks(monkeypatch):
    session = open_session()
    run_demo(session)

    class Flaky(MockDecisionEngine):
        calls = 0

        def evaluate_batch(self, requests):
            out = []
            for request in requests:
                Flaky.calls += 1
                if Flaky.calls == 4:
                    raise EngineError("HTTP 503")
                out.append(self.evaluate(request))
            return out

    engine = Flaky("paid", 1.0, "Paid")
    try:
        score_engine(session, engine, get_settings(), "relevant", "run-1")
    except EngineError:
        pass
    kept = session.scalar(
        select(func.count()).select_from(ModelObservation).where(ModelObservation.engine_id == "paid")
    )
    cached = session.scalar(
        select(func.count()).select_from(InferenceCache).where(InferenceCache.engine_id == "paid")
    )
    assert kept == 3
    assert cached == 3
    before = Flaky.calls
    score_engine(session, engine, get_settings(), "relevant", "run-2")
    assert Flaky.calls == before + 1 or Flaky.calls > before
    session.close()


def test_reconstruction_is_stable_and_reactivation_survives():
    session = open_session()
    for index in range(12):
        add_concept(
            session,
            taxonomy_id=f"emotion.probe_{index:02d}",
            name=f"Probe {index}",
            family="emotion",
            definition="d",
            inclusion="i",
            exclusion="e",
            status="active",
            day="2024-03-05",
            rationale="",
        )
    state = reconstruct(session, "2024-03-05")
    assert all(state[f"emotion.probe_{index:02d}"]["status"] == "active" for index in range(12))
    add_concept(
        session,
        taxonomy_id="emotion.probe",
        name="Probe",
        family="emotion",
        definition="d",
        inclusion="i",
        exclusion="e",
        status="proposed",
        day="2024-03-01",
        rationale="",
    )
    set_candidate_status(session, "emotion.probe", "active", "", "2024-03-02")
    merge_concepts(session, "emotion.probe", "emotion.anger", "", "2024-03-03")
    set_candidate_status(session, "emotion.probe", "active", "", "2024-03-04")
    assert session.get(TaxonomyConcept, "emotion.probe").status == "active"
    assert reconstruct(session, "2024-03-04")["emotion.probe"]["status"] == "active"
    session.close()


def test_reimport_keeps_new_messages():
    session = open_session()
    base = to_chatgpt_export()
    import_conversations(session, base)
    session.commit()
    document = base[0]
    extra_id = "m-extra"
    parent = document["current_node"]
    document["mapping"][f"node-{extra_id}"] = {
        "id": f"node-{extra_id}",
        "parent": parent,
        "children": [],
        "message": {
            "id": extra_id,
            "author": {"role": "user"},
            "create_time": _ts(12, 9),
            "content": {"content_type": "text", "parts": ["A later note."]},
        },
    }
    document["mapping"][parent]["children"].append(f"node-{extra_id}")
    document["current_node"] = f"node-{extra_id}"
    stats = import_conversations(session, [document])
    session.commit()
    assert stats["new_messages"] == 1
    assert session.scalar(select(func.count()).select_from(Message).where(Message.external_id == extra_id)) == 1
    session.close()


def test_linear_decay_ignores_extra_midnights():
    start = datetime(2024, 3, 1, 0, tzinfo=timezone.utc)
    snapshots, _events = replay_concept(
        [ObservationPoint(start, 100.0)],
        date(2024, 3, 1),
        date(2024, 3, 4),
        decay_type="linear",
        half_life_hours=24,
        gain=1.0,
        algorithm="bounded_saturating",
    )
    levels = {item.day: item.level for item in snapshots}
    assert levels[date(2024, 3, 1)] == 50
    assert levels[date(2024, 3, 2)] == 0
    assert levels[date(2024, 3, 4)] == 0


def test_later_engine_sees_the_historical_target(tmp_path):
    session = open_session()
    run_demo(session)
    merge_concepts(
        session,
        "compression.obligation_pressure",
        "emotion.anxiety",
        "later human merge",
        "2026-09-26",
    )
    score_engine(session, MockDecisionEngine("late", 1.0, "Late"), get_settings(), "relevant", "run-late")

    def count(engine: str) -> int:
        return int(
            session.scalar(
                select(func.count())
                .select_from(ModelObservation)
                .where(
                    ModelObservation.engine_id == engine,
                    ModelObservation.concept_id == "compression.obligation_pressure",
                )
            )
            or 0
        )

    assert count("late") == count("mock")
    assert count("mock") > 0
    session.close()


def test_keziah_call_sends_user_text_and_stores_the_distribution(monkeypatch):
    monkeypatch.setenv("SERAH_KEZIAH_BASE_URL", "http://keziah.test")
    monkeypatch.setenv("SERAH_IGNORE_DOTENV", "1")
    captured: dict = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "status": "succeeded",
                "job_id": "job_1",
                "resolved_model": "mock",
                "model_version": "mock-1",
                "response": {
                    "answers": {
                        "emotion.anger": {
                            "type": "score",
                            "score": 5,
                            "probabilities": {str(index): (1.0 if index == 5 else 0.0) for index in range(10)},
                        }
                    }
                },
            }

    def fake_post(url, json, headers, timeout):  # type: ignore[no-untyped-def]
        captured["url"] = url
        captured["json"] = json
        return FakeResponse()

    real_import = builtins.__import__

    def guarded(name, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name == "keziah" or name.startswith("keziah."):
            raise ImportError
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    monkeypatch.setattr(httpx, "post", fake_post)
    engine = KeziahDecisionEngine(get_settings())
    request = DecisionRequest(
        request_id="r",
        engine_id="keziah",
        episode_id="e",
        concept_id="emotion.anger",
        concept_version=1,
        question_version=1,
        state="I am furious.",
        questions={"emotion.anger": {"type": "score", "instructions": "how strong", "criteria": ["a"] * 10}},
        evidence_hash="h",
        cache_key="c",
    )
    result = engine.evaluate(request)
    assert captured["json"]["state"] == "I am furious."
    assert "You sound" not in str(captured["json"]["state"])
    assert result.distribution
    assert result.expected_intensity is not None
    monkeypatch.delenv("SERAH_KEZIAH_BASE_URL")
    assert KeziahDecisionEngine(get_settings()).status().availability == "NOT_CONFIGURED"
