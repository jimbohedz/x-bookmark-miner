#!/usr/bin/env python3
"""
x-bookmark-miner — X Bookmarks Scraper
----------------------------------------
Turns your X/Twitter bookmarks into a searchable Markdown knowledge base.
Self-healing GraphQL API: auto-discovers rotating query IDs from X's JS bundles.
No official API key needed. Your cookies never leave your machine.

USAGE:
  python bookmark_scraper.py                   -- scrape / resume (adds new bookmarks)
  python bookmark_scraper.py --reset           -- wipe progress, start fresh
  python bookmark_scraper.py --rebuild         -- rebuild markdown from saved data (instant)
  python bookmark_scraper.py --fix-unsure      -- re-categorize low-confidence entries via Gemini
  python bookmark_scraper.py --rescrape-articles  -- re-fetch articles that returned empty
  python bookmark_scraper.py --rescrape-replies   -- backfill author thread replies
  python bookmark_scraper.py --transcribe-videos  -- transcribe X native videos (GPU or CPU)
  python bookmark_scraper.py --vision             -- analyze images via local Ollama vision model
  python bookmark_scraper.py --search "query"     -- semantic search bookmarks by meaning
  python bookmark_scraper.py --raw                -- output bookmarks_raw.md (uncategorized,
                                                     no AI key needed — feed to your Claude/Codex
                                                     for personalized categorization)
  python bookmark_scraper.py --schedule [HH:MM]  -- install daily morning run (default 10:00)
  python bookmark_scraper.py --unschedule         -- remove the daily schedule
  python bookmark_scraper.py --schedule-status    -- show next scheduled run time

  Add --gemini to any command to enable Gemini AI categorization:
    python bookmark_scraper.py --gemini
    python bookmark_scraper.py --rebuild --gemini

  Add --debug for verbose output:
    python bookmark_scraper.py --debug

SETUP:
  1. Copy config.example.yaml to config.yaml and edit it.
  2. Export your X cookies to the path set in config.yaml (default: xcookies.json).
  3. pip install requests   (or: pip install -r requirements.txt -- same thing)
  4. python bookmark_scraper.py
"""

import html
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests

# ─────────────────────────────────────────
#  DEBUG
# ─────────────────────────────────────────
DEBUG = "--debug" in sys.argv


def dbg(label: str, value=None):
    if not DEBUG:
        return
    if value is None:
        print(f"  [DBG] {label}")
    elif isinstance(value, (dict, list)):
        print(f"  [DBG] {label}: {str(value)[:300]}")
    else:
        print(f"  [DBG] {label}: {value}")


# ─────────────────────────────────────────
#  CONFIG LOADER
# ─────────────────────────────────────────
BASE_DIR = Path(__file__).parent


def _load_config() -> dict:
    """Load config.yaml if present, otherwise fall back to safe defaults."""
    defaults = {
        "cookies_path": str(BASE_DIR / "xcookies.json"),
        "output_path": str(BASE_DIR / "bookmarks_output.md"),
        "progress_path": str(BASE_DIR / "bookmarks_progress.json"),
        "categories": None,          # None = use built-in defaults
        "gemini_model": "gemini-2.0-flash",
        "whisper_model": "medium",
        "whisper_device": "auto",    # "auto" | "cuda" | "cpu"
        "ollama_url": "http://localhost:11434",
        "vision_model": "gemma3:12b",
        "delay_seconds": 1.5,
        "max_bookmarks": 9999,
    }
    cfg_path = BASE_DIR / "config.yaml"
    if cfg_path.exists():
        try:
            import yaml  # type: ignore
            with open(cfg_path, encoding="utf-8") as f:
                user_cfg = yaml.safe_load(f) or {}
            defaults.update({k: v for k, v in user_cfg.items() if v is not None})
        except ImportError:
            # pyyaml not installed — silently use defaults
            pass
        except Exception as e:
            print(f"[warn] Could not parse config.yaml: {e} — using defaults")
    return defaults


def _load_env() -> None:
    """Load KEY=value pairs from .env.local or .env (optional)."""
    for env_file in (BASE_DIR / ".env.local", BASE_DIR / ".env"):
        if not env_file.exists():
            continue
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip().lstrip("﻿")
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_env()
CONFIG = _load_config()

COOKIES_JSON     = Path(CONFIG["cookies_path"])
OUTPUT_MD        = Path(CONFIG["output_path"])
PROGRESS_FILE    = Path(CONFIG["progress_path"])
GEMINI_API_KEY   = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL     = CONFIG["gemini_model"]
OLLAMA_URL       = CONFIG["ollama_url"]
VISION_MODEL     = CONFIG["vision_model"]
DELAY_S          = float(CONFIG["delay_seconds"])
MAX_BOOKMARKS    = int(CONFIG["max_bookmarks"])
PER_PAGE         = 20

# ─────────────────────────────────────────
#  X API CONSTANTS (public — not secrets)
# ─────────────────────────────────────────
# X's public app bearer token — same for all web clients, embedded in their JS bundles.
# This is NOT your personal API key.
BEARER = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D"
    "1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)

# Known Bookmarks GraphQL query IDs — script auto-discovers current ones from X's JS.
# Add new ones here if auto-discovery ever fails.
KNOWN_QUERY_IDS = [
    "toTC7lB_mQm5fuBE5yyEJw",
    "tmd9HkBBPHNMU3m2pnuMRQ",
    "VeblqmzONFRBHt7SB0bFxg",
    "E70IMNnX_DlnFP78Xnlp3w",
    "HuqiGvnFp25HF3-r3JnnEw",
    "v1p8N-sLkVuNgB4pHoNVlw",
]

KNOWN_TWEETDETAIL_IDS = [
    "nBS-WpgA6ZG0CyNHD517JQ",
    "B9_KmbkLhXt6jRwGjJrweg",
    "xOhkmRac04YFZmOzU9PJHg",
    "BbCrSoXIR7z93lLCVFlTQQ",
]

FEATURES = {
    "rweb_video_screen_enabled": False,
    "profile_label_improvements_pcf_label_in_post_enabled": True,
    "responsive_web_profile_redirect_enabled": False,
    "rweb_tipjar_consumption_enabled": False,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "premium_content_api_read_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
    "responsive_web_grok_analyze_post_followups_enabled": True,
    "responsive_web_jetfuel_frame": True,
    "responsive_web_grok_share_attachment_enabled": True,
    "responsive_web_grok_annotations_enabled": True,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "tweet_awards_web_tipping_enabled": False,
    "responsive_web_grok_show_grok_translated_post": False,
    "responsive_web_grok_analysis_button_from_backend": True,
    "post_ctas_fetch_enabled": True,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_grok_image_annotation_enabled": True,
    "responsive_web_grok_imagine_annotation_enabled": True,
    "responsive_web_grok_community_note_auto_translation_is_enabled": False,
    "responsive_web_enhance_cards_enabled": False,
}

# ─────────────────────────────────────────
#  CATEGORIES
# ─────────────────────────────────────────
_DEFAULT_CATEGORIES = {
    "AI Tools & Prompts": [
        "chatgpt", "gpt-4", "gpt4", "openai", "claude", "anthropic",
        "prompt engineer", "prompt tip", " llm ", "midjourney",
        "stable diffusion", "copilot", "gemini", "perplexity",
        "ai agent", "n8n ", "make.com", "zapier", "langchain",
        "cursor ", "ai tool", "text to image", "text to video",
        "suno", "udio", "elevenlabs", "luma", "runway", "kling",
        " veo ", " grok ", "deepseek", "system prompt", "few-shot",
        " rag ", "fine-tun", "artificial intelligence", "automation tool",
        "ai workflow", "agentic", "mcp ", "function calling",
        "image prompt", "image generat", "hailuo",
        "token efficiency", "context window", "claude code",
    ],
    "Trading/Crypto": [
        "trade ", "trading", "crypto ", "bitcoin", " btc", " eth ",
        "ethereum", "altcoin", "chart ", "technical analysis", " ta ",
        " dex ", " cex ", "futures", "leverage", "long ", "short ",
        " pnl", "memecoin", "pump ", "whale ", "market cap",
        "bullish", "bearish", "entry ", "stop loss", "breakout",
        "support level", "resistance", "coinbase", "binance", "bybit",
        "kucoin", "degen", "ape in", "moonshot", "snipe", "copy trade",
        "yield", "airdrop", "presale", "ido ", "gem ", "100x", "alpha call",
    ],
    "Content Creation": [
        "tiktok", "content creat", "viral", "creator economy", "video edit",
        "youtube", "instagram", "reels", "trending", "hook ", "caption",
        "growth hack", "followers", "engagement", "views", "posting",
        "faceless", "monetize content", "ugc", "shorts", "scriptwriting",
        "storytelling", "thumbnail", "algorithm", "niche", "audience",
        "personal brand", "influencer", "social media", "content strategy",
        "repurpose", "carousel",
    ],
    "Dev/Automation": [
        "api key", "api call", " bot ", "webhook", "telegram bot",
        "discord bot", " script", "automat", "github.com", "deploy",
        " server", "sniper bot", "token tracker", "monitor",
        "listener", "rpc call", "endpoint", "rate limit", " python ",
        "node.js", "fastapi", "flask ", "express ", "cron job",
        "scheduler", ".env", "docker", "environment variable",
        "rest api", "async ", "event listener", "polling",
    ],
    "Web3/Blockchain Dev": [
        "solana", " sol ", "anchor ", "rust ", "smart contract", " nft",
        "defi ", "web3", "phantom wallet", "metamask", "onchain",
        "blockchain dev", " dapp", "raydium", "jupiter agg", "jito",
        "helius", " rpc ", "program id", " pda ", "spl token",
        "mint address", "abi ", "ethers.js", "web3.js", "hardhat",
        "foundry", "remix ide", "solidity", "move lang", "pump.fun",
        "base chain", "evm ", "layer 2", " l2 ",
    ],
    "Mindset": [
        "mindset", "limiting belief", "belief system", "subconscious",
        "manifestation", "affirmation", "nlp ", "hypnos", "theta wave",
        "visualiz", "neuroplast", "reprogram", "law of attract",
        "self-image", "inner voice", "identity shift", "belief change",
        "discipline", "mental model", "stoic", "psychology", "brainwash",
        "self-help", "self-improv", "self-develop", "personal growth",
        "abundance mindset", "growth mindset", "confidence", "mindful",
        "meditat", "unlearn", "neural pathway", "subliminal", "rewire",
    ],
    "Money/Finance": [
        "passive income", "side hustle", "income stream", "make money",
        "how to get rich", "financial freedom", "financial independ",
        "net worth", "wealth build", "personal finance", "budget",
        "saving", "invest", "millionaire", "rich ", "get rich",
        "$0 to ", "per month", "revenue", "profit", "roi ",
        "business model", "agency ", "client", "freelanc",
        "upwork", "fiverr", "consulting", "productiz", "cash flow",
        "money online", "online business", "digital product",
        "course ", "coaching", "sell ", "selling ", "sales ",
    ],
}


