# PZDB Pilot QA Validation

## Metrics

- PDFs scanned: `45`
- Meetings: `44`
- Agenda items: `125`
- Locations: `107`
- Motions: `83`
- ArcGIS rows: `107`
- ArcGIS missing coordinates: `0`
- Blank ArcGIS lat/lon rows: `0`
- Malformed application IDs: `0`
- Motions with parsed vote counts: `75`

## Integrity Checks

- Bad agenda item meeting refs: `0`
- Bad location item refs: `0`
- Bad motion item refs: `0`
- Duplicate item summaries within a meeting: `0`
- Meetings without items: `0`

## Remaining Watch Items

- Items without addresses are expected for procedural, consent, and non-site-specific actions.
- Motions without parsed vote counts generally lack explicit Aye/Nay sections in extracted text.
- Duplicate item summaries should be manually reviewed when nonzero.
