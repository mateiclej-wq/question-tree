---
name: question-tree
description: "Question-driven drafting for lawyers. Before a pleading, skeleton argument, advice or substantial letter is written, build a question tree: state the proposition as an answer, generate every material follow-up question (Paul's six Socratic categories, Walton-style critical questions, and the opponent's, the court's and the client's questions), answer each in Toulmin slots (answer, evidence, authority, qualifier, rebuttal), and treat each answer as a new proposition to interrogate until a structural closure test passes. The reviewer approves the rendered tree before any prose is written; the tree is then linearised into the document in answer-first order, with peripheral answers kept as a reserve for oral argument. Stdlib-only Python store with integrity seal, staleness tracking and byte-exact approval. Modes: draft (the AI answers, the lawyer reviews) and tutor (the AI asks, the lawyer answers). Triggers: 'question tree', 'Socratic draft', 'answer every question first'."
argument-hint: "[proposition] [--doc slug] [--mode draft|tutor]"
metadata:
  author: "Matei Clej"
  license: "mit"
  version: "1.0.0"
---

# Question tree: question-driven drafting

A legal document is a chain of answers to questions the reader will ask. Most drafting failures are questions nobody asked before the prose was written: the assumption no one tested, the authority no one checked for later treatment, the opponent's best point met only in a footnote. This skill makes the questions come first.

It runs in a loop: state a proposition, extract the questions it raises, answer each one, and repeat until no material question is left. Four traditions fix the gaps in the raw loop:

- **Question generator.** Paul's six Socratic categories, plus Walton-style critical questions per argument type. See `questions.md`.
- **Answer shape.** Toulmin: claim, grounds, warrant, qualifier, rebuttal.
- **Structure and stopping.** Issue tree, MECE (mutually exclusive, collectively exhaustive), pyramid (answer-first) order.
- **Discipline.** Every answer rests on a primary source opened in the task: the evidence read in full, the authority read at the pinpoint, never a summary or recollection.

## The store

`qtree.py` (Python 3, standard library only) keeps the tree as JSON plus a rendered `.md`. Run `python3 qtree.py -h` for every command.

```bash
python3 qtree.py init  <work_dir> --root "<proposition>" --doc <slug> [--mode draft]
python3 qtree.py add-many <file> Q0 --json '[{"q":"…","gen":"paul:assumptions","mat":3}]'
python3 qtree.py open  <file>                       # what is left, most material first
python3 qtree.py answer <file> Q1 --type law --a "…" --warrant "<authority + pinpoint>" --effect supports
python3 qtree.py check <file>                       # 0 closed · 2 closed within budget · 1 not closed
python3 qtree.py place <file> Q1 --section "Ground 1" --order 1
python3 qtree.py render <file> && python3 qtree.py approve <file>
python3 qtree.py ready <file>                       # 0 = draft from the Document plan
```

Follow-up questions take hierarchical ids (`Q1.1`, `Q1.2`, `Q1.1.1`). `examples/demo.sh` takes a small limitation point from proposition to `ready`. Keep the tree in a working directory outside anything that will be served or filed.

- **Integrity seal.** Every tree file carries a SHA-256 seal of its content. A file changed outside qtree is refused on load, so **change a tree only through qtree commands**. Behind the seal, full schema and semantic validation (reachability, field types, decision requirements) means a forged file is refused with a message rather than crashing the tool. Every save is validated first, so no command can write an invalid tree.
- **Literal rendering.** User text is rendered with HTML and Markdown syntax shown literally, so a citation such as `[6](b)` reads exactly as typed and cannot forge a heading.
- **State model.** Each question stores its own *decision* (OPEN, ANSWERED, CONCEDED, OUT_OF_SCOPE, IMMATERIAL, DUPLICATE, BLOCKED, DEFERRED) and a *stale* flag. PRUNED is derived, never stored: a question is pruned while any question above it is closed as CONCEDED, OUT_OF_SCOPE, IMMATERIAL or DUPLICATE. `status <id>` shows the derived state.

## Precedence (which rule wins)

1. **The deadline and the protective step win.** When time is short, skip the tree, or run it at `--depth 2 --threshold 3 --budget-min 30` on the critical points only. Draft at once and record what is still open in the draft's cover note. Only the *tree* shrinks; the reading of the evidence and the review of the document do not.
2. **Then the source rules.** Read the primary evidence in full, and confirm you hold every document the matter turns on, before generating questions. Questions generated from a summary are summary-shaped.
3. **Then the tree.** Use the budgets: `--budget-min` (default 120) and `--max-nodes` (default 60). When either is exceeded, stop expanding, close the remaining material items as `DEFERRED --reason "budget: …"`, and proceed. `check` exits 2 ("closed within budget") and lists the residue.

## Mode (ask once per task)

1. **Draft** (default). The AI generates and answers. The lawyer reviews the rendered tree **before** any prose is written.
2. **Tutor** (opt-in). The AI asks no more than five questions per batch, critical branches only unless asked for more. The lawyer answers. The AI records the answers, sources them and generates the follow-ups. A "hint" names where to look, not what it says.

