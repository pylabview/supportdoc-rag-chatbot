#!/usr/bin/env python3
"""Apply labels from a JSON file to a GitHub repo using GitHub CLI (gh).

Requirements:
  - GitHub CLI installed: https://cli.github.com/
  - Authenticated: `gh auth login`

Usage:
  python apply_labels.py --repo OWNER/REPO --labels supportdoc_rag_labels.json

Notes:
  - Uses `gh label create --force` so existing labels are updated in-place.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.check_call(cmd)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="GitHub repo in OWNER/REPO form.")
    ap.add_argument("--labels", required=True, help="Path to labels JSON file.")
    args = ap.parse_args()

    labels_path = Path(args.labels)
    labels = json.loads(labels_path.read_text(encoding="utf-8"))

    for lb in labels:
        name = lb["name"]
        color = lb.get("color", "ededed")
        desc = lb.get("description", "")
        cmd = [
            "gh",
            "label",
            "create",
            name,
            "--repo",
            args.repo,
            "--color",
            color,
            "--description",
            desc,
            "--force",
        ]
        run(cmd)

    print("\nDone. Labels applied to", args.repo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
