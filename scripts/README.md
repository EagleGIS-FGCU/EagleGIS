# EagleGIS extraction pipeline

This folder contains the local data extraction pipeline used to turn Village of
Estero meeting PDFs and the legacy ArcGIS CSV into normalized review files and
ArcGIS-ready map CSVs.

The pipeline is local/offline code. GitHub Pages does not run it live. To update
the data shown by the site or imported into ArcGIS, run the pipeline locally,
review the generated CSVs, then commit/push the chosen outputs when the team is
ready.

## Entry point

Run from the repository root:

```powershell
python scripts\build_normalized_csvs.py --out-dir normalized_csv
```

If the `pdfs/` folder is available locally, the script reads PDFs from that
folder. If not, it can read PDFs and the legacy CSV from a git ref:

```powershell
python scripts\build_normalized_csvs.py --git-ref origin/script --source-git-ref origin/script --out-dir normalized_csv
```

For a specific local PDF folder and legacy CSV:

```powershell
python scripts\build_normalized_csvs.py --pdf-dir pdfs --source-csv pdfs\Estero_Meetings_Final.csv --out-dir normalized_csv
```

Useful debug option:

```powershell
python scripts\build_normalized_csvs.py --pdf-dir pdfs --source-csv pdfs\Estero_Meetings_Final.csv --out-dir normalized_csv_test --max-pages 3
```

## How it is built

The main builder is `build_normalized_csvs.py`. It coordinates the whole run:

1. Loads the legacy source CSV, usually `pdfs/Estero_Meetings_Final.csv`.
2. Loads meeting PDFs from a local `pdfs/` directory or from a git ref.
3. Extracts text from each PDF.
4. Infers meeting metadata such as date, board, meeting format, venue, and staff
   code.
5. Splits meeting text into agenda-level entries and action/motion records.
6. Matches agenda items to known project and location aliases.
7. Applies cached geocodes from `normalized_csv/geocoded_locations.csv`.
8. Writes normalized database-style CSVs, review CSVs, and ArcGIS import CSVs.

Supporting modules live in `scripts/eaglegis_pipeline/`:

- `sources.py`: reads PDFs from disk or from git.
- `text.py`: extracts PDF text with PyMuPDF and falls back to OCR when needed.
- `extractors.py`: extracts meeting dates, times, meeting types, staff codes,
  agenda entries, and action text.
- `classifiers.py`: classifies actions, detects votes, finds address candidates,
  and matches projects/locations.
- `config.py`: stores project aliases, location seeds, and address/geocode
  hints.
- `writer.py`: writes consistent CSV files.

## OCR

The first pass uses PyMuPDF text extraction. If a PDF has too little embedded
text, the pipeline tries OCR.

OCR uses:

- `pytesseract`
- `Pillow`
- the local Tesseract executable

On Windows, `text.py` automatically checks:

- `C:\Program Files\Tesseract-OCR\tesseract.exe`
- `C:\Program Files (x86)\Tesseract-OCR\tesseract.exe`
- any `tesseract` executable already on `PATH`

If Tesseract is missing or unavailable, the PDF is still processed with whatever
embedded text can be extracted, and weak/scanned files are surfaced in review
outputs.

## Meeting type model

The database-facing meeting type grouping is intentionally limited to the four
types currently used by the database:

- `Village Council`
- `Planning Zoning & Design Board`
- `Public Hearing`
- `Workshop`

More detailed labels are preserved separately as meeting formats, such as
`Regular Meeting`, `Special Meeting`, `Workshop`, `Zoning Hearing`, `Budget
Hearing`, and `Cancelled`.

## Location model

The pipeline creates agenda-level locations when the agenda item text contains
evidence for a known project/location alias or an address candidate.

Coordinates come from three places:

- Coordinates already present in the legacy CSV.
- Location seeds in `config.py`.
- Cached geocode results in `normalized_csv/geocoded_locations.csv`.

The ArcGIS agenda output is point-based. For roads, corridors, and large areas,
the point is a representative map point, not a parcel boundary or line geometry.
Exact road routes or project boundaries would require separate ArcGIS line or
polygon layers.

