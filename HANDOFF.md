# Handoff: Data Refinement Pipeline

This document is for teammates and future contributors who need to continue or
maintain the work added in the data refinement pipeline. It covers what's
running, why it's structured the way it is, how to operate it, and the
roadmap of what's intentionally left for the next person.

If you only read one section, read **"Mental model"** and **"Daily commands"**.

---

## Status (last updated 2026-05-09)

The pipeline is **up to date and fully wired**. Everything described below
is live on `main` and operational:

- **Bronze → silver refinement**: validation, cleaning, FK checks, atomic
  writes, run manifest, rejects file. ✅
- **Silver → Supabase publish**: idempotent, non-destructive, FK-safe,
  field-sliced upsert. Now also resilient to per-table failures and to
  secondary `UNIQUE(name)` collisions on reference tables (see "Recovering
  from drift" below). ✅
- **Supabase verify (redundancy check)**: read-back, diff vs silver,
  per-table drift report. ✅
- **31 tests passing** (cleaner, validator, end-to-end, fake Supabase
  including unique-constraint + reset-reference paths). ✅
- **Automation**: GitHub Actions CI on every push/PR, scheduled publish
  to Supabase nightly + on push to `main`, drift-watch every 6 hours,
  manual dispatch, local pre-commit hooks, Dependabot. ✅

What's **not** done is in the "Open issues" section near the bottom — those
are intentionally deferred for follow-up work, not bugs.

> If you re-run `python -m app.pipeline.run --strict` right now you should
> see `meetings: in=100 out=100 rejects=0` and the committed silver should
> match byte-for-byte (`git diff --exit-code app/data/silver/`).

---

## Mental model

The repo follows a **medallion architecture**:

```
bronze (raw)        →   silver (validated, cleaned)   →   gold (Supabase)
app/data/*.csv          app/data/silver/*.csv             projects, meeting_types,
                                                          locations, meetings, documents
                                                          on Supabase Postgres

reference (curated YAML, used by both)
app/data/reference/*.yaml
```

Three rules to keep in your head:

1. **Bronze is sacred.** Never edit `app/data/silver/` by hand — it's regenerated
   from bronze by the pipeline. If silver is wrong, fix bronze (the CSV) or fix
   the pipeline (`app/pipeline/`).
2. **Silver is the canonical source of truth.** Supabase is the *serving copy*.
   Anything in Supabase that differs from silver is "drift," and the verify
   stage will surface it.
3. **The pipeline never deletes from Supabase.** It only upserts. If you need
   to remove rows, do it explicitly in the Supabase dashboard.

---

## Repository map (pipeline-relevant pieces only)

```
app/
├── data/
│   ├── meetings.csv               BRONZE  raw meeting rows (edit to add records)
│   ├── documents.csv              BRONZE  raw document rows
│   ├── reference/                 REFERENCE  human-curated lookups (edit freely)
│   │   ├── projects.yaml
│   │   ├── meeting_types.yaml
│   │   ├── locations.yaml         (lat/long lives here)
│   │   └── geometries.yaml        (LineString / Polygon coords by location_id)
│   ├── silver/                    GENERATED  do not hand-edit
│   │   ├── meetings.csv
│   │   ├── documents.csv          (real documents only)
│   │   ├── documents_planned.csv  (future placeholders, isolated)
│   │   └── _rejects.json          (rows that failed validation, with reasons)
│   ├── runs/                      GENERATED & gitignored  per-run manifest
│   │   └── <UTC-timestamp>/manifest.json
│   └── csv_store.py               read-only API the (mock) FastAPI service uses
│
├── pipeline/                      THE PIPELINE
│   ├── config.py                  filesystem paths, Estero bbox constant
│   ├── reference.py               YAML loader (cached, has reload())
│   ├── clean/text.py              OCR-artifact cleaner; pure functions, well-tested
│   ├── validate/schemas.py        Pydantic models + FK checks + reject collection
│   ├── load/silver.py             bronze → silver (atomic writes, dup checks)
│   ├── publish/supabase.py        silver+reference → Supabase (idempotent upsert)
│   ├── verify/supabase.py         Supabase → diff vs silver+reference (drift report)
│   └── run.py                     CLI orchestrator + run-manifest writer
│
├── routers/
│   ├── export.py                  Supabase-backed CSV exports for ArcGIS
│   └── feature_service.py         Esri Feature Service endpoint
│
├── db.py                          Supabase client (get_client, try_get_client)
└── ...

tests/                             pytest, no external dependencies
├── test_clean_text.py             OCR-artifact cleaning cases
├── test_validate.py               Pydantic schema + FK validation cases
├── test_pipeline_e2e.py           runs the pipeline against real bronze
└── test_supabase_publish_verify.py  uses an in-process FakeSupabaseClient
```

---

## Daily commands

The `Makefile` is the primary command surface. Run `make help` for the full menu.

```bash
make install-dev          # one-time setup: venv, deps, pre-commit hooks
make build                # build silver locally, no network
make test                 # run pytest
make publish              # publish silver to Supabase + verify (needs SUPABASE_*)
make publish-dry          # preview publish without remote calls
make verify               # read-only Supabase diff
make ci                   # strict pipeline + tests (what CI runs)
make run-server           # uvicorn on :8000
```

If you prefer the raw commands:

```bash
# Install
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

# Build silver / test / publish
python -m app.pipeline.run                                              # offline
python -m app.pipeline.run --strict                                     # fail on rejects
SUPABASE_URL=... SUPABASE_KEY=... python -m app.pipeline.run --publish --verify
SUPABASE_URL=... SUPABASE_KEY=... python -m app.pipeline.run --publish --dry-run

pytest -q                                                               # tests
uvicorn app.main:app --reload                                           # FastAPI dev server
```

### Strict-mode exit codes

`--strict` is what CI uses; it makes the pipeline turn warning-level
findings into a non-zero exit so the workflow fails loudly. The codes are
distinct so you can tell at a glance what kind of failure happened:

| Code | Meaning |
|------|---------|
| `0`  | Success |
| `2`  | Silver build had rejected rows (validation failures) |
| `3`  | Verify reported drift between silver+reference and Supabase |
| `4`  | Publish recorded a per-table error (e.g. PostgREST `23505` on a unique constraint) |

The code is the *highest* one that applied — so a run with both rejects
and drift reports `2`, but a run with only drift reports `3`.

## Automation

Pipeline runs in five different ways without anyone clicking a button:

| Trigger | What runs | Where |
|---|---|---|
| Every push & PR | `pytest -q`, `python -m app.pipeline.run --strict`, "silver matches commit" guard | `.github/workflows/ci.yml` |
| Push to `main` (data/pipeline files) | `python -m app.pipeline.run --publish --verify --strict` | `.github/workflows/publish.yml` |
| Nightly at 06:00 UTC | Same publish + verify pass — re-asserts canonical state | `.github/workflows/publish.yml` (schedule) |
| Every 6 hours | `python -m app.pipeline.run --verify --strict` (read-only drift watch) | `.github/workflows/drift-watch.yml` |
| Operator-triggered | Manual `workflow_dispatch` from the Actions UI, with optional `--dry-run` | `.github/workflows/publish.yml` |
| Local `git commit` (after `make install-dev`) | Pre-commit framework: rebuilds silver if you touched bronze/reference, stages the regenerated outputs into your commit | `.pre-commit-config.yaml` |

**One-time setup for the GitHub workflows:** in *Settings → Secrets and variables → Actions* on the GitHub repo, add `SUPABASE_URL` and `SUPABASE_KEY` (or `SUPABASE_SERVICE_KEY`). The workflows skip cleanly when secrets aren't set, so a fork or anyone without access can still run CI.

If you want the API health check to run in CI, also set the repo variable `RUN_API_HEALTH=true` in *Settings → Secrets and variables → Actions → Variables*.

**Dependabot** (`.github/dependabot.yml`) watches Python deps and GitHub Actions weekly; you'll see grouped PRs ("patches" / "minors") to review.

---

## Recovering from drift

Two failure modes show up regularly and are worth understanding:

### A) Per-table publish error (e.g. `PostgREST 23505`)

Symptom in the workflow log:

```
duplicate key value violates unique constraint "meeting_types_type_name_key"
Key (type_name)=(...) already exists.
```

What happens now:

1. The publish step **does not abort** anymore. The offending table's
   report records `"error": "..."` and the rest of `publish` (other
   tables) plus `verify` still run.
2. For reference tables (`projects`, `meeting_types`, `locations`) the
   publish also pre-flights against remote rows that already use a
   row's stable name (`project_name` / `type_name` / `location_name`)
   with a different primary key. Those rows are **skipped** and recorded
   under `"name_conflicts"` / `"name_conflict_count"` in the per-table
   report, so `--strict` flags them via the new exit code `4`.

The next person looks at the manifest's `stages.publish.<table>` and
sees exactly which rows couldn't land and why.

### B) Remote IDs disagree with the YAML (`--reset-reference`)

Sometimes the Supabase project was seeded by an earlier import with a
different `type_id ↔ type_name` mapping (or a different `project_id`,
`location_id` mapping) than the canonical YAML. Plain upserts can't
fix this, because they can't change a row's primary key without breaking
foreign keys, and we never delete remote data implicitly.

For this case there is now an **explicit, opt-in** escape hatch:

```bash
# Always preview first.
SUPABASE_URL=... SUPABASE_KEY=... python -m app.pipeline.run \
  --reset-reference --publish --verify --dry-run

# When you're confident, run for real.
SUPABASE_URL=... SUPABASE_KEY=... python -m app.pipeline.run \
  --reset-reference --publish --verify --strict
```

`--reset-reference` deletes every row from `projects`, `meeting_types`,
and `locations` on the remote, then `--publish` reseeds them from YAML
with the correct IDs. **It does not touch `meetings` or `documents`.**
Those are larger, FK-bearing, and may contain user-curated state, so
they're cleaned up out of band in the Supabase dashboard if at all.

Operator checklist when you reach for `--reset-reference`:

1. Confirm there are no human edits to `projects` / `meeting_types` /
   `locations` on the remote you'd lose. (These tables are
   YAML-canonical, so this should be a non-event.)
