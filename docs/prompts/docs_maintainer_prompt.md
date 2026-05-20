# Updater prompt: maintaining `docs/` in full compliance

You are responsible for **creating, editing, and organising** the repository tree rooted at:

`docs/`

**Scope.** This document is the **complete** normative standard for **what** that tree must contain, **how** files are named and structured, and **how** to update it diligently (including after code changes or PRs). It does **not** describe read-only navigation strategies.

**Hands off `docs/prompts/`.** The folder `docs/prompts/` contains copies of standardised prompt files (including this one). **Never** read, edit, create, or delete anything inside it. An automated system keeps those files up to date; manual changes will be overwritten.

---

## 1. Authority and supersession

- `docs/` is the **canonical** in-repository documentation about the project: product, technical design, backlog-style future work, and change history.
- It is intended to **standardise and supersede** fragmented narrative docs elsewhere in the repo (READMEs, loose markdown, informal `docs/`). When migrating or reconciling content, **`docs/` wins**.
- Some repositories contain documentation files **outside** `docs/` that **cannot be removed** because tooling, packaging, or platform conventions require them (e.g. a root `README.md`, `package.json` description fields, manifest files). Those external files **must** be kept up to date with the relevant content in this folder structure. Conversely, the appropriate files inside `docs/` **should** mention any such external documentation where relevant—especially when the external file contains additional detail on a specific area beyond what `docs/` covers.
- Exceptions may be acknowledged **inside** `docs/history/` (or rarely in explicit notes in relevant files)—do not silently leave contradictory documents outside the tree unless the team process says otherwise.

**Naming.** Paths and filenames under `docs/` use **ASCII snake_case**. No spaces in filenames.

---

## 2. Mandatory root layout

Every adopting repository **MUST** contain:

```text
docs/
├── product/
├── technical/
├── future/
└── history/
```

Do **not** rename or omit these subfolders. If a subtree has little content yet, optionally add a short `README.md` in that folder explaining that it is intentionally minimal.

---

## 3. Folder: `product/`

**Purpose.** Describe **what** the project is, **who consumes it**, **how it is used**, which **other projects or systems** it interacts with (name and role only—not how those systems work internally), and each **user- or integrator-visible feature**.

**Integrations.** List external dependencies, services, contracts, and integration points with enough detail that implementers know **what to search for in code** and what not to duplicate.

### 3.1 Standard general files


| File              | Contents                                                                                                |
| ----------------- | ------------------------------------------------------------------------------------------------------- |
| `overview.md`     | Elevator description, problem solved, audiences, in/out of scope                                        |
| `usage.md`        | High-level run, deploy, invoke; pointers to feature files                                               |
| `integrations.md` | External systems; purpose of link; artifact type; **where in this repo** integration lives (path-level) |


### 3.2 Feature files

Each distinct user- or integrator-visible feature **MUST** have **exactly one** primary file:

`feature_<NN>_<short_descriptive_slug>.md`

- `<NN>`: **fixed-width decimal**, **zero-padded to at least two digits** (`01` … `99`; use three+ digits only if the repo exceeds 99 features).
- `<short_descriptive_slug>`: stable snake_case (not marketing-title-dependent).

**Numbering (global rule).** Feature numbers are **monotonic**. The next feature **MUST** use `max(existing NN) + 1` on the integration branch. **Never reuse** a number after retirement; obsolete files **MUST** be superseded in place with a clear banner and/or explained in `history/`, not silently deleted without trace.

### 3.3 Screenshot folders (UI-bearing repositories)

For repositories that contain user interfaces, `product/` **may** (and **should**, where practical) include screenshots illustrating UI features. Screenshots for a given feature live in a dedicated folder:

`feature_<NN>_screenshots/`

- `<NN>`: the same zero-padded feature number as the corresponding `feature_<NN>_*.md` file.
- Create the folder only when there is at least one screenshot for that feature.

