"""
Configuration and settings for Librarian AI.
Manages environment variables, default constants, and the 20-folder taxonomy guide.
"""

from datetime import datetime, timezone
import os
from pathlib import Path
import re
from typing import Any, Dict, List

try:
    from dotenv import load_dotenv
    # Load .env from current project directory
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        load_dotenv(dotenv_path=env_file, override=True)
    else:
        load_dotenv(override=True)
except ImportError:
    pass


class Settings:
    """Application configuration container."""

    def __init__(self, **kwargs: Any) -> None:
        # Telegram Settings
        raw_api_id = os.getenv("TELEGRAM_API_ID", "").strip().strip("'\"")
        try:
            self.telegram_api_id: int = int(raw_api_id) if raw_api_id else 0
        except ValueError:
            self.telegram_api_id = 0
        self.telegram_api_hash: str = os.getenv("TELEGRAM_API_HASH", "").strip().strip("'\"")
        self.telegram_phone: str = os.getenv("TELEGRAM_PHONE", "").strip().strip("'\"")
        self.telegram_session_name: str = os.getenv("TELEGRAM_SESSION_NAME", "librarian_telegram").strip().strip("'\"")

        # Ingestion Filter Cutoff (September 1, 2025)
        self.ingestion_start_date: datetime = datetime(2025, 9, 1, 0, 0, 0, tzinfo=timezone.utc)

        # Storage & Paths
        self.db_path: Path = Path(os.getenv("DATABASE_PATH", "processed_links.db")).resolve()
        self.obsidian_vault_path: Path = Path(os.getenv("OBSIDIAN_VAULT_PATH", "./vault")).resolve()
        self.cookies_path: Path = Path(os.getenv("COOKIES_PATH", "cookies.json")).resolve()

        # AI Engine Settings
        self.llm_provider: str = os.getenv("LLM_PROVIDER", "llamacpp" if not os.getenv("USE_OPENAI", "false").lower() in ("true", "1", "yes") else "openai").lower()
        self.llamacpp_base_url: str = os.getenv("LLAMACPP_BASE_URL", "http://localhost:8080/v1")
        self.llamacpp_model_name: str = os.getenv("LLAMACPP_MODEL_NAME", "Muse-Glimmer-30B")
        self.reasoning_effort: str = os.getenv("REASONING_EFFORT", "high")

        self.use_openai: bool = os.getenv("USE_OPENAI", "false").lower() in ("true", "1", "yes") or self.llm_provider == "openai"
        self.openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
        self.openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o")
        self.ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3:8b")

        # Vision Model Settings (Self-Hosted / Cloud)
        self.vision_enabled: bool = os.getenv("VISION_ENABLED", "true").lower() in ("true", "1", "yes")
        self.vision_provider: str = os.getenv("VISION_PROVIDER", self.llm_provider).lower()
        self.vision_model: str = os.getenv("VISION_MODEL", self.llamacpp_model_name if self.vision_provider == "llamacpp" else "llama3.2-vision")
        self.vision_base_url: str = os.getenv("VISION_BASE_URL", self.llamacpp_base_url if self.vision_provider == "llamacpp" else "http://localhost:11434")
        self.tile_height: int = int(os.getenv("TILE_HEIGHT", "1568"))  # PixelRAG optimal tile height
        self.attachments_path: Path = (self.obsidian_vault_path / "attachments").resolve()

        # Google Calendar Settings
        self.google_calendar_credentials_path: Path = Path(
            os.getenv("GOOGLE_CALENDAR_CREDENTIALS", "credentials.json")
        ).resolve()
        self.google_calendar_token_path: Path = Path(
            os.getenv("GOOGLE_CALENDAR_TOKEN", "token.json")
        ).resolve()

        # Scraping Settings
        self.playwright_headless: bool = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() in ("true", "1", "yes")
        self.scrape_timeout_ms: int = int(os.getenv("SCRAPE_TIMEOUT_MS", "30000"))

        # Extra kwargs override
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def ensure_directories(self) -> None:
        """Ensure vault directory, attachments folder, and all 20 taxonomy subdirectories exist."""
        self.obsidian_vault_path.mkdir(parents=True, exist_ok=True)
        self.attachments_path.mkdir(parents=True, exist_ok=True)
        for folder in TAXONOMY_FOLDERS:
            folder_path = self.obsidian_vault_path / folder
            folder_path.mkdir(parents=True, exist_ok=True)

    def __str__(self) -> str:
        return (
            f"Settings(vault='{self.obsidian_vault_path}', db='{self.db_path}', "
            f"use_openai={self.use_openai}, model='{self.openai_model if self.use_openai else self.ollama_model}')"
        )

    def __repr__(self) -> str:
        return self.__str__()


# Exact 20 Folder Taxonomy definitions for Knowledge & Jobs
TAXONOMY_FOLDERS: List[str] = [
    "research",
    "agents",
    "workflows",
    "ML",
    "big_data",
    "trading",
    "jobs",
    "ideas",
    "resources",
    "drafts",
    "repositories",
    "tools",
    "rules",
    "policy",
    "cases",
    "issues",
    "literature",
    "hooks",
    "hints",
    "other",
]

TAXONOMY_GUIDE: Dict[str, str] = {
    "research": "Academic papers, scientific studies, deep theoretical analysis, and experimental methodologies.",
    "agents": "Autonomous AI systems, multi-agent frameworks, LLM orchestrators, memory systems, and tool use.",
    "workflows": "Business processes, automation sequences, pipeline architectures, CI/CD, and productivity frameworks.",
    "ML": "Machine learning models, neural networks, computer vision, NLP, fine-tuning, training, and benchmarks.",
    "big_data": "Distributed data processing, Spark, Kafka, data lakes, warehouses, ETL architectures, and analytics.",
    "trading": "Financial algorithms, quantitative analysis, market strategies, crypto, economics, and portfolio management.",
    "jobs": "Job postings, recruitment opportunities, career postings, hiring manager contacts, and vacancy specs.",
    "ideas": "Inventions, product concepts, brainstorming notes, raw startup ideas, and visionary musings.",
    "resources": "Curated lists, cheatsheets, dataset links, public APIs, collections, and educational guides.",
    "drafts": "Incomplete writings, work-in-progress blogs, rough notes, and exploratory sketches.",
    "repositories": "Open source GitHub/GitLab repositories, code libraries, source code implementations, and project releases.",
    "tools": "Developer utilities, software applications, SaaS products, CLI tools, libraries, and desktop apps.",
    "rules": "Coding standards, linting rules, architectural constraints, security guidelines, and protocol specs.",
    "policy": "Legal terms, governance guidelines, AI safety policies, regulatory compliance, and privacy rules.",
    "cases": "Real-world case studies, industry post-mortems, practical incident reviews, and business retrospectives.",
    "issues": "Technical bugs, troubleshooting logs, known CVEs, software defects, workarounds, and GitHub issues.",
    "literature": "Books, essays, long-form journalism, philosophical pieces, and historical reviews.",
    "hooks": "Event triggers, webhooks, integration callbacks, prompt hooks, and signal interception mechanisms.",
    "hints": "Quick tips, shortcuts, performance hacks, hidden features, and micro-optimizations.",
    "other": "Miscellaneous links, failed scrapes, unclassifiable content, login walls, and fallback materials.",
}


settings = Settings()
