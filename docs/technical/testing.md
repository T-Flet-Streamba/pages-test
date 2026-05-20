<!-- docs_as_of: 2026-05-14T15:00:00 -->

# Testing

## Layout

| Location | Scope |
| -------- | ----- |
| `tests/` | Shared modules: `test_redis_cache.py`, `test_utils.py`, `test_user_management.py`, `test_ls_warnings.py`; fixtures in `tests/conftest.py` |
| `collabgpt_lg/tests/` | Endpoint integration (`test_endpoints.py`), graph/behaviour tests, `test_vorai.py` (optional live HTTP against deployed functions) |
| `collabgpt_get_ls_warnings/tests/` | Function-specific unit tests |
| `collabgpt_check_subscriptions/tests/` | Subscription utilities (includes ad-hoc scripts; not all are pytest modules) |

## How to run

From the repository root with a virtual environment matching `requirements.txt` and `requirements_dev.txt` (if used):

```bash
python -m pytest
```

`pytest.ini` enables CLI logging with timestamps.

## Merge-critical suites

- A selection of both relevant and unrelated queries from the commented-out test cases of TestCollabGPT.test_invoked_tool in `collabgpt_lg/tests/test_vorai.py`. (The full batch is overkill; a good selection of ~20 or so is reasonable).
    - Note that the function allows targeting all 3 instances: local, dev, and live, so repeated batches of tests are recommended (contextual query batch locally until satisfied, reasonable batch as described above on dev, sanity-check-sized batch on live).
- All tests in `collabgpt_lg/tests/test_endpoints.py`, though some of them may fail without manual intervention in VOR or updating of test cases (due to date ranges and filters becoming obsolete as data moves out of the data sources). Vor Search–backed classes (`FlightsByDescriptionVorSearch`, `VoyagesByDescriptionVorSearch`, `ShipmentsVorSearch`, `RoadTransportJobsVorSearch`) and their date/sort JSON fixtures are especially sensitive to moving calendar windows.

**Recommended default for code touching logistics APIs:** `collabgpt_lg/tests/test_endpoints.py` (async integration against real backends — needs valid env). **Code touching Redis cache contracts:** `tests/test_redis_cache.py` and `tests/test_ls_warnings.py`.

## Area-scoped suites

| When you change | Consider running |
| ---------------- | ----------------- |
| `collabgpt_lg/endpoints.py` | `collabgpt_lg/tests/test_endpoints.py` |
| `collabgpt_lg/graph.py`, `tools.py` | `collabgpt_lg/tests/` graph and tool tests |
| `shared/user_management.py` | `tests/test_user_management.py` |
| `collabgpt_get_ls_warnings` | `collabgpt_get_ls_warnings/tests/test_main.py` |

## Human-only suites

**`collabgpt_lg/tests/test_vorai.py`** — exercises deployed HTTP endpoints when `COLLAB_GPT_LG_DEV` / `COLLAB_GPT_LG_LIVE` and matching `*_KEY` variables are set. Do **not** wire this into default CI without secrets and stable target environments; run manually before releases or when validating prompt changes end-to-end.

## Lint / format

`pyproject.toml` configures **Black** (`line-length = 88`), but it is not followed in actual code, so do not run it.
