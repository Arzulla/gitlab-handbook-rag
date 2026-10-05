"""Shallow, sparse checkout of the GitLab Handbook at the pinned commit (`make data`).

Only the sections listed in `config/access.yaml` are checked out. The corpus lives in
`data/raw/handbook` (git-ignored) and is never committed. Safe to re-run.
"""

import subprocess
import sys
from pathlib import Path

from handbook_rag.access import load_access_config
from handbook_rag.ingest import HANDBOOK_COMMIT_SHA, HANDBOOK_REPO_URL, RAW_HANDBOOK_DIR
from handbook_rag.ingest.parse import CONTENT_ROOT, TOP_LEVEL_ONLY_SECTIONS


def sparse_patterns(sections: list[str]) -> list[str]:
    """Non-cone patterns: whole dir, or only top-level `.md` (`*` does not match `/`)."""
    return [
        f"/{CONTENT_ROOT}/{s}/*.md" if s in TOP_LEVEL_ONLY_SECTIONS else f"/{CONTENT_ROOT}/{s}/"
        for s in sorted(sections)
    ]


def git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", "-c", "advice.detachedHead=false", *args], cwd=cwd, check=True)


def main() -> None:
    dest = RAW_HANDBOOK_DIR
    patterns = sparse_patterns(list(load_access_config().sections))
    if not (dest / ".git").exists():
        dest.mkdir(parents=True, exist_ok=True)
        git("init", "--quiet", cwd=dest)
        git("remote", "add", "origin", HANDBOOK_REPO_URL, cwd=dest)
    git("sparse-checkout", "set", "--no-cone", *patterns, cwd=dest)
    git("fetch", "--depth=1", "--filter=blob:none", "origin", HANDBOOK_COMMIT_SHA, cwd=dest)
    git("checkout", "--quiet", "--detach", HANDBOOK_COMMIT_SHA, cwd=dest)
    n_files = sum(1 for _ in (dest / CONTENT_ROOT).rglob("*.md"))
    print(f"Handbook @ {HANDBOOK_COMMIT_SHA[:12]} -> {dest} ({n_files} markdown files)")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(f"git failed: {exc}")
