"""testlens ingest | report | gate"""

from __future__ import annotations

import argparse
import sys

from . import analysis
from .junit import parse
from .store import add_run, connect


def report(conn, commit_sha: str) -> str:
    g = analysis.gate(conn, commit_sha)
    lines = [f"# Test triage for {commit_sha}", ""]
    lines += [f"Gate: {'PASS' if g.passed else 'FAIL'} "
              f"({len(g.new_failures)} new, {len(g.known_failures)} already failing, "
              f"{len(g.flaky_failures)} flaky)", ""]
    if g.new_failures:
        lines += ["## New failures", ""] + [f"- {t}" for t in g.new_failures] + [""]
    if g.known_failures:
        lines += ["## Already failing", ""]
        lines += [f"- {t} (since {analysis.first_failing_commit(conn, t)})" for t in g.known_failures] + [""]
    flaky = analysis.flaky_tests(conn)
    if flaky:
        lines += ["## Flaky tests (passed and failed on the same commit)", ""]
        lines += [f"- {t}: {', '.join(c)}" for t, c in flaky.items()] + [""]
    clusters = analysis.failure_clusters(conn, commit_sha)
    if clusters:
        lines += ["## Failures grouped by cause", ""]
        for c in clusters:
            lines.append(f"- `{c.text}` ({len(c.tests)} tests): {', '.join(c.tests)}")
        lines.append("")
    slow = analysis.slower_tests(conn, commit_sha)
    if slow:
        lines += ["## Slower than before", ""]
        lines += [f"- {t}: {b}s -> {n}s" for t, b, n in slow] + [""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="testlens")
    ap.add_argument("--db", default="testlens.db")
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("ingest", help="store one run's JUnit XML")
    i.add_argument("xml", nargs="+")
    i.add_argument("--run", required=True)
    i.add_argument("--commit", required=True)
    i.add_argument("--seq", type=int, required=True, help="position of the commit on the branch")
    i.add_argument("--source", default="ci")
    for name in ("report", "gate"):
        p = sub.add_parser(name)
        p.add_argument("--commit", required=True)
    args = ap.parse_args(argv)
    conn = connect(args.db)

    if args.cmd == "ingest":
        results = [r for path in args.xml for r in parse(path)]
        n = add_run(conn, args.run, args.commit, args.seq, args.source, results)
        print(f"stored {n} results for run {args.run}")
        return 0
    if args.cmd == "report":
        print(report(conn, args.commit))
        return 0
    g = analysis.gate(conn, args.commit)
    print(report(conn, args.commit))
    return 0 if g.passed else 1


if __name__ == "__main__":
    sys.exit(main())
