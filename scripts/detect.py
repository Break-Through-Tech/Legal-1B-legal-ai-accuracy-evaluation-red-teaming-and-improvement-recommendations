"""Run the end-to-end hallucination detector: python scripts/detect.py [--help]

Examples:
    python scripts/detect.py --evaluate          # all 200 benchmark docs, then the accuracy scorecard
    python scripts/detect.py doc-0001 doc-0136   # a subset
    python scripts/detect.py --input path/to/docx/folder

Writes data/processed/detect/{reports.jsonl, flags.jsonl, run-log.json} and logs/detect-<run_id>.log.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.detect import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
