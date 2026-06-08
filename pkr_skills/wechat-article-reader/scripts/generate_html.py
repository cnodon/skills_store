#!/usr/bin/env python3
"""Render a WeChat article + extracted insights into a single HTML file."""
from __future__ import annotations

import argparse
import json
import re
import sys
from html import escape
from pathlib import Path


TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title_html} · 阅读笔记</title>
<style>
  :root {{
    --bg: #faf8f3;
    --surface: #ffffff;
    --ink: #1f1d1a;
    --muted: #6b6660;
    --line: #e6e1d6;
    --accent: #07c160;
    --quote-bg: #fff8e1;
    --quote-bar: #d49b00;
  }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; padding: 0; background: var(--bg); color: var(--ink); }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB",
                 "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif;
    line-height: 1.75; font-size: 17px;
  }}
  .wrap {{ max-width: 760px; margin: 0 auto; padding: 56px 24px 96px; }}
  header.meta {{ border-bottom: 1px solid var(--line); padding-bottom: 24px; margin-bottom: 32px; }}
  h1 {{ font-size: 30px; line-height: 1.3; margin: 0 0 12px; letter-spacing: -0.01em; }}
  .byline {{ color: var(--muted); font-size: 14px; }}
  .byline a {{ color: var(--muted); text-decoration: none; border-bottom: 1px dotted var(--muted); }}
  .byline .dot {{ margin: 0 8px; opacity: .5; }}
  section {{ margin: 36px 0; }}
  section h2 {{
    font-size: 13px; font-weight: 600; letter-spacing: .12em; text-transform: uppercase;
    color: var(--accent); margin: 0 0 14px;
  }}
  section h2 .zh {{ font-size: 18px; letter-spacing: 0; text-transform: none; color: var(--ink);
                   margin-left: 10px; font-weight: 600; }}
  .summary {{
    background: var(--surface); border: 1px solid var(--line); border-radius: 12px;
    padding: 22px 26px; font-size: 17px;
  }}
  ul.points {{ list-style: none; padding: 0; margin: 0; }}
  ul.points {{ counter-reset: pt; }}
  ul.points li {{
    background: var(--surface); border: 1px solid var(--line); border-radius: 10px;
    padding: 14px 18px 14px 48px; margin-bottom: 10px; position: relative;
  }}
  ul.points li::before {{
    content: counter(pt, decimal-leading-zero); counter-increment: pt;
    position: absolute; left: 16px; top: 14px; color: var(--accent);
    font-weight: 700; font-variant-numeric: tabular-nums; font-size: 14px;
  }}
  blockquote.quote {{
    margin: 0 0 14px; padding: 14px 20px; background: var(--quote-bg);
    border-left: 4px solid var(--quote-bar); border-radius: 4px;
    font-size: 17px; color: #4a3a00;
  }}
  blockquote.quote::before {{ content: "“"; font-size: 28px; color: var(--quote-bar);
    line-height: 0; vertical-align: -8px; margin-right: 4px; }}
  blockquote.quote::after  {{ content: "”"; font-size: 28px; color: var(--quote-bar);
    line-height: 0; vertical-align: -14px; margin-left: 4px; }}
  details.original {{ margin-top: 48px; border-top: 1px dashed var(--line); padding-top: 24px; }}
  details.original summary {{
    cursor: pointer; color: var(--muted); font-size: 14px; user-select: none;
  }}
  details.original .body {{ margin-top: 18px; color: #2a2925; }}
  details.original .body p {{ margin: 0 0 1em; }}
  footer.foot {{
    margin-top: 60px; padding-top: 20px; border-top: 1px solid var(--line);
    color: var(--muted); font-size: 13px; display: flex; justify-content: space-between;
    flex-wrap: wrap; gap: 8px;
  }}
  footer.foot a {{ color: var(--muted); }}
  .badge-missing {{
    display: inline-block; font-size: 11px; color: #b00; background: #fde7e7;
    padding: 1px 6px; border-radius: 4px; margin-left: 6px; vertical-align: 2px;
  }}
</style>
</head>
<body>
<div class="wrap">
  <header class="meta">
    <h1>{title_html}</h1>
    <div class="byline">
      {byline_html}
    </div>
  </header>

  <section>
    <h2>SUMMARY <span class="zh">核心观点总结</span></h2>
    <div class="summary">{summary_html}</div>
  </section>

  <section>
    <h2>KEY POINTS <span class="zh">关键要点</span></h2>
    <ul class="points">
      {points_html}
    </ul>
  </section>

  {quotes_section_html}

  <details class="original">
    <summary>展开原文（{char_count} 字）</summary>
    <div class="body">
      {original_html}
    </div>
  </details>

  <footer class="foot">
    <span>由 wechat-article-reader 生成</span>
    <a href="{url_html}" target="_blank" rel="noopener">查看原文 ↗</a>
  </footer>
</div>
</body>
</html>
"""


def slugify(s: str, fallback: str = "wechat-article") -> str:
    s = s.strip()
    if not s:
        return fallback
    s = re.sub(r"[\s\\/:*?\"<>|.,!?，。！？、（）()\[\]{}]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:60] or fallback


def render_summary(summary: str) -> str:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", summary.strip()) if p.strip()]
    if not paragraphs:
        return "<em>（未提供摘要）</em>"
    return "".join(f"<p>{escape(p)}</p>" for p in paragraphs)


def render_points(points: list[str]) -> str:
    if not points:
        return "<li><em>（未提取到要点）</em></li>"
    return "".join(f"<li>{escape(p.strip())}</li>" for p in points if p.strip())


def render_quotes(quotes: list[str], full_text: str) -> str:
    if not quotes:
        return ""
    lis = []
    for q in quotes:
        q = q.strip().strip("“”\"'")
        if not q:
            continue
        norm_q = re.sub(r"\s+", "", q)
        norm_src = re.sub(r"\s+", "", full_text)
        missing = norm_q not in norm_src
        badge = '<span class="badge-missing" title="该金句未在原文中匹配到">未匹配</span>' if missing else ""
        lis.append(f"<blockquote class=\"quote\">{escape(q)}{badge}</blockquote>")
    body = "\n      ".join(lis) if lis else "<em>（无金句）</em>"
    return (
        '<section>\n'
        '    <h2>GOLDEN QUOTES <span class="zh">金句摘录</span></h2>\n'
        f"    {body}\n"
        '  </section>'
    )


def render_original(text: str) -> str:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    return "\n      ".join(f"<p>{escape(p)}</p>" for p in paragraphs)


def render_byline(author: str, publish_time: str, url: str) -> str:
    parts = []
    if author:
        parts.append(f"<span>{escape(author)}</span>")
    if publish_time:
        parts.append(f"<span>{escape(publish_time)}</span>")
    parts.append(f'<a href="{escape(url)}" target="_blank" rel="noopener">原文链接</a>')
    return '<span class="dot">·</span>'.join(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--article", required=True)
    ap.add_argument("--insights", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    article = json.loads(Path(args.article).read_text(encoding="utf-8"))
    insights = json.loads(Path(args.insights).read_text(encoding="utf-8"))

    title = article.get("title") or "（无标题）"
    author = article.get("author") or ""
    publish_time = article.get("publish_time") or ""
    url = article.get("url") or ""
    full_text = article.get("content_text") or ""

    summary = insights.get("summary") or ""
    points = insights.get("key_points") or []
    quotes = insights.get("golden_quotes") or []

    html = TEMPLATE.format(
        title_html=escape(title),
        byline_html=render_byline(author, publish_time, url),
        summary_html=render_summary(summary),
        points_html=render_points(points),
        quotes_section_html=render_quotes(quotes, full_text),
        original_html=render_original(full_text),
        char_count=len(full_text),
        url_html=escape(url),
    )

    out_path = Path(args.out) if args.out else Path.cwd() / f"{slugify(title)}.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"WROTE: {out_path}", file=sys.stderr)
    print(out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
