"""
Scraper Engine for Librarian AI with PixelRAG-inspired Visual Capture.
Handles multi-source extraction (Playwright with DOM clutter stripping, 1568px screenshot tiling,
GitHub raw README conversion, Trafilatura for web) and multimodal visual asset preservation.
"""

from io import BytesIO
import json
import logging
import math
from pathlib import Path
import re
from typing import Any, Dict, Generator, List, Optional, Tuple
from urllib.parse import urlparse

import httpx
from PIL import Image

try:
    from playwright.sync_api import Error as PlaywrightError, Page, sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    PlaywrightError = Exception  # type: ignore[misc, assignment]
    sync_playwright = None  # type: ignore[assignment]
    Page = Any  # type: ignore[misc, assignment]

try:
    import trafilatura
    TRAFILATURA_AVAILABLE = True
except ImportError:
    TRAFILATURA_AVAILABLE = False
    trafilatura = None  # type: ignore[assignment]

from config import settings
from utils import log_execution, measure_performance, retry, sanitize_filename

logger = logging.getLogger("librarian.scraper")


class VisualTile:
    """Represents a rendered screenshot tile for multimodal vision models."""

    def __init__(self, path: Path, index: int, width: int, height: int, **kwargs: Any) -> None:
        self.path: Path = Path(path).resolve()
        self.index: int = index
        self.width: int = width
        self.height: int = height

    def __str__(self) -> str:
        return f"VisualTile(idx={self.index}, file='{self.path.name}', dims={self.width}x{self.height})"

    def __repr__(self) -> str:
        return self.__str__()


class ScrapedContent:
    """Encapsulates scraped text, visual screenshot tiles, and integrity state."""

    def __init__(
        self,
        url: str,
        title: str,
        text: str,
        source_type: str = "web",
        **kwargs: Any,
    ) -> None:
        self.url: str = url
        self.title: str = title or "Untitled Document"
        self.text: str = text.strip()
        self.source_type: str = source_type
        self.failed_scrape: bool = kwargs.get("failed_scrape", False)
        self.failure_reason: Optional[str] = kwargs.get("failure_reason")
        self.code_snippets: List[str] = kwargs.get("code_snippets", [])
        self.visual_tiles: List[VisualTile] = kwargs.get("visual_tiles", [])

    @property
    def has_visuals(self) -> bool:
        """True if visual screenshot tiles were captured."""
        return len(self.visual_tiles) > 0

    def __len__(self) -> int:
        """Length of scraped text content."""
        return len(self.text)

    def __bool__(self) -> bool:
        """Truthy if scraping succeeded with valid text or visual tiles."""
        if self.has_visuals and not self.failed_scrape:
            return True
        return not self.failed_scrape and len(self.text) >= 200

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def __str__(self) -> str:
        status = "FAILED" if self.failed_scrape else "SUCCESS"
        visual_info = f", tiles={len(self.visual_tiles)}" if self.has_visuals else ""
        return (
            f"ScrapedContent(title='{self.title[:35]}', type='{self.source_type}', "
            f"status={status}, chars={len(self)}{visual_info})"
        )

    def __repr__(self) -> str:
        return self.__str__()


