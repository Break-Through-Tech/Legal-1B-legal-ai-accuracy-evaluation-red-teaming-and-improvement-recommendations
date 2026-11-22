"""Run the detector regression set: python scripts/run_regression.py."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.regression import DEFAULT_CASES, run_regression  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run fixture-driven detector regressions.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    args = parser.parse_args(argv)

    results = run_regression(args.cases)
    failed = [result for result in results if result["failures"]]
    for result in results:
        status = "PASS" if not result["failures"] else "FAIL"
        print(f"{status} {result['id']} ({result['category']})")
        for failure in result["failures"]:
            print(f"  - {failure}")

    print(f"\n{len(results) - len(failed)}/{len(results)} regression cases passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
