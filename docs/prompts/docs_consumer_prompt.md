# Consumer prompt: reading `docs/` efficiently (read-only)

You have been given a task in a repository that uses a **standardised documentation tree** at:

`docs/`

**Your permissions.** You **must not** create, edit, move, or delete anything under `docs/` (or assume you have that ability). This prompt only governs **how to find and read** the minimum useful material for the task.

**Hands off `docs/prompts/`.** The folder `docs/prompts/` contains copies of standardised prompt files (including this one). **Never** read or interact with anything inside it. An automated system keeps those files up to date; they are not project documentation and are irrelevant to your task.

**Authority for understanding the project.** Treat `docs/` as the **canonical** in-repo description of what the project is, how it is structured, how it is tested and configured, what is planned, and what changed in the past. Prefer it over README files, wiki dumps, ad hoc markdown elsewhere, or a generic `docs/` tree **unless** the task explicitly points elsewhere or clearly requires information that appears nowhere under `docs/`. If external notes conflict with `docs/`, assume **`docs/` is authoritative** until a human disagrees—do **not** "fix" the tree yourself. Note: some repositories have documentation files outside `docs/` that cannot be removed because tooling or platform conventions require them (e.g. a root `README.md`, manifest files). These external files should be kept consistent with `docs/`, but if they conflict, trust `docs/`. That said, such external files may occasionally contain additional detail on a specific area that `docs/` references but does not fully duplicate—in those cases, read them as supplementary material.

**Naming.** Filenames under this tree use **ASCII snake_case** unless noted below.

---

## 1. Layout (know where to list and search)

```text
docs/
├── product/    # what the project is, usage, integrations, features (user-facing)
├── technical/  # architecture, layout, env vars, tests (implementation-facing)
├── future/     # plans, feedback, ideas (YAML frontmatter on every file)
└── history/    # dated change summaries with PR and story links
```

Start many tasks by **listing** one or more of these directories so you know what files exist; **do not** assume every standard filename is present until you see it.

---

## 2. Predictable filenames and patterns (for listing and search)

Use these patterns to **narrow** what you open. Prefer **searching** for identifiers from the task (feature numbers, paths, symbols, PR URLs) before reading large bodies.

### 2.1 `product/`


| File              | Role                                                        |
| ----------------- | ----------------------------------------------------------- |
| `overview.md`     | Scope, audience, in/out of project                          |
| `usage.md`        | Run, deploy, invoke; points to feature files                |
| `integrations.md` | Other systems and where this repo touches them (path-level) |


**Feature files:** `feature_<NN>_<slug>.md` where `<NN>` is **zero-padded to at least two digits** (`01`, `12`, …). Example: treat filenames as matching the regex `feature_[0-9]{2,}_` as a prefix pattern (wider padding only if the repo exceeds 99 features).

**Screenshot folders (UI-bearing repositories):** For projects with a user interface, `product/` may contain a `feature_<NN>_screenshots/` folder for any feature that has screenshots. Inside it, files are named with an informative slug (e.g. `overview_panel.png`). When screenshots form a logical sequence they follow the pattern `<consistent_slug>_<MM>_<step_slug>.<ext>` (e.g. `widget_config_01_open_dialog.png`, `widget_config_02_choose_type.png`). These are referenced from the corresponding `feature_NN_*.md` files.

### 2.2 `technical/`


| File                       | Role                                                                      |
| -------------------------- | ------------------------------------------------------------------------- |
| `project_layout.md`        | Tree-oriented map of dirs/files, short blurbs, key symbols                |
| `architecture.md`          | Narrative architecture; **may** be split (`architecture_<aspect>.md`)     |
| `environment_variables.md` | Env vars the code reads                                                   |
| `testing.md`               | Where tests live, merge-critical suites, scoped suites, human-only suites |


The first line of `project_layout.md` (and optionally other technical files) is often a freshness hint:

`<!-- docs_as_of: YYYY-MM-DDThh:mm:ss -->`