def _resolve_categories() -> dict:
    """Return user-defined categories from config, or built-in defaults."""
    user_cats = CONFIG.get("categories")
    if user_cats and isinstance(user_cats, dict):
        return user_cats
    # Try loading from categories.json next to script
    cats_json = BASE_DIR / "categories.json"
    if cats_json.exists():
        try:
            with open(cats_json, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[warn] Could not load categories.json: {e} — using defaults")
    return _DEFAULT_CATEGORIES


CATEGORIES = _resolve_categories()
ALL_CATS = list(CATEGORIES.keys()) + ["Other"]


# ─────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────
def categorize(text: str) -> tuple:
    t = text.lower()
    scores = {c: 0 for c in CATEGORIES}
    for cat, kws in CATEGORIES.items():
        for kw in kws:
            if kw in t:
                scores[cat] += 1
    best = max(scores, key=scores.get)
    return (best, scores[best]) if scores[best] > 0 else ("Other", 0)


def categorize_with_gemini(entries: list, only_unsure: bool = False) -> list:
    """Re-categorize entries using Gemini. Falls back silently on error."""
    if not GEMINI_API_KEY:
        print("[gemini] No GEMINI_API_KEY set. Set it in your environment or .env file.")
        return entries

    cats = list(CATEGORIES.keys()) + ["Other"]
    cats_lower = {c.lower().strip(): c for c in cats}

    if only_unsure:
        unsure_indices = [i for i, e in enumerate(entries) if e.get("score", 1) == 0]
        if not unsure_indices:
            print("[gemini] No low-confidence entries found.")
            return entries
        print(f"[gemini] Found {len(unsure_indices)} low-confidence entries to fix.")
        subset = [entries[i] for i in unsure_indices]
        result_subset = categorize_with_gemini(subset, only_unsure=False)
        updated = list(entries)
        for orig_idx, new_entry in zip(unsure_indices, result_subset):
            updated[orig_idx] = new_entry
        return updated

    cats_str = "\n".join(f'{i+1}. "{c}"' for i, c in enumerate(cats))
    system_prompt = f"""\
You are categorizing bookmarks saved from X/Twitter.
Read each post and pick the BEST category.

CATEGORIES:
{cats_str}

Return ONLY a valid JSON array of category strings, one per post, same order.
No explanation, no markdown fences — just the JSON array.
Example for 3 posts: ["AI Tools & Prompts", "Trading/Crypto", "Other"]
"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    BATCH = 50
    updated = list(entries)
    total = len(entries)
    batches = (total + BATCH - 1) // BATCH
    print(f"\n[gemini] Categorizing {total} entries in {batches} batch(es)...")

    for b in range(batches):
        batch = entries[b * BATCH:(b + 1) * BATCH]
        items_parts = []
        for j, e in enumerate(batch):
            tweet_text = (e.get("full_text") or e.get("summary", "")).strip()
            article_text = " ".join(
                a["content"][:600] for a in e.get("articles", []) if a.get("content")
            )
            combined = tweet_text
            if article_text:
                combined += f"\n[Linked content]: {article_text}"
            items_parts.append(f"POST {j+1}:\n{combined[:1000]}")

        items_str = "\n\n---\n\n".join(items_parts)
        prompt = (
            f"{system_prompt}\n\n"
            f"Categorize the following {len(batch)} posts.\n\n"
            f"{items_str}\n\n"
            f"Return ONLY a valid JSON array of EXACTLY {len(batch)} strings.\n"
            f"Use only these exact strings: {json.dumps(cats)}"
        )

        for attempt in range(5):
            try:
                if attempt > 0:
                    wait = 60 * attempt
                    print(f"[gemini] Rate limited — waiting {wait}s...")
                    time.sleep(wait)
                r = requests.post(
                    url,
                    json={
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {"temperature": 0},
                    },
                    timeout=90,
                )
                r.raise_for_status()
                raw = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
                raw = re.sub(r'\s*```\s*$', '', raw, flags=re.MULTILINE).strip()
                result_cats = json.loads(raw)
                if not isinstance(result_cats, list):
                    raise ValueError(f"Expected list, got {type(result_cats)}")

                assigned = 0
                for j, cat in enumerate(result_cats):
                    idx = b * BATCH + j
                    if idx >= total:
                        break
                    cat_str = str(cat).strip()
                    matched = cat_str if cat_str in cats else cats_lower.get(cat_str.lower())
                    if matched:
                        updated[idx]["category"] = matched
                        updated[idx]["score"] = 1
                        assigned += 1

                print(f"[gemini] Batch {b+1}/{batches}: {assigned}/{len(batch)} categorized.")
                break
            except Exception as e:
                if attempt == 4:
                    print(f"[gemini] Batch {b+1} failed after retries ({e}) — keeping existing categories.")

        if b < batches - 1:
            time.sleep(5)

    return updated


def clean(text: str, maxlen: int = 220) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return (text[:maxlen] + "...") if len(text) > maxlen else text


# ─────────────────────────────────────────
#  ARTICLE SCRAPING
# ─────────────────────────────────────────
_TCO_RE = re.compile(r'https?://t\.co/[A-Za-z0-9]+')
_SKIP_HOSTS = {"x.com", "twitter.com", "t.co", "mobile.twitter.com"}
_X_ARTICLE_RE = re.compile(r'https?://(?:x|twitter)\.com/i/article/')


def _expand_url(url: str) -> str:
    try:
        r = requests.head(url, allow_redirects=True, timeout=8,
                          headers={"User-Agent": "Mozilla/5.0"})
        return r.url
    except Exception:
        return url


def _html_to_text(raw: str) -> str:
    raw = re.sub(r'<(script|style|nav|footer|header|aside)[^>]*>.*?</\1>',
                 '', raw, flags=re.DOTALL | re.IGNORECASE)
    raw = re.sub(r'<[^>]+>', ' ', raw)
    raw = html.unescape(raw)
    raw = re.sub(r'[ \t]{2,}', ' ', raw)
    raw = re.sub(r'\n{3,}', '\n\n', raw)
    return raw.strip()


_YT_RE = re.compile(
    r'(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/)([A-Za-z0-9_-]{11})'
)


def fetch_youtube_transcript(url: str) -> str:
    m = _YT_RE.search(url)
    if not m:
        return ""
    vid_id = m.group(1)
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        entries = YouTubeTranscriptApi.get_transcript(vid_id)
        return " ".join(e["text"] for e in entries).strip()
    except ImportError:
        dbg("youtube_transcript_api not installed — pip install youtube-transcript-api")
        return ""
    except Exception as e:
        dbg("YouTube transcript failed", str(e))
        return ""


def fetch_x_article_playwright(url: str) -> str:
    """Fetch a JS-rendered X article via Playwright + saved cookies."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  [playwright] Not installed. Run: pip install playwright && playwright install chromium")
        return ""

    cookies = []
    if COOKIES_JSON.exists():
        try:
            with open(COOKIES_JSON, encoding="utf-8") as f:
                raw = json.load(f)
            for c in raw:
                name = c.get("name", "")
                value = c.get("value", "")
                if not name or not value:
                    continue
                domain = c.get("domain", ".x.com")
                if not domain.startswith(".") and "x.com" in domain:
                    domain = ".x.com"
                cookies.append({
                    "name": name, "value": value,
                    "domain": domain, "path": c.get("path", "/"),
                    "secure": c.get("secure", True),
                })
        except Exception as e:
            dbg("playwright cookie load error", str(e))

    if not cookies:
        dbg("playwright: no cookies — cannot authenticate")
        return ""

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                )
            )
            context.add_cookies(cookies)
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)

            for sel in ["[data-testid='article-content']", "[data-testid='tweetText']",
                        "article", "[role='article']", "main"]:
                try:
                    page.wait_for_selector(sel, timeout=8000)
                    break
                except Exception:
                    continue

            content = ""
            for sel in ["[data-testid='article-content']", "article", "[role='article']", "main"]:
                try:
                    el = page.query_selector(sel)
                    if el:
                        text = el.inner_text()
                        if len(text) > 200:
                            content = text
                            break
                except Exception:
                    continue

            if not content or len(content) < 200:
                try:
                    content = page.inner_text("body")
                except Exception:
                    pass

            browser.close()

            if content:
                lines = [l.strip() for l in content.splitlines() if l.strip()]
                content = "\n".join(l for l in lines if len(l) > 15)

            return content.strip()
    except Exception as e:
        dbg("playwright exception", str(e))
        return ""


def _detect_whisper_device() -> str:
    """Return 'cuda' if a CUDA GPU is available, else 'cpu'."""
    device = CONFIG.get("whisper_device", "auto")
    if device != "auto":
        return device
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        pass
    try:
        import ctypes
        ctypes.cdll.LoadLibrary("libcuda.so")
        return "cuda"
    except Exception:
        return "cpu"


def transcribe_x_video(tweet_url: str, whisper_model=None) -> tuple:
    """Download audio from an X video and transcribe with faster-whisper (GPU or CPU)."""
    import subprocess
    import tempfile

    tmp_dir = tempfile.gettempdir()
    url_hash = str(abs(hash(tweet_url)))[:12]
    audio_path = os.path.join(tmp_dir, f"bm_audio_{url_hash}")

    try:
        try:
            import imageio_ffmpeg
            ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError:
            ffmpeg_path = "ffmpeg"

        cookies_txt = None
        if COOKIES_JSON.exists():
            try:
                with open(COOKIES_JSON, "r", encoding="utf-8") as f:
                    cj = json.load(f)
                cookies_txt = os.path.join(tmp_dir, "bm_ytdlp_cookies.txt")
                with open(cookies_txt, "w", encoding="utf-8") as cf:
                    cf.write("# Netscape HTTP Cookie File\n")
                    for c in cj:
                        domain = c.get("domain", ".x.com")
                        flag = "TRUE" if domain.startswith(".") else "FALSE"
                        path = c.get("path", "/")
                        secure = "TRUE" if c.get("secure", False) else "FALSE"
                        expiry = str(int(c.get("expirationDate", 0)))
                        cf.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expiry}\t{c['name']}\t{c['value']}\n")
            except Exception:
                cookies_txt = None

        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--no-warnings", "-q",
            "-f", "bestaudio/best",
            "-o", audio_path + ".%(ext)s",
            tweet_url,
        ]
        if cookies_txt:
            cmd.insert(4, "--cookies")
            cmd.insert(5, cookies_txt)

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            return "", whisper_model

        raw_path = None
        for f in os.listdir(tmp_dir):
            if f.startswith(f"bm_audio_{url_hash}"):
                raw_path = os.path.join(tmp_dir, f)
                break
        if not raw_path:
            return "", whisper_model

        wav_path = audio_path + ".wav"
        if not raw_path.endswith(".wav"):
            conv_cmd = [
                ffmpeg_path, "-y", "-i", raw_path,
                "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                wav_path,
            ]
            conv = subprocess.run(conv_cmd, capture_output=True, text=True, timeout=120)
            if conv.returncode != 0:
                return "", whisper_model
            try:
                os.remove(raw_path)
            except OSError:
                pass
        else:
            wav_path = raw_path

        if whisper_model is None:
            from faster_whisper import WhisperModel
            device = _detect_whisper_device()
            compute_type = "float16" if device == "cuda" else "int8"
            model_name = CONFIG.get("whisper_model", "medium")
            print(f"  [whisper] Loading {model_name} model on {device}...")
            whisper_model = WhisperModel(model_name, device=device, compute_type=compute_type)
            print("  [whisper] Model loaded.")

        segments, info = whisper_model.transcribe(wav_path, beam_size=5)
        dbg("whisper language", f"{info.language} (prob={info.language_probability:.2f})")

        transcript = " ".join(seg.text.strip() for seg in segments).strip()
        if len(transcript) > 50000:
            transcript = transcript[:50000] + "\n\n... [truncated at 50K chars]"

        return transcript, whisper_model

    except Exception as e:
        dbg("transcribe_x_video error", str(e))
        return "", whisper_model
    finally:
        for f in os.listdir(tmp_dir):
            if f.startswith(f"bm_audio_{url_hash}"):
                try:
                    os.remove(os.path.join(tmp_dir, f))
                except OSError:
                    pass


