"""Command line for import, scoring, replay, and the local UI."""

from __future__ import annotations

from pathlib import Path

import typer
from sqlalchemy import select

from serah import __version__
from serah.config import get_settings
from serah.errors import EngineUnavailable, SerahError
from serah.models import Experiment, ModelObservation
from serah.pipeline import (
    create_experiment,
    doctor_report,
    ensure_database,
    open_session,
    run_demo,
    run_extract,
    run_import,
    run_replay,
    run_score,
    run_taxonomy,
    status_report,
)
from serah.queries import concept_detail, list_concepts

app = typer.Typer(no_args_is_help=True, add_completion=False)
taxonomy_app = typer.Typer(no_args_is_help=True)
app.add_typer(taxonomy_app, name="taxonomy")


@app.command("import")
def import_cmd(path: Path) -> None:
    """Import a ChatGPT export (json file, directory, or zip)."""
    ensure_database()
    session = open_session()
    stats = run_import(session, path)
    session.close()
    typer.echo(
        f"imported {stats['conversations']} conversations, {stats['messages']} messages, "
        f"skipped {stats['skipped_conversations']} conversations, {stats['warnings']} warnings"
    )


@app.command()
def status() -> None:
    """Show local counts. No personal text is printed."""
    ensure_database()
    session = open_session()
    report = status_report(session)
    session.close()
    typer.echo(f"serah {report['version']}")
    typer.echo(
        f"conversations {report['conversations']}  messages {report['messages']}  "
        f"episodes {report['episodes']}  experiments {report['experiments']}"
    )
    typer.echo(f"concepts {report['concepts']}")
    typer.echo(f"observations {report['observations']}")


@app.command()
def extract() -> None:
    """Extract emotional episodes from imported user messages."""
    ensure_database()
    session = open_session()
    stats = run_extract(session)
    session.close()
    typer.echo(f"episodes {stats['episodes']}  skipped {stats['skipped']}  already {stats['already']}")


@taxonomy_app.command("replay")
def taxonomy_replay() -> None:
    """Run the daily taxonomy curator in causal order."""
    ensure_database()
    session = open_session()
    stats = run_taxonomy(session)
    session.close()
    typer.echo(
        f"days {stats['days']}  skipped {stats['skipped']}  "
        f"proposed {stats['proposed']}  activated {stats['activated']}"
    )


@taxonomy_app.command("show")
def taxonomy_show(concept_id: str | None = None) -> None:
    """List concepts, or show one concept without dumping episode text."""
    ensure_database()
    session = open_session()
    if concept_id:
        detail = concept_detail(session, concept_id)
        typer.echo(
            f"{detail['id']}  {detail['name']}  {detail['family']}  {detail['status']}  "
            f"v{detail['version']}  support_days {detail['support_count']}"
        )
        typer.echo(detail["definition"])
    else:
        for concept in list_concepts(session):
            lock = "locked" if concept["locked"] else "open"
            typer.echo(
                f"{concept['id']:36}  {concept['status']:12}  {lock:6}  {concept['name']}"
            )
    session.close()


@app.command()
def models() -> None:
    """Report engine availability. Missing engines do not stop Serah."""
    report = doctor_report()
    for engine in report["engines"]:
        typer.echo(f"{engine['engine_id']:18}  {engine['availability']:16}  {engine['detail']}")


@app.command()
def score(
    engine: str = typer.Option(..., "--engine"),
    mode: str = typer.Option(None, "--mode"),
) -> None:
    """Score stored episodes with one decision engine."""
    ensure_database()
    session = open_session()
    try:
        stats = run_score(session, engine, mode=mode)
    except (EngineUnavailable, SerahError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=3) from exc
    finally:
        session.close()
    typer.echo(f"scored {stats['scored']}  cached {stats['cached']}  skipped {stats['skipped']}")


@app.command()
def replay(
    experiment: str | None = typer.Option(None, "--experiment"),
    half_life_hours: float | None = typer.Option(None, "--half-life-hours"),
    decay: str | None = typer.Option(None, "--decay"),
    gain: float | None = typer.Option(None, "--gain"),
) -> None:
    """Replay reservoirs. A new half-life clones the experiment and keeps observations."""
    ensure_database()
    settings = get_settings()
    session = open_session()
    source = session.get(Experiment, experiment) if experiment else _latest(session)
    if half_life_hours is not None or decay is not None or gain is not None:
        if source is None:
            engines = _engines_with_observations(session) or ["mock", "mock_conservative"]
            source_engines = engines
            source_decay = settings.decay
            source_gain = settings.activation_gain
            source_update = settings.reservoir_update
            source_mode = settings.scoring_mode
            source_name = "replay"
            source_hours = settings.half_life_hours
        else:
            source_engines = list(source.engines)
            source_decay = source.decay_type
            source_gain = source.activation_gain
            source_update = source.reservoir_update
            source_mode = source.core_scoring_mode
            source_name = source.name
            source_hours = source.half_life_hours
        chosen_hours = half_life_hours if half_life_hours is not None else source_hours
        created = create_experiment(
            session,
            name=f"{source_name} / {chosen_hours}h",
            engines=source_engines,
            decay_type=decay or source_decay,
            half_life_hours=chosen_hours,
            activation_gain=gain if gain is not None else source_gain,
            reservoir_update=source_update,
            core_scoring_mode=source_mode,
            notes="Cloned so raw observations stay attached to the previous experiment.",
        )
        target_id = created.id
    else:
        if source is None:
            typer.echo("no experiment to replay", err=True)
            raise typer.Exit(code=2)
        target_id = source.id
    stats = run_replay(session, target_id)
    session.close()
    typer.echo(f"experiment {target_id}  days {stats['days']}  engines {', '.join(stats['engines'])}")


@app.command()
def demo() -> None:
    """Load the fictional history and run the offline path."""
    ensure_database()
    session = open_session()
    result = run_demo(session)
    session.close()
    typer.echo(f"experiment {result['experiment_id']}")
    typer.echo(
        f"messages {result['import']['messages']}  episodes {result['extract']['episodes']}  "
        f"taxonomy days {result['taxonomy']['days']}"
    )
    typer.echo("next: serah serve")


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8740) -> None:
    """Serve the API and, if built, the research UI."""
    import uvicorn

    ensure_database()
    uvicorn.run("serah.api:app", host=host, port=port, factory=False)


@app.command()
def doctor() -> None:
    """Check the local install. Unavailable models are reported, not fatal."""
    report = doctor_report()
    for check in report["checks"]:
        typer.echo(f"{'ok' if check['ok'] else 'FAIL':4}  {check['name']:12}  {check['detail']}")
    for engine in report["engines"]:
        typer.echo(f"    {engine['engine_id']:18}  {engine['availability']}")
    if not report["ok"]:
        raise typer.Exit(code=1)


@app.command()
def version() -> None:
    typer.echo(__version__)


def _latest(session):
    return session.scalar(select(Experiment).order_by(Experiment.created_at.desc()))


def _engines_with_observations(session) -> list[str]:
    rows = session.scalars(select(ModelObservation.engine_id).distinct()).all()
    return list(rows)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
