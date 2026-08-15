"""
Unit tests for scraper.py, visual tile iteration, and integrity checks.
"""

from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch
from PIL import Image
import pytest

from scraper import ScrapedContent, ScraperEngine, VisualTile


def test_scraped_content_with_visual_tiles():
    tile = VisualTile(path=Path("/tmp/tile_0.jpg"), index=0, width=1280, height=800)
    doc = ScrapedContent(
        url="https://x.com/post/1",
        title="Visual Diagram",
        text="Short caption",  # Even with short text, has_visuals makes it truthy
        source_type="x",
        visual_tiles=[tile],
    )
    assert doc.has_visuals is True
    assert bool(doc) is True
    assert "tiles=1" in str(doc)


def test_image_tile_generator():
    engine = ScraperEngine()
    # Create a tall dummy test image (1280 x 3500 px)
    img = Image.new("RGB", (1280, 3500), color=(73, 109, 137))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    img_bytes = buf.getvalue()

    # Slice with tile_height = 1568
    tiles = list(engine.iter_image_tiles(img_bytes, tile_height=1568))

    # 3500 / 1568 = 3 tiles (1568, 1568, 364)
    assert len(tiles) == 3
    assert tiles[0][0] == 0  # index
    assert tiles[0][2] == 1280  # width
    assert tiles[0][3] == 1568  # height
    assert tiles[2][3] == 364  # tail height


def test_integrity_check_login_wall():
    engine = ScraperEngine()
    login_text = "Please Sign In to LinkedIn to view this post. Create an account or log in with your email."
    is_failed, reason = engine.check_integrity(login_text)
    assert is_failed is True
    assert "login" in reason.lower()


@patch("httpx.Client.get")
def test_scrape_github_readme(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "# AutoGen\nA framework for multi-agent applications.\n" + ("Detailed documentation. " * 30)
    mock_get.return_value = mock_resp

    engine = ScraperEngine()
    result = engine.scrape_github("https://github.com/microsoft/autogen")

    assert result.source_type == "github"
    assert result.failed_scrape is False
    assert "AutoGen" in result.text
