"""End-to-end checks on the fictional history and the layer boundaries."""

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from serah.api import app
from serah.ids import stable_id
from serah.models import Episode, Message, ModelObservation
from serah.pipeline import open_session, run_demo, run_replay, run_score, run_taxonomy
from serah.scoring import cache_key
from serah.taxonomy import reconstruct


def _demo():
    session = open_session()
    result = run_demo(session)
    return session, result


def test_import_is_stable_ordered_and_idempotent():
    session = open_session()
    from serah.ingest import import_conversations
    from serah.synthetic import to_chatgpt_export

    first = import_conversations(session, to_chatgpt_export())
    session.commit()
    messages = session.scalars(select(Message).order_by(Message.ordinal)).all()
    timestamps = [message.timestamp for message in messages if message.timestamp]
    assert timestamps == sorted(timestamps)
    branch = [message for message in messages if message.external_id == "m-branch-fury"]
    assert branch and branch[0].on_current_branch is False
    expected = stable_id("chatgpt", "message", "conv-demo", "m-d3")
    stored = next(message.id for message in messages if message.external_id == "m-d3")
    assert stored == expected
    second = import_conversations(session, to_chatgpt_export())
    session.commit()
    assert second["messages"] == 0
    assert second["new_messages"] == 0
    assert first["warnings"] >= 1
    session.close()


def test_assistant_words_are_not_user_evidence_and_taxonomy_is_causal():
    session, result = _demo()
    episodes = session.scalars(select(Episode)).all()
    assert all("You sound" not in episode.user_text for episode in episodes)
    film = [episode for episode in episodes if "film I am only describing" in episode.user_text]
    assert film == []
    library = [episode for episode in episodes if "library closes" in episode.user_text]
    assert library == []
    anger_episodes = [episode for episode in episodes if "emotion.anger" in episode.direct_states]
    assert anger_episodes
    assert all("furious" in episode.user_text.lower() or "anger" in episode.user_text.lower() for episode in anger_episodes)
    before = reconstruct(session, "2024-03-10")
    after = reconstruct(session, "2024-03-11")
    assert before["compression.obligation_pressure"]["status"] == "candidate"
    assert after["compression.obligation_pressure"]["status"] == "active"
    assert after["emotion.anger"]["status"] == "active"
    assert "compression.obligation_pressure" not in reconstruct(session, "2024-03-05")
    again = run_taxonomy(session)
    assert again["skipped"] >= 1
    assert result["taxonomy"]["activated"] >= 1
    session.close()


def test_replay_changes_with_half_life_and_keeps_observations():
    session, result = _demo()
    experiment_id = result["experiment_id"]
    before = session.scalars(select(ModelObservation)).all()
    before_ids = sorted(row.id for row in before)
    client_levels = _anger_levels(session, experiment_id, "mock")
    assert client_levels["2024-03-03"] > client_levels["2024-03-04"]
    assert client_levels["2024-03-04"] > 0
    from serah.models import Experiment
    from serah.pipeline import create_experiment

    source = session.get(Experiment, experiment_id)
    cloned = create_experiment(
        session,
        name="shorter half-life",
        engines=list(source.engines),
        decay_type=source.decay_type,
        half_life_hours=24,
        activation_gain=source.activation_gain,
        reservoir_update=source.reservoir_update,
        core_scoring_mode=source.core_scoring_mode,
    )
    run_replay(session, cloned.id)
    shorter = _anger_levels(session, cloned.id, "mock")
    assert shorter["2024-03-04"] < client_levels["2024-03-04"]
    after_ids = sorted(row.id for row in session.scalars(select(ModelObservation)).all())
    assert after_ids == before_ids
    mock = [row.expected_intensity for row in before if row.engine_id == "mock" and row.concept_id == "emotion.anger"]
    other = [
        row.expected_intensity
        for row in before
        if row.engine_id == "mock_conservative" and row.concept_id == "emotion.anger"
    ]
    assert mock and other
    assert mock != other
    run_replay(session, experiment_id)
    assert _anger_levels(session, experiment_id, "mock") == client_levels
    session.close()


def test_cache_identity_changes_with_the_question():
    one = cache_key("mock", "bias:1", "abc", "emotion.anger", 1, 1, "question")
    two = cache_key("mock", "bias:1", "abc", "emotion.anger", 1, 2, "question")
    assert one != two


