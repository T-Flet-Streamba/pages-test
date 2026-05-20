# Feature 05 — Vessels in transit by location (HTTP)

## Summary

`collabgpt_get_vessels_in_transit_by_location` combines **in-progress voyage** data (via `get_voyages_in_progress` in `collabgpt_get_vessels_in_transit_by_location/util.py`) with optional **AIS** lookups (`AISData` in `shared/cosmos.py`) to return vessel status JSON for a requested **location**, **direction**, and optional MMSI / range checks.
This feature is currently only intended for Chevron, and its only use is in the `Geofencing Alerts` flow on Langflow, used only for demo purposes.

## Primary surface

- **Trigger**: HTTP (`collabgpt_get_vessels_in_transit_by_location/function.json`, `authLevel: function`).
- **Notable query params** (from `main` in `collabgpt_get_vessels_in_transit_by_location/__init__.py`): `location`, `direction` (default `either`), `get_ais`, `check_all_vessels`, `check_all_vessels_range`, `vessel_id_or_mmsi`. Params other than `code` are logged as “safe” for observability.

## Supporting assets

- Static mapping file: `collabgpt_get_vessels_in_transit_by_location/20241217-154119-vessel-mmsi-mappings.json`

## Technical pointers

- `shared/cosmos.py` — AIS data access pattern
- [Environment variables](../technical/environment_variables.md) — Cosmos-related configuration
