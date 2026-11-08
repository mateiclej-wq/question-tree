# Question bank: generators for /question-tree

These are question prompts, not legal propositions. They tell you what to ask. They never supply an answer. Every answer still passes the source-first rule.

The six Paul categories follow Paul & Elder, *The Thinker's Guide to the Art of Socratic Questioning* (Foundation for Critical Thinking, 2006). The Walton families follow the "argumentation scheme + critical questions" method (Walton, Reed & Macagno, *Argumentation Schemes*, 2008). The wording below is **adapted for English litigation practice**. It is not a verbatim quotation of either text.

## 1. Paul: six categories (`--gen paul:<x>`)

| tag | Ask of the proposition |
|---|---|
| `clarification` | What exactly does each operative term mean here: statutory meaning, case-law meaning or ordinary meaning? What is the precise relief or finding sought? |
| `assumptions` | What must be true for this to hold that I have not stated? Which fact am I taking as found that is in fact disputed? Which legal premise is contested? |
| `evidence` | What document, page or witness proves each fact? What is the best evidence against it? Is it admissible, and is it before the court? |
| `viewpoints` | How will the opponent put the point? How will the judge frame it? How has the client lived it? How would an appellate court see it? |
| `implications` | If the court accepts this, what follows? Does it prove too much, concede something elsewhere, or open a floodgate? What order follows? |
| `question` | Is this the right question for this forum and this stage? Is it the question the statute or test actually asks? Who bears the burden, and to what standard? |

## 2. Walton-style critical questions (`--gen walton:<x>`): the opponent's attack

| tag | Scheme | Critical questions |
|---|---|---|
| `precedent` | "Case X decided Y; this case is like X" | Is X binding, persuasive or distinguishable? What were X's material facts? Is our matrix analogous on *those* facts? How has X been treated since: applied, distinguished, narrowed or doubted? Is there a later or higher authority the other way? Is the passage relied on ratio or obiter? |
| `analogy` | "A is like B, so the same result follows" | In which respects are A and B alike, and are those the respects that mattered? Which difference could justify a different result? Is there a closer analogy pointing the other way? |
| `expert` | "Expert E says P" | Is E an expert *in this field*? Did E actually say P, at which paragraph, and with which qualifications? Is E independent and compliant with the expert's duties under the procedural regime of *this* forum (criminal and extradition: CrimPR Part 19; civil: CPR Part 35; tribunals: their own rules) — identify which applies and verify the rule? Is P consistent with other experts and with the documents? On what material was P based, and was that material complete? |
| `statute` | "Provision S means M" | What is the text? What context and purpose? Is the provision in force as amended? What do the authorities say it means? Is there an alternative reading, and which canon prefers it? Is there a Convention-compatible reading (HRA s.3)? |
| `evidence-inference` | "Fact F shows conclusion C" | Is F proved? Does F make C more likely than the alternatives (evidential weight, not the standard of proof)? Who bears the burden on C, and to what standard (verify from the statute and authorities for this forum)? What else explains F? Is there a gap in the chain? |
| `consequences` | "Outcome O would follow, and O is bad or good" | How likely is O? Is the link causal or speculative? Does the court have the power to weigh O under this test? |
| `sign` | "Indicator I signals state S" (e.g. flight risk, fugitivity) | Is I a reliable sign of S? Is there an innocent explanation? What does the leading authority say counts as S? |

## 3. Roles (`--gen opp` / `court` / `client` / `self`)

- `opp`: the strongest question the other side will put. Ask it in their voice.
- `court`: the question the judge will ask from the bench, often "so what?", "where is that in the bundle?" or "what order do you want?".
- `client`: what the client needs answered: risk, cost, timing, what happens next.
- `self`: anything else you would ask yourself.

## 4. Materiality (`--mat`)

- **3: critical.** If this answer goes wrong, the proposition fails. It must be answered **and** interrogated, with at least one follow-up question.
- **2: material.** It must be answered or closed with a reason before drafting.
- **1: peripheral.** Answer it if cheap. Otherwise it goes to the reserve as oral-argument preparation.