## Procedure

**0. Gates.** Settle the strategy: what finding or order the document seeks. Confirm the source set is complete. Read the primary evidence in full.

**1. Root.** Write the proposition **as an answer**, not a topic: the finding or order sought.

**2. First ring.** Generate questions:
- all six Paul categories;
- the Walton families that fit the arguments in play;
- at least one `opp` and one `court` question.

Merge overlaps (MECE) and assign materiality (`questions.md` §4). Use `add-many` with one JSON list. It is atomic and idempotent: an identical retry changes nothing and keeps approval. A re-add with a *different* generator or materiality is refused; `reclass <id> --mat N --gen …` changes them deliberately.

**3. Answer.** Work from `qtree.py open`, which is breadth-first with critical questions first. Each answer declares:
- `--type fact` needs `--grounds` (the fact plus where it is in the evidence);
- `--type law` needs `--warrant` (authority plus pinpoint, **opened in this task**);
- `--type mixed` needs both.

Each answer also takes `--effect supports|undermines|neutral` against the proposition, and optionally `--qualifier` and `--rebuttal`. `[VERIFY]` in **any** slot counts as unsourced, and an unverified rebuttal does not meet an undermining answer. Anything **placed in the document plan** must meet these standards, even a peripheral answer. Re-answering **replaces every slot**; omitted slots are emptied. **Any** change to an answer's substance makes **every decided follow-up STALE**, including closures whose pruned branches are restored for review, and clears approval. After re-review, `confirm <id>` keeps the stale question's own decision exactly as it was; otherwise re-answer or close it again. `reopen <id>` undoes a closure and marks the follow-ups stale.

Close a question without answering it only with a stated basis:
- `CONCEDED --concession "<exact conceded proposition, as drafted>"`: the abandoned answer is archived to history and never exported.
- `OUT_OF_SCOPE --reason …` / `IMMATERIAL --reason …`
- `DUPLICATE --of <id>`: "answered at <id>". The target must be a current, sound answer or concession outside this question's own lineage, never another duplicate, and **no deeper** than this question, so no obligation is carried downward. The target takes the highest materiality of the questions pointing at it, so a critical question cannot be downgraded by pointing it at a peripheral one. If the target later changes, the duplicate goes STALE.
- `BLOCKED --reason "[VERIFY] …"`: a source could not be reached. Never answer from recollection.
- `DEFERRED --reason "budget: …"`

**4. Recurse.** Each answer is a new proposition. Ask of it the questions it raises, especially `assumptions`, `evidence` and the matching Walton family.

**5. Closure.** `qtree.py check` exits 1 (not closed) while any of the following is true:
- a material question within the depth cap is OPEN or STALE;
- a material answer lacks the support its type requires;
- a material question is BLOCKED;
- a material answer UNDERMINES the proposition with no rebuttal (concede it, rebut it, or revisit the strategy);
- a critical answer has no follow-up that is a sourced answer or a concession;
- no first-ring answer SUPPORTS the proposition.

It exits 2 when closed within budget, listing the residue for the draft's cover note. The check is **structural**: it cannot tell whether an answer is right. The lawyer's review does that.

**6. Document plan.** Assign each material answer to a heading with `place <id> --section "<heading>" --order N`. The root is always rendered first as the **Conclusion**, with its qualifier. Headings follow the *document's* logic (the grounds, the issues, the order the court decides them), not the order of the interrogation. One answer serves one section; a shared premise is placed once and cross-referred.

**7. Review gate.** Run `render`; the lawyer reviews the tree and the document plan; then `approve`. The render is **deterministic** (no timestamps or approval state), and `ready` requires the file on disk to equal a fresh render byte for byte, so any hand edit is detected. Approval binds to the render on disk, and any later substantive edit clears it. **Never approve on the lawyer's behalf without their review.**

**8. Ready.** `qtree.py ready` exits 0 only when `check` exits 0 or 2, the approved render is current and unaltered, and every material answer is placed. Only then draft, **from the Document plan section**:
- the conclusion first;
- each section in plan order;
- each paragraph answers the question the reader would ask next;
- concessions use their stated wording;
- qualifiers and rebuttals stay attached to their propositions.

Questions never appear in the served document. Before handover, scan the draft for question marks and for `Q<n>` tokens.

**9. Reserve.** Answered peripheral questions, with their evidence, authority and rebuttal, become prepared answers to questions from the bench.

## Rules

- The tree is an **internal, privileged analytical document**. Keep it out of anything served or filed.
- Generators are locators. A question bank never supplies a legal proposition; every answer is sourced.
- A fatal `opp` question with no answer goes back to the strategy. Do not draft around it.
- Tree time is drafting time on the task it serves.

## Files

- `qtree.py` — the store (stdlib only; POSIX file locking).
- `questions.md` — the generator bank.
- `examples/demo.sh` — worked example.
- `tests/` — regression suite, fuzzer with an independent oracle, mutation tests. See `TESTING.md`.
