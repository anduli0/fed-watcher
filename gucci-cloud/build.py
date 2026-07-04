#!/usr/bin/env python3
"""Build gucci-cloud/artifact.html from the mirrored Gucci Intelligence site.

Takes gucci-mirror/index.html (the original SPA, untouched UI) and embeds all
mirrored API JSON so the app runs fully offline inside a Claude Artifact:
- strips document wrapper tags (the Artifact host supplies them)
- removes external font/manifest links (blocked by the Artifact CSP)
- replaces jget() network calls with lookups into an embedded data map
- adds a cloud-mirror banner with the data snapshot date

Usage: python3 gucci-cloud/build.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
MIRROR = ROOT / "gucci-mirror"
OUT = Path(__file__).parent / "artifact.html"

JGET_ORIG = "async function jget(u){ const r=await fetch(u.replace(/^\\//,'')); return r.json(); }"
JGET_SHIM = (
    "async function jget(u){ const k=u.replace(/^\\//,''); "
    "if(Object.prototype.hasOwnProperty.call(window.__EMBED,k)) "
    "return JSON.parse(JSON.stringify(window.__EMBED[k])); "
    "return {error:'cloud mirror: endpoint not captured'}; }"
)

ENDPOINTS = [
    "summary", "timeseries", "news", "luxury", "events", "products",
    "calendar", "ambassadors", "reports", "sov", "pool", "status", "runlog",
]


def main() -> int:
    html = (MIRROR / "index.html").read_text(encoding="utf-8")

    embed = {}
    for ep in ENDPOINTS:
        p = MIRROR / "api" / f"{ep}.json"
        if p.exists():
            embed[f"api/{ep}"] = json.loads(p.read_text(encoding="utf-8"))

    # Force viewer mode regardless of what the mirror captured.
    st = embed.get("api/status", {})
    st.update({"readonly": True, "running": False, "claude_available": False,
               "auth_error": False})
    embed["api/status"] = st
    embed.setdefault("api/runlog", {"lines": []})

    # Reports: api/report/<path> -> mirrored reports/<path with / -> _>.json
    reports = embed.get("api/reports", {}).get("reports", [])
    for r in reports:
        path = r.get("path", "")
        f = MIRROR / "reports" / (path.replace("/", "_") + ".json")
        if path and f.exists():
            embed[f"api/report/{path}"] = json.loads(f.read_text(encoding="utf-8"))

    snap = embed.get("api/summary", {}).get("date", "?")

    # --- strip document wrapper (Artifact host supplies its own) ---
    for pat in [r"<!DOCTYPE html>", r"<html[^>]*>", r"</html>",
                r"<head>", r"</head>", r"<body>", r"</body>"]:
        html = re.sub(pat, "", html, count=1)

    # --- remove CSP-blocked / irrelevant external links ---
    html = re.sub(r'<link rel="preconnect"[^>]*>\n?', "", html)
    html = re.sub(r'<link rel="stylesheet" href="https://[^"]*"[^>]*>\n?', "", html)
    html = re.sub(r'<link rel="apple-touch-icon"[^>]*>\n?', "", html)
    html = re.sub(r'<link rel="manifest"[^>]*>\n?', "", html)

    # --- swap network jget for embedded lookup ---
    if JGET_ORIG not in html:
        print("ERROR: jget signature not found — upstream index.html changed; "
              "update JGET_ORIG in build.py", file=sys.stderr)
        return 1
    html = html.replace(JGET_ORIG, JGET_SHIM)

    blob = json.dumps(embed, ensure_ascii=False).replace("</", "<\\/")
    inject = f"<script>window.__EMBED = {blob};</script>\n"

    # Embed map must be defined before the app script runs.
    idx = html.index("<script>")
    html = html[:idx] + inject + html[idx:]

    # --- cloud-mirror banner + belt-and-braces img fallback ---
    badge = (
        "\n<script>\n"
        "(function(){\n"
        "  var b=document.createElement('div');\n"
        "  b.style.cssText='padding:6px 26px;font-size:11px;color:#8a7440;"
        "border-bottom:1px solid #2e2a24;letter-spacing:.05em';\n"
        f"  b.textContent='\\u2601 CLOUD MIRROR \\u00b7 \\ub370\\uc774\\ud130 \\uc2a4\\ub0c5\\uc0f7 {snap} \\u00b7 PC\\uac00 \\ucf1c\\uc9c0\\uba74 \\uc790\\ub3d9 \\ub3d9\\uae30\\ud654';\n"
        "  var h=document.querySelector('header');\n"
        "  if(h) h.parentNode.insertBefore(b,h.nextSibling);\n"
        "  document.addEventListener('error',function(e){\n"
        "    if(e.target&&e.target.tagName==='IMG'&&!e.target.dataset.phDone){"
        "e.target.dataset.phDone=1;e.target.style.display='none';}\n"
        "  },true);\n"
        "})();\n"
        "</script>\n"
    )
    html = html + badge

    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT} ({len(html)} bytes, snapshot {snap}, "
          f"{len(embed)} embedded endpoints)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
