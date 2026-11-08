# Testing — question-tree v1.0.0

All figures below are from runs of this package on 8 November 2026 (macOS; Python 3.14.3, and Python 3.11.17 for the regression suite and fuzzer).

## Regression suite — `bash tests/test_qtree.sh`

**192 passed, 0 failed** on Python 3.14.3 and 3.11.17.

There is one test for each defect found during development across thirteen independent QA passes, plus a happy path through every command. Every test setup is asserted, so a setup that silently fails counts as a failure and cannot pass vacuously. The line `could not create the tree (No space left on device)` in the output is expected: one test simulates a full disk and checks that nothing is written.

## Fuzzer — `python3 tests/fuzz_qtree.py`

**200 runs, 11,852 operations, 0 failure classes**, on both Python versions.

The fuzzer drives random and guided command sequences and checks every state against an **independent oracle**: it re-implements the closure, staleness, pruning and plan rules without reusing any production predicate. It also forges and tampers with files. It prints coverage, so a run that never reaches a closed or ready tree is visibly worthless:

```
check closed(0/2) = 2587 · check refused = 9265 · ready passed = 882 · approve ok = 2423 · confirm ok = 283
```

It exits 3 if coverage is too thin to prove anything.

## Mutation tests — `python3 tests/mutate.py`

The script plants 42 deliberate bugs in a copy of `qtree.py`, one at a time. Each must be caught by the regression suite or the fuzzer. Expect about 45 minutes.

**Run of 8.11.2026: 39/42 killed.** The three survivors were examined:

| Mutant | Outcome |
|---|---|
| created date not validated | **Real gap.** `strptime` accepts `1.2.2026`, which the `dd.mm.yyyy` format rule rejects. Regression test 13.2 was added and now kills this mutant. |
| render path not checked | **Unreachable.** The loader refuses any path not ending in `.json` before the render guard is reached, so the guard is defence in depth. |
| save without validation | **No reachable path found.** The mutant survived all 192 regression tests and 200 fuzz runs, tamper scenarios included. The pre-save schema check is a backstop; no command sequence tried so far produces an invalid tree for it to catch. |

One further mutant (the approval-hash check) is excluded as equivalent, because approval is also bound to the revision number.

## Worked example — `bash examples/demo.sh`

The demo takes a limitation point from proposition to `ready`. Expected exits: `check` 1 (the critical answers have not yet been interrogated), then `check` 0, then `ready` 0. The statutory references in the demo (Limitation Act 1980 ss.5 and 14A(1)) were checked against legislation.gov.uk on 8.11.2026. The demo shows the mechanics only and is not legal advice.
