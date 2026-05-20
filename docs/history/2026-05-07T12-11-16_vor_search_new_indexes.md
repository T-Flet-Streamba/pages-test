# VOR Search new indexes (flights, voyages, shipments)

This record follows merged work on the default integration line after [PR #366](https://github.com/streamba/vor-collabgpt-functions/pull/366); the merge commit covered here is [PR #367](https://github.com/streamba/vor-collabgpt-functions/pull/367) ([AB#12041](https://dev.azure.com/streambadev/f4c58d4f-554e-4af2-b9d7-2442543c3572/_workitems/edit/12041)).

**Timestamp in filename:** merge time of PR #367 on GitHub (`mergedAt`).

## Summary

- **VOR Search–backed retrieval** for **Shell UK** and **ExxonMobilGuyana**: `find_flights` and `find_voyages` use dedicated Vor Search HTTP indexes with structured arguments (`search_term`, JSON `date_ranges` / `sort`, and entity-specific filters). **ExxonMobilGuyana** additionally wires `find_shipments` to `ShipmentsVorSearch` (Customer API enrichment; milestone dates localised in index dataframe columns).
- **CHEVRON** unchanged for exposed tools: `find_flights` / `find_road_transport_jobs` / `find_shipments` remain on **VOR AI Search**. `RoadTransportJobsVorSearch` exists in `collabgpt_lg/endpoints.py` for Chevron org validation but is **not** registered in `tools_by_org` (reserved for later).
- **Shell UK:** `voyages_by_id` tool removed from the agent; voyage lookup and filtering go through **`find_voyages`** (index + Data Enhancer by-ID enrichment, including ID-shaped `search_term` fallback).
- **Config:** new required env **`RESULTS_LIMIT_FROM_SOURCE`** → `config.ai_behaviour.source_results_limit` (page size sent to Vor Search). **`VOR_SEARCH_AUTH_URL`**, **`VOR_SEARCH_GLOBAL_URL`**, and **`VOR_SEARCH_FLIGHTS_URL`** removed; auth and search path suffixes are **hardcoded** in `config.py` under `vor_search.url` (including `/roadTransportJobs/search`, `/shipments/search`, `/voyages/search`).
- **Prompts:** non-Chevron orgs receive expanded guidance on `vor_global_search` vs `find_*`, `date_ranges` / `sort` JSON, and `further_processing`; Chevron-only URL handoff text is isolated to Chevron parser prompt branch.
- **Tests:** `collabgpt_lg/tests/test_endpoints.py` covers Vor Search flights (Exxon + Shell), voyages, shipments (Exxon), road transport jobs Vor Search (Chevron API class); `org_state` in `collabgpt_lg/utils.py` now sets a stable **`user_id`** per org for tests.

## Paths and symbols (primary)

| Area | Paths / symbols |
| ---- | ---------------- |
| Vor Search URL config | `config.vor_search` |
| Shared index search pipeline | `VorSearchBaseClass._get_search_body`, `_query_pipeline`, `non_index_data_pipeline` in `collabgpt_lg/endpoints_base.py` |
| Implementations | `FlightsByDescriptionVorSearch`, `VoyagesByDescriptionVorSearch`, `ShipmentsVorSearch`, `RoadTransportJobsVorSearch` in `collabgpt_lg/endpoints.py` |
| Tool registration | `flights_vor_search_tool_wrapper`, `shipments_vor_search_tool_wrapper`, `voyages_tool_wrapper`, `tools_by_org`, `non_index_api_dispatcher_by_org` in `collabgpt_lg/tools.py` |
| ID fallback | `by_id_fallback` accepts `search_term` as well as `query` in `collabgpt_lg/endpoints_base.py` |

## Feature IDs

- **[01](../product/feature_01_vor_ai_langgraph_http.md)** — VOR AI (LangGraph): retrieval tool matrix and Vor Search integration surface.
