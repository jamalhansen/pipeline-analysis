# /// script
# dependencies = [
#   "duckdb",
#   "rich",
# ]
# ///

import argparse
import os
from collections import Counter
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


def _resolve_db_path(cli_value: str | None) -> Path:
    if cli_value:
        return _normalize_db_path(
            Path(cli_value).expanduser(), default_filename="error_log.duckdb"
        )
    if env := os.environ.get("LOCAL_FIRST_ERROR_LOG_DB"):
        return _normalize_db_path(
            Path(env).expanduser(), default_filename="error_log.duckdb"
        )
    return DEFAULT_DB_PATH


def _top_warning_tools_query(table_name: str) -> str:
    if table_name == "operational_log":
        return """
        SELECT
            COALESCE(tool_name, '(unknown)') AS tool_name,
            COUNT(*) AS warning_count
        FROM operational_log
        WHERE created_at >= CURRENT_TIMESTAMP - (? * INTERVAL '1 day')
        GROUP BY 1
        ORDER BY warning_count DESC
        LIMIT ?
        """

    return """
    SELECT
        COALESCE(tool_name, '(unknown)') AS tool_name,
        COUNT(*) AS warning_count
    FROM processing_log
    WHERE created_at >= CURRENT_TIMESTAMP - (? * INTERVAL '1 day')
      AND (
          COALESCE(xml_fallbacks, 0) > 0
          OR COALESCE(parse_errors, 0) > 0
          OR COALESCE(success, TRUE) = FALSE
      )
    GROUP BY 1
    ORDER BY warning_count DESC
    LIMIT ?
    """


def _recurring_exception_types_query(table_name: str) -> str:
    if table_name == "operational_log":
        return """
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

    return """
    SELECT
        COALESCE(
            NULLIF(
                regexp_extract(COALESCE(error_message, ''), '^([A-Za-z_][A-Za-z0-9_\\.]*)[: ]', 1),
                ''
            ),
            '(unknown)'
        ) AS exception_type,
        COUNT(*) AS occurrences
    FROM processing_log
    WHERE created_at >= CURRENT_TIMESTAMP - (? * INTERVAL '1 day')
      AND error_message IS NOT NULL
      AND error_message <> ''
    GROUP BY 1
    ORDER BY occurrences DESC
    LIMIT ?
    """


def _most_failing_context_query(table_name: str) -> str:
    if table_name == "operational_log":
        return """
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

    return """
    SELECT
        tool_name,
        source_location
    FROM processing_log
    WHERE created_at >= CURRENT_TIMESTAMP - (? * INTERVAL '1 day')
      AND COALESCE(success, TRUE) = FALSE
    """


def _resolve_log_table(con: duckdb.DuckDBPyConnection) -> str | None:
    tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
    if "operational_log" in tables:
        return "operational_log"
    if "processing_log" in tables:
        return "processing_log"
    return None


def _aggregate_processing_fail_contexts(rows: list[tuple], limit: int) -> list[tuple]:
    counter: Counter[tuple[str, str]] = Counter()
    for tool_name, source_location in rows:
        tool = tool_name or "(unknown-tool)"
        source = source_location or "(missing source_location)"
        counter[(tool, source)] += 1
    return [
        (tool, source, count) for (tool, source), count in counter.most_common(limit)
    ]


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
        table_name = _resolve_log_table(con)
        if table_name is None:
            console.print(
                "Table operational_log/processing_log not found in the selected DB."
            )
            return 1

        console.print(f"DB: {db_path}")

        if verbose:
            total = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
            console.print(f"Rows available in {table_name}: {total}")

        warning_rows = con.execute(
            _top_warning_tools_query(table_name), [days, limit]
        ).fetchall()
        exception_rows = con.execute(
            _recurring_exception_types_query(table_name),
            [days, limit],
        ).fetchall()
        if table_name == "operational_log":
            context_rows = con.execute(
                _most_failing_context_query(table_name),
                [days, limit],
            ).fetchall()
        else:
            raw_context_rows = con.execute(
                _most_failing_context_query(table_name),
                [days],
            ).fetchall()
            context_rows = _aggregate_processing_fail_contexts(raw_context_rows, limit)
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
    if table_name == "operational_log":
        _print_table(
            console,
            f"Most Common Failing Modules (last {days} days)",
            ["Module", "Errors"],
            context_rows,
        )
    else:
        _print_table(
            console,
            f"Most Common Failing Sources (last {days} days)",
            ["Tool", "Source Location", "Errors"],
            context_rows,
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
        help="Path to DuckDB file (default: LOCAL_FIRST_ERROR_LOG_DB or ~/sync/logging/error_log.duckdb)",
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
