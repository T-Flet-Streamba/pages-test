# Feature 01 — VOR AI (LangGraph) HTTP function

## Summary

**CollabGPT LangGraph** (`collabgpt_lg`) exposes an HTTP-triggered Azure Function that runs a compiled **LangGraph** workflow (`graph_builder().compile()` in `collabgpt_lg/graph.py`) to answer logistics questions using org-scoped tools, optional **DuckDB** SQL over retrieved datasets, and optional **Langflow** notification / subscription agents when allowed.

## Primary surface

- **Trigger**: HTTP GET/POST (`collabgpt_lg/function.json`, `authLevel: function`).
- **Entry**: `collabgpt_lg/__init__.py` → `main` → `GraphLogisticsBot().run(query)`.
- **Core types**: `GraphState`, `ConfigSchema` in `collabgpt_lg/graph_types.py`.

## Supported organisations

Driven by `config.ai_behaviour.supported_orgs` (`SUPPORTED_ORGS` env var, pipe-separated). Per-org tools are defined in `collabgpt_lg/tools.py` (`tools_by_org`). Time zones live in `config.org_time_zones`. The org key **`Shell UK`** is unchanged in requests and config; user-facing answers refer to the organisation as **Adura** (see `glossary` / `answer_guidelines` in `collabgpt_lg/prompts.py`).

| Org key (examples from code) | Retrieval tools (high level) | Action tools |
| ---------------------------- | ----------------------------- | ------------ |
| `CHEVRON` | Containers, flights (**VOR AI Search** `find_flights`), global search, logistics summary, MRs, priorities, RTJs, shipments, voyage manifests, work orders | None in `tools_by_org` (empty `action` list) |
| `Shell UK` | Containers, **Vor Search** `find_flights` and `find_voyages` (structured filters + JSON `date_ranges` / `sort`; all-digit voyage numbers resolved via ID lookup first), flight requests, `vor_global_search` | Flight request approve/reject |
| `ExxonMobilGuyana` | Dancer cargo events, CCU hires, **Vor Search** `find_flights`, `find_shipments`, `find_voyages`, `vor_global_search` | None |

## Request and response shape

The bot expects a **dict** (see `GraphLogisticsBot.run` in `collabgpt_lg/bot.py`): at minimum `organization` and `message`; optional `existingMessages`, `source`, `userId`, `userDisplayName`, `teamsId`, `threadId`, etc.

The HTTP layer passes `userQuery` from JSON body or query string into `run`. Responses are JSON with fields including `message`, `used_tools`, `llm_calls`, `tokens_count`, `tokens_cost`, `likely_reference_numbers`, and legacy-compatible `tools_used` / `tools_params`.

## Retrieval behaviour (notable)

- **Voyage numbers:** for `find_voyages`, an all-digit `search_term` is tried as a voyage ID via `VoyagesByID` before the Vor Search index pipeline (`VoyagesByDescriptionVorSearch.query` in `collabgpt_lg/endpoints.py`).
- **Global vs typed search:** `vor_global_search` is for cross-entity or unstructured lookup; when a typed `find_*` tool exists and the user needs **time filtering** on that entity type, the agent should prefer the typed tool (documented on `vor_global_search_wrapper` in `collabgpt_lg/tools.py`).
- **Org-specific prompt context:** VOR page links and global-search entity-type filters per org live in `collabgpt_lg/org_config.py` (`vor_url_list`, `vor_search_result_filters`), shared by prompts and endpoint URL mapping.

## Constraints and guardrails

- **Action tools** only when org is in `ACTION_ALLOWED_ORGS` **and** the org has non-empty `action` tools (`_actions_allowed_for_org` in `collabgpt_lg/graph.py`).
- **Notification agent** path when Langflow is configured, org is in `UA_NOTIFICATION_AGENT_ALLOW_LIST`, and parsed query contains `NOTIFICATION AGENT` — not used when `source == 'Collab'` (see `router` in `collabgpt_lg/graph.py`).
- **Mixpanel** `collabgpt_lg_response` is skipped when `user_display_name == 'Automated Tester'`.

## Technical pointers

- Graph nodes and edges: [Architecture](../technical/architecture.md)
- Endpoint classes: `collabgpt_lg/endpoints.py`, bases in `collabgpt_lg/endpoints_base.py`
- Tests hitting deployed endpoints: `collabgpt_lg/tests/test_vorai.py` (uses env URLs `COLLAB_GPT_LG_*`)
