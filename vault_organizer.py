"""
Vault Cleaner & Knowledge Compendium Generator for Personal Intelligence ETL.

Features:
1. Analyzes unsorted notes in vault/other/ and accurately reclassifies them into the 20-folder taxonomy.
2. Relocates markdown files to their target directories and updates SQLite database tracking.
3. Cleans up empty / failed placeholder notes.
4. Generates a comprehensive, high-density NotebookLM Master Compendium (vault/NOTEBOOKLM_KNOWLEDGE_BASE.md).
"""

import logging
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Set, Tuple

from config import settings
from database import db_manager
from utils import log_execution, measure_performance, sanitize_filename

logger = logging.getLogger("librarian.organizer")

TAXONOMY_RULES: Dict[str, List[str]] = {
    "jobs": [
        r"\b(?:engineer\s*[\$€£0-9]|qa\s+engineer|sdet|manual\s+qa|middle\s+qa|senior\s+qa|qa\s+tester|full\s*stack\s+qa|automation\s+qa|qa\s+manual|careers|job\s+openings|ваканс|найди\s+работу|віддалена\s+робота|online\s+class\s+linkedin|softeq\s+careers|grid\s+dynamics|zoolatech|omnicore|blackrock\s+software|ascendix|startupsoft|neverending|dash\s+financial|quantox|mind\s+studios|small\s+metrics|netflix\s+careers|dataannotation|injobe)\b",
        r"\b(?:salary|compensation|responsibilities|qualifications|hiring|job\s+posting|vacancy|apply\s+now)\b",
    ],
    "trading": [
        r"\b(?:futures\s+trading|order\s+block|smart\s+money|prop\s+firm|bybit|turbo\s+trade|tradingview|crypto\s+fund|gocollect\s+payout|funded\s+accounts|london\s+&\s+new\s+york\s+session|forex|pnl|leverage)\b",
    ],
    "agents": [
        r"\b(?:ai\s+agents?|langgraph|agentmemory|llm\s+wiki|claude\s+code\s+subagents|moltbot|agent-reach|roo\s+code|coding\s+agents|autogen|crewai|superpowers|agentic|multi-agent)\b",
    ],
    "ML": [
        r"\b(?:machine\s+learning|gemma|llama|qwen|transformers|gguf|kquant|vram|rag|100-days-of-ml|pleias-rag|deep\s+learning|fine-tuning|lora|quantization|embeddings|ollama|mamaylm|whisper)\b",
    ],
    "research": [
        r"\b(?:scientific\s+research|arxiv|carbon\s+neutrality|verra|vm0042|benchmark|empirical|academic\s+paper|nuclear\s+weapon|labor\s+market\s+impacts|claims\s+provable|frontier\s+model|methodology\s+breakdown)\b",
    ],
    "workflows": [
        r"\b(?:ai-пайплайн|пайплайн|піраміда\s+тестування|one\s+page\s+test\s+plan|github\s+spec\s+kit|friday\s+night\s+testing|інженерія\s+якості|playwright\s+vs\s+selenium|playwright-ui-api|vibe\s+coded|ci/cd|test\s+automation|testing\s+practices|версіонування\s+api)\b",
    ],
    "cases": [
        r"\b(?:ai\s+engineering\s+mindset|netflix\s+ai|сільпо\s+ai\s+factory|хакатон|як\s+ми\s+скоротили\s+підготовку|як\s+змінилася\s+роль\s+qa|я\s+побудувала\s+ai-пайплайн|case\s+study|revenuecat\s+shipaton)\b",
    ],
    "tools": [
        r"\b(?:toon\s+🎒|token-oriented|vscode\s+extension|markgone|remove\s+watermarks|rentahuman|spoti-flac|flowsurface|skales|petdex|oh\s+my\s+git|postgres|mongodb|desktop\s+app|cli\s+tool|software\s+utility)\b",
    ],
    "hints": [
        r"\b(?:89\s+things\s+i\s+know\s+about\s+git|git\s+для\s+самых\s+маленьких|задачи\s+и\s+решения\s+для\s+бойца\s+postgresql|уроки\s+sql|гайды\s+по\s+python|гайды\s+по\s+бд|qa\s+quiz|собеседовании\s+у\s+qa|що\s+питають\s+на\s+співбесіді|interview\s+questions|quick\s+tips|cheat\s+sheet)\b",
    ],
    "literature": [
        r"\b(?:30\s+days\s+of\s+python|30-seconds-of-python|learn-python|python\s+reference|python-guide|project-based-learning|amazing-python-scripts|awesome-python|book|epam\s+campus|leadership\s+foundations|courses?|tutorial|textbook|guidebook)\b",
    ],
    "repositories": [
        r"\b(?:github\s*-\s*|0xsojalsecanus|coding-problems|self-learning-skills|thealgorithmspython|huggingface\s+spaces|repo|source\s+code)\b",
    ],
    "issues": [
        r"\b(?:attacking\s+mongodb|ipv6\s+penetration\s+testing|bug\s+bounty|vulnerability|exploit|stenography|cve|cident-be-ex|security\s+audit)\b",
    ],
    "ideas": [
        r"\b(?:ai\s+money\s+lab|ai❤️4life|ben\s+horowitz|right\s+product,\s+right\s+time|image\s+to\s+video\s+ai|startup\s+ideas?|business\s+concepts?)\b",
    ],
}


