#!/usr/bin/env bash
set -euo pipefail

# Apply labels using GitHub CLI.
#
# Requirements:
#   - gh installed + authenticated: gh auth login
#   - python3 available
#
# Usage:
#   ./apply_labels.sh OWNER/REPO supportdoc_rag_labels.json

REPO="${1:-}"
LABELS_FILE="${2:-supportdoc_rag_labels.json}"

if [[ -z "$REPO" ]]; then
  echo "Usage: $0 OWNER/REPO [labels.json]" >&2
  exit 1
fi

python3 apply_labels.py --repo "$REPO" --labels "$LABELS_FILE"
