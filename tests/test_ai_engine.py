"""
Unit tests for ai_engine.py, Muse-Glimmer-30B triage routing, and NotebookLM Markdown generation.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from ai_engine import AILibrarian, TriageResult
from config import TAXONOMY_FOLDERS
from scraper import ScrapedContent, VisualTile


def test_triage_result_notebooklm_markdown_with_visuals():
    tile1 = VisualTile(path=Path("/vault/attachments/post_01_tile_00.jpg"), index=0, width=1280, height=1568)
    tile2 = VisualTile(path=Path("/vault/attachments/post_01_tile_01.jpg"), index=1, width=1280, height=900)

    triage = TriageResult(
        url="https://x.com/tech_expert/status/987654321",
        title="Next-Gen Architecture Flowchart",
        category="workflows",
        item_type="knowledge",
        summary="A detailed diagram illustrating event-driven ETL pipelines with real-time stream ingestion.",
        insights=[
            "Visual chart depicts multi-region Kafka clusters",
            "Obsidian vault acts as cold storage tier",
        ],
        tags=["workflows", "architecture", "etl"],
        code_snippets=["docker run -d kafka:latest"],
        original_text="Check out this architecture diagram:",
        visual_tiles=[tile1, tile2],
        date_str="2025-09-20",
    )

    md = triage.to_notebooklm_markdown()

    # Frontmatter verification
    assert md.startswith("---\n")
    assert "url: https://x.com/tech_expert/status/987654321" in md
    assert "date: 2025-09-20" in md
    assert "category: workflows" in md
    assert "type: knowledge" in md

    # Summary & Insights verification
    assert "## AI Summary" in md
    assert "event-driven ETL pipelines" in md
    assert "## Key Insights" in md
    assert "- Visual chart depicts multi-region Kafka clusters" in md

    # Embedded Visual Snapshots verification
    assert "## Visual Snapshots" in md
    assert "![Visual Snapshot 1](../attachments/post_01_tile_00.jpg)" in md
    assert "![Visual Snapshot 2](../attachments/post_01_tile_01.jpg)" in md


def test_failed_scrape_guardrail():
    librarian = AILibrarian()
    failed_doc = ScrapedContent(
        url="https://example.com/blocked",
        title="Sign In",
        text="Sign in to continue.",
        source_type="web",
        failed_scrape=True,
        failure_reason="Detected login wall",
    )

    result = librarian.process_content(failed_doc)

    assert result.category == "other"
    assert "failed_scrape" in result.tags
    assert "login wall" in result.summary.lower()


@patch.object(AILibrarian, "_call_llamacpp")
def test_ai_triage_with_muse_glimmer_30b(mock_llamacpp):
    mock_llamacpp.return_value = '{"title": "Distributed Multi-Agent Architecture", "category": "agents", "type": "knowledge", "summary": "Muse-Glimmer-30B analyzed the visual diagram demonstrating multi-agent routing with checkpointing.", "insights": ["Visual flowchart reveals hierarchical orchestrator", "Worker pool scales dynamically"], "tags": ["agents", "muse_glimmer", "visual_rag"], "code_snippets": []}'

    tile = VisualTile(path=Path("/tmp/tile_00.jpg"), index=0, width=1280, height=800)
    librarian = AILibrarian(
        llm_provider="llamacpp",
        llamacpp_model_name="Muse-Glimmer-30B",
        reasoning_effort="high",
    )

    doc = ScrapedContent(
        url="https://x.com/ai_research/status/999888777",
        title="Multi-Agent System",
        text="Architecture blueprint:",
        source_type="x",
        visual_tiles=[tile],
    )

    result = librarian.process_content(doc)
    assert result.category == "agents"
    assert "Distributed Multi-Agent Architecture" in result.title
    assert len(result.visual_tiles) == 1
    mock_llamacpp.assert_called_once()


@patch.object(AILibrarian, "_call_ollama_vision")
def test_ai_triage_with_ollama_vision(mock_vision):
    mock_vision.return_value = '{"title": "Autonomous Agent Blueprint", "category": "agents", "type": "knowledge", "summary": "Visual diagram shows an agent loop with tool-use reflection.", "insights": ["Visual flowchart shows critique loop", "State manager handles checkpointing"], "tags": ["agents", "visual_rag", "autonomy"], "code_snippets": []}'

    tile = VisualTile(path=Path("/tmp/tile_00.jpg"), index=0, width=1280, height=800)
    librarian = AILibrarian(
        llm_provider="ollama",
        vision_enabled=True,
        vision_provider="ollama",
        vision_model="llama3.2-vision",
    )

    doc = ScrapedContent(
        url="https://x.com/ai_research/status/111222333",
        title="Agent Blueprint",
        text="Infographic on autonomous loops:",
        source_type="x",
        visual_tiles=[tile],
    )

    result = librarian.process_content(doc)
    assert result.category == "agents"
    assert "Autonomous Agent Blueprint" in result.title
    assert len(result.visual_tiles) == 1
