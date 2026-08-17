"""
Infrastructure utilities for Librarian AI.
Provides decorators for timing, logging, and retries, as well as context managers.
"""

import functools
import logging
import re
import sys
import time
from contextlib import contextmanager
from typing import Any, Callable, Generator, Optional, TypeVar

# Setup root logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger("librarian.utils")

F = TypeVar("F", bound=Callable[..., Any])


def measure_performance(func: F) -> F:
    """Decorator to measure execution time of functions."""
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        start_time = time.perf_counter()
        func_name = getattr(func, "__qualname__", func.__name__)
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            elapsed = time.perf_counter() - start_time
            logger.info("Function '%s' executed in %.4f seconds", func_name, elapsed)

    return wrapper  # type: ignore[return-value]


def retry(max_retries: int = 3, backoff: float = 2.0, exceptions: tuple = (Exception,)) -> Callable[[F], F]:
    """Decorator to retry flaky operations (network, I/O, API calls) with exponential backoff."""
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            attempts = 0
            current_delay = 1.0
            func_name = getattr(func, "__qualname__", func.__name__)
            while attempts < max_retries:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    attempts += 1
                    if attempts >= max_retries:
                        logger.error("Function '%s' failed after %d attempts: %s", func_name, attempts, e)
                        raise
                    logger.warning(
                        "Function '%s' attempt %d/%d failed with error (%s). Retrying in %.2fs...",
                        func_name, attempts, max_retries, e, current_delay
                    )
                    time.sleep(current_delay)
                    current_delay *= backoff
            return None
        return wrapper  # type: ignore[return-value]
    return decorator


def log_execution(level: int = logging.INFO) -> Callable[[F], F]:
    """Decorator to log function entry, exit, and parameters."""
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            func_name = getattr(func, "__qualname__", func.__name__)
            logger.log(level, "Starting execution of '%s'", func_name)
            try:
                result = func(*args, **kwargs)
                logger.log(level, "Successfully completed '%s'", func_name)
                return result
            except Exception as e:
                logger.error("Error during execution of '%s': %s", func_name, e)
                raise
        return wrapper  # type: ignore[return-value]
    return decorator


def sanitize_filename(title: str, max_length: int = 80, **kwargs: Any) -> str:
    """Sanitize a string for use as a cross-platform safe markdown filename."""
    # Replace illegal characters
    cleaned = re.sub(r'[\\/*?:"<>|#\[\]^~`]', "", title)
    # Normalize whitespaces and dashes
    cleaned = re.sub(r"[\s_]+", " ", cleaned).strip()
    if not cleaned:
        cleaned = "untitled_note"
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rsplit(" ", 1)[0]
    return cleaned


def extract_urls(text: Optional[str], **kwargs: Any) -> Generator[str, None, None]:
    """Lazy generator yielding unique URLs extracted from message text."""
    if not text:
        return
    url_pattern = re.compile(
        r"https?://(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(?::\d+)?(?:/[^\s<>'\"`()]*)*",
        re.IGNORECASE,
    )
    seen = set()
    for match in url_pattern.finditer(text):
        url = match.group(0).rstrip(".,!?:;)")
        if url not in seen:
            seen.add(url)
            yield url


def clean_transcript_text(text: str, **kwargs: Any) -> str:
    """
    Cleans spoken transcripts of speaker noise, stutters, and sound effects:
    - Strips [music], [applause], [snorts], [laughter], [coughing], >>, etc.
    - Removes consecutive stutter word repetitions.
    - Preserves all real speech in original language (Ukrainian, English, etc.).
    """
    if not text:
        return ""

    # 1. Remove bracketed acoustic/sound annotations
    sound_pattern = re.compile(
        r"\[(?:music|applause|laughter|snorts|cheering|coughing|throat clearing|screaming|sighs|inaudible|silence|whispering|groans|crying|gasping|chuckle)[^\]]*\]",
        re.IGNORECASE,
    )
    cleaned = sound_pattern.sub(" ", text)

    # 2. Remove speaker turn indicators (>> or > >)
    cleaned = re.sub(r">\s*>\s*", " ", cleaned)

    # 3. Clean duplicate stutter words (e.g. "and and and" -> "and", "the the" -> "the")
    cleaned = re.sub(r"\b([a-zA-Zа-яА-ЯіїєґІЇЄҐ]+)(?:\s+\1\b)+", r"\1", cleaned, flags=re.IGNORECASE)

    # 4. Normalize excessive whitespace
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n\s*\n+", "\n\n", cleaned)
    return cleaned.strip()


def clean_promo_noise(text: str, **kwargs: Any) -> str:
    """
    Strips social media boilerplate, advertising prompts, and sponsor clutter:
    - Removes 'like and subscribe', 'link in description', 'з питань реклами', etc.
    - Preserves all substantive content in the source language.
    """
    if not text:
        return ""

    promo_patterns = [
        re.compile(r"(?:з\s+питань\s+реклами|по\s+вопросам\s+рекламы|for\s+sponsorships?)\s*[:@-]?\s*\S+", re.IGNORECASE),
        re.compile(r"(?:підписуйтесь|подписывайтесь|subscribe\s+to|follow\s+us\s+on)\s+(?:на\s+)?(?:наш\s+)?(?:канал|telegram|телеграм|youtube|channel|twitter|x\.com)\S*", re.IGNORECASE),
        re.compile(r"(?:don't\s+forget\s+to\s+like|leave\s+a\s+like|hit\s+the\s+bell|ставьте\s+лайки?|тисніть\s+дзвіночок)[^.!?\n]*[.!?\n]?", re.IGNORECASE),
        re.compile(r"(?:link\s+in\s+(?:the\s+)?description|посилання\s+в\s+описі|ссылка\s+в\s+описании)[^.!?\n]*[.!?\n]?", re.IGNORECASE),
    ]

    cleaned = text
    for pat in promo_patterns:
        cleaned = pat.sub("", cleaned)

    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n\s*\n+", "\n\n", cleaned)
    return cleaned.strip()
