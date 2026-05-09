"""
Pipeline orchestrator and CLI entrypoint.

Run with::

    python -m app.pipeline.run                          # build silver only
    python -m app.pipeline.run --publish                # silver + upsert to Supabase
    python -m app.pipeline.run --verify                 # silver + diff vs Supabase
    python -m app.pipeline.run --publish --verify       # publish then verify (recommended)
    python -m app.pipeline.run --publish --dry-run      # show what would be sent, don't call
    python -m app.pipeline.run --strict                 # exit !=0 on any rejects, drift, or
                                                        # publish errors
    python -m app.pipeline.run --reset-reference --publish --verify
                                                        # **destructive**: wipe the small
                                                        # reference tables (projects,
                                                        # meeting_types, locations) on the
                                                        # remote, then republish from YAML.
                                                        # Use when remote IDs have drifted out
                                                        # of alignment with the YAML.

Outputs:

  * app/data/silver/                       — refined data
  * app/data/runs/<UTC-timestamp>/manifest.json — provenance for this run

Exit codes (with ``--strict``):

  * ``0`` — success.
  * ``2`` — silver build had rejected rows.
  * ``3`` — verify reported drift.
  * ``4`` — publish recorded a per-table error (e.g. PostgREST 23505).

The manifest records git SHA (when available), input/output row counts per
stage, reject counts, output file hashes, the elapsed wall time, and (when
publish/verify ran) a per-table report from each Supabase stage. This makes
runs reproducible and diffable across deploys.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.pipeline import config
from app.pipeline.load.silver import build_silver
from app.pipeline.publish.supabase import (
    has_publish_errors,
    publish as publish_to_supabase,
    reset_reference as reset_reference_tables,
)
from app.pipeline.verify.supabase import all_in_sync, verify as verify_against_supabase

logger = logging.getLogger("pipeline")


def _git_sha() -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(config.DATA_DIR.parent.parent),
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
        if out.returncode == 0:
            return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _file_hash(path: Path) -> dict:
    if not path.exists():
        return {"path": str(path), "exists": False}
    h = hashlib.sha256()
    size = 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
            size += len(chunk)
    return {
        "path": str(path.relative_to(config.DATA_DIR.parent.parent)),
        "exists": True,
        "sha256": h.hexdigest(),
        "bytes": size,
    }


def _write_manifest(payload: dict) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = config.RUNS_DIR / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    return manifest_path


def _maybe_run_supabase_stages(
    *,
    do_publish: bool,
    do_verify: bool,
    do_reset_reference: bool,
    dry_run: bool,
    manifest_stages: dict,
) -> tuple[bool, bool]:
    """Run reset/publish/verify against Supabase if enabled.

    Returns ``(drift_detected, publish_errors)`` so the caller can choose
    a strict-mode exit code.
    """
    if not (do_publish or do_verify or do_reset_reference):
        return False, False

    from app.db import try_get_client

    client = try_get_client()
    if client is None:
        logger.warning(
            "Supabase not configured (SUPABASE_URL / SUPABASE_KEY missing); "
            "skipping --publish/--verify/--reset-reference"
        )
        manifest_stages["supabase"] = {"skipped": "credentials not set"}
        return False, False

    drift_detected = False
    publish_errors = False

    if do_reset_reference:
        logger.warning(
            "reset-reference: deleting all rows from %s on remote%s",
            ", ".join(("projects", "meeting_types", "locations")),
            " (dry-run)" if dry_run else "",
        )
        reset_report = reset_reference_tables(client, dry_run=dry_run)
        manifest_stages["reset_reference"] = reset_report

    if do_publish:
        publish_report = publish_to_supabase(client, dry_run=dry_run)
        manifest_stages["publish"] = publish_report
        if has_publish_errors(publish_report):
            publish_errors = True
            logger.warning(
                "publish: one or more tables recorded an error — "
                "see manifest 'publish' section"
            )

    if do_verify:
        verify_report = verify_against_supabase(client)
        manifest_stages["verify"] = verify_report
        if not all_in_sync(verify_report):
            drift_detected = True
            logger.warning("verify: drift detected — see manifest 'verify' section")

    return drift_detected, publish_errors


def run(
    *,
    strict: bool = False,
    do_publish: bool = False,
    do_verify: bool = False,
    do_reset_reference: bool = False,
    dry_run: bool = False,
) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )
    started = time.monotonic()
    logger.info("starting pipeline (cwd=%s)", os.getcwd())

    stages: dict = {}

    silver_report = build_silver()
    stages["silver"] = silver_report
    logger.info("silver build complete: %s", silver_report)

    drift_detected, publish_errors = _maybe_run_supabase_stages(
        do_publish=do_publish,
        do_verify=do_verify,
        do_reset_reference=do_reset_reference,
        dry_run=dry_run,
        manifest_stages=stages,
    )

    elapsed_ms = int((time.monotonic() - started) * 1000)

    manifest = {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_ms": elapsed_ms,
        "git_sha": _git_sha(),
        "stages": stages,
        "outputs": [
            _file_hash(config.SILVER_MEETINGS),
            _file_hash(config.SILVER_DOCUMENTS),
            _file_hash(config.SILVER_DOCUMENTS_PLANNED),
            _file_hash(config.SILVER_REJECTS),
        ],
    }
    manifest_path = _write_manifest(manifest)
    logger.info("wrote manifest: %s", manifest_path)

    rejects = (
        silver_report["meetings"]["rejects"]
        + silver_report["documents"]["rejects"]
    )
    if rejects:
        logger.warning("pipeline finished with %d rejected rows", rejects)
        if strict:
            return 2
    if drift_detected and strict:
        return 3
    if publish_errors and strict:
        return 4
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Estero data refinement pipeline")
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Exit non-zero on rejects (code 2), drift (code 3), or "
            "publish errors (code 4)"
        ),
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="After silver build, upsert silver+reference into Supabase",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Read Supabase and diff against silver+reference; report drift",
    )
    parser.add_argument(
        "--reset-reference",
        action="store_true",
        help=(
            "**DESTRUCTIVE.** Delete every row from projects, meeting_types, "
            "and locations on the remote before publish. Use only when remote "
            "IDs have drifted out of alignment with the YAML and you want the "
            "next --publish to reseed them. Combine with --dry-run first."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "With --publish, show what would be upserted but make no remote "
            "writes. With --reset-reference, count rows that would be deleted "
            "but don't delete them."
        ),
    )
    args = parser.parse_args(argv)
    return run(
        strict=args.strict,
        do_publish=args.publish,
        do_verify=args.verify,
        do_reset_reference=args.reset_reference,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