def fetch_article(url: str) -> tuple:
    """Returns (real_url, content_text). Tries trafilatura, falls back to basic scrape."""
    real_url = _expand_url(url)
    host = urlparse(real_url).netloc.lstrip("www.")

    if "youtube.com" in host or "youtu.be" in host:
        transcript = fetch_youtube_transcript(real_url)
        if transcript:
            return real_url, transcript

    if _X_ARTICLE_RE.search(real_url):
        content = fetch_x_article_playwright(real_url)
        return real_url, content

    if any(skip in host for skip in _SKIP_HOSTS):
        return real_url, ""

    try:
        try:
            import trafilatura
            downloaded = trafilatura.fetch_url(real_url)
            text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
            if text:
                return real_url, text.strip()
        except ImportError:
            pass
        r = requests.get(real_url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            text = _html_to_text(r.text)
            if len(text) > 10000:
                text = text[:10000] + "\n\n... [truncated — pip install trafilatura for full extraction]"
            return real_url, text
    except Exception as e:
        dbg("fetch_article exception", str(e))
    return real_url, ""


# ─────────────────────────────────────────
#  PROGRESS
# ─────────────────────────────────────────
def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        try:
            with open(PROGRESS_FILE, encoding="utf-8") as f:
                data = json.load(f)
            if "entries" not in data:
                raise ValueError("missing 'entries' key")
            print(f"[resume] {len(data['entries'])} entries saved — continuing.\n")
            return data
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[ERROR] Progress file is corrupt or wrong format: {e}")
            print(f"[ERROR] Run with --reset to start fresh, or delete {PROGRESS_FILE} manually.")
            sys.exit(1)
    return {"processed_ids": [], "entries": [], "cursor": None}


def save_progress(data: dict):
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ─────────────────────────────────────────
#  MARKDOWN OUTPUT
# ─────────────────────────────────────────
_DISPLAY_TEXT_REPLACEMENTS = {
    "â€”": "-",
    "â€“": "-",
    "â€¦": "...",
    "â€˜": "'",
    "â€™": "'",
    "â€œ": '"',
    "â€": '"',
    "ï¿¼": "",
    "￼": "",
}


def _clean_display_text(value: str) -> str:
    if not value:
        return value
    for bad, good in _DISPLAY_TEXT_REPLACEMENTS.items():
        value = value.replace(bad, good)
    return value


def _tweet_title(item: dict) -> str:
    full = _clean_display_text((item.get("full_text") or item.get("summary", "")).strip())
    before_json = full.split("{")[0].strip()
    for line in before_json.splitlines():
        line = line.strip()
        if len(line) > 8:
            return (line[:120] + "...") if len(line) > 120 else line
    return (full[:80] + "...") if len(full) > 80 else full or "(no text)"


def write_markdown(entries: list):
    buckets = {c: [] for c in ALL_CATS}
    for e in entries:
        cat = e.get("category", "Other")
        if cat not in buckets:
            cat = "Other"
        buckets[cat].append(e)

    n_articles = sum(1 for e in entries if any(a.get("content") for a in e.get("articles", [])))
    n_videos = sum(1 for e in entries if e.get("is_video"))
    n_unsure = sum(1 for e in entries if e.get("score", 1) == 0)
    n_threads = sum(1 for e in entries if e.get("author_replies"))
    n_yt = sum(
        1 for e in entries
        if any(a.get("content") and ("youtube.com" in a.get("url", "") or "youtu.be" in a.get("url", ""))
               for a in e.get("articles", []))
    )
    n_video_t = sum(1 for e in entries if e.get("video_transcript"))

    video_note = f"{n_videos} videos"
    t_parts = []
    if n_yt:
        t_parts.append(f"{n_yt} YouTube")
    if n_video_t:
        t_parts.append(f"{n_video_t} X video")
    if t_parts:
        video_note += f" ({' + '.join(t_parts)} transcribed)"

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = []

    lines += [
        "# X Bookmarks — Knowledge Base\n\n",
        f"*Last updated: {now_str}*  \n",
        f"*Total: {len(entries)} bookmarks  |  {n_articles} with scraped content"
        f"  |  {n_threads} with author threads  |  {video_note}  |  {n_unsure} low-confidence category*\n\n",
        "---\n\n",
    ]

    lines += [
        "## Contents\n\n",
        "| Category | Count |\n",
        "|---|---|\n",
    ]
    for cat in ALL_CATS:
        if buckets[cat]:
            lines.append(f"| **{cat}** | {len(buckets[cat])} |\n")
    lines.append("\n")

    video_entries = [e for e in entries if e.get("is_video")]
    if video_entries:
        lines += [
            "## Video Watch List\n\n",
            "_YouTube transcripts auto-extracted. X native videos: run `--transcribe-videos`._\n\n",
            "| # | Author | Category | Title | Transcript? |\n",
            "|---|---|---|---|---|\n",
        ]
        for i, e in enumerate(video_entries, 1):
            has_yt_t = any(
                a.get("content") and ("youtube.com" in a.get("url", "") or "youtu.be" in a.get("url", ""))
                for a in e.get("articles", [])
            )
            has_v_t = bool(e.get("video_transcript"))
            t_col = "YouTube" if has_yt_t else ("transcribed" if has_v_t else "missing")
            lines.append(
                f"| {i} | [@{e['author']}]({e['url']}) | {e.get('category', '?')} "
                f"| {_tweet_title(e)} | {t_col} |\n"
            )
        lines.append("\n")

    lines.append("---\n\n")

    for cat in ALL_CATS:
        items = buckets[cat]
        if not items:
            continue
        lines.append(f"\n---\n\n## {cat} ({len(items)})\n\n")

        for item in items:
            tags = []
            if item.get("is_video"):
                tags.append("VIDEO")
            if item.get("score", 1) == 0:
                tags.append("LOW CONFIDENCE")
            tag_str = "  |  " + "  |  ".join(tags) if tags else ""

            lines.append(f"### @{item['author']}{tag_str}\n\n")
            lines.append(f"{item['url']}\n\n")

            if item.get("is_video"):
                has_yt_t = any(
                    a.get("content") and ("youtube.com" in a.get("url", "") or "youtu.be" in a.get("url", ""))
                    for a in item.get("articles", [])
                )
                if has_yt_t:
                    lines.append("_[YouTube video — transcript below]_\n\n")
                elif item.get("video_transcript"):
                    lines.append("_[X video — transcript below]_\n\n")
                else:
                    lines.append("_[X native video — no transcript yet; run --transcribe-videos]_\n\n")

            full = (item.get("full_text") or item.get("summary", "")).strip()
            if "\n\n--- THREAD ---\n\n" in full:
                full = full.split("\n\n--- THREAD ---\n\n")[0].strip()
            if "\n\n--- VIDEO TRANSCRIPT ---\n\n" in full:
                full = full.split("\n\n--- VIDEO TRANSCRIPT ---\n\n")[0].strip()
            if full:
                lines.append(f"{full}\n\n")

            author_replies = item.get("author_replies", [])
            if author_replies:
                lines.append("**Author's thread:**\n\n")
                for idx, reply in enumerate(author_replies, 1):
                    reply_text = reply.get("text", "").strip()
                    if reply_text:
                        lines.append(f"[{idx}] {reply_text}\n\n")

            video_transcript = (item.get("video_transcript") or "").strip()
            if video_transcript:
                lines.append("**Video transcript:**\n\n")
                lines.append(f"{video_transcript}\n\n")

            image_analysis = (item.get("image_analysis") or "").strip()
            if image_analysis:
                lines.append("**Image analysis:**\n\n")
                lines.append(f"{image_analysis}\n\n")

            for art in item.get("articles", []):
                content = (art.get("content") or "").strip()
                if not content:
                    continue
                art_url = art.get("url", "")
                is_yt = "youtube.com" in art_url or "youtu.be" in art_url
                label = "**YouTube transcript:**" if is_yt else "**Linked article:**"
                lines.append(f"{label} {art_url}\n\n")
                lines.append(f"{content}\n\n")

            lines.append("---\n\n")

    lines = [_clean_display_text(line) for line in lines]
    with open(OUTPUT_MD, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"  [saved] {OUTPUT_MD.name}")


# ─────────────────────────────────────────
#  X API SESSION
# ─────────────────────────────────────────
def _session_from_cookie_file() -> requests.Session | None:
    if not COOKIES_JSON.exists():
        return None
    print(f"[cookies] Found {COOKIES_JSON.name} — loading...")
    try:
        with open(COOKIES_JSON, encoding="utf-8") as f:
            raw = json.load(f)
        session = requests.Session()
        for c in raw:
            name = c.get("name", "")
            value = c.get("value", "")
            domain = c.get("domain", ".x.com")
            if name and value:
                session.cookies.set(name, value, domain=domain)
        return session
    except Exception as e:
        print(f"[warn] Could not parse {COOKIES_JSON.name}: {e}")
        return None


def _session_from_browser() -> requests.Session | None:
    try:
        import browser_cookie3
    except ImportError:
        return None
    try:
        print("[cookies] Reading X session from Chrome profile...")
        cj = browser_cookie3.chrome(domain_name=".x.com")
        session = requests.Session()
        for cookie in cj:
            session.cookies.set(cookie.name, cookie.value, domain=cookie.domain)
        try:
            cj2 = browser_cookie3.chrome(domain_name=".twitter.com")
            for cookie in cj2:
                session.cookies.set(cookie.name, cookie.value, domain=cookie.domain)
        except Exception:
            pass
        return session
    except Exception as e:
        print(f"[warn] browser_cookie3 failed: {e}")
        return None


def build_session() -> requests.Session:
    """Build an authenticated requests session from cookies."""
    session = _session_from_cookie_file()
    if session is None:
        session = _session_from_browser()

    if session is None:
        print()
        print("[ERROR] No X cookies found. Two options:\n")
        print("  OPTION A — Export cookies from Chrome (recommended, no admin needed):")
        print("    1. Install 'Cookie-Editor' extension in Chrome")
        print("    2. Go to x.com and make sure you're logged in")
        print("    3. Click Cookie-Editor -> Export -> 'Export as JSON'")
        print(f"    4. Save as: {COOKIES_JSON}")
        print("    5. Re-run: python bookmark_scraper.py\n")
        print("  OPTION B — Run as administrator so browser_cookie3 can read Chrome's profile.")
        sys.exit(1)

    ct0 = (
        session.cookies.get("ct0", domain=".x.com")
        or session.cookies.get("ct0", domain="x.com")
        or session.cookies.get("ct0")
    )
    if not ct0:
        print("[ERROR] No 'ct0' cookie found. Your cookies may be stale — re-export from Chrome.")
        sys.exit(1)

    print(f"[cookies] ct0 found ({ct0[:8]}...)  Session OK.\n")
    session.headers.update({
        "Authorization": f"Bearer {BEARER}",
        "x-csrf-token": ct0,
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-active-user": "yes",
        "x-twitter-client-language": "en",
        "Content-Type": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Referer": "https://x.com/",
        "Origin": "https://x.com",
    })
    return session


def get_user_id(session: requests.Session) -> str:
    r = session.get(
        "https://api.x.com/1.1/account/verify_credentials.json",
        params={"skip_status": "true", "include_entities": "false"},
        timeout=30,
    )
    if r.status_code == 200:
        return str(r.json()["id"])
    # Fallback: read from twid cookie
    for c in session.cookies:
        if c.name == "twid":
            return c.value.replace("u%3D", "").replace("u=", "")
    print(f"[ERROR] Could not get user ID: {r.status_code}")
    sys.exit(1)


# ─────────────────────────────────────────
#  QUERY ID DISCOVERY (shared logic)
# ─────────────────────────────────────────
def _find_graphql_query_id(
    session: requests.Session,
    operation_name: str,
    known_ids: list,
    probe_params_fn,
    label: str,
) -> str | None:
    """
    Generic: scan X's JS bundles for a GraphQL query ID, fall back to known IDs.
    Returns the query ID or None if not found (fatal for Bookmarks, non-fatal for TweetDetail).
    """
    patterns = [
        rf'queryId:"([A-Za-z0-9_-]{{15,}})",operationName:"{operation_name}"',
        rf'operationName:"{operation_name}",queryId:"([A-Za-z0-9_-]{{15,}})"',
        rf'"queryId":"([A-Za-z0-9_-]{{15,}})","operationName":"{operation_name}"',
        rf'{operation_name}.{{0,120}}queryId["\s:]+([A-Za-z0-9_-]{{15,}})',
    ]

    def search_text(text):
        for p in patterns:
            m = re.search(p, text)
            if m:
                return m.group(1)
        return None

    print(f"[{label}] Scanning X JS bundles...")
    js_urls = []
    for start_url in ["https://x.com/i/bookmarks", "https://x.com/home", "https://x.com/"]:
        try:
            r = session.get(start_url, headers={"Accept": "text/html"}, timeout=15)
            qid = search_text(r.text)
            if qid:
                print(f"[{label}] Found in page HTML: {qid}")
                return qid
            js_urls = list(set(
                re.findall(r'https://abs\.twimg\.com/responsive-web/client-web/[^\s"\']+\.js', r.text)
                + [
                    "https://abs.twimg.com" + u
                    for u in re.findall(r'["\'](?:/responsive-web/client-web/[^\s"\']+\.js)', r.text)
                ]
            ))
            if js_urls:
                break
        except Exception:
            pass

    if js_urls:
        js_urls.sort(key=len)
        print(f"[{label}] Searching {min(len(js_urls), 25)} JS files...")
        for url in js_urls[:25]:
            try:
                rj = session.get(url, timeout=20, stream=True)
                if rj.status_code != 200:
                    continue
                chunk = rj.raw.read(800_000).decode("utf-8", errors="ignore")
                qid = search_text(chunk)
                if qid:
                    print(f"[{label}] Found in {url.split('/')[-1].split('?')[0]}: {qid}")
                    return qid
            except Exception:
                continue

    print(f"[{label}] Trying cached IDs...")
    for qid in known_ids:
        try:
            params = probe_params_fn(qid)
            r = session.get(
                f"https://x.com/i/api/graphql/{qid}/{operation_name}",
                params=params,
                timeout=10,
            )
            if r.status_code == 200 and "data" in r.text:
                print(f"[{label}] Found working cached ID: {qid}")
                return qid
        except Exception:
            continue

    return None


def find_query_id(session: requests.Session) -> str:
    def probe(qid):
        return {
            "variables": json.dumps({"count": 1, "includePromotedContent": False}),
            "features": json.dumps(FEATURES),
        }

    qid = _find_graphql_query_id(
        session, "Bookmarks", KNOWN_QUERY_IDS, probe, "query_id"
    )
    if not qid:
        print("\n[ERROR] Could not find a working Bookmarks query ID.")
        print("  X rotates these on each deploy. To fix:")
        print("  1. Open x.com/i/bookmarks in Chrome, open DevTools (F12)")
        print("  2. Network tab -> filter 'Bookmarks' -> copy the queryId from the URL")
        print("  3. Add it to KNOWN_QUERY_IDS at the top of this script")
        sys.exit(1)
    return qid


def find_tweetdetail_query_id(session: requests.Session) -> str | None:
    def probe(qid):
        return {
            "variables": json.dumps({
                "focalTweetId": "1", "with_rux_injections": False,
                "includePromotedContent": False, "withCommunity": True,
                "withQuickPromoteEligibilityTweetFields": False,
                "withBirdwatchNotes": False, "withVoice": True, "withV2Timeline": True,
            }),
            "features": json.dumps(FEATURES),
        }

    qid = _find_graphql_query_id(
        session, "TweetDetail", KNOWN_TWEETDETAIL_IDS, probe, "tweetdetail_qid"
    )
    if not qid:
        print("[tweetdetail_qid] WARNING: Could not find TweetDetail ID — author reply scraping disabled.")
    return qid


# ─────────────────────────────────────────
#  TWEET PARSING
# ─────────────────────────────────────────
def extract_tweet(result: dict) -> dict | None:
    try:
        if result.get("__typename") == "TweetWithVisibilityResults":
            result = result.get("tweet", result)

        rest_id = result.get("rest_id", "")
        if not rest_id:
            return None

        legacy = result.get("legacy", {})
        _core = result.get("core", {})
        _user_res = _core.get("user_results", {})
        _user_inner = _user_res.get("result", {})
        _user_legacy = _user_inner.get("legacy", {})

        author = (
            _user_legacy.get("screen_name")
            or _user_inner.get("core", {}).get("screen_name")
            or _user_inner.get("screen_name")
            or legacy.get("user_id_str", "unknown")
        ) or "unknown"

        text = ""
        note = result.get("note_tweet", {})
        if note:
            text = (note.get("note_tweet_results", {}).get("result", {}).get("text", ""))
        if not text:
            text = legacy.get("full_text", legacy.get("text", ""))

        qt = result.get("quoted_status_result", {}).get("result", {})
        if qt:
            qt_legacy = qt.get("legacy", {})
            qt_text = qt_legacy.get("full_text", qt_legacy.get("text", ""))
            if qt_text:
                text += " | QT: " + qt_text

        card = result.get("card", {}).get("legacy", {})
        if card:
            for bv in card.get("binding_values", []):
                if bv.get("key") == "title":
                    card_title = bv.get("value", {}).get("string_value", "")
                    if card_title:
                        text += " [link: " + card_title + "]"
                        break

        article_data = result.get("article", {})
        if article_data:
            art_res = article_data.get("article_results", {}).get("result", {})
            art_title = art_res.get("title", "")
            art_body = art_res.get("content", {})
            art_text = art_body.get("text", "") if isinstance(art_body, dict) else (art_body if isinstance(art_body, str) else "")
            if art_title or art_text:
                extra = (art_title + "\n\n" + art_text).strip()
                text = (text + "\n\n" + extra).strip() if text else extra

        media = legacy.get("extended_entities", legacy.get("entities", {})).get("media", [])
        is_video = any(m.get("type") in ("video", "animated_gif") for m in media)
        image_urls = [m.get("media_url_https") for m in media
                      if m.get("type") == "photo" and m.get("media_url_https")]

        return {
            "id": rest_id,
            "url": f"https://x.com/{author}/status/{rest_id}",
            "author": author,
            "text": text,
            "is_video": is_video,
            "image_urls": image_urls,
        }
    except Exception as e:
        dbg("extract_tweet exception", str(e))
        return None


def fetch_author_replies(session, tweetdetail_qid: str, tweet_id: str, author_handle: str) -> list:
    if not tweetdetail_qid:
        return []
    try:
        variables = {
            "focalTweetId": tweet_id,
            "with_rux_injections": False,
            "includePromotedContent": False,
            "withCommunity": True,
            "withQuickPromoteEligibilityTweetFields": False,
            "withBirdwatchNotes": False,
            "withVoice": True,
            "withV2Timeline": True,
        }
        r = session.get(
            f"https://x.com/i/api/graphql/{tweetdetail_qid}/TweetDetail",
            params={"variables": json.dumps(variables), "features": json.dumps(FEATURES)},
            timeout=15,
        )
        if r.status_code != 200:
            return []

        data = r.json()
        instructions = (
            data.get("data", {})
                .get("threaded_conversation_with_injections_v2", {})
                .get("instructions", [])
        )

        replies = []
        author_lower = author_handle.lower()

        for instr in instructions:
            if instr.get("type") != "TimelineAddEntries":
                continue
            for entry in instr.get("entries", []):
                content = entry.get("content", {})
                items_to_check = []
                if content.get("entryType") == "TimelineTimelineItem":
                    items_to_check.append(content.get("itemContent", {}))
                elif content.get("entryType") == "TimelineTimelineModule":
                    for module_item in content.get("items", []):
                        items_to_check.append(module_item.get("item", {}).get("itemContent", {}))

                for item in items_to_check:
                    if item.get("itemType") != "TimelineTweet":
                        continue
                    result = item.get("tweet_results", {}).get("result", {})
                    if result.get("__typename") == "TweetWithVisibilityResults":
                        result = result.get("tweet", result)

                    rest_id = result.get("rest_id", "")
                    if rest_id == tweet_id or not rest_id:
                        continue

                    user_legacy = (result.get("core", {}).get("user_results", {})
                                   .get("result", {}).get("legacy", {}))
                    if user_legacy.get("screen_name", "").lower() != author_lower:
                        continue

                    legacy = result.get("legacy", {})
                    text = ""
                    note = result.get("note_tweet", {})
                    if note:
                        text = (note.get("note_tweet_results", {}).get("result", {}).get("text", ""))
                    if not text:
                        text = legacy.get("full_text", legacy.get("text", ""))

                    reply_media = legacy.get("extended_entities", legacy.get("entities", {})).get("media", [])
                    reply_imgs = [m.get("media_url_https") for m in reply_media
                                  if m.get("type") == "photo" and m.get("media_url_https")]

                    if text.strip() or reply_imgs:
                        entry_data = {"id": rest_id, "text": text.strip()}
                        if reply_imgs:
                            entry_data["image_urls"] = reply_imgs
                        replies.append(entry_data)
                        if len(replies) >= 5:
                            break

                if len(replies) >= 5:
                    break
            if len(replies) >= 5:
                break

        return replies
    except Exception as e:
        dbg("fetch_author_replies exception", str(e))
        return []


def parse_page(data: dict) -> tuple:
    tweets = []
    cursor = None
    try:
        instructions = (
            data.get("data", {})
                .get("bookmark_timeline_v2", {})
                .get("timeline", {})
                .get("instructions", [])
        )
    except Exception:
        return tweets, cursor

    for instr in instructions:
        if instr.get("type") != "TimelineAddEntries":
            continue
        for entry in instr.get("entries", []):
            content = entry.get("content", {})
            if content.get("entryType") == "TimelineTimelineCursor":
                if content.get("cursorType") == "Bottom":
                    cursor = content.get("value")
                continue
            item = content.get("itemContent", {})
            if item.get("itemType") == "TimelineTweet":
                result = item.get("tweet_results", {}).get("result", {})
                t = extract_tweet(result)
                if t:
                    tweets.append(t)

    return tweets, cursor


# ─────────────────────────────────────────
#  MAIN SCRAPER LOOP
# ─────────────────────────────────────────
def scrape(session, query_id, user_id, progress, tweetdetail_qid=None) -> list:
    processed_ids = set(progress["processed_ids"])
    entries = list(progress["entries"])
    cursor = None
    _whisper_model = None

    print(f"[scraping] Have: {len(entries)} — scanning from top for new bookmarks\n")

    while len(entries) < MAX_BOOKMARKS:
        variables = {"count": PER_PAGE, "includePromotedContent": False}
        if cursor:
            variables["cursor"] = cursor

        r = session.get(
            f"https://x.com/i/api/graphql/{query_id}/Bookmarks",
            params={"variables": json.dumps(variables), "features": json.dumps(FEATURES)},
            timeout=30,
        )

        if r.status_code == 429:
            print("[rate limit] Waiting 60s...")
            time.sleep(60)
            continue

        if r.status_code != 200:
            print(f"[ERROR] API returned {r.status_code}: {r.text[:300]}")
            break

        data = r.json()
        tweets, next_cursor = parse_page(data)

        if not tweets:
            print("[info] No more bookmarks.")
            break

        new_on_page = [t for t in tweets if t["id"] not in processed_ids]
        if not new_on_page:
            print("[info] All bookmarks on this page already processed — caught up.")
            break

        for t in tweets:
            if len(entries) >= MAX_BOOKMARKS:
                break
            if t["id"] in processed_ids:
                continue

            category, score = categorize(t["text"])
            summary = clean(t["text"]) if t["text"].strip() else "(no text)"
            if t["is_video"]:
                summary = "[VIDEO] " + summary

            tco_urls = _TCO_RE.findall(t["text"])
            articles = []
            for tco in tco_urls:
                real_url, content = fetch_article(tco)
                articles.append({"url": real_url, "content": content})

            author_replies = []
            if tweetdetail_qid:
                author_replies = fetch_author_replies(session, tweetdetail_qid, t["id"], t["author"])
                if author_replies:
                    time.sleep(1.0)

            full_text_with_thread = t["text"]
            if author_replies:
                thread_parts = [f"[{i}/{len(author_replies)}] {r['text']}"
                                for i, r in enumerate(author_replies, 1)]
                full_text_with_thread += "\n\n--- THREAD ---\n\n" + "\n\n".join(thread_parts)

            video_transcript = ""
            if t["is_video"]:
                try:
                    from faster_whisper import WhisperModel  # noqa: F811
                    transcript, _whisper_model = transcribe_x_video(t["url"], _whisper_model)
                    if transcript:
                        video_transcript = transcript
                        full_text_with_thread += "\n\n--- VIDEO TRANSCRIPT ---\n\n" + transcript
                except ImportError:
                    pass
                except Exception as e:
                    dbg("scrape video transcribe error", str(e))

            all_image_urls = list(t.get("image_urls", []))
            for reply in author_replies:
                for img in reply.get("image_urls", []):
                    if img not in all_image_urls:
                        all_image_urls.append(img)

            entry = {
                "id": t["id"],
                "url": t["url"],
                "author": t["author"],
                "category": category,
                "score": score,
                "is_video": t["is_video"],
                "summary": summary,
                "full_text": full_text_with_thread,
                "articles": articles,
                "author_replies": author_replies,
                "image_urls": all_image_urls,
            }
            if video_transcript:
                entry["video_transcript"] = video_transcript

            entries.append(entry)
            processed_ids.add(t["id"])

            vid = " [VID]" if t["is_video"] else ""
            unc = " [?]" if score == 0 else ""
            scraped = f"  ({sum(1 for a in articles if a['content'])}/{len(articles)} links)" if articles else ""
            replies_note = f"  (+{len(author_replies)} replies)" if author_replies else ""
            transcript_note = f"  [transcribed {len(video_transcript)} chars]" if video_transcript else ""
            print(f"  [{len(entries):03d}]  @{t['author']:<22}  ->  {category}{vid}{unc}{scraped}{replies_note}{transcript_note}")

            if len(entries) % 5 == 0:
                progress["processed_ids"] = list(processed_ids)
                progress["entries"] = entries
                progress["cursor"] = cursor
                save_progress(progress)
                write_markdown(entries)

        cursor = next_cursor
        if not cursor:
            print("[info] Reached end of bookmarks.")
            break

        time.sleep(DELAY_S)

    progress["processed_ids"] = list(processed_ids)
    progress["entries"] = entries
    progress["cursor"] = cursor
    save_progress(progress)
    write_markdown(entries)
    return entries


# ─────────────────────────────────────────
#  RESCRAPE / BACKFILL MODES
# ─────────────────────────────────────────
def rescrape_articles(progress: dict) -> tuple:
    entries = progress["entries"]
    n_fixed = n_tried = 0
    print("\n[rescrape] Scanning for empty X article links...\n")

    for i, entry in enumerate(entries):
        articles = entry.get("articles", [])
        tco_in_text = _TCO_RE.findall(entry.get("full_text", ""))
        known_urls = {a["url"] for a in articles}

        for tco in tco_in_text:
            expanded = _expand_url(tco)
            if _X_ARTICLE_RE.search(expanded) and expanded not in known_urls:
                articles.append({"url": expanded, "content": ""})
                known_urls.add(expanded)

        for j, art in enumerate(articles):
            art_url = art.get("url", "")
            if not art.get("content") and _X_ARTICLE_RE.search(art_url):
                n_tried += 1
                print(f"  [{i+1:03d}] {art_url}")
                content = fetch_x_article_playwright(art_url)
                if content:
                    entries[i]["articles"][j]["content"] = content
                    n_fixed += 1
                    print(f"         OK {len(content)} chars")
                else:
                    print("         -- still empty")
                time.sleep(1.0)

        entries[i]["articles"] = articles

    progress["entries"] = entries
    return progress, n_tried, n_fixed


def rescrape_replies(session, tweetdetail_qid: str, progress: dict) -> tuple:
    entries = progress["entries"]
    n_tried = n_found = 0
    print("\n[rescrape-replies] Scanning for entries without author replies...\n")

    for i, entry in enumerate(entries):
        if entry.get("author_replies"):
            continue
        tweet_id = entry.get("id", "")
        author = entry.get("author", "")
        if not tweet_id or not author:
            continue

        n_tried += 1
        replies = fetch_author_replies(session, tweetdetail_qid, tweet_id, author)
        entry["author_replies"] = replies

        if replies:
            n_found += 1
            thread_parts = [f"[{idx}/{len(replies)}] {r['text']}"
                            for idx, r in enumerate(replies, 1)]
            full_text = entry.get("full_text", "")
            if "\n\n--- THREAD ---\n\n" not in full_text:
                entry["full_text"] = full_text + "\n\n--- THREAD ---\n\n" + "\n\n".join(thread_parts)
            print(f"  [{i+1:03d}] @{author:<22} +{len(replies)} replies")
        else:
            print(f"  [{i+1:03d}] @{author:<22} (no thread)")

        entries[i] = entry
        if n_tried % 5 == 0:
            progress["entries"] = entries
            save_progress(progress)
        time.sleep(1.0)

    progress["entries"] = entries
    return progress, n_tried, n_found


def transcribe_videos(progress: dict) -> tuple:
    entries = progress["entries"]
    n_tried = n_transcribed = 0
    whisper_model = None
    print("\n[transcribe] Scanning for untranscribed X videos...\n")

    for i, entry in enumerate(entries):
        if not entry.get("is_video") or entry.get("video_transcript"):
            continue
        tweet_url = entry.get("url", "")
        if not tweet_url:
            continue

        n_tried += 1
        print(f"  [{n_tried:03d}] @{entry.get('author', '?'):<22} ", end="", flush=True)

        transcript, whisper_model = transcribe_x_video(tweet_url, whisper_model)
        if transcript:
            entry["video_transcript"] = transcript
            n_transcribed += 1
            full_text = entry.get("full_text", "")
            if "\n\n--- VIDEO TRANSCRIPT ---\n\n" not in full_text:
                entry["full_text"] = full_text + "\n\n--- VIDEO TRANSCRIPT ---\n\n" + transcript
            print(f"OK {len(transcript)} chars")
        else:
            print("-- failed")

        entries[i] = entry
        if n_tried % 5 == 0:
            progress["entries"] = entries
            save_progress(progress)
        time.sleep(1.0)

    progress["entries"] = entries
    return progress, n_tried, n_transcribed


# ─────────────────────────────────────────
#  AI VISION (Ollama)
# ─────────────────────────────────────────
def vision_analyze(progress: dict) -> tuple:
    import base64
    entries = progress["entries"]
    need_analysis = [e for e in entries if e.get("image_urls") and not e.get("image_analysis")]
    if not need_analysis:
        print("[vision] No images to analyze.")
        return progress, 0, 0

    print(f"\n[vision] {len(need_analysis)} entries with images to analyze.\n")
    n_tried = n_done = 0

    for i, entry in enumerate(need_analysis):
        imgs = entry.get("image_urls", [])
        if not imgs:
            continue

        n_tried += 1
        author = entry.get("author", "?")
        print(f"  [{n_tried:03d}] @{author:<22} {len(imgs)} image(s)  ", end="", flush=True)

        try:
            all_analyses = []
            for img_idx, img_url in enumerate(imgs):
                resp = requests.get(img_url, timeout=15)
                if resp.status_code != 200:
                    continue
                img_b64 = base64.b64encode(resp.content).decode("utf-8")
                tweet_text = (entry.get("full_text") or entry.get("summary", ""))[:300]
                img_label = f"Image {img_idx+1}/{len(imgs)}: " if len(imgs) > 1 else ""
                prompt = (
                    "This image is from a bookmarked X/Twitter post. "
                    f"Tweet text: \"{tweet_text}\"\n\n"
                    "Extract ALL text visible in the image verbatim — every word, number, label, "
                    "code snippet, URL. Then describe visual elements: diagrams, charts, "
                    "screenshots, UI elements, or infographics."
                )
                r = requests.post(
                    f"{OLLAMA_URL}/api/generate",
                    json={
                        "model": VISION_MODEL,
                        "prompt": prompt,
                        "images": [img_b64],
                        "stream": False,
                        "options": {"num_predict": 500},
                    },
                    timeout=120,
                )
                if r.status_code != 200:
                    continue
                analysis = r.json().get("response", "").strip()
                if analysis:
                    all_analyses.append(f"{img_label}{analysis}")
                time.sleep(0.3)

            if all_analyses:
                combined = "\n\n".join(all_analyses)
                entry["image_analysis"] = combined
                full_text = entry.get("full_text", "")
                if "\n\n--- IMAGE ANALYSIS ---\n\n" not in full_text:
                    entry["full_text"] = full_text + "\n\n--- IMAGE ANALYSIS ---\n\n" + combined
                n_done += 1
                print(f"OK {len(combined)} chars ({len(all_analyses)} img)")
            else:
                print("-- no results")
        except Exception as e:
            dbg("vision error", str(e))
            print("-- error")

        if n_tried % 10 == 0:
            progress["entries"] = entries
            save_progress(progress)
        time.sleep(0.5)

    progress["entries"] = entries
    return progress, n_tried, n_done


# ─────────────────────────────────────────
#  SEMANTIC SEARCH (Ollama nomic-embed-text)
# ─────────────────────────────────────────
EMBED_MODEL = "nomic-embed-text"
EMBEDDINGS_FILE = BASE_DIR / "bookmarks_embeddings.json"


def _get_embedding(text: str) -> list:
    r = requests.post(
        f"{OLLAMA_URL}/api/embed",
        json={"model": EMBED_MODEL, "input": text},
        timeout=30,
    )
    if r.status_code != 200:
        return []
    embeddings = r.json().get("embeddings", [])
    return embeddings[0] if embeddings else []


def _cosine_sim(a: list, b: list) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def build_embeddings(progress: dict) -> dict:
    entries = progress["entries"]
    index = {}
    if EMBEDDINGS_FILE.exists():
        with open(EMBEDDINGS_FILE, "r", encoding="utf-8") as f:
            index = json.load(f)

    need_embed = [e for e in entries if e.get("id") and e["id"] not in index]
    if not need_embed:
        print(f"[search] Embedding index up to date ({len(index)} entries).")
        return index

    print(f"[search] Embedding {len(need_embed)} new entries...")
    for i, entry in enumerate(need_embed):
        text = " ".join(filter(None, [
            entry.get("full_text", ""),
            entry.get("summary", ""),
            entry.get("image_analysis", ""),
            f"@{entry.get('author', '')}",
            entry.get("category", ""),
        ]))[:8000]
        vec = _get_embedding(text)
        if vec:
            index[entry["id"]] = vec
        if (i + 1) % 50 == 0:
            print(f"  ... {i+1}/{len(need_embed)} embedded")
            with open(EMBEDDINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(index, f)

    with open(EMBEDDINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f)
    print(f"[search] Done. {len(index)} total embeddings saved.")
    return index


def semantic_search(progress: dict, query: str, top_n: int = 10):
    entries = progress["entries"]
    index = build_embeddings(progress)
    if not index:
        print("[search] No embeddings available.")
        return

    print(f"\n[search] Querying: \"{query}\"\n")
    query_vec = _get_embedding(query)
    if not query_vec:
        print("[search] Failed to embed query. Is Ollama running?")
        return

    scores = []
    entry_by_id = {e["id"]: e for e in entries if e.get("id")}
    for eid, vec in index.items():
        scores.append((_cosine_sim(query_vec, vec), eid))
    scores.sort(reverse=True)

    print(f"{'#':<4} {'Score':<7} {'Author':<22} {'Category':<25} Summary")
    print("-" * 110)
    for rank, (sim, eid) in enumerate(scores[:top_n], 1):
        entry = entry_by_id.get(eid)
        if not entry:
            continue
        author = f"@{entry.get('author', '?')}"
        cat = entry.get("category", "Other")
        summary = (entry.get("summary") or entry.get("full_text", ""))[:80].replace("\n", " ")
        url = entry.get("url", "")
        print(f"{rank:<4} {sim:<7.3f} {author:<22} {cat:<25} {summary}"[:110])
        print(f"     {url}")
    print()


# ─────────────────────────────────────────
#  RAW / AGENT-NATIVE OUTPUT
# ─────────────────────────────────────────
RAW_OUTPUT_MD = BASE_DIR / "bookmarks_raw.md"


def write_raw_markdown(entries: list):
    """Write an uncategorized markdown dump — no AI key needed.
    Designed for agent-native workflows: the user's Claude/Codex/Cursor
    reads this file and categorizes + personalizes it against their own profile.
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    n_articles = sum(1 for e in entries if any(a.get("content") for a in e.get("articles", [])))
    n_videos = sum(1 for e in entries if e.get("is_video"))
    n_threads = sum(1 for e in entries if e.get("author_replies"))

    lines = [
        "# X Bookmarks — Raw (Agent-Native)\n\n",
        f"*Last updated: {now_str}*  \n",
        f"*Total: {len(entries)} bookmarks  |  {n_articles} with scraped content"
        f"  |  {n_threads} with author threads  |  {n_videos} videos*\n\n",
        "**This file is uncategorized by design.**  \n",
        "Feed it to your Claude/Codex with your own profile (CLAUDE.md / AGENTS.md) "
        "to get a personalized digest matched to your actual projects and interests.  \n",
        "See the [Agent-Native guide](README.md#use-with-claude-code--codex-recommended-zero-keys) for the exact workflow.\n\n",
        "---\n\n",
    ]

    for i, item in enumerate(entries, 1):
        tags = []
        if item.get("is_video"):
            tags.append("VIDEO")
        tag_str = "  |  " + "  |  ".join(tags) if tags else ""

        lines.append(f"### [{i}] @{item['author']}{tag_str}\n\n")
        lines.append(f"{item['url']}\n\n")

        full = (item.get("full_text") or item.get("summary", "")).strip()
        if "\n\n--- THREAD ---\n\n" in full:
            full = full.split("\n\n--- THREAD ---\n\n")[0].strip()
        if "\n\n--- VIDEO TRANSCRIPT ---\n\n" in full:
            full = full.split("\n\n--- VIDEO TRANSCRIPT ---\n\n")[0].strip()
        if full:
            lines.append(f"{full}\n\n")

        author_replies = item.get("author_replies", [])
        if author_replies:
            lines.append("**Author's thread:**\n\n")
            for idx, reply in enumerate(author_replies, 1):
                reply_text = reply.get("text", "").strip()
                if reply_text:
                    lines.append(f"[{idx}] {reply_text}\n\n")

        video_transcript = (item.get("video_transcript") or "").strip()
        if video_transcript:
            lines.append("**Video transcript:**\n\n")
            lines.append(f"{video_transcript}\n\n")

        for art in item.get("articles", []):
            content = (art.get("content") or "").strip()
            if not content:
                continue
            art_url = art.get("url", "")
            is_yt = "youtube.com" in art_url or "youtu.be" in art_url
            label = "**YouTube transcript:**" if is_yt else "**Linked article:**"
            lines.append(f"{label} {art_url}\n\n")
            lines.append(f"{content}\n\n")

        lines.append("---\n\n")

    lines = [_clean_display_text(line) for line in lines]
    with open(RAW_OUTPUT_MD, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"  [saved] {RAW_OUTPUT_MD.name}")
    print(f"  [raw]   {len(entries)} entries, uncategorized.")
    print(f"  [next]  Feed bookmarks_raw.md to your AI with your CLAUDE.md/AGENTS.md")
    print(f"          to get a personalized digest. See README for the exact workflow.\n")


# ─────────────────────────────────────────
#  DEMO / DRY-RUN MODE
# ─────────────────────────────────────────
def demo_mode():
    """Run in demo mode without X cookies. Shows the output format with fake data."""
    print("=" * 60)
    print("  x-bookmark-miner — DEMO MODE")
    print("  (no cookies needed — shows example output format)")
    print("=" * 60)
    print()

    demo_entries = [
        {
            "id": "demo_001",
            "url": "https://x.com/example_user/status/1234567890",
            "author": "example_user",
            "category": "AI Tools & Prompts",
            "score": 3,
            "is_video": False,
            "summary": "Just discovered this insane LLM trick — you can build entire apps with a single well-structured prompt. Thread:",
            "full_text": "Just discovered this insane LLM trick — you can build entire apps with a single well-structured prompt. Thread:",
            "articles": [{"url": "https://example.com/ai-tips", "content": "Example article content about AI tools and prompting strategies..."}],
            "author_replies": [
                {"id": "demo_001_r1", "text": "Step 1: Start with a detailed system prompt that explains your project structure and constraints."},
                {"id": "demo_001_r2", "text": "Step 2: Keep context clean — quality degrades past 30-40% capacity on most models."},
            ],
            "image_urls": [],
        },
        {
            "id": "demo_002",
            "url": "https://x.com/crypto_trader/status/9876543210",
            "author": "crypto_trader",
            "category": "Trading/Crypto",
            "score": 5,
            "is_video": True,
            "summary": "[VIDEO] BTC breaking out of 6-month accumulation range. Here's why this is the most important level to watch.",
            "full_text": "[VIDEO] BTC breaking out of 6-month accumulation range. Here's why this is the most important level to watch.",
            "articles": [],
            "author_replies": [],
            "image_urls": [],
        },
        {
            "id": "demo_003",
            "url": "https://x.com/dev_builder/status/1122334455",
            "author": "dev_builder",
            "category": "Dev/Automation",
            "score": 4,
            "is_video": False,
            "summary": "Built a full webhook notification bot in 2 hours using n8n. No server needed. Here's the exact workflow:",
            "full_text": "Built a full webhook notification bot in 2 hours using n8n. No server needed. Here's the exact workflow:",
            "articles": [],
            "author_replies": [
                {"id": "demo_003_r1", "text": "1. Create a Webhook node in n8n. Copy the URL."},
                {"id": "demo_003_r2", "text": "2. Add a notification node (Telegram, Slack, email — your choice). Connect them. Done."},
            ],
            "image_urls": [],
        },
    ]

    demo_output = BASE_DIR / "demo_output.md"

    # Write demo file directly without touching the global OUTPUT_MD
    buckets = {c: [] for c in ALL_CATS}
    for e in demo_entries:
        cat = e.get("category", "Other")
        buckets.setdefault(cat, []).append(e)

    lines = [
        "# X Bookmarks — Knowledge Base (DEMO)\n\n",
        "*This is a demo with fake data. Run without --demo to scrape your real bookmarks.*\n\n",
        "---\n\n",
    ]
    for cat in ALL_CATS:
        items = buckets.get(cat, [])
        if not items:
            continue
        lines.append(f"\n## {cat} ({len(items)})\n\n")
        for item in items:
            lines.append(f"### @{item['author']}\n\n")
            lines.append(f"{item['url']}\n\n")
            full = (item.get("full_text") or "").strip()
            if full:
                lines.append(f"{full}\n\n")
            for idx, reply in enumerate(item.get("author_replies", []), 1):
                if idx == 1:
                    lines.append("**Author's thread:**\n\n")
                lines.append(f"[{idx}] {reply.get('text', '')}\n\n")
            for art in item.get("articles", []):
                if art.get("content"):
                    lines.append(f"**Linked article:** {art['url']}\n\n{art['content']}\n\n")
            lines.append("---\n\n")

    with open(demo_output, "w", encoding="utf-8") as f:
        f.writelines(lines)

    print(f"\n[demo] Generated example output at: {demo_output.name}")
    print("[demo] Open it to see what your real bookmarks output will look like.")
    print()
    print("To scrape your real bookmarks:")
    print("  1. Export cookies from Chrome -> Cookie-Editor -> Export as JSON -> save as xcookies.json")
    print("  2. Run: python bookmark_scraper.py")
    print()


# ─────────────────────────────────────────
#  SCHEDULING — self-installing morning run
# ─────────────────────────────────────────
TASK_NAME = "XBookmarkMiner"
PLIST_LABEL = "com.xbookmarkminer.daily"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{PLIST_LABEL}.plist"
CRON_TAG = "# XBookmarkMiner"


def _parse_hhmm(value: str) -> str:
    """Validate and normalise a HH:MM string. Returns 'HH:MM' or raises ValueError."""
    value = value.strip()
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError(f"Time must be HH:MM, got: {value!r}")
    h, m = parts
    if not (h.isdigit() and m.isdigit()):
        raise ValueError(f"Time must be digits only (HH:MM), got: {value!r}")
    hh, mm = int(h), int(m)
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise ValueError(f"Time out of range: {hh:02d}:{mm:02d}")
    return f"{hh:02d}:{mm:02d}"


def _python_exe() -> str:
    return sys.executable


def _script_path() -> str:
    return os.path.abspath(__file__)


# --- Windows ---

def _schtasks_create(hhmm: str) -> None:
    import subprocess
    py = _python_exe()
    script = _script_path()
    cmd = [
        "schtasks", "/create",
        "/tn", TASK_NAME,
        "/tr", f'"{py}" "{script}" --raw',
        "/sc", "DAILY",
        "/st", hhmm,
        "/f",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())


def _schtasks_delete() -> None:
    import subprocess
    cmd = ["schtasks", "/delete", "/tn", TASK_NAME, "/f"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "cannot find" in stderr.lower() or "does not exist" in stderr.lower():
            raise LookupError("Task not found.")
        raise RuntimeError(stderr or result.stdout.strip())


def _schtasks_query() -> str:
    import subprocess
    cmd = ["schtasks", "/query", "/tn", TASK_NAME, "/fo", "LIST"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


# --- macOS launchd ---

def _launchd_plist_xml(hhmm: str) -> str:
    h, m = hhmm.split(":")
    py = _python_exe()
    script = _script_path()
    script_dir = str(Path(script).parent)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"'
        ' "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        '<dict>\n'
        f'  <key>Label</key><string>{PLIST_LABEL}</string>\n'
        '  <key>ProgramArguments</key>\n'
        '  <array>\n'
        f'    <string>{py}</string>\n'
        f'    <string>{script}</string>\n'
        '    <string>--raw</string>\n'
        '  </array>\n'
        '  <key>StartCalendarInterval</key>\n'
        '  <dict>\n'
        f'    <key>Hour</key><integer>{int(h)}</integer>\n'
        f'    <key>Minute</key><integer>{int(m)}</integer>\n'
        '  </dict>\n'
        '  <key>WorkingDirectory</key>'
        f'<string>{script_dir}</string>\n'
        '</dict>\n'
        '</plist>\n'
    )


def _launchd_install(hhmm: str) -> None:
    import subprocess
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Unload first if already loaded (ignore errors)
    subprocess.run(["launchctl", "unload", str(PLIST_PATH)], capture_output=True)
    PLIST_PATH.write_text(_launchd_plist_xml(hhmm), encoding="utf-8")
    result = subprocess.run(["launchctl", "load", str(PLIST_PATH)], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())


def _launchd_uninstall() -> None:
    import subprocess
    if not PLIST_PATH.exists():
        raise LookupError("Plist not found — not scheduled.")
    subprocess.run(["launchctl", "unload", str(PLIST_PATH)], capture_output=True)
    PLIST_PATH.unlink()


def _launchd_status() -> str:
    import subprocess
    if not PLIST_PATH.exists():
        return ""
    result = subprocess.run(
        ["launchctl", "list", PLIST_LABEL], capture_output=True, text=True
    )
    if result.returncode != 0:
        return f"Plist exists at {PLIST_PATH} but launchctl reports it is not loaded."
    return result.stdout.strip()


# --- Linux/macOS crontab ---

def _crontab_line(hhmm: str) -> str:
    h, m = hhmm.split(":")
    py = _python_exe()
    script = _script_path()
    return f"{int(m)} {int(h)} * * * \"{py}\" \"{script}\" --raw {CRON_TAG}"


def _read_crontab() -> str:
    import subprocess
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if result.returncode != 0:
        return ""
    return result.stdout


def _write_crontab(content: str) -> None:
    import subprocess
    proc = subprocess.run(["crontab", "-"], input=content, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())


def _crontab_install(hhmm: str) -> None:
    existing = _read_crontab()
    # Remove any existing XBookmarkMiner line (idempotent)
    lines = [ln for ln in existing.splitlines() if CRON_TAG not in ln]
    lines.append(_crontab_line(hhmm))
    _write_crontab("\n".join(lines) + "\n")


def _crontab_uninstall() -> None:
    existing = _read_crontab()
    filtered = [ln for ln in existing.splitlines() if CRON_TAG not in ln]
    if len(filtered) == len(existing.splitlines()):
        raise LookupError("No XBookmarkMiner cron entry found.")
    _write_crontab("\n".join(filtered) + "\n")


def _crontab_status() -> str:
    existing = _read_crontab()
    for ln in existing.splitlines():
        if CRON_TAG in ln:
            return ln
    return ""


# --- Public schedule commands ---

def cmd_schedule(hhmm: str) -> None:
    """Install the daily scheduled task/job for this machine."""
    if sys.platform == "win32":
        try:
            _schtasks_create(hhmm)
            print(f"[schedule] Daily task created: runs at {hhmm} every morning.")
            print(f"[schedule] Task name: {TASK_NAME}")
            print(f"[schedule] Script: {_script_path()}")
            print(f"[schedule] Run: --raw  (refreshes bookmarks_raw.md)")
            print(f"[schedule] To remove: py bookmark_scraper.py --unschedule")
        except Exception as e:
            print(f"[schedule] Failed to create task: {e}")
            print("[schedule] You can create it manually via Task Scheduler.")
            print(f"  Program: {_python_exe()}")
            print(f"  Arguments: \"{_script_path()}\" --raw")
    elif sys.platform == "darwin":
        try:
            _launchd_install(hhmm)
            print(f"[schedule] LaunchAgent installed: runs at {hhmm} every morning.")
            print(f"[schedule] Plist: {PLIST_PATH}")
            print(f"[schedule] To remove: python bookmark_scraper.py --unschedule")
        except Exception as e:
            print(f"[schedule] Failed to install LaunchAgent: {e}")
            print("[schedule] Manual cron fallback:")
            print(f"  Add to crontab:  {_crontab_line(hhmm)}")
    else:
        # Linux: try crontab, fall back to printing the line
        try:
            _crontab_install(hhmm)
            print(f"[schedule] Cron job installed: runs at {hhmm} every morning.")
            print(f"[schedule] Tag: {CRON_TAG}")
            print(f"[schedule] To remove: python bookmark_scraper.py --unschedule")
        except LookupError:
            # crontab -l returned non-zero (no existing crontab) — print manual line
            line = _crontab_line(hhmm)
            print("[schedule] Could not write crontab automatically.")
            print("[schedule] Add this line manually with: crontab -e")
            print(f"  {line}")
        except Exception as e:
            print(f"[schedule] Failed to write crontab: {e}")
            print("[schedule] Add this line manually with: crontab -e")
            print(f"  {_crontab_line(hhmm)}")


def cmd_unschedule() -> None:
    """Remove the daily scheduled task/job."""
    if sys.platform == "win32":
        try:
            _schtasks_delete()
            print(f"[unschedule] Task '{TASK_NAME}' removed.")
        except LookupError:
            print(f"[unschedule] No task named '{TASK_NAME}' found. Nothing to remove.")
        except Exception as e:
            print(f"[unschedule] Failed to remove task: {e}")
    elif sys.platform == "darwin":
        try:
            _launchd_uninstall()
            print(f"[unschedule] LaunchAgent '{PLIST_LABEL}' removed.")
        except LookupError:
            # Try crontab fallback
            try:
                _crontab_uninstall()
                print("[unschedule] Cron entry removed.")
            except LookupError:
                print("[unschedule] No scheduled task found (checked launchd and crontab).")
        except Exception as e:
            print(f"[unschedule] Failed: {e}")
    else:
        try:
            _crontab_uninstall()
            print("[unschedule] Cron entry removed.")
        except LookupError:
            print("[unschedule] No XBookmarkMiner cron entry found. Nothing to remove.")
        except Exception as e:
            print(f"[unschedule] Failed to update crontab: {e}")


def cmd_schedule_status() -> None:
    """Print current schedule status."""
    if sys.platform == "win32":
        info = _schtasks_query()
        if not info:
            print(f"[schedule-status] Not scheduled (no task named '{TASK_NAME}').")
            print("[schedule-status] Run: py bookmark_scraper.py --schedule 10:00")
            return
        # Extract Next Run Time line for a clean one-liner
        next_run = ""
        for ln in info.splitlines():
            if "Next Run Time" in ln or "Next Run" in ln:
                next_run = ln.strip()
                break
        print(f"[schedule-status] Task '{TASK_NAME}' is scheduled.")
        if next_run:
            print(f"[schedule-status] {next_run}")
        else:
            print(info)
    elif sys.platform == "darwin":
        status = _launchd_status()
        if status:
            print(f"[schedule-status] LaunchAgent '{PLIST_LABEL}' is active.")
            print(status)
        else:
            # Check crontab fallback
            ct = _crontab_status()
            if ct:
                print(f"[schedule-status] Cron entry found: {ct}")
            else:
                print(f"[schedule-status] Not scheduled.")
                print("[schedule-status] Run: python bookmark_scraper.py --schedule 10:00")
    else:
        ct = _crontab_status()
        if ct:
            print(f"[schedule-status] Cron entry: {ct}")
        else:
            print("[schedule-status] Not scheduled.")
            print("[schedule-status] Run: python bookmark_scraper.py --schedule 10:00")


# ─────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(
        prog="bookmark_scraper.py",
        description="x-bookmark-miner: turn your X/Twitter bookmarks into a searchable knowledge base",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python bookmark_scraper.py                     Scrape / resume
  python bookmark_scraper.py --reset             Wipe progress, start fresh
  python bookmark_scraper.py --rebuild           Rebuild markdown instantly
  python bookmark_scraper.py --rebuild --gemini  Rebuild + re-categorize with Gemini
  python bookmark_scraper.py --fix-unsure        Fix low-confidence categories with Gemini
  python bookmark_scraper.py --rescrape-articles Re-fetch empty article links
  python bookmark_scraper.py --rescrape-replies  Backfill author thread replies
  python bookmark_scraper.py --transcribe-videos Transcribe X native videos
  python bookmark_scraper.py --vision            Analyze images via local Ollama model
  python bookmark_scraper.py --search "query"    Semantic search your bookmarks
  python bookmark_scraper.py --raw               Output bookmarks_raw.md (no AI key, agent-native)
  python bookmark_scraper.py --demo              Run without cookies, see example output

Add --gemini to enable Gemini AI categorization (set GEMINI_API_KEY env var).
Add --debug for verbose output.
        """,
    )
    parser.add_argument("--reset", action="store_true", help="Wipe progress and start fresh")
    parser.add_argument("--rebuild", action="store_true", help="Rebuild markdown from saved data")
    parser.add_argument("--view", action="store_true", help="Alias for --rebuild --gemini")
    parser.add_argument("--fix-unsure", action="store_true", dest="fix_unsure",
                        help="Re-categorize low-confidence entries with Gemini")
    parser.add_argument("--rescrape-articles", action="store_true", dest="rescrape_articles",
                        help="Re-fetch article links that returned empty")
    parser.add_argument("--rescrape-replies", action="store_true", dest="rescrape_replies",
                        help="Backfill author thread replies for existing entries")
    parser.add_argument("--transcribe-videos", action="store_true", dest="transcribe_videos",
                        help="Transcribe X native videos (GPU if available, CPU fallback)")
    parser.add_argument("--vision", action="store_true",
                        help="Analyze images via local Ollama vision model")
    parser.add_argument("--search", metavar="QUERY", nargs="?", const="",
                        help="Semantic search bookmarks by meaning")
    parser.add_argument("--gemini", action="store_true", help="Enable Gemini AI categorization")
    parser.add_argument("--raw", action="store_true",
                        help="Output uncategorized markdown (bookmarks_raw.md) - no Gemini key needed. "
                             "Ideal for agent-native workflows: your Claude/Codex categorizes against your own profile.")
    parser.add_argument("--debug", action="store_true", help="Verbose debug output")
    parser.add_argument("--demo", action="store_true",
                        help="Run in demo mode without X cookies (shows example output)")
    parser.add_argument(
        "--schedule",
        metavar="HH:MM",
        nargs="?",
        const="10:00",
        help="Install a daily morning run (default 10:00 if no time given). "
             "Example: --schedule 07:30",
    )
    parser.add_argument(
        "--unschedule",
        action="store_true",
        help="Remove the previously installed daily schedule",
    )
    parser.add_argument(
        "--schedule-status",
        action="store_true",
        dest="schedule_status",
        help="Show whether a daily schedule is active and when it next runs",
    )

    args = parser.parse_args()
    global DEBUG
    DEBUG = args.debug

    # ── Scheduling commands (no cookies/progress file needed) ──
    if args.schedule_status:
        cmd_schedule_status()
        return

    if args.unschedule:
        cmd_unschedule()
        return

    if args.schedule is not None:
        try:
            hhmm = _parse_hhmm(args.schedule)
        except ValueError as e:
            print(f"[schedule] Invalid time: {e}")
            return
        cmd_schedule(hhmm)
        return

    if args.demo:
        demo_mode()
        return

    # --raw: rebuild (or scrape) then write uncategorized output for agent workflows
    if args.raw:
        if PROGRESS_FILE.exists():
            with open(PROGRESS_FILE, encoding="utf-8") as f:
                data = json.load(f)
            write_raw_markdown(data["entries"])
        else:
            print("[raw] No progress file found. Run the scraper first (without --raw), then run with --raw to generate the agent-native output.")
        return

    if args.reset:
        if PROGRESS_FILE.exists():
            PROGRESS_FILE.unlink()
            print("[reset] Progress cleared.\n")

    if args.rescrape_articles:
        if not PROGRESS_FILE.exists():
            print("[rescrape-articles] No progress file found. Run the scraper first.")
            return
        with open(PROGRESS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        data, n_tried, n_fixed = rescrape_articles(data)
        if n_tried == 0:
            print("\n[rescrape-articles] No empty X article URLs found.")
        else:
            save_progress(data)
            if args.gemini:
                data["entries"] = categorize_with_gemini(data["entries"])
                save_progress(data)
            write_markdown(data["entries"])
            print(f"\n[rescrape-articles] Done. {n_fixed}/{n_tried} articles fetched.")
        return

    if args.rescrape_replies:
        if not PROGRESS_FILE.exists():
            print("[rescrape-replies] No progress file found. Run the scraper first.")
            return
        with open(PROGRESS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        session = build_session()
        tweetdetail_qid = find_tweetdetail_query_id(session)
        if not tweetdetail_qid:
            print("[rescrape-replies] Cannot find TweetDetail query ID — aborting.")
            return
        data, n_tried, n_found = rescrape_replies(session, tweetdetail_qid, data)
        save_progress(data)
        write_markdown(data["entries"])
        print(f"\n[rescrape-replies] Done. {n_found}/{n_tried} entries got thread replies.")
        return

    if args.vision:
        if not PROGRESS_FILE.exists():
            print("[vision] No progress file found. Run the scraper first.")
            return
        with open(PROGRESS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        try:
            data, n_tried, n_done = vision_analyze(data)
        except KeyboardInterrupt:
            print("\n[paused] Progress saved.")
            save_progress(data)
            write_markdown(data["entries"])
            return
        save_progress(data)
        write_markdown(data["entries"])
        print(f"\n[vision] Done. {n_done}/{n_tried} images analyzed.")
        return

    if args.search is not None:
        if not PROGRESS_FILE.exists():
            print("[search] No progress file found. Run the scraper first.")
            return
        query = args.search
        if not query:
            query = input("[search] Enter search query: ").strip()
        if not query:
            print("[search] No query provided.")
            return
        with open(PROGRESS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        semantic_search(data, query)
        return

    if args.transcribe_videos:
        if not PROGRESS_FILE.exists():
            print("[transcribe-videos] No progress file found. Run the scraper first.")
            return
        with open(PROGRESS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        n_videos = sum(1 for e in data["entries"] if e.get("is_video") and not e.get("video_transcript"))
        if n_videos == 0:
            print("[transcribe-videos] No untranscribed videos found.")
            return
        print(f"[transcribe-videos] {n_videos} videos to transcribe.\n")
        try:
            data, n_tried, n_transcribed = transcribe_videos(data)
        except KeyboardInterrupt:
            print("\n[paused] Progress saved.")
            save_progress(data)
            write_markdown(data["entries"])
            return
        save_progress(data)
        write_markdown(data["entries"])
        print(f"\n[transcribe-videos] Done. {n_transcribed}/{n_tried} videos transcribed.")
        return

    if args.rebuild or args.view:
        if PROGRESS_FILE.exists():
            with open(PROGRESS_FILE, encoding="utf-8") as f:
                data = json.load(f)
            entries = data["entries"]
            if args.gemini or args.view:
                entries = categorize_with_gemini(entries)
                data["entries"] = entries
                save_progress(data)
            write_markdown(entries)
            n_unsure = sum(1 for e in entries if e.get("score", 1) == 0)
            print(f"[rebuild] Done. {len(entries)} entries, {n_unsure} low-confidence.")
        else:
            print("[rebuild] No progress file found.")
        return

    if args.fix_unsure:
        if PROGRESS_FILE.exists():
            with open(PROGRESS_FILE, encoding="utf-8") as f:
                data = json.load(f)
            entries = categorize_with_gemini(data["entries"], only_unsure=True)
            data["entries"] = entries
            save_progress(data)
            write_markdown(entries)
            n_still = sum(1 for e in entries if e.get("score", 1) == 0)
            print(f"[fix-unsure] Done. {n_still} entries still low-confidence.")
        else:
            print("[fix-unsure] No progress file found.")
        return

    # Default: scrape
    print("=" * 58)
    print("  x-bookmark-miner  (cookie mode)")
    print("  Ctrl+C anytime — auto-saves every 5 entries")
    print("=" * 58)
    print()

    progress = load_progress()
    session = build_session()
    user_id = get_user_id(session)
    query_id = find_query_id(session)
    tweetdetail_qid = find_tweetdetail_query_id(session)

    print(f"[user]  ID: {user_id}")
    print(f"[query] Bookmarks: {query_id}")
    print(f"[query] TweetDetail: {tweetdetail_qid or 'NOT FOUND (replies disabled)'}\n")

    try:
        entries = scrape(session, query_id, user_id, progress, tweetdetail_qid=tweetdetail_qid)
    except KeyboardInterrupt:
        print("\n[paused] Progress saved.")
        save_progress(progress)
        write_markdown(progress["entries"])
        entries = progress["entries"]

    n = len(entries)
    print(f"\n{'=' * 58}")
    print(f"  Done. {n} bookmarks scraped.")
    print(f"  Output  ->  {OUTPUT_MD.name}")
    print(f"  Re-run anytime to pick up new bookmarks.")
    print(f"{'=' * 58}\n")


if __name__ == "__main__":
    main()
