# testlens

Turns JUnit XML from pytest and Robot Framework into a test history, so a red build
comes with answers: is this failure new, has the test been failing for a while, is it
flaky, when did it start, which failures share a cause, and what got slower.

I built it to practise the part of test engineering that comes after writing tests:
making the results useful during development. It is a small personal project.

## What it does

- **Ingest** one run's XML files (pytest `--junitxml`, Robot Framework `--xunit`) into
  SQLite with the commit and its position on the branch. Re-ingesting a run replaces it.
- **Flaky tests**: a test that both passed and failed on the same commit.
- **First failing commit**: for a test failing now, the first commit of its current run of
  consistent failures. A flaky commit stops the search instead of counting as a failure.
- **Failures grouped by cause**: failure messages are normalised (numbers, hex values, temp
  paths, UUIDs, quoted values and timings replaced) so the same root cause in different
  tests and runs lands in one group.
- **Slower tests**: median duration on this commit against the earlier median.
- **Gate** for CI: exits non-zero only for failures that are new on this commit and not
  flaky. A test that was already failing is reported but does not block every later merge.

## System under test

`sut/framing.py` is a framed serial protocol (start byte, length, payload,
CRC-16/CCITT-FALSE) with a streaming decoder that reassembles frames split across reads
and resynchronises after line noise or a corrupt frame. It is tested two ways: unit tests
in pytest (`sut/test_framing.py`, including the standard CRC check value) and acceptance
tests in Robot Framework (`robot/framing.robot` with a Python keyword library). CI runs
both and feeds their XML to testlens.

## Run it

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[test]"
pytest -q                                   # testlens and the system under test
pytest -q sut --junitxml=out/pytest.xml
PYTHONPATH=. robot --outputdir out --xunit robot.xml robot/framing.robot
testlens ingest out/pytest.xml out/robot.xml --run 1 --commit "$(git rev-parse --short HEAD)" --seq 1
testlens gate --commit "$(git rev-parse --short HEAD)"
```

## Limits

- The history lives in one SQLite file; in CI it would be kept as an artifact or a
  shared database between runs.
- Branch order comes from `--seq`; there is no git integration or bisecting.
- Normalisation rules are general-purpose and may need project-specific additions.

## Licence

MIT
