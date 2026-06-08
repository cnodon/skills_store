---
name: wechat-article-reader
description: Scrape a WeChat public account article (mp.weixin.qq.com URL), extract its core viewpoints and golden quotes, then generate a clean Markdown summary (default) or HTML report. Use this skill whenever the user provides a WeChat article URL (mp.weixin.qq.com/s/...) and wants it summarized, analyzed, "read for them," or saved locally, even if they don't say "WeChat" or "公众号" explicitly. Also trigger when the user pastes such a link and asks for "key points", "金句", "总结", "核心观点", or wants a markdown/HTML version.
---

# WeChat Article Reader

This skill turns a WeChat public account article into a structured summary file. **Markdown is the default output format** (filename matches the article title); HTML is available as an opt-in via `generate_html.py`. The summary contains:

1. **Article metadata** — title, author/account, publish date
2. **核心观点总结 (Core Viewpoint Summary)** — a tight 3–6 sentence overview of what the piece argues
3. **关键要点 (Key Points)** — 5–8 bullet points, the load-bearing ideas
4. **金句 (Golden Quotes)** — the most memorable / quotable sentences, lifted verbatim from the original
5. **(Optional) Original full text** — collapsed by default for reference (in MD: `<details>` block; in HTML: collapsible section)

The default output is one `.md` file named after the article title, saved to the current working directory (or a user-specified path). Use `generate_html.py` instead if the user explicitly asks for HTML.

## Workflow

### Step 1 — Fetch the article

Run the fetch script to download and parse the article into structured JSON:

```bash
python3 "$CLAUDE_SKILL_DIR/scripts/fetch_article.py" "<URL>" --out /tmp/wechat_article.json
```

(Or use the absolute path to this skill's `scripts/fetch_article.py` if `$CLAUDE_SKILL_DIR` is unset.)

The script writes JSON of shape:
```json
{
  "url": "...",
  "title": "...",
  "author": "...",
  "publish_time": "...",
  "content_text": "...",
  "content_html": "..."
}
```

If fetching fails, **do not fabricate content**. Try the fallbacks below in order.

#### Fetch fallbacks (when `fetch_article.py` fails)

WeChat aggressively blocks server-side fetches. Known failure modes and what works:

1. **`urlopen` returns 403 / `blocked-by-allowlist` / Tunnel Forbidden** — the host sandbox is blocking outbound to `mp.weixin.qq.com`. Retrying the script will not help. Skip to step 3 or 4.
2. **`WebFetch` returns an "环境异常 / 去验证" page** — WeChat's anti-bot challenge served the verification interstitial instead of the article. `WebFetch` cannot solve it. Skip to step 3 or 4.
3. **chrome-devtools MCP (preferred fallback).** Ask the user to launch Chrome with a debug port (one-line, isolated profile, leaves their normal browser alone):
   ```
   /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
     --remote-debugging-port=9222 --user-data-dir=$HOME/.chrome-debug
   ```
   Then drive it via MCP:
   - `mcp__chrome-devtools__new_page` with the article URL.
   - `mcp__chrome-devtools__evaluate_script` to extract straight from the live DOM:
     ```js
     () => {
       const title = (document.querySelector('#activity-name')?.innerText || document.title).trim();
       const author = (document.querySelector('#js_name')?.innerText || '').trim();
       const time = (document.querySelector('#publish_time')?.innerText || '').trim();
       const content = document.querySelector('#js_content');
       const clone = content.cloneNode(true);
       clone.querySelectorAll('script,style').forEach(e => e.remove());
       clone.querySelectorAll('br').forEach(b => b.replaceWith('\n'));
       const text = clone.innerText.replace(/ /g, ' ').replace(/\n{3,}/g, '\n\n').trim();
       return { title, author, time, text };
     }
     ```
   - Pass `filePath:` on `evaluate_script` to dump straight to disk if the payload is large, then assemble `/tmp/wechat_article.json` matching the shape above (`url`, `title`, `author`, `publish_time`, `content_text`, `content_html: ""`).
   - **Gotcha — embedded video.** If the article has a video player, `#js_content`'s `innerText` will include UI noise like `已关注 / 重播 / 倍速 / 视频地址：…`. Either strip a known noise block or leave it in `content_text` and ignore it during summarization — golden-quote verification still works because the rest of the body is verbatim.
   - `mcp__chrome-devtools__wait_for` against text like `"js_content"` may time out even when the article is fully rendered — don't rely on it. Just call `evaluate_script` directly; if `#js_content` is missing, the result will tell you.
4. **Ask the user to run the fetch script themselves.** If no Chrome MCP is reachable and they don't want to start one, the same script works fine outside the host sandbox:
   ```
   python3 /Users/parkeryuan/.claude/skills/wechat-article-reader/scripts/fetch_article.py \
     "<URL>" --out /tmp/wechat_article.json
   ```
   Then read `/tmp/wechat_article.json` and continue at step 2.

Do **not** try to install a headless browser (`pip install playwright`, `playwright install chromium`, etc.) as a workaround — the sandbox blocks pypi and the chrome-for-testing CDN, so the install itself will fail.

### Step 2 — Extract insights

Read the JSON. Then **you** (the model) produce:

- **summary**: 3–6 Chinese sentences capturing the central thesis. Be faithful, not promotional. Don't just restate the title.
- **key_points**: 5–8 bullets. Each bullet is one self-contained idea, not a section header. Prefer concrete claims over vague themes.
- **golden_quotes**: 3–8 quotes. **Lift them verbatim from the original text** — do not paraphrase, do not invent. Pick sentences that are either (a) the sharpest expression of an idea, (b) memorable phrasing, or (c) surprising/counterintuitive claims. If the article is dry and has no quotable lines, return fewer (or zero) rather than padding with mediocre ones.

Match the language of the article (Chinese articles → Chinese summary; English → English).

### Step 3 — Generate the output file

Save your extracted insights as JSON, then call the **Markdown** generator (default):

```bash
python3 "$CLAUDE_SKILL_DIR/scripts/generate_md.py" \
  --article /tmp/wechat_article.json \
  --insights /tmp/wechat_insights.json \
  --out "<article-title>.md"
```

If `--out` is omitted, the file is written to `./<safe-title-slug>.md` in the current working directory. The filename should mirror the article title (use the slugifier built into the script — it strips filesystem-forbidden chars but keeps CJK characters intact).

Only use `generate_html.py` (same flags, `.html` output) when the user explicitly asks for HTML.

The `insights.json` shape (same for both generators):
```json
{
  "summary": "...",
  "key_points": ["...", "..."],
  "golden_quotes": ["...", "..."]
}
```

The MD generator verifies that every golden quote is present verbatim in the article body (whitespace-insensitive). Quotes that don't match get a ⚠️ marker in the output and are listed on stderr — fix them rather than ignore.

### Step 4 — Report back

Tell the user the output file path and give a one-line preview of the summary so they know it worked. Don't dump the full summary into chat — the HTML is the deliverable.

## Notes

- **Don't invent quotes.** Golden quotes must be substrings of `content_text`. The generator will warn if a quote isn't found verbatim — investigate rather than ignore.
- **Don't translate the article unless asked.** Preserve the source language.
- **If the URL is not a WeChat article** (not on `mp.weixin.qq.com`), tell the user this skill is for WeChat articles specifically and ask whether to proceed anyway with a generic fetch.
- **Encoding**: WeChat serves UTF-8; the fetch script handles this. The generated HTML declares UTF-8 too.
