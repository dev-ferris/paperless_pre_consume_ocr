import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import psycopg
import pytest

from paperless_pre_consume_ocr.environment import (
    DatabaseConfig,
    fetch_ocr_config,
    load_database_config,
    load_environment,
)
from paperless_pre_consume_ocr.exceptions import DatabaseError


def _mock_connect(mock_psycopg, fetchone_result):
    """Wire up a psycopg.connect mock that returns ``fetchone_result``."""
    mock_psycopg.Error = psycopg.Error
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = fetchone_result
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = mock_cursor
    mock_psycopg.connect.return_value = mock_conn


class TestLoadDatabaseConfig:
    """Tests for load_database_config."""

    def test_missing_dbhost_raises(self):
        """Missing PAPERLESS_DBHOST should raise ValueError."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="PAPERLESS_DBHOST"):
                load_database_config()

    def test_reads_all_env_vars(self):
        """Should pick up every PAPERLESS_DB* variable."""
        env = {
            "PAPERLESS_DBHOST": "localhost",
            "PAPERLESS_DBPORT": "5433",
            "PAPERLESS_DBNAME": "testdb",
            "PAPERLESS_DBUSER": "testuser",
            "PAPERLESS_DBPW": "testpw",
        }
        with patch.dict(os.environ, env, clear=True):
            db = load_database_config()
            assert db.host == "localhost"
            assert db.port == "5433"
            assert db.name == "testdb"
            assert db.user == "testuser"
            assert db.password == "testpw"

    def test_defaults_applied(self):
        """Optional env vars should fall back to Paperless's conventional defaults."""
        with patch.dict(os.environ, {"PAPERLESS_DBHOST": "db.local"}, clear=True):
            db = load_database_config()
            assert db.port == "5432"
            assert db.name == "paperless"
            assert db.user == "paperless"
            assert db.password == "paperless"


class TestFetchOcrConfig:
    """Tests for fetch_ocr_config."""

    def _db(self) -> DatabaseConfig:
        return DatabaseConfig(host="localhost")

    def test_connection_string_has_space_between_dbname_and_user(self):
        """Regression test: connection string must have space between dbname and user."""
        with patch("paperless_pre_consume_ocr.environment.psycopg") as mock_psycopg:
            _mock_connect(mock_psycopg, fetchone_result=None)

            fetch_ocr_config(self._db())

            conn_str = mock_psycopg.connect.call_args[0][0]
            assert "dbname=paperless user=paperless" in conn_str

    def test_raises_database_error_on_failure(self):
        """A failing DB connection should raise DatabaseError, not silently fall back."""
        with patch("paperless_pre_consume_ocr.environment.psycopg") as mock_psycopg:
            mock_psycopg.Error = psycopg.Error
            mock_psycopg.connect.side_effect = psycopg.Error("Connection refused")
            with pytest.raises(DatabaseError, match="Failed to read OCR configuration"):
                fetch_ocr_config(self._db())

    def test_returns_defaults_when_no_row(self):
        """Should return defaults when the configuration row is missing."""
        with patch("paperless_pre_consume_ocr.environment.psycopg") as mock_psycopg:
            _mock_connect(mock_psycopg, fetchone_result=None)

            result = fetch_ocr_config(self._db())
            assert result["language"] == "deu+eng"
            assert result["mode"] == "skip"
            assert result["image_dpi"] == 300

    def test_merges_db_values_with_defaults(self):
        """DB values should override defaults; NULL DB values should not blank them."""
        with patch("paperless_pre_consume_ocr.environment.psycopg") as mock_psycopg:
            _mock_connect(
                mock_psycopg,
                fetchone_result={
                    "mode": "force",
                    "image_dpi": None,
                    "language": "fra",
                },
            )

            result = fetch_ocr_config(self._db())
            assert result["mode"] == "force"  # overridden
            assert result["language"] == "fra"  # overridden
            assert result["image_dpi"] == 300  # NULL ignored, default preserved
            assert result["deskew"] is True  # default preserved

    def test_uses_connect_timeout(self):
        """Connection string must include connect_timeout to avoid hangs."""
        with patch("paperless_pre_consume_ocr.environment.psycopg") as mock_psycopg:
            _mock_connect(mock_psycopg, fetchone_result=None)

            fetch_ocr_config(self._db())
            conn_str = mock_psycopg.connect.call_args[0][0]
            assert "connect_timeout=5" in conn_str


class TestLoadEnvironment:
    """Tests for load_environment."""

    def test_missing_working_path_raises(self):
        """Missing DOCUMENT_WORKING_PATH should raise ValueError."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="DOCUMENT_WORKING_PATH"):
                load_environment()

    def test_nonexistent_working_path_raises(self, tmp_path):
        """Non-existent working path should raise FileNotFoundError."""
        env = {"DOCUMENT_WORKING_PATH": str(tmp_path / "nonexistent.pdf")}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(FileNotFoundError):
                load_environment()

    def test_valid_paths(self, tmp_path):
        """Should correctly resolve paths when valid."""
        working_file = tmp_path / "test.pdf"
        working_file.touch()

        env = {
            "DOCUMENT_WORKING_PATH": str(working_file),
            "DOCUMENT_SOURCE_PATH": str(tmp_path / "source.pdf"),
            "DOCUMENT_CONSUME_PATH": str(tmp_path / "consume"),
        }
        with patch.dict(os.environ, env, clear=True):
            result = load_environment()
            assert result.paths.working == working_file
            assert result.paths.source == tmp_path / "source.pdf"
            assert result.paths.consume == tmp_path / "consume"

    def test_source_path_none_when_unset(self, tmp_path):
        """source should be None when DOCUMENT_SOURCE_PATH is not set."""
        working_file = tmp_path / "test.pdf"
        working_file.touch()

        env = {"DOCUMENT_WORKING_PATH": str(working_file)}
        with patch.dict(os.environ, env, clear=True):
            result = load_environment()
            assert result.paths.source is None

    def test_consume_default_path(self, tmp_path):
        """consume should use default when DOCUMENT_CONSUME_PATH is not set."""
        working_file = tmp_path / "test.pdf"
        working_file.touch()

        env = {"DOCUMENT_WORKING_PATH": str(working_file)}
        with patch.dict(os.environ, env, clear=True):
            result = load_environment()
            assert result.paths.consume == Path("/usr/src/paperless/consume")

    def test_task_id_from_env(self, tmp_path):
        """Should read TASK_ID from environment."""
        working_file = tmp_path / "test.pdf"
        working_file.touch()

        env = {
            "DOCUMENT_WORKING_PATH": str(working_file),
            "TASK_ID": "test-123",
        }
        with patch.dict(os.environ, env, clear=True):
            result = load_environment()
            assert result.task_id == "test-123"

    def test_task_id_default(self, tmp_path):
        """Should default to 'paperless' when TASK_ID is not set."""
        working_file = tmp_path / "test.pdf"
        working_file.touch()

        env = {"DOCUMENT_WORKING_PATH": str(working_file)}
        with patch.dict(os.environ, env, clear=True):
            result = load_environment()
            assert result.task_id == "paperless"
