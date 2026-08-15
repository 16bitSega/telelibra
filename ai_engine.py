"""
AI Librarian Engine for Librarian AI with Multimodal Vision Model Support.
Supports Ollama vision (llama3.2-vision, qwen2.5-vl), local vLLM/SGLang servers, and OpenAI GPT-4o.
Triages into 20-folder taxonomy, extracts visual diagrams/tables, and produces NotebookLM Markdown.
"""

import base64
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Union

import httpx

from config import TAXONOMY_FOLDERS, TAXONOMY_GUIDE, settings
from scraper import ScrapedContent, VisualTile
from utils import log_execution, measure_performance, retry

logger = logging.getLogger("librarian.ai_engine")


class TriageResult:
    """Represents AI analysis and categorization results with visual attachments."""

    def __init__(
        self,
        url: str,
        title: str,
        category: str,
        item_type: str,
        summary: str,
        insights: List[str],
        tags: List[str],
        **kwargs: Any,
    ) -> None:
        self.url: str = url
        self.title: str = title
        self.category: str = category if category in TAXONOMY_FOLDERS else "other"
        self.item_type: str = "job" if item_type.lower() == "job" or category == "jobs" else "knowledge"
        self.summary: str = summary
        self.insights: List[str] = insights
        self.tags: List[str] = tags
        self.code_snippets: List[str] = kwargs.get("code_snippets", [])
        self.original_text: str = kwargs.get("original_text", "")
        self.visual_tiles: List[VisualTile] = kwargs.get("visual_tiles", [])
        self.date_str: str = kwargs.get("date_str", datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def __str__(self) -> str:
        visuals = f", visuals={len(self.visual_tiles)}" if self.visual_tiles else ""
        return f"TriageResult(title='{self.title[:35]}', category='{self.category}', type='{self.item_type}'{visuals})"

    def __repr__(self) -> str:
        return self.__str__()

    def to_notebooklm_markdown(self, relative_attachments_prefix: str = "../attachments", **kwargs: Any) -> str:
        """
        Format the result into NotebookLM-ready Markdown with YAML frontmatter,
        English summary/insights/tags, embedded visual screenshot tiles, and original source text.
        """
        formatted_tags = " ".join(
            f"#{t.lstrip('#').replace(' ', '_').replace('-', '_')}" for t in self.tags if t
        )

        insights_md = "\n".join(f"- {insight}" for insight in self.insights) if self.insights else "- No specific insights extracted."

        code_md = ""
        if self.code_snippets:
            snippets_list = []
            for snippet in self.code_snippets:
                snippets_list.append(f"```\n{snippet.strip()}\n```")
            code_md = "\n\n## Code Snippets\n" + "\n\n".join(snippets_list)

        # Embedded Visual Screenshots
        visual_md = ""
        if self.visual_tiles:
            images_list = []
            for tile in self.visual_tiles:
                # Relative link from vault folder to attachments
                rel_path = f"{relative_attachments_prefix}/{tile.path.name}"
                images_list.append(f"![Visual Snapshot {tile.index + 1}]({rel_path})")
            visual_md = "\n\n## Visual Snapshots\n" + "\n\n".join(images_list)

        markdown = f"""---
url: {self.url}
date: {self.date_str}
category: {self.category}
type: {self.item_type}
---

# {self.title}

## AI Summary
{self.summary}

## Key Insights
{insights_md}{code_md}{visual_md}

## Tags
{formatted_tags}

---
## Original Source
{self.original_text}
"""
        return markdown.strip() + "\n"


class AILibrarian:
    """Multimodal Triage Engine supporting Self-Hosted Vision Models (Ollama, vLLM) & OpenAI."""

    def __init__(self, **kwargs: Any) -> None:
        self.use_openai: bool = kwargs.get("use_openai", settings.use_openai)
        self.openai_key: str = kwargs.get("openai_api_key", settings.openai_api_key)
        self.openai_model: str = kwargs.get("openai_model", settings.openai_model)
        self.ollama_url: str = kwargs.get("ollama_base_url", settings.ollama_base_url)
        self.ollama_model: str = kwargs.get("ollama_model", settings.ollama_model)

        # Vision model properties
        self.vision_enabled: bool = kwargs.get("vision_enabled", settings.vision_enabled)
        self.vision_provider: str = kwargs.get("vision_provider", settings.vision_provider)
        self.vision_model: str = kwargs.get("vision_model", settings.vision_model)
        self.vision_base_url: str = kwargs.get("vision_base_url", settings.vision_base_url)

    def _encode_image_b64(self, image_path: Path) -> Optional[str]:
        """Read image file and return base64 encoded string."""
        if not image_path.exists():
            return None
        try:
            with open(image_path, "rb") as img_f:
                return base64.b64encode(img_f.read()).decode("utf-8")
        except OSError as e:
            logger.warning("Failed to encode image at %s: %s", image_path, e)
            return None

    def _build_system_prompt(self) -> str:
        """Constructs system prompt embedding the exact 20-folder taxonomy guide."""
        taxonomy_lines = [f"- **{folder}**: {desc}" for folder, desc in TAXONOMY_GUIDE.items()]
        taxonomy_block = "\n".join(taxonomy_lines)

        return f"""You are the AI Librarian for a Personal Intelligence ETL pipeline.
Your job is to analyze web content and visual document screenshots, triage into either "Job Opportunity" or "Knowledge", categorize into exactly ONE of the 20 taxonomy folders, and produce a structured analysis.

### FOLDER TAXONOMY (Choose EXACTLY ONE):
{taxonomy_block}

### RULES:
1. **Job Triage**: If the content is from linkedin.com/jobs, is a job posting, recruitment pitch, or vacancy specification, set category to "jobs" and type to "job".
2. **Knowledge Triage**: Otherwise, categorize into the single best matching folder from the 20 taxonomy options above, and set type to "knowledge".
3. **Visual & Multimodal Reasoning**: If screenshot images are provided, carefully examine diagrams, architecture flowcharts, infographics, tables, and UI screenshots. Incorporate visual facts, numbers, and system components into your Summary and Key Insights.
4. **Russian & Foreign Language Translation**: If the source text or images are in Russian or any non-English language (e.g. Habr articles), your AI Summary, Key Insights, and Tags MUST BE TRANSLATED INTO ENGLISH. The Title should also be in English.
5. **Code Snippets**: Extract important code, command-line snippets, or configuration samples into code_snippets.
6. **Output Format**: Respond ONLY with a valid JSON object matching the requested schema. No markdown wrapping around JSON or conversational text.

### JSON Output Schema:
{{
  "title": "Clean descriptive title in English",
  "category": "one_of_the_20_folders",
  "type": "knowledge" | "job",
  "summary": "Concise 2-4 paragraph executive summary in English",
  "insights": ["Key insight 1 in English", "Key insight 2 in English", "Key insight 3 in English"],
  "tags": ["tag1", "tag2", "tag3"],
  "code_snippets": ["code block 1 (optional)"]
}}
"""

    @retry(max_retries=2, backoff=2.0, exceptions=(httpx.HTTPError, OSError))
    def _call_ollama_vision(
        self,
        prompt: str,
        system_prompt: str,
        tiles: List[VisualTile],
        **kwargs: Any,
    ) -> str:
        """Call self-hosted Ollama Vision Model (e.g. llama3.2-vision, qwen2.5-vl)."""
        url = f"{self.vision_base_url.rstrip('/')}/api/generate"
        b64_images = []
        for tile in tiles[:3]:  # Send up to 3 primary tiles
            b64 = self._encode_image_b64(tile.path)
            if b64:
                b64_images.append(b64)

        payload: Dict[str, Any] = {
            "model": self.vision_model,
            "system": system_prompt,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.2},
        }
        if b64_images:
            payload["images"] = b64_images

        with httpx.Client(timeout=120.0) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "")

    @retry(max_retries=2, backoff=2.0, exceptions=(httpx.HTTPError, OSError))
    def _call_openai_vision(
        self,
        prompt: str,
        system_prompt: str,
        tiles: List[VisualTile],
        **kwargs: Any,
    ) -> str:
        """Call OpenAI GPT-4o Vision API."""
        if not self.openai_key:
            raise ValueError("OPENAI_API_KEY is not set but USE_OPENAI=true is configured.")

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.openai_key}",
            "Content-Type": "application/json",
        }

        user_content: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]

        # Add image tiles as base64 data URLs
        for tile in tiles[:3]:
            b64 = self._encode_image_b64(tile.path)
            if b64:
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"},
                })

        payload = {
            "model": self.openai_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }
        with httpx.Client(timeout=90.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    @retry(max_retries=2, backoff=2.0, exceptions=(httpx.HTTPError, OSError))
    def _call_vllm_vision(
        self,
        prompt: str,
        system_prompt: str,
        tiles: List[VisualTile],
        **kwargs: Any,
    ) -> str:
        """Call self-hosted OpenAI-compatible local Vision endpoint (vLLM / SGLang)."""
        url = f"{self.vision_base_url.rstrip('/')}/chat/completions"
        user_content: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]

        for tile in tiles[:3]:
            b64 = self._encode_image_b64(tile.path)
            if b64:
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                })

        payload = {
            "model": self.vision_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.2,
        }
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    def _parse_llm_json(self, raw_response: str) -> Dict[str, Any]:
        """Safely parse JSON response from LLM."""
        cleaned = raw_response.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.warning("JSON decode warning: %s. Output snippet: %s", e, raw_response[:200])
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
            return {}

    @measure_performance
    def process_content(
        self,
        scraped: ScrapedContent,
        date_str: Optional[str] = None,
        **kwargs: Any,
    ) -> TriageResult:
        """
        Process scraped document through Multimodal AI Librarian pipeline.
        Utilizes visual screenshot tiles when available.
        """
        curr_date = date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Guardrail: Handle failed scrapes if no text and no visual tiles exist
        if scraped.failed_scrape and not scraped.has_visuals:
            logger.info("Content flagged as failed scrape: %s", scraped.failure_reason)
            return TriageResult(
                url=scraped.url,
                title=f"Failed Scrape - {scraped.title}",
                category="other",
                item_type="knowledge",
                summary=f"Automated scraping could not extract clean content. Reason: {scraped.failure_reason or 'Short text / login wall'}.",
                insights=["Manual inspection required at source URL.", "Scraper flagged login wall or insufficient text."],
                tags=["failed_scrape", "manual_review"],
                original_text=scraped.text,
                date_str=curr_date,
            )

        if "linkedin.com/jobs" in scraped.url:
            preset_category = "jobs"
            preset_type = "job"
        else:
            preset_category = None
            preset_type = None

        system_prompt = self._build_system_prompt()
        visual_notice = f"\nAttached Visual Screenshot Tiles: {len(scraped.visual_tiles)} image(s)." if scraped.has_visuals else ""
        
        user_prompt = f"""URL: {scraped.url}
Source Type: {scraped.source_type}
Title: {scraped.title}{visual_notice}

CONTENT TO ANALYZE:
{scraped.text[:10000] if scraped.text else "[Visual Document - See attached screenshot tiles]"}
"""

        raw_llm_output = ""
        try:
            # Route based on provider preference & visual availability
            if self.use_openai and self.openai_key:
                logger.info("Processing with OpenAI (%s, visuals=%s) for %s", self.openai_model, scraped.has_visuals, scraped.url)
                raw_llm_output = self._call_openai_vision(user_prompt, system_prompt, scraped.visual_tiles, **kwargs)
            elif self.vision_provider == "vllm":
                logger.info("Processing with local vLLM endpoint (%s) for %s", self.vision_model, scraped.url)
                raw_llm_output = self._call_vllm_vision(user_prompt, system_prompt, scraped.visual_tiles, **kwargs)
            else:
                # Default: Ollama (vision-enabled if tiles exist)
                logger.info("Processing with Ollama (%s, visuals=%s) for %s", self.vision_model if scraped.has_visuals else self.ollama_model, scraped.has_visuals, scraped.url)
                raw_llm_output = self._call_ollama_vision(user_prompt, system_prompt, scraped.visual_tiles, **kwargs)
        except Exception as e:
            logger.error("LLM processing encountered error: %s. Falling back to default triage.", e)

        parsed = self._parse_llm_json(raw_llm_output) if raw_llm_output else {}

        category = preset_category or parsed.get("category", "other")
        if category not in TAXONOMY_FOLDERS:
            category = "other"

        item_type = preset_type or parsed.get("type", "job" if category == "jobs" else "knowledge")
        title = parsed.get("title") or scraped.title or "Untitled Document"
        summary = parsed.get("summary") or "Summary generated from visual analysis."
        insights = parsed.get("insights") or []
        tags = parsed.get("tags") or [category]
        code_snippets = parsed.get("code_snippets") or []

        return TriageResult(
            url=scraped.url,
            title=title,
            category=category,
            item_type=item_type,
            summary=summary,
            insights=insights,
            tags=tags,
            code_snippets=code_snippets,
            original_text=scraped.text,
            visual_tiles=scraped.visual_tiles,
            date_str=curr_date,
        )


ai_librarian = AILibrarian()
