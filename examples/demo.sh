#!/usr/bin/env bash
# Worked example: a small limitation point taken from proposition to `ready`.
# Illustrates the mechanics only; it is not legal advice. Run: bash examples/demo.sh
set -u
Q="$(cd "$(dirname "$0")/.." && pwd)/qtree.py"; q(){ python3 "$Q" "$@"; }
W=$(mktemp -d)
q init "$W" --root "The contract claim is time-barred." --doc demo >/dev/null
F=$(ls "$W"/*.json)

# First ring: Paul, Walton, opponent, court
q add-many "$F" Q0 --json '[
 {"q":"When did the cause of action accrue?","gen":"paul:evidence","mat":3},
 {"q":"Which limitation period applies?","gen":"walton:statute","mat":3},
 {"q":"Will the claimant say time was extended?","gen":"opp","mat":2},
 {"q":"What order is sought?","gen":"court","mat":2}]' >/dev/null

q answer "$F" Q1 --type fact --a "Breach on 1 March 2019." --grounds "Letter of 01.03.2019 (bundle p.12)" --effect supports
q answer "$F" Q2 --type law --a "Six years from accrual." --warrant "Limitation Act 1980 s.5" --effect supports
q answer "$F" Q3 --type fact --a "No acknowledgment or part payment exists." --grounds "Correspondence file pp.20-40" --effect neutral
q answer "$F" Q4 --type fact --a "Judgment for the defendant on the limitation defence." --grounds "Defence para 3" --effect supports

echo "--- check (expect exit 1: critical answers not yet interrogated)"; q check "$F"; echo "exit $?"

# Recurse: each critical answer is a new proposition
q add "$F" Q1 --q "Is there a later breach that restarts time?" --gen paul:assumptions --mat 2 >/dev/null
q add "$F" Q2 --q "Does a special period for latent damage apply?" --gen walton:statute --mat 2 >/dev/null
q answer "$F" Q1.1 --type fact --a "No; the only breach pleaded is on 01.03.2019." --grounds "Particulars of Claim para 7" --effect supports
q answer "$F" Q2.1 --type law --a "No; s.14A applies to actions for damages for negligence, and this claim is in contract." --warrant "Limitation Act 1980 s.14A(1)" --effect supports

echo "--- check (expect exit 0)"; q check "$F"; echo "exit $?"

i=1; for id in Q1 Q1.1 Q2 Q2.1 Q3 Q4; do q place "$F" "$id" --section "Limitation" --order $i >/dev/null; i=$((i+1)); done
q render "$F" >/dev/null
echo "--- review ${F%.json}.md, then approve"; q approve "$F"
echo "--- ready (expect exit 0)"; q ready "$F"; echo "exit $?"
echo "Tree: ${F%.json}.md"
