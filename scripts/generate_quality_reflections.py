from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quality_reflections import generate_quality_reflections


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate structured quality reflections from latest nightly artifacts.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Artifacts directory. Defaults to OUTPUT_DIR.")
    parser.add_argument("--knowledge-dir", type=Path, default=ROOT / "knowledge")
    parser.add_argument("--blocked-run-dir", type=Path, default=None, help="Optional blocked run directory override.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.output_dir is None:
        from config import settings

        output_dir = settings.output_dir
    else:
        output_dir = args.output_dir
    payload = generate_quality_reflections(
        output_dir=output_dir,
        knowledge_dir=args.knowledge_dir,
        blocked_run_dir=args.blocked_run_dir,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
