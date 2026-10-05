"""Ingest: GitLab Handbook markdown -> chunks with an `access_group`."""

from pathlib import Path

HANDBOOK_REPO_URL = "https://gitlab.com/gitlab-com/content-sites/handbook.git"
# Pinned so every run (and every eval) sees the same corpus. Bump deliberately.
HANDBOOK_COMMIT_SHA = "9e86f098ae65daef23f14ddf0e7d8172bd565a6b"

RAW_HANDBOOK_DIR = Path("data/raw/handbook")
CHUNKS_FILE = Path("data/processed/chunks.jsonl")
