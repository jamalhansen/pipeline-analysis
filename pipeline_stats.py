# /// script
# dependencies = [
#   "duckdb",
#   "rich",
# ]
# ///

import duckdb
from rich.console import Console
from rich.table import Table
import os

def run_pipeline_stats():
    # Expand user paths
    db_paths = {
        "discovery": os.path.expanduser("~/sync/content-discovery/store.db"),
        "triage": os.path.expanduser("~/sync/thread-triage/thread-triage.db"),
        "social": os.path.expanduser("~/sync/social-reader/social-post-reader.db"),
        "tutor": os.path.expanduser("~/sync/japanese-tutor/japanese_tutor.db"),
    }

    # Connect to an in-memory DuckDB
    con = duckdb.connect()

    # Attach SQLite databases
    try:
        con.execute(f"ATTACH '{db_paths['discovery']}' AS discovery (TYPE sqlite);")
        con.execute(f"ATTACH '{db_paths['triage']}' AS triage (TYPE sqlite);")
        con.execute(f"ATTACH '{db_paths['social']}' AS social (TYPE sqlite);")
        if os.path.exists(db_paths['tutor']):
            con.execute(f"ATTACH '{db_paths['tutor']}' AS tutor (TYPE sqlite);")
    except Exception as e:
        print(f"Error attaching databases: {e}")
        return

    # Execute the curation pipeline query
    query = """
    SELECT 'discovery' as source, status, COUNT(*) as count FROM discovery.items GROUP BY status
    UNION ALL
    SELECT 'triage', human_disposition, COUNT(*) FROM triage.thread_triage GROUP BY human_disposition
    UNION ALL
    SELECT 'social', status, COUNT(*) FROM social.candidates GROUP BY status
    """
    
    if os.path.exists(db_paths['tutor']):
        query += """
        UNION ALL
        SELECT 'study', 'mastered', COUNT(*) FROM tutor.cards WHERE consecutive_correct >= 5
        UNION ALL
        SELECT 'study', 'learning', COUNT(*) FROM tutor.cards WHERE repetitions > 0 AND consecutive_correct < 5
        UNION ALL
        SELECT 'study', 'new', COUNT(*) FROM tutor.cards WHERE repetitions = 0
        """

    query += " ORDER BY source, status;"

    results = con.execute(query).fetchall()

    # Display results using Rich
    console = Console()
    table = Table(title="Full Curation Pipeline Stats")

    table.add_column("Source", style="cyan")
    table.add_column("Status / Disposition", style="magenta")
    table.add_column("Count", justify="right", style="green")

    for row in results:
        table.add_row(row[0], str(row[1]), str(row[2]))

    console.print(table)

if __name__ == "__main__":
    run_pipeline_stats()
