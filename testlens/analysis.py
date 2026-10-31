"""Questions a test history can answer that a single red build cannot.

- Is this failure new, or has the test been failing for a while?
- Is the test flaky: did it both pass and fail on the same commit?
- When did it start failing: the first commit where it failed after last passing?
- Which failures share a root cause (same normalised message)?
- Which tests got slower?
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from statistics import median

FAIL = ("failed", "error")


def flaky_tests(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """Tests that both passed and failed on the same commit, with those commits."""
    rows = conn.execute(
        """SELECT r.test_id, ru.commit_sha
           FROM results r JOIN runs ru USING (run_id)
           WHERE r.outcome IN ('passed', 'failed', 'error')
           GROUP BY r.test_id, ru.commit_sha
           HAVING SUM(r.outcome = 'passed') > 0 AND SUM(r.outcome IN ('failed', 'error')) > 0
           ORDER BY r.test_id, MIN(ru.seq)""").fetchall()
    out: dict[str, list[str]] = {}
    for r in rows:
        out.setdefault(r["test_id"], []).append(r["commit_sha"])
    return out


def commit_outcomes(conn: sqlite3.Connection, test_id: str) -> list[tuple[int, str, str]]:
    """Per commit (in branch order): 'pass', 'fail' or 'mixed' for one test."""
    rows = conn.execute(
        """SELECT ru.seq, ru.commit_sha,
                  SUM(r.outcome = 'passed') AS p, SUM(r.outcome IN ('failed', 'error')) AS f
           FROM results r JOIN runs ru USING (run_id)
           WHERE r.test_id = ? AND r.outcome != 'skipped'
           GROUP BY ru.seq, ru.commit_sha ORDER BY ru.seq""", (test_id,)).fetchall()
    return [(r["seq"], r["commit_sha"], "mixed" if r["p"] and r["f"] else ("fail" if r["f"] else "pass"))
            for r in rows]


def first_failing_commit(conn: sqlite3.Connection, test_id: str) -> str | None:
    """The first commit of the current run of consistent failures, if the test is
    failing now. Mixed commits (flaky) break the search rather than count as a failure."""
    history = commit_outcomes(conn, test_id)
    if not history or history[-1][2] != "fail":
        return None
    first = None
    for _, sha, state in reversed(history):
        if state == "fail":
            first = sha
        else:
            break
    return first


@dataclass
class Cluster:
    signature: str
    text: str
    tests: list[str]
    occurrences: int


def failure_clusters(conn: sqlite3.Connection, commit_sha: str | None = None) -> list[Cluster]:
    where = "WHERE r.outcome IN ('failed', 'error')" + (" AND ru.commit_sha = ?" if commit_sha else "")
    rows = conn.execute(
        f"""SELECT r.sig, r.sig_text, r.test_id, COUNT(*) AS n
            FROM results r JOIN runs ru USING (run_id) {where}
            GROUP BY r.sig, r.test_id ORDER BY r.sig""", (commit_sha,) if commit_sha else ()).fetchall()
    clusters: dict[str, Cluster] = {}
    for r in rows:
        c = clusters.setdefault(r["sig"], Cluster(r["sig"], r["sig_text"], [], 0))
        c.tests.append(r["test_id"])
        c.occurrences += r["n"]
    return sorted(clusters.values(), key=lambda c: (-len(c.tests), -c.occurrences))


def slower_tests(conn: sqlite3.Connection, commit_sha: str, factor: float = 1.5,
                 min_seconds: float = 0.5) -> list[tuple[str, float, float]]:
    """Tests whose median duration on this commit is `factor` times their earlier median."""
    seq = conn.execute("SELECT MIN(seq) FROM runs WHERE commit_sha = ?", (commit_sha,)).fetchone()[0]
    if seq is None:
        return []
    out = []
    for (test_id,) in conn.execute(
            "SELECT DISTINCT test_id FROM results r JOIN runs ru USING (run_id) WHERE ru.commit_sha = ?",
            (commit_sha,)).fetchall():
        def durations(cond):
            return [r[0] for r in conn.execute(
                f"""SELECT duration FROM results r JOIN runs ru USING (run_id)
                    WHERE r.test_id = ? AND r.outcome = 'passed' AND {cond}""", (test_id, seq)).fetchall()]
        before, now = durations("ru.seq < ?"), durations("ru.seq = ?")
        if before and now:
            b, n = median(before), median(now)
            if n >= min_seconds and n >= factor * b:
                out.append((test_id, round(b, 3), round(n, 3)))
    return sorted(out, key=lambda x: -x[2] / max(x[1], 1e-9))


@dataclass
class Gate:
    commit_sha: str
    new_failures: list[str]
    known_failures: list[str]
    flaky_failures: list[str]

    @property
    def passed(self) -> bool:
        return not self.new_failures


def gate(conn: sqlite3.Connection, commit_sha: str) -> Gate:
    """Fail only on failures that are new on this commit and not explained by flakiness:
    a test already failing before this commit is reported but does not block again."""
    failing = [r["test_id"] for r in conn.execute(
        """SELECT DISTINCT r.test_id FROM results r JOIN runs ru USING (run_id)
           WHERE ru.commit_sha = ? AND r.outcome IN ('failed', 'error') ORDER BY r.test_id""",
        (commit_sha,)).fetchall()]
    flaky = flaky_tests(conn)
    new, known, flaky_now = [], [], []
    for t in failing:
        if t in flaky:
            flaky_now.append(t)
        elif first_failing_commit(conn, t) == commit_sha:
            new.append(t)
        else:
            known.append(t)
    return Gate(commit_sha, new, known, flaky_now)
