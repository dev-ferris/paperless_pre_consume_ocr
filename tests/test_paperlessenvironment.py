import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import psycopg
import pytest

from exceptions import DatabaseError
from paperlessenvironment import PaperlessConfig, PaperlessEnvironment, PaperlessPaths


class TestPaperlessConfig:
    """Tests for PaperlessConfig."""

    def test_init_missing_dbhost_raises(self):
        """Missing PAPERLESS_DBHOST should raise ValueError."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="PAPERLESS_DBHOST"):
                PaperlessConfig()

    def test_init_with_dbhost(self):
        """Config should initialize with PAPERLESS_DBHOST set."""
        env = {
            "PAPERLESS_DBHOST": "localhost",
            "PAPERLESS_DBPORT": "5433",
            "PAPERLESS_DBNAME": "testdb",
            "PAPERLESS_DBUSER": "testuser",
            "PAPERLESS_DBPW": "testpw",
        }
        with patch.dict(os.environ, env, clear=True):
            config = PaperlessConfig()
            assert config.host == "localhost"
            assert config.port == "5433"
            assert config.name == "testdb"
            assert config.user == "testuser"
            assert config.password == "testpw"

    def test_init_defaults(self):
        """Config should use defaults for optional values."""
        with patch.dict(os.environ, {"PAPERLESS_DBHOST": "db.local"}, clear=True):
            config = PaperlessConfig()
            assert config.port == "5432"
            assert config.name == "paperless"
            assert config.user == "paperless"
            assert config.password == "paperless"

    def test_connection_string_has_space_between_dbname_and_user(self):
        """Regression test: connection string must have space between dbname and user."""
        env = {
            "PAPERLESS_DBHOST": "localhost",
            "PAPERLESS_DBPORT": "5432",
            "PAPERLESS_DBNAME": "paperless",
            "PAPERLESS_DBUSER": "paperless",
            "PAPERLESS_DBPW": "secret",
        }
        with patch.dict(os.environ, env, clear=True):
            config = PaperlessConfig()

            # Mock psycopg.connect to capture the connection string
            with patch("paperlessenvironment.psycopg") as mock_psycopg:
                mock_conn = MagicMock()
                mock_cursor = MagicMock()
                mock_cursor.fetchone.return_value = None
                mock_conn.__enter__ = MagicMock(return_value=mock_conn)
                mock_conn.__exit__ = MagicMock(return_value=False)
                mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
                mock_cursor.__exit__ = MagicMock(return_value=False)
                mock_conn.cursor.return_value = mock_cursor
                mock_psycopg.connect.return_value = mock_conn

                config.get_ocr_config()

                call_args = mock_psycopg.connect.call_args
                conn_str = call_args[0][0]
                # Ensure "dbname=paperless user=paperless" has a space
                assert "dbname=paperless user=paperless" in conn_str

    def test_get_ocr_config_raises_database_error_on_failure(self):
        """A failing DB connection should raise DatabaseError, not silently fall back."""
        with patch.dict(os.environ, {"PAPERLESS_DBHOST": "nonexistent"}, clear=True):
            config = PaperlessConfig()

            with patch("paperlessenvironment.psycopg") as mock_psycopg:
                mock_psycopg.Error = psycopg.Error
                mock_psycopg.connect.side_effect = psycopg.Error("Connection refused")
                with pytest.raises(DatabaseError, match="Failed to read OCR configuration"):
                    config.get_ocr_config()

    def test_get_ocr_config_returns_defaults_when_no_row(self):
        """Should return defaults when the configuration row is missing."""
        env = {"PAPERLESS_DBHOST": "localhost"}
        with patch.dict(os.environ, env, clear=True):
            config = PaperlessConfig()

            with patch("paperlessenvironment.psycopg") as mock_psycopg:
                mock_psycopg.Error = psycopg.Error
                mock_conn = MagicMock()
                mock_cursor = MagicMock()
                mock_cursor.fetchone.return_value = None
                mock_conn.__enter__ = MagicMock(return_value=mock_conn)
                mock_conn.__exit__ = MagicMock(return_value=False)
                mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
                mock_cursor.__exit__ = MagicMock(return_value=False)
                mock_conn.cursor.return_value = mock_cursor
                mock_psycopg.connect.return_value = mock_conn

                result = config.get_ocr_config()
                assert result["language"] == "deu+eng"
                assert result["mode"] == "skip"
                assert result["image_dpi"] == 300

    def test_get_ocr_config_merges_db_values_with_defaults(self):
        """DB values should override defaults; NULL DB values should not blank them."""
        env = {"PAPERLESS_DBHOST": "localhost"}
        with patch.dict(os.environ, env, clear=True):
            config = PaperlessConfig()

            with patch("paperlessenvironment.psycopg") as mock_psycopg:
                mock_psycopg.Error = psycopg.Error
                mock_conn = MagicMock()
                mock_cursor = MagicMock()
                # Mode overridden, image_dpi NULL → default kept,
                # language overridden.
                mock_cursor.fetchone.return_value = {
                    "mode": "force",
                    "image_dpi": None,
                    "language": "fra",
                }
                mock_conn.__enter__ = MagicMock(return_value=mock_conn)
                mock_conn.__exit__ = MagicMock(return_value=False)
                mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
                mock_cursor.__exit__ = MagicMock(return_value=False)
                mock_conn.cursor.return_value = mock_cursor
                mock_psycopg.connect.return_value = mock_conn

                result = config.get_ocr_config()
                assert result["mode"] == "force"  # overridden
                assert result["language"] == "fra"  # overridden
                assert result["image_dpi"] == 300  # NULL ignored, default
                assert result["deskew"] is True  # default preserved

    def test_get_ocr_config_uses_connect_timeout(self):
        """Connection string must include connect_timeout to avoid hangs."""
        env = {"PAPERLESS_DBHOST": "localhost"}
        with patch.dict(os.environ, env, clear=True):
            config = PaperlessConfig()

            with patch("paperlessenvironment.psycopg") as mock_psycopg:
                mock_psycopg.Error = psycopg.Error
                mock_conn = MagicMock()
                mock_cursor = MagicMock()
                mock_cursor.fetchone.return_value = None
                mock_conn.__enter__ = MagicMock(return_value=mock_conn)
                mock_conn.__exit__ = MagicMock(return_value=False)
                mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
                mock_cursor.__exit__ = MagicMock(return_value=False)
                mock_conn.cursor.return_value = mock_cursor
                mock_psycopg.connect.return_value = mock_conn

                config.get_ocr_config()
                conn_str = mock_psycopg.connect.call_args[0][0]
                assert "connect_timeout=5" in conn_str


class TestPaperlessPaths:
    """Tests for PaperlessPaths."""

    def test_missing_working_path_raises(self):
        """Missing DOCUMENT_WORKING_PATH should raise ValueError."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="DOCUMENT_WORKING_PATH"):
                PaperlessPaths()

    def test_nonexistent_working_path_raises(self, tmp_path):
        """Non-existent working path should raise FileNotFoundError."""
        env = {"DOCUMENT_WORKING_PATH": str(tmp_path / "nonexistent.pdf")}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(FileNotFoundError):
                PaperlessPaths()

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
            paths = PaperlessPaths()
            assert paths.working == working_file
            assert paths.source == tmp_path / "source.pdf"
            assert paths.consume == tmp_path / "consume"

    def test_source_path_none_when_unset(self, tmp_path):
        """source should be None when DOCUMENT_SOURCE_PATH is not set."""
        working_file = tmp_path / "test.pdf"
        working_file.touch()

        env = {"DOCUMENT_WORKING_PATH": str(working_file)}
        with patch.dict(os.environ, env, clear=True):
            paths = PaperlessPaths()
            assert paths.source is None

    def test_consume_default_path(self, tmp_path):
        """consume should use default when DOCUMENT_CONSUME_PATH is not set."""
        working_file = tmp_path / "test.pdf"
        working_file.touch()

        env = {"DOCUMENT_WORKING_PATH": str(working_file)}
        with patch.dict(os.environ, env, clear=True):
            paths = PaperlessPaths()
            assert paths.consume == Path("/usr/src/paperless/consume")


class TestPaperlessEnvironment:
    """Tests for PaperlessEnvironment."""

    def test_task_id_from_env(self):
        """Should read TASK_ID from environment."""
        with patch.dict(os.environ, {"TASK_ID": "test-123"}, clear=True):
            env = PaperlessEnvironment()
            assert env.task_id == "test-123"

    def test_task_id_default(self):
        """Should default to 'paperless' when TASK_ID is not set."""
        with patch.dict(os.environ, {}, clear=True):
            env = PaperlessEnvironment()
            assert env.task_id == "paperless"

    def test_paths_cached(self, tmp_path):
        """paths property should return the same instance on repeated access."""
        working_file = tmp_path / "test.pdf"
        working_file.touch()

        env_vars = {"DOCUMENT_WORKING_PATH": str(working_file)}
        with patch.dict(os.environ, env_vars, clear=True):
            env = PaperlessEnvironment()
            paths1 = env.paths
            paths2 = env.paths
            assert paths1 is paths2