2. Run with `--dry-run` first; the manifest's `stages.reset_reference`
   block tells you `would_delete` per table.
3. Run for real. The `delete` happens before the `publish`, so a single
   command takes the remote from "drifted" to "matches YAML."
4. `--verify --strict` at the end of the same command confirms
   everything is `in_sync`. CI's drift-watch will pass on the next tick.

### What `--reset-reference` will **not** fix

The 133 extra `meetings` and 169 extra `documents` rows shown by
drift-watch are remote rows the pipeline never published. Those need to
be triaged manually:

```sql
-- In the Supabase SQL editor, identify which PKs are remote-only:
select meeting_id from public.meetings
where meeting_id not in (<the IDs your silver publishes>);
```

Your options are:

- **Keep them** (and accept that drift-watch will keep flagging them).
- **Delete them** if they're stale: a one-time `delete from meetings
  where meeting_id in (...)`. Same for `documents`.
- **Promote them** into the canonical CSV/YAML by adding the rows to
  bronze and rerunning the pipeline.

This was an intentional design choice: the pipeline never deletes
operational data. See "Architectural decisions worth not undoing."

---

## How to add new data

### Add a new project

1. Edit `app/data/reference/projects.yaml`. Add an entry with the next
   available `project_id`.
2. Run `python -m app.pipeline.run --publish --verify`.
3. The new project is now in Supabase and ArcGIS can see it.

### Add a new location (with lat/long)

1. Edit `app/data/reference/locations.yaml`. Make sure `latitude` /
   `longitude` are inside the Estero bounding box (≈ 26.30–26.55 N,
   −81.95 to −81.65 W).
2. If it's a road or trail, also add a coordinate sequence under
   `road_geometries:` in `geometries.yaml` keyed by the same `location_id`.
3. Run the pipeline.

### Add new meeting records

1. Append rows to `app/data/meetings.csv` (this is the bronze layer).
2. Make sure the `project_id` and `type_id` exist in the reference YAML —
   the pipeline's FK checks will reject the row otherwise and you'll see
   the row in `app/data/silver/_rejects.json`.
3. Run the pipeline.

### Add new documents

Same as meetings, but in `documents.csv`. **There is currently a known
mismatch between document `meeting_id`s and the meetings table** — see the
"Open issues" section below.

---

## How to read a run

After every `python -m app.pipeline.run` you get a manifest at
`app/data/runs/<timestamp>/manifest.json`. Open it; every section is
human-readable. The fields you care about most:

- `stages.silver.meetings.{in, out, rejects}` — did anything fail validation?
- `stages.silver.documents.fk_warnings` — count of docs with broken FK to meetings (currently 76, see open issues)
- `stages.publish.<table>.upserted` — how many rows we wrote to Supabase per table
- `stages.publish.<table>.error` — present iff that table's upsert raised; the message is captured here and the rest of `publish` still ran
- `stages.publish.<table>.name_conflicts` — local rows that share a `name_field` with a different-PK remote row and were skipped (reference tables only); see "Recovering from drift"
- `stages.reset_reference.<table>.deleted` — present iff `--reset-reference` ran; how many rows we deleted (or `would_delete` under `--dry-run`)
- `stages.verify.<table>.in_sync` — `true` if Supabase agrees with silver for this table
- `stages.verify.<table>.in_local_only_sample` / `in_remote_only_sample` — first 50 PKs that disagree
- `stages.verify.<table>.mismatched_sample` — first 10 rows where field values differ, with `local` and `remote` values

If you see a non-empty `_rejects.json` after a run, the file has a
`row` (the original CSV row) and `errors` (human-readable list of what was
wrong). Fix the source CSV/YAML, re-run.

---

## Open issues — work the next person should pick up

These are real problems the pipeline surfaced or that were intentionally
left in scope for a follow-up.

### 1. Document → Meeting FK mismatch (76 warnings)

`documents.csv` references `meeting_id` values 158–233; `meetings.csv`
covers 1–139. **Zero overlap.** They were clearly built independently, and
the pipeline currently records each document as a "fk_warning" but keeps
the row.

Options for the next person:

- **Repair the source.** Walk both CSVs, match documents to meetings by
  `meeting_date` + `filename` (the bronze data has both), rewrite
  `documents.csv` with the correct `meeting_id`. This is the right fix.
- **Rebuild documents from meetings.** Many meetings already have a
  `filename` column pointing at the PDF. We could synthesize document
  rows from meetings rather than tracking them separately.

### 2. `action_taken` is still a `|`-joined blob

The cleaner fixes the OCR artifacts but the structure is still:

```
"Approved Resolution 2024-01. | Approved Contract EC 2024-07 with ..."
```

`split_actions()` in `clean/text.py` already breaks this into a list. The
natural next step is a real `meeting_actions` table:

```
meeting_actions
  action_id (PK)
  meeting_id (FK)
  sequence  (0, 1, 2, ...)
  kind      ("Adopted Resolution" | "Approved Contract" | ...)
  reference_code  ("2024-07")
  amount_usd  (NUMERIC, nullable)
  raw_text  (the cleaned clause)
