# pipeline-analysis — Dev Notes

Running log of decisions and reporting behavior for workspace analytics scripts.
This file captures why reporting tools changed, not just what changed.

---

## How to run

```bash
# LLM usage summary (processing_log)
uv run pipeline-analysis/usage_stats.py

# Operational warning/error summary (operational_log)
uv run pipeline-analysis/operational_log_report.py --days 30 --limit 10
```

---

## Changes Log

### 2026-04-18 — Added operational warning/error reporting script

**Changed:** Added `pipeline-analysis/operational_log_report.py` with three sections:

- top warning-producing tools (last N days)
- recurring exception types
- most common failing modules (`ERROR` + `CRITICAL`)

The script accepts `--db-path`, `--days`, `--limit`, and `--verbose` and defaults to `LOCAL_FIRST_TRACKING_DB` or `~/sync/local-first/processing_log.duckdb`.

**Because:** The remediation plan called for a lightweight operational analysis script after central warning/error persistence was added.

**Learned:** Putting this as a standalone script keeps query evolution fast without coupling reporting to runtime tool code.

### 2026-04-18 — Wired into remediation smoke workflow

**Changed:** Added a workspace Makefile target (`make ops-report`) and kept Phase 3 smoke CI focused on deterministic test commands while operational reporting remains a manual/analysis step.

**Because:** The report depends on runtime log data availability, so it is useful in developer workflows but not as a strict CI gate.

**Learned:** Separating deterministic smoke checks from data-dependent analytics avoids flaky CI while preserving observability tooling.

**Update:** Phase 3 CI now includes a dedicated script-entrypoint import gate in addition to smoke tests, while operational reporting remains manual/data-driven.

---

## Known Issues / Next Steps

- Add a JSON output mode if dashboard ingestion becomes a requirement.
- Add a simple trend section (7-day vs 30-day change) when enough history accumulates.
