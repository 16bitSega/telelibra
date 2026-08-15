"""
Standalone testing utility for Self-Hosted Vision Models and PixelRAG Visual Pipelines.
Allows testing Ollama (llama3.2-vision, qwen2.5-vl), vLLM, or OpenAI directly against any URL or image.

Usage:
    # Test local Ollama vision model with a live URL:
    python test_vision_pipeline.py --url "https://news.ycombinator.com" --provider ollama --model llama3.2-vision

    # Test with custom self-hosted vLLM vision server:
    python test_vision_pipeline.py --url "https://arxiv.org/abs/2404.12387" --provider vllm --base-url "http://localhost:8000/v1" --model "Qwen/Qwen2.5-VL-7B-Instruct"

    # Test against an existing local screenshot or diagram:
    python test_vision_pipeline.py --image "vault/attachments/sample.jpg" --provider ollama --model llama3.2-vision
"""

import argparse
import logging
from pathlib import Path
import sys

from ai_engine import AILibrarian
from config import settings
from scraper import ScrapedContent, VisualTile, scraper_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_vision")


def main() -> None:
    parser = argparse.ArgumentParser(description="Test Self-Hosted Vision Models with Librarian AI / PixelRAG")
    parser.add_argument("--url", type=str, help="Web URL to screenshot and visually analyze")
    parser.add_argument("--image", type=str, help="Path to local image/diagram to test directly")
    parser.add_argument(
        "--provider",
        type=str,
        default="llamacpp",
        choices=["llamacpp", "ollama", "vllm", "openai"],
        help="Vision provider (default: llamacpp for Muse-Glimmer-30B)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="Muse-Glimmer-30B",
        help="Model name (e.g. Muse-Glimmer-30B, llama3.2-vision, qwen2.5-vl, gpt-4o)",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default="http://localhost:8080/v1",
        help="Base URL for llama.cpp, Ollama, or vLLM endpoint",
    )
    args = parser.parse_args()

    if not args.url and not args.image:
        print("Please specify either --url or --image to test. Use --help for options.")
        sys.exit(1)

    logger.info("Initializing Vision Librarian (Provider=%s, Model=%s, Endpoint=%s)", args.provider, args.model, args.base_url)
    
    librarian = AILibrarian(
        vision_enabled=True,
        vision_provider=args.provider,
        vision_model=args.model,
        vision_base_url=args.base_url,
        use_openai=(args.provider == "openai"),
    )

    visual_tiles = []
    page_title = "Local Test Image"
    text_content = ""
    target_url = args.url or f"file://{args.image}"

    if args.url:
        logger.info("Capturing screenshot tiles from %s using Playwright...", args.url)
        title, text, tiles, is_failed, reason = scraper_engine.capture_screenshot_tiles(
            url=args.url,
            force_visual=True,
        )
        page_title = title
        text_content = text
        visual_tiles = tiles
        logger.info("Captured %d visual tile(s). Title: '%s'", len(visual_tiles), page_title)
        for tile in visual_tiles:
            logger.info("  Tile %d: %s (%dx%d)", tile.index, tile.path, tile.width, tile.height)
    elif args.image:
        img_path = Path(args.image).resolve()
        if not img_path.exists():
            logger.error("Image file not found: %s", img_path)
            sys.exit(1)
        visual_tiles = [VisualTile(path=img_path, index=0, width=1280, height=800)]

    scraped = ScrapedContent(
        url=target_url,
        title=page_title,
        text=text_content,
        source_type="web",
        visual_tiles=visual_tiles,
    )

    logger.info("Sending visual tiles to Vision Model (%s)...", args.model)
    triage = librarian.process_content(scraped)

    print("\n" + "=" * 60)
    print(f"📊 VISION TRIAGE RESULT:")
    print(f"Title:    {triage.title}")
    print(f"Category: {triage.category}")
    print(f"Type:     {triage.item_type}")
    print(f"Tags:     {triage.tags}")
    print("\n📝 AI SUMMARY (from visual analysis):")
    print(triage.summary)
    print("\n💡 KEY INSIGHTS:")
    for insight in triage.insights:
        print(f"  - {insight}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
