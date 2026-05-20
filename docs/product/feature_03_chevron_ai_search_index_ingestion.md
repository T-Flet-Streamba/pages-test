# Feature 03 — CHEVRON AI Search index ingestion

## Summary

Several functions **push CHEVRON logistics documents** into **VOR AI Search** indexing endpoints configured in `config.ai_search.url` (`flight_indexing`, `road_transport_indexing`, `priority_indexing`). Retrieval for the main agent uses search/query URLs; these jobs populate or refresh index documents.

All ingestion paths observed in code are **hard-scoped to CHEVRON** (e.g. `org_state('CHEVRON')`, `IndexUploader(..., 'CHEVRON', ...)`).

## Functions in this feature


| Folder                                   | Trigger              | Purpose                                                                                                                                                            |
| ---------------------------------------- | -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `collabgpt_get_flights`                  | Timer `0 50 * * * `* | Last ~1h10m of flights from Data Enhancer by date → map via `FlightsByID._data_mapping` → upload                                                                   |
| `collabgpt_get_flights_bulk`             | HTTP (function key)  | Same retriever class; `from` / `to` query params; optional `upload_batch_size` (default 200)                                                                       |
| `collabgpt_get_road_transport_jobs`      | Timer                | Recent road transport events → `RoadTransportJobsByID` mapping → upload                                                                                            |
| `collabgpt_get_road_transport_jobs_bulk` | HTTP                 | `SummaryRoadTransportDataHandler` using summary-by-date endpoint; params `from_date`, `to_date`, `entries_limit`, `upload_batch_size`, `concurrent_requests_limit` |
| `collabgpt_get_priority_items`           | Timer `0 30 * * * *` | Read JSON from Redis key `config.redis.cvx.priorityfreight` → batched upload                                                                                       |


Shared upload logic: `shared/index_uploader.py` (`IndexUploader`, inherits `AISearchBaseClass`).

The indexing and search API for these and more entities is in the [vorai-search](https://github.com/streamba/vorai-search) repo.

## Technical pointers

- `../technical/project_layout.md` — file map
- Environment: `../technical/environment_variables.md` (`VOR_AISEARCH_*`, Data Enhancer, Redis)

