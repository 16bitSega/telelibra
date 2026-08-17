"""
Unit tests for specialized YouTube and ArXiv extractors in scraper.py.
"""

from unittest.mock import MagicMock, patch
import pytest

from scraper import ScrapedContent, ScraperEngine


def test_youtube_scraper_with_transcript():
    engine = ScraperEngine()
    url = "https://youtu.be/bkFnPiMHzcE?si=test123"

    mock_transcript = MagicMock()
    mock_snippet_1 = MagicMock(text="Welcome to this podcast on AI assistants.")
    mock_snippet_2 = MagicMock(text="We explore autonomous research frameworks and LLM orchestration.")
    mock_transcript.snippets = [mock_snippet_1, mock_snippet_2]

    with patch("httpx.Client.get") as mock_oembed, \
         patch("youtube_transcript_api.YouTubeTranscriptApi.fetch", return_value=mock_transcript):

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "title": "Empowering AI Assistants for Advanced Scientific Research",
            "author_name": "AI Research Podcast",
        }
        mock_oembed.return_value = mock_resp

        scraped = engine.scrape(url)

        assert scraped.source_type == "youtube"
        assert "Empowering AI Assistants" in scraped.title
        assert "AI Research Podcast" in scraped.text
        assert "autonomous research frameworks" in scraped.text
        assert scraped.failed_scrape is False


def test_arxiv_scraper():
    engine = ScraperEngine()
    url = "https://arxiv.org/abs/2405.12345"

    sample_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>Large Language Models for Scientific Discovery</title>
        <summary>We present a novel benchmark demonstrating autonomous hypothesis generation.</summary>
        <author><name>Dr. Jane Doe</name></author>
        <author><name>Dr. John Smith</name></author>
      </entry>
    </feed>
    """

    with patch("httpx.Client.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = sample_xml
        mock_get.return_value = mock_resp

        scraped = engine.scrape(url)

        assert scraped.source_type == "arxiv"
        assert "Large Language Models for Scientific Discovery" in scraped.title
        assert "Jane Doe" in scraped.text
        assert "hypothesis generation" in scraped.text
        assert scraped.failed_scrape is False
