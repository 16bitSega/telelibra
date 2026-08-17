# Telelibra — Personal Intelligence ETL Pipeline 

**Telelibra** is an autonomous Personal Intelligence ETL (Extract, Transform, Load) pipeline designed for continuous knowledge synthesis and personal intelligence management.

It ingests your **Telegram "Saved Messages"**, scrapes multi-platform web sources (**YouTube Speech-to-Text Transcripts, ArXiv Papers, X/Twitter, LinkedIn, GitHub, Habr, Technical Blogs**), cleans audio and advertising noise, deeply analyzes content via local or cloud LLMs (**Muse-Glimmer-30B on Apple Silicon Metal**, OpenAI GPT-4o, or Ollama), automatically categorizes notes into an **Obsidian 20-Folder Knowledge Taxonomy**, prevents duplicate notes via **Smart Overwrite**, and generates a unified **Google NotebookLM Master Compendium** for audio deep dives, podcasts, and cross-document reasoning.

---

## 🏛️ System Architecture & Workflow

```mermaid
flowchart TD
    TG[Telegram Saved Messages >= Cutoff Date] -->|Telethon Stream| Runner[run_timed_session.py: Timed Session Runner]
    
    Runner --> Checkpoint{Checkpoints DB: URL Already Processed?}
    Checkpoint -->|Yes & Note on Disk| Skip[⏩ Fast Skip: 0.0001s / 0 Tokens Wasted]
    
    Checkpoint -->|No / Reprocess| Scraper[scraper.py: Multi-Source Scraper Engine]
    
    Scraper -->|YouTube / Podcast| YTExtract[youtube-transcript-api + oEmbed: Full Spoken Transcript]
    Scraper -->|ArXiv Research| ArXivExtract[ArXiv API: XML Abstract & Authors]
    Scraper -->|GitHub Repos| GHExtract[Raw README.md Extraction]
    Scraper -->|LinkedIn / X / Web| PWExtract[Thread-Isolated Playwright + PixelRAG Tiles]
    
    YTExtract --> Cleaner[utils.py: Audio Noise & Promo Fluff Cleaner]
    ArXivExtract --> Cleaner
    GHExtract --> Cleaner
    PWExtract --> Cleaner
    
    Cleaner -->|Strips [music], [snorts], stutters & ads| AIEngine[ai_engine.py: AI Librarian Triage]
    
    AIEngine -->|Primary Provider| LocalMetal[run_llm_server.sh: Muse-Glimmer-30B on Metal]
    AIEngine -.->|Fallback Chain| CloudOpenAI[OpenAI GPT-4o]
    AIEngine -.->|Fallback Chain| LocalOllama[Ollama llama3:8b]
    
    LocalMetal --> TriageResult[Structured JSON: Title, Category, Summary, Insights, Tags]
    
    TriageResult --> SmartOverwrite{database.py: Smart Overwrite Engine}
    SmartOverwrite -->|Relocate / Update in-place| Vault[vault/: 20-Folder Knowledge Taxonomy]
    
    Vault --> Organizer[vault_organizer.py: Knowledge Compendium Generator]
    Organizer --> NotebookLM[vault/NOTEBOOKLM_KNOWLEDGE_BASE.md: Ready for Google NotebookLM]
```

---

## ⚡ Key Capabilities

1. **🎙️ Complete YouTube & Podcast Audio Speech-to-Text**:
   - Fetches complete spoken transcripts (up to 70,000+ characters) across English, Ukrainian, Russian, and all languages.
   - Cleans acoustic noise tags (`[music]`, `[applause]`, `[snorts]`, `[coughing]`, speaker arrows `>>`) and stutters.
   - Strips channel sponsorship plugs, like/subscribe prompts, and Telegram bot advertising.

2. **🧠 High-Performance Local LLM on Apple Silicon Metal**:
   - Runs `Muse-Glimmer-30B` locally with 16k context window, **Q8_0 KV Cache** (50% VRAM savings), and reasoning preservation.
   - Fits comfortably into **24GB Unified Memory** (utilizing ~18.2 GB, leaving ample headroom for macOS).
   - Supports **Speculative Decoding (`dflash-kquant.gguf`)** for 2x–2.5x generation speedup.

