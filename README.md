# EagleGIS Scripts

Scripts for processing Village of Estero meeting-minute PDFs and producing the
data the GitHub Pages site (on the `main` branch) consumes.

## Pipeline

```
pdfs/*.pdf
   |
   |  pdf_pipeline.py        (extract + clean + parse Action: blocks)
   |     - prefers pdfplumber (much cleaner word boundaries than PyPDF2)
   |     - falls back to PyPDF2 if pdfplumber is unavailable
   v
fixminutes.py                -> estero_map_data.csv
sanitizeData.py              -> estero_map_data_polished.csv  (+ rewrites
                                                              Document_Link
                                                              to GitHub URLs)
refine_final_csv.py          -> pdfs/Estero_Meetings_Final.csv (the dataset
                                                                the frontend
                                                                renders)
```

`pdf_pipeline.py` is the single source of truth. It exposes:

- `extract_pages(path)`         – per-page text via pdfplumber/PyPDF2
- `clean_text(raw)`             – fixes mid-word breaks, stray leading capitals,
                                  `\ufffd` apostrophes, page-footer bleed
- `extract_actions(clean)`      – pulls every `Action:` block, lazy-stops at the
                                  next `Vote:` / `Motion:` / `Aye:` etc.
- `extract_meeting_type(...)`   – classifies the document using the filename
                                  hint and the title line near the top of the
                                  body (does **not** scan the agenda body, so
                                  agenda-item words like "PUBLIC HEARING:" or
                                  "Quasi-judicial" never hijack the type)
- `process_pdf(path)`           – full structured result (date, type, times,
                                  status, staff code, action list)

### Meeting types

Canonical labels emitted by `extract_meeting_type` (see
`pdf_pipeline.MEETING_TYPES`):

Council:
- `Regular Council Meeting`
- `Council Workshop`           *(budget, CIP, comprehensive plan, etc.)*
- `Special Called Meeting`     *(special, organizational, emergency,
                                 budget-hearing)*
- `Joint Meeting`              *(with Lee County MPO, Bonita Springs, …)*
- `Public Hearing`             *(zoning hearing, DRI development order)*
- `Quasi-judicial Hearing`
- `Goal-setting / Strategic Planning Session`

Planning, Zoning & Design Board (PZDB / PZB):
- `PZDB Public Information Meeting`
- `PZDB Public Hearing`
- `PZDB Workshop`
- `PZDB Meeting` *(default when no PZDB sub-type can be determined)*

## CI

`.github/workflows/process_pdfs.yml` runs on every push to the `script`
branch that touches a PDF or any pipeline script. It runs:

1. `python fixminutes.py` (raw extract)
2. `python sanitizeData.py` (polish + GitHub blob URLs)
3. `python refine_final_csv.py` (refresh frontend dataset preserving the
   manually curated `ProjectName`, `LocationName`, `Latitude`, `Longitude`)

and commits the updated CSVs back to the branch.

## Files

- `pdf_pipeline.py`        – shared extraction / cleaning module
- `fixminutes.py`          – produces `estero_map_data.csv`
- `sanitizeData.py`        – produces `estero_map_data_polished.csv`
- `refine_final_csv.py`    – refreshes `pdfs/Estero_Meetings_Final.csv`
- `script.py`              – older standalone version, kept for reference
