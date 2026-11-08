#!/usr/bin/env python3
"""Mutation test: each planted bug must be caught by the fuzzer. Usage: mutate.py [runs] [steps]"""
import os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.environ.get("QT_PATH") or os.path.join(HERE, "..", "qtree.py")
FUZZ = os.path.join(HERE, "fuzz_qtree.py")
REG = os.path.join(HERE, "test_qtree.sh")
M = [
 ("qualifier dropped from plan", 's += f" [Qualifier: {esc(n[\'qualifier\'])}]"', "pass"),
 ("stale duplicate still counts", '    return (n["decision"] == "DUPLICATE" and live(t, i) and not n["stale"]', '    return (n["decision"] == "DUPLICATE" and live(t, i)'),
 ("duplicate onto unsound target accepted", '    if not sound(t, target):\n        return f"{target} is', '    if False:\n        return f"{target} is'),
 ("place ignores order", 't["nodes"][a.id]["order"] = " ".join(a.section.split()), a.order', 't["nodes"][a.id]["order"] = " ".join(a.section.split()), 0'),
 ("reclass ignores materiality", '            n["mat"] = a.mat', '            pass'),
 ("reserve drops support", '        L += support_lines(N[i])\n    if not res:', '    if not res:'),
 ("[VERIFY] ignored in slots", 'if VERIFY.search(n[k] or ""):\n            bad.append', 'if False:\n            bad.append'),
 ("no invalidation of follow-ups", '        if dn["decision"] != "OPEN" and not dn["stale"]:', '        if False:'),
 ("ready ignores approval", 'appr = t.get("approved_rev") == t["rev"] and t.get("approved_hash") == digest(t)', 'appr = True'),
 ("pruning never applied", 'return any(t["nodes"][a]["decision"] in PRUNING for a in ancestors(t, i))', 'return False'),
 ("evidence dropped from plan", '(("grounds", "Evidence"), ("warrant", "Authority"),\n                                                      ("rebuttal", "Meets"))', '(("warrant", "Authority"),\n                                                      ("rebuttal", "Meets"))'),
 ("BLOCKED material passes", '(F if mat else R).append(f"{i}: BLOCKED', 'R.append(f"{i}: BLOCKED'),
 ("stale exclusion may hide critical", 'if n["decision"] in PRUNING and (n["stale"] or bad_dup):', 'if n["decision"] in PRUNING and bad_dup:'),
 ("unmet undermining passes", 'if n["effect"] == "undermines" and (blank(n["rebuttal"]) or VERIFY.search(n["rebuttal"])):', 'if False:'),
 ("ready skips render freshness", '        fresh = render_current(t, a.file)\n        up', '        fresh = True\n        up'),
 ("duplicate does not lift materiality", '            m = max(m, o["mat"])', '            pass'),
 ("root conclusion dropped from plan", 'f"- Q0: {fmt_answer(N[\'Q0\'])}"]', '""]'),
 ("answer does nothing", 'def cmd_answer(a):\n', 'def cmd_answer(a):\n    return\n'),
 ("placed peripheral skips sourcing", '(F if (mat or placed) else R).append(f"{i}: {x}"', '(F if mat else R).append(f"{i}: {x}"'),
 ("target change leaves duplicate current", '        if o["decision"] == "DUPLICATE" and o["dup_of"] == i and not o["stale"]:\n            o["stale"] = True', '        if False:\n            o["stale"] = True'),
 ("duplicate onto deeper target accepted", '    if depth(target) > depth(i):', '    if False:'),
 ("reserve wording wrong", '        L.append(f"- {i}: {esc(N[i][\'q\'])} → {fmt_answer(N[i])}")', '        L.append(f"- {i}: {esc(N[i][\'q\'])} → WRONG")'),
 ("section heading wrong", '        L.append(f"### {esc(sec)}")', '        L.append("### WRONG SECTION")'),
 ("concession text substituted", 'concession=(a.concession or "").strip() if st == "CONCEDED" else "",', 'concession="WRONG" if st == "CONCEDED" else "",'),
 ("broken duplicate may hide material", 'bad_dup = n["decision"] == "DUPLICATE" and not n["stale"] and check_duplicate(t, i, n["dup_of"]) is not None', 'bad_dup = False'),
 ("plan ignores order", '    order = lambda x: (N[x]["order"], key(x))', '    order = lambda x: (0, key(x))'),
 ("reserve emptied", '    res = [i for i in walk(t) if i != "Q0" and status(t, i) == "ANSWERED"', '    res = [] and [i for i in walk(t) if i != "Q0" and status(t, i) == "ANSWERED"'),
 ("answer type forced", 'def cmd_answer(a):\n    if blank(a.a):', 'def cmd_answer(a):\n    a.type = "fact"\n    if blank(a.a):'),
 ("plan entry prefixed", '            L.append(f"- {i}: {fmt_answer(N[i])}")', '            L.append(f"- {i}: NOT {fmt_answer(N[i])}")'),
 ("plan entry suffixed", '            L.append(f"- {i}: {fmt_answer(N[i])}")', '            L.append(f"- {i}: {fmt_answer(N[i])} (withdrawn)")'),
 ("conceded label dropped", '        return f"(Conceded) {esc(n[\'concession\'])}"', '        return f"{esc(n[\'concession\'])}"'),
 ("orphan check removed", '    if seen != set(t["nodes"]):', '    if False:'),
 ("integrity seal not checked", '        if not isinstance(t, dict) or seal_of(t) is None or t.get("seal") != seal_of(t):', '        if not isinstance(t, dict):'),
 ("markdown not escaped", '    return re.sub(r"([\\\\\\[\\]*_~|#])", r"\\\\\\1", s)', '    return s'),
 ("surplus prose in plan", '    up = unplaced(t)\n    L.append(', '    up = unplaced(t)\n    L.append("- Withdraw all grounds.")\n    L.append('),
 ("root semantic check removed", '        if i == "Q0" and (n["decision"] != "ANSWERED"', '        if False and (n["decision"] != "ANSWERED"'),
 ("orphan support line in plan", '        L.append(f"### {esc(sec)}")', '        L.append(f"### {esc(sec)}")\n        L.append("  - Withdraw all grounds.")'),
 ("save without validation", '            problem = schema_problem(t)\n            if problem:\n                die(f"this operation would leave', '            problem = None\n            if problem:\n                die(f"this operation would leave'),
 ("generator not validated", '        if fam not in GENS or (GENS[fam] and sub not in GENS[fam]) or (not GENS[fam] and sub):\n            return f"{i}: bad generator', '        if False:\n            return f"{i}: bad generator'),
 ("render path not checked", '    if not f.endswith(".json"):\n        die(f"refusing to render', '    if False:\n        die(f"refusing to render'),
 ("created date not validated", '                or not re.fullmatch(r"\\d\\d\\.\\d\\d\\.\\d{4}", t["created"]):', '                or False:'),
 ("concession keeps old answer", '            for k in SLOTS:\n                n[k] = ""\n            n["type"] = n["effect"] = ""', '            pass'),
]
runs, steps = (sys.argv[1:3] + ["120", "80"][len(sys.argv[1:3]):])
if not (runs.isdigit() and steps.isdigit() and int(runs) >= 50):
    sys.exit("usage: mutate.py [runs>=50] [steps]")
