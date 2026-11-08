#!/bin/bash
# Regression tests for qtree v2 — each block reproduces a finding from an independent QA pass.
Q=${QT_PATH:-$(cd "$(dirname "$0")/.." && pwd)/qtree.py}; TH="$(cd "$(dirname "$0")" && pwd)/th.py"; D=$(mktemp -d); pass=0; fail=0
must(){ if ! python3 $Q "$@" >/dev/null 2>&1; then fail=$((fail+1)); echo "SETUP FAILED: $*"; fi; }
reseal(){ python3 - "$Q" "$1" <<'PY'
import sys, json, importlib.util
spec = importlib.util.spec_from_file_location("q", sys.argv[1]); q = importlib.util.module_from_spec(spec); spec.loader.exec_module(q)
t = json.load(open(sys.argv[2])); t.pop("seal", None); open(sys.argv[2], "w").write(q.sealed_json(t))
PY
}
ok(){ if [ "$1" = "$2" ]; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL [$3] expected $2 got $1"; fi; }
run(){ python3 $Q "$@" >/dev/null 2>&1; echo $?; }
new(){ local f; f=$(python3 $Q init "$D" --root "Root P" --doc "t$1" "${@:2}"); [ -f "$f" ] || { fail=$((fail+1)); echo "SETUP FAILED: init t$1" >&2; }; echo "$f"; }

# F4 bounds
ok $(run init $D --root R --doc b1 --threshold 99) 1 "threshold bound"
ok $(run init $D --root R --doc b2 --depth -1) 1 "depth bound"
ok $(run init $D --root "  " --doc b3) 1 "blank root"

# F1 unsupported root / unanswered m1 under m3 / undermining answer
F=$(new 1)
must add "$F" Q0 --q "peripheral" --gen court --mat 1
ok $(run check "$F") 1 "root with only m1 OPEN child is not closed (no support)"
must add "$F" Q0 --q "critical" --gen paul:evidence --mat 3
must answer "$F" Q2 --type fact --a "Yes" --effect supports --grounds "B/1"
must add "$F" Q2 --q "follow" --gen paul:assumptions --mat 1
ok $(run check "$F") 1 "m3 with only unresolved follow-up fails"
must answer "$F" Q2.1 --type fact --a "ok" --effect neutral --grounds "B/2"
ok $(run check "$F") 2 "closed with residue (Q1 m1 open)"
must add "$F" Q0 --q "opp attack" --gen opp --mat 2
must answer "$F" Q3 --type law --a "Authority against us" --effect undermines --warrant "X v Y [2020] §4"
ok $(run check "$F") 1 "unmet undermining answer fails"
must answer "$F" Q3 --type law --a "Authority against us" --effect undermines --warrant "X v Y [2020] §4" --rebuttal "Distinguishable: §5 facts"
ok $(run check "$F") 2 "met undermining answer passes"

# F5 sourcing
F=$(new 2)
ok $(run answer "$F" Q0 --type fact --a "   " --effect supports) 1 "blank answer rejected"
must add "$F" Q0 --q "fact q" --gen paul:evidence --mat 2
must answer "$F" Q1 --type fact --a "He attended" --effect supports --warrant "s.20"
ok $(run check "$F") 1 "fact answer with only warrant fails"
must answer "$F" Q1 --type fact --a "He attended" --effect supports --grounds "[VERIFY] B/3"
ok $(run check "$F") 1 "[VERIFY] grounds do not count"
must answer "$F" Q1 --type mixed --a "He attended" --effect supports --grounds "B/3"
ok $(run check "$F") 1 "mixed answer needs warrant too"

# F3 re-answer replaces slots, stales descendants, clears approval
F=$(new 3)
must add "$F" Q0 --q "attend?" --gen paul:evidence --mat 3
must answer "$F" Q1 --type fact --a "attended" --effect supports --grounds "attendance record B/9"
must add "$F" Q1 --q "proof?" --gen paul:evidence --mat 2
must answer "$F" Q1.1 --type fact --a "record" --effect supports --grounds "B/9"
must render "$F"; must approve "$F"
ok "$(python3 "$TH" approved "$F")" True "F3 approval actually recorded"
ok $(run ready "$F") 1 "not ready: unplaced"
must answer "$F" Q1 --type fact --a "did not attend" --effect supports
ok "$(python3 "$TH" cleared "$F") $(python3 $Q status "$F" Q1.1)" "True STALE" "re-answer clears/stales/unapproves"
ok $(run check "$F") 1 "stale descendants block closure"

# F7 cascades + duplicates
F=$(new 4)
must add "$F" Q0 --q "a" --gen self --mat 2
must answer "$F" Q1 --type law --a "A" --effect supports --warrant "s.1"
must add "$F" Q1 --q "b" --gen self --mat 2
must close "$F" Q1.1 BLOCKED --reason "[VERIFY] x"
ok $(run close "$F" Q1 DUPLICATE --of Q999) 1 "dup of nonexistent rejected"
ok $(run close "$F" Q1 DUPLICATE --of Q1.1) 1 "dup of own descendant rejected"
ok $(run close "$F" Q1 CONCEDED) 1 "concession needs text"
must add "$F" Q0 --q "c" --gen self --mat 2
must answer "$F" Q2 --type law --a "C" --effect supports --warrant "s.2"
must close "$F" Q1 OUT_OF_SCOPE --reason "later stage"
ok "$(python3 $Q status "$F" Q1.1)" PRUNED "closing parent prunes BLOCKED child"
ok $(run check "$F") 0 "pruned BLOCKED no longer obstructs"
ok $(run answer "$F" Q1.1 --type law --a x --effect neutral --warrant y) 1 "cannot answer pruned node"
must reopen "$F" Q1
ok "$(python3 $Q status "$F" Q1.1)" STALE "reopen returns child for review"
must confirm "$F" Q1.1; ok "$(python3 $Q status "$F" Q1.1)" BLOCKED "confirm restores the exact decision"

# F2 export: concession text, qualifiers, sources; no question fallback
F=$(new 5)
must add "$F" Q0 --q "conceded q?" --gen opp --mat 2
must answer "$F" Q1 --type law --a "old answer" --effect supports --warrant "s.9"
must close "$F" Q1 CONCEDED --concession "The RP accepts the conviction is final."
must add "$F" Q0 --q "main" --gen self --mat 2
must answer "$F" Q2 --type law --a "Main point" --effect supports --warrant "Celinski §13" --qualifier "on the DJ's findings"
must place "$F" Q1 --section "Concessions" --order 2; must place "$F" Q2 --section "Ground 1" --order 1
M=$(python3 $Q render "$F")
PL=$(sed -n '/## Document plan/,/## Reserve/p' "$M")
ok "$(echo "$PL" | grep -c 'The RP accepts the conviction is final')" 1 "concession text exported"
ok "$(grep -A3 '### Concessions' "$M" | grep -c 'old answer')" 0 "superseded answer not exported"
ok "$(echo "$PL" | grep -c "Qualifier: on the DJ's findings")" 1 "qualifier exported"
ok "$(echo "$PL" | grep -c 'Authority: Celinski')" 1 "authority exported"
ok "$(grep '### ' "$M" | sed -n 2p | grep -c 'Ground 1')" 1 "plan ordered by --order (after Conclusion)"
must approve "$F"
ok $(run ready "$F") 0 "ready when closed+approved+placed"
must add "$F" Q2 --q "late" --gen self --mat 1
ok $(run ready "$F") 1 "any edit clears approval"

# F10 naming, idempotency, numeric order
F=$(new 6)
ok $(run init $D --root R --doc t6) 1 "same doc+day refused"
for i in $(seq 1 11); do must add "$F" Q0 --q "q$i" --gen self --mat 2; done
ok "$(python3 $Q add "$F" Q0 --q "  Q5 " --gen self | tr -d ' ')" "Q5(exists)" "idempotent add (case/space-insensitive)"
ok "$(python3 $Q open "$F" | head -3 | awk '{print $1}' | tr '\n' ' ')" "Q1 Q2 Q3 " "numeric sort"
ok $(run add "$F" Q1 --q x --gen self) 1 "cannot add under unanswered node"

# F4 depth cap residue
F=$(python3 $Q init "$D" --root R --doc t7 --depth 1)
must add "$F" Q0 --q "a" --gen self --mat 3
must answer "$F" Q1 --type law --a A --effect supports --warrant w
must add "$F" Q1 --q "deep" --gen self --mat 3
ok $(run check "$F") 2 "beyond-cap material item is residue, not silently dropped"
ok "$(python3 $Q check "$F" 2>/dev/null | grep -c 'beyond depth cap')" 1 "residue names the item"
ok $(run close "$F" Q1.1 DEFERRED --reason "not now") 1 "material deferral needs budget reason"

# F8 concurrency: 20 parallel adds, no lost writes, unique ids
F=$(new 8)
for i in $(seq 1 20); do python3 $Q add "$F" Q0 --q "p$i" --gen self >/dev/null & done; wait
ok "$(python3 "$TH" children "$F")" "20 20" "parallel adds"

# node budget
F=$(python3 $Q init "$D" --root R --doc t9 --max-nodes 2)
must add "$F" Q0 --q a --gen self; must add "$F" Q0 --q b --gen self
ok $(run add "$F" Q0 --q c --gen self) 1 "node budget enforced"

# fuzz-found: duplicate cycles
F=$(new 10)
for x in a b c; do must add "$F" Q0 --q $x --gen self; done
must answer "$F" Q2 --type fact --a B --effect neutral --grounds B/1
must close "$F" Q1 DUPLICATE --of Q2
ok $(run close "$F" Q2 DUPLICATE --of Q1) 1 "2-cycle rejected"
ok $(run close "$F" Q3 DUPLICATE --of Q1) 1 "dup of a duplicate refused (no chains)"
# fuzz-found: re-answering a CONCEDED node / root restores its pruned branch
F=$(new 11)
must add "$F" Q0 --q a --gen self
must answer "$F" Q1 --type law --a A --effect supports --warrant w
must add "$F" Q1 --q b --gen self
must close "$F" Q1 CONCEDED --concession "C"
must answer "$F" Q0 --type law --a "Root v2" --effect supports
ok "$(python3 $Q status "$F" Q1) $(python3 $Q status "$F" Q1.1)" "STALE PRUNED" "root change stales concession; branch stays pruned until confirmed/reopened"

# ===== QA round 2 — one test per reproduced finding =====
sup(){ must add "$1" Q0 --q "Main?" --gen self --mat ${2:-2}; must answer "$1" Q1 --type fact --a "Supporting fact" --effect supports --grounds "Record B/1"; }
fin(){ python3 $Q render "$1" >/dev/null; must approve "$1"; python3 $Q ready "$1" >/dev/null 2>&1; echo $?; }
# B1 [VERIFY] in answer/qualifier/rebuttal
F=$(new b1); must add "$F" Q0 --q m --gen self
must answer "$F" Q1 --type fact --a "[VERIFY] Supporting fact" --effect supports --grounds B/1 --qualifier "[VERIFY] q"
must place "$F" Q1 --section G1; ok $(fin "$F") 1 "B1 VERIFY in answer/qualifier blocks"
F=$(new b1b); sup "$F"; must place "$F" Q1 --section G1
must add "$F" Q0 --q adverse --gen opp
must answer "$F" Q2 --type law --a "Binding adverse rule" --effect undermines --warrant "Auth §12" --rebuttal "[VERIFY] find a distinction"
must place "$F" Q2 --section G1; ok $(fin "$F") 1 "B1 VERIFY rebuttal does not meet"
# B2 changing evidence/qualifier stales descendants
F=$(new b2); sup "$F"; must add "$F" Q1 --q "What follows?" --gen court
must answer "$F" Q1.1 --type fact --a "OLD CONCLUSION" --effect neutral --grounds "Old B/2"
must answer "$F" Q1 --type fact --a "Supporting fact" --effect supports --grounds "Replacement B/9" --qualifier "Only before 2020"
ok "$(python3 $Q status "$F" Q1.1)" STALE "B2 slot change stales child"
must confirm "$F" Q1.1
ok "$(python3 $Q status "$F" Q1.1)" ANSWERED "B2 confirm restores after review"
# B3 closure decisions under a changed premise go STALE
F=$(new b3); sup "$F"; must add "$F" Q1 --q "Old limitation?" --gen opp
must close "$F" Q1.1 OUT_OF_SCOPE --reason "only if the fact changes"
must answer "$F" Q1 --type fact --a "The fact changes" --effect supports --grounds "New B/3"
ok "$(python3 $Q status "$F" Q1.1)" STALE "B3 OUT_OF_SCOPE re-opened for review"
# B4 concession exports no superseded support
F=$(new b4); sup "$F"; must place "$F" Q1 --section G1
must add "$F" Q0 --q "Did he attend?" --gen opp
must answer "$F" Q2 --type mixed --a "He attended" --effect supports --grounds "Old evidence B/2" --warrant "Old auth §9" --rebuttal "Reject absence"
must place "$F" Q2 --section Concessions; must close "$F" Q2 CONCEDED --concession "He did not attend."
M=$(python3 $Q render "$F"); PL=$(sed -n '/## Document plan/,/## Reserve/p' "$M")
ok "$(echo "$PL" | grep -c 'Old evidence\|Old auth\|Reject absence')" 0 "B4 concession carries no old support"
# B5 duplicate lifts materiality of canonical
F=$(new b5); sup "$F"; must place "$F" Q1 --section G1
must add "$F" Q0 --q "Peripheral version?" --gen self --mat 1
must close "$F" Q2 BLOCKED --reason "[VERIFY] decisive source unavailable"
must add "$F" Q0 --q "Critical source question?" --gen opp --mat 3
ok $(run close "$F" Q3 DUPLICATE --of Q2) 1 "B5 duplicate onto a BLOCKED question refused"
ok $(run check "$F") 1 "B5 critical question stays open and blocks"
# B6 BLOCKED / self-referring follow-up does not interrogate
F=$(new b6); sup "$F" 3; must place "$F" Q1 --section G1
must add "$F" Q1 --q "Valid inference?" --gen opp --mat 1
must close "$F" Q1.1 BLOCKED --reason "[VERIFY] cannot test"
ok $(run check "$F") 1 "B6 BLOCKED follow-up does not interrogate"
ok $(run close "$F" Q1.1 DUPLICATE --of Q1) 1 "B6 duplicate of own ancestor refused"
# B7 approval binds to the reviewed render
F=$(new b7); sup "$F"; must place "$F" Q1 --section G1; must render "$F"
must answer "$F" Q1 --type fact --a "Replacement never shown" --effect supports --grounds "New B/9"
ok $(run approve "$F") 1 "B7 approve refused on stale render"
must render "$F"; must approve "$F"; ok $(run ready "$F") 0 "B7 ready after fresh render+approve"
sed -i '' 's/Replacement never shown/Tampered text/' "${F%.json}.md"; ok $(run ready "$F") 1 "B7 edited render detected"
# B8 root in plan with qualifier; root not placeable
F=$(new b8); must answer "$F" Q0 --type fact --a "Allow the appeal" --effect supports --grounds "B/0" --qualifier "Only if fresh evidence is admitted"
ok $(run place "$F" Q0 --section Conclusion) 1 "B8 root placement refused"
sup "$F"; M=$(python3 $Q render "$F")
ok "$(sed -n '/## Document plan/,/## Reserve/p' "$M" | grep -c 'Only if fresh evidence is admitted')" 1 "B8 root qualifier in Conclusion"
# B9 render cannot overwrite tree
F=$(new b9); cp "$F" "${F%.json}.md"; ok $(run render "${F%.json}.md") 1 "B9 non-.json tree refused"
# B10 malformed batches rejected atomically, no crash
F=$(new b10)
for j in '[null]' '[{"q":1,"gen":"self"}]' '[{"q":"x","gen":null}]' '[{"q":"x","gen":"self","mat":"abc"}]' '[{"q":"x","gen":"self","mat":2.9}]' '[{"q":"x","gen":"self","mat":true}]' '{"q":"x"}' 'nope' '[{"q":"ok","gen":"self"},{"q":"bad","gen":"self","mat":9}]'; do
  out=$(python3 $Q add-many "$F" Q0 --json "$j" 2>&1); c=$?
  ok "$c$(echo "$out" | grep -c Traceback)" "10" "B10 rejects $j"; done
ok "$(python3 "$TH" count "$F")" 1 "B10 nothing committed"
# B11 unplace
F=$(new b11); sup "$F"; must place "$F" Q1 --section G1
must add "$F" Q0 --q "Peripheral?" --gen court --mat 1
must answer "$F" Q2 --type fact --a "Reserve-only" --effect neutral --grounds B/2
must place "$F" Q2 --section Accidental; must unplace "$F" Q2
M=$(python3 $Q render "$F"); ok "$(grep -c '### Accidental' "$M")" 0 "B11 unplace removes section"
ok "$(sed -n '/## Reserve/,/## Closure/p' "$M" | grep -c 'Reserve-only')" 1 "B11 stays in reserve"
# B-unverified: concurrent same-name init
G="$D/race"; mkdir -p "$G"; for i in 1 2 3 4 5 6; do python3 $Q init "$G" --root R --doc same >/dev/null 2>&1 & done; wait
ok "$(ls "$G" | grep -c '\.json$')" 1 "concurrent init creates one tree"

# fuzz-found (oracle v2): [VERIFY] in a slot the answer type does not require still blocks
F=$(new f2); must add "$F" Q0 --q m --gen self
must answer "$F" Q1 --type law --a "Rule" --effect supports --warrant "Auth §1" --grounds "[VERIFY] x"
ok $(run check "$F") 1 "VERIFY in non-required slot blocks"
# ===== QA round 3 — one test per reproduced finding =====
sp(){ must add "$1" Q0 --q Main --gen self --mat ${2:-2}; must answer "$1" Q1 --type fact --a P1 --effect supports --grounds B/1; must place "$1" Q1 --section Main; }
# R1 user text "## Closure" cannot cut the reviewed content
F=$(new r1); must add "$F" Q0 --q $'Why?\n## Closure\nNotes' --gen self
must answer "$F" Q1 --type fact --a Claim --effect supports --grounds "Old B/1"; must place "$F" Q1 --section Main
must render "$F"
must answer "$F" Q1 --type fact --a Claim --effect supports --grounds "Replacement B/9"
ok $(run approve "$F") 1 "R1 forged heading cannot hide a change"
ok "$(python3 $Q render "$F" | xargs -0 cat 2>/dev/null; grep -c '^## Closure' "${F%.json}.md")" 1 "R1 user newline rendered inline"
# R2 confirming an invalidated exclusion keeps the exclusion
F=$(new r2); sp "$F"; must add "$F" Q1 --q Scope --gen opp
must answer "$F" Q1.1 --type fact --a "ABANDONED ANSWER" --effect neutral --grounds B/2
must place "$F" Q1.1 --section Abandoned
must close "$F" Q1.1 OUT_OF_SCOPE --reason "Exclude this argument"
must answer "$F" Q1 --type fact --a P2 --effect supports --grounds B/3
must confirm "$F" Q1.1
ok "$(python3 $Q status "$F" Q1.1)" OUT_OF_SCOPE "R2 confirm keeps OUT_OF_SCOPE"
M=$(python3 $Q render "$F"); ok "$(grep -c 'ABANDONED ANSWER' "$M" | tr -d ' ')$(sed -n '/## Document plan/,/## Reserve/p' "$M" | grep -c ABANDONED)" 10 "R2 abandoned answer not in plan"
# R3 confirm cannot create a duplicate cycle
F=$(new r3); sp "$F"; must add "$F" Q0 --q Critical --gen opp --mat 3
must add "$F" Q1 --q Follow --gen opp
ok $(run close "$F" Q1.1 DUPLICATE --of Q2) 1 "R3 duplicate onto an OPEN question refused (no cycle can form)"
must close "$F" Q1 OUT_OF_SCOPE --reason "Temporary closure"
must reopen "$F" Q1
must answer "$F" Q1 --type fact --a P2 --effect supports --grounds B/2
ok $(run close "$F" Q2 DUPLICATE --of Q1.1) 1 "R3 cycle refused at close"
ok $(run check "$F") 1 "R3 critical unanswered Q2 blocks"
# R4 answering a conceded parent stales exclusions based on the old premise
F=$(new r4); sp "$F"; must add "$F" Q1 --q "Only if P2" --gen opp
must close "$F" Q1.1 OUT_OF_SCOPE --reason "P1 applies"
must close "$F" Q1 CONCEDED --concession "Concede P1"
must answer "$F" Q1 --type fact --a P2 --effect supports --grounds B/2
ok "$(python3 $Q status "$F" Q1.1)" STALE "R4 exclusion stale after concession replaced"
ok $(run check "$F") 1 "R4 stale exclusion blocks closure"
# R5 concession of a previously answered node interrogates
F=$(new r5); sp "$F" 3; must add "$F" Q1 --q Counterpoint --gen opp --mat 1
must answer "$F" Q1.1 --type fact --a A --effect neutral --grounds B/2
must close "$F" Q1.1 CONCEDED --concession "We concede C"
ok "$(run check "$F")" 0 "R5 concession from ANSWERED interrogates"
# R6 pruning a stale answer keeps it confirmable
F=$(new r6); sp "$F"; must add "$F" Q1 --q Follow --gen self
must answer "$F" Q1.1 --type fact --a A --effect neutral --grounds B/2
must answer "$F" Q1 --type fact --a P2 --effect supports --grounds B/3
must close "$F" Q1 OUT_OF_SCOPE --reason "Temporarily unused"
must reopen "$F" Q1; must confirm "$F" Q1
ok $(run confirm "$F" Q1.1) 0 "R6 stale answer still confirmable after prune/restore"
ok "$(python3 $Q status "$F" Q1.1)" ANSWERED "R6 answer intact"
# R7 first-ring duplicate of a supporting answer counts as support
F=$(new r7); must add "$F" Q0 --q Context --gen self
must answer "$F" Q1 --type fact --a Context --effect neutral --grounds B/1
must add "$F" Q1 --q Evidence --gen paul:evidence
must answer "$F" Q1.1 --type fact --a Support --effect supports --grounds B/2
must add "$F" Q0 --q "Same evidence" --gen court
ok $(run close "$F" Q2 DUPLICATE --of Q1.1) 1 "R7 (v4.5) duplicate onto a deeper question refused"
# R8 node-budget overrun is residue
F=$(python3 $Q init "$D" --root R --doc r8 --max-nodes 1); sp "$F"
must add "$F" Q0 --q Extra --gen court --force
must answer "$F" Q2 --type fact --a E --effect neutral --grounds B/2; must place "$F" Q2 --section Extra
ok $(run check "$F") 2 "R8 node budget overrun listed"
# R9 (v4.3) duplicate must point at a current sound answer; it lifts that answer's materiality
F=$(new r9); must add "$F" Q0 --q "Peripheral canonical" --gen self --mat 1
must add "$F" Q0 --q "Critical duplicate" --gen opp --mat 3
ok $(run close "$F" Q2 DUPLICATE --of Q1) 1 "R9 duplicate onto an OPEN question refused"
must answer "$F" Q1 --type fact --a "Answer" --effect supports --grounds B/1
must close "$F" Q2 DUPLICATE --of Q1
ok "$(python3 $Q check "$F" 2>/dev/null | grep -c 'Q1: critical answer not interrogated')" 1 "R9 lifted answer carries the critical obligation"
# not raised in QA: symlink path shares the lock; failed write leaves no temp file and an intact tree
F=$(new sym); ln -s "$F" "$D/link.json"
for i in $(seq 1 10); do python3 $Q add "$F" Q0 --q "a$i" --gen self >/dev/null & python3 $Q add "$D/link.json" Q0 --q "b$i" --gen self >/dev/null & done; wait
ok "$(python3 "$TH" children "$F")" "20 20" "symlink + real path share one lock"
F=$(new ro); chmod 555 "$D"; out=$(python3 $Q add "$F" Q0 --q x --gen self 2>&1); c=$?; chmod 755 "$D"
ok "$c$(ls -a "$D" | grep -c '\.qtree-')" "10" "failed write: nonzero exit, no temp left"
ok "$(python3 "$TH" count "$F")" 1 "failed write: tree intact"

# ===== QA round 4 =====
bs(){ must add "$1" Q0 --q Main --gen self --mat ${2:-2}; must answer "$1" Q1 --type fact --a Support --effect supports --grounds B/1; must place "$1" Q1 --section Main; }
fz(){ python3 $Q render "$1" >/dev/null; must approve "$1"; python3 $Q ready "$1" >/dev/null 2>&1; echo $?; }
# 4.1 content inserted between body and marker
F=$(new s1); bs "$F"; ok $(fz "$F") 0 "4.1 baseline ready"
M="${F%.json}.md"; python3 - "$M" <<'PY'
import sys; p=sys.argv[1]; s=open(p).read(); s=s.replace("\n## Closure","\n## Document plan\n### Superseding Conclusion\n- Dismiss the appeal.\n## Closure",1); open(p,"w").write(s)
PY
ok $(run ready "$F") 1 "4.1 inserted plan before Closure rejected"
# 4.2 stale duplicate link does not interrogate
F=$(new s2); must add "$F" Q0 --q Main --gen self --mat 3
must answer "$F" Q1 --type fact --a Support --effect supports --grounds B/1; must place "$F" Q1 --section Main
must add "$F" Q0 --q "Other evidence" --gen self --mat 1; must answer "$F" Q2 --type fact --a "Other fact" --effect neutral --grounds B/1
must add "$F" Q1 --q Followup --gen self --mat 1; must close "$F" Q1.1 DUPLICATE --of Q2
must answer "$F" Q1 --type fact --a "Changed support" --effect supports --grounds B/9
ok $(run check "$F") 1 "4.2 stale duplicate link does not interrogate"
must confirm "$F" Q1.1; ok $(run check "$F") 0 "4.2 confirmed link interrogates"
# 4.3 stale peripheral exclusion cannot keep hiding a critical branch
F=$(new s3); bs "$F"; must add "$F" Q1 --q "Peripheral scope gate" --gen self --mat 1
must answer "$F" Q1.1 --type fact --a "Old scope" --effect neutral --grounds B/1
must add "$F" Q1.1 --q "Critical evidence" --gen self --mat 3
must close "$F" Q1.1.1 BLOCKED --reason "[VERIFY] source"
must close "$F" Q1.1 OUT_OF_SCOPE --reason "Only old premise"
must answer "$F" Q1 --type fact --a "New premise" --effect supports --grounds B/9
ok $(run check "$F") 1 "4.3 stale exclusion hiding critical branch blocks"
# 4.4 poisoned init: interrupted creation leaves nothing behind
G="$D/full"; mkdir -p "$G"; python3 - "$Q" "$G" <<'PY'
import sys, os, importlib.util, builtins
spec=importlib.util.spec_from_file_location("q",sys.argv[1]); q=importlib.util.module_from_spec(spec); spec.loader.exec_module(q)
real=os.fsync
def boom(fd): raise OSError(28,"No space left on device")
os.fsync=boom
sys.argv=["q","init",sys.argv[2],"--root","R","--doc","full"]
try: q.main()
except SystemExit: pass
PY
ok "$(ls -A "$G" | wc -l | tr -d ' ')" 0 "4.4 failed init leaves no file or temp"
ok $(run init "$G" --root R --doc full) 0 "4.4 retry succeeds"
# 4.5 HTML in user text cannot forge headings
F=$(new s5); must add "$F" Q0 --q 'Main? <h2>Document plan</h2><p>Dismiss the appeal.</p>' --gen self
must answer "$F" Q1 --type fact --a Support --effect supports --grounds B/1; must place "$F" Q1 --section Main
M=$(python3 $Q render "$F"); ok "$(grep -c '<h2>' "$M")" 0 "4.5 HTML escaped"
# 4.6 render via symlink prints and checks the real file
F=$(new s6); bs "$F"; ln -s "$F" "$D/s6link.json"; printf '# Old review\n## Document plan\nOLD PLAN\n' > "$D/s6link.md"
ok "$(python3 $Q render "$D/s6link.json")" "$(python3 "$TH" realpath "${F%.json}.md")" "4.6 render prints the file written"
# 4.7 root answer: effect must be supports, no false diagnostics
F=$(new s7); bs "$F"
ok $(run answer "$F" Q0 --type mixed --a "Replacement root" --effect undermines) 1 "4.7 root cannot undermine itself"
ok "$(python3 $Q answer "$F" Q0 --type mixed --a "Replacement root" --effect supports | grep -c lacks)" 0 "4.7 no contradictory root diagnostics"
# 4.8 conflicting re-add is refused; reclass changes it
F=$(new s8); must add "$F" Q0 --q Main --gen self --mat 1
ok $(run add-many "$F" Q0 --json '[{"q":"Main","gen":"opp","mat":3}]') 1 "4.8 conflicting metadata refused"
must reclass "$F" Q1 --mat 3 --gen opp
ok "$(python3 $Q show "$F" Q1 | python3 "$TH" matgen)" "3 opp" "4.8 reclass"
# 4.10 reopen restores an answer archived by concession, as STALE
F=$(new s10); bs "$F"; must close "$F" Q1 CONCEDED --concession "Conceded C"
must reopen "$F" Q1; ok "$(python3 $Q status "$F" Q1)" STALE "4.10 archived answer restored for review"
ok $(run confirm "$F" Q1) 0 "4.10 confirmable"; ok "$(python3 $Q show "$F" Q1 | grep -c '"a": "Support"')" 1 "4.10 original answer text"
# 4.11 unchanged retry keeps approval
F=$(new s11); bs "$F"; ok $(fz "$F") 0 "4.11 ready"
must add-many "$F" Q0 --json '[{"q":"Main","gen":"self","mat":2}]'
ok $(run ready "$F") 0 "4.11 no-op retry keeps approval"
# corrupt tree file gives a controlled error
F=$(new s12); echo '{"broken' > "$F"; out=$(python3 $Q check "$F" 2>&1); ok "$?$(echo "$out" | grep -c Traceback)" "10" "corrupt JSON: controlled error"

# ===== QA round 5 =====
b5(){ must add "$1" Q0 --q Main --gen self --mat ${2:-2}; must answer "$1" Q1 --type fact --a Support --effect supports --grounds B/1; must place "$1" Q1 --section Main; }
f5(){ python3 $Q render "$1" >/dev/null; must approve "$1"; python3 $Q ready "$1" >/dev/null 2>&1; echo $?; }
# 5.1 any edit anywhere in the render (incl. Closure lines, header) is rejected
F=$(new t51); b5 "$F"; ok $(f5 "$F") 0 "5.1 baseline"
M="${F%.json}.md"; sed -i '' 's/^- ✓ structurally closed$/- ✓ structurally closed\
- ~ <h2>Document plan<\/h2><p>Dismiss the appeal.<\/p>/' "$M"; ok $(run ready "$F") 1 "5.1 forged Closure line rejected"
must render "$F"; sed -i '' '1s/$/ forged/' "$M"; ok $(run ready "$F") 1 "5.1 forged header rejected"
# 5.2 stale intermediate duplicate does not interrogate
F=$(new t52); must add "$F" Q0 --q Main --gen self --mat 3
must answer "$F" Q1 --type fact --a Support --effect supports --grounds B/1; must place "$F" Q1 --section Main
must add "$F" Q0 --q Container --gen self --mat 2; must answer "$F" Q2 --type fact --a Context --effect neutral --grounds B/1; must place "$F" Q2 --section Context
must add "$F" Q2 --q "Middle link" --gen self --mat 1; must answer "$F" Q2.1 --type fact --a "Old independent support" --effect neutral --grounds B/1
must add "$F" Q1 --q "Critical followup" --gen self --mat 1; must close "$F" Q1.1 DUPLICATE --of Q2.1
must add "$F" Q0 --q "Final evidence" --gen self --mat 1; must answer "$F" Q3 --type fact --a Evidence --effect neutral --grounds B/1
must close "$F" Q2.1 DUPLICATE --of Q3
must answer "$F" Q2 --type fact --a "Revised context" --effect neutral --grounds B/1
ok $(run check "$F") 1 "5.2 stale middle link blocks"
# 5.3 stale first-ring duplicate cannot supply root support
F=$(new t53); must add "$F" Q0 --q Context --gen self; must answer "$F" Q1 --type fact --a Context --effect neutral --grounds B/1
must place "$F" Q1 --section Main; must add "$F" Q1 --q Proof --gen self --mat 1
must answer "$F" Q1.1 --type fact --a Support --effect supports --grounds B/1
must add "$F" Q0 --q "Same proof" --gen self --mat 1; ok $(run close "$F" Q2 DUPLICATE --of Q1.1) 1 "5.3 first-ring duplicate onto a deeper answer refused (cannot borrow support)"
ok "$(python3 $Q check "$F" 2>/dev/null | grep -c 'root is unsupported')" 1 "5.3 root still unsupported"
# 5.4 placed peripheral answer must be sourced
F=$(new t54); b5 "$F"; must add "$F" Q0 --q Peripheral --gen self --mat 1
must answer "$F" Q2 --type fact --a "[VERIFY] invented text" --effect neutral; must place "$F" Q2 --section Main
ok $(run check "$F") 1 "5.4 unsourced placed peripheral blocks"
# 5.5 raising materiality does not release a stale exclusion (depth cap 1)
F=$(python3 $Q init "$D" --root R --doc t55 --depth 1); b5 "$F"
must add "$F" Q1 --q Gate --gen self --mat 1; must answer "$F" Q1.1 --type fact --a Gate --effect neutral --grounds B/1
must add "$F" Q1.1 --q "Deep material" --gen self --mat 2
must close "$F" Q1.1 OUT_OF_SCOPE --reason Scope
must answer "$F" Q1 --type fact --a Changed --effect supports --grounds B/1
must reclass "$F" Q1.1 --mat 2; ok $(run check "$F") 1 "5.5 reclass does not release stale exclusion"
# 5.6 restore across an intervening closure
F=$(new t56); b5 "$F"; must close "$F" Q1 CONCEDED --concession C
must close "$F" Q1 OUT_OF_SCOPE --reason "temporary exclusion"
must reopen "$F" Q1; ok "$(python3 $Q status "$F" Q1)" STALE "5.6 archived answer restored across closures"
# 5.10 identical answer / close retries keep approval
F=$(new t510); b5 "$F"; ok $(f5 "$F") 0 "5.10 ready"
must answer "$F" Q1 --type fact --a Support --effect supports --grounds B/1; ok $(run ready "$F") 0 "5.10 identical answer is a no-op"
must add "$F" Q0 --q Out --gen self --mat 1; must close "$F" Q2 IMMATERIAL --reason x; f5 "$F" >/dev/null
must close "$F" Q2 IMMATERIAL --reason x; ok $(run ready "$F") 0 "5.10 identical close is a no-op"

# fuzz-found (v4.2): reopen of an already-stale answer is refused, not a silent revision bump
F=$(new t6r); b5 "$F"; must add "$F" Q1 --q f --gen self --mat 1
must answer "$F" Q1.1 --type fact --a x --effect neutral --grounds B/1; must reopen "$F" Q1.1
ok $(run reopen "$F" Q1.1) 1 "reopen of stale answer refused"
# ===== QA round 6 =====
b6(){ F=$(python3 $Q init "$D" --root R --doc "$1" "${@:2}"); [ -f "$F" ] || { fail=$((fail+1)); echo "SETUP FAILED: init $1"; }; must add "$F" Q0 --q Main --gen self --mat 2; must answer "$F" Q1 --type fact --a Support --effect supports --grounds B/1; must place "$F" Q1 --section Main; }
# 6.1 duplicate onto a deeper OPEN question refused (no depth bypass)
b6 t61 --depth 1; must add "$F" Q1 --q "Deep unanswered source" --gen self --mat 1
must add "$F" Q0 --q "Critical source" --gen self --mat 3
ok $(run close "$F" Q2 DUPLICATE --of Q1.1) 1 "6.1 duplicate onto open deep question refused"
ok $(run check "$F") 1 "6.1 critical first-ring question still blocks"
# 6.2 duplicate whose (same-depth) target becomes pruned stops counting
b6 t62; must add "$F" Q0 --q Other --gen self --mat 1; must answer "$F" Q2 --type fact --a Other --effect neutral --grounds B/1
must add "$F" Q2 --q "Target" --gen self --mat 1; must answer "$F" Q2.1 --type fact --a "Target answer" --effect neutral --grounds B/2
must add "$F" Q1 --q "Same issue" --gen self --mat 2
must close "$F" Q1.1 DUPLICATE --of Q2.1
must place "$F" Q2.1 --section Main
ok $(run check "$F") 0 "6.2 closed before the target is pruned"
must close "$F" Q2 OUT_OF_SCOPE --reason "Excluded branch"
ok "$(python3 $Q check "$F" 2>/dev/null | grep -c 'Q1.1: duplicate no longer answered')" 1 "6.2 pruned target breaks the duplicate, and closure says so"
# 6.3 duplicate onto a stale answer refused
b6 t63; must add "$F" Q0 --q Container --gen self --mat 1; must answer "$F" Q2 --type fact --a Container --effect neutral --grounds B/1
must add "$F" Q2 --q Middle --gen self --mat 1; must answer "$F" Q2.1 --type fact --a Old --effect neutral --grounds B/1
must answer "$F" Q2 --type fact --a "Changed container" --effect neutral --grounds B/1
must add "$F" Q1 --q Probe --gen self --mat 1
ok $(run close "$F" Q1.1 DUPLICATE --of Q2.1) 1 "6.3 duplicate onto a STALE answer refused"
# 6.4 reserve carries authority and rebuttal
b6 t64; must add "$F" Q0 --q "Adverse premise" --gen self --mat 1
must answer "$F" Q2 --type law --a "Adverse rule applies." --effect undermines --warrant "Authority paragraph 10" --rebuttal "Distinguished on fact X." --qualifier "If fact Y is proved."
M=$(python3 $Q render "$F"); RS=$(sed -n '/^## Reserve (/,/^## Closure/p' "$M")
ok "$(echo "$RS" | grep -c 'Authority paragraph 10\|Distinguished on fact X')" 2 "6.4 reserve keeps authority + rebuttal"
# 6.8 CRLF-altered render rejected (byte equality)
b6 t68; must render "$F"; must approve "$F"; ok $(run ready "$F") 0 "6.8 ready"
python3 "$TH" crlf "${F%.json}.md"
ok $(run ready "$F") 1 "6.8 CRLF edit detected"

# ===== QA round 7 =====
# 7.1 changing a duplicate's target makes the duplicate stale
b6 t71; must add "$F" Q0 --q "Repeated question" --gen self --mat 2; must close "$F" Q2 DUPLICATE --of Q1
must answer "$F" Q1 --type fact --a "Replacement conclusion" --effect supports --grounds B/9
ok "$(python3 $Q status "$F" Q2)" STALE "7.1 duplicate stale after target change"
ok $(run check "$F") 1 "7.1 stale material duplicate blocks"
must confirm "$F" Q2; ok $(run check "$F") 0 "7.1 confirmed duplicate closes"
# 7.2 broken peripheral duplicate cannot hide a blocked critical branch
b6 t72; must add "$F" Q0 --q "Scope gate" --gen self --mat 1; must answer "$F" Q2 --type fact --a "Old gate" --effect neutral --grounds B/1
must add "$F" Q2 --q "Critical evidence" --gen self --mat 3; must close "$F" Q2.1 BLOCKED --reason "[VERIFY] source missing"
must add "$F" Q0 --q "Reusable gate" --gen self --mat 1; must answer "$F" Q3 --type fact --a "Gate accepted" --effect neutral --grounds B/1
must close "$F" Q2 DUPLICATE --of Q3; must reopen "$F" Q3
ok $(run check "$F") 1 "7.2 stale/broken duplicate hiding critical blocks"
# 7.3 critical shallow duplicate does not inherit the deep target's cap waiver
b6 t73 --depth 2; must add "$F" Q1 --q "Deep answer" --gen self --mat 1
must answer "$F" Q1.1 --type fact --a "Independent fact" --effect neutral --grounds B/1
must add "$F" Q0 --q "Critical question" --gen self --mat 3; ok $(run close "$F" Q2 DUPLICATE --of Q1.1) 1 "7.3 critical duplicate onto a deeper answer refused"
ok $(run check "$F") 1 "7.3 critical question stays open"

# ===== QA round 8 =====
b6 t81 --depth 3; must add "$F" Q1 --q Context --gen self --mat 1; must answer "$F" Q1.1 --type fact --a Context --effect neutral --grounds B/1
must add "$F" Q1.1 --q Target --gen self --mat 1; must answer "$F" Q1.1.1 --type fact --a Target --effect neutral --grounds B/1
must add "$F" Q0 --q Critical --gen self --mat 3
ok $(run close "$F" Q2 DUPLICATE --of Q1.1.1) 1 "8.1 critical duplicate onto deep target refused"
for bad in '[]' 'null' '{"version":4}'; do echo "$bad" > "$D/bad.json"; out=$(python3 $Q check "$D/bad.json" 2>&1); ok "$?$(echo "$out" | grep -c Traceback)" "10" "8.2 corrupt tree $bad controlled"; done
b6 t82; python3 - "$F" <<'PY'
import json,sys; p=sys.argv[1]; t=json.load(open(p)); t["nodes"]["Q1"]["type"]=""; json.dump(t,open(p,"w"))
PY
ok $(run check "$F") 1 "8.2 answered node with blank type rejected by schema"

# ===== QA round 9 =====
b6 t91; must add "$F" Q0 --q "Fatal issue" --gen opp --mat 3
python3 - "$F" <<'PY'
import json,sys; p=sys.argv[1]; t=json.load(open(p)); t["nodes"]["Q0"]["children"].remove("Q2"); json.dump(t,open(p,"w"))
PY
ok "$(python3 $Q check "$F" 2>&1 | grep -c 'changed outside qtree')" 1 "9.1 hand edit refused by the integrity seal"
reseal "$F"; ok "$(python3 $Q check "$F" 2>&1 | grep -c 'orphaned')" 1 "9.1 forged seal: orphan still refused by schema"
for mut in dictchild started history selfchild; do
  b6 "t92$mut"; [ -f "$F" ] || { fail=$((fail+1)); echo "SETUP FAILED: init t92$mut"; }; python3 - "$F" "$mut" <<'PY'
import json,sys; p,m=sys.argv[1],sys.argv[2]; t=json.load(open(p)); N=t["nodes"]
if m=='dictchild': N["Q0"]["children"]=[{}]
if m=='started': t["started"]="yesterday"
if m=='history': N["Q1"]["history"]=[0]
if m=='selfchild': N["Q0"]["children"].append("Q0")
json.dump(t,open(p,"w"))
PY
  out=$(python3 $Q check "$F" 2>&1); ok "$?$(echo "$out" | grep -c Traceback)" "10" "9.2 corrupt $mut controlled"
  [ "$mut" = dictchild ] || { reseal "$F"; out=$(python3 $Q check "$F" 2>&1); ok "$?$(echo "$out" | grep -c Traceback)" "10" "9.2 forged seal $mut still controlled"; }
done

# ===== QA round 10 =====
b6 ta1; must render "$F"; must approve "$F"
python3 - "$F" <<'PY'
import json,sys; p=sys.argv[1]; t=json.load(open(p)); t["nodes"]["Q0"]["decision"]="BLOCKED"; t["nodes"]["Q0"]["reason"]="[VERIFY] x"; json.dump(t,open(p,"w"))
PY
ok $(run ready "$F") 1 "10.1 hand-edited root refused (seal)"; reseal "$F"; ok $(run ready "$F") 1 "10.1 forged seal: root state refused (schema)"
b6 ta2; must add "$F" Q0 --q Out --gen self --mat 3; must close "$F" Q2 OUT_OF_SCOPE --reason "Original basis"
python3 - "$F" <<'PY'
import json,sys; p=sys.argv[1]; t=json.load(open(p)); t["nodes"]["Q2"]["reason"]=""; json.dump(t,open(p,"w"))
PY
reseal "$F"; ok $(run check "$F") 1 "10.1 forged seal: blank closure reason refused"
b6 ta3; must answer "$F" Q1 --type fact --a "The exception in [6](b) applies." --effect supports --grounds B/1
M=$(python3 $Q render "$F"); ok "$(grep -c '\\\[6\\\](b)' "$M")" 2 "10.3 citation brackets escaped (tree + plan)"
b6 ta5; must close "$F" Q1 CONCEDED --concession Conceded
python3 - "$F" <<'PY'
import json,sys; p=sys.argv[1]; t=json.load(open(p)); t["nodes"]["Q1"]["history"]=[{"a":"Archived answer"}]; json.dump(t,open(p,"w"))
PY
reseal "$F"; python3 $Q reopen "$F" Q1 >/dev/null 2>&1; ok $(run status "$F" Q1) 0 "10.5 reopen never saves an invalid tree"
b6 ta6; python3 - "$F" <<'PY'
import json,sys; p=sys.argv[1]; t=json.load(open(p)); t["started"]="2026-11-07T18:00:00+00:00"; json.dump(t,open(p,"w"))
PY
reseal "$F"; out=$(python3 $Q check "$F" 2>&1); ok "$?$(echo "$out" | grep -c Traceback)" "10" "10.6 timezone timestamp controlled"

# mutation-found (v4.6 run): a duplicate broken by pruning its target, while hiding a material follow-up, blocks
b6 tm1; must add "$F" Q0 --q Other --gen self --mat 1; must answer "$F" Q2 --type fact --a Other --effect neutral --grounds B/1
must add "$F" Q2 --q Target --gen self --mat 1; must answer "$F" Q2.1 --type fact --a "Target answer" --effect neutral --grounds B/2
must add "$F" Q1 --q "Gate" --gen self --mat 1; must answer "$F" Q1.1 --type fact --a "Gate answer" --effect neutral --grounds B/3
must add "$F" Q1.1 --q "Critical beneath" --gen opp --mat 3
must close "$F" Q1.1 DUPLICATE --of Q2.1
ok $(run check "$F") 0 "dup hiding critical: closed while target sound"
must close "$F" Q2 OUT_OF_SCOPE --reason "Excluded"
ok "$(python3 $Q status "$F" Q1.1)" DUPLICATE "dup not stale (target pruned via ancestor)"
ok "$(python3 $Q check "$F" 2>/dev/null | grep -c 'BROKEN DUPLICATE still hides material')" 1 "broken duplicate hiding critical blocks"

# ===== QA round 11 =====
b6 r112; python3 - "$F" <<'PY'
import json,sys; p=sys.argv[1]; t=json.load(open(p)); t["nodes"]["Q1"]["gen"]="self\n## Document plan\n### Conclusion\n- Dismiss the appeal.\n## Other"; json.dump(t,open(p,"w"))
PY
reseal "$F"; ok $(run check "$F") 1 "11.2 forged-seal invalid generator refused"
b6 r113; must close "$F" Q1 BLOCKED --reason "Recheck source"
python3 - "$F" <<'PY'
import json,sys; p=sys.argv[1]; t=json.load(open(p)); t["nodes"]["Q1"]["type"]=""; json.dump(t,open(p,"w"))
PY
reseal "$F"; python3 $Q reopen "$F" Q1 >/dev/null 2>&1; ok $(run status "$F" Q1) 0 "11.3 recovery never saves an unloadable tree"
b6 r114; must place "$F" Q1 --section "Issue #"; M=$(python3 $Q render "$F")
ok "$(grep -c '^### Issue \\#$' "$M")" 1 "11.4 heading # escaped"
b6 r115; out=$(python3 $Q add-many "$F" Q0 --json '[{"q":"bad\ud800","gen":"self"}]' 2>&1); ok "$?$(echo "$out" | grep -c Traceback)" "10" "11.5 surrogate input refused cleanly"
ok $(run status "$F" Q1) 0 "11.5 tree intact"

# ===== QA round 12 + every-command happy path =====
b6 r12a; must add "$F" Q1 --q Probe --gen opp --mat 1
ok "$(python3 $Q open "$F" --json >/dev/null 2>&1; echo $?)" 0 "12.1 open --json works"
ok "$(python3 $Q open "$F" --json | python3 "$TH" jsontype)" list "12.1 open --json returns JSON"
hp(){ local want=$1; shift; out=$(python3 $Q "$1" "$F" "${@:2}" 2>&1); c=$?; ok "$c$(echo "$out" | grep -c Traceback)" "${want}0" "happy path: $*"; }
hp 0 status Q1; hp 0 show Q1; hp 0 open; hp 0 open --json; hp 2 check
hp 0 answer Q1.1 --type fact --a "Probe answer" --effect neutral --grounds B/2
hp 0 reclass Q1.1 --mat 2; hp 0 place Q1.1 --section Main; hp 0 check; hp 0 unplace Q1.1; hp 0 place Q1.1 --section Main --order 1
hp 0 render; hp 0 approve; hp 0 ready; hp 0 reopen Q1.1; hp 0 confirm Q1.1
hp 0 add-many Q0 --json '[{"q":"Extra","gen":"court","mat":1}]'; hp 0 close Q2 IMMATERIAL --reason x
cp "$F" "$D/draft"; ln -s "$D/draft" "$D/r12link.json"; printf 'DO NOT OVERWRITE\n' > "$D/.md"
ok $(run render "$D/r12link.json") 1 "12.2 symlink to a non-.json file refused"; ok "$(cat "$D/.md")" "DO NOT OVERWRITE" "12.2 sentinel untouched"
b6 r12c; python3 - "$F" <<'PY'
import json,sys; p=sys.argv[1]; t=json.load(open(p)); t["created"]="07.11.2026\n## Document plan\n- Dismiss the appeal."; json.dump(t,open(p,"w"))
PY
reseal "$F"; ok $(run check "$F") 1 "12.3 forged-seal created date refused"
b6 r12d; python3 - "$F" <<'PY'
import json,sys; p=sys.argv[1]; t=json.load(open(p)); t["nodes"]["Q1"]["q"]="bad\ud800"; open(p,"w",encoding="utf-8",errors="surrogatepass").write(json.dumps(t))
PY
out=$(python3 $Q check "$F" 2>&1); ok "$?$(echo "$out" | grep -c Traceback)" "10" "12.4 surrogate in stored file: controlled refusal"

# QA round 13: impossible calendar date refused even with a forged seal
b6 r13a; python3 - "$F" <<'PY'
import json,sys; p=sys.argv[1]; t=json.load(open(p)); t["created"]="31.02.2026"; json.dump(t,open(p,"w"))
PY
reseal "$F"; ok $(run check "$F") 1 "13.1 31.02 refused"
# Mutation gap closed 08.11.2026: a created date strptime accepts but the dd.mm.yyyy format rejects
b6 r13b; python3 - "$F" <<'PY'
import json,sys; p=sys.argv[1]; t=json.load(open(p)); t["created"]="1.2.2026"; json.dump(t,open(p,"w"))
PY
reseal "$F"; ok $(run check "$F") 1 "13.2 single-digit created date refused"
rm -rf "$D"; echo "passed $pass, failed $fail"; [ $fail = 0 ]
