"""Tests for pipeline-analysis scripts.

These scripts use inline PEP 723 dependencies and query DuckDB databases.
Tests validate the path resolution and DB query logic without requiring
production databases to exist.
"""

import sys
from pathlib import Path

import duckdb
import pytest

# Add parent directory to path so we can import script modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from operational_log_report import _normalize_db_path as ops_normalize
from operational_log_report import _resolve_db_path as ops_resolve_db_path
from provider_failure_report import resolve_db_path as failure_resolve_db_path
from provider_failure_report import top_contexts, top_tools
from usage_stats import _normalize_db_path as usage_normalize
from usage_stats import resolve_db_path as usage_resolve_db_path

# --- _normalize_db_path tests (shared logic across scripts) ---


class TestNormalizeDbPath:
    def test_directory_gets_filename_appended(self, tmp_path):
        result = usage_normalize(tmp_path, "processing_log.duckdb")
        assert result == tmp_path / "processing_log.duckdb"

    def test_duckdb_extension_returned_as_is(self, tmp_path):
        p = tmp_path / "custom.duckdb"
        result = usage_normalize(p, "processing_log.duckdb")
        assert result == p

    def test_no_extension_gets_filename_appended(self, tmp_path):
        p = tmp_path / "mydir"
        result = usage_normalize(p, "processing_log.duckdb")
        assert result == p / "processing_log.duckdb"

    def test_ops_normalize_same_behavior(self, tmp_path):
        result = ops_normalize(tmp_path, "error_log.duckdb")
        assert result == tmp_path / "error_log.duckdb"


# --- resolve_db_path tests ---


class TestResolveDbPath:
    def test_usage_env_var_used_when_set(self, tmp_path, monkeypatch):
        db = tmp_path / "custom.duckdb"
        db.touch()
        monkeypatch.setenv("LOCAL_FIRST_TRACKING_DB", str(db))
        result = usage_resolve_db_path()
        assert result == db

    def test_ops_env_var_used_when_set(self, tmp_path, monkeypatch):
        db = tmp_path / "error.duckdb"
        monkeypatch.setenv("LOCAL_FIRST_ERROR_LOG_DB", str(db))
        result = ops_resolve_db_path(None)
        assert result == db

    def test_ops_cli_value_takes_priority(self, tmp_path, monkeypatch):
        env_db = tmp_path / "env.duckdb"
        cli_db = tmp_path / "cli.duckdb"
        monkeypatch.setenv("LOCAL_FIRST_ERROR_LOG_DB", str(env_db))
        result = ops_resolve_db_path(str(cli_db))
        assert result == cli_db

    def test_failure_report_uses_error_log_default(self, monkeypatch):
        monkeypatch.delenv("LOCAL_FIRST_ERROR_LOG_DB", raising=False)
        result = failure_resolve_db_path(None)
        assert "error_log" in result.name


# --- Query function tests against a real in-memory DuckDB ---


@pytest.fixture
def operational_db(tmp_path):
    """Create a minimal operational_log table with test data."""
    db_path = tmp_path / "error_log.duckdb"
    con = duckdb.connect(str(db_path))
    con.execute("""
        CREATE TABLE operational_log (
            id INTEGER,
            tool_name VARCHAR,
            run_context VARCHAR,
            level VARCHAR,
            message VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    con.execute("""
        INSERT INTO operational_log (id, tool_name, run_context, level, message) VALUES
        (1, 'content-discovery-agent', 'provider_score', 'ERROR', 'Connection refused'),
        (2, 'content-discovery-agent', 'provider_score', 'ERROR', 'Timeout'),
        (3, 'promo-generator', 'provider_generate', 'ERROR', 'Model not found'),
        (4, 'content-discovery-agent', 'provider_review', 'WARNING', 'Slow response')
    """)
    con.close()
    return db_path


class TestQueryFunctions:
    def test_top_tools_returns_sorted_by_failures(self, operational_db):
        con = duckdb.connect(str(operational_db))
        results = top_tools(con, days=365, limit=10)
        con.close()
        assert len(results) >= 1
        tool_names = [r[0] for r in results]
        assert "content-discovery-agent" in tool_names
        # content-discovery-agent has 2 provider_ errors, should rank first
        assert results[0][0] == "content-discovery-agent"

    def test_top_tools_respects_limit(self, operational_db):
        con = duckdb.connect(str(operational_db))
        results = top_tools(con, days=365, limit=1)
        con.close()
        assert len(results) == 1

    def test_top_contexts_returns_results(self, operational_db):
        con = duckdb.connect(str(operational_db))
        results = top_contexts(con, days=365, limit=10)
        con.close()
        assert len(results) >= 1
        contexts = [r[0] for r in results]
        assert "provider_score" in contexts

    def test_empty_db_returns_empty_results(self, tmp_path):
        db_path = tmp_path / "empty.duckdb"
        con = duckdb.connect(str(db_path))
        con.execute("""
            CREATE TABLE operational_log (
                id INTEGER, tool_name VARCHAR, run_context VARCHAR,
                level VARCHAR, message VARCHAR, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        results = top_tools(con, days=7, limit=10)
        con.close()
        assert results == []