src = open(SRC).read(); missed = []

def fuzz(path):
    r = subprocess.run([sys.executable, FUZZ, runs, steps, "7"], env=os.environ | {"QT_PATH": path, "QT_GUIDE": "0.6"},
                       capture_output=True, text=True, cwd=os.path.dirname(path))
    return r

_reg = subprocess.run(["bash", REG], capture_output=True, text=True)
if _reg.returncode != 0 or "failed 0" not in _reg.stdout:
    sys.exit("BASELINE REGRESSION SUITE NOT GREEN: " + _reg.stdout[-300:])
base = fuzz(SRC)
if base.returncode != 0:
    sys.exit(f"BASELINE NOT HEALTHY (exit {base.returncode}): fix the tool or fuzzer first\n{base.stdout[-500:]}{base.stderr[-500:]}")
for name, a, b in M:
    if src.count(a) != 1:
        print(f"SITE-MISSING {name}: mutation site matches {src.count(a)} times (need exactly 1) — update mutate.py"); missed.append(name); continue
    d = tempfile.mkdtemp(); p = os.path.join(d, "qtree.py"); open(p, "w").write(src.replace(a, b, 1))
    reg = subprocess.run(["bash", REG], env=os.environ | {"QT_PATH": p}, capture_output=True, text=True)
    reg_fail = next((l for l in reg.stdout.splitlines() if l.startswith("FAIL")), "")
    if reg_fail:                                         # the regression suite caught it: no need to fuzz
        print("KILLED  ", name, "· regression:", reg_fail[:100]); continue
    r = fuzz(p)
    first = next((l for l in r.stdout.splitlines() if l.startswith("==")), "")
    caught = r.returncode == 1 and bool(first)          # killed only by an identified invariant failure
    infra = not caught and r.returncode not in (0, 3)
    print(("KILLED  " if caught else "RUNNER-FAILED" if infra else "SURVIVED"), name, "·", (first or (r.stderr.strip().splitlines() or [""])[-1])[:110])
    if not caught: missed.append(name)
print(f"{len(M) - len(missed)}/{len(M)} mutants killed  (excluded as equivalent: approval-hash check — approval is also bound to the revision)")
sys.exit(1 if missed else 0)
