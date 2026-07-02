# x-bookmark-miner

![Python](https://img.shields.io/badge/python-3.10%2B-blue) ![License](https://img.shields.io/badge/license-MIT-green) ![No API key](https://img.shields.io/badge/no%20API%20key-required-brightgreen)

**Your X bookmarks are a goldmine. This tool mines them.**

Scrape every tweet you've ever bookmarked on X (Twitter) into a structured, searchable Markdown knowledge base — with article content, author threads, video transcripts, and AI categorization. All local. No API key required. Your cookies never leave your machine.

---

## Table of Contents

- [Use with Claude Code / Codex (recommended, zero keys)](#use-with-claude-code--codex-recommended-zero-keys)
- [What it produces](#what-it-produces)
- [Features](#features)
- [Quickstart](#quickstart)
- [All commands](#all-commands)
- [Optional features](#optional-features)
- [Configuration](#configuration)
- [Example output](#example-output)
- [Privacy](#privacy)
- [How it works](#how-it-works)
- [FAQ](#faq)
- [Troubleshooting](#troubleshooting)
- [Requirements](#requirements)
- [Contributing](#contributing)
- [License](#license)

---

## Use with Claude Code / Codex (recommended, zero keys)

> **Your bookmarks + your AI = a personal research analyst that knows your projects.**

The agent-native workflow skips the AI categorization step entirely. Instead, your own Claude Code or Codex reads your bookmarks *and* your profile — then surfaces what's actually relevant to *you*, matched to your real projects and interests.

**3 steps:**

**1. Clone and scrape:**
```bash
git clone https://github.com/jimbohedz/x-bookmark-miner.git
cd x-bookmark-miner
pip install requests
# export cookies → xcookies.json (see Quickstart)
python bookmark_scraper.py        # Run this first — scrapes your bookmarks
python bookmark_scraper.py --raw  # Then run this — writes bookmarks_raw.md (uncategorized, agent-ready)
```

> **Windows users:** use `py` instead of `python` (e.g. `py bookmark_scraper.py`)

**2. Copy the skill to your Claude Code setup:**
```bash
# macOS/Linux:
cp -r .claude/skills/bookmark-miner ~/.claude/skills/
# Windows (Command Prompt):
xcopy /E /I .claude\skills\bookmark-miner %USERPROFILE%\.claude\skills\bookmark-miner
```
Or paste `AGENTS_SNIPPET.md` into your `AGENTS.md` for Codex.

**3. Say "mine my bookmarks" to your AI.**

That's it. No Gemini key. No config. Your agent reads `bookmarks_raw.md`, reads your `CLAUDE.md` or `AGENTS.md`, and writes `FOR_YOU.md` — a personalized digest matched to your actual life.

### What FOR_YOU.md gives you

`FOR_YOU.md` is a curated digest, not a dump. Your AI cross-matches your bookmarks against your profile and produces sections like:

```
## For your trading system project

- @crypto_analyst: "BTC SMA200 confluence plays thread" — directly applies to your
  signal scoring work. The 3-TF alignment method he describes matches what you're building.
  → Read this before your next strategy session.

- @quant_dev: "Backtesting survival bias explainer" — relevant to your OOS validation phase.
  → Flag for your RESEARCH_METHOD doc.

## Your hiking research

- @ultralight_hiker: "PCT gear list for 2026" — you saved this when planning your summer trip.
  Matches: lightweight pack, nutrition strategy, permit logistics.
  → This belongs in your hiking project folder.

## Don't miss

- @indie_builder: "Zero to $10k MRR in 90 days" — high-signal thread on pricing and
  outreach. Relevant to every revenue pillar you're running.
```

### Persona examples

**Trader:** Saves crypto threads all week. Claude reads their trading system CLAUDE.md, finds
their signal scoring project, and surfaces the 4 bookmarked threads on backtest methodology
directly into that project's context — flagged as "read before next strategy session."

**Hiker:** Saves gear reviews and route tips. Claude reads their AGENTS.md, sees they're
planning a PCT section hike, and pulls every relevant bookmark into a "For your PCT prep"
section with links and key takeaways.

**Founder:** Saves SaaS threads, cold outreach tips, pricing experiments. Claude reads their
CLAUDE.md, sees they're in launch mode, and writes a digest of only the bookmarks that apply
to their current phase — with "this belongs in your pitch deck" callouts.

---

## What it produces

```
# X Bookmarks — Knowledge Base
Last updated: 2026-07-02 14:31
Total: 312 bookmarks | 89 with scraped content | 203 with author threads | 24 videos (6 transcribed)

## AI Tools & Prompts (93)
### @swyx
https://x.com/swyx/status/...

Here are 7 Claude Code tricks that changed how I build:

Author's thread:
[1] Start with a detailed CLAUDE.md. The model reads it on every session start.
[2] /compact is your best friend. Context quality drops past 30-40% capacity.
[3] Use hooks for automated actions — Claude Code runs them, not Claude.

Linked article: https://swyx.io/claude-code-tips
[full article text extracted here...]

---

## Trading/Crypto (166)
...
```

Every section is browsable, searchable, and ready to feed to any AI for Q&A, summaries, or action plans.

---

## Features

| Feature | What it does |
|---|---|
| **Self-healing GraphQL** | Auto-discovers X's rotating query IDs from JS bundles. Most scrapers break weekly. This one doesn't. |
| **4-layer article extraction** | t.co expansion → trafilatura → HTML fallback → Playwright for JS-rendered pages |
| **Author thread scraping** | Fetches the original poster's own reply thread below each bookmarked tweet |
| **X native video transcription** | yt-dlp + faster-whisper. GPU if available, CPU fallback. |
| **YouTube transcript extraction** | Auto-pulls transcripts from linked YouTube videos |
| **Agent-native raw output** | `--raw` flag: writes uncategorized `bookmarks_raw.md` — your AI categorizes it against your own profile |
| **AI categorization (optional)** | Gemini for smart categorization, keyword fallback if no API key |
| **Local semantic search** | Embed your bookmarks with nomic-embed-text (Ollama) and search by meaning |
| **Image analysis** | Extract text from infographic screenshots via local Ollama vision model |
| **Incremental resume** | Never re-scrapes. Ctrl+C safe. Saves every 5 entries. |
| **Custom categories** | Bring your own `categories.json` |

---

## Quickstart

**Step 1 — Install the core dependency:**

```bash
pip install requests
```

**Step 2 — Export your X cookies:**

1. Install the [Cookie-Editor](https://chromewebstore.google.com/detail/hlkenndednhfkekhgcdicdfddnkalmdm) extension in Chrome
2. Go to [x.com](https://x.com) — make sure you're logged in
3. Click Cookie-Editor → Export → **Export as JSON**
4. Save the file as `xcookies.json` in the same folder as the script

**Step 3 — Run:**

```bash
python bookmark_scraper.py
```

Output goes to `bookmarks_output.md`. That's it.

### Try it without cookies first

```bash
python bookmark_scraper.py --demo
```

Generates `demo_output.md` with example data so you can see exactly what you'll get.

---

## All commands

```bash
# Core
python bookmark_scraper.py                     # Scrape / resume from where you left off
python bookmark_scraper.py --reset             # Wipe progress and start fresh
python bookmark_scraper.py --rebuild           # Rebuild markdown from saved data (instant)
python bookmark_scraper.py --debug             # Verbose output (add to any command)
python bookmark_scraper.py --demo              # Preview output format without cookies

# Agent-native (zero API keys)
python bookmark_scraper.py --raw               # Write bookmarks_raw.md for your AI to personalize

# Enrich existing data
python bookmark_scraper.py --rescrape-articles  # Re-fetch article links that returned empty
python bookmark_scraper.py --rescrape-replies   # Backfill author thread replies
python bookmark_scraper.py --transcribe-videos  # Transcribe X native videos
python bookmark_scraper.py --vision             # Analyze images via local Ollama vision model
python bookmark_scraper.py --search "query"     # Semantic search by meaning

# AI categorization (needs GEMINI_API_KEY)
python bookmark_scraper.py --gemini             # Scrape + Gemini categorization
python bookmark_scraper.py --rebuild --gemini   # Rebuild with full Gemini re-categorization
python bookmark_scraper.py --fix-unsure         # Re-categorize low-confidence entries only

# Daily automation (self-installing)
python bookmark_scraper.py --schedule 10:00     # Install daily run at 10:00 AM
python bookmark_scraper.py --schedule-status    # Show next scheduled run
python bookmark_scraper.py --unschedule         # Remove the daily schedule
```

### Flag reference

| Flag | Requires | Output | Notes |
|---|---|---|---|
| *(none)* | xcookies.json | bookmarks_output.md | Scrape / resume |
| `--raw` | existing scrape | bookmarks_raw.md | Uncategorized, agent-native. Run default scrape first. |
| `--rebuild` | existing scrape | bookmarks_output.md | Instant rebuild from saved data |
| `--view` | GEMINI_API_KEY | bookmarks_output.md | Shortcut for --rebuild --gemini |
| `--gemini` | GEMINI_API_KEY | bookmarks_output.md | AI categorization via Gemini |
| `--fix-unsure` | GEMINI_API_KEY | bookmarks_output.md | Re-categorize low-confidence only |
| `--rescrape-articles` | existing scrape | updates progress | Re-fetch empty article links |
| `--rescrape-replies` | existing scrape | updates progress | Backfill author threads |
| `--transcribe-videos` | faster-whisper, yt-dlp | updates progress | GPU recommended |
| `--vision` | Ollama running | updates progress | Requires vision model (e.g. gemma3:12b) |
| `--search "query"` | Ollama + nomic-embed | terminal output | Semantic search |
| `--demo` | nothing | demo_output.md | Safe preview, no cookies |
| `--reset` | — | — | Clears progress, starts fresh |
| `--debug` | — | — | Verbose output, add to any command |
| `--schedule [HH:MM]` | — | — | Install daily run (default 10:00). No admin needed. |
| `--schedule-status` | — | terminal | Show next scheduled run time |
| `--unschedule` | — | — | Remove the daily schedule |

---

## Run it every morning

The core use case: doomscroll at night, bookmarks appear as a knowledge base every morning.

**One command installs the daily automation on any platform:**

```bash
py bookmark_scraper.py --schedule 10:00
```

That's it. The script registers itself as a scheduled task (Windows), LaunchAgent (macOS), or cron job (Linux) using the exact Python interpreter it is running under. No admin rights needed. No Task Scheduler GUI. No editing plist files.

```bash
# Check when it next runs
py bookmark_scraper.py --schedule-status

# Change the time (re-run --schedule with a new time — idempotent)
py bookmark_scraper.py --schedule 07:30

# Remove the schedule
py bookmark_scraper.py --unschedule
```

> Note: `--raw` requires an existing scrape (`bookmarks_progress.json`). Run the default scrape at least once first. After that, the scheduled run refreshes from your latest saved data — it's instant.

**Manual fallback (if the one-liner doesn't work for you)**

<details>
<summary>Windows — Task Scheduler GUI</summary>

1. Open Task Scheduler -> Create Basic Task
2. Name: "Bookmark Miner"
3. Trigger: Daily, 10:00 AM
4. Action: Start a program
   - Program: `C:\Python311\python.exe` (find yours: run `where py`)
   - Arguments: `bookmark_scraper.py --raw`
   - Start in: `C:\path\to\x-bookmark-miner`
5. Finish.

</details>

<details>
<summary>macOS — launchd plist (manual)</summary>

Create `~/Library/LaunchAgents/com.xbookmarkminer.daily.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.xbookmarkminer.daily</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>/path/to/x-bookmark-miner/bookmark_scraper.py</string>
    <string>--raw</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>10</integer><key>Minute</key><integer>0</integer></dict>
  <key>WorkingDirectory</key><string>/path/to/x-bookmark-miner</string>
</dict>
</plist>
```
Then: `launchctl load ~/Library/LaunchAgents/com.xbookmarkminer.daily.plist`

</details>

<details>
<summary>Linux — cron (manual)</summary>

```bash
crontab -e
# Add this line (runs at 10am daily):
0 10 * * * /path/to/python3 /path/to/bookmark_scraper.py --raw # XBookmarkMiner
```

</details>

---

## Optional features

Install only what you need:

```bash
# Better article text extraction
pip install trafilatura

# Scrape JS-rendered pages (X native articles, paywalled sites)
pip install playwright && playwright install chromium

# YouTube transcript extraction
pip install youtube-transcript-api

# X native video transcription (GPU recommended, CPU fallback included)
pip install faster-whisper yt-dlp imageio-ffmpeg

# Auto-read cookies from Chrome (no manual export, may need admin/sudo)
pip install browser-cookie3

# Config file support
pip install pyyaml

# Semantic search (also needs Ollama running locally)
# Install Ollama: https://ollama.com
# ollama pull nomic-embed-text
```

---

## Configuration

Copy `config.example.yaml` to `config.yaml` to customize paths, models, and categories:

```yaml
cookies_path: xcookies.json          # path to your cookie file
output_path: bookmarks_output.md     # where to write the knowledge base
whisper_model: medium                # tiny / base / small / medium / large-v3
whisper_device: auto                 # auto (detects GPU/CPU) | cuda | cpu
ollama_url: http://localhost:11434   # local Ollama server
vision_model: gemma3:12b             # for image analysis
delay_seconds: 1.5                   # polite delay between API calls
```

### Custom categories

Copy `categories.example.json` to `categories.json` and define your own:

```json
{
  "My Research": ["keyword one", "topic two"],
  "Work Projects": ["client name", "project keyword"]
}
```

### Gemini AI categorization (optional)

The tool works without any AI key. Keyword-based categorization handles most collections well.
If you want smarter categorization via Gemini:

Get a free key at [aistudio.google.com](https://aistudio.google.com/) and set it:

```bash
# Option A — environment variable
# macOS/Linux:
export GEMINI_API_KEY=your_key_here
# Windows (Command Prompt):
set GEMINI_API_KEY=your_key_here
# Windows (PowerShell):
$env:GEMINI_API_KEY="your_key_here"

# Option B — .env file (copy .env.example to .env)
GEMINI_API_KEY=your_key_here
```

Then run with `--gemini`. The agent-native `--raw` mode skips Gemini entirely.

---

## Example output

Below is a sanitized example showing what three bookmarks look like in the output file:

```markdown
## AI Tools & Prompts (93)

### @ai_researcher

https://x.com/ai_researcher/status/1234567890

The context window isn't the bottleneck. YOUR PROMPTING IS.
Here's how to get 10x better responses from any LLM (thread):

Author's thread:

[1] Stop writing vague instructions. Specificity is everything.
    Bad: "Write me a blog post"
    Good: "Write a 600-word blog post for senior Python devs on async patterns..."

[2] Use XML tags to separate sections. Claude especially loves this.
    <context>...</context><task>...</task><format>...</format>

[3] Show examples. One good example is worth 100 words of instruction.

Linked article: https://example.com/llm-prompting-guide

[Full article text extracted: 2,400 chars]
How to write better prompts for large language models...

---

## Trading/Crypto (166)

### @crypto_analyst  |  VIDEO

https://x.com/crypto_analyst/status/9876543210

BTC just broke a 6-month accumulation. Here's why this matters:

[X native video — transcript below]

Video transcript:

In this video I'm going to walk you through what just happened on the Bitcoin chart.
We've been in this tight range between 58k and 62k for almost six months now...

---

## Dev/Automation (45)

### @builder_dev

https://x.com/builder_dev/status/1122334455

Shipped a full Telegram notification bot in 90 minutes using n8n.
No server. No code. Just webhooks and JSON.

Author's thread:

[1] Step 1: Create a Webhook node in n8n. Set to POST. Copy the URL.
[2] Step 2: In Telegram, message @BotFather. /newbot. Get your token.
[3] Step 3: Add a Telegram node in n8n. Paste your token and chat ID.
[4] Step 4: Connect Webhook → Telegram. Done. Test it.

---
```

---

## Privacy

- **Your cookies stay local.** They are read from `xcookies.json` on your machine and used to make requests directly to X's API. They are never sent anywhere else.
- **Nothing is uploaded.** All data — bookmarks, progress, output — stays on your filesystem.
- **AI features are local-first.** Vision analysis and semantic search use Ollama running on your machine. Gemini categorization sends only tweet text (not cookies or personal info) to Google's API. It is optional.
- **Agent-native mode sends nothing.** `--raw` produces a local file. Your AI (Claude Code, Codex, Cursor) reads it locally. Zero data leaves your machine for categorization.
- **Open source.** The full source is in this repo. Read it.

---

## How it works

X's official API costs $100+/month for basic access. This tool uses the same internal GraphQL endpoints that your browser uses when you view your bookmarks — no paid API needed.

The trick is that X rotates the GraphQL query IDs with each deployment. Most scrapers hardcode these and break every few weeks. This tool **auto-discovers** the current query IDs by scanning X's JS bundles at runtime, with a fallback list of known working IDs. It only needs to find them once per session.

Data flow:
```
X GraphQL API
    → parse tweets (text, media, author)
    → expand t.co links → scrape linked articles
    → fetch author's reply threads
    → keyword categorize (or Gemini if enabled, or skip for --raw)
    → save to bookmarks_progress.json (incremental)
    → write bookmarks_output.md  (categorized)
    → write bookmarks_raw.md     (--raw: uncategorized, agent-native)
```

---

## FAQ

**Q: Will this get my account banned?**
A: This uses the same session your browser uses. It adds a polite 1.5s delay between requests. In over 6 months of use with 500+ bookmarks, no issues. That said: use it at your own risk, don't reduce the delay to zero, and don't run it on a bot account.

**Q: My query ID stopped working.**
A: X deploys code changes and rotates IDs. Run with `--debug` to see what's happening. If auto-discovery fails, open DevTools on `x.com/i/bookmarks`, filter Network for "Bookmarks", find the request URL, and copy the `queryId` from it. Add it to `KNOWN_QUERY_IDS` at the top of the script.

**Q: Can I run this without a GPU?**
A: Yes. Everything except `--transcribe-videos` works without a GPU. Video transcription uses `whisper_device: auto` which falls back to CPU automatically. CPU transcription with `medium` model takes roughly 5-10x longer.

**Q: Can I use a different AI for categorization?**
A: Yes. Edit `categorize_with_gemini()` in the script, or just use keyword-based categorization (the default), or use `--raw` and let your own Claude/Codex categorize against your profile.

**Q: The article content is empty.**
A: Some sites block scrapers or require JS. Install Playwright (`pip install playwright && playwright install chromium`) and run `--rescrape-articles` — it launches a headless browser with your X cookies to fetch JS-rendered pages.

**Q: How do I search my bookmarks?**
A: Three ways: (1) `grep -i "keyword" bookmarks_output.md` — it's just a text file. (2) `python bookmark_scraper.py --search "your question"` for semantic search (needs Ollama running with `nomic-embed-text`). (3) Say "what did I save about X" to your Claude/Codex after the agent-native setup.

**Q: Do I need Gemini / any AI key?**
A: No. Core scraping and keyword categorization need no API keys. `--raw` + agent-native workflow also needs no API keys. Gemini is optional for smarter standalone categorization.

**Q: Can I use this with Cursor / other AI IDEs?**
A: Yes. Copy `AGENTS_SNIPPET.md` into your `AGENTS.md`. The workflow is the same: scrape → `--raw` → your AI reads `bookmarks_raw.md` + your profile and writes `FOR_YOU.md`.

---

## Troubleshooting

**`[query_id] All known query IDs failed. Attempting auto-discovery...`**
X rotated their IDs. Auto-discovery usually fixes this. If it also fails, run `--debug` and follow the DevTools method in the FAQ above.

**`requests.exceptions.ConnectionError`**
Check your internet connection. X's API may also be briefly down — wait a few minutes and retry.

**Empty article content**
Install trafilatura for better extraction: `pip install trafilatura`. For JS-rendered sites, add Playwright: `pip install playwright && playwright install chromium`, then run `--rescrape-articles`.

**`bookmarks_raw.md: No progress file found`**
You need to run `python bookmark_scraper.py` first (without `--raw`) to scrape your bookmarks. Once you have `bookmarks_progress.json`, then run `--raw`.

**Slow transcription**
`--transcribe-videos` on CPU with `medium` model is slow (~5-10x realtime). Use `whisper_model: tiny` or `whisper_model: base` in `config.yaml` for faster CPU transcription. Or get a GPU.

**Cookie-Editor not showing Export as JSON**
Make sure you selected "JSON" format (not "Netscape"). The exported file should start with `[{`.

---

## Requirements

- Python 3.10+
- X account with bookmarks
- Chrome or Firefox with Cookie-Editor extension (for cookie export)
- Core: `pip install requests`
- Everything else is optional — install only what you need

---

## Contributing

PRs welcome. Key areas where help is useful:

- **Query ID resilience** — if X rotates IDs and auto-discovery fails, PRs with updated fallback IDs are the highest-value contribution
- **Article extraction** — sites that return empty content (paywalls, aggressive JS)
- **New output formats** — JSON export, Obsidian vault format, Notion import
- **Bug reports** — open an issue with your Python version, OS, and `--debug` output

Please do not submit PRs that add external API dependencies to the core scrape path. The zero-key default is a feature.

---

## License

MIT — do what you want, keep the attribution.

---

*Built for people who use X as a research tool and want their saved knowledge to be actually useful.*
