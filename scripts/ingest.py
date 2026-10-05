"""Build `data/processed/chunks.jsonl` from the downloaded handbook (`make ingest`)."""

import sys
from collections import Counter

from handbook_rag.access import load_access_config
from handbook_rag.ingest import CHUNKS_FILE, HANDBOOK_COMMIT_SHA, RAW_HANDBOOK_DIR
from handbook_rag.ingest.chunk import build_chunks


def main() -> None:
    head_file = RAW_HANDBOOK_DIR / ".git" / "HEAD"
    if not head_file.exists():
        sys.exit(f"{RAW_HANDBOOK_DIR} not found: run `make data` first")
    head = head_file.read_text().strip()
    if head != HANDBOOK_COMMIT_SHA:
        sys.exit(f"Checkout is at {head}, expected pinned {HANDBOOK_COMMIT_SHA}: run `make data`")

    chunks = build_chunks(RAW_HANDBOOK_DIR, load_access_config(), HANDBOOK_COMMIT_SHA)
    CHUNKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with CHUNKS_FILE.open("w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(chunk.model_dump_json() + "\n")

    counts = Counter((c.section, c.access_group) for c in chunks)
    print(f"{'section':<18}{'access_group':<14}{'chunks':>7}")
    for (section, group), n in sorted(counts.items()):
        print(f"{section:<18}{group:<14}{n:>7}")
    for group, n in sorted(Counter(c.access_group for c in chunks).items()):
        print(f"{'(all)':<18}{group:<14}{n:>7}")
    print(f"{'total':<32}{len(chunks):>7}  -> {CHUNKS_FILE}")


if __name__ == "__main__":
    main()
