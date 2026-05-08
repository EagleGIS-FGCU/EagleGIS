# Handoff: Data Refinement Pipeline

This document is for teammates and future contributors who need to continue or
maintain the work added in the data refinement pipeline. It covers what's
running, why it's structured the way it is, how to operate it, and the
roadmap of what's intentionally left for the next person.

If you only read one section, read **"Mental model"** and **"Daily commands"**.

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

```bash
# Install dependencies (one time, requires Python 3.10+)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Build silver locally, no network
python -m app.pipeline.run

# Run the test suite
pytest -q

# Push silver up to Supabase, then redundancy-check
SUPABASE_URL=...  SUPABASE_KEY=...  python -m app.pipeline.run --publish --verify

# Inspect what publish would change without making any calls
SUPABASE_URL=...  SUPABASE_KEY=...  python -m app.pipeline.run --publish --dry-run

# CI-friendly: fail on any rejects (exit 2) or drift (exit 3)
python -m app.pipeline.run --publish --verify --strict

# Run the FastAPI service locally (read-only, hits Supabase)
uvicorn app.main:app --reload
```

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

### 5. No CI yet

GitHub Actions running `pytest -q` and
`python -m app.pipeline.run --strict` on every PR would catch any
regression. Optional follow-up: also run `--publish --verify --strict`
against a staging Supabase project before merging to `main`.

### 6. The mock CSV-backed routers aren't wired up

`app/routers/{projects,meetings,meeting_types,locations,layers,documents}.py`
all use `app/dependencies.py::get_store()` (which reads silver/bronze
locally) but they aren't included in `app/main.py`. They're functional but
not mounted — only `export` and `feature_service` are. If we ever want a
"local mode" for ArcGIS-style endpoints without Supabase, mount these in
`main.py`.

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
