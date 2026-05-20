# Usage

## What runs here

One **Azure Functions** host loads every function folder in the repo. Each folder with a `function.json` defines a separate function (HTTP, timer, or queue trigger). The host configuration is in `host.json` at the repository root.

## Local and CI expectations

- **CI** (`azure-pipelines.yml`): triggered on branch `dev`; uses Python 3.12, installs dependencies with `uv pip install --target=./.python_packages/lib/site-packages -r requirements.txt`, and publishes a zip artifact.
- **Local**: Azure Functions Core Tools and the same environment variables as deployed environments are expected for meaningful runs.

## Primary HTTP entrypoint (VOR AI)

See `feature_01_vor_ai_langgraph_http.md`. Callers typically send a JSON body whose top-level key **`userQuery`** wraps the object consumed by `GraphLogisticsBot.run` in `collabgpt_lg/bot.py` (fields such as `organization`, `message`, `existingMessages`, `source`, `userId`, `userDisplayName`, `teamsId`, `threadId`).

The function `collabgpt_lg/__init__.py` also reads a query string parameter `userQuery`, as different interfaces may send it at that level.

## Other HTTP functions

- **Logistics summary warnings** — `feature_04_logistics_summary_warnings_http.md`
- **Vessels in transit / AIS** — `feature_05_vessels_ais_location_http.md`
- **Bulk indexing (CHEVRON)** — `feature_03_chevron_ai_search_index_ingestion.md`

## Timed and queue-driven functions

No direct HTTP invoke; they run on schedules or queue messages. See feature docs **02**, **03**, and **06** in this folder. **06** (PO shipments timer) is **dormant**: it depended on Flowise, which has been decommissioned in favour of LangFlow; that flow was not reimplemented yet.

## Pointers to technical detail

- Layout of folders and files: `../technical/project_layout.md`
- Graph and agent flow: `../technical/architecture.md`
- Configuration: `../technical/environment_variables.md`
- Tests: `../technical/testing.md`
