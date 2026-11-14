"""Index/search policies offline. --demo uses fictional sources and a temporary encrypted cache."""

import argparse
import json
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from agent.fakes import FakeDatabaseKeys
from agent.kb.library import PolicyLibrary, SearchInput
from agent.security.keys import OSVaultKeyProvider
from agent.store.database import open_database


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--query")
    parser.add_argument("--year", type=int)
    parser.add_argument("--circular-no")
    parser.add_argument(
        "--newest", action="store_true", help="List matches by issue date instead of relevance"
    )
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    if args.demo and (args.library or args.database or args.watch):
        parser.error("--demo uses only the bundled fictional library and a temporary cache")
    if not args.demo and (args.library is None or args.database is None):
        parser.error("Choose --library and --database, or --demo")
    if args.watch and args.query:
        parser.error("--watch maintains the index; run queries in another process")
    try:
        with TemporaryDirectory(prefix="aria-policy-demo-") as temporary:
            folder = (
                Path(__file__).resolve().parents[5] / "library/policies"
                if args.demo
                else args.library
            )
            path = Path(temporary) / "policy.db" if args.demo else args.database
            if path.resolve().is_relative_to(folder.resolve()):
                raise ValueError("The cache must be outside the policy folder")
            keys = FakeDatabaseKeys() if args.demo else OSVaultKeyProvider()
            with open_database(path, keys) as database:
                library = PolicyLibrary(folder, database)
                while True:
                    status = library.refresh()
                    output = (
                        library.search(
                            SearchInput(
                                query=args.query,
                                year=args.year,
                                circular_no=args.circular_no,
                                sort="newest" if args.newest else "relevance",
                            )
                        )
                        if args.query
                        else status
                    )
                    print(
                        json.dumps(output.model_dump(mode="json", exclude={"sources"}), indent=2),
                        flush=True,
                    )
                    if not args.watch:
                        return 1 if status.failed else 0
                    time.sleep(5)
    except KeyboardInterrupt:
        return 0
    except Exception:  # noqa: BLE001 - paths and native diagnostics stay private
        print(
            "Policy search failed. Check the folder, manifest and encrypted cache.", file=sys.stderr
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
