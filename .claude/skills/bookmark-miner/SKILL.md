---
name: bookmark-miner
description: >
  Mine, organize, and personalize your X bookmarks using your own AI — no extra API keys.
  Use when asked to: "mine my bookmarks", "organize my bookmarks", "what did I save about X",
  "bookmark digest", "categorize my bookmarks", "what bookmarks do I have on [topic]",
  "surface bookmarks for my project", "build my knowledge base from bookmarks".
argument-hint: [topic or project to focus on, optional]
allowed-tools: Read, Grep, Glob, Bash
---

# Bookmark Miner — Agent-Native Workflow

You are acting as the user's personal research analyst. You will mine their X bookmarks,
read their own profile to understand their interests and projects, then produce a personalized
digest matched to what actually matters to them.

**CRITICAL: Never read bookmarks_output.md or bookmarks_raw.md entirely into context.**
They can be 1MB+. Always use Grep or Read with section limits.

---

## Step 1 — Run the scraper (or use existing output)

Check if a fresh raw output exists (less than 24 hours old):

```bash
# Check last modified time of raw output
python -c "import os,time; f='bookmarks_raw.md'; print(f'exists={os.path.exists(f)}, age_hours={(time.time()-os.path.getmtime(f))/3600:.1f}' if os.path.exists(f) else 'not found')"
```

If the file is fresh (under 24h), skip to Step 2. Otherwise run:

```bash
python bookmark_scraper.py --raw
```

This outputs `bookmarks_raw.md` — all scraped bookmarks, uncategorized, ready for the agent.
No Gemini key needed.

> **Note:** The commands above assume `bookmark_scraper.py` is in your current working directory.
> If you installed it elsewhere, either set `output_path` in `config.yaml` to an absolute path
> (e.g. `/home/you/bookmarks_raw.md`) so the output lands in a predictable location, or run the
> script by full path: `python /path/to/x-bookmark-miner/bookmark_scraper.py --raw`.

---

## Step 2 — Read the user's profile

Find and read whatever profile file exists (check in this order):

1. `CLAUDE.md` in the current project
2. `~/.claude/CLAUDE.md` (global)
3. `AGENTS.md` in the current project
4. `~/.config/AGENTS.md`

Extract from the profile:
- Active projects and their goals
- Topics the user cares about (hobbies, interests, domains)
- Current focus / priority
- Any explicit "I want to know more about X" signals

If no profile file exists: ask the user "What are your main interests and active projects?"
before continuing.

---

## Step 3 — Scan bookmarks by interest area

For each interest/project extracted from the profile, grep the raw output:

```
Grep pattern="<keyword>" path="bookmarks_raw.md" output_mode="content" -C=3
```

Use 2-3 keyword variants per topic (e.g., "hiking" → also "trail", "outdoor", "hike").
For each topic, collect the top 3-5 most relevant entries.

Do NOT read the entire file. Work section by section via targeted searches.

---

## Step 4 — Write FOR_YOU.md

Write a personalized digest to `FOR_YOU.md` in the current directory.

Structure:

```markdown
# Your Bookmark Digest — [date]

*Personalized against your profile. [N] bookmarks scanned.*

---

## For your [Project Name] project

[2-4 bookmarks most relevant to this project]
- Why it's relevant: [1 line]
- Actionable: [what they could do with this]

## [Interest Area 1]

[2-4 bookmarks]

## [Interest Area 2]

[2-4 bookmarks]

---

## Worth your attention (don't miss these)

[2-3 high-signal saves that don't fit a category but are exceptional]

---

## Full bookmarks_raw.md

The full unsorted list is in bookmarks_raw.md.
Search it: Grep pattern="<topic>" path="bookmarks_raw.md" output_mode="content" -C=3
```

---

## Example invocations

**"Mine my bookmarks"**
→ Run full workflow: scrape (if stale) → read profile → write FOR_YOU.md

**"What did I save about trading systems?"**
→ Skip to Step 3: Grep bookmarks_raw.md for "trading", "signal", "strategy", "backtest"
→ Return top 5 results with context, no FOR_YOU.md needed

**"Bookmark digest for my hiking project"**
→ Read profile to confirm project exists → grep "hiking", "trail", "gear", "route"
→ Write a focused FOR_YOU.md section for just that project

---

## Notes

- bookmarks_raw.md is the agent-native file. bookmarks_output.md (if it exists) is the
  keyword-categorized version — use it if raw is unavailable, but same rules apply: Grep only.
- If $ARGUMENTS was provided, treat it as the primary topic/project to focus on.
- After writing FOR_YOU.md, tell the user: how many bookmarks were scanned, how many
  matched their interests, and 1 "you'll want to see this" highlight.
