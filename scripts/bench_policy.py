"""Score the bundled Nigerian/fictional policy corpus offline; no provider or network."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from agent.fakes import FakeDatabaseKeys
from agent.kb.evaluation import GoldenSet, evaluate, prepare_corpus
from agent.kb.library import PolicyLibrary
from agent.store.database import open_database

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write a JSON report instead of printing it")
    parser.add_argument(
        "--min-case-pass",
        type=float,
        default=None,
        help="Optional keyword-retrieval threshold, not the Phase D model-quality gate",
    )
    args = parser.parse_args()
    if args.min_case_pass is not None and not 0 <= args.min_case_pass <= 100:
        parser.error("--min-case-pass must be between zero and 100")
    try:
        golden = GoldenSet.model_validate_json(
            (ROOT / "tests/kb_questions/golden_set.json").read_bytes()
        )
        with TemporaryDirectory(prefix="aria-policy-eval-") as temporary:
            root = Path(temporary)
            corpus = prepare_corpus(ROOT, root / "sources")
            with open_database(root / "evaluation.db", FakeDatabaseKeys()) as database:
                report = evaluate(PolicyLibrary(corpus.folder, database), corpus, golden)
        text = json.dumps(report, indent=2) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(text)
        else:
            print(text, end="")
        if report["metrics"]["invalid_citations"]:
            return 1
        return int(
            args.min_case_pass is not None
            and report["metrics"]["case_pass_pct"] < args.min_case_pass
        )
    except Exception:  # noqa: BLE001 - safe even if fixtures/parser/storage fail
        print(
            "Policy evaluation failed; verify bundled sources, hashes and evidence labels.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
