"""Repros for docs/review-2026-09-26.md. Run: .venv/bin/python scripts/review_repro.py [r1 r2 ...]"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ["SERAH_IGNORE_DOTENV"] = "1"
os.environ["SERAH_CURATOR"] = "mock"
os.environ["SERAH_EXTRACTOR"] = "mock"


def fresh_db() -> None:
    os.environ["SERAH_DB_PATH"] = str(Path(tempfile.mkdtemp(prefix="serah-r-")) / "s.sqlite")


def ts(day: int, hour: int) -> float:
    return datetime(2024, 3, day, hour, tzinfo=timezone.utc).timestamp()


def conversation(conv_id: str, turns: list[tuple[str, str, float, str]]) -> dict:
    mapping, parent = {}, None
    for msg_id, role, stamp, text in turns:
        node = f"n-{msg_id}"
        mapping[node] = {"id": node, "parent": parent, "children": [], "message": {
            "id": msg_id, "author": {"role": role}, "create_time": stamp,
            "content": {"content_type": "text", "parts": [text]}}}
        if parent:
            mapping[parent]["children"].append(node)
        parent = node
    return {"id": conv_id, "conversation_id": conv_id, "title": conv_id,
            "create_time": turns[0][2], "current_node": parent, "mapping": mapping}


def check(name):
    def deco(fn):
        def run():
            print(f"\n=== {name}")
            fresh_db()
            try:
                fn()
            except Exception as exc:  # pragma: no cover
                import traceback
                traceback.print_exc()
                print(f"  ERROR {type(exc).__name__}: {exc}")
        run.__name__ = fn.__name__
        return run
    return deco


@check("R1 incremental import: earlier day reviewed with the future taxonomy; reviewed day never re-reviewed")
def r1():
    from sqlalchemy import select
    from serah.ingest import import_conversations
    from serah.models import Episode, EpisodeRelevance
    from serah.pipeline import open_session, run_demo, run_extract, run_taxonomy
    from serah.taxonomy import reconstruct
    s = open_session()
    run_demo(s)
    later = conversation("conv-later-export", [
        ("x7", "user", ts(7, 9), "I have to sort it today. My stomach is tight, it is urgent, and relief comes once it is done."),
        ("x3", "user", ts(3, 20), "Still furious tonight. The anger has not gone."),
    ])
    import_conversations(s, [later])
    s.commit()
    run_extract(s)
    run_taxonomy(s)
    eps = {e.user_text[:12]: e.id for e in s.scalars(select(Episode)).all()}
    rel = {(r.episode_id, r.concept_id) for r in s.scalars(select(EpisodeRelevance)).all()}
    op = "compression.obligation_pressure"
    print(f"  obligation_pressure status in reconstruct(2024-03-07): {reconstruct(s, '2024-03-07').get(op, {}).get('status')}")
    print(f"  ...but the new 2024-03-07 episode is marked relevant to it: {(eps['I have to so'], op) in rel}")
    print(f"  new 2024-03-03 anger episode has any relevance row (needed to be scored): "
          f"{any(e == eps['Still furiou'] for e, _ in rel)}")


@check("R2 re-importing a newer export drops messages added to a known conversation")
def r2():
    from sqlalchemy import func, select
    from serah.ingest import import_conversations
    from serah.models import Message
    from serah.pipeline import open_session
    s = open_session()
    base = [("a1", "user", ts(1, 9), "I feel anxious."), ("a2", "assistant", ts(1, 10), "Tell me more.")]
    import_conversations(s, [conversation("c1", base)])
    s.commit()
    grown = base + [("a3", "user", ts(9, 9), "Weeks later I am furious about it.")]
    stats = import_conversations(s, [conversation("c1", grown)])
    s.commit()
    print("  second import stats:", {k: stats[k] for k in ("messages", "skipped_conversations", "warnings")})
    print("  messages stored:", s.scalar(select(func.count()).select_from(Message)), "(export now holds 3)")


@check("R3 one scoring failure discards every result already paid for")
def r3():
    from sqlalchemy import func, select
    from serah.config import get_settings
    from serah.engines.mock import MockDecisionEngine
    from serah.errors import EngineError
    from serah.models import InferenceCache, ModelObservation
    from serah.pipeline import open_session, run_demo
    from serah.scoring import score_engine

    class Flaky(MockDecisionEngine):
        calls = 0
        def evaluate_batch(self, requests):
            out = []
            for request in requests:
                Flaky.calls += 1
                if Flaky.calls == len(requests):
                    raise EngineError("HTTP 503 on the last request")
                out.append(self.evaluate(request))
            return out

    s = open_session()
    run_demo(s)
    engine = Flaky("paid_remote", 0.9, "Paid remote")
    try:
        score_engine(s, engine, get_settings(), "all-core", "run-1")
    except EngineError:
        s.commit()
    kept = s.scalar(select(func.count()).select_from(ModelObservation).where(ModelObservation.engine_id == "paid_remote"))
    cached = s.scalar(select(func.count()).select_from(InferenceCache).where(InferenceCache.engine_id == "paid_remote"))
    print(f"  engine calls made: {Flaky.calls}; observations kept: {kept}; cache rows kept: {cached}")


@check("R4 same-day human events reconstruct in random order")
def r4():
    from serah.manual import add_concept
    from serah.pipeline import open_session
    from serah.taxonomy import reconstruct
    s = open_session()
    for i in range(40):
        add_concept(s, taxonomy_id=f"emotion.probe_{i:02d}", name=f"Probe {i}", family="emotion",
                    definition="d", inclusion="i", exclusion="e", status="active", day="2024-03-05", rationale="")
    state = reconstruct(s, "2024-03-05")
    statuses = [state[f"emotion.probe_{i:02d}"]["status"] for i in range(40)]
    print("  live status: active x40; reconstructed:", {v: statuses.count(v) for v in set(statuses)})


@check("R5 CONCEPT_REACTIVATED is not reconstructed")
def r5():
    from serah.manual import add_concept, merge_concepts, set_candidate_status
    from serah.models import TaxonomyConcept
    from serah.pipeline import open_session
    from serah.taxonomy import reconstruct
    s = open_session()
    add_concept(s, taxonomy_id="emotion.probe", name="Probe", family="emotion", definition="d",
                inclusion="i", exclusion="e", status="proposed", day="2024-03-01", rationale="")
    set_candidate_status(s, "emotion.probe", "active", "", "2024-03-02")
    merge_concepts(s, "emotion.probe", "emotion.anger", "", "2024-03-03")
    set_candidate_status(s, "emotion.probe", "active", "", "2024-03-04")
    print("  live:", s.get(TaxonomyConcept, "emotion.probe").status,
          "| reconstruct(2024-03-04):", reconstruct(s, "2024-03-04")["emotion.probe"]["status"])


@check("R6 linear decay depends on how many midnights fall inside the interval")
def r6():
    from datetime import timedelta
    from serah.temporal import ObservationPoint, replay_concept
    def level_after(start_hour: int) -> float:
        at = datetime(2024, 3, 1, start_hour, tzinfo=timezone.utc)
        snaps, _ = replay_concept([ObservationPoint(at, 100.0)], date(2024, 3, 1), date(2024, 3, 4),
                                  decay_type="linear", half_life_hours=24, gain=1.0, algorithm="bounded_saturating")
        return {sn.day: sn.level for sn in snaps}
    a = level_after(0)
    print("  obs at 00:00, half-life 24h. Documented: 50 at 24h, 0 at 48h.")
    print("  snapshot after 24h:", round(a[date(2024, 3, 1)], 2), "| after 48h:", round(a[date(2024, 3, 2)], 2),
          "| after 96h:", round(a[date(2024, 3, 4)], 2))
    del timedelta


@check("R7 an engine scored later sees a different target set than one scored earlier")
def r7():
    from sqlalchemy import func, select
    from serah.config import get_settings
    from serah.engines.mock import MockDecisionEngine
    from serah.manual import merge_concepts
    from serah.models import ModelObservation
    from serah.pipeline import open_session, run_demo
    from serah.scoring import score_engine
    s = open_session()
    run_demo(s)
    merge_concepts(s, "compression.obligation_pressure", "emotion.anxiety", "later human merge", "2026-09-26")
    score_engine(s, MockDecisionEngine("late_engine", 1.0, "Late"), get_settings(), "relevant", "run-late")
    s.commit()
    def n(engine: str) -> int:
        return s.scalar(select(func.count()).select_from(ModelObservation).where(
            ModelObservation.engine_id == engine, ModelObservation.concept_id == "compression.obligation_pressure"))
    print(f"  obligation_pressure observations: mock={n('mock')} late_engine={n('late_engine')} "
          "(same 2024 evidence, merge dated 2026)")


@check("R8 API: every request re-initialises the database; any Host header is served")
def r8():
    import time
    from fastapi.testclient import TestClient
    from serah import db as dbmod
    from serah.api import app
    from serah.pipeline import open_session, run_demo
    s = open_session()
    run_demo(s)
    s.close()
    calls = {"n": 0}
    original = dbmod.init_database
    def counting(*a, **k):
        calls["n"] += 1
        return original(*a, **k)
    import serah.db
    serah.db.init_database = counting
    import serah.pipeline as pl
    pl.session_scope.__globals__["init_database"] = counting
    with TestClient(app) as c:
        t0 = time.perf_counter()
        for _ in range(50):
            c.get("/api/taxonomy")
        per = (time.perf_counter() - t0) / 50 * 1000
        rebind = c.get("/api/experiments", headers={"Host": "attacker.example"})
    print(f"  init_database calls for 50 GET /api/taxonomy: {calls['n']}; mean {per:.1f} ms/request")
    print(f"  Host: attacker.example -> HTTP {rebind.status_code}, {len(rebind.content)} bytes")


@check("R9 LLM-baseline distributions with out-of-scale bins are accepted")
def r9():
    from serah.engines.translate import from_bin_distribution
    out = from_bin_distribution({"150": 0.5, "250": 0.5}, method="llm_instrument_bins")
    print("  bins {150:0.5, 250:0.5} -> expected_intensity", out["expected_intensity"])


if __name__ == "__main__":
    only = set(sys.argv[1:])
    for fn in [r1, r2, r3, r4, r5, r6, r7, r8, r9]:
        if not only or fn.__name__ in only:
            fn()