**Interpretation only:** if `docs_as_of` is visibly old compared to churn implied by your task or by recent paths in git, treat layout/architecture descriptions as **possibly stale** and **cross-check against the codebase** after reading—still no edits to `docs/`.

### 2.3 `future/`

- Filenames begin with exactly one of: `plan_`, `feedback_`, `idea_`.
- **No** numeric prefix; slug is descriptive.
- Every file starts with **YAML frontmatter** (`---` … `---`). You can often decide relevance by **reading only the frontmatter** first (see §3).

### 2.4 `history/`

- Filenames look like: `YYYY-MM-DDThh-mm-ss_<descriptive_slug>.md`  
(date + `T` + time with **hyphens** between hour-minute-second, **no colons**, no timezone, no fractional seconds).
- Sorting lexically approximates chronological order for the prefix.

---

## 3. Efficient retrieval workflow

**Default strategy:** **list → grep/narrow → read partial → read full**

1. **List** the subfolders most likely to hold answers (`product/`, `technical/`, `future/`, or `history/`).
2. **Search within `docs/`** using the task's **anchors**, for example:
  - Feature mentions: identifiers like `feature_07`, `07`, `feature_7`; general matches of feature names/descriptions; in `future/` frontmatter the field `**related_features`** uses **integers**.
  - Paths or modules from the task: grep repo-relative paths or file names echoed in docs.
  - Symbol names (classes, functions) likely repeated in `project_layout.md` or `architecture*.md`.
  - PR URLs, ticket IDs, user-story keys (`US-123`) in `future/` frontmatter (`**related_prs`**, `**related_user_stories`**) or in `history/` bodies.
3. **For `future/` only:** after a grep hit, read the **frontmatter block** first; load the full body if the item is relevant.
4. **Open full files** only when the task needs narrative detail or the grep hit is clearly the right section. Some files are reasonable to open in full in general, of course; e.g. if you need to start looking at code, then do  `project_layout.md` , and when looking at actual code after that, you be the judge of what to read.
5. If something is **missing** (e.g. task names a feature number with no `feature_NN_*.md`), **fall back** to code and other allowed sources; do not invent `docs/` content.

---

## 4. Task → where to start reading

Use the **task shape** to pick **initial** files (still list/grep before reading everything). Expand when the task names a feature ID, path, or subsystem.


| Task shape                                                  | Read first (in rough order)                                                         | Then follow                                                                                        |
| ----------------------------------------------------------- | ----------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| New repo / orientation                                      | `product/overview.md`, `product/usage.md`, `technical/project_layout.md`            | `integrations.md`, `architecture*.md`, specific `feature_NN_*.md`                                 |
| User-visible behaviour or API                               | Relevant `feature_NN_*.md`, `usage.md`                                             | `architecture*.md`, code under paths mentioned in layout                                           |
| "Where does X live?" / refactor / concrete planning of work | `technical/project_layout.md`, `architecture*.md`                                   | `feature_`* that document those areas; `environment_variables.md` if config-related; relevant code |
| Tests / CI / what must pass                                 | `technical/testing.md`                                                              | Merge-critical commands and paths **only**; see §5                                                 |
| Config / "why does local fail?"                             | `technical/environment_variables.md`, `product/usage.md`                            | `integrations.md`, then code                                                                       |
| Planning / backlog / grooming                               | `future/*.md` — filter by frontmatter `status`, `related_features`, grep for themes | Bodies of matching `plan_`*, `feedback_`*, `idea_*`                                                |
| Past change / release context                               | `history/*` — grep by date range, PR, keyword, or slug                              | PRs and stories linked inside the chosen file(s)                                                   |


**Token discipline:** Prefer **one** architecture-oriented file + **one** feature file + **layout** over loading every `feature_*.md`. Add more feature files only when the task crosses multiple numbered features.

---

## 5. Tests and human-only suites

`technical/testing.md` may label some suites as **not for automation** (long, expensive, or needing human judgement). **Do not** assume you should run those unless the user explicitly tells you to (regardless of whether you are writing a plan or performing actual code changes). Your job is to **read** the classification and respect it; still use merge-critical and scoped guidance when your role includes running checks.
