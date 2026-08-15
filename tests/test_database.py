"""
Unit tests for database.py and Smart Overwrite logic.
"""

from pathlib import Path
import tempfile
import pytest

from database import DatabaseManager, ProcessedRecord


@pytest.fixture
def temp_vault_and_db():
    with tempfile.TemporaryDirectory() as tmp_dir:
        vault_path = Path(tmp_dir) / "vault"
        vault_path.mkdir(parents=True, exist_ok=True)
        db_path = Path(tmp_dir) / "test_processed_links.db"
        manager = DatabaseManager(db_path=db_path)
        yield vault_path, manager


def test_database_crud(temp_vault_and_db):
    vault_path, db = temp_vault_and_db
    url = "https://github.com/test/repo"
    file_path = vault_path / "repositories" / "test_repo.md"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("sample content", encoding="utf-8")

    # Insert record
    record = db.upsert_record(
        url=url,
        file_path=file_path,
        category="repositories",
        title="Test Repo",
        item_type="knowledge",
    )

    assert record.url == url
    assert len(db) == 1
    assert url in db

    # Fetch record
    fetched = db.get_record(url)
    assert fetched is not None
    assert fetched.title == "Test Repo"
    assert fetched.category == "repositories"


def test_smart_overwrite_existing_file(temp_vault_and_db):
    vault_path, db = temp_vault_and_db
    url = "https://example.com/article"
    category = "research"
    target_folder = vault_path / category
    target_folder.mkdir(parents=True, exist_ok=True)
    original_file = target_folder / "article_note.md"
    original_file.write_text("---\nurl: https://example.com/article\n---\n# Old Content", encoding="utf-8")

    db.upsert_record(url=url, file_path=original_file, category=category, title="Article Note")

    # Smart overwrite resolution when file stays in place
    resolved_path, is_overwrite = db.resolve_target_filepath(
        url=url, category=category, title="Article Note", vault_path=vault_path
    )

    assert is_overwrite is True
    assert resolved_path == original_file.resolve()


def test_smart_overwrite_moved_file_in_vault(temp_vault_and_db):
    vault_path, db = temp_vault_and_db
    url = "https://example.com/moved-post"

    # Step 1: File originally created in /drafts
    drafts_folder = vault_path / "drafts"
    drafts_folder.mkdir(parents=True, exist_ok=True)
    old_file_path = drafts_folder / "moved_post.md"
    old_file_path.write_text("---\nurl: https://example.com/moved-post\n---\n# Draft Note", encoding="utf-8")

    db.upsert_record(url=url, file_path=old_file_path, category="drafts", title="Moved Post")

    # Step 2: User moves file from /drafts to /agents in Obsidian!
    agents_folder = vault_path / "agents"
    agents_folder.mkdir(parents=True, exist_ok=True)
    new_moved_path = agents_folder / "curated_moved_post.md"
    old_file_path.rename(new_moved_path)

    assert not old_file_path.exists()
    assert new_moved_path.exists()

    # Step 3: Re-processing the same URL should locate the moved file in /agents and overwrite it there
    resolved_path, is_overwrite = db.resolve_target_filepath(
        url=url, category="agents", title="Moved Post", vault_path=vault_path
    )

    assert is_overwrite is True
    assert resolved_path.resolve() == new_moved_path.resolve()


def test_lazy_iteration(temp_vault_and_db):
    vault_path, db = temp_vault_and_db
    for i in range(5):
        url = f"https://example.com/item_{i}"
        p = vault_path / "tools" / f"item_{i}.md"
        db.upsert_record(url=url, file_path=p, category="tools", title=f"Item {i}")

    assert len(db) == 5
    records = list(db.iter_records())
    assert len(records) == 5
    assert all(isinstance(r, ProcessedRecord) for r in records)
