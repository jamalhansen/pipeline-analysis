# /// script
# dependencies = [
#   "duckdb",
#   "rich",
# ]
# ///

"""Recent provider failure events with optional filters."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import duckdb
from rich.console import Console
from rich.table import Table

DEFAULT_DB_PATH = Path("~/sync/logging/error_log.duckdb").expanduser()


def _normalize_db_path(path: Path, default_filename: str) -> Path:
    if path.exists() and path.is_dir():
        return path / default_filename
    if path.suffix.lower() == ".duckdb":
        return path
    if not path.suffix:
        return path / default_filename
    return path


def resolve_db_path(cli_value: str | None) -> Path:
    if cli_value:
        return _normalize_db_path(
            Path(cli_value).expanduser(), default_filename="error_log.duckdb"
        )
    if env := os.environ.get("LOCAL_FIRST_ERROR_LOG_DB"):
        return _normalize_db_path(
            Path(env).expanduser(), default_filename="error_log.duckdb"
        )
    return DEFAULT_DB_PATH


def fetch_recent(
    con: duckdb.DuckDBPyConnection,
    hours: int,
    limit: int,
    tool_name: str | None,
    context_filter: str | None,
) -> list[tuple]:
    query = """
    SELECT
        created_at,
        COALESCE(tool_name, '(unknown)') AS tool_name,
        COALESCE(run_context, '(none)') AS run_context,
        COALESCE(source_location, '(unknown-model)') AS model,
        LEFT(message, 140) AS message
    FROM operational_log
    WHERE created_at >= CURRENT_TIMESTAMP - (? * INTERVAL '1 hour')
      AND run_context LIKE 'provider_%'
      AND (? IS NULL OR tool_name = ?)
      AND (? IS NULL OR run_context LIKE '%' || ? || '%')
    ORDER BY created_at DESC
    LIMIT ?
    """
    return con.execute(
        query,
        [hours, tool_name, tool_name, context_filter, context_filter, limit],
    ).fetchall()


def run_report(
    db_path: Path,
    hours: int,
    limit: int,
    tool_name: str | None,
    context_filter: str | None,
    verbose: bool = False,
) -> int:
    console = Console()

    if not db_path.exists():
        console.print(f"Database not found: {db_path}")
        return 1

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
        if "operational_log" not in tables:
            console.print("Table operational_log not found in the selected DB.")
            return 1

        if verbose:
            total = con.execute("SELECT COUNT(*) FROM operational_log").fetchone()[0]
            console.print(f"Operational rows available: {total}")

        rows = fetch_recent(con, hours, limit, tool_name, context_filter)
    finally:
        con.close()

    table = Table(title=f"Recent Provider Failures (last {hours} hours)")
    table.add_column("Created At")
    table.add_column("Tool")
    table.add_column("Run Context")
    table.add_column("Model")
    table.add_column("Message")

    if not rows:
        table.add_row("No rows", "-", "-", "-", "-")
    else:
        for row in rows:
            table.add_row(*(str(value) for value in row))

    console.print(table)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Show recent provider failure events from operational logs.",
    )
    parser.add_argument(
        "-b",
        "--db-path",
        default=None,
        help="Path to DuckDB file (default: LOCAL_FIRST_ERROR_LOG_DB or ~/sync/logging/error_log.duckdb)",
    )
    parser.add_argument(
        "-H",
        "--hours",
        type=int,
        default=24,
        help="Lookback window in hours (default: 24)",
    )
    parser.add_argument(
        "-l",
        "--limit",
        type=int,
        default=30,
        help="Number of rows to show (default: 30)",
    )
    parser.add_argument(
        "-t",
        "--tool",
        default=None,
        help="Optional tool_name filter (exact match)",
    )
    parser.add_argument(
        "-c",
        "--context",
        default=None,
        help="Optional run_context substring filter",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show extra diagnostics.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.hours <= 0:
        parser.error("--hours must be greater than 0")
    if args.limit <= 0:
        parser.error("--limit must be greater than 0")

    return run_report(
        resolve_db_path(args.db_path),
        args.hours,
        args.limit,
        args.tool,
        args.context,
        args.verbose,
    )


if __name__ == "__main__":
    raise SystemExit(main())
