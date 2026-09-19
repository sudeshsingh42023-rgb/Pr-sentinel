"""CLI: review a diff, index repo conventions, run the benchmark."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .agents.convention_agent import ConventionIndex
from .config import Settings
from .orchestrator import format_markdown_review, review_diff


def _git_diff(base: str, head: str = "HEAD") -> str:
    return subprocess.check_output(["git", "diff", f"{base}...{head}"], text=True)


def cmd_review(args: argparse.Namespace) -> int:
    settings = Settings.load()
    diff_text = Path(args.diff_file).read_text() if args.diff_file else _git_diff(args.base, args.head)

    index = None
    index_path = Path(settings.repo.convention_index_path) / "index.json"
    if index_path.exists():
        index = ConventionIndex.load(index_path)

    result = review_diff(diff_text, args.intent or "", settings, convention_index=index)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(format_markdown_review(result))

    if args.fail_on_block and result["review"].get("should_block_merge"):
        return 1
    return 0


def cmd_index_conventions(args: argparse.Namespace) -> int:
    settings = Settings.load()
    index = ConventionIndex.build(args.repo)
    out_path = Path(settings.repo.convention_index_path) / "index.json"
    index.save(out_path)
    print(f"Indexed {len(index.snippets)} snippets from {args.repo} -> {out_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sentinel")
    sub = parser.add_subparsers(dest="command", required=True)

    p_review = sub.add_parser("review", help="review a diff")
    p_review.add_argument("--base", default="origin/main", help="base ref for git diff")
    p_review.add_argument("--head", default="HEAD")
    p_review.add_argument("--diff-file", help="review a saved .diff file instead of git")
    p_review.add_argument("--intent", help="PR title + description")
    p_review.add_argument("--json", action="store_true")
    p_review.add_argument("--fail-on-block", action="store_true",
                          help="exit 1 if severity meets the block threshold (for CI)")
    p_review.set_defaults(func=cmd_review)

    p_index = sub.add_parser("index-conventions", help="build the repo convention index")
    p_index.add_argument("--repo", default=".")
    p_index.set_defaults(func=cmd_index_conventions)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