## ArcGIS deliverables

These are the main files for ArcGIS.

### `normalized_csv/arcgis_map_data.csv`

Legacy-compatible map data. This is designed to behave like the old working
ArcGIS CSV, with the same general location display pattern and popup fields.

Use this when you want the stable project/location layer that mirrors the old
map behavior.

### `normalized_csv/arcgis_agenda_map_data.csv`

Agenda-level map data. This is the newer file that maps individual agenda items
to locations and includes meeting/action details for popups.

Use this when you want users to click a location and page through chronological
agenda records for that place.

Important ArcGIS fields include:

- `ProjectName`
- `Board`
- `MeetingFormat`
- `MeetingType`
- `MeetingDate`
- `ArcGIS_Date`
- `AgendaItemID`
- `AgendaItemNumber`
- `ProjectTitle`
- `Summary`
- `ActionTaken`
- `Outcome`
- `MotionText`
- `ApplicantName`
- `ApplicationID`
- `LocationName`
- `Location`
- `Latitude`
- `Longitude`
- `Document_Link`
- `RecordType`

Long text fields are capped before export so ArcGIS does not reject rows because
of field-length limits.

The output is sorted by:

1. `LocationName`
2. `ProjectName`
3. `ArcGIS_Date`
4. `AgendaItemID`
5. `AgendaItemNumber`

That ordering is meant to make repeated records at the same map point appear in
chronological order.

### `normalized_csv/arcgis_missing_coordinates.csv`

Agenda rows that could not be mapped because they are missing coordinates.

This should normally be empty except for the header row. If rows appear here,
add or correct geocodes in `geocoded_locations.csv` or the location seed config,
then rerun the pipeline.

## Normalized CSV deliverables

These files line up with the refactored database shape and are useful for review,
database loading, or downstream analysis.

- `boards.csv`: board lookup values.
- `meeting_formats.csv`: detailed meeting format lookup values.
- `meeting_types.csv`: the four grouped database meeting types.
- `meetings_v2.csv`: one row per meeting/PDF, with board, format, date, venue,
  source URL, raw text, summary, and notes.
- `documents_v2.csv`: one row per source PDF/document.
- `agenda_items.csv`: extracted agenda items, including item numbers, project
  titles, summaries, outcomes, motions, vote results, applicants, and addresses.
- `locations_v2.csv`: agenda-item-level location records with coordinates and
  geocode confidence.
- `motions.csv`: extracted motion text, proposer/seconder when found, outcome,
  and vote counts when detected.
- `projects.csv`: project lookup values used by the matcher.
- `legacy_locations.csv`: legacy location reference data.

## Review deliverables

These files are for QA before importing data into ArcGIS or the database.

- `extraction_review.csv`: PDFs/items that may need human review, including weak
  matches, missing dates, scanned/OCR cases, and unlinked agenda items.
- `location_candidates.csv`: candidate places/addresses that may need geocoding
  or alias cleanup.
- `unmapped_agenda_items.csv`: agenda items that did not get a usable location.
- `agenda_location_accuracy_review.csv`: checks whether mapped agenda locations
  are supported by text evidence from the PDFs.
- `ocr_needed_files.txt`: scanned or weak-text files that still need OCR
  attention.

## Expected workflow

1. Run the pipeline locally.
2. Open `arcgis_missing_coordinates.csv`; it should have no data rows.
3. Review `agenda_location_accuracy_review.csv` and `extraction_review.csv`.
4. Import `arcgis_agenda_map_data.csv` into ArcGIS using `Latitude` and
   `Longitude`.
5. Use `ArcGIS_Date` or `MeetingDate` for date-based sorting/filtering.
6. Only push the branch or merge into production after the generated data has
   been reviewed.

## Production safety

The live GitHub Pages site publishes from the production branch configured in
GitHub Pages, currently understood to be `script`. Running this pipeline or
committing on a local feature branch does not change production.

Production changes only happen when updated static files are pushed to the Pages
source branch or when a branch is merged into that source branch.