**Individual screenshot naming:** inside the folder, each file is simply:

`<informative_slug>.<ext>`

where `<informative_slug>` is a descriptive snake_case slug of what the screenshot shows, and `<ext>` is the image format (e.g. `png`, `jpg`, `webp`).

**Sequences.** When several screenshots form a logical sequence (e.g. the UI after each step of a multi-step task), name them:

`<consistent_slug>_<MM>_<step_slug>.<ext>`

- `<consistent_slug>`: a shared slug identifying the sequence as a whole.
- `<MM>`: a zero-padded ordinal giving the position in the sequence.
- `<step_slug>`: a short slug describing the specific step.

Example folder for feature 03:

```text
product/
├── feature_03_dashboard.md
└── feature_03_screenshots/
    ├── overview_panel.png
    ├── widget_config_01_open_dialog.png
    ├── widget_config_02_choose_type.png
    └── widget_config_03_confirm.png
```

Reference screenshots from the corresponding feature file where useful.

New feature files are **rare**; numbering discipline must hold so `technical/` and `history/` can cite stable IDs.

**Content expectations:** short summary, primary surface (API/UI), constraints, pointers to `technical/` filenames, optional pointers to `future/` or `history/`.

---

## 4. Folder: `technical/`

**Purpose.** Describe **how** the repository implements behaviour: architecture, layout, configuration, tests, design tradeoffs.

**Cross-references.** Technical prose **MUST** tie to **feature IDs** (number + `feature_NN`_ name), **repository paths**, and **stable symbol names** (types, functions, classes, modules), wherever that reduces ambiguity.

Split work across multiple files so none becomes unmanageably large; **one main concern per file** with explicit cross-links.

### 4.1 `docs_as_of` timestamp (drift control)

Any file that lists **directory trees**, **file inventories**, or other **high-churn structure** **MUST** begin with **line 1**:

```text
<!-- docs_as_of: YYYY-MM-DDThh:mm:ss -->
```

Rules:

- **No** timezone suffix; **no** fractional seconds.
- Update this line **whenever** the body is updated to reflect current structure or facts.
- The file `**project_layout.md` MUST** use this stamp.
- Other `technical/` files **SHOULD** use it when they describe facts that change often (e.g. architecture summaries).

### 4.2 Standard technical files


| File                       | Contents                                                                                                                                                                                       |
| -------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `project_layout.md`        | Tree-oriented map: dirs and important files, very short purpose each; key class/function/module **names**; **MUST** start with `docs_as_of`                                                    |
| `architecture.md`          | Components, boundaries, flows, invariants; **MAY** split as `architecture_<aspect>.md`; must reference features, paths, symbols                                                                |
| `environment_variables.md` | **All** env vars the project is **expected** to read; per var: name, one-line meaning, where/how used (if used in many files, give general description, not list), required vs optional when known                                                         |
| `testing.md`               | Test locations; how to run; **merge-critical** suites; **area-scoped** suites (run when touching related code); **human-only** suites (do not automate; document when a human should run them) |


Regeneration of `project_layout.md` **MAY** be automated elsewhere; the stamp and cross-links **MUST** remain correct after publish.

---

## 5. Folder: `future/`

**Purpose.** Plans, feedback, and ideas **not** yet fully reflected in shipped behaviour.

### 5.1 Filename prefixes (exact)

Each item is its own file, with **exactly one** prefix:


| Prefix      | Use                                                  |
| ----------- | ---------------------------------------------------- |
| `plan_`     | Execution intent, milestones, sequenced work         |
| `feedback_` | Observations, pain, requests not yet a plan          |
| `idea_`     | Exploratory directions; may be discarded or promoted |


**No** numeric prefix; use a descriptive slug (e.g. `plan_redesign_export_api.md`).

### 5.2 YAML frontmatter (mandatory on every file)

First lines of **every** `future/` file **MUST** be:

