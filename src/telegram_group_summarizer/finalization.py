from __future__ import annotations

from .db import (
    count_raw_messages,
    delete_raw_messages,
    get_generated_report,
    get_run_with_target,
    update_run_status,
)
from .models import ResolvedTarget, TargetReference


async def finalize_run(
    *,
    connection,
    telegram_client=None,
    run_id: str,
    mark_read: bool,
    purge_raw: bool,
) -> dict:
    run = get_run_with_target(connection, run_id)
    if run is None:
        raise ValueError(f"Run {run_id} does not exist.")

    report = get_generated_report(connection, run_id)
    if report is None:
        raise ValueError(f"Run {run_id} has no stored report. Refusing to finalize.")

    resolved_target = ResolvedTarget(
        target_key=run["target_key"],
        entity_id=run["telegram_entity_id"],
        entity_type=run["telegram_entity_type"],
        display_name=run["target_display_name"],
        reference=TargetReference(kind="target_key", value=run["target_key"]),
    )

    try:
        if mark_read and run["read_marked_at"] is None:
            if telegram_client is None:
                raise ValueError("A Telegram client is required when mark_read is requested.")
            await telegram_client.mark_target_read(resolved_target)
            update_run_status(connection, run_id, status="summarized", read_marked=True)

        purged_rows = 0
        if purge_raw and count_raw_messages(connection, run_id) > 0:
            purged_rows = delete_raw_messages(connection, run_id)
            update_run_status(connection, run_id, status="summarized", raw_purged=True)

        update_run_status(connection, run_id, status="finalized", completed=True)
        return {
            "run_id": run_id,
            "marked_read": bool(mark_read),
            "purged_rows": purged_rows,
            "report_output_path": report["output_path"],
        }
    except Exception as exc:
        update_run_status(
            connection, run_id, status="failed_finalization", error_summary=str(exc), completed=True
        )
        raise
