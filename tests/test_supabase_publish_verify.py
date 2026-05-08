"""
Tests for the Supabase publish + verify stages.

Uses an in-process ``FakeSupabaseClient`` that mimics the subset of the
supabase-py surface we actually call: ``client.table(name).upsert(rows,
on_conflict=pk).execute()`` and ``client.table(name).select("*")
.range(a, b).execute().data``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from app.pipeline.publish.supabase import PUBLISH_ORDER, TABLE_SPEC, publish, slice_fields
from app.pipeline.verify.supabase import all_in_sync, diff_table, verify


# ---------------------------------------------------------------------------
# Fake Supabase client
# ---------------------------------------------------------------------------

@dataclass
class _Resp:
    data: list[dict]


class _Query:
    def __init__(self, store: dict[str, dict[Any, dict]], table: str):
        self._store = store
        self._table = table
        self._range: tuple[int, int] | None = None

    def select(self, _what: str = "*") -> "_Query":
        return self

    def range(self, lo: int, hi: int) -> "_Query":
        self._range = (lo, hi)
        return self

    def upsert(self, rows: list[dict], on_conflict: str | None = None) -> "_Query":
        pk = on_conflict or "id"
        bucket = self._store.setdefault(self._table, {})
        for r in rows:
            bucket[r[pk]] = dict(r)
        return self

    def execute(self) -> _Resp:
        bucket = self._store.get(self._table, {})
        rows = list(bucket.values())
        if self._range is not None:
            lo, hi = self._range
            rows = rows[lo : hi + 1]
        return _Resp(data=rows)


@dataclass
class FakeSupabaseClient:
    store: dict[str, dict[Any, dict]] = field(default_factory=dict)

    def table(self, name: str) -> _Query:
        return _Query(self.store, name)

    def seed(self, table: str, rows: list[dict]) -> None:
        spec = TABLE_SPEC[table]
        bucket = self.store.setdefault(table, {})
        for r in rows:
            bucket[r[spec["pk"]]] = dict(r)


# ---------------------------------------------------------------------------
# diff_table unit tests
# ---------------------------------------------------------------------------

def test_diff_table_in_sync():
    fields = ["id", "name"]
    local = [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]
    remote = [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]
    rep = diff_table(local, remote, "id", fields)
    assert rep["in_sync"] is True
    assert rep["local_count"] == 2 and rep["remote_count"] == 2


def test_diff_table_local_only():
    rep = diff_table(
        [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}],
        [{"id": 1, "name": "A"}],
        "id", ["id", "name"],
    )
    assert rep["in_sync"] is False
    assert rep["in_local_only_count"] == 1


def test_diff_table_remote_only():
    rep = diff_table(
        [{"id": 1, "name": "A"}],
        [{"id": 1, "name": "A"}, {"id": 9, "name": "stranger"}],
        "id", ["id", "name"],
    )
    assert rep["in_remote_only_count"] == 1
    assert rep["in_sync"] is False


def test_diff_table_field_mismatch():
    rep = diff_table(
        [{"id": 1, "name": "A"}],
        [{"id": 1, "name": "A-edited"}],
        "id", ["id", "name"],
    )
    assert rep["mismatched_count"] == 1
    assert rep["mismatched_sample"][0]["fields"]["name"] == {"local": "A", "remote": "A-edited"}


def test_diff_table_string_int_normalize():
    """CSV gives strings, Supabase gives ints — they should compare equal."""
    rep = diff_table(
        [{"id": "1", "name": "A"}],
        [{"id": 1, "name": "A"}],
        "id", ["id", "name"],
    )
    assert rep["in_sync"] is True


# ---------------------------------------------------------------------------
# slice_fields
# ---------------------------------------------------------------------------

def test_slice_fields_drops_extras_and_normalizes_empty():
    rows = [{"project_id": 1, "project_name": "X", "extra": "drop me", "description": ""}]
    out = slice_fields(rows, TABLE_SPEC["projects"]["fields"])
    assert "extra" not in out[0]
    assert out[0]["description"] is None


# ---------------------------------------------------------------------------
# publish end-to-end against the fake client
# ---------------------------------------------------------------------------

def test_publish_upserts_in_fk_order_and_is_idempotent():
    fake = FakeSupabaseClient()
    report = publish(fake, dry_run=False)

    # Every managed table got a report and at least the reference rows.
    for table in PUBLISH_ORDER:
        assert table in report
    assert report["projects"]["upserted"] >= 1
    assert report["meeting_types"]["upserted"] >= 1
    assert report["locations"]["upserted"] >= 1

    # Re-running with no local changes produces the same end state
    # (upsert is idempotent: same row count, same content).
    snapshot = {t: dict(rows) for t, rows in fake.store.items()}
    publish(fake, dry_run=False)
    assert fake.store == snapshot


def test_publish_dry_run_makes_no_writes():
    fake = FakeSupabaseClient()
    report = publish(fake, dry_run=True)
    assert all(report[t]["dry_run"] for t in PUBLISH_ORDER if report[t].get("upserted"))
    assert fake.store == {}


# ---------------------------------------------------------------------------
# verify end-to-end against the fake client
# ---------------------------------------------------------------------------

def test_verify_reports_in_sync_after_publish():
    fake = FakeSupabaseClient()
    publish(fake, dry_run=False)
    rep = verify(fake)
    assert all_in_sync(rep), rep


def test_verify_detects_remote_only_drift():
    fake = FakeSupabaseClient()
    publish(fake, dry_run=False)
    fake.seed("projects", [{
        "project_id": 9999, "project_name": "Drifted",
        "description": None, "status": "Active",
    }])
    rep = verify(fake)
    assert rep["projects"]["in_sync"] is False
    assert rep["projects"]["in_remote_only_count"] == 1


def test_verify_detects_field_mismatch():
    fake = FakeSupabaseClient()
    publish(fake, dry_run=False)
    # Mutate a published row in the fake remote.
    any_pk = next(iter(fake.store["projects"]))
    fake.store["projects"][any_pk]["project_name"] = "Tampered"
    rep = verify(fake)
    assert rep["projects"]["in_sync"] is False
    assert rep["projects"]["mismatched_count"] >= 1
