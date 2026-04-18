# /// script
# dependencies = [
#   "duckdb",
#   "rich",
# ]
# ///

import argparse
import os
from pathlib import Path

import duckdb
from rich.console import Console
from rich.table import Table


DEFAULT_DB_PATH = Path("~/sync/local-first/processing_log.duckdb").expanduser()


def _resolve_db_path(cli_value: str | None) -> Path:
    if cli_value:
        return Path(cli_value).expanduser()
    if env := os.environ.get("LOCAL_FIRST_TRACKING_DB"):
        return Path(env).expanduser()
    return DEFAULT_DB_PATH


def _top_warning_tools(con: duckdb.DuckDBPyConnection, days: int, limit: int):
    query = """
    SELECT
        COALESCE(tool_name, '(unknown)') AS tool_name,
        COUNT(*) AS warning_count
    FROM operational_log
    WHERE created_at >= CURRENT_TIMESTAMP - (? * INTERVAL '1 day')
    GROUP BY 1
    ORDER BY warning_count DESC
    LIMIT ?
    """
    return con.execute(query, [days, limit]).fetchall()


def _recurring_exception_types(con: duckdb.DuckDBPyConnection, days: int, limit: int):
    query = """
    SELECT
        exception_type,
        COUNT(*) AS occurrences
    FROM operational_log
    WHERE created_at >= CURRENT_TIMESTAMP - (? * INTERVAL '1 day')
      AND exception_type IS NOT NULL
      AND exception_type <> ''
    GROUP BY 1
    ORDER BY occurrences DESC
    LIMIT ?
    """
    return con.execute(query, [days, limit]).fetchall()


def _most_failing_modules(con: duckdb.DuckDBPyConnection, days: int, limit: int):
    query = """
    SELECT
        COALESCE(module, '(unknown)') AS module_name,
        COUNT(*) AS error_count
    FROM operational_log
    WHERE created_at >= CURRENT_TIMESTAMP - (? * INTERVAL '1 day')
      AND level IN ('ERROR', 'CRITICAL')
    GROUP BY 1
    ORDER BY error_count DESC
    LIMIT ?
    """
    return con.execute(query, [days, limit]).fetchall()


def _print_table(console: Console, title: str, columns: list[str], rows: list[tuple]):
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

        warning_rows = _top_warning_tools(con, days, limit)
        exception_rows = _recurring_exception_types(con, days, limit)
        module_rows = _most_failing_modules(con, days, limit)
    finally:
        con.close()

    _print_table(
        console,
        f"Top Warning-Producing Tools (last {days} days)",
        ["Tool", "Warnings"],
        warning_rows,
    )
    _print_table(
        console,
        f"Recurring Exception Types (last {days} days)",
        ["Exception Type", "Occurrences"],
        exception_rows,
    )
    _print_table(
        console,
        f"Most Common Failing Modules (last {days} days)",
        ["Module", "Errors"],
        module_rows,
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Report warning/error trends from local-first operational logs.",
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
        default=30,
        help="Lookback window in days (default: 30)",
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
    parser = _build_parser()
    args = parser.parse_args()

    if args.days <= 0:
        parser.error("--days must be greater than 0")
    if args.limit <= 0:
        parser.error("--limit must be greater than 0")

    return run_report(
        _resolve_db_path(args.db_path), args.days, args.limit, args.verbose
    )


if __name__ == "__main__":
    raise SystemExit(main())
