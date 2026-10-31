"""Read JUnit XML as written by pytest (--junitxml) and Robot Framework (--xunit).

Both use <testsuite>/<testcase> with <failure>, <error> and <skipped> children; pytest
wraps suites in <testsuites>. Anything else in the file is ignored."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Result:
    test_id: str
    outcome: str          # passed | failed | error | skipped
    duration: float
    message: str


def parse(path: str | Path) -> list[Result]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else root.iter("testsuite")
    out = []
    for suite in suites:
        for case in suite.iter("testcase"):
            classname = case.get("classname") or suite.get("name") or ""
            test_id = f"{classname}::{case.get('name')}" if classname else case.get("name", "")
            outcome, message = "passed", ""
            for tag in ("failure", "error", "skipped"):
                el = case.find(tag)
                if el is not None:
                    outcome = {"failure": "failed", "error": "error", "skipped": "skipped"}[tag]
                    message = (el.get("message") or el.text or "").strip()
                    break
            out.append(Result(test_id, outcome, float(case.get("time") or 0), message))
    return out