```yaml
---
status: draft | active | blocked | superseded
created: YYYY-MM-DD
updated: YYYY-MM-DD
related_features: [7, 12]
related_prs: ["https://github.com/org/repo/pull/123"]
related_user_stories: ["US-456", "US-789"]
---
```

- `status` required; keep it current.
- `related_features`: **integers** only (match `feature_<NN>_` by ID).
- `related_prs` / `related_user_stories`: use `[]` when empty; fill when known.
- Body **SHOULD** repeat or link stories/PRs for readers who skip YAML.

On **every** substantive edit, bump `updated:` and adjust `status` / relations as needed.

---

## 6. Folder: `history/`

**Purpose.** Durable summaries of **what changed** and **why**, with **PR** and **user-story** links.

### 6.1 Filename pattern

Each distinct record **MUST** be its own file:

`<ISO_LOCAL_DATETIME>_<descriptive_slug>.md`

Where `<ISO_LOCAL_DATETIME>` is:

`YYYY-MM-DDThh-mm-ss`

- No timezone; no fractional seconds.
- **Filename-safe time:** **hyphens** between hour, minute, second (never **colons**—Windows-unfriendly).

Choose a prefix that avoids collisions (seconds resolution is normal; if two writes could share a second, vary the slug or defer one second).

### 6.2 Which instant the prefix encodes

Use **exactly one** of:

1. **Last commit timestamp** of the summarised change set (typically the **merge** commit of the last PR involved), or, if for some reason cannot find this,
2. **Now** of the documentation-updating PR that adds this entry (typically "now" when the updater runs).

If you used the second, state so in the **first paragraph** of the file body.

### 6.3 Body requirements

History records **meaningful** delivered work and **documentation coverage**. Summarise outcomes and affected areas for substantive changes. For PRs reviewed during a doc-update pass that did **not** warrant edits elsewhere, still include them here: link each PR, briefly say what it did, and note that no changes to `product/`, `technical/`, or `future/` were required—so readers know the work was considered.

Each history file **MUST** include:

- Links to relevant **PRs** (full URLs or repo-consistent convention).
- **User story** / ticket references when applicable.
- Summary of work: **paths/areas** touched, **feature numbers** affected.
- Optional: pointers to updated/superseded `future/` items.

### 6.4 Immutability norm

**Append** new history files for new events. **Do not** rewrite old history for cosmetic reasons. **Correct** a past file only for factual errors; if the error mattered, add a **new** history entry explaining the correction.

### 6.5 Writing multiple new history files

If there are multiple PRs in the set of changes your are going over, you will have to decide the optimal way to log their changes in new history files.
In general you should prefer fewer new files than there are PRs, as the files are meant to be records of single broader releases, therefore typically only a single new history file would be added.
However, if you think that some of the involved PRs are different or substantial enough when compared to the rest, or that the set of PRs partitions neatly into broader categories, by all means feel free to split your history updates into more than one new file.

---

## 7. Global numbering

- Feature IDs in filenames: **at least two** zero-padded digits (`feature_01_…`).
- Any **new** numbered convention introduced later **MUST** document its padding width in an amendment to this updater prompt (or a linked single source of truth).

---

## 8. When to update what (ongoing diligence)

**Appropriate grain.** `docs/` describes **durable, reader-relevant facts** at roughly feature, module, and system level; not a running log of every code change. When reconciling PRs or diffs, use judgement: update `product/` and `technical/` only where a reader would be **misled or uninformed** without the change. Internal refactors, test-only edits, dependency bumps, and small fixes that do not alter user-visible behaviour, documented contracts, layout, env vars, or test policy generally **do not** warrant edits outside `history/`. Prefer **surgical** updates there; use `history/` for a concise record that each reviewed PR was covered (see §6.3).

**Tailor edits to each document's level of detail.** Not every code change belongs in every file that touches the same feature or area. Each document has an established **abstraction level**—match it; do not pull diff-level facts upward into higher-level prose.

