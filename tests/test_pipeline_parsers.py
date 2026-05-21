from __future__ import annotations

import sys
import unittest
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from build_normalized_csvs import NormalizedBuilder, infer_application_id, infer_vote_counts
from eaglegis_pipeline.classifiers import extract_address_candidates
from eaglegis_pipeline.extractors import extract_agenda_entries
from eaglegis_pipeline.sources import PdfAsset, iter_local_pdfs


class PipelineParserTests(unittest.TestCase):
    def test_application_id_ignores_common_word_fragments(self) -> None:
        self.assertIsNone(infer_application_id("Approved with staff conditions."))
        self.assertIsNone(infer_application_id("Standards for elevated single-family homes."))
        self.assertIsNone(infer_application_id("The site plan was discussed."))

    def test_application_id_extracts_pzdb_identifiers(self) -> None:
        self.assertEqual(
            infer_application_id("Development Order (DOS2023-E012) with staff conditions."),
            "DOS2023-E012",
        )
        self.assertEqual(
            infer_application_id("Limited Development Order LDO2024-E041 was approved."),
            "LDO2024-E041",
        )
        self.assertEqual(
            infer_application_id("Outdoor Consumption on Premises COP2023-E002."),
            "COP2023-E002",
        )

    def test_fallback_approved_does_not_capture_board_header(self) -> None:
        text = (
            "APPROVED BY BOARD FEBRUARY 13, 2024 Planning Zoning and Design Board Meeting "
            "Village of Estero 9401 Corkscrew Palms Circle Estero, FL 33928 "
            "1. CALL TO ORDER 2. ROLL CALL"
        )
        self.assertEqual(extract_agenda_entries(text), [])

    def test_action_entry_preserves_following_vote_text(self) -> None:
        text = (
            "Motion: Motion to approve. Motion by: Board Member Jones Seconded by: Board Member Wallace "
            "Action: Approved the Development Order with staff conditions. "
            "Vote: Aye: Board Members Jones, Wallace Nay: None Abstentions: None "
            "Public Input None."
        )
        entries = extract_agenda_entries(text)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].action_text, "Approved the Development Order with staff conditions")
        self.assertIn("Aye: Board Members Jones, Wallace", entries[0].vote_text or "")

    def test_section_fallback_extracts_non_action_location_item(self) -> None:
        text = (
            "PUBLIC INFORMATION MEETINGS (a) Estero Storage LLC - Zoning Amendment "
            "(No application submitted) (District 4) 10251 Arcos Avenue located on a 7-acre "
            "vacant site east of the Estero Medical Center. Staff Presentation/Comments Mary Gibbs. "
            "BOARD COMMUNICATIONS Next meeting."
        )
        entries = extract_agenda_entries(text)
        self.assertEqual(len(entries), 1)
        self.assertIn("No formal action recorded", entries[0].action_text)
        self.assertIn("10251 Arcos Avenue", entries[0].action_text)

    def test_address_candidates_include_estero_street_addresses(self) -> None:
        text = (
            "Culver's Coconut Point Development Order at 8400 Murano Del Lago Dr, "
            "east of US 41 and south of Pelican Colony Blvd."
        )
        self.assertIn("8400 Murano Del Lago Dr", extract_address_candidates(text))

    def test_vote_count_parses_aye_nay_abstentions(self) -> None:
        yes, no, abstain = infer_vote_counts(
            "Vote: Aye: Board Members Jones, Jeannin, Naratil, Chairman Wood "
            "Nay: Board Member Wallace Abstentions: None"
        )
        self.assertEqual(yes, 4)
        self.assertEqual(no, 1)
        self.assertEqual(abstain, 0)

    def test_empty_abstentions_stop_at_numbered_heading(self) -> None:
        yes, no, abstain = infer_vote_counts(
            "Vote: Aye: Board Members Jones, Jeannin Nay: Board Member Wallace "
            "Abstentions: 8. PUBLIC INPUT None."
        )
        self.assertEqual(yes, 2)
        self.assertEqual(no, 1)
        self.assertEqual(abstain, 0)

    def test_local_pdf_discovery_is_recursive(self) -> None:
        root = ROOT / ".test_tmp" / uuid4().hex
        try:
            nested = root / "2024"
            nested.mkdir(parents=True)
            pdf_path = nested / "20240213 PZDB Minutes.pdf"
            pdf_path.write_bytes(b"%PDF-test")
            assets = iter_local_pdfs(root)
            self.assertEqual([asset.filename for asset in assets], ["20240213 PZDB Minutes.pdf"])
        finally:
            if root.exists():
                for path in sorted(root.rglob("*"), reverse=True):
                    if path.is_file():
                        path.unlink()
                    else:
                        path.rmdir()
                root.rmdir()

    def test_builder_skips_exact_duplicate_agenda_items(self) -> None:
        builder = NormalizedBuilder(source_rows=[])
        kwargs = {
            "meeting_id": 1,
            "item_order": 1,
            "meeting_type": "Planning Zoning & Design Board",
            "item_title": "Development Order (DOS2024-E001)",
            "action_text": "Approved the Development Order with staff conditions",
            "vote_text": None,
            "staff_code": None,
            "needs_ocr": False,
            "date_missing": False,
            "used_csv_fallback": False,
            "fallback_projects": [],
            "fallback_locations": [],
            "asset": PdfAsset(path="test.pdf", filename="test.pdf", data=b""),
        }
        builder._add_action(**kwargs)
        builder._add_action(**kwargs)
        self.assertEqual(len(builder.agenda_items), 1)


if __name__ == "__main__":
    unittest.main()
