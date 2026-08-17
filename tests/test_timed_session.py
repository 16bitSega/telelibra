"""
Unit tests for run_timed_session.py and checkpointing / resuming logic.
"""

from pathlib import Path
import tempfile
from unittest.mock import patch
import pytest

from database import DatabaseManager
from run_timed_session import TimedSessionRunner


@pytest.fixture
def temp_runner_env():
    with tempfile.TemporaryDirectory() as tmp_dir:
        vault_path = Path(tmp_dir) / "vault"
        db_path = Path(tmp_dir) / "test_session.db"
        isolated_db = DatabaseManager(db_path=db_path)

        with patch("config.settings.obsidian_vault_path", vault_path), \
             patch("config.settings.db_path", db_path), \
             patch("config.settings.attachments_path", vault_path / "attachments"):
            runner = TimedSessionRunner(duration_minutes=0.01)  # 0.6 seconds
            runner.db = isolated_db
            yield runner, vault_path, isolated_db


def test_checkpointing_state(temp_runner_env):
    runner, vault_path, db = temp_runner_env

    # Store checkpoint
    db.set_checkpoint("last_processed_message_id", "45678")
    db.set_checkpoint("last_processed_url", "https://github.com/microsoft/autogen")

    assert db.get_checkpoint("last_processed_message_id") == "45678"
    assert db.get_checkpoint("last_processed_url") == "https://github.com/microsoft/autogen"


def test_skipping_already_processed_urls(temp_runner_env):
    runner, vault_path, db = temp_runner_env
    url = "https://example.com/existing_article"

    # Pre-create note in vault
    note_path = vault_path / "research" / "existing_article.md"
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text("# Existing note", encoding="utf-8")

    db.upsert_record(url=url, file_path=note_path, category="research", title="Existing Article")

    # When runner is called with reprocess=False, it should skip
    res = runner.process_single_url(url=url)
    assert res is None
    assert runner.skipped_count == 1
    assert runner.processed_count == 0


def test_database_stats_summary(temp_runner_env):
    runner, vault_path, db = temp_runner_env

    p1 = vault_path / "agents" / "note1.md"
    p2 = vault_path / "jobs" / "note2.md"

    db.upsert_record(url="https://example.com/1", file_path=p1, category="agents", item_type="knowledge")
    db.upsert_record(url="https://example.com/2", file_path=p2, category="jobs", item_type="job")

    stats = db.get_summary_stats()
    assert stats["total_processed"] == 2
    assert stats["jobs_count"] == 1
    assert stats["categories"]["agents"] == 1
    assert stats["categories"]["jobs"] == 1
