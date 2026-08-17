"""
Timed Session Runner with Automatic Checkpointing and Resuming for Librarian AI.
Runs for a specified duration (default: 15 minutes), processes Telegram Saved Messages,
saves progress in SQLite, and allows seamless resumption from where it was paused.
"""

import argparse
import asyncio
from datetime import datetime, timezone
import logging
from pathlib import Path
import signal
import sys
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

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

# Configure clean logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("librarian.session")


class TimedSessionRunner:
    """Manages timed ETL execution with checkpointing and state resumption."""

    def __init__(
        self,
        duration_minutes: float = 15.0,
        reprocess: bool = False,
        reprocess_failed: bool = False,
        force_visual: bool = False,
        **kwargs: Any,
    ) -> None:
        self.duration_seconds: float = duration_minutes * 60.0
        self.reprocess: bool = reprocess
        self.reprocess_failed: bool = reprocess_failed
        self.force_visual: bool = force_visual
        self.settings = settings
        self.db = db_manager
        self.scraper = scraper_engine
        self.ai = ai_librarian
        self.calendar = calendar_manager

        self.start_time: float = 0.0
        self.stop_requested: bool = False
        self.processed_count: int = 0
        self.skipped_count: int = 0
        self.failed_count: int = 0
        self.categories_processed: Dict[str, int] = {}

        self.settings.ensure_directories()

    def get_time_remaining(self) -> float:
        """Calculate remaining time in seconds."""
        if self.start_time == 0.0:
            return self.duration_seconds
        elapsed = time.time() - self.start_time
        return max(0.0, self.duration_seconds - elapsed)

    def is_time_up(self) -> bool:
        """Check if session duration limit has been reached."""
        return self.get_time_remaining() <= 0.0

    def format_time(self, seconds: float) -> str:
        """Format seconds into MM:SS string."""
        mins, secs = divmod(int(seconds), 60)
        return f"{mins:02d}m {secs:02d}s"

    def print_status_bar(self) -> None:
        """Print real-time session progress."""
        rem_str = self.format_time(self.get_time_remaining())
        sys.stdout.write(
            f"\r⏱️  [Time Remaining: {rem_str} | Processed: {self.processed_count} | Skipped: {self.skipped_count} | Errors: {self.failed_count}]\n"
        )
        sys.stdout.flush()

    async def iter_messages_with_resume(
        self,
        client: TelegramClient,
        since_date: Optional[datetime] = None,
        limit: Optional[int] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[Message, None]:
        """
        Stream messages from Telegram Saved Messages.
        Checks last checkpointed message ID and date cutoff >= September 1, 2025.
        """
        cutoff_date = since_date or self.settings.ingestion_start_date
        last_msg_id_str = self.db.get_checkpoint("last_processed_message_id")
        last_msg_id = int(last_msg_id_str) if last_msg_id_str else None

        if last_msg_id:
            logger.info("Resuming session from last checkpointed Telegram message ID: %s", last_msg_id)
        else:
            logger.info("Starting fresh stream from cutoff date: %s", cutoff_date.strftime("%Y-%m-%d"))

        async for message in client.iter_messages("me", limit=limit):
            if self.stop_requested or self.is_time_up():
                break

            msg_date = message.date
            if msg_date and msg_date < cutoff_date:
                logger.info("Reached message dated %s before cutoff %s. Stream complete.", msg_date, cutoff_date)
                break

            if message.text:
                yield message

    @measure_performance
    def process_single_url(
        self,
        url: str,
        message_id: Optional[int] = None,
        message_date: Optional[datetime] = None,
        **kwargs: Any,
    ) -> Optional[Dict[str, Any]]:
        """
        Process a URL with Smart Overwrite & checkpoint update.
        Skips already processed URLs unless reprocess=True.
        """
        # Resume Check: Skip if already in SQLite and file exists
        if not self.reprocess:
            existing_rec = self.db.get_record(url)
            if existing_rec:
                # Verify file still exists on disk
                target_file = Path(existing_rec.file_path)
                if target_file.exists():
                    logger.info("⏩ [SKIP - Already Processed] %s -> %s", url, target_file.name)
                    self.skipped_count += 1
                    return None

        logger.info("📥 [PROCESSING] %s", url)
        date_str = (message_date or datetime.now(timezone.utc)).strftime("%Y-%m-%d")

        # 1. Scrape Content
        scraped = self.scraper.scrape(url, force_visual=self.force_visual, **kwargs)

        # 2. Multimodal AI Triage
        triage = self.ai.process_content(scraped, date_str=date_str, **kwargs)
        notebooklm_md = triage.to_notebooklm_markdown()

        # 3. Resolve Target Path (Smart Overwrite)
        target_path, is_overwrite = self.db.resolve_target_filepath(
            url=url,
            category=triage.category,
            title=triage.title,
            vault_path=self.settings.obsidian_vault_path,
        )

        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(notebooklm_md)

        # 4. Update Database & Checkpoint
        self.db.upsert_record(
            url=url,
            file_path=target_path,
            category=triage.category,
            title=triage.title,
            item_type=triage.item_type,
            telegram_message_id=message_id,
        )

        if message_id:
            self.db.set_checkpoint("last_processed_message_id", str(message_id))
            self.db.set_checkpoint("last_processed_url", url)

        # 5. Calendar Event for Jobs
        if triage.item_type == "job":
            self.calendar.create_job_event(title=triage.title, url=url, notes=triage.summary)

        self.processed_count += 1
        self.categories_processed[triage.category] = self.categories_processed.get(triage.category, 0) + 1

        action_name = "UPDATED (Overwritten)" if is_overwrite else "CREATED (New)"
        logger.info("✅ [%s] %s -> [%s] %s", action_name, triage.title, triage.category, target_path.name)

        return {
            "url": url,
            "title": triage.title,
            "category": triage.category,
            "target_path": str(target_path),
        }

    async def run_session(self, since_date: Optional[datetime] = None, limit: Optional[int] = None) -> None:
        """Run the session for the configured time duration."""
        if not TELETHON_AVAILABLE:
            logger.error("Telethon library not found. Please install dependencies.")
            return

        if not self.settings.telegram_api_id or not self.settings.telegram_api_hash:
            logger.error(
                "❌ Telegram credentials missing. Please fill in TELEGRAM_API_ID and TELEGRAM_API_HASH in .env."
            )
            return

        self.start_time = time.time()
        logger.info(
            "🚀 Starting %s session with checkpointing...",
            self.format_time(self.duration_seconds)
        )
        logger.info("📂 Vault Destination: %s", self.settings.obsidian_vault_path)
        logger.info("🤖 AI Provider: %s (%s)", self.settings.llm_provider, self.settings.vision_model if self.settings.vision_enabled else self.settings.ollama_model)

        client = TelegramClient(
            self.settings.telegram_session_name,
            self.settings.telegram_api_id,
            self.settings.telegram_api_hash,
        )

        try:
            await client.start(phone=self.settings.telegram_phone)
            logger.info("🔌 Connected to Telegram successfully.")

            async for message in self.iter_messages_with_resume(client, since_date=since_date, limit=limit):
                if self.stop_requested or self.is_time_up():
                    break

                urls = list(extract_urls(message.text))
                for url in urls:
                    if self.stop_requested or self.is_time_up():
                        break

                    self.print_status_bar()
                    try:
                        self.process_single_url(
                            url=url,
                            message_id=message.id,
                            message_date=message.date,
                        )
                    except Exception as e:
                        self.failed_count += 1
                        logger.error("❌ Error processing %s: %s", url, e, exc_info=False)

            elapsed_total = time.time() - self.start_time
            print("\n" + "=" * 65)
            if self.is_time_up():
                print(f"⏱️  TIME LIMIT REACHED ({self.format_time(self.duration_seconds)}) - SESSION PAUSED")
            elif self.stop_requested:
                print("🛑 SESSION INTERRUPTED BY USER - CHECKPOINT SAVED")
            else:
                print("🏁 BATCH COMPLETED ALL MESSAGES UP TO CUTOFF")
            print("=" * 65)
            print(f"📊 SESSION SUMMARY:")
            print(f"  • Time Elapsed:       {self.format_time(elapsed_total)}")
            print(f"  • Notes Processed:    {self.processed_count}")
            print(f"  • Already Existing:   {self.skipped_count} (skipped without wasting tokens)")
            print(f"  • Errors/Failed:      {self.failed_count}")
            
            if self.categories_processed:
                print("\n📁 CATEGORIES BREAKDOWN (This Session):")
                for cat, count in sorted(self.categories_processed.items(), key=lambda x: -x[1]):
                    print(f"  - {cat:15s}: {count} note(s)")

            stats = self.db.get_summary_stats()
            print(f"\n📈 TOTAL VAULT STATS (All Sessions):")
            print(f"  • Total Tracked URLs: {stats['total_processed']}")
            print(f"  • Job Opportunities:  {stats['jobs_count']}")
            print("=" * 65)
            print("💡 TO RESUME WHERE YOU LEFT OFF, JUST RUN:")
            print("   python run_timed_session.py")
            print("=" * 65 + "\n")

        except RPCError as e:
            logger.error("Telegram RPC Error: %s", e)
        finally:
            await client.disconnect()

    def run_reprocess_failed(self, limit: Optional[int] = None) -> None:
        """
        Scan all notes in database that are in 'other' or have placeholder stubs,
        re-extract them with enhanced extractors (YouTube transcripts, ArXiv),
        and relocate them into appropriate 20-folder taxonomy folders.
        """
        self.start_time = time.time()
        logger.info("🔄 Scanning database for failed or placeholder notes in 'other'...")
        records = list(self.db.iter_records())
        failed_records = [
            r for r in records
            if r.category == "other" or "failed" in r.title.lower() or "youtube.com" in r.url or "youtu.be" in r.url or "arxiv.org" in r.url
        ]
        total_targets = len(failed_records)
        logger.info("Found %d candidate notes to reprocess and categorize.", total_targets)

        target_list = failed_records[:limit] if limit else failed_records
        for idx, r in enumerate(target_list, 1):
            if self.stop_requested or self.is_time_up():
                break

            logger.info("Progress [%d/%d]: Reprocessing %s", idx, len(target_list), r.url)
            self.print_status_bar()
            try:
                # Force reprocessing on this URL
                old_reprocess = self.reprocess
                self.reprocess = True
                self.process_single_url(url=r.url, message_id=r.telegram_message_id)
                self.reprocess = old_reprocess
            except Exception as e:
                self.failed_count += 1
                logger.error("Error reprocessing %s: %s", r.url, e)

        elapsed_total = time.time() - self.start_time
        print("\n" + "=" * 65)
        print("🏁 REPROCESSING COMPLETE")
        print("=" * 65)
        print(f"📊 SUMMARY:")
        print(f"  • Time Elapsed:       {self.format_time(elapsed_total)}")
        print(f"  • Successfully Fixed: {self.processed_count}")
        print(f"  • Errors/Failed:      {self.failed_count}")
        stats = self.db.get_summary_stats()
        print(f"\n📈 UPDATED VAULT STATS (All Categories):")
        for cat, cnt in sorted(stats["categories"].items(), key=lambda x: -x[1]):
            print(f"  - {cat:15s}: {cnt} note(s)")
        print("=" * 65 + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Librarian AI timed ETL session with state checkpointing and automatic resumption."
    )
    parser.add_argument(
        "--duration-minutes",
        type=float,
        default=15.0,
        help="Session duration in minutes before pausing (default: 15.0)",
    )
    parser.add_argument(
        "--since",
        type=str,
        default="2025-09-01",
        help="Ingestion cutoff date YYYY-MM-DD (default: 2025-09-01)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of Telegram messages to scan",
    )
    parser.add_argument(
        "--reprocess",
        action="store_true",
        help="Force reprocessing and updating existing notes instead of skipping them",
    )
    parser.add_argument(
        "--reprocess-failed",
        action="store_true",
        help="Scan and reprocess existing 'other' or failed notes in vault with enhanced extractors",
    )
    parser.add_argument(
        "--visual",
        action="store_true",
        help="Force visual screenshot tile rendering on all pages (PixelRAG mode)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    since_dt = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    runner = TimedSessionRunner(
        duration_minutes=args.duration_minutes,
        reprocess=args.reprocess,
        reprocess_failed=args.reprocess_failed,
        force_visual=args.visual,
    )

    # Handle graceful termination on Ctrl+C
    def sig_handler(sig: int, frame: Any) -> None:
        logger.info("\nReceived stop signal. Finishing current URL and saving checkpoint...")
        runner.stop_requested = True

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    if args.reprocess_failed:
        runner.run_reprocess_failed(limit=args.limit)
    else:
        asyncio.run(runner.run_session(since_date=since_dt, limit=args.limit))


if __name__ == "__main__":
    main()
