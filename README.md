# question-tree

Question-driven drafting for lawyers, as an agent skill.

Before a pleading, skeleton argument, advice or substantial letter is written, the agent builds a **question tree**. It states the proposition as an answer, generates every material follow-up question, answers each one with its evidence and authority, and treats each answer as a new proposition to interrogate. It stops only when a structural closure test passes. The lawyer reviews and approves the rendered tree; only then is prose written, from the tree's document plan, in answer-first order.

The method draws on four traditions:

- **Paul's six Socratic categories:** clarification, assumptions, evidence, viewpoints, implications, the question itself.
- **Walton-style critical questions** for each argument type: precedent, analogy, expert, statute, inference from evidence, consequences, sign.
- **Toulmin's argument model** for every answer: claim, grounds, warrant, qualifier, rebuttal.
- **Issue trees, MECE and pyramid order** for structure and stopping.

## What the store enforces

`qtree.py` is a single Python 3 file using the standard library only.

- A material answer of law needs an authority with a pinpoint, and an answer of fact needs its evidence. `[VERIFY]` in any slot counts as unsourced.
- A critical answer must itself be interrogated by at least one sourced follow-up.
- An answer that undermines the proposition blocks closure until it is rebutted or conceded. A concession is recorded in its drafted wording.
- Changing any answer marks every decided follow-up **stale** and clears approval.
- Approval binds to a deterministic render, checked byte for byte. A hand edit to the tree or the render is detected.
- Every tree file carries a SHA-256 integrity seal and is schema-validated on load and before every save.

`check` is structural. It cannot tell whether an answer is right; the lawyer's review does that.

## Install

Copy the folder into your skills directory, e.g. `~/.claude/skills/question-tree/`. There is nothing to install beyond Python 3 (standard library only; tested on 3.11 and 3.14).

```bash
python3 qtree.py -h
bash examples/demo.sh      # proposition → questions → answers → closure → approval → ready
```

## Tests

```bash
bash tests/test_qtree.sh          # regression suite
python3 tests/fuzz_qtree.py       # fuzzer against an independent oracle
python3 tests/mutate.py           # planted bugs the suites must catch (slow)
```

See `TESTING.md` for the results.

## Platform

macOS and Linux. The store uses `fcntl` file locking, so Windows needs WSL.

## Licence

MIT. See `LICENSE`.
