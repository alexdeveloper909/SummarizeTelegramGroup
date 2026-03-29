from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from telegram_group_summarizer.config import load_config
from telegram_group_summarizer.db import ensure_database, get_run
from telegram_group_summarizer.logging_utils import configure_logging
from telegram_group_summarizer.report_layout import (
    artifact_directory_path,
    classify_legacy_report_file,
)


def _fallback_started_at(path: Path) -> str:
    modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return modified_at.isoformat()


def _resolve_started_at(connection, path: Path, run_id: str) -> str:
    run = get_run(connection, run_id)
    if run is not None and run["started_at"]:
        return str(run["started_at"])
    return _fallback_started_at(path)


def _update_report_output_paths(connection, run_id: str, output_path: Path) -> None:
    output_path_str = str(output_path)
    connection.execute(
        "UPDATE collection_runs SET report_output_path = ? WHERE run_id = ?",
        (output_path_str, run_id),
    )
    connection.execute(
        "UPDATE generated_reports SET output_path = ? WHERE run_id = ?",
        (output_path_str, run_id),
    )
    connection.commit()


def _move_file(source_path: Path, destination_path: Path, *, dry_run: bool) -> bool:
    if source_path == destination_path:
        return False
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    if destination_path.exists():
        if source_path.read_bytes() == destination_path.read_bytes():
            if not dry_run:
                source_path.unlink()
            return False
        raise FileExistsError(
            f"Refusing to overwrite existing file with different content: {destination_path}"
        )
    if not dry_run:
        source_path.rename(destination_path)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Move flat report artifacts into the dated report folder layout."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan the migration without moving files.",
    )
    args = parser.parse_args()

    config = load_config()
    configure_logging(config.log_level)
    connection = ensure_database(config)

    moved_count = 0
    skipped_count = 0
    for path in sorted(config.reports_dir.iterdir()):
        if path.name == ".gitkeep" or path.is_dir():
            continue

        placement = classify_legacy_report_file(path)
        if placement is None:
            skipped_count += 1
            print(f"SKIP {path.name}")
            continue

        started_at = _resolve_started_at(connection, path, placement.run_id)
        destination_path = (
            artifact_directory_path(
                config.reports_dir,
                started_at,
                placement.artifact_directory,
            )
            / placement.filename
        )
        changed = _move_file(path, destination_path, dry_run=args.dry_run)
        action = "MOVE" if changed else "KEEP"
        print(f"{action} {path.name} -> {destination_path.relative_to(config.reports_dir)}")
        if changed:
            moved_count += 1
        else:
            skipped_count += 1

        if placement.artifact_directory == "report" and not args.dry_run:
            _update_report_output_paths(connection, placement.run_id, destination_path)

    print(f"moved={moved_count} skipped={skipped_count}")


if __name__ == "__main__":
    main()
