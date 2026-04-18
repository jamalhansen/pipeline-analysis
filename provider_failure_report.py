# /// script
# dependencies = [
#   "duckdb",
#   "rich",
# ]
# ///

"""Provider failure summary report from operational_log."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import duckdb
from rich.console import Console
from rich.table import Table

DEFAULT_DB_PATH = Path("~/sync/local-first/processing_log.duckdb").expanduser()


def resolve_db_path(cli_value: str | None) -> Path:
    if cli_value:
        return Path(cli_value).expanduser()
    if env := os.environ.get("LOCAL_FIRST_TRACKING_DB"):
        return Path(env).expanduser()
    return DEFAULT_DB_PATH


def top_tools(con: duckdb.DuckDBPyConnection, days: int, limit: int) -> list[tuple]:
    query = """
    SELECT
        COALESCE(tool_name, '(unknown)') AS tool_name,
        COUNT(*) AS failures
    FROM operational_log
    WHERE created_at >= CURRENT_TIMESTAMP - (? * INTERVAL '1 day')
      AND run_context LIKE 'provider_%'
    GROUP BY 1
    ORDER BY failures DESC
    LIMIT ?
    """
    return con.execute(query, [days, limit]).fetchall()


def top_contexts(con: duckdb.DuckDBPyConnection, days: int, limit: int) -> list[tuple]:
    query = """
    SELECT
        COALESCE(run_context, '(none)') AS run_context,
        COUNT(*) AS failures
    FROM operational_log
    WHERE created_at >= CURRENT_TIMESTAMP - (? * INTERVAL '1 day')
      AND run_context LIKE 'provider_%'
    GROUP BY 1
    ORDER BY failures DESC
    LIMIT ?
    """
    return con.execute(query, [days, limit]).fetchall()


def top_models(con: duckdb.DuckDBPyConnection, days: int, limit: int) -> list[tuple]:
    query = """
    SELECT
        COALESCE(source_location, '(unknown-model)') AS model,
        COUNT(*) AS failures
    FROM operational_log
    WHERE created_at >= CURRENT_TIMESTAMP - (? * INTERVAL '1 day')
      AND run_context LIKE 'provider_%'
    GROUP BY 1
    ORDER BY failures DESC
    LIMIT ?
    """
    return con.execute(query, [days, limit]).fetchall()


def print_table(
    console: Console, title: str, columns: list[str], rows: list[tuple]
) -> None:
    table = Table(title=title)
    for index, column in enumerate(columns):
        justify = "right" if index > 0 else "left"
        table.add_column(column, justify=justify)

    if not rows:
        table.add_row("No rows", *("-" for _ in columns[1:]))
    else:
        for row in rows:
            table.add_row(*(str(value) for value in row))

    console.print(table)


def run_report(db_path: Path, days: int, limit: int, verbose: bool = False) -> int:
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

        tool_rows = top_tools(con, days, limit)
        context_rows = top_contexts(con, days, limit)
        model_rows = top_models(con, days, limit)
    finally:
        con.close()

    print_table(
        console,
        f"Provider Failures by Tool (last {days} days)",
        ["Tool", "Count"],
        tool_rows,
    )
    print_table(
        console,
        f"Provider Failure Contexts (last {days} days)",
        ["Run Context", "Count"],
        context_rows,
    )
    print_table(
        console,
        f"Provider Failure Models (last {days} days)",
        ["Model", "Count"],
        model_rows,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Provider-focused failure summary from operational logs.",
    )
    parser.add_argument(
        "-b",
        "--db-path",
        default=None,
        help="Path to DuckDB file (default: LOCAL_FIRST_TRACKING_DB or ~/sync/local-first/processing_log.duckdb)",
    )
    parser.add_argument(
        "-d",
        "--days",
        type=int,
        default=7,
        help="Lookback window in days (default: 7)",
    )
    parser.add_argument(
        "-l",
        "--limit",
        type=int,
        default=10,
        help="Max rows per section (default: 10)",
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

    if args.days <= 0:
        parser.error("--days must be greater than 0")
    if args.limit <= 0:
        parser.error("--limit must be greater than 0")

    return run_report(
        resolve_db_path(args.db_path), args.days, args.limit, args.verbose
    )


if __name__ == "__main__":
    raise SystemExit(main())
