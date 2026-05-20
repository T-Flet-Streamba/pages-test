# Feature 06 — PO shipment overdue workflow (timer; legacy Flowise — dormant)

## Status (read this first)

**This path is dormant.** The codebase still defines `collabgpt_po_shipments_trigger` and a **Flowise**-oriented wrapper (`FlowiseWrapper` in `collabgpt_po_shipments_trigger/classes.py`), but the **Flowise instance is gone**: the team **migrated to LangFlow** for external agent flows. **Not every Flowise flow was ported**; flows are reintroduced in LangFlow when there is product need again. The PO overdue chatflow **has not been rebuilt in LangFlow yet**, so nothing meaningful should call the old Flowise endpoints today.

## Original design (what the code was built for)

`collabgpt_po_shipments_trigger` runs on a **weekday schedule** (`0 0 2 * * Mon-Fri` in `collabgpt_po_shipments_trigger/function.json`). It loads PO shipment data via `PoShipmentsTrigger`, finds **overdue** items (allocated but not booked per business logic in `collabgpt_po_shipments_trigger/classes.py`), and was intended to start or continue **Flowise** chatflow sessions using `config.flowise.po_warnings_chatflow_id`.

## Freight forwarder split

The timer groups overdue POs by `allocatedFreightForwarder` and only auto-triggered workflows for **`DBSchenker`** and **`DSV`**; other forwarders log a warning (`collabgpt_po_shipments_trigger/__init__.py`). This logic remains in code for whenever the feature is revived on Langflow.

## Technical pointers

- Legacy **Flowise** env vars (only relevant if this feature is revived or code is removed): [Environment variables](../technical/environment_variables.md) (`FLOWISE_*`)
- [`collabgpt_po_shipments_trigger/readme.md`](https://github.com/T-Flet-Streamba/pages-test/blob/main/collabgpt_po_shipments_trigger/readme.md) in repo
