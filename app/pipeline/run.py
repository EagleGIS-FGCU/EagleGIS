"""
Pipeline orchestrator and CLI entrypoint.

Run with::

    python -m app.pipeline.run                          # build silver only
    python -m app.pipeline.run --publish                # silver + upsert to Supabase
    python -m app.pipeline.run --verify                 # silver + diff vs Supabase
    python -m app.pipeline.run --publish --verify       # publish then verify (recommended)
    python -m app.pipeline.run --publish --dry-run      # show what would be sent, don't call
    python -m app.pipeline.run --strict                 # exit !=0 on any rejects or drift

Outputs:

  * app/data/silver/                       — refined data
  * app/data/runs/<UTC-timestamp>/manifest.json — provenance for this run

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
from app.pipeline.publish.supabase import publish as publish_to_supabase
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
    dry_run: bool,
    manifest_stages: dict,
) -> bool:
    """Run publish/verify against Supabase if enabled. Returns True iff a
    'verify' run completed and reported drift."""
    if not (do_publish or do_verify):
        return False

    from app.db import try_get_client

    client = try_get_client()
    if client is None:
        logger.warning(
            "Supabase not configured (SUPABASE_URL / SUPABASE_KEY missing); "
            "skipping --publish/--verify"
        )
        manifest_stages["supabase"] = {"skipped": "credentials not set"}
        return False

    drift_detected = False

    if do_publish:
        publish_report = publish_to_supabase(client, dry_run=dry_run)
        manifest_stages["publish"] = publish_report

    if do_verify:
        verify_report = verify_against_supabase(client)
        manifest_stages["verify"] = verify_report
        if not all_in_sync(verify_report):
            drift_detected = True
            logger.warning("verify: drift detected — see manifest 'verify' section")

    return drift_detected


def run(
    *,
    strict: bool = False,
    do_publish: bool = False,
    do_verify: bool = False,
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

    drift_detected = _maybe_run_supabase_stages(
        do_publish=do_publish,
        do_verify=do_verify,
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
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Estero data refinement pipeline")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any rows fail validation (code 2) or any drift is detected (code 3)",
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
        "--dry-run",
        action="store_true",
        help="With --publish, show what would be upserted but make no remote calls",
    )
    args = parser.parse_args(argv)
    return run(
        strict=args.strict,
        do_publish=args.publish,
        do_verify=args.verify,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