3. **📂 20-Folder Obsidian Knowledge Taxonomy**:
   - Classifies notes into:
     `/agents`, `/ML`, `/workflows`, `/cases`, `/research`, `/tools`, `/trading`, `/hints`, `/literature`, `/repositories`, `/issues`, `/jobs`, `/ideas`, `/resources`, `/drafts`, `/rules`, `/policy`, `/big_data`, `/hooks`, `/other`.
   - **Smart Overwrite Engine**: If you move a note to a different folder in Obsidian, the system automatically detects its new location and updates it in-place without generating duplicates like `Note (1).md`.

4. **📚 Google NotebookLM Master Compendium (`NOTEBOOKLM_KNOWLEDGE_BASE.md`)**:
   - Automatically aggregates all vault notes into a structured, high-density Knowledge Pack.
   - Includes executive tables of contents, chapter overviews, synthesized summaries, actionable insights, and source excerpts ready for direct upload into **Google NotebookLM** for generating **two-host audio podcasts** and cross-document Q&A.

5. **⏱️ Timed Sessions with SQLite State Checkpointing**:
   - Run batch sessions in 15-minute, 60-minute, or custom intervals with real-time countdown progress.
   - State is saved per-URL in SQLite (`processed_links.db`). Graceful `Ctrl+C` interrupt handling ensures you never lose progress.

---

## 📋 System Requirements

### Hardware:
* **Recommended**: Mac with Apple Silicon (**M1 / M2 / M3 / M4 / M5 Pro/Max**) with **24GB+ Unified Memory**.
* **Alternative**: Any Mac / Linux / Windows system with OpenAI API key (`USE_OPENAI=true`) or local Ollama.

### Software:
* **Python 3.10+** (tested on Python 3.11).
* **llama.cpp** (Homebrew build 10450+ or compiled from source with Metal).
* **Playwright Chromium** for authenticated social and web rendering.

---

## 🚀 Installation & Setup

### 1. Clone the Repository & Create Virtual Environment
```bash
git clone https://github.com/16bitSega/telelibra.git
cd telelibra

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Install Playwright Browsers
```bash
playwright install chromium
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Edit `.env` and fill in your parameters:
```ini
# Telegram Credentials (get from https://my.telegram.org)
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=your_telegram_api_hash_here
TELEGRAM_PHONE=+380XXXXXXXXX
TELEGRAM_SESSION_NAME=librarian_telegram

# LLM Provider (llamacpp, openai, or ollama)
LLM_PROVIDER=llamacpp
LLAMACPP_BASE_URL=http://localhost:8080/v1
LLAMACPP_MODEL_NAME=Muse-Glimmer-30B
```

### 4. (Optional) Configure Social Cookies (`cookies.json`)
To scrape private LinkedIn connections or protected X/Twitter posts:
```bash
cp cookies.example.json cookies.json
```
Fill in your session cookies (`li_at` for LinkedIn, `auth_token` for X).

---

## 🛠️ Operating Workflows & Commands

### Workflow 1: Launch Local LLM Server (Metal)

In a dedicated terminal tab, start the optimized Metal server:
```bash
./run_llm_server.sh
```

*(Optional: to enable speculative decoding for ~2x faster token generation)*:
```bash
ENABLE_DFLASH=true ./run_llm_server.sh
```

---

### Workflow 2: Run Timed Ingestion Session

#### A. Standard Ingestion (Ingest from Today back to September 1, 2025):
```bash
python run_timed_session.py --since 2025-09-01 --duration-minutes 60
```

#### B. Reprocess & Enrich Incomplete Notes:
Scans notes in `vault/other/` or failed stubs, extracts full YouTube transcripts, runs them through the LLM, and relocates them to their proper taxonomy folders:
```bash
python run_timed_session.py --reprocess-failed
```

#### C. Force Reprocess All Messages:
```bash
python run_timed_session.py --since 2025-09-01 --reprocess --duration-minutes 60
```

---

### Workflow 3: Reorganize Vault & Generate NotebookLM Compendium

