# pipeline-analysis

Standalone analysis scripts for workspace telemetry and operational health. Queries the two DuckDB databases that the local-first toolchain writes to at runtime.

## What It Does

Four scripts, two databases:

| Script | Database | Purpose |
|--------|----------|---------|
| `usage_stats.py` | `processing_log.duckdb` | LLM usage by tool (daily, weekly, total counts) |
| `operational_log_report.py` | `error_log.duckdb` | Warning/error summary by tool and exception type |
| `provider_failure_report.py` | `error_log.duckdb` | Provider failures aggregated by tool, context, model |
| `provider_failure_recent.py` | `error_log.duckdb` | Recent provider failure events with filters |

## Usage

```bash
# From workspace root
make usage          # LLM usage summary
make ops-report     # Operational warning/error summary (last 30 days)

# Direct invocation
uv run pipeline-analysis/usage_stats.py
uv run pipeline-analysis/operational_log_report.py --days 30 --limit 10
uv run pipeline-analysis/provider_failure_report.py --days 7 --limit 10
uv run pipeline-analysis/provider_failure_recent.py --hours 24 --limit 30 --tool content-discovery-agent
```

## Database Paths

**Default paths:**

| Variable | Default |
|----------|---------|
| `LOCAL_FIRST_TRACKING_DB` | `~/sync/local-first/processing_log.duckdb` |
| `LOCAL_FIRST_ERROR_LOG_DB` | `~/sync/logging/error_log.duckdb` |

Override with environment variables or `--db-path` flag.

## Script Reference

### `usage_stats.py`

Reads from `processing_log.duckdb`. Shows LLM call counts per tool for today, this week, and all time. Helps answer: "which tools do I actually use?"

```bash
uv run pipeline-analysis/usage_stats.py
uv run pipeline-analysis/usage_stats.py --db-path ~/custom/path.duckdb
```

### `operational_log_report.py`

Reads from `error_log.duckdb`. Three sections: top warning-producing tools, recurring exception types, most common failing modules. Helps answer: "what's breaking and how often?"

```bash
uv run pipeline-analysis/operational_log_report.py
uv run pipeline-analysis/operational_log_report.py --days 7 --limit 5 --verbose
```

### `provider_failure_report.py`

Reads from `error_log.duckdb`. Aggregates provider-layer failures by tool, run context, and model. Helps answer: "which provider/model combinations are failing?"

```bash
uv run pipeline-analysis/provider_failure_report.py --days 14
```

### `provider_failure_recent.py`

Reads from `error_log.duckdb`. Event feed of recent provider failures with optional tool and context filters. Helps answer: "what just failed and why?"

```bash
uv run pipeline-analysis/provider_failure_recent.py --hours 24
uv run pipeline-analysis/provider_failure_recent.py --tool content-discovery-agent --context provider_score
```

## Design Notes

Scripts are standalone using PEP 723 inline script dependencies (`# /// script`). This means they can be run with `uv run` without a project-level venv -- useful for running reports from the workspace root without activating a tool-specific environment.

Each script reads from exactly one database and queries exactly one table family. This is intentional: operational reports and usage stats are kept separate because they answer different questions and live in different storage backends.

See `_NOTES.md` for the full decision log.
