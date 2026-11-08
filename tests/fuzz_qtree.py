#!/usr/bin/env python3
"""Randomised invariant fuzzer for qtree. INDEPENDENT ORACLE: re-implements the rules from
SKILL.md; never calls production predicates. Usage: fuzz_qtree.py [runs] [steps] [seed]"""
import contextlib, importlib.util, io, json, os, random, re, sys, tempfile, traceback

spec = importlib.util.spec_from_file_location("qtree", os.environ.get("QT_PATH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "qtree.py"))
Q = importlib.util.module_from_spec(spec); spec.loader.exec_module(Q)
V = re.compile(r"\[\s*verify", re.I)

def call(argv):
    sys.argv = ["qtree"] + argv
    out, err = io.StringIO(), io.StringIO(); code = 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            Q.main()
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
        except BaseException:
            return "CRASH", out.getvalue(), traceback.format_exc()
    return code, out.getvalue(), err.getvalue()

# ---------- independent oracle (re-implements SKILL.md; no production predicates) ----------
PR = {"CONCEDED", "OUT_OF_SCOPE", "IMMATERIAL", "DUPLICATE"}
def k(i): return tuple(int(x) for x in i[1:].split(".")) if i != "Q0" else ()
def anc(a, d): return d != a and (a == "Q0" or d.startswith(a + "."))
def pr(N, i): return any(anc(a, i) and N[a]["decision"] in PR for a in N)
def st(N, i): return "PRUNED" if pr(N, i) else ("STALE" if N[i]["stale"] else N[i]["decision"])
def canon(N, i):
    seen = set()
    while N[i]["decision"] == "DUPLICATE":
        if i in seen or N[i]["dup_of"] not in N: return None
        seen.add(i); i = N[i]["dup_of"]
    return i
def emat(N, i):
    return max([N[i]["mat"]] + [N[j]["mat"] for j in N if j != i and N[j]["decision"] == "DUPLICATE" and not pr(N, j) and N[j]["dup_of"] == i])
def good(n):
    if n["decision"] == "CONCEDED": return bool(n["concession"].strip()) and not V.search(n["concession"])
    if any(V.search(n[f] or "") for f in ("a", "grounds", "warrant", "qualifier", "rebuttal")): return False
    g, w = n["grounds"].strip(), n["warrant"].strip()
    return bool(n["a"].strip()) and {"fact": bool(g), "law": bool(w), "mixed": bool(g and w)}.get(n["type"], False)
def sound(N, i): return st(N, i) in ("ANSWERED", "CONCEDED") and good(N[i])
def dup_ok(N, i):
    n = N[i]; tg = n["dup_of"]
    return (n["decision"] == "DUPLICATE" and not pr(N, i) and not n["stale"] and tg in N and tg != i and len(k(tg)) <= len(k(i))
            and not anc(i, tg) and not anc(tg, i) and N[tg]["decision"] != "DUPLICATE" and sound(N, tg) and not N[tg]["stale"])
def edepth(N, i):
    return min([len(k(i))] + [len(k(j)) for j in N if N[j]["decision"] == "DUPLICATE" and N[j]["dup_of"] == i and not pr(N, j) and not N[j]["stale"]])
def path_ok(N, i):
    """The node answering i: i if sound, its target if i is a valid duplicate."""
    if N[i]["decision"] == "DUPLICATE": return N[i]["dup_of"] if dup_ok(N, i) else None
    return i if sound(N, i) and not N[i]["stale"] else None

def oracle_closed(t):
    N = t["nodes"]; th, cap = t["threshold"], t["depth_cap"]
    r = N["Q0"]
    if not r["a"].strip() or any(V.search(r[f] or "") for f in ("a", "grounds", "warrant", "qualifier", "rebuttal")): return False
    first = [c for c in r["children"] if not pr(N, c)]
    if not first: return False
    for i in N:
        if i == "Q0" or pr(N, i): continue
        n, s, m, d = N[i], st(N, i), emat(N, i) >= th, len(k(i))
        placed = bool(n["section"]) and s in ("ANSWERED", "CONCEDED")
        if m and s in ("OPEN", "STALE") and d <= cap: return False
        if (m or placed) and s in ("ANSWERED", "CONCEDED") and not good(n): return False
        if m and s == "BLOCKED": return False
        if (m or placed) and s == "ANSWERED" and n["effect"] == "undermines" and (not n["rebuttal"].strip() or V.search(n["rebuttal"])): return False
        if s == "ANSWERED" and emat(N, i) == 3 and d < cap:
            if not any(not pr(N, x) and path_ok(N, x) for x in n["children"]):
                return False
        if n["decision"] == "DUPLICATE" and not n["stale"] and m and not dup_ok(N, i): return False
        broken = n["decision"] == "DUPLICATE" and not n["stale"] and not dup_ok(N, i)
        if (n["stale"] or broken) and n["decision"] in PR and (any(anc(i, x) and emat(N, x) >= th for x in N) or (m and d > cap)): return False
    return any(path_ok(N, c) and N[path_ok(N, c)]["decision"] == "ANSWERED"
               and N[path_ok(N, c)]["effect"] == "supports" for c in first)

def E_(x):
    x = " ⏎ ".join((x or "").splitlines())
    x = x.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("`", "&#96;")
    return re.sub(r"([\\\[\]*_~|#])", r"\\\1", x)

def subst(n):
    return (n["decision"],) + tuple((n[x] or "").strip() for x in ("a", "grounds", "warrant", "qualifier", "rebuttal")) + (
        n["type"], n["effect"], n["concession"].strip(), n["dup_of"], n["reason"].strip())

def invariants(f, prev, argv, code):
    t = json.load(open(f)); N = t["nodes"]; E = []
    for i, n in N.items():
        for c in n["children"]:
            if c not in N: E.append(f"missing child {c}")
            elif c != (f"Q{k(c)[-1]}" if i == "Q0" else f"{i}.{k(c)[-1]}"): E.append(f"bad id {c}")
        if n["decision"] == "ANSWERED" and not n["a"].strip(): E.append(f"{i} answered blank")
        if n["decision"] == "CONCEDED" and (n["grounds"] or n["warrant"] or n["rebuttal"] or n["a"] or n["type"]):
            E.append(f"{i} concession keeps abandoned answer")
        if n["decision"] not in ("OPEN", "ANSWERED", "CONCEDED", "OUT_OF_SCOPE", "IMMATERIAL", "DUPLICATE", "BLOCKED", "DEFERRED"):
            E.append(f"{i} bad decision {n['decision']}")
    # dependency: any change of a decided node's substance stales every decided descendant
    if code == 0 and prev is not None and argv[0] in ("answer", "close", "reopen"):
        P = prev["nodes"]; i = argv[2]
        if i in P and P[i]["decision"] != "OPEN" and subst(P[i]) != subst(N[i]) or argv[0] == "reopen":
            for d in N:
                if anc(i, d) and N[d]["decision"] != "OPEN" and not N[d]["stale"]:
                    E.append(f"after {argv[0]} {i}, descendant {d} decided and not stale")
                if N[d]["decision"] == "DUPLICATE" and N[d]["dup_of"] == i and not N[d]["stale"] and P.get(d, {}).get("decision") == "DUPLICATE":
                    E.append(f"after {argv[0]} {i}, duplicate {d} relying on it not stale")
    if code == 0 and prev is not None:
        P = prev["nodes"]; op = argv[0]
        def arg(name):
            idx = [j for j, x in enumerate(argv) if x == name]
            return argv[idx[-1] + 1].strip() if idx else ""
        if op == "answer" and argv[2] in N:
            n = N[argv[2]]
            if argv[2] != "Q0" and n["type"] != arg("--type"):
                E.append("postcondition: answer did not record the type")
            if n["decision"] != "ANSWERED" or n["stale"] or n["a"] != arg("--a") or n["effect"] != arg("--effect") \
               or any(n[x] != arg("--" + x) for x in ("grounds", "warrant", "qualifier", "rebuttal")):
                E.append("postcondition: answer did not record what was given")
        if op == "close" and argv[2] in N and argv[3] == "CONCEDED" and N[argv[2]]["concession"] != arg("--concession"):
            E.append("postcondition: concession text not stored as given")
        if op == "close" and argv[2] in N and N[argv[2]]["decision"] != argv[3]:
            E.append("postcondition: close did not record the decision")
        if op == "place" and argv[2] in N and N[argv[2]]["section"] != " ".join(arg("--section").split()):
            E.append("postcondition: place did not record the section")
        if op == "place" and argv[2] in N and N[argv[2]]["order"] != int(arg("--order") or 0):
            E.append("postcondition: place did not record the order")
        if op == "reclass" and argv[2] in N and arg("--mat") and N[argv[2]]["mat"] != int(arg("--mat")):
            E.append("postcondition: reclass did not record materiality")
        if op == "confirm" and argv[2] in N and argv[2] in P and N[argv[2]]["decision"] != P[argv[2]]["decision"]:
            E.append("postcondition: confirm changed the decision")
        if op == "close" and argv[2] in N and argv[3] == "DUPLICATE" and not dup_ok(N, argv[2]) and not pr(N, argv[2]):
            E.append("postcondition: close DUPLICATE accepted an invalid target")
        if op == "unplace" and argv[2] in N and N[argv[2]]["section"]:
            E.append("postcondition: unplace left a section")
        if op == "confirm" and argv[2] in N and N[argv[2]]["stale"]:
            E.append("postcondition: confirm left the node stale")
        if op == "add" and not any(N[c]["q"].lower().split() == arg("--q").lower().split() for c in N.get(argv[2], {"children": []})["children"]):
            E.append("postcondition: add did not create or find the question")
    core = lambda x: json.dumps({kk: ({nid: {fk: fv for fk, fv in nv.items() if fk != "history"} for nid, nv in v.items()} if kk == "nodes" else v)
                                 for kk, v in x.items() if kk not in ("rev", "updated", "approved_rev", "approved_hash", "approved_at")}, sort_keys=True)
    if prev is not None and argv[0] not in Q_READONLY and code == 0 and t.get("approved_rev") == t["rev"] and core(prev) != core(t):
        E.append(f"approval survived a real change by {argv[0]}")
    if prev is not None and code == 0 and core(prev) == core(t) and t["rev"] != prev["rev"] and argv[0] != "approve":
        E.append(f"no-op {argv[0]} bumped the revision")
    c, _, _ = call(["check", f]); STATS["check", c] += 1
    if c == "CRASH": E.append("check crashed")
    else:
        want = oracle_closed(t)
        if c in (0, 2) and not want: E.append("tool closed, oracle says not closed")
        if c == 1 and want: E.append("FALSE REFUSAL: oracle says closed, tool refused")
    r, _, _ = call(["ready", f]); STATS["ready", r] += 1
    if r != "CRASH":
        placed_all = all(N[i]["section"] for i in N if i != "Q0" and st(N, i) in ("ANSWERED", "CONCEDED") and emat(N, i) >= t["threshold"])
        expect = oracle_closed(t) and t.get("approved_rev") == t["rev"] and placed_all and f not in TAMPERED
        if expect and r != 0: E.append("FALSE READY REFUSAL: oracle expects ready")
        if not expect and r == 0: E.append("ready passed, oracle expects refusal")
    if r == "CRASH": E.append("ready crashed")
    elif r == 0:
        md = open(f[:-5] + ".md").read().splitlines()
        a0 = [j for j, l in enumerate(md) if l.startswith("## Document plan (")]
        b0 = [j for j, l in enumerate(md) if l.startswith("## Reserve (")]
        if len(a0) != 1 or len(b0) != 1: E.append("ready: render does not have exactly one plan and one reserve heading"); return E
        lines = md[a0[0] + 1:b0[0]]
        # 9 exactly one root conclusion, first in the plan
        nonblank = [l for l in lines if l.strip()]
        if nonblank[:2] != ["### Conclusion", f"- Q0: {E_(N['Q0']['a'])}" + (f" [Qualifier: {E_(N['Q0']['qualifier'])}]" if N['Q0']['qualifier'] else "")]:
            E.append("ready: plan does not open with the root Conclusion")
        if sum(1 for l in lines if l.startswith("- Q0: ")) != 1: E.append("ready: root conclusion not exactly once")
        for i, n in N.items():
            tag = f"- {i}: "
            at = [j for j, l in enumerate(lines) if l.startswith(tag)]
            s = st(N, i)
            if i != "Q0" and s not in ("ANSWERED", "CONCEDED") and at: E.append(f"ready: {s} {i} in plan")
            if i != "Q0" and s in ("ANSWERED", "CONCEDED") and emat(N, i) >= t["threshold"] and not at: E.append(f"ready: material {i} unplaced")
            for j in at:
                block = []
                for l in lines[j + 1:]:
                    if not l.startswith("  - "): break
                    block.append(l)
                exp = [] if n["decision"] == "CONCEDED" else [f"  - {lab}: {E_(n[x])}" for x, lab in (("grounds", "Evidence"), ("warrant", "Authority"), ("rebuttal", "Meets")) if n[x]]
                if block != exp: E.append(f"ready: plan support for {i} differs from tree")
                exp_line = (f"- {i}: (Conceded) {E_(n['concession'])}" if n["decision"] == "CONCEDED" else
                            f"- {i}: {E_(n['a'])}" + (f" [Qualifier: {E_(n['qualifier'])}]" if n["qualifier"] else ""))
                if lines[j] != exp_line: E.append(f"ready: plan entry for {i} is not exactly the tree's wording")
        plan_ids = [l.split(":")[0][2:] for l in lines if l.startswith("- Q")]
        placed = [i for i in N if i != "Q0" and N[i]["section"] and st(N, i) in ("ANSWERED", "CONCEDED")]
        secs = []
        for i in sorted(placed, key=lambda x: (N[x]["order"], k(x))):
            if N[i]["section"] not in secs: secs.append(N[i]["section"])
        want = ["Q0"] + [i for sc in secs for i in sorted([x for x in placed if N[x]["section"] == sc], key=lambda x: (N[x]["order"], k(x)))]
        if plan_ids != want: E.append("ready: plan order differs from expected section/order")
        def ent(i):
            n = N[i]
            line = (f"- {i}: (Conceded) {E_(n['concession'])}" if n["decision"] == "CONCEDED" else
                    f"- {i}: {E_(n['a'])}" + (f" [Qualifier: {E_(n['qualifier'])}]" if n["qualifier"] else ""))
            sup = [] if n["decision"] == "CONCEDED" else [f"  - {lab}: {E_(n[x])}" for x, lab in (("grounds", "Evidence"), ("warrant", "Authority"), ("rebuttal", "Meets")) if n[x]]
            return [line] + sup
        expected = ["", "### Conclusion"] + ent("Q0")
        for sc in secs:
            expected.append(f"### {E_(sc)}")
            for i in sorted([x for x in placed if N[x]["section"] == sc], key=lambda x: (N[x]["order"], k(x))):
                expected += ent(i)
        unpl_ids = [i for i in sorted(N, key=k) if i != "Q0" and st(N, i) in ("ANSWERED", "CONCEDED") and emat(N, i) >= t["threshold"] and not N[i]["section"]]
        expected.append(f"- **Unplaced material answers:** {', '.join(unpl_ids)}" if unpl_ids else "- all material answers placed")
        expected.append("")
        if lines != expected: E.append("ready: document plan is not exactly the expected plan")
        heads = [l[4:] for l in lines if l.startswith("### ")]
        if heads != ["Conclusion"] + [E_(x) for x in secs]: E.append("ready: plan headings differ from expected sections")
        unpl = [i for i in N if i != "Q0" and st(N, i) in ("ANSWERED", "CONCEDED") and emat(N, i) >= t["threshold"] and not N[i]["section"]]
        for l in lines:
            if not (l == "" or l.startswith("### ") or l.startswith("- Q") or l.startswith("  - ")
                    or l == "- all material answers placed" or l.startswith("- **Unplaced material answers:** ")):
                E.append("ready: unexpected line in the document plan"); break
        cur = None
        for l in lines:
            if l.startswith("### "): cur = l[4:]
            elif l.startswith("- Q") and not l.startswith("- Q0: "):
                i = l.split(":")[0][2:]
                if i in N and cur != E_(N[i]["section"]): E.append(f"ready: {i} rendered under the wrong heading")
        rs = md[b0[0] + 1:]
        rs = rs[:next((j for j, l in enumerate(rs) if l.startswith("## Closure")), len(rs))]
        res_ids = [l.split(":")[0][2:] for l in rs if l.startswith("- Q")]
        want_res = sorted([i for i in N if i != "Q0" and st(N, i) == "ANSWERED" and emat(N, i) < t["threshold"]], key=k)
        if res_ids != want_res: E.append("ready: reserve membership differs from expected")
        for l in rs:
            if l.startswith("- Q"):
                i = l.split(":")[0][2:]
                if i in N:
                    n = N[i]
                    exp = f"- {i}: {E_(n['q'])} → {E_(n['a'])}" + (f" [Qualifier: {E_(n['qualifier'])}]" if n["qualifier"] else "")
                    if l != exp: E.append(f"ready: reserve wording for {i} differs from tree")
        for i, n in N.items():
            at = [j for j, l in enumerate(rs) if l.startswith(f"- {i}: ")]
            for j in at:
                block = []
                for l in rs[j + 1:]:
                    if not l.startswith("  - "): break
                    block.append(l)
                exp = [f"  - {lab}: {E_(n[x])}" for x, lab in (("grounds", "Evidence"), ("warrant", "Authority"), ("rebuttal", "Meets")) if n[x]]
                if block != exp: E.append(f"ready: reserve support for {i} differs from tree")
        if c == 1: E.append("ready while check fails")
    return E

import collections
TAMPERED = set()
def tamper(f, r):
    mp = f[:-5] + ".md"
    if not os.path.exists(mp): return False
    s = open(mp).read()
    edits = [lambda x: x.replace("\n## Closure", "\n### Inserted\n- Dismiss the appeal.\n## Closure", 1),
             lambda x: x.replace("- Q1: ", "- Q1: (edited) ", 1),
             lambda x: x + "extra line\n",
             lambda x: x.replace("Evidence: ", "Evidence: forged ", 1)]
    new = r.choice(edits)(s)
    open(mp, "w").write(new)
    return new != s
STATS = collections.Counter()
GUIDE = float(os.environ.get("QT_GUIDE", "0.5"))
Q_READONLY = {"open", "show", "check", "ready", "render", "approve", "status"}
GENS = ["paul:clarification", "paul:assumptions", "walton:precedent", "opp", "court", "self", "bad:gen", "walton:x", ""]
TEXT = ["Is it?", "  ", "Why so?", "What evidence?", "is it?", "Ç'est quoi — «x»?", "a" * 300, "x\ny", "[VERIFY] q?"]
SLOTV = ["B/1", "[VERIFY] x", " ", "s.21 §3", "[ verify ]", "Auth §2"]
JUNK = ["[null]", '[{"q":1,"gen":"self"}]', '[{"q":"x","gen":"self","mat":2.5}]', '[{"q":"x","gen":"self","mat":true}]',
        '{"q":"x"}', "nope", "[]", '[{"q":"x","gen":"self","extra":1}]']

def rnd_op(r, f, t):
    ids = list(t["nodes"]); i = r.choice(ids + ["Q999", "Q1.1.1", "Q0"])
    op = r.choice(["add"] * 4 + ["answer"] * 6 + ["close"] * 3 + ["reopen", "place", "place", "unplace", "confirm",
                                                                    "confirm", "approve", "render", "render", "addmany", "junk", "tamper"])
    if op == "add": return ["add", f, i, "--q", r.choice(TEXT), "--gen", r.choice(GENS), "--mat", str(r.choice([1, 2, 3, 3, 0, 4]))]
    if op == "addmany": return ["add-many", f, i, "--json", json.dumps([{"q": r.choice(TEXT), "gen": r.choice(GENS[:6]), "mat": r.choice([1, 2, 3])} for _ in range(r.randint(0, 3))])]
    if op == "junk": return ["add-many", f, i, "--json", r.choice(JUNK)]
    if op == "answer":
        n = t["nodes"].get(i)
        if n and n["a"] and r.random() < .35:     # re-submit identical, or tweak exactly one slot
            a = ["answer", f, i, "--type", n["type"] or "fact", "--a", n["a"] or "Yes.", "--effect", n["effect"] or "neutral"]
            for s in ("grounds", "warrant", "qualifier", "rebuttal"):
                if n[s]: a += [f"--{s}", n[s]]
            if r.random() < .6: a += ["--qualifier", r.choice(SLOTV)]
            return a
        a = ["answer", f, i, "--type", r.choice(["fact", "law", "mixed"]), "--a", r.choice(["Yes.", "No.", " ", "Maybe.", "[VERIFY] y"]),
             "--effect", r.choice(["supports", "supports", "undermines", "neutral"])]
        for s in ("grounds", "warrant", "rebuttal", "qualifier"):
            if r.random() < .6: a += [f"--{s}", r.choice(SLOTV)]
        return a
    same = [x for x in ids if t["nodes"][x]["q"].startswith("Same as ") and t["nodes"][x]["decision"] == "OPEN"]
    if same and r.random() < .5:
        x = r.choice(same); return ["close", f, x, "DUPLICATE", "--of", t["nodes"][x]["q"][8:-1]]
    if op == "close":
        a = ["close", f, i, r.choice(["CONCEDED", "OUT_OF_SCOPE", "IMMATERIAL", "DUPLICATE", "BLOCKED", "DEFERRED"])]
        if r.random() < .8: a += ["--reason", r.choice(["budget", "x", " ", "[VERIFY] src"])]
        if r.random() < .7: a += ["--concession", r.choice(["Conceded X.", "[VERIFY] c", " "])]
        if r.random() < .8: a += ["--of", r.choice(ids)]
        return a
    if op in ("reopen", "unplace", "confirm"): return [op, f, i]
    if op == "tamper": return ["tamper", f]
    if op == "place": return ["place", f, i, "--section", r.choice(["G1", "G2", " "]), "--order", str(r.randint(-1, 3))]
    return [op, f]

def complete_ops(r, f, t):
    """Guided: a valid sequence that drives the tree towards closed + approved + ready."""
    N = t["nodes"]; ops = []
    if not [c for c in N["Q0"]["children"] if not pr(N, c)]:
        ops.append(["add", f, "Q0", "--q", f"Main {r.random()}", "--gen", "self", "--mat", str(r.choice([2, 3]))])
        return ops
    for i in sorted(N, key=lambda x: (len(k(x)), k(x))):
        if i == "Q0" or pr(N, i): continue
        s = st(N, i); n = N[i]
        if s == "STALE":
            ops.append(["confirm", f, i] if r.random() < .6 else ["answer", f, i, "--type", "fact", "--a", f"A{i}", "--effect", "neutral", "--grounds", "B/9"]); continue
        if s == "OPEN" or (s == "ANSWERED" and not good(n)) or (s == "BLOCKED"):
            eff = "supports" if len(k(i)) == 1 and r.random() < .7 else r.choice(["neutral", "supports", "undermines"])
            a = ["answer", f, i, "--type", r.choice(["fact", "law", "mixed"]), "--a", f"Ans {i}", "--effect", eff,
                 "--grounds", f"B/{len(i)}", "--warrant", "Auth §1"]
            if eff == "undermines": a += ["--rebuttal", "Distinguished"]
            if r.random() < .3: a += ["--qualifier", "on the findings"]
            ops.append(a); continue
        if s == "ANSWERED" and n["mat"] == 3 and len(k(i)) < t["depth_cap"] and not n["children"]:
            ops.append(["add", f, i, "--q", f"Why {i}?", "--gen", "paul:assumptions", "--mat", str(r.choice([1, 2]))]); continue
        if s in ("ANSWERED", "CONCEDED") and not n["section"]:
            ops.append(["place", f, i, "--section", r.choice(["G1", "G2"]), "--order", str(r.randint(0, 2))])
    ops += [["render", f], ["approve", f]]
    return ops

def perturb_ops(r, f, t):
    """Semantic perturbations of a (near-)complete tree: the moves real drafting makes."""
    N = t["nodes"]
    ans = [i for i in N if i != "Q0" and st(N, i) == "ANSWERED"]
    withkids = [i for i in ans if N[i]["children"]]
    ops = []
    roll = r.random()
    if withkids and roll < .3:                       # change a premise that has decided follow-ups
        i = r.choice(withkids); n = N[i]
        ops.append(["answer", f, i, "--type", n["type"] or "fact", "--a", n["a"] + " (revised)", "--effect", n["effect"] or "supports",
                    "--grounds", "B/77", "--warrant", "Auth §9"])
    elif withkids and roll < .5:                     # exclude a question that has a branch beneath it
        i = r.choice(withkids)
        ops.append(["close", f, i, r.choice(["OUT_OF_SCOPE", "IMMATERIAL"]), "--reason", "scope decision"])
        if r.random() < .6:                          # ... then change the premise above it
            par = i.rsplit(".", 1)[0] if "." in i else "Q0"
            if par != "Q0" and st(N, par) == "ANSWERED":
                ops.append(["answer", f, par, "--type", "fact", "--a", "Premise changed", "--effect", "supports", "--grounds", "B/5"])
    elif ans and roll < .65:                         # an adverse answer with no rebuttal
        i = r.choice(ans)
        ops.append(["answer", f, i, "--type", "law", "--a", "Adverse authority", "--effect", "undermines", "--warrant", "X §3"])
    elif ans and roll < .8:                          # critical follow-up chain, then stale it
        i = r.choice(ans)
        ops += [["reclass", f, i, "--mat", "3"], ["add", f, i, "--q", f"Probe {i}?", "--gen", "opp", "--mat", "1"]]
    elif ans:                                        # duplicate a fresh question onto an answered one
        i = r.choice(ans)
        ops += [["add", f, "Q0", "--q", f"Same as {i}?", "--gen", "court", "--mat", str(r.choice([1, 3]))]]
    for _ in range(r.randint(0, 2)):
        ops += [["render", f], ["approve", f]]
    return ops

def chain_ops(r, f, t):
    """Compound scenarios real drafting produces but random generation almost never assembles."""
    N = t["nodes"]
    ans = [i for i in N if i != "Q0" and st(N, i) == "ANSWERED" and len(k(i)) <= 2]
    if not ans: return []
    i = r.choice(ans); tag = f"{r.randint(0, 99999)}"; c = None
    pick = r.random()
    if pick < .34:      # critical answer whose only (peripheral) probe goes stale
        return [["reclass", f, i, "--mat", "3"],
                ["add", f, i, "--q", f"Probe {tag}?", "--gen", "opp", "--mat", "1"],
                ["@answer-last", f, i, "fact"],
                ["answer", f, i, "--type", "fact", "--a", f"Revised {tag}", "--effect", N[i]["effect"] or "supports", "--grounds", "B/71"],
                ["render", f], ["approve", f]]
    if pick < .67:      # stale peripheral exclusion still hiding a critical question
        return [["add", f, i, "--q", f"Gate {tag}?", "--gen", "self", "--mat", "1"],
                ["@answer-last", f, i, "fact"],
                ["@add-under-last", f, i, f"Critical {tag}?", "3"],
                ["@close-last-last", f, i, "BLOCKED"],
                ["@close-last", f, i, "OUT_OF_SCOPE"],
                ["answer", f, i, "--type", "fact", "--a", f"Premise {tag}", "--effect", N[i]["effect"] or "supports", "--grounds", "B/72"],
                ["render", f], ["approve", f]]
    if pick < .84:      # critical answer interrogated only via a duplicate link, then its premise changes
        others = [x for x in N if x != "Q0" and st(N, x) == "ANSWERED" and good(N[x]) and not anc(i, x) and not anc(x, i) and x != i]
        if others:
            o = r.choice(others)
            return [["reclass", f, i, "--mat", "3"],
                    ["add", f, i, "--q", f"Linked {tag}?", "--gen", "court", "--mat", "1"],
                    ["@dup-last-to", f, i, o],
                    ["answer", f, i, "--type", "fact", "--a", f"Changed {tag}", "--effect", N[i]["effect"] or "supports", "--grounds", "B/73"],
                    ["render", f], ["approve", f]]
    if pick < .92:      # an unsourced peripheral answer placed in the plan
        return [["add", f, "Q0", "--q", f"Aside {tag}?", "--gen", "court", "--mat", "1"],
                ["@answer-last-unsourced", f, "Q0"], ["@place-last", f, "Q0"], ["render", f], ["approve", f]]
    return [["add", f, "Q0", "--q", f"Peripheral {tag}?", "--gen", "self", "--mat", "1"],   # critical duplicate lifts an answered peripheral
            ["@answer-last", f, "Q0", "fact"],
            ["add", f, "Q0", "--q", f"Critical twin {tag}?", "--gen", "opp", "--mat", "3"],
            ["@dup-last-two", f, "Q0"], ["render", f], ["approve", f]]


import random as _rnd
r_choice = _rnd.Random(5).choice

def resolve_macro(argv, t):
    """Expand '@' steps against the live tree (children ids are only known at run time)."""
    if not argv[0].startswith("@"): return argv
    N = t["nodes"]; m, f, i = argv[0], argv[1], argv[2]
    kids = sorted(N[i]["children"], key=k) if i in N else []
    if not kids: return ["status", f, i]
    last = kids[-1]
    if m == "@answer-last": return ["answer", f, last, "--type", "fact", "--a", f"Ans {last}", "--effect", "neutral", "--grounds", "B/3"]
    if m == "@add-under-last": return ["add", f, last, "--q", argv[3], "--gen", "opp", "--mat", argv[4]]
    if m == "@close-last":
        return ["close", f, last, argv[3], "--reason", "scope: old premise"]
    if m == "@close-last-last":
        g = sorted(N[last]["children"], key=k)
        return ["close", f, g[-1], argv[3], "--reason", "[VERIFY] source"] if g else ["status", f, last]
    if m == "@answer-last-unsourced":
        return ["answer", f, last, "--type", "fact", "--a", r_choice(["[VERIFY] invented", "Unsupported aside"]), "--effect", "neutral"]
    if m == "@place-last": return ["place", f, last, "--section", "G1"]
    if m == "@dup-last-to": return ["close", f, last, "DUPLICATE", "--of", argv[3]]
    if m == "@dup-last-two":
        if len(kids) < 2: return ["status", f, i]
        return ["close", f, kids[-1], "DUPLICATE", "--of", kids[-2]]
    return ["status", f, i]

def main():
    runs, steps, seed = (int(x) for x in (sys.argv[1:4] + ["200", "60", "1"][len(sys.argv[1:4]):]))
    found = {}; ops = 0
    for run in range(runs):
        r = random.Random(seed * 100000 + run); d = tempfile.mkdtemp()
        _, out, _ = call(["init", d, "--root", r.choice(["P", "Allow the appeal"]), "--doc", "f",
                          "--depth", str(r.choice([1, 2, 3, 5])), "--threshold", str(r.choice([1, 2, 3]))])
        f = out.strip(); hist = []
        queue = []
        for _ in range(steps):
            prev = json.load(open(f))
            if not queue and r.random() < GUIDE:
                roll = r.random()
                queue = (chain_ops(r, f, prev) if roll < .2 else perturb_ops(r, f, prev) if roll < .45
                         else complete_ops(r, f, prev)[:8])
                if queue and queue[0][0] == "add" and queue[0][3].startswith("Same as") and r.random() < .7:
                    pass
            argv = resolve_macro(queue.pop(0), prev) if queue else rnd_op(r, f, prev)
            if argv[0] == "tamper":
                if tamper(f, r): TAMPERED.add(f)
                hist.append(argv); continue
            code, o, e = call(argv); ops += 1; hist.append(argv)
            if code == "CRASH":
                found.setdefault("crash " + argv[0] + " " + e.strip().splitlines()[-1][:60], (run, list(hist), e.strip().splitlines()[-1])); break
            STATS[argv[0], code] += 1
            if argv[0] == "render" and code == 0: TAMPERED.discard(f)
            for x in invariants(f, prev, argv, code):
                key = re.sub(r"Q[\d.]+", "Q#", x)
                found.setdefault(key, (run, list(hist), x))
    for key, (run, h, x) in found.items():
        print(f"== {x}  (run {run}, step {len(h)})")
        for a in h[-5:]:
            print("   ", " ".join(a[:1] + a[2:])[:170])
    print("coverage: check closed(0/2) =", STATS["check", 0] + STATS["check", 2], "· check refused =", STATS["check", 1],
          "· ready passed =", STATS["ready", 0], "· approve ok =", STATS["approve", 0], "· confirm ok =", STATS["confirm", 0])
    print(f"{runs} runs, {ops} ops: {len(found)} distinct failure class(es)")
    thin = steps < 10 or STATS["ready", 0] < max(1, runs // 2) or STATS["check", 0] + STATS["check", 2] < max(1, runs // 2)
    if thin:
        print(f"INSUFFICIENT COVERAGE: need ≥{runs} closed and ≥{runs} ready states; this run proves nothing")
    sys.exit(1 if found else (3 if thin else 0))

main()
