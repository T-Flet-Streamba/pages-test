# Feature 04 — Logistics summary warnings (HTTP)

## Summary

`collabgpt_get_ls_warnings` is an HTTP GET function that returns **logistics summary warning items** for an organisation, optionally filtered by `filter_type` and `location`, backed by Redis (`SummaryWarningsCache` in `collabgpt_get_ls_warnings/__init__.py` extending `SpecificRedisCache`).

NOTE: this feature will be removed in the near future, when time-based triggers are added to subscriptions (Feature 02), as their absence is the only thing preventing replicating this functionality with them (subscriptions to the same reports but triggered by data changes are already available).

## Primary surface

- **Trigger**: HTTP GET (`collabgpt_get_ls_warnings/function.json`).
- **Parameters**: Read from query string or JSON body — at least `organization`; optional `filter_type`, `location` (see `main` in `collabgpt_get_ls_warnings/__init__.py`).

## Relationship to VOR AI

The main agent’s `logistics_summary` tool (`collabgpt_lg/tools.py`) uses `LogisticsSummaryReports` which hits customer/Data paths appropriate for interactive queries. This HTTP function instead serves **pre-aggregated cache** for consumers that need the same warning families without running the graph.

## Technical pointers

- Tests: `collabgpt_get_ls_warnings/tests/test_main.py`, root `tests/test_ls_warnings.py`
- Redis env: `../technical/environment_variables.md`
