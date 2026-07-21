# Changes Summary

A high-level summary of the latest round of work landed on `main`
(8 feature commits + 1 integration merge; ~5,900 insertions across 49 files).

## CI/CD migration

All CI/CD has been migrated to the new GitHub repository:
**https://github.com/krocks9903/rag-arcgis-chatbot**

The pipelines (build, test, data refresh, and the RAG model-serving deploy)
now run from that repository as the canonical home for the chatbot stack.

## New features and improvements

### RAG model-serving service + cloud deployment
- Added a containerized **RAG model service** (FastAPI) with `/embed`,
  `/rerank`, and role-aware `/generate` endpoints, plus batch fan-out for
  concurrent work across role-tiered LLMs (utility vs. generation).
- **Cloud Run deployment** path: multi-stage `Dockerfile`, Cloud Build config,
  GitHub Actions workflow (Workload Identity Federation), and `Makefile`
  targets.
- Authored architecture plans: router-first RAG/text-to-SQL design, Cloud Run
  deployment guide, and a monorepo GitHub CI/CD architecture
  (`docs/RAG_PIPELINE_PLAN.md`, `docs/DEPLOY_CLOUD_RUN.md`,
  `docs/GITHUB_ARCHITECTURE.md`).

### Civic-participation & "finalized minutes" UI
- Pipeline now **classifies in-progress meetings** (PZ&DB project mapping,
  future placeholders, Pending status) and publishes `Finalized`,
  `InProgress`, and `InProgressNote` columns in the gold layer.
- Public site surfaces this with finalized/in-progress **status chips**, an
  "Official minutes posted?" **filter**, and a **PZ&DB civic-participation
  notice** that links residents to Engage Estero and the Village eComment form.
- This UI was ported onto the refactored split frontend
  (`index.html` + `app.js` + `styles.css`) during integration.

### Data quality
- **Strict location validation** with PDF verification: cross-checks resolved
  coordinates against the Estero bounding box and verifies expected location
  text appears in the minutes PDFs (strict-mode exit code on violations).
- Cross-platform fix so gold report paths use POSIX separators
  (`gold.py` `_rel()`), keeping outputs stable on Windows and Linux.

### Dashboard & API
- Added an **admin-only internal pin-notes API** for the map dashboard.

### Pipeline & repo hygiene
- Fixed the **"Refresh data artifacts" workflow** `ModuleNotFoundError` by
  prepending the repo root to `sys.path` in the CLI scraper shims so direct
  `python scripts/...` invocation works in Actions.
- Removed obsolete bootstrap scaffolding and tidied `.gitignore`.

## Integration
- Merged 18 upstream commits (ArcGIS agenda data, AI-gold outputs, PZDB pilot,
  accessibility work) into the feature branch, resolving 5 conflicts and
  regenerating gold artifacts from the merged pipeline.
- Verification: **126 tests passing**; frontend JS syntax-checked; gold
  pipeline rebuilt cleanly.
