---
name: gemini-gen-image
description: Generate images via Google Gemini's "nano banana" model (Gemini 2.5/3 Flash Image) by driving gemini.google.com in Chrome via the chrome-devtools MCP, then save and display the result inline. Use this skill whenever the user wants to create, generate, make, draw, or render an image, picture, illustration, poster, icon, logo, or any visual artwork — even if they don't mention Gemini by name. Also use when the user provides a short visual description and clearly expects an image back. Default save path is $TMPDIR.
---

# gemini-gen-image

Generate images by driving Chrome via the `chrome-devtools` MCP against gemini.google.com. Optimizes the prompt, automates the chat UI, extracts the image via canvas, saves to `$TMPDIR`, and displays it inline using the `Read` tool.

## Pre-flight: Chrome must be running with remote debugging

**Always check first** with `mcp__chrome-devtools__list_pages`. If it returns a connection error, ask the user to run this command in a terminal and wait for Chrome to open:

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/chrome-debug-profile
```

**Why `--user-data-dir=/tmp/chrome-debug-profile`**: Using the original Chrome profile (`~/Library/Application Support/Google/Chrome`) may cause a bus error crash on some machines due to binary hooks (e.g. Dobby). A fresh temp profile avoids this. The user will need to log into Google in the new window — remind them if needed.

Once Chrome is open, `list_pages` should succeed. The new Chrome window often opens `gemini.google.com` automatically, but if not, navigate there in step 2.

## Step 1 — Prompt optimization

Rewrite the user's description into a single dense English paragraph (40–120 words) covering:

1. **Subject** — who/what, pose, expression, key props
2. **Composition** — shot type (close-up / wide / overhead), framing
3. **Style** — medium (Pixar 3D render, anime, oil paint, photo, etc.)
4. **Lighting** — direction, quality (soft / harsh / golden hour)
5. **Color & mood** — palette, atmosphere
6. **Quality cues** — "highly detailed", "sharp focus" — only if they fit the style

Rules:
- Preserve every concrete detail the user gave.
- Always write in **English** regardless of the user's language — Gemini image model performs best in English.
- Don't add safety filler. Gemini handles policy itself.
- Show the optimized prompt to the user before sending so they can redirect.

## Step 2 — Drive Chrome via chrome-devtools MCP

Concrete, tested flow:

### 2a. Connect and navigate
```
mcp__chrome-devtools__list_pages          → get pageId
mcp__chrome-devtools__select_page         → select it
mcp__chrome-devtools__navigate_page       → type: "url", url: "https://gemini.google.com/app"
```

### 2b. Find and use the input box
```
mcp__chrome-devtools__take_snapshot       → find textbox uid (role="textbox", placeholder contains "Gemini")
mcp__chrome-devtools__click               → uid of the textbox
mcp__chrome-devtools__type_text           → text: "<optimized prompt>", submitKey: "Enter"
```

### 2c. Wait for the image to appear
```
mcp__chrome-devtools__wait_for            → text: ["Download", "Generated image"], timeout: 90000
```
This is the most reliable way to detect completion. The snapshot after `wait_for` will contain the download button uid and the generated `img` element.

### 2d. Extract the image via canvas (DO NOT use the Download button or fetch blob URLs)

**Do not click the Download button** — when using a temp profile, the file lands in an inaccessible folder.  
**Do not use `fetch(blob_url)`** — Gemini serves images as `blob:` URLs which cannot be fetched from JS context.

Instead, use the canvas approach:

```
mcp__chrome-devtools__evaluate_script     →
  function: () => {
    const img = [...document.querySelectorAll('img')]
      .filter(i => i.naturalWidth > 200)[0];
    const canvas = document.createElement('canvas');
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    canvas.getContext('2d').drawImage(img, 0, 0);
    return canvas.toDataURL('image/png');
  }
  filePath: "/tmp/gemini-image-b64.json"
```

The `filePath` parameter saves the result (a JSON-encoded base64 data URL string) to disk.

## Step 3 — Decode and save the image

Use a Bash Python one-liner to decode the base64 JSON and write the PNG. **Always use `os.environ.get('TMPDIR')` for the output path** — `~/Downloads` and `/tmp` may be write-protected by the sandbox.

```bash
python3 -c "
import json, base64, os
with open('/tmp/gemini-image-b64.json') as f:
    data = json.load(f)
header, b64 = data.split(',', 1)
img_bytes = base64.b64decode(b64)
tmpdir = os.environ.get('TMPDIR', '/tmp')
slug = 'SLUG-HERE'   # 4-6 word kebab-case slug from user's intent
date = 'YYYYMMDD'    # today's date
out = os.path.join(tmpdir, f'{slug}-{date}.png')
with open(out, 'wb') as f:
    f.write(img_bytes)
print(out)
"
```

Replace `SLUG-HERE` and `YYYYMMDD` with the actual values before running.

## Step 4 — Display and report

After saving, use the `Read` tool on the saved path to display the image **inline** in the conversation:

```
Read → file_path: "/tmp/claude-502/your-image.png"   (path printed by the Python script)
```

Then report to the user:
- The saved path as a clickable markdown link
- The optimized prompt (one line for easy iteration)
- One follow-up offer: "Want a variation, different style, or aspect ratio?"

Keep the report to 3–5 lines.

## Failure modes & recovery

| Situation | Action |
|-----------|--------|
| `list_pages` connection error | Ask user to run the Chrome launch command above |
| Chrome login screen / consent | Screenshot and ask user to log in, then retry |
| New temp profile, not logged in | Tell user to log into Google in the Chrome window |
| Gemini refuses the prompt | Show refusal text verbatim, suggest milder rewording, ask before retrying |
| No image after 90s | Screenshot the page; try again with "Generate an image of …" prefix |
| `canvas.toDataURL` returns blank | The image may still be loading — wait 5s and retry the canvas script |
| Multiple images generated | Run canvas script for each `img[naturalWidth > 200]`, save with `-1`, `-2` suffixes |
| Python write permission error | Check `echo $TMPDIR` in Bash and use that exact path |

## What not to do

- Don't click the "Download full size image" button — the file goes to the temp profile's download folder which is not accessible.
- Don't use `fetch(blob_url)` in JS — blob URLs from Gemini are not fetchable.
- Don't write to `~/Downloads` or `/tmp` directly — use `$TMPDIR` (the sandbox-writable temp dir).
- Don't use the original Chrome user data dir (`~/Library/Application Support/Google/Chrome`) — may crash on some machines.
- Don't call any external image API.
- Don't loop generating variations unless the user asks.
