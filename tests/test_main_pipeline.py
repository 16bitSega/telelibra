"""
Integration tests for the Librarian AI main pipeline with Visual support.
"""

from datetime import datetime, timezone
from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch
import pytest

from ai_engine import TriageResult
from main import LibrarianPipeline
from scraper import ScrapedContent, VisualTile


@pytest.fixture
def mock_pipeline_env():
    with tempfile.TemporaryDirectory() as tmp_dir:
        vault_path = Path(tmp_dir) / "vault"
        db_path = Path(tmp_dir) / "test_db.db"

        with patch("config.settings.obsidian_vault_path", vault_path), \
             patch("config.settings.db_path", db_path), \
             patch("config.settings.attachments_path", vault_path / "attachments"):
            pipeline = LibrarianPipeline()
            yield pipeline, vault_path, db_path


def test_pipeline_process_url_with_visuals(mock_pipeline_env):
    pipeline, vault_path, db_path = mock_pipeline_env
    url = "https://x.com/expert/status/123"

    tile = VisualTile(path=vault_path / "attachments" / "test_tile_00.jpg", index=0, width=1280, height=800)

    # Mock scraper output with visual tile
    mock_scraped = ScrapedContent(
        url=url,
        title="Agent Blueprint",
        text="Diagram of agent architecture",
        source_type="x",
        visual_tiles=[tile],
    )

    # Mock AI triage output
    mock_triage = TriageResult(
        url=url,
        title="Agent Blueprint",
        category="agents",
        item_type="knowledge",
        summary="Detailed architecture extracted from screenshot.",
        insights=["Autonomous loop", "Dynamic tool execution"],
        tags=["agents", "ai"],
        original_text=mock_scraped.text,
        visual_tiles=[tile],
        date_str="2025-09-10",
    )

    with patch.object(pipeline.scraper, "scrape", return_value=mock_scraped), \
         patch.object(pipeline.ai, "process_content", return_value=mock_triage):

        result = pipeline.process_url(
            url=url,
            message_id=101,
            message_date=datetime(2025, 9, 10, tzinfo=timezone.utc),
            dry_run=False,
            force_visual=True,
        )

        assert result["url"] == url
        assert result["category"] == "agents"
        assert len(result["visual_tiles"]) == 1

        target_file = Path(result["target_path"])
        assert target_file.exists()

        content = target_file.read_text(encoding="utf-8")
        assert "## Visual Snapshots" in content
        assert "![Visual Snapshot 1](../attachments/test_tile_00.jpg)" in content