```

This unlocks proper SQL filtering ("show me all approved contracts over
$100k") and structured ArcGIS popups.

### 3. The scraper is gone

`README.md` mentions a `scraper/` directory that doesn't exist in the repo.
Re-introducing it as `app/pipeline/extract/` that writes timestamped raw
files to a `bronze/` subfolder (with provenance: source URL, fetch time)
is a clean unit of work.

### 4. No geocoding stage

`locations.yaml` is hand-edited. Adding `app/pipeline/enrich/geocode.py`
that calls the US Census Geocoder (free, no API key) and caches results
in `app/data/reference/geocode_cache.json` would let teammates add
addresses without manually looking up lat/long.

### 5. The mock CSV-backed routers aren't wired up

`app/routers/{projects,meetings,meeting_types,locations,layers,documents}.py`
all use `app/dependencies.py::get_store()` (which reads silver/bronze
locally) but they aren't included in `app/main.py`. They're functional but
not mounted — only `export` and `feature_service` are. If we ever want a
"local mode" for ArcGIS-style endpoints without Supabase, mount these in
`main.py`.

### 6. CI is configured but secrets need to be set

`SUPABASE_URL` / `SUPABASE_KEY` need to be added in the GitHub repo's
*Settings → Secrets and variables → Actions* before `publish.yml` and
`drift-watch.yml` can do anything useful. Without them the workflows
still pass (the pipeline gracefully skips publish/verify), but they
won't actually publish to Supabase or detect drift.

---

## Architectural decisions worth not undoing

These are the design choices that make the pipeline professional rather
than ad-hoc — please push back on PRs that try to undo them.

1. **Reference data lives in YAML, not Python.** Non-developers can edit
   it. Don't move it back into `csv_store.py`.
2. **Pipeline never deletes from Supabase.** Drift gets reported; resolving
   it is an operator's call. Don't add an "auto-cleanup" mode that
   silently destroys remote rows.
3. **Atomic writes in `load/silver.py`.** The pipeline writes to a
   tempfile, then `os.replace`s it. A crashed run never corrupts silver.
   Don't replace this with a plain `open(..., "w")`.
4. **Validation rejects are non-fatal by default.** Bad rows go to
   `_rejects.json`, the pipeline keeps going on the good rows. Use
   `--strict` if you need CI to fail on them.
5. **`from __future__ import annotations` everywhere in `app/pipeline/`.**
   Annotations are strings, not runtime types. This lets the pipeline run
   on Python 3.9 even though the FastAPI service requires 3.10+.
6. **Tests don't require Supabase credentials.** `test_supabase_publish_verify.py`
   uses an in-process `FakeSupabaseClient` stub. Keep it that way; if a
   teammate adds tests that hit real Supabase, they'll break in CI.

---

## Useful pointers

- **Pydantic schemas** for the *pipeline* (strict, with FK checks) live in
  `app/pipeline/validate/schemas.py`. The Pydantic schemas for the *API*
  (the contract with ArcGIS) live in `app/models/schemas.py`. They look
  similar but serve different purposes — don't merge them.
- **The `action_taken` cleaner** is a list of regex `(pattern, replacement)`
  pairs. To handle a new OCR artifact, add a pair in
  `app/pipeline/clean/text.py::_SPLIT_VERB_FIXES` and a unit test in
  `tests/test_clean_text.py`. The cleaner is pure (no I/O), so testing is
  trivial.
- **Adding a new pipeline stage** (e.g. geocoding) follows the same pattern
  as `publish/supabase.py`: a module under `app/pipeline/<stage>/`, a
  function that takes a client/config and returns a report dict, plus a
  flag in `run.py` and a manifest section. Keep stages pure if possible.
- **The `Estero bounding box`** is `app/pipeline/config.py::ESTERO_BBOX`.
  Use it in any new geo-validation code so the bounds stay consistent.

---

## Contacts

| Role | Person |
|---|---|
| Original implementation (refinement pipeline) | Nolan Stilwell-Carroll |
| Supabase / database architecture | Krish Shah |
| Queries / docs | Ethan Malviala |
| Community partner | Terry Flanagan (Engage Estero / EsteroToday.com) |
| ArcGIS / StoryMap | Kim Dailey |
| Faculty | Dr. Vinod Ahuja, COP 3710, FGCU |

If you're stuck on the pipeline specifically, the run manifest plus the
`_rejects.json` will tell you 90% of what you need. The next 10% is
either in the docstrings of `app/pipeline/*.py` or in the test files,
which double as worked examples.
