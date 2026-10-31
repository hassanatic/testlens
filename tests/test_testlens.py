import textwrap

import pytest

from testlens import analysis
from testlens.cli import main, report
from testlens.junit import Result, parse
from testlens.signature import normalise, signature
from testlens.store import add_run, connect

PYTEST_XML = """<?xml version="1.0"?><testsuites><testsuite name="pytest">
<testcase classname="tests.test_a" name="test_ok" time="0.10"/>
<testcase classname="tests.test_a" name="test_bad" time="0.20"><failure message="AssertionError: expected 3, got 4">trace</failure></testcase>
<testcase classname="tests.test_a" name="test_skip" time="0"><skipped message="not on CI"/></testcase>
<testcase classname="tests.test_b" name="test_err" time="0.30"><error message="ConnectionError: port 5432 refused"/></testcase>
</testsuite></testsuites>"""

ROBOT_XML = """<?xml version="1.0"?><testsuite name="Framing" tests="2">
<testcase classname="Framing" name="Frames Arrive In Order" time="0.010"/>
<testcase classname="Framing" name="Corrupted Frame Is Skipped" time="0.020"><failure message="expected ['next'], got []"/></testcase>
</testsuite>"""


def test_parse_reads_pytest_and_robot_xunit(tmp_path):
    p, r = tmp_path / "p.xml", tmp_path / "r.xml"
    p.write_text(PYTEST_XML)
    r.write_text(ROBOT_XML)
    got = {x.test_id: x.outcome for x in parse(p) + parse(r)}
    assert got == {"tests.test_a::test_ok": "passed", "tests.test_a::test_bad": "failed",
                   "tests.test_a::test_skip": "skipped", "tests.test_b::test_err": "error",
                   "Framing::Frames Arrive In Order": "passed", "Framing::Corrupted Frame Is Skipped": "failed"}


def test_signature_ignores_the_parts_that_change_between_runs():
    a = "TimeoutError: no reply from 10.0.0.12 after 5.2 s (session 'a1b2')"
    b = "TimeoutError: no reply from 10.0.0.97 after 30 s (session 'ffee')"
    assert signature(a) == signature(b)
    assert normalise(a) == "TimeoutError: no reply from <n>.<n> after <time> (session <str>)"
    assert signature("AssertionError: x") != signature("TimeoutError: x")
    assert signature("") == ""


def R(t, outcome, msg="", d=0.1):
    return Result(t, outcome, d, msg)


@pytest.fixture
def history():
    conn = connect()
    # c1: all pass. c2: 'stable' still passes, 'flaky' fails once of two runs.
    # c3: 'broken' starts failing. c4: 'broken' still failing, 'new' starts failing.
    add_run(conn, "r1", "c1", 1, "ci", [R("stable", "passed"), R("flaky", "passed"), R("broken", "passed"), R("new", "passed")])
    add_run(conn, "r2", "c2", 2, "ci", [R("stable", "passed"), R("flaky", "failed", "Timeout after 3 s"), R("broken", "passed"), R("new", "passed")])
    add_run(conn, "r2b", "c2", 2, "ci", [R("flaky", "passed")])
    add_run(conn, "r3", "c3", 3, "ci", [R("stable", "passed"), R("flaky", "passed"), R("broken", "failed", "KeyError: 'id'"), R("new", "passed")])
    add_run(conn, "r4", "c4", 4, "ci", [R("stable", "passed", d=1.2), R("flaky", "passed"), R("broken", "failed", "KeyError: 'uid'"),
                                        R("new", "failed", "KeyError: 'name'")])
    return conn


def test_flaky_means_both_outcomes_on_one_commit(history):
    assert analysis.flaky_tests(history) == {"flaky": ["c2"]}


def test_first_failing_commit(history):
    assert analysis.first_failing_commit(history, "broken") == "c3"
    assert analysis.first_failing_commit(history, "new") == "c4"
    assert analysis.first_failing_commit(history, "stable") is None


def test_gate_blocks_only_on_new_failures(history):
    g = analysis.gate(history, "c4")
    assert g.new_failures == ["new"] and g.known_failures == ["broken"] and not g.passed
    g3 = analysis.gate(history, "c3")
    assert g3.new_failures == ["broken"]


def test_failures_with_one_cause_are_grouped(history):
    clusters = analysis.failure_clusters(history, "c4")
    assert len(clusters) == 1
    assert sorted(clusters[0].tests) == ["broken", "new"]
    assert clusters[0].text == "KeyError: <str>"


def test_slower_tests_compare_medians(history):
    assert analysis.slower_tests(history, "c4") == [("stable", 0.1, 1.2)]


def test_reingesting_a_run_replaces_it(history):
    add_run(history, "r4", "c4", 4, "ci", [R("new", "passed")])
    assert analysis.gate(history, "c4").passed


def test_cli_ingest_and_gate_exit_codes(tmp_path, capsys):
    db = str(tmp_path / "h.db")
    good = tmp_path / "good.xml"
    good.write_text('<testsuite name="s"><testcase classname="s" name="t" time="0.1"/></testsuite>')
    bad = tmp_path / "bad.xml"
    bad.write_text('<testsuite name="s"><testcase classname="s" name="t" time="0.1"><failure message="boom"/></testcase></testsuite>')
    assert main(["--db", db, "ingest", str(good), "--run", "1", "--commit", "a", "--seq", "1"]) == 0
    assert main(["--db", db, "gate", "--commit", "a"]) == 0
    assert main(["--db", db, "ingest", str(bad), "--run", "2", "--commit", "b", "--seq", "2"]) == 0
    assert main(["--db", db, "gate", "--commit", "b"]) == 1
    out = capsys.readouterr().out
    assert "## New failures" in out and "- s::t" in out


def test_report_lists_flaky_and_known(history):
    text = report(history, "c4")
    assert "Gate: FAIL (1 new, 1 already failing, 0 flaky)" in text
    assert "- broken (since c3)" in text
    assert "- flaky: c2" in text
