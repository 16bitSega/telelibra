# Librarian AI 📚🧠

Personal Intelligence ETL (Extract, Transform, Load) pipeline that monitors your **Telegram "Saved Messages"**, scrapes web sources (X/Twitter, LinkedIn, GitHub, Habr, tech blogs), triages content into **Job Opportunities** or **Knowledge (20 Obsidian folders)**, and generates structured, **NotebookLM-ready Markdown notes** in your Obsidian Vault with **Smart Overwrite** tracking and **Google Calendar** integration.

---

## Key Features

1. **Telegram Ingestion Filter**:
   - Streams Telegram "Saved Messages" using Telethon.
   - Automatically filters for messages containing URLs dated **>= September 1, 2025**.
2. **Smart Overwrite Engine**:
   - Tracks all processed URLs and their file paths in SQLite (`processed_links.db`).
   - If you move a file into a different Obsidian subfolder (e.g. from `/drafts` to `/agents`), Librarian AI detects the new location via frontmatter scanning and updates the existing note in-place instead of creating duplicates like `Title (1).md`.
3. **Multi-Source Scraping**:
   - **X.com / LinkedIn**: Automated Playwright scraper with cookie injection (`cookies.json`) and double-scroll to capture full threads and dynamic replies without context loss.
   - **GitHub**: Automatically converts repository links to raw `README.md` content via `raw.githubusercontent.com`.
   - **Technical Articles & Habr**: Clean HTML parsing and text extraction via Trafilatura.
   - **Integrity Guardrail**: Detects login walls and text < 200 characters, tagging them with `#failed_scrape` and routing to the `other` folder without polluting summaries.
4. **AI Librarian Triage**:
   - **Job Branch**: Detects job postings (`linkedin.com/jobs` or hiring text), saves note to `/jobs`, and schedules a review event in **Google Calendar (Tomorrow @ 9:00 AM)**.
   - **Knowledge Branch**: Classifies into exactly one of **20 taxonomy folders**:
     `research`, `agents`, `workflows`, `ML`, `big_data`, `trading`, `jobs`, `ideas`, `resources`, `drafts`, `repositories`, `tools`, `rules`, `policy`, `cases`, `issues`, `literature`, `hooks`, `hints`, `other`.
   - **Russian Translation**: Automatically translates Russian sources (Habr, etc.) to English AI Summaries and English tags.
   - **NotebookLM Metadata**: Injects YAML frontmatter (`url`, `date`, `category`, `type`) with clean markdown formatting.
5. **Local / Cloud AI Toggle**:
   - Defaults to local **Ollama** (`http://localhost:11434` with `llama3:8b` or `mistral`).
   - Switchable to OpenAI **GPT-4o** via `USE_OPENAI=true` in `.env`.

---

## Project Structure

```
/telelibra
├── main.py              # Batch trigger & Telegram stream orchestrator
├── database.py          # SQLite persistence & Smart Overwrite vault relocation
├── scraper.py           # Playwright/Trafilatura logic & integrity checks
├── ai_engine.py         # Prompt engineering, LLM routing & NotebookLM generator
├── calendar_util.py     # Google Calendar OAuth & Event creation (Tomorrow @ 9 AM)
├── config.py            # .env management & 20-Folder Taxonomy definitions
├── utils.py             # Decorators (@measure_performance, @retry), helpers
├── cookies.json         # Browser cookies for authenticated X / LinkedIn scraping
├── Dockerfile           # Playwright-heavy Docker container
├── docker-compose.yml   # Volume mapping for Obsidian Vault & Ollama gateway
├── requirements.txt     # Python dependencies
├── pyproject.toml       # Project metadata & test configs
└── .env.example         # Template environment configuration
```

---

## Quickstart

### 1. Setup Environment
Copy the `.env.example` file to `.env` and fill in your Telegram API credentials:
```bash
cp .env.example .env
```
Get Telegram credentials (`TELEGRAM_API_ID` & `TELEGRAM_API_HASH`) from [my.telegram.org](https://my.telegram.org).

### 2. Configure Cookies for X.com / LinkedIn (Optional)
Populate `cookies.json` with valid cookies for X.com and LinkedIn to scrape authenticated content and private posts.

### 3. Run Locally

Install dependencies and Playwright browser:
```bash
pip install -r requirements.txt
playwright install chromium
```

Test a single URL directly:
```bash
python main.py --url "https://github.com/microsoft/autogen"
```

Run full Telegram batch scan from September 1, 2025:
```bash
python main.py
```

### 4. Run with Docker Compose

Ensure Ollama is running on your host machine, then launch the container:
```bash
docker-compose up --build
```
Your notes will automatically appear in your local `./vault` directory, categorized across the 20 taxonomy folders.

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
