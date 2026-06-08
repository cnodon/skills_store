#!/usr/bin/env python3
"""Fetch a WeChat public-account article and dump structured JSON.

Usage:
    python3 fetch_article.py <url> [--out path.json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from html import unescape
from urllib.request import Request, urlopen


UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def fetch(url: str) -> str:
    req = Request(url, headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"})
    with urlopen(req, timeout=20) as resp:
        raw = resp.read()
    return raw.decode("utf-8", errors="replace")


def first(pattern: str, text: str, flags: int = re.S) -> str:
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else ""


def extract_meta(html: str) -> dict:
    title = first(r'<h1[^>]*id="activity-name"[^>]*>(.*?)</h1>', html)
    if not title:
        title = first(r'var\s+msg_title\s*=\s*["\']([^"\']+)["\']', html)
    if not title:
        title = first(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', html)
    title = unescape(re.sub(r"\s+", " ", title)).strip()

    author = first(r'<a[^>]*id="js_name"[^>]*>(.*?)</a>', html)
    if not author:
        author = first(r'var\s+nickname\s*=\s*["\']([^"\']+)["\']', html)
    if not author:
        author = first(r'<meta[^>]+property="og:site_name"[^>]+content="([^"]+)"', html)
    author = unescape(re.sub(r"\s+", " ", author)).strip()

    publish_time = first(r'var\s+publish_time\s*=\s*["\']([^"\']+)["\']', html)
    if not publish_time:
        publish_time = first(r'id="publish_time"[^>]*>([^<]+)<', html)
    publish_time = publish_time.strip()

    return {"title": title, "author": author, "publish_time": publish_time}


def extract_body(html: str) -> tuple[str, str]:
    m = re.search(
        r'<div[^>]*id="js_content"[^>]*>(.*?)</div>\s*<script',
        html,
        re.S,
    )
    if not m:
        m = re.search(r'<div[^>]*id="js_content"[^>]*>(.*?)</div>', html, re.S)
    body_html = m.group(1) if m else ""

    text = body_html
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", text, flags=re.S | re.I)
    text = re.sub(r"</(p|section|div|li|h[1-6]|blockquote)\s*>", "\n\n", text, flags=re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    lines = [re.sub(r"[ \t　]+", " ", ln).strip() for ln in text.splitlines()]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    return body_html.strip(), text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--out", default="-")
    args = ap.parse_args()

    try:
        html = fetch(args.url)
    except Exception as e:
        print(f"ERROR: failed to fetch {args.url}: {e}", file=sys.stderr)
        return 2

    meta = extract_meta(html)
    body_html, body_text = extract_body(html)

    if not body_text:
        print(
            "ERROR: could not locate article body (js_content). "
            "The article may be deleted, region-locked, or require verification.",
            file=sys.stderr,
        )
        return 3

    payload = {
        "url": args.url,
        "title": meta["title"],
        "author": meta["author"],
        "publish_time": meta["publish_time"],
        "content_text": body_text,
        "content_html": body_html,
    }

    out = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out == "-":
        print(out)
    else:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out)
        print(
            f"OK: title={meta['title']!r} author={meta['author']!r} "
            f"chars={len(body_text)} -> {args.out}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
