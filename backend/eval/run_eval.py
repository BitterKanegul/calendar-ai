#!/usr/bin/env python3
"""
Calendar AI — Evaluation Framework CLI

Usage (from backend/ directory):
  python -m eval.run_eval                       # router + baseline, no judge
  python -m eval.run_eval --judge               # include LLM judge (costs tokens)
  python -m eval.run_eval --filter create list  # run only specific categories
  python -m eval.run_eval --output results/     # save JSON report to directory

The multi-agent evaluation runs the LangGraph router directly (no database or
Redis required).  The single-agent baseline calls GPT-4.1 via the OpenAI API.

Set OPENAI_API_KEY (and DATABASE_URL / SECRET_KEY for env loading) before running.
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# Ensure backend/ is on the path when run as a module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Load environment before importing config-dependent modules
from dotenv import load_dotenv
env = os.getenv("ENV", "development")
load_dotenv(dotenv_path=f".env.{env}", override=False)

from eval.runner.harness import run_harness
from eval.runner.report import print_summary, save_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DATASET_PATH = Path(__file__).parent / "dataset" / "test_cases.json"


def load_test_cases(categories: list[str] | None = None) -> list[dict]:
    with open(DATASET_PATH, encoding="utf-8") as f:
        cases = json.load(f)
    if categories:
        cases = [c for c in cases if c["category"] in categories]
    return cases


async def main(args: argparse.Namespace) -> None:
    test_cases = load_test_cases(args.filter or None)

    if not test_cases:
        logger.error("No test cases loaded (check --filter values).")
        sys.exit(1)

    logger.info(
        "Loaded %d test cases (categories: %s)",
        len(test_cases),
        ", ".join(sorted({c["category"] for c in test_cases})),
    )

    results = await run_harness(
        test_cases=test_cases,
        run_judge=args.judge,
        concurrency=args.concurrency,
    )

    print_summary(results)

    if args.output:
        out_dir = Path(args.output)
        out_dir.mkdir(parents=True, exist_ok=True)
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = out_dir / f"eval_report_{ts}.json"
        save_report(results, str(out_path))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Calendar AI Evaluation Framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--judge",
        action="store_true",
        default=False,
        help="Enable LLM-as-a-judge scoring (uses extra API calls)",
    )
    p.add_argument(
        "--filter",
        nargs="+",
        metavar="CATEGORY",
        choices=["create", "update", "delete", "list", "plan", "email", "message"],
        help="Run only these test case categories",
    )
    p.add_argument(
        "--output",
        metavar="DIR",
        default="eval/results",
        help="Directory to write JSON report (default: eval/results/)",
    )
    p.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="Max parallel API calls per system (default: 5)",
    )
    p.add_argument(
        "--list-cases",
        action="store_true",
        help="Print available test cases and exit",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if args.list_cases:
        cases = load_test_cases()
        print(f"\n{'ID':<22} {'Category':<10} Description")
        print("-" * 70)
        for c in cases:
            print(f"{c['id']:<22} {c['category']:<10} {c['description']}")
        print(f"\nTotal: {len(cases)} cases\n")
        sys.exit(0)

    asyncio.run(main(args))