@dataclass
class VaultNote:
    """Representation of a Vault Note."""
    file_path: Path
    title: str
    category: str
    content: str
    url: Optional[str] = None
    summary: str = ""
    insights: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    is_failed: bool = False


class VaultOrganizer:
    """
    Intelligent Vault Cleaner and NotebookLM Compendium Builder.
    """

    def __init__(self, vault_path: Optional[Path] = None, **kwargs: Any) -> None:
        self.vault_path: Path = Path(vault_path or settings.obsidian_vault_path).resolve()
        self.db = db_manager
        self.stats: Dict[str, int] = {
            "reclassified": 0,
            "moved": 0,
            "failed_cleaned": 0,
            "processed": 0,
        }

    def _iter_vault_markdown_files(self, folder_name: Optional[str] = None, **kwargs: Any) -> Generator[Path, None, None]:
        """Lazy generator yielding markdown file paths in the vault."""
        target_dir = self.vault_path / folder_name if folder_name else self.vault_path
        if not target_dir.exists():
            return
        for root, _, files in os.walk(target_dir):
            for file_name in sorted(files):
                if file_name.endswith(".md") and not file_name.startswith("NOTEBOOKLM"):
                    yield Path(root) / file_name

    def parse_note(self, file_path: Path, **kwargs: Any) -> Optional[VaultNote]:
        """Parse note content and extract frontmatter / markdown sections."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError) as e:
            logger.warning("Could not read %s: %s", file_path, e)
            return None

        # Extract title from H1 or filename
        title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else file_path.stem

        # Extract URL
        url_match = re.search(r"\*\*Source URL\*\*:\s*\[.*?\]\((https?://[^\)]+)\)", content)
        url = url_match.group(1) if url_match else None

        # Check if failed scrape
        is_failed = "#failed_scrape" in content or "Failed Scrape" in title or len(content.strip()) < 100

        # Extract Summary
        summary = ""
        summary_match = re.search(r"##\s+AI Summary\s*\n(.*?)(?=\n##|\Z)", content, re.DOTALL)
        if summary_match:
            summary = summary_match.group(1).strip()

        # Extract Insights
        insights = []
        insights_match = re.search(r"##\s+Key Insights\s*\n(.*?)(?=\n##|\Z)", content, re.DOTALL)
        if insights_match:
            for line in insights_match.group(1).strip().splitlines():
                line = re.sub(r"^[-*•]\s*", "", line).strip()
                if line and not line.startswith("No specific insights"):
                    insights.append(line)

        # Extract Tags
        tags = re.findall(r"#([a-zA-Z0-9_\-\/]+)", content)

        parent_folder = file_path.parent.name
        return VaultNote(
            file_path=file_path,
            title=title,
            category=parent_folder,
            content=content,
            url=url,
            summary=summary,
            insights=insights,
            tags=tags,
            is_failed=is_failed,
        )

    def classify_note(self, note: VaultNote, **kwargs: Any) -> str:
        """Classify note content using taxonomy rules."""
        text_corpus = f"{note.title}\n{note.file_path.stem}\n{note.url or ''}\n{note.summary}\n{' '.join(note.insights)}\n{note.content[:2000]}".lower()

        scores: Dict[str, int] = {}
        for category, patterns in TAXONOMY_RULES.items():
            score = 0
            for pat in patterns:
                matches = re.findall(pat, text_corpus, re.IGNORECASE)
                score += len(matches)
            if score > 0:
                scores[category] = score

        if scores:
            best_cat = max(scores.items(), key=lambda x: x[1])[0]
            return best_cat

        # Default heuristic based on keywords
        if "github.com" in text_corpus:
            return "repositories"
        elif "podcast" in text_corpus or "youtube.com" in text_corpus:
            return "workflows"
        elif "linkedin.com" in text_corpus:
            return "jobs"

        return "other"

    @measure_performance
    def reorganize_vault(self, dry_run: bool = False, **kwargs: Any) -> List[Tuple[Path, Path, str]]:
        """Reorganize all notes from vault/other/ into proper category folders."""
        moves: List[Tuple[Path, Path, str]] = []
        logger.info("🚀 Starting intelligent vault reorganization (dry_run=%s)...", dry_run)

        for file_path in self._iter_vault_markdown_files(folder_name="other"):
            self.stats["processed"] += 1
            note = self.parse_note(file_path)
            if not note:
                continue

            # Check if dead failed stub with no text
            if note.is_failed and len(note.content) < 300:
                logger.info("🗑️  Cleaning up dead failed stub: %s", file_path.name)
                if not dry_run:
                    file_path.unlink(missing_ok=True)
                self.stats["failed_cleaned"] += 1
                continue

            target_category = self.classify_note(note)
            if target_category != "other":
                target_dir = self.vault_path / target_category
                target_dir.mkdir(parents=True, exist_ok=True)
                target_path = target_dir / file_path.name

                moves.append((file_path, target_path, target_category))
                self.stats["reclassified"] += 1

                if not dry_run:
                    # Move file on disk
                    shutil.move(str(file_path), str(target_path))
                    self.stats["moved"] += 1

                    # Update SQLite record in processed_links
                    with self.db.get_connection() as conn:
                        conn.execute(
                            """
                            UPDATE processed_links
                            SET file_path = ?, category = ?, item_type = ?
                            WHERE file_path = ? OR file_path LIKE ? OR (url IS NOT NULL AND url = ?)
                            """,
                            (
                                str(target_path.resolve()),
                                target_category,
                                "job" if target_category == "jobs" else "knowledge",
                                str(file_path.resolve()),
                                f"%{file_path.name}",
                                note.url or "",
                            ),
                        )
                    logger.info("📦 Moved: %s -> [%s] %s", file_path.name, target_category, target_path.name)

    def sync_database_with_vault(self) -> None:
        """Scan all markdown files in vault and synchronize SQLite category and file_path."""
        logger.info("🔄 Synchronizing SQLite database with current vault directory structure...")
        with self.db.get_connection() as conn:
            for file_path in self._iter_vault_markdown_files():
                category = file_path.parent.name
                item_type = "job" if category == "jobs" else "knowledge"
                conn.execute(
                    """
                    UPDATE processed_links
                    SET file_path = ?, category = ?, item_type = ?
                    WHERE file_path LIKE ? OR file_path = ?
                    """,
                    (str(file_path.resolve()), category, item_type, f"%{file_path.name}", str(file_path.resolve())),
                )

    @measure_performance
    def generate_notebooklm_compendium(self, output_filename: str = "NOTEBOOKLM_KNOWLEDGE_BASE.md", **kwargs: Any) -> Path:
        """
        Synthesize all notes across the vault into a structured Master Knowledge Pack
        specifically formatted for Google NotebookLM source ingestion.
        """
        output_path = self.vault_path / output_filename
        logger.info("📚 Generating Master NotebookLM Compendium at %s...", output_path)

        # Categorize all valid notes across the entire vault
        catalog: Dict[str, List[VaultNote]] = {}
        total_notes = 0

        for file_path in self._iter_vault_markdown_files():
            note = self.parse_note(file_path)
            if not note or note.is_failed:
                continue

            cat = note.category
            if cat not in catalog:
                catalog[cat] = []
            catalog[cat].append(note)
            total_notes += 1

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        # Build Master Markdown Document
        doc_lines: List[str] = [
            "# 🧠 Personal Intelligence & Engineering Knowledge Base",
            f"> **Master Knowledge Compendium for NotebookLM Synthesis & Audio Deep Dives**",
            f"> **Generated**: {now_str} | **Total Analyzed Sources**: {total_notes} notes across {len(catalog)} domains",
            "",
            "---",
            "",
            "## 📖 Executive Table of Contents & Knowledge Domains",
            "",
        ]

        # Domain summary table
        doc_lines.append("| Domain | Folder | Notes Count | Key Themes |")
        doc_lines.append("|---|---|---|---|")
        domain_descriptions = {
            "agents": "Autonomous AI Agents, LangGraph, Multi-Agent Architectures, Agentic Memory",
            "ML": "Large Language Models, Local Inference, Quantization, RAG Systems, Embeddings",
            "workflows": "Quality Engineering, SDET AI Pipelines, Test Automation, CI/CD, Git Practices",
            "cases": "Real-world Enterprise AI Implementations (Netflix, Silpo, Svoi.ru)",
            "research": "Scientific Benchmarks, Environmental & Market Studies, Frontier Models",
            "tools": "Developer Tooling, VS Code Extensions, Data Protocols (TOON), Utilities",
            "trading": "Financial Markets, Smart Money Concepts, Order Blocks, Prop Trading",
            "hints": "Technical Cheat Sheets, SQL & PostgreSQL Optimization, QA Interview Guides",
            "literature": "Comprehensive Tutorials, Python Best Practices, Programming Guides",
            "repositories": "Curated Open-Source Repositories and Reference Codebases",
            "issues": "Security Research, Penetration Testing, Bug Bounty Insights",
            "jobs": "Market Opportunities, AI & QA Engineering Requirements, Salary Benchmarks",
            "ideas": "Product Concepts, Startup Architectures, AI Applications",
            "other": "General Knowledge & Miscellaneous Articles",
        }

        for cat, notes in sorted(catalog.items(), key=lambda x: -len(x[1])):
            desc = domain_descriptions.get(cat, "Technical Knowledge & Resources")
            doc_lines.append(f"| **{cat.upper()}** | `/{cat}` | {len(notes)} | {desc} |")

        doc_lines.append("\n---\n")

        # Knowledge Chapters
        chapter_idx = 1
        for cat, notes in sorted(catalog.items(), key=lambda x: -len(x[1])):
            doc_lines.append(f"# Chapter {chapter_idx}: {cat.upper()} ({len(notes)} Document Sources)")
            doc_lines.append(f"*{domain_descriptions.get(cat, 'Technical domain analysis and synthesized notes.')}*\n")

            for note in notes:
                doc_lines.append(f"## {note.title}")
                if note.url:
                    doc_lines.append(f"- **Source URL**: {note.url}")
                doc_lines.append(f"- **Category Path**: `vault/{cat}/{note.file_path.name}`")
                if note.tags:
                    doc_lines.append(f"- **Tags**: {' '.join(f'#{t}' for t in note.tags[:5])}")
                doc_lines.append("")

                if note.summary and "Summary generated from visual analysis" not in note.summary:
                    doc_lines.append("### Executive Summary")
                    doc_lines.append(note.summary)
                    doc_lines.append("")

                if note.insights:
                    doc_lines.append("### Core Takeaways & Key Insights")
                    for ins in note.insights[:6]:
                        doc_lines.append(f"- {ins}")
                    doc_lines.append("")

                # Extract key excerpts or transcripts
                original_match = re.search(r"##\s+Original Source\s*\n(.*?)(?=\n##|\Z)", note.content, re.DOTALL)
                if original_match:
                    src_text = original_match.group(1).strip()
                    if src_text:
                        # Include up to 2500 characters of high-signal source excerpt
                        clean_excerpt = src_text[:2500]
                        if len(src_text) > 2500:
                            clean_excerpt += "\n... [Source content continued in individual note] ..."
                        doc_lines.append("### Source Excerpt / Dialogue")
                        doc_lines.append(f"```text\n{clean_excerpt}\n```")
                        doc_lines.append("")

                doc_lines.append("---\n")

            chapter_idx += 1

        full_document = "\n".join(doc_lines)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(full_document)

        logger.info("✅ Master NotebookLM Compendium created successfully (%d bytes, %d lines) at %s", len(full_document), len(doc_lines), output_path)
        return output_path


def main() -> None:
    organizer = VaultOrganizer()
    print("=" * 65)
    print("🧹 LAUNCHING VAULT CLEANER & NOTEBOOKLM COMPENDIUM GENERATOR")
    print("=" * 65)

    # 1. Reorganize Vault
    moves = organizer.reorganize_vault(dry_run=False)
    print(f"\n✅ Reorganization Results:")
    print(f"  • Notes Processed:    {organizer.stats['processed']}")
    print(f"  • Notes Reclassified: {organizer.stats['reclassified']}")
    print(f"  • Notes Moved:        {organizer.stats['moved']}")
    print(f"  • Dead Stubs Cleaned: {organizer.stats['failed_cleaned']}")

    # 2. Synchronize Database with on-disk state
    organizer.sync_database_with_vault()

    # 3. Updated Vault Stats
    stats = organizer.db.get_summary_stats()
    print(f"\n📊 NEW VAULT TAXONOMY DISTRIBUTION:")
    for cat, cnt in sorted(stats["categories"].items(), key=lambda x: -x[1]):
        if cnt > 0:
            print(f"  - /{cat:15s}: {cnt} note(s)")

    # 4. Generate NotebookLM Document
    compendium_path = organizer.generate_notebooklm_compendium()
    print(f"\n📚 NOTEBOOKLM MASTER DOCUMENT CREATED:")
    print(f"  • Destination: {compendium_path}")
    print(f"  • File Size:   {compendium_path.stat().st_size / 1024:.1f} KB")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
