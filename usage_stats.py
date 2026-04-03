# /// script
# dependencies = [
#   "duckdb",
#   "rich",
# ]
# ///

import os
import duckdb
from rich.console import Console
from rich.table import Table
from pathlib import Path

def get_usage_stats():
    db_path = Path("~/sync/local-first/processing_log.duckdb").expanduser()
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
        table.add_row(
            row[0], 
            str(row[1]), 
            str(row[2]), 
            str(row[3])
        )

    console.print(table)

if __name__ == "__main__":
    get_usage_stats()
