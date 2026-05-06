"""
Polishes ``estero_map_data.csv`` (produced by ``fixminutes.py``) into the
``estero_map_data_polished.csv`` artifact and rewrites the placeholder
``Document_Link`` to point at the GitHub-hosted PDFs on the ``script`` branch.

Cleaning logic is delegated to :mod:`pdf_pipeline.clean_text` so it stays in
lockstep with the actual PDF extraction step.
"""
from __future__ import annotations

import pandas as pd

from pdf_pipeline import clean_text

GITHUB_USER = "krocks9903"
GITHUB_REPO = "EagleGIS"
BRANCH_NAME = "script"
BASE_URL = (f"https://github.com/{GITHUB_USER}/{GITHUB_REPO}/blob/"
            f"{BRANCH_NAME}/pdfs/")


def professional_grooming(text: object) -> object:
    """Pass non-string / sentinel values through; clean everything else."""
    if not isinstance(text, str):
        return text
    if text in ("Meeting Cancelled", "No action found"):
        return text
    return clean_text(text)


def main() -> None:
    print("[sanitize] starting professional refinement...")
    try:
        df = pd.read_csv("estero_map_data.csv")
    except FileNotFoundError:
        print("[sanitize] estero_map_data.csv not found; nothing to polish")
        return

    print("[sanitize] step 1: rewriting Document_Link to GitHub blob URLs")
    df["Document_Link"] = df["Filename"].apply(
        lambda x: f"{BASE_URL}{str(x).replace(' ', '%20')}"
    )

    if "Action Taken" in df.columns:
        print("[sanitize] step 2: cleaning Action Taken text artifacts")
        df["Action Taken"] = df["Action Taken"].apply(professional_grooming)

    df.to_csv("estero_map_data_polished.csv", index=False)
    print("[sanitize] wrote estero_map_data_polished.csv")


if __name__ == "__main__":
    main()