- **`product/`** (especially `feature_NN_*.md`, `overview.md`, `usage.md`) stays at **what** the user or integrator sees: capabilities, surfaces, constraints, and outcomes. Do **not** revise a feature summary, elevator description, or usage flow because **low-level logic** inside that feature changed (e.g. a different algorithm, helper, branch, or refactor in the same module) when user-visible behaviour and documented contracts are unchanged.
- **`technical/`** files differ by concern: `architecture*.md` stays at components, boundaries, and flows; `project_layout.md` at structure and naming; other files at their stated scope. Do **not** add implementation minutiae to a broad architecture or feature-linked section when the change is local and does not alter boundaries, invariants, or how a reader should navigate the system.
- **Placement rule:** put new detail only where it **fits the file's existing grain**. If the change is below that grain, leave the file unchanged (record coverage in `history/` per §6.3). If genuinely new detail is needed, prefer the **most specific** existing technical file—or a narrowly scoped addition there—not a rewrite of high-level `product/` text.

Ask: *Would someone reading only this file, at its usual level of detail, be misled if we said nothing?* If not, do not mention the change here.

| Area         | Update when                                                                                                                                                                                                                                       |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `product/`   | User-visible behaviour, usage, or integrations change. New `feature_NN_*.md` only for **new** numbered features (rare). Update screenshots when UI changes materially.                                                                           |
| `technical/` | Layout, architecture, env vars, or test strategy change. **Always** refresh `docs_as_of` on `project_layout.md` (since always have to check its content is up to date); refresh stamps on other technical files when their factual claims change. |
| `future/`    | Items are added, progress, blocked, or superseded—keep frontmatter **and** body aligned.                                                                                                                                                          |
| `history/`   | After a doc-update pass or meaningful delivered work. Several PRs may be summarised in **one** file (see §6.5). **Always** note PRs that were reviewed even when `product/` / `technical/` / `future/` needed no change; a short "what it was; no other docs updates required" line per PR is enough. |


---

## 9. PR-close (or documentation PR) checklist

When finishing a change that should leave `docs/` consistent, work through this list. **Skip** items that truly do not apply; if something expected is skipped, **say so** in the new history file body.

1. `**history/`** — Add one new file per §6; include PRs, stories, paths, feature numbers; set filename timestamp per §6.2 and disclose which clock rule you used.
2. `technical/project_layout.md` — If structure changed: update content. Regardless, refresh `docs_as_of`.
3. `**technical/architecture*.md**` — If boundaries or major flows changed: update and fix cross-references to features and symbols.
4. `**technical/environment_variables.md**` — If code reads new/removed vars: update the list.
5. `**technical/testing.md**` — If test layout or merge/human-only policy changed: update.
6. `**product/**` — If behaviour changed: update affected `feature_NN_*.md`, `usage.md` / `integrations.md` if entrypoints or integration facts changed. Update or add screenshots if UI changed.
7. `**future/**` — If items were implemented, superseded, or blocked: update `status`, dates, and relations; link to the new history file or PR where useful. If the work done fully covers some file here, remove it.
8. **External docs** — If the repo has documentation files outside `docs/` that cannot be removed (root `README.md`, manifests, etc.), ensure they are consistent with the content just updated in `docs/`.

---

## 10. Hygiene: what not to do

- **Human-only** suites in `testing.md` are documented for humans—do not wire them into **default** automated runs in updater workflows without explicit instruction.
- Avoid **bulk** rewrites of all `feature_*.md` for minor wording-only edits; stay **surgical**.
- Do **not** **downshift** or **upshift** detail: avoid pasting low-level implementation changes into high-level `product/` or broad `technical/` prose, and avoid bloating specialised technical files with narrative that belongs in `product/`.
- **Never** replace or delete `history/` entries to hide mistakes—**append** corrections.
