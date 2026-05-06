"""
Legacy entry point. Walks ``pdfs/`` (or the current directory) and writes
``estero_map_data.csv`` for downstream tooling.

The actual extraction/cleaning lives in :mod:`pdf_pipeline` so every script
in this repo (``fixminutes.py``, ``sanitizeData.py``, ``refine_final_csv.py``)
shares the same logic.
"""
from __future__ import annotations

import csv
import os
import re

from pdf_pipeline import process_pdf

BASE_URL = "https://your-website.com/estero-pdfs/"
HEADERS = [
    "Filename", "Meeting Date", "ArcGIS_Date", "Meeting Type", "Location",
    "Start Time", "End Time", "Action Taken", "Staff Code", "Status",
    "Document_Link",
]
# 'Meeting Type' values come from pdf_pipeline.MEETING_TYPES.

# Streets and developments referenced in Estero minutes; used to guess a
# project location from the action text.
ESTERO_LOCATIONS = [
    "Corkscrew Road", "Three Oaks Parkway", "US 41", "Tamiami Trail",
    "Williams Road", "Estero Parkway", "Ben Hill Griffin Parkway",
    "Via Coconut Point", "Coconut Road", "Broadway Avenue", "River Ranch Road",
    "Sandy Lane", "Cypress Bend", "Estero River", "Bamboo Island",
    "River Oaks Preserve", "Fountain Lakes", "Vintage Parkway",
    "Pelican Sound", "Grandezza", "Wildcat Run", "Shadow Wood", "The Brooks",
    "Copperleaf", "Bella Terra", "Stoneybrook", "Country Creek",
    "Marsh Landing", "Coconut Shores", "Rapallo", "Lighthouse Bay",
    "Breckenridge", "Meadowbrook", "Hertz Arena", "Coconut Point",
    "Miromar Outlets", "Koreshan State Park", "Estero High School",
    "Spring Run", "Coconut Point Mall", "Estero Bay Village", "Sunny Grove",
    "University Village", "Genova", "Tidewater", "Wild Blue", "West Bay",
    "Estero Place", "Loves", "Cascades", "Villages at Country Creek",
]

DEFAULT_LOCATION = "9401 Corkscrew Palms Circle, Estero, FL 33928"


def extract_project_location(action_text: str) -> str:
    if not action_text or "Meeting Cancelled" in action_text:
        return DEFAULT_LOCATION
    for loc in ESTERO_LOCATIONS:
        m = re.search(rf"(\d+)\s+{re.escape(loc)}", action_text, re.I)
        if m:
            return f"{m.group(1)} {loc}, Estero, FL"
    for i, a in enumerate(ESTERO_LOCATIONS):
        for b in ESTERO_LOCATIONS[i + 1:]:
            if (re.search(rf"\b{re.escape(a)}\b", action_text, re.I)
                    and re.search(rf"\b{re.escape(b)}\b", action_text, re.I)):
                return f"{a} and {b}, Estero, FL"
    for loc in ESTERO_LOCATIONS:
        if re.search(rf"\b{re.escape(loc)}\b", action_text, re.I):
            return f"{loc}, Estero, FL"
    return DEFAULT_LOCATION


def row_for_pdf(pdf_path: str) -> dict:
    fn = os.path.basename(pdf_path)
    try:
        result = process_pdf(pdf_path)
    except Exception as e:
        print(f"[fixminutes] {fn}: {e}")
        return {
            "Filename": fn, "Meeting Date": "Unknown", "ArcGIS_Date": "",
            "Meeting Type": "Regular Council Meeting",
            "Location": DEFAULT_LOCATION,
            "Start Time": "9:30 am", "End Time": "Unknown",
            "Action Taken": "No action found", "Staff Code": "N/A",
            "Status": "Accepted", "Document_Link": BASE_URL + fn,
        }

    md = result["meeting_date"]
    arc = md.strftime("%Y-%m-%d") if md else ""
    if md:
        pretty = f"{md.strftime('%B')} {md.day}, {md.year}"
    else:
        pretty = "Unknown"

    action_text = result["action_text"] or "No action found"
    return {
        "Filename": fn,
        "Meeting Date": pretty,
        "ArcGIS_Date": arc,
        "Meeting Type": result["meeting_type"],
        "Location": extract_project_location(action_text),
        "Start Time": result["start_time"] or "9:30 am",
        "End Time": result["end_time"] or "Unknown",
        "Action Taken": action_text,
        "Staff Code": result["staff_code"] or "N/A",
        "Status": result["status"],
        "Document_Link": BASE_URL + fn,
    }


def main() -> None:
    pdf_dir = "pdfs" if os.path.isdir("pdfs") else "."
    pdfs = sorted(
        os.path.join(pdf_dir, f) for f in os.listdir(pdf_dir)
        if f.lower().endswith(".pdf")
    )
    rows = [row_for_pdf(p) for p in pdfs]
    with open("estero_map_data.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"[fixminutes] processed {len(pdfs)} PDFs -> estero_map_data.csv")


if __name__ == "__main__":
    main()
