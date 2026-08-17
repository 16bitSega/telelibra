from utils import (
    clean_promo_noise,
    clean_transcript_text,
    extract_urls,
    measure_performance,
    sanitize_filename,
)


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


def test_clean_transcript_text():
    raw = "[snorts] [music] >> Hello world! This is a a test. [applause] >> We discuss AI."
    cleaned = clean_transcript_text(raw)
    assert "[snorts]" not in cleaned
    assert "[music]" not in cleaned
    assert "[applause]" not in cleaned
    assert ">>" not in cleaned
    assert "a a" not in cleaned
    assert "Hello world! This is a test. We discuss AI." in cleaned


def test_clean_promo_noise():
    raw = "Here is the architectural review. З питань реклами: @promo_bot. Don't forget to like and subscribe! Final conclusions."
    cleaned = clean_promo_noise(raw)
    assert "@promo_bot" not in cleaned
    assert "like and subscribe" not in cleaned
    assert "Here is the architectural review." in cleaned
    assert "Final conclusions." in cleaned
