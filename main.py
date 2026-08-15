"""
Main pipeline orchestrator for Librarian AI with Visual-Native Processing.
Scans Telegram Saved Messages (>= September 1, 2025), extracts URLs, executes scraping
with PixelRAG-inspired visual screenshot tiling, performs Multimodal AI triage, and saves notes to Obsidian Vault.
"""

import argparse
import asyncio
from datetime import datetime, timezone
import logging
from pathlib import Path
import sys
from typing import Any, AsyncGenerator, Dict, Generator, List, Optional

try:
    from telethon import TelegramClient
    from telethon.errors import RPCError
    from telethon.tl.custom.message import Message
    TELETHON_AVAILABLE = True
except ImportError:
    TELETHON_AVAILABLE = False
    TelegramClient = None  # type: ignore[misc, assignment]
    RPCError = Exception  # type: ignore[misc, assignment]
    Message = Any  # type: ignore[misc, assignment]

from ai_engine import ai_librarian
from calendar_util import calendar_manager
from config import settings
from database import db_manager
from scraper import scraper_engine
from utils import extract_urls, log_execution, measure_performance

logger = logging.getLogger("librarian.main")


class LibrarianPipeline:
    """Orchestrates end-to-end Personal Intelligence ETL pipeline with Visual RAG support."""

    def __init__(self, **kwargs: Any) -> None:
        self.settings = settings
        self.db = db_manager
        self.scraper = scraper_engine
        self.ai = ai_librarian
        self.calendar = calendar_manager

        # Ensure base directories, attachments, and 20 taxonomy folders exist
        self.settings.ensure_directories()

    async def iter_saved_messages(
        self,
        client: TelegramClient,
        since_date: Optional[datetime] = None,
        limit: Optional[int] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[Message, None]:
        """
        Lazy async generator streaming messages from Telegram 'Saved Messages'
        filtered for date >= September 1, 2025.
        """
        target_cutoff = since_date or self.settings.ingestion_start_date
        logger.info("Scanning Telegram 'Saved Messages' from cutoff: %s", target_cutoff.isoformat())

        count = 0
        async for message in client.iter_messages("me", limit=limit):
            msg_date = message.date
            if msg_date and msg_date < target_cutoff:
                logger.info("Reached message dated %s before cutoff date %s. Stopping stream.", msg_date, target_cutoff)
                break

            if message.text:
                count += 1
                yield message

        logger.info("Finished streaming %d messages from Telegram.", count)

    @measure_performance
    def process_url(
        self,
        url: str,
        message_id: Optional[int] = None,
        message_date: Optional[datetime] = None,
        dry_run: bool = False,
        force_visual: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Process an individual URL through the full ETL workflow:
        1. Scrape content (Playwright with visual tiles, GitHub raw README, Trafilatura)
        2. AI Librarian multimodal triage (Job vs 20 Knowledge folders + Vision reasoning)
        3. Smart Overwrite in Obsidian Vault with embedded visual snapshots
        4. Google Calendar event creation for Jobs
        5. SQLite tracking update
        """
        logger.info("Processing URL: %s (force_visual=%s)", url, force_visual)
        date_str = (message_date or datetime.now(timezone.utc)).strftime("%Y-%m-%d")

        # Step 1: Scrape Content (with PixelRAG screenshot tiling)
        scraped = self.scraper.scrape(url, force_visual=force_visual, **kwargs)

        # Step 2: Multimodal AI Triage & NotebookLM structuring
        triage = self.ai.process_content(scraped, date_str=date_str, **kwargs)
        notebooklm_md = triage.to_notebooklm_markdown()

        # Step 3: Smart Overwrite Path Resolution
        target_path, is_overwrite = self.db.resolve_target_filepath(
            url=url,
            category=triage.category,
            title=triage.title,
            vault_path=self.settings.obsidian_vault_path,
        )

        logger.info(
            "Target path: %s (Action: %s, Visuals: %d tiles)",
            target_path, "SMART OVERWRITE" if is_overwrite else "CREATE NEW",
            len(triage.visual_tiles)
        )

        if not dry_run:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(notebooklm_md)

            self.db.upsert_record(
                url=url,
                file_path=target_path,
                category=triage.category,
                title=triage.title,
                item_type=triage.item_type,
                telegram_message_id=message_id,
            )

        # Step 4: Job Branch Google Calendar scheduling
        calendar_result = None
        if triage.item_type == "job":
            logger.info("Job opportunity identified. Scheduling Google Calendar event...")
            if not dry_run:
                calendar_result = self.calendar.create_job_event(
                    title=triage.title,
                    url=url,
                    notes=triage.summary,
                )

        return {
            "url": url,
            "title": triage.title,
            "category": triage.category,
            "type": triage.item_type,
            "target_path": str(target_path),
            "is_overwrite": is_overwrite,
            "visual_tiles": [str(t.path) for t in triage.visual_tiles],
            "calendar_event": calendar_result,
        }

    async def run_batch(
        self,
        since_date: Optional[datetime] = None,
        limit: Optional[int] = None,
        dry_run: bool = False,
        force_visual: bool = False,
        **kwargs: Any,
    ) -> None:
        """Execute full batch scan from Telegram Saved Messages."""
        if not self.settings.telegram_api_id or not self.settings.telegram_api_hash:
            logger.error(
                "Telegram API credentials (TELEGRAM_API_ID, TELEGRAM_API_HASH) are not configured. "
                "Please configure .env before running batch scan."
            )
            return

        client = TelegramClient(
            self.settings.telegram_session_name,
            self.settings.telegram_api_id,
            self.settings.telegram_api_hash,
        )

        try:
            await client.start(phone=self.settings.telegram_phone)
            logger.info("Telethon client connected to Telegram successfully.")

            processed_count = 0
            async for message in self.iter_saved_messages(client, since_date=since_date, limit=limit):
                urls = list(extract_urls(message.text))
                for url in urls:
                    try:
                        self.process_url(
                            url=url,
                            message_id=message.id,
                            message_date=message.date,
                            dry_run=dry_run,
                            force_visual=force_visual,
                            **kwargs,
                        )
                        processed_count += 1
                    except Exception as e:
                        logger.error("Error processing URL %s: %s", url, e, exc_info=True)

            logger.info("Batch scan completed. Processed %d URLs.", processed_count)

        except RPCError as e:
            logger.error("Telegram RPC error: %s", e)
        finally:
            await client.disconnect()


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Librarian AI - Personal Intelligence ETL Pipeline with Visual Support")
    parser.add_argument("--url", type=str, help="Process a single URL directly (bypasses Telegram)")
    parser.add_argument("--visual", action="store_true", help="Force visual screenshot tile rendering (PixelRAG mode)")
    parser.add_argument("--dry-run", action="store_true", help="Run without writing files to vault or database")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of Telegram messages to scan")
    parser.add_argument(
        "--since",
        type=str,
        default="2025-09-01",
        help="Start date filter YYYY-MM-DD (default: 2025-09-01)",
    )
    return parser.parse_args()


def main() -> None:
    """CLI entrypoint."""
    args = parse_arguments()
    pipeline = LibrarianPipeline()

    if args.url:
        logger.info("Direct single URL mode: %s", args.url)
        res = pipeline.process_url(url=args.url, dry_run=args.dry_run, force_visual=args.visual)
        visual_str = f"\n  Visual Tiles: {len(res['visual_tiles'])} saved to attachments/" if res['visual_tiles'] else ""
        print(f"\nCompleted:\n  Title: {res['title']}\n  Category: {res['category']}\n  Path: {res['target_path']}{visual_str}")
        return

    since_dt = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    asyncio.run(pipeline.run_batch(
        since_date=since_dt,
        limit=args.limit,
        dry_run=args.dry_run,
        force_visual=args.visual,
    ))


if __name__ == "__main__":
    main()
