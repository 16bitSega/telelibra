"""
Unit tests for utils.py functions and decorators.
"""

from utils import extract_urls, measure_performance, sanitize_filename


def test_sanitize_filename():
    assert sanitize_filename('My Title: A Guide / How-To? *Awesome*') == "My Title A Guide How-To Awesome"
    assert sanitize_filename("   ") == "untitled_note"
    long_title = "A " * 60
    sanitized = sanitize_filename(long_title, max_length=50)
    assert len(sanitized) <= 50


def test_extract_urls():
    text = (
        "Check this repo https://github.com/test/repo, and this post "
        "https://x.com/user/status/123456! Also duplicated https://github.com/test/repo."
    )
    urls = list(extract_urls(text))
    assert len(urls) == 2
    assert "https://github.com/test/repo" in urls
    assert "https://x.com/user/status/123456" in urls


def test_measure_performance_decorator():
    @measure_performance
    def sample_func(x: int) -> int:
        return x * 2

    assert sample_func(5) == 10