class ScraperEngine:
    """Multi-source scraping & PixelRAG visual tile renderer."""

    LOGIN_PATTERNS: List[re.Pattern] = [
        re.compile(r"\b(?:sign\s*in|log\s*in|login|log\s*on)\b", re.IGNORECASE),
        re.compile(r"\b(?:join\s+linkedin|sign\s+in\s+to\s+linkedin)\b", re.IGNORECASE),
        re.compile(r"\b(?:sign\s+in\s+to\s+x|log\s+in\s+to\s+twitter)\b", re.IGNORECASE),
        re.compile(r"\b(?:войти|авторизация|вход\s+в\s+аккаунт|введите\s+пароль)\b", re.IGNORECASE),
        re.compile(r"\b(?:access\s+denied|captcha|verify\s+you\s+are\s+human)\b", re.IGNORECASE),
    ]

    def __init__(self, cookies_path: Optional[Path] = None, **kwargs: Any) -> None:
        self.cookies_path: Path = Path(cookies_path or settings.cookies_path).resolve()
        self.timeout_ms: int = kwargs.get("timeout_ms", settings.scrape_timeout_ms)
        self.headless: bool = kwargs.get("headless", settings.playwright_headless)
        self.tile_height: int = kwargs.get("tile_height", settings.tile_height)
        self.attachments_path: Path = Path(kwargs.get("attachments_path", settings.attachments_path)).resolve()
        self.attachments_path.mkdir(parents=True, exist_ok=True)

    def _load_cookies(self) -> List[Dict[str, Any]]:
        """Load cookie list from cookies.json if file exists."""
        if not self.cookies_path.exists():
            return []
        try:
            with open(self.cookies_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict) and "cookies" in data:
                    return data["cookies"]
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load cookies from %s: %s", self.cookies_path, e)
        return []

    def strip_dom_clutter(self, page: Page) -> None:
        """
        PixelRAG pattern: Strip floating cookie banners, modals, fixed overlays
        and ensure background is painted cleanly before capturing screenshot tiles.
        """
        try:
            page.evaluate("""
                () => {
                    const noiseSelectors = [
                        '[class*="cookie"]', '[id*="cookie"]',
                        '[class*="consent"]', '[id*="consent"]',
                        '[class*="banner"]', '[id*="banner"]',
                        '[class*="modal-backdrop"]', '[class*="popup"]',
                        '[class*="signup-prompt"]', '[id*="layers"]'
                    ];
                    noiseSelectors.forEach(sel => {
                        try {
                            document.querySelectorAll(sel).forEach(el => {
                                if (el.offsetHeight < 300 || el.style.position === 'fixed') {
                                    el.remove();
                                }
                            });
                        } catch (e) {}
                    });

                    // Convert fixed & sticky navigation to absolute so they don't repeat on every tile
                    document.querySelectorAll('*').forEach(el => {
                        const style = window.getComputedStyle(el);
                        if (style.position === 'fixed' || style.position === 'sticky') {
                            el.style.position = 'absolute';
                        }
                    });
                }
            """)
        except Exception as e:
            logger.debug("DOM clutter stripping notice: %s", e)

    def iter_image_tiles(
        self,
        full_image_bytes: bytes,
        tile_height: int = 1568,
        **kwargs: Any,
    ) -> Generator[Tuple[int, bytes, int, int], None, None]:
        """
        Lazy generator splitting a full-page screenshot into model-optimized vertical tiles (1568px).
        Avoids downscaling and text unreadability in Vision LLMs.
        Yields (index, tile_bytes, width, height).
        """
        with Image.open(BytesIO(full_image_bytes)) as img:
            width, height = img.size
            if height <= tile_height:
                output = BytesIO()
                img.save(output, format="JPEG", quality=90)
                yield 0, output.getvalue(), width, height
                return

            num_tiles = math.ceil(height / tile_height)
            for i in range(num_tiles):
                top = i * tile_height
                bottom = min(top + tile_height, height)
                # Crop vertical slice
                tile = img.crop((0, top, width, bottom))
                output = BytesIO()
                tile.save(output, format="JPEG", quality=90)
                yield i, output.getvalue(), width, (bottom - top)

    def check_integrity(self, text: str, **kwargs: Any) -> Tuple[bool, Optional[str]]:
        """
        Verify scraped text meets length and anti-login wall integrity standards.
        Returns (is_failed, failure_reason).
        """
        clean_text = text.strip()
        first_chunk = clean_text[:1500]
        for pattern in self.LOGIN_PATTERNS:
            if pattern.search(first_chunk):
                return True, f"Detected login wall pattern matching '{pattern.pattern}'"

        if len(clean_text) < 200:
            return True, f"Text length too short ({len(clean_text)} chars < 200 chars)"

        return False, None

    @retry(max_retries=2, backoff=2.0, exceptions=(httpx.HTTPError, OSError))
    def scrape_github(self, url: str, **kwargs: Any) -> ScrapedContent:
        """
        Scrapes GitHub repo by fetching raw README.md.
        """
        parsed = urlparse(url)
        path_parts = [p for p in parsed.path.strip("/").split("/") if p]

        if len(path_parts) >= 2:
            owner, repo = path_parts[0], path_parts[1]
            raw_urls = [
                f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/README.md",
                f"https://raw.githubusercontent.com/{owner}/{repo}/main/README.md",
                f"https://raw.githubusercontent.com/{owner}/{repo}/master/README.md",
            ]
            with httpx.Client(timeout=15.0, follow_redirects=True) as client:
                for raw_url in raw_urls:
                    try:
                        resp = client.get(raw_url)
                        if resp.status_code == 200 and len(resp.text) > 50:
                            readme_text = resp.text
                            title = f"GitHub - {owner}/{repo}"
                            is_failed, reason = self.check_integrity(readme_text)
                            return ScrapedContent(
                                url=url,
                                title=title,
                                text=readme_text,
                                source_type="github",
                                failed_scrape=is_failed,
                                failure_reason=reason,
                            )
                    except httpx.HTTPError:
                        continue

        return self.scrape_trafilatura(url, **kwargs)

    @measure_performance
    def capture_screenshot_tiles(
        self,
        url: str,
        source_type: str = "web",
        force_visual: bool = False,
        **kwargs: Any,
    ) -> Tuple[str, str, List[VisualTile], bool, Optional[str]]:
        """
        PixelRAG visual capture pipeline:
        Renders URL with Playwright, strips clutter, captures full-page screenshot,
        and saves 1568px tiles to vault attachments.
        Returns (page_title, text_content, visual_tiles, is_failed, failure_reason).
        """
        if not PLAYWRIGHT_AVAILABLE or sync_playwright is None:
            logger.warning("Playwright not installed. Cannot perform visual screenshot capture.")
            return "Untitled Document", "", [], True, "Playwright not available"

        cookies = self._load_cookies()
        domain = "x.com" if "x.com" in url or "twitter.com" in url else "linkedin.com"

        text_content = ""
        page_title = f"{source_type.capitalize()} Document"
        visual_tiles: List[VisualTile] = []
        is_failed = False
        failure_reason = None

        slug = sanitize_filename(urlparse(url).path.replace("/", "_") or "page", max_length=30)
        timestamp = int(urlparse(url).netloc.__hash__() % 100000)

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=self.headless,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
                )
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1280, "height": 800},
                )

                if cookies:
                    relevant_cookies = [
                        c for c in cookies
                        if domain in c.get("domain", "") or "." + domain in c.get("domain", "")
                    ]
                    if relevant_cookies:
                        try:
                            context.add_cookies(relevant_cookies)
                        except Exception as e:
                            logger.warning("Cookie injection notice: %s", e)

                page = context.new_page()
                page.set_default_timeout(self.timeout_ms)

                page.goto(url, wait_until="domcontentloaded")
                # Wait for network idle and dynamic components
                try:
                    page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass

                # Scroll twice to load full threads/comments
                for _ in range(2):
                    page.evaluate("window.scrollBy(0, window.innerHeight * 1.2)")
                    page.wait_for_timeout(1000)

                # Strip DOM clutter and fixed overlays
                self.strip_dom_clutter(page)

                page_title = page.title() or page_title

                # Extract text if present
                if "x.com" in url or "twitter.com" in url:
                    elements = page.query_selector_all('[data-testid="tweetText"], article')
                    if elements:
                        texts = [el.inner_text().strip() for el in elements if el.inner_text().strip()]
                        text_content = "\n\n---\n\n".join(texts)
                elif "linkedin.com" in url:
                    elements = page.query_selector_all(
                        ".feed-shared-update-v2__description, .update-components-text, .jobs-description, article"
                    )
                    if elements:
                        texts = [el.inner_text().strip() for el in elements if el.inner_text().strip()]
                        text_content = "\n\n".join(texts)

                if not text_content:
                    text_content = page.inner_text("body")

                # Check if visual capture is needed (forced, or text is short / image-heavy post)
                is_short_or_visual = len(text_content.strip()) < 250 or force_visual

                if is_short_or_visual or settings.vision_enabled:
                    logger.info("Generating visual screenshot tiles for %s...", url)
                    screenshot_bytes = page.screenshot(full_page=True, type="jpeg", quality=90)
                    
                    # Generate 1568px high screenshot tiles
                    for idx, tile_bytes, w, h in self.iter_image_tiles(screenshot_bytes, tile_height=self.tile_height):
                        # Cap at maximum 5 tiles per page to prevent context explosion
                        if idx >= 5:
                            break
                        tile_filename = f"{slug}_{timestamp}_tile_{idx:02d}.jpg"
                        tile_filepath = self.attachments_path / tile_filename
                        with open(tile_filepath, "wb") as f:
                            f.write(tile_bytes)
                        visual_tiles.append(VisualTile(path=tile_filepath, index=idx, width=w, height=h))

                browser.close()

        except Exception as e:
            logger.error("Visual capture failed for %s: %s", url, e)
            is_failed = True
            failure_reason = f"Playwright error: {str(e)}"

        # If we captured visual tiles, short text does NOT count as a failed scrape!
        if not is_failed:
            if visual_tiles:
                # We have visual context for our vision LLM!
                is_failed = False
                failure_reason = None
            else:
                is_failed, failure_reason = self.check_integrity(text_content)

        return page_title, text_content, visual_tiles, is_failed, failure_reason

    @measure_performance
    def scrape_social_playwright(self, url: str, source_type: str = "x", **kwargs: Any) -> ScrapedContent:
        """Scrapes dynamic social platforms with visual tile support."""
        title, text, tiles, is_failed, reason = self.capture_screenshot_tiles(
            url=url, source_type=source_type, **kwargs
        )
        return ScrapedContent(
            url=url,
            title=title,
            text=text,
            source_type=source_type,
            failed_scrape=is_failed,
            failure_reason=reason,
            visual_tiles=tiles,
        )

    @retry(max_retries=2, backoff=2.0, exceptions=(httpx.HTTPError, OSError))
    def scrape_trafilatura(self, url: str, **kwargs: Any) -> ScrapedContent:
        """Clean extraction for technical articles via Trafilatura with visual fallback."""
        force_visual = kwargs.get("force_visual", False)
        title = "Article Note"
        try:
            if not force_visual:
                downloaded = trafilatura.fetch_url(url)
                if downloaded:
                    extracted = trafilatura.extract(
                        downloaded,
                        include_comments=True,
                        include_tables=True,
                        include_links=True,
                        output_format="txt",
                    )
                    meta = trafilatura.extract_metadata(downloaded)
                    if meta and meta.title:
                        title = meta.title

                    if extracted and len(extracted.strip()) >= 200:
                        is_failed, reason = self.check_integrity(extracted)
                        return ScrapedContent(
                            url=url,
                            title=title,
                            text=extracted,
                            source_type="web",
                            failed_scrape=is_failed,
                            failure_reason=reason,
                        )
        except Exception as e:
            logger.warning("Trafilatura notice for %s: %s. Switching to visual capture...", url, e)

        # Fallback to PixelRAG visual tile capture
        return self.scrape_social_playwright(url, source_type="web", **kwargs)

    @measure_performance
    def scrape(self, url: str, force_visual: bool = False, **kwargs: Any) -> ScrapedContent:
        """
        Main entrypoint: routes URL to appropriate scraper with visual tile support.
        """
        domain = urlparse(url).netloc.lower()

        if "x.com" in domain or "twitter.com" in domain:
            return self.scrape_social_playwright(url, source_type="x", force_visual=force_visual, **kwargs)
        elif "linkedin.com" in domain:
            return self.scrape_social_playwright(url, source_type="linkedin", force_visual=force_visual, **kwargs)
        elif "github.com" in domain and not force_visual:
            return self.scrape_github(url, **kwargs)
        else:
            return self.scrape_trafilatura(url, force_visual=force_visual, **kwargs)


scraper_engine = ScraperEngine()
