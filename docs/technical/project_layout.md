<!-- docs_as_of: 2026-05-14T11:53:44 -->

# Project layout

Repository root is a **Python Azure Functions** app: each first-level folder with `function.json` is one deployed function. Shared code lives under `shared/`; cross-cutting configuration in `config.py`.

```text
vor-collabgpt-functions/
├── azure-pipelines.yml      # CI: dev branch, Python 3.12, uv install, zip artifact
├── host.json                # Functions host v2; queue messageEncoding none; extension bundle 4.x
├── config.py                # Central getenv() wrappers (fail-fast import side effects)
├── requirements.txt         # Pinned dependencies for deployment
├── requirements_dev.txt     # Dev-only additions (if used locally)
├── pyproject.toml           # Black configuration
├── pytest.ini               # Pytest logging format
├── collabgpt_lg/            # Feature 01 — LangGraph VOR AI (HTTP)
│   ├── __init__.py          # HTTP main → GraphLogisticsBot
│   ├── bot.py               # GraphLogisticsBot, message history, reference extraction
│   ├── graph.py             # StateGraph builder, nodes (parser, router, tools, SQL, notifications)
│   ├── graph_types.py       # GraphState, ConfigSchema, reducers
│   ├── endpoints.py         # Customer/DataEnhancer/AI Search/VorSearch (incl. index-backed flights/voyages/shipments)
│   ├── endpoints_base.py    # Shared aiohttp/auth patterns for endpoint families
│   ├── tools.py             # @tool wrappers and tools_by_org
│   ├── tool_utils.py        # Tool call extraction helpers
│   ├── prompts.py           # LLM prompts, structured output schemas
│   ├── utils.py             # org_state, LLM call accounting, dataframe helpers
│   ├── org_config.py        # vor_search_result_filters, vor_url_list (per-org VOR UI links)
│   ├── function.json        # HTTP trigger GET+POST
│   └── tests/               # Endpoint, graph, integration tests
├── collabgpt_check_subscriptions/   # Feature 02 — timer subscription sweep
├── collabgpt_check_subscription_queue/  # Feature 02 — queue consumer
├── collabgpt_get_flights/           # Feature 03 — timer flight index ingestion
├── collabgpt_get_flights_bulk/      # Feature 03 — HTTP bulk flight indexing
├── collabgpt_get_road_transport_jobs/   # Feature 03 — timer RTJ ingestion
├── collabgpt_get_road_transport_jobs_bulk/  # Feature 03 — HTTP RTJ bulk
├── collabgpt_get_priority_items/    # Feature 03 — timer priority index from Redis
├── collabgpt_get_ls_warnings/         # Feature 04 — HTTP logistics summary cache
├── collabgpt_get_vessels_in_transit_by_location/  # Feature 05 — HTTP + util + JSON mappings
├── collabgpt_po_shipments_trigger/    # Feature 06 — timer (dormant; legacy Flowise client; LangFlow TBD)
├── shared/
│   ├── cosmos.py            # AIS / Cosmos reads for vessels feature
│   ├── redis_cache.py       # Generic Redis cache helpers
│   ├── index_uploader.py    # IndexUploader → AI Search indexing POSTs
│   ├── user_actions.py      # Active subscriptions HTTP client
│   ├── user_management.py   # User lookup helpers
│   ├── slack.py             # @slack_logging decorator
│   ├── mixpanel.py          # track_event helper
│   ├── utils.py             # Shared dataframe/JSON utilities
│   └── ids/                 # Regex packs per org (container, MR, etc.)
└── tests/                   # Root-level pytest modules (redis, utils, user_management, ls_warnings)
```

## Key symbols (quick index)

| Symbol | Module | Role |
| ------ | ------ | ---- |
| `main` | Each `*/__init__.py` with `function.json` | Azure Function entry |
| `GraphLogisticsBot` | `collabgpt_lg/bot.py` | Builds LLMs, runs compiled graph, shapes HTTP response |
| `graph_builder` | `collabgpt_lg/graph.py` | Returns `StateGraph` before `.compile()` |
| `tools_by_org` | `collabgpt_lg/tools.py` | Org → retrieval/action tool lists |
| `vor_url_list`, `vor_search_result_filters` | `collabgpt_lg/org_config.py` | Per-org VOR page URLs and global-search entity filters for prompts |
| `trim_data` | `collabgpt_lg/utils.py` | Trims tool outputs for router; keeps `status`, `system_message` |
| `apis_by_org` | `collabgpt_check_subscriptions/__init__.py` | Subscribeable entity type → endpoint class (timer + notification router) |
| `IndexUploader` | `shared/index_uploader.py` | Batched POST to indexing URLs |
| `slack_logging` | `shared/slack.py` | Wraps functions for Slack error reporting |
