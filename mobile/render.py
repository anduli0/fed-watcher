#!/usr/bin/env python3
"""Render mobile/dashboard.html from mobile/data.json + mobile/template.html.

Usage: python3 mobile/render.py
The output file is what gets deployed as the Claude Artifact.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
REQUIRED = [
    "updated_at_kst", "next_update_kst", "policy_rate", "next_fomc",
    "meeting_probs", "hawk_dove_score", "stance", "horizons", "macro",
    "briefing", "history", "sources",
]


def main() -> int:
    data = json.loads((HERE / "data.json").read_text(encoding="utf-8"))
    missing = [k for k in REQUIRED if k not in data]
    if missing:
        print(f"data.json missing keys: {missing}", file=sys.stderr)
        return 1
    for h in ("6m", "12m", "3y", "10y"):
        if h not in data["horizons"]:
            print(f"data.json horizons missing {h}", file=sys.stderr)
            return 1

    template = (HERE / "template.html").read_text(encoding="utf-8")
    blob = json.dumps(data, ensure_ascii=False)
    # Keep </script> inside JSON strings from terminating the script tag.
    blob = blob.replace("</", "<\\/")
    html = template.replace("__DATA_JSON__", blob)
    out = HERE / "dashboard.html"
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({len(html)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
