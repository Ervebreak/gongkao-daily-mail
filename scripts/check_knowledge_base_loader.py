from __future__ import annotations

import logging
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from knowledge_base_loader import (  # noqa: E402
    load_policy_all,
    load_policy_core,
    load_qiushi_article_index,
    load_qiushi_chunks,
    load_qiushi_quotes_candidates,
    load_qiushi_quotes_core,
    load_topic_frameworks,
)


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s:%(name)s:%(message)s")
    loaders = [
        ("policy_core", load_policy_core),
        ("policy_all", load_policy_all),
        ("qiushi_article_index", load_qiushi_article_index),
        ("qiushi_chunks", load_qiushi_chunks),
        ("qiushi_quotes_core", load_qiushi_quotes_core),
        ("qiushi_quotes_candidates", load_qiushi_quotes_candidates),
        ("topic_frameworks", load_topic_frameworks),
    ]
    for name, loader in loaders:
        print(f"{name}: {len(loader())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
