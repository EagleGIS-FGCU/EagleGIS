# PZDB pilot corpus

Planning Zoning & Design Board meeting minutes used for reproducible extraction testing.

## Scope

- **Board:** Planning Zoning & Design Board (PZDB)
- **Years:** 2022–2025 (scraped from [estero-fl.gov/pzdbminutes](https://estero-fl.gov/pzdbminutes/))
- **Count:** 45 PDFs (all minutes linked on the Village site for those years; `documents.csv` lists 53 rows but 8 are missing/cancelled/404 on the site)
- **Naming:** `YYYYMMDD PZDB Minutes.pdf` (single space before `PZDB`)

## Layout

```
data/raw/pzdb/
  2022/
  2023/
  2024/
  2025/
  manifest_pilot.csv
```

## Regenerate

From repo root:

```powershell
powershell -File scripts/download_pzdb_pilot.ps1
```

## Pipeline

Point Ethan's extractor at this folder:

```powershell
python scripts/build_normalized_csvs.py --pdf-dir data/raw/pzdb --out-dir normalized_csv
```

## Notes

- Village Council PDFs live on branch `script` under `pdfs/` — not duplicated here.
- 2023 source URLs on estero-fl.gov use extra spaces; files are saved with canonical names.
- PDFs are tracked with Git LFS.
