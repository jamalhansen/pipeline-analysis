# /// script
# dependencies = [
#   "duckdb",
#   "rich",
# ]
# ///

import os
from pathlib import Path

import duckdb
from rich.console import Console
from rich.table import Table

DEFAULT_DB_PATH = Path("~/sync/local-first/processing_log.duckdb").expanduser()


def _normalize_db_path(path: Path, default_filename: str) -> Path:
    if path.exists() and path.is_dir():
        return path / default_filename
    if path.suffix.lower() == ".duckdb":
        return path
    if not path.suffix:
        return path / default_filename
    return path


def resolve_db_path() -> Path:
    if env := os.environ.get("LOCAL_FIRST_TRACKING_DB"):
        candidate = _normalize_db_path(
            Path(env).expanduser(), default_filename="processing_log.duckdb"
        )
        if candidate.exists() or not DEFAULT_DB_PATH.exists():
            return candidate
    return DEFAULT_DB_PATH


def get_usage_stats():
    db_path = resolve_db_path()
    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return

    con = duckdb.connect(str(db_path))

    # Query for daily, weekly, and total counts per tool
    query = """
    WITH stats AS (
        SELECT 
            tool_name,
            CASE WHEN created_at >= CURRENT_DATE THEN 1 ELSE 0 END as is_today,
            CASE WHEN created_at >= date_trunc('week', CURRENT_DATE) THEN 1 ELSE 0 END as is_week
        FROM processing_log
    )
    SELECT 
        tool_name,
        SUM(is_today) as today_count,
        SUM(is_week) as week_count,
        COUNT(*) as total_count
    FROM stats
    GROUP BY tool_name
    ORDER BY total_count DESC;
    """

    results = con.execute(query).fetchall()
    con.close()

    console = Console()
    table = Table(title="LLM Usage Stats by Tool")

    table.add_column("Tool", style="cyan")
    table.add_column("Today", justify="right", style="green")
    table.add_column("This Week", justify="right", style="magenta")
    table.add_column("Total", justify="right", style="blue")

    for row in results:
        table.add_row(row[0], str(row[1]), str(row[2]), str(row[3]))

    console.print(table)


if __name__ == "__main__":
    get_usage_stats()
