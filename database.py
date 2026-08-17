"""
SQLite persistence and Smart Overwrite tracking for Librarian AI.
Tracks processed URLs, categories, file paths, and locates moved notes within Obsidian Vault.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
import sqlite3
from typing import Any, Dict, Generator, Iterator, Optional, Tuple, Union

from config import settings
from utils import log_execution, measure_performance, sanitize_filename


class ProcessedRecord:
    """Represents a tracked URL and note in SQLite."""

    def __init__(
        self,
        url: str,
        file_path: str,
        category: str,
        **kwargs: Any,
    ) -> None:
        self.url: str = url
        self.file_path: str = file_path
        self.category: str = category
        self.title: str = kwargs.get("title", "")
        self.item_type: str = kwargs.get("item_type", "knowledge")
        self.telegram_message_id: Optional[int] = kwargs.get("telegram_message_id")
        self.processed_at: str = kwargs.get("processed_at", datetime.now(timezone.utc).isoformat())
        self.content_hash: str = kwargs.get("content_hash", "")

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def __str__(self) -> str:
        return f"ProcessedRecord(url='{self.url}', path='{self.file_path}', cat='{self.category}')"

    def __repr__(self) -> str:
        return self.__str__()


class DatabaseManager:
    """Manages SQLite database operations and Smart Overwrite file path resolution."""

    def __init__(self, db_path: Optional[Union[str, Path]] = None, **kwargs: Any) -> None:
        self.db_path: Path = Path(db_path or settings.db_path).resolve()
        self._init_db()

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for atomic SQLite transactions."""
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except sqlite3.Error as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Create the processed_links table and indexes if they do not exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS processed_links (
                    url TEXT PRIMARY KEY,
                    title TEXT,
                    file_path TEXT NOT NULL,
                    category TEXT NOT NULL,
                    item_type TEXT NOT NULL,
                    telegram_message_id INTEGER,
                    processed_at TEXT NOT NULL,
                    content_hash TEXT
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoints (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_category ON processed_links(category);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_file_path ON processed_links(file_path);"
            )

    def __len__(self) -> int:
        """Return total count of processed URLs in database."""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM processed_links")
            row = cursor.fetchone()
            return int(row[0]) if row else 0

    def __contains__(self, url: str) -> bool:
        """Check if a URL has already been processed."""
        return self.get_record(url) is not None

    def __iter__(self) -> Iterator[ProcessedRecord]:
        """Lazy iterator yielding all processed records from SQLite."""
        return self.iter_records()

    def iter_records(self, **kwargs: Any) -> Generator[ProcessedRecord, None, None]:
        """Lazy generator yielding ProcessedRecord items from SQLite."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT url, title, file_path, category, item_type, telegram_message_id, processed_at, content_hash "
                "FROM processed_links ORDER BY processed_at DESC"
            )
            for row in cursor:
                yield ProcessedRecord(
                    url=row["url"],
                    file_path=row["file_path"],
                    category=row["category"],
                    title=row["title"],
                    item_type=row["item_type"],
                    telegram_message_id=row["telegram_message_id"],
                    processed_at=row["processed_at"],
                    content_hash=row["content_hash"],
                )

    def get_record(self, url: str, **kwargs: Any) -> Optional[ProcessedRecord]:
        """Fetch record for a specific URL."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT url, title, file_path, category, item_type, telegram_message_id, processed_at, content_hash "
                "FROM processed_links WHERE url = ?",
                (url,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return ProcessedRecord(
                url=row["url"],
                file_path=row["file_path"],
                category=row["category"],
                title=row["title"],
                item_type=row["item_type"],
                telegram_message_id=row["telegram_message_id"],
                processed_at=row["processed_at"],
                content_hash=row["content_hash"],
            )

    def upsert_record(
        self,
        url: str,
        file_path: Union[str, Path],
        category: str,
        **kwargs: Any,
    ) -> ProcessedRecord:
        """Insert or update a URL record in SQLite."""
        title: str = kwargs.get("title", "")
        item_type: str = kwargs.get("item_type", "knowledge")
        telegram_message_id: Optional[int] = kwargs.get("telegram_message_id")
        processed_at: str = kwargs.get("processed_at", datetime.now(timezone.utc).isoformat())
        content_hash: str = kwargs.get("content_hash", "")

        str_path = str(Path(file_path).resolve())

        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO processed_links (
                    url, title, file_path, category, item_type, telegram_message_id, processed_at, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    title = excluded.title,
                    file_path = excluded.file_path,
                    category = excluded.category,
                    item_type = excluded.item_type,
                    telegram_message_id = COALESCE(excluded.telegram_message_id, processed_links.telegram_message_id),
                    processed_at = excluded.processed_at,
                    content_hash = excluded.content_hash;
                """,
                (url, title, str_path, category, item_type, telegram_message_id, processed_at, content_hash),
            )

        return ProcessedRecord(
            url=url,
            file_path=str_path,
            category=category,
            title=title,
            item_type=item_type,
            telegram_message_id=telegram_message_id,
            processed_at=processed_at,
            content_hash=content_hash,
        )

    def set_checkpoint(self, key: str, value: str, **kwargs: Any) -> None:
        """Store or update a checkpoint state in SQLite."""
        now = datetime.now(timezone.utc).isoformat()
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO checkpoints (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at;
                """,
                (key, str(value), now),
            )

    def get_checkpoint(self, key: str, **kwargs: Any) -> Optional[str]:
        """Retrieve stored checkpoint value by key."""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT value FROM checkpoints WHERE key = ?", (key,))
            row = cursor.fetchone()
            return str(row["value"]) if row else None

    def get_summary_stats(self, **kwargs: Any) -> Dict[str, Any]:
        """Return breakdown of processed URLs, categories, and jobs."""
        with self.get_connection() as conn:
            total_cursor = conn.execute("SELECT COUNT(*) FROM processed_links")
            total = total_cursor.fetchone()[0]

            jobs_cursor = conn.execute("SELECT COUNT(*) FROM processed_links WHERE item_type = 'job'")
            jobs_count = jobs_cursor.fetchone()[0]

            cat_cursor = conn.execute(
                "SELECT category, COUNT(*) as cnt FROM processed_links GROUP BY category ORDER BY cnt DESC"
            )
            categories = {row["category"]: row["cnt"] for row in cat_cursor}

            return {
                "total_processed": total,
                "jobs_count": jobs_count,
                "categories": categories,
            }

    def iter_vault_markdown_files(
        self,
        vault_path: Path,
        **kwargs: Any,
    ) -> Generator[Path, None, None]:
        """Lazy generator scanning all .md files in the Obsidian vault."""
        if not vault_path.exists():
            return
        try:
            for file_path in vault_path.rglob("*.md"):
                if file_path.is_file():
                    yield file_path
        except (OSError, PermissionError) as e:
            # Handle vault directory traversal errors gracefully
            return

    def locate_moved_file_in_vault(
        self,
        url: str,
        vault_path: Path,
        **kwargs: Any,
    ) -> Optional[Path]:
        """
        Locates a note file if moved by the user in Obsidian.
        Matches by frontmatter 'url: <url>' or filename.
        """
        expected_filename: Optional[str] = kwargs.get("expected_filename")

        # 1. Search for frontmatter url match (100% precision even if renamed or moved)
        for md_file in self.iter_vault_markdown_files(vault_path):
            try:
                with open(md_file, "r", encoding="utf-8", errors="ignore") as f:
                    # Read first 30 lines (frontmatter area) to avoid reading massive files
                    head_lines = [f.readline() for _ in range(30)]
                    head_content = "".join(head_lines)
                    # Check frontmatter url: url pattern
                    if f"url: {url}" in head_content or f'url: "{url}"' in head_content or f"url: '{url}'" in head_content:
                        return md_file
            except (OSError, PermissionError):
                continue

        # 2. Fallback search by exact filename if provided
        if expected_filename:
            for md_file in self.iter_vault_markdown_files(vault_path):
                if md_file.name == expected_filename:
                    return md_file

        return None

    @measure_performance
    def resolve_target_filepath(
        self,
        url: str,
        category: str,
        title: str,
        vault_path: Optional[Path] = None,
        **kwargs: Any,
    ) -> Tuple[Path, bool]:
        """
        Smart Overwrite path resolver:
        1. Check if URL is in DB.
        2. If stored file exists on disk, reuse it for overwrite.
        3. If file moved, scan vault to locate the new path and reuse it.
        4. If not found in vault, create standard path at vault/category/title.md.
        Returns (target_path, is_overwrite_flag).
        """
        v_path = (vault_path or settings.obsidian_vault_path).resolve()
        safe_title = sanitize_filename(title)
        default_filename = f"{safe_title}.md"
        default_path = v_path / category / default_filename

        existing_record = self.get_record(url)
        if existing_record:
            stored_path = Path(existing_record.file_path).resolve()
            # Case A: File still exists at stored path
            if stored_path.exists() and stored_path.is_file():
                return stored_path, True

            # Case B: File moved within vault - scan vault to locate it
            moved_path = self.locate_moved_file_in_vault(
                url=url,
                vault_path=v_path,
                expected_filename=stored_path.name,
            )
            if moved_path and moved_path.exists():
                return moved_path, True

        # Case C: Not found in DB or vault - create clean target path
        # Ensure category folder exists
        default_path.parent.mkdir(parents=True, exist_ok=True)
        return default_path, (default_path.exists())


db_manager = DatabaseManager()
