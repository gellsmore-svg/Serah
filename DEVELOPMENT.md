# Development

Python 3.12. Node 18 or newer for the UI.

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/ruff check src tests
.venv/bin/pytest

cd frontend
npm install
npm test
npm run build
```

CI runs those commands with the mock curator, the mock engines, and the fictional history. It does not download weights and it does not read API keys.

The database for normal use is `SERAH_DB_PATH` or `~/.local/share/serah/serah.sqlite`. Tests point `SERAH_DB_PATH` at a temporary file and set `SERAH_IGNORE_DOTENV=1`.

Schema changes belong in a new Alembic revision. The first revision creates the SQLAlchemy metadata. From the repository root:

```bash
SERAH_DB_PATH=/tmp/serah.sqlite .venv/bin/alembic upgrade head
```

Startup also calls `create_all`, so a development tree still opens if Alembic has not been run.

Useful commands:

```bash
serah doctor
serah models
serah demo
serah import ./export.zip
serah extract
serah taxonomy replay
serah taxonomy show
serah taxonomy show emotion.anger
serah score --engine mock
serah score --engine jev
serah replay --half-life-hours 24
serah serve
```

`serah score --engine jev` exits non-zero when no key is configured and does not write observations.

Frontend development can use `npm run dev` in `frontend/`, which proxies `/api` to port 8740. Production serving uses `frontend/dist` after `npm run build`.

Prompts are packaged under `src/serah/prompts/`. Change the file and the version directory together when the wording of an instrument changes. Question rows are versioned in the database. Editing a prompt does not rewrite old question rows by itself. A new concept version does.
