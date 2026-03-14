# SupportDoc RAG — Label Setup

This package includes:
- `supportdoc_rag_labels.json` — the label definitions
- `apply_labels.py` — applies labels using GitHub CLI (`gh`)
- `apply_labels.sh` — convenience wrapper

## Prereqs
1. Install GitHub CLI: https://cli.github.com/
2. Authenticate:
   ```bash
   gh auth login
   ```

## Apply to your repo
From this folder:
```bash
python3 apply_labels.py --repo OWNER/REPO --labels supportdoc_rag_labels.json
```

Or:
```bash
chmod +x apply_labels.sh
./apply_labels.sh OWNER/REPO supportdoc_rag_labels.json
```

## Notes
- The script uses `gh label create --force`, so it will **create or update** labels.
