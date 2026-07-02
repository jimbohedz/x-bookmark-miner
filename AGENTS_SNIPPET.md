# AGENTS.md Snippet — x-bookmark-miner

Paste this into your `AGENTS.md` (project root) or `~/.config/AGENTS.md` (global) to give
Codex and other OpenAI Agents SDK-compatible tools the bookmark-miner workflow.

---

```markdown
## Bookmark Miner (x-bookmark-miner)

Tool location: `bookmark_scraper.py` in this project root.

### When to run
Trigger this workflow when the user says any of:
- "mine my bookmarks"
- "organize my bookmarks"
- "what did I save about [topic]"
- "bookmark digest"
- "surface bookmarks for my [project]"
- "what bookmarks do I have on [topic]"

### Workflow

1. **Check for fresh output** (under 24h):
   ```
   python bookmark_scraper.py --raw
   ```
   This writes `bookmarks_raw.md` — all scraped bookmarks, uncategorized, no AI key needed.
   Skip if `bookmarks_raw.md` exists and was modified in the last 24 hours.

2. **Read the user's profile** — look for `AGENTS.md`, `CLAUDE.md`, or `README.md` in the
   project. Extract: active projects, interests, current focus. This is what you personalize against.

3. **Search bookmarks by interest** — use grep/search on `bookmarks_raw.md` for 2-3 keywords
   per interest area. **Never read the whole file** — it can be 1MB+.

4. **Write `FOR_YOU.md`** — a personalized digest with sections per project/interest:
   - Which bookmarks match this project and why
   - What's actionable from each save
   - "Don't miss" highlights for high-signal saves that don't fit categories

### Concrete example
User profile says they love hiking and are building a SaaS product.
- Grep `bookmarks_raw.md` for: "hiking", "trail", "gear", "outdoor"
- Grep for: "saas", "product", "launch", "revenue", "indie"
- Write FOR_YOU.md with two sections: "For your hiking research" and "For your SaaS build"
- In each section: bookmark URL, tweet text, why it's relevant, what to do with it

### Output files
| File | What it is |
|---|---|
| `bookmarks_raw.md` | All bookmarks, uncategorized, full content. Agent's working input. |
| `FOR_YOU.md` | Personalized digest you write. User reads this. |

### Rules
- NEVER read bookmarks_raw.md entirely into context. Always grep/slice by topic.
- Always cross-match against the user's actual profile — generic categorization is not the goal.
- If no profile exists, ask: "What are your main interests and active projects?"
```

---

## Installation

1. Copy the block above into your `AGENTS.md`
2. Clone or copy `bookmark_scraper.py` into your project
3. Run `python bookmark_scraper.py --raw` once to generate `bookmarks_raw.md`
4. Say "mine my bookmarks" to your agent

No API keys required. Your agent does the categorization.
