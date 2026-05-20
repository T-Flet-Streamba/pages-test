# Overview

This repository is a **single Azure Functions** Python application hosting multiple function apps that power **VOR AI** and related logistics automation for enterprise customers. The primary surface is **`collabgpt_lg`**: a LangGraph-based conversational agent (internally referred to alongside the **Collab** thread system; the product name is **VOR**).

## Problem solved

- **Natural-language access** to logistics entities (containers, flights, movement requests, road transport, shipments, voyages/manifests, work orders, priorities, summaries) with org-specific data sources and guardrails.
- **Background pipelines** for entity subscriptions (change detection and notifications), **CHEVRON-only** ingestion into custom **VOR AI Search** indexes, auxiliary HTTP APIs (logistics summary warnings, vessel/AIS lookup), and a **timer-based PO shipment overdue path** that historically called **Flowise** (see below — **dormant** today).
- **External agent orchestration** for notifications and subscriptions runs on **LangFlow** (replacing the old Flowise deployment). Not every Flowise-era flow was ported; some will be rebuilt in LangFlow only when needed again.

## Audiences

| Audience | Use this documentation for |
| -------- | --------------------------- |
| Integrators of VOR / Collab | `usage.md`, `feature_*.md`, `integrations.md` |
| Engineers maintaining the function app | `../technical/` |
| Operators / SRE | Environment and triggers in `../technical/environment_variables.md`, `../technical/project_layout.md` |

## In scope

- All Python packages and Azure Function folders at the repository root (except ignored tooling paths).
- Shared libraries under `shared/`.
- Root tests and per-function tests as described in `../technical/testing.md`.

## Out of scope

- Internal design of **VOR** customer APIs, **Data Enhancer**, **AI Search** service implementations, and **LangFlow** agents (plus any legacy **Flowise**-shaped env vars still referenced by dormant code) beyond what this repo calls.
- Non-Python infrastructure (Azure portal configuration, networking, secrets rotation procedures) except where implied by environment variables.


