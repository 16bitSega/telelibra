# Librarian AI

Personal Intelligence ETL (Extract, Transform, Load) pipeline that monitors your **Telegram "Saved Messages"**, scrapes web sources (X/Twitter, LinkedIn, GitHub, Habr, tech blogs), triages content into **Job Opportunities** or **Knowledge (20 Obsidian folders)** with **Muse-Glimmer-30B** and **PixelRAG Visual Engine**, and generates structured, **NotebookLM-ready Markdown notes** in your Obsidian Vault with **Smart Overwrite** tracking and **Google Calendar** integration.

---

## Key Features

1. **Primary Local AI Engine: Muse-Glimmer-30B**:
   - Dense ~30B parameter model with GQA + sliding-window attention (context up to 131,072+ tokens).
   - Runs natively on **Apple Silicon Metal** via `llama-server` (llama.cpp).
   - Dedicated 24GB Unified Memory tuning with single-slot isolation (`-np 1`) and controllable reasoning effort (`high`).
   - Multimodal vision support via `mmproj-kquant.gguf` projector.
   - High generation throughput via speculative decoding with `dflash-kquant.gguf`.
2. **PixelRAG-Inspired Visual Engine**:
   - Renders dynamic web pages and social posts into **1568px screenshot tiles** via Playwright.
   - Strips DOM clutter (cookie banners, modals, floating popups) prior to capture.
   - Extracts architecture flowcharts, infographics, benchmark charts, and tables straight from images.
   - Saves visual tiles to `vault/attachments/` and embeds them directly in Obsidian notes.
3. **Telegram Ingestion Filter**:
   - Streams Telegram "Saved Messages" using Telethon.
   - Automatically filters for messages containing URLs dated **>= September 1, 2025**.
4. **Smart Overwrite Engine**:
   - Tracks all processed URLs and file paths in SQLite (`processed_links.db`).
   - Detects if notes are moved across folders in Obsidian, updating them in-place instead of creating duplicates like `Title (1).md`.
5. **AI Librarian Triage & Translation**:
   - **Job Branch**: Detects job postings (`linkedin.com/jobs` or hiring text), saves note to `/jobs`, and schedules a review event in **Google Calendar (Tomorrow @ 9:00 AM)**.
   - **Knowledge Branch**: Classifies into exactly one of **20 taxonomy folders**:
     `research`, `agents`, `workflows`, `ML`, `big_data`, `trading`, `jobs`, `ideas`, `resources`, `drafts`, `repositories`, `tools`, `rules`, `policy`, `cases`, `issues`, `literature`, `hooks`, `hints`, `other`.
   - **Russian Translation**: Automatically translates Russian sources (Habr, etc.) to English AI Summaries and English tags.
   - **NotebookLM Metadata**: Injects YAML frontmatter (`url`, `date`, `category`, `type`) with clean markdown formatting.

---

## Quickstart

### 1. Launch Muse-Glimmer-30B Local Server (Mac M5 Pro)

Place model files in `llama/runtime/models/Muse-Glimmer-30B/`:
- `muse-glimmer-30B-kquant-17gb.gguf` (Main model, ~16.8GB)
- `mmproj-kquant.gguf` (Vision projector, ~1.4GB)
- `dflash-kquant.gguf` (Speculative drafter, ~1.6GB)

Launch the server:
```bash
./scripts/run_muse_glimmer.sh
```
The server will start at `http://localhost:8080/v1` with Metal GPU acceleration and 32k context.

### 2. Configure Environment
```bash
cp .env.example .env
```
Fill in your Telegram API credentials (`TELEGRAM_API_ID` & `TELEGRAM_API_HASH` from [my.telegram.org](https://my.telegram.org)).

### 3. Test Local Vision Pipeline
```bash
# Test against a live website or social post
python test_vision_pipeline.py --url "https://news.ycombinator.com" --provider llamacpp --model Muse-Glimmer-30B

# Test single URL execution with visual screenshot tiles
python main.py --url "https://github.com/microsoft/autogen" --visual
```

### 4. Run Full Batch Telegram Stream
```bash
python main.py
```

---

## 20-Folder Taxonomy

| Folder | Definition |
|---|---|
| `research` | Academic papers, scientific studies, theoretical analysis |
| `agents` | Autonomous AI systems, multi-agent frameworks, LLM orchestrators |
| `workflows` | Business processes, automation sequences, pipeline architectures, CI/CD |
| `ML` | Machine learning models, neural networks, fine-tuning, training |
| `big_data` | Distributed data processing, Spark, Kafka, data lakes, ETL |
| `trading` | Financial algorithms, quantitative analysis, crypto, economics |
| `jobs` | Job postings, recruitment opportunities, vacancy specs |
| `ideas` | Inventions, product concepts, brainstorming notes, startup ideas |
| `resources` | Curated lists, cheatsheets, dataset links, public APIs |
| `drafts` | Incomplete writings, work-in-progress blogs, rough notes |
| `repositories` | Open source GitHub/GitLab repositories, code libraries |
| `tools` | Developer utilities, software applications, SaaS products, CLI tools |
| `rules` | Coding standards, linting rules, architectural constraints |
| `policy` | Legal terms, governance guidelines, AI safety policies |
| `cases` | Real-world case studies, industry post-mortems, incident reviews |
| `issues` | Technical bugs, troubleshooting logs, known CVEs, defects |
| `literature` | Books, essays, long-form journalism, philosophical pieces |
| `hooks` | Event triggers, webhooks, integration callbacks, signals |
| `hints` | Quick tips, shortcuts, performance hacks, hidden features |
| `other` | Miscellaneous links, failed scrapes, login walls |