To reorganize any unsorted notes across the 20 folders, synchronize the SQLite database, and generate the Master NotebookLM document:
```bash
python vault_organizer.py
```

Output:
* **`vault/NOTEBOOKLM_KNOWLEDGE_BASE.md`** — Ready to drag-and-drop directly into Google NotebookLM!

---

## 📁 Taxonomy Guide (20 Obsidian Folders)

| Folder | Name / Domain | Description & Content Type |
|---|---|---|
| `/agents` | **AI Agents & Multi-Agent Systems** | LangGraph, CrewAI, AutoGen, AgentMemory, Roo Code, Claude Code subagents. |
| `/ML` | **Machine Learning & LLM Core** | Quantization (GGUF, AWQ), model architectures, RAG libraries, fine-tuning, embeddings. |
| `/workflows` | **Quality Engineering & Pipelines** | AI test automation, testing pyramids, CI/CD pipelines, Git commit best practices. |
| `/cases` | **Enterprise AI Case Studies** | Real-world industry implementations (Netflix AI Engineering, Silpo AI Factory, Svoi.ru). |
| `/research` | **Academic & Scientific Papers** | ArXiv research, empirical benchmarks, frontier model studies, methodology analyses. |
| `/tools` | **Developer Tooling & Utilities** | VS Code extensions, TOON format, desktop utilities, image/video AI tools. |
| `/trading` | **Financial Markets & Trading** | Futures trading, Smart Money Concepts, Order Blocks, Bybit, Prop firm analysis. |
| `/hints` | **Technical Cheat Sheets & Tips** | SQL & PostgreSQL recipes, database optimizations, QA interview question banks. |
| `/literature` | **Tutorials, Books & Courses** | 30 Days of Python, programming textbooks, EPAM testing courses, comprehensive guides. |
| `/repositories` | **Open-Source Codebases** | Curated GitHub repositories, frameworks, and reference implementations. |
| `/issues` | **Security Research & Bug Bounty** | Penetration testing, vulnerability analyses, exploit write-ups, security audits. |
| `/jobs` | **Career & Job Opportunities** | Vacancy specifications, hiring pitches, compensation packages, role requirements. |
| `/ideas` | **Product & Startup Concepts** | AI business ideas, product architectures, hackathon proposals. |
| `/resources` | **External Platforms & Portals** | Developer portals, documentation hubs, reference sites. |
| `/drafts` | **WIP Notes & Sketches** | Incomplete thoughts, early draft notes. |
| `/rules` | **Engineering Standards & Lints** | Style guides, coding conventions, architectural invariants. |
| `/policy` | **Governance & Compliance** | Data protection policies, security guidelines, terms of service. |
| `/big_data` | **Data Engineering & Big Data** | Spark, Kafka, ETL pipelines, large-scale data warehouses. |
| `/hooks` | **Event Triggers & Webhooks** | System webhooks, automation triggers, event listeners. |
| `/other` | **Miscellaneous Notes** | General knowledge items not fitting other specific categories. |

---

## 🧪 Testing & Quality Assurance

Run the comprehensive test suite with `pytest`:
```bash
pytest -v
```

**Test Coverage**:
* `test_youtube_and_arxiv_scrapers.py`: Validates speech-to-text transcript fetching, audio cleaning, and ArXiv XML parsing.
* `test_timed_session.py`: Validates SQLite checkpointing, skip logic, and session summaries.
* `test_database.py`: Validates CRUD operations, Smart Overwrite, and vault path resolution.
* `test_ai_engine.py`: Validates JSON schema formatting, taxonomy routing, and fallback chains.
* `test_scraper.py`: Validates PixelRAG visual screenshot tiling, DOM clutter stripping, and anti-login wall checks.
* `test_utils.py`: Validates acoustic noise cleaning, promo filtering, and sanitized cross-platform filenames.

---

## 🔒 Privacy & Security

* **100% Local Inference**: When using `Muse-Glimmer-30B` on Metal, no text, transcripts, or personal messages leave your machine.
* **Credentials Protection**: All `.env` files, `.session` tokens, and `cookies.json` are excluded from version control via `.gitignore`.

---

## 📄 License
MIT License. Created for autonomous Personal Intelligence Engineering.