def test_unavailable_engine_does_not_invent_scores():
    session = open_session()
    try:
        run_score(session, "jev")
        raised = False
    except Exception:
        raised = True
    assert raised
    assert session.scalar(select(func.count()).select_from(ModelObservation)) in {None, 0}
    session.close()


def test_api_series_day_and_drilldown():
    session, result = _demo()
    session.close()
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        listed = client.get("/api/experiments")
        assert listed.status_code == 200
        experiment_id = result["experiment_id"]
        series = client.get(
            "/api/series",
            params={"experiment_id": experiment_id, "concept_id": "emotion.anger", "mode": "reservoir"},
        )
        assert series.status_code == 200
        body = series.json()
        assert {line["engine_id"] for line in body["series"]} == {"mock", "mock_conservative"}
        raw = client.get(
            "/api/series",
            params={"experiment_id": experiment_id, "concept_id": "emotion.anger", "mode": "raw"},
        )
        point = raw.json()["series"][0]["points"][0]
        detail = client.get(f"/api/observations/{point['observation_id']}", params={"experiment_id": experiment_id})
        assert detail.status_code == 200
        payload = detail.json()
        assert payload["episode"]["user_text"]
        assert payload["observation"]["distribution"]
        day = client.get(
            "/api/days/2024-03-03",
            params={"experiment_id": experiment_id, "engine_id": "mock"},
        )
        assert day.status_code == 200
        assert any(state["concept_id"] == "emotion.anger" for state in day.json()["states"])
        concepts = client.get("/api/taxonomy").json()["concepts"]
        assert any(concept["id"] == "compression.obligation_pressure" for concept in concepts)
        models = client.get("/api/models").json()["engines"]
        jev = next(item for item in models if item["engine_id"] == "jev")
        assert jev["availability"] == "NOT_CONFIGURED"
        mock = next(item for item in models if item["engine_id"] == "mock")
        assert mock["availability"] == "AVAILABLE"


def _anger_levels(session, experiment_id, engine_id) -> dict[str, float]:
    from serah.models import DailySnapshot

    rows = session.scalars(
        select(DailySnapshot).where(
            DailySnapshot.experiment_id == experiment_id,
            DailySnapshot.engine_id == engine_id,
        )
    ).all()
    levels = {}
    for row in rows:
        payload = (row.states or {}).get("emotion.anger")
        if payload and payload.get("level") is not None:
            levels[row.day] = payload["level"]
    return levels


def test_multiple_engines_are_not_averaged():
    session, _result = _demo()
    rows = session.scalars(
        select(ModelObservation).where(ModelObservation.concept_id == "emotion.gratitude")
    ).all()
    by_engine = {}
    for row in rows:
        by_engine.setdefault(row.engine_id, []).append(row.expected_intensity)
    assert set(by_engine) >= {"mock", "mock_conservative"}
    session.close()


def test_explicit_revision_is_versioned_and_a_locked_suggestion_is_not_applied():
    from serah.manual import human_revise
    from serah.questions import current_version
    from serah.schemas import DefinitionSuggestion
    from serah.taxonomy import _apply_suggestion

    session = open_session()
    human_revise(
        session,
        "emotion.anger",
        "A heated push-back against something that feels wrong.",
        "The user describes heat or fury.",
        "Do not use for mere blockage.",
        "Explicit human revision.",
        "2024-04-01",
    )
    assert current_version(session, "emotion.anger").version == 2
    stats = {"suggestions": 0}
    _apply_suggestion(
        session,
        "2024-04-02",
        DefinitionSuggestion(
            concept_id="emotion.calm",
            definition="A different definition that must not apply.",
            inclusion_guidance="n/a",
            exclusion_guidance="n/a",
            rationale="curator suggestion",
        ),
        None,
        "mock",
        None,
        0,
        stats,
    )
    assert current_version(session, "emotion.calm").version == 1
    assert stats["suggestions"] == 1
    session.close()


def test_alembic_upgrade_creates_tables(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config

    database = tmp_path / "migrated.sqlite"
    monkeypatch.setenv("SERAH_DB_PATH", str(database))
    monkeypatch.setenv("SERAH_IGNORE_DOTENV", "1")
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    assert database.exists()