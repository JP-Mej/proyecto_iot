# Repository Guidelines

## Project Structure & Module Organization

- `dashboard/` contains the Flask application (`app.py`), MQTT integration, SQLite setup helpers, Jinja templates, and static CSS/JavaScript/assets.
- `arduino/` contains one ESP32 sketch per sensor module: environmental, waste-level, camera, and sound.
- `db/` provides scripts to create and inspect the local `lscc.db` database.
- Root-level Python and SQL files implement the local medallion pipeline and AWS S3/Athena workflow.
- `documentacion/` holds operational guides and generated project documents. Update the relevant Markdown guide when behavior or setup changes.

## Build, Test, and Development Commands

Create and activate a Windows virtual environment, then install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r dashboard\requirements.txt
pip install -r requirements_aws.txt
```

From `dashboard/`, copy `.env.example` to `.env`, fill in local secrets, and run:

```powershell
python crear_db.py       # initialize dashboard/lscc.db
python app.py            # serve http://localhost:5000
python ..\db\ver_db.py   # inspect stored sensor data
```

Use `python pipeline_medallon_local.py` from the repository root to build local medallion outputs. Compile and upload `.ino` files with Arduino IDE using the board documented in `README.md`.

## Coding Style & Naming Conventions

Use four spaces for Python indentation and follow PEP 8: `snake_case` for functions and variables, `UPPER_CASE` for constants. Keep Flask routes thin and place shared logic in named helper functions. In Arduino code, preserve existing C++ formatting and use descriptive hardware- or sensor-oriented identifiers. Use lowercase, underscore-separated names for new scripts. No formatter or linter is currently configured; keep changes focused and consistent with neighboring code.

## Testing Guidelines

There is no automated test suite or coverage requirement. Before submitting changes, run affected Python scripts, load the dashboard, exercise modified API routes, and verify database state with `db/ver_db.py`. For firmware changes, record the board used and confirm serial output plus MQTT publication. If adding tests, place them under `tests/` and name files `test_<module>.py` for pytest discovery.

## Commit & Pull Request Guidelines

The current history uses Conventional Commit style, for example `chore: guardar version pre-consolidacion v0.1.0`. Continue with concise prefixes such as `feat:`, `fix:`, `docs:`, or `chore:`. Pull requests should explain the change, list validation performed, link related issues, and include screenshots for dashboard UI changes. Call out database schema, environment-variable, MQTT-topic, or hardware wiring changes explicitly.

## Security & Configuration

Never commit `.env`, SQLite databases, uploaded images, generated data-lake files, Wi-Fi credentials, or real MQTT/AWS secrets. Keep safe placeholders in `.env.example`; regenerate broker password files for each deployment.
