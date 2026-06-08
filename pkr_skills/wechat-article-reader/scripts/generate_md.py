#!/usr/bin/env python3
"""Generate a Markdown summary from a fetched WeChat article + extracted insights.

Usage:
    python3 generate_md.py --article article.json --insights insights.json --out out.md

If --out is omitted, the file is written to ./<safe-title-slug>.md in CWD.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def slugify(title: str, maxlen: int = 80) -> str:
    # Keep CJK, alphanumerics, dashes; collapse whitespace and forbidden FS chars to '-'
    s = re.sub(r"[\\/:*?\"<>|\r\n\t]+", "-", title).strip()
    s = re.sub(r"\s+", " ", s)
    if len(s) > maxlen:
        s = s[:maxlen].rstrip()
    return s or "wechat-article"


def verify_quotes(quotes: list[str], body: str) -> list[tuple[str, bool]]:
    norm_body = re.sub(r"\s+", "", body)
    out = []
    for q in quotes:
        norm_q = re.sub(r"\s+", "", q)
        out.append((q, norm_q in norm_body))
    return out


def build_md(article: dict, insights: dict, include_original: bool = True) -> str:
    title = article.get("title", "").strip() or "(无标题)"
    author = article.get("author", "").strip()
    publish_time = article.get("publish_time", "").strip()
    url = article.get("url", "").strip()
    body_text = article.get("content_text", "")

    summary = insights.get("summary", "").strip()
    key_points = insights.get("key_points", []) or []
    quotes = insights.get("golden_quotes", []) or []

    verified = verify_quotes(quotes, body_text)

    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")

    meta_bits = []
    if author:
        meta_bits.append(f"**作者 / 公众号**：{author}")
    if publish_time:
        meta_bits.append(f"**发布时间**：{publish_time}")
    if url:
        meta_bits.append(f"**原文链接**：<{url}>")
    if meta_bits:
        lines.extend(meta_bits)
        lines.append("")

    lines.append("---")
    lines.append("")

    lines.append("## 📌 核心观点总结")
    lines.append("")
    lines.append(summary if summary else "_(未提供)_")
    lines.append("")

    lines.append("## 🔑 关键要点")
    lines.append("")
    if key_points:
        for i, kp in enumerate(key_points, 1):
            lines.append(f"{i}. {kp.strip()}")
    else:
        lines.append("_(未提供)_")
    lines.append("")

    lines.append("## 💬 金句摘录")
    lines.append("")
    if verified:
        for q, ok in verified:
            mark = "" if ok else " _(⚠️ 未在原文中找到精确匹配)_"
            lines.append(f"> {q.strip()}{mark}")
            lines.append("")
    else:
        lines.append("_(未提供)_")
        lines.append("")

    if include_original and body_text:
        lines.append("---")
        lines.append("")
        lines.append("<details>")
        lines.append("<summary>📄 原文全文（点击展开）</summary>")
        lines.append("")
        for para in body_text.split("\n\n"):
            para = para.strip()
            if para:
                lines.append(para)
                lines.append("")
        lines.append("</details>")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--article", required=True, help="path to article JSON from fetch_article.py")
    ap.add_argument("--insights", required=True, help="path to insights JSON")
    ap.add_argument("--out", default=None, help="output .md path (default: ./<title>.md)")
    ap.add_argument("--no-original", action="store_true", help="omit collapsed original-text block")
    args = ap.parse_args()

    article = json.loads(Path(args.article).read_text(encoding="utf-8"))
    insights = json.loads(Path(args.insights).read_text(encoding="utf-8"))

    md = build_md(article, insights, include_original=not args.no_original)

    if args.out:
        out_path = Path(args.out)
    else:
        out_path = Path.cwd() / f"{slugify(article.get('title', 'wechat-article'))}.md"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")

    # Report quote verification on stderr
    unverified = [q for q, ok in verify_quotes(insights.get("golden_quotes", []) or [], article.get("content_text", "")) if not ok]
    if unverified:
        print(f"WARN: {len(unverified)} golden quote(s) not found verbatim in article:", file=sys.stderr)
        for q in unverified:
            print(f"  - {q[:80]}...", file=sys.stderr)

    print(f"OK -> {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
