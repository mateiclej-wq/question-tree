#!/usr/bin/env python3
"""qtree v1.0.0 (internal v4.9) — question-tree store for question-driven drafting (/question-tree).

Tree: proposition (Q0) -> questions -> answers -> follow-up questions -> ...
Each node = one question + its answer (Toulmin slots). Children = follow-up
questions the ANSWER provokes (a parent must be ANSWERED to take children).

STATE MODEL (v4). Each node stores only its own `decision` and a `stale` flag.
  decision ∈ OPEN ANSWERED CONCEDED OUT_OF_SCOPE IMMATERIAL DUPLICATE BLOCKED DEFERRED
  stale    = the decision rests on a premise that has since changed; it must be confirmed or redone
  PRUNED   is never stored: a node is pruned while any ancestor's decision is
           CONCEDED / OUT_OF_SCOPE / IMMATERIAL / DUPLICATE.
Displayed status = PRUNED if pruned, else STALE if stale, else decision.
Any change to a node's decision or substance marks every decided descendant stale.

  init     <prep_dir> --root "<proposition>" --doc <slug> [--mode draft|tutor] [--threshold 2] [--depth 5]
           [--budget-min 120] [--max-nodes 60]
  add      <file> <parent> --q "<question>" --gen paul:assumptions [--mat 1-3] [--force]   (idempotent)
  add-many <file> <parent> --json '[{"q":"..","gen":"..","mat":2}, ...]'                   (atomic)
  answer   <file> <id> --type fact|law|mixed --a ".." --effect supports|undermines|neutral
           [--grounds ..] [--warrant ..] [--qualifier ..] [--rebuttal ..]   (replaces every slot)
  close    <file> <id> CONCEDED --concession ".." | OUT_OF_SCOPE|IMMATERIAL --reason ..
           | DUPLICATE --of <id> | BLOCKED --reason "[VERIFY] .." | DEFERRED --reason "budget: .."
  reopen   <file> <id>        undo a closure (or flag an answer) for re-review
  confirm  <file> <id>        clear STALE: the node's own decision stands unchanged after re-review
  place    <file> <id> --section "<heading>" [--order N]   |   unplace <file> <id>
  reclass  <file> <id> [--mat 1-3] [--gen ..]   change a question's materiality / generator
  render   <file>             writes <stem>.md (tree, document plan, reserve, closure)
  approve  <file>             binds approval to the render on disk; render first
  open     <file> [--json]    material OPEN/STALE work, breadth-first, most material first
  show     <file> <id>        |   status <file> <id>   (derived status)
  check    <file>   exit 0 closed | 2 closed within budget, residue listed | 1 not closed
  ready    <file>   exit 0 only if check exits 0/2, the approved render is current and unaltered,
                    and every material answer is placed
check is STRUCTURAL validation. It cannot tell whether an answer is right; the reviewer's review does that.
"""
import argparse, contextlib, datetime, fcntl, hashlib, json, os, re, sys, tempfile

DECISIONS = {"OPEN", "ANSWERED", "CONCEDED", "OUT_OF_SCOPE", "IMMATERIAL", "DUPLICATE", "BLOCKED", "DEFERRED"}
PRUNING = {"CONCEDED", "OUT_OF_SCOPE", "IMMATERIAL", "DUPLICATE"}
GENS = {"paul": ["clarification", "assumptions", "evidence", "viewpoints", "implications", "question"],
        "walton": ["precedent", "analogy", "expert", "statute", "evidence-inference", "consequences", "sign"],
        "opp": [], "court": [], "client": [], "self": []}
SLOTS = ("a", "grounds", "warrant", "qualifier", "rebuttal")
VERIFY = re.compile(r"\[\s*verify", re.I)
MARK = "<!-- qtree-review-sha256: "


# ---------------- storage ----------------
@contextlib.contextmanager
def txn(f, write=True):
    real = os.path.realpath(f)                       # one lock per real file, whatever path or symlink is used
    try:
        lock = open(real + ".lock", "a+")
    except OSError as e:
        die(f"cannot open lock beside the tree ({e.strerror}): check folder permissions")
    fcntl.flock(lock, fcntl.LOCK_EX if write else fcntl.LOCK_SH)
    try:
        try:
            with open(real) as h:
                raw = h.read()
            t = json.loads(raw)
        except ValueError:
            die(f"tree file is not valid JSON: {real} (restore it from the .json history or start a new tree)")
        if not isinstance(t, dict) or seal_of(t) is None or t.get("seal") != seal_of(t):
            die("tree file was changed outside qtree (integrity seal does not match): undo the edit, "
                "or start a new tree — change a tree only through qtree commands")
        problem = schema_problem(t)
        if problem:
            die(f"tree file failed validation ({problem}): restore it or start a new tree")
        before = json.dumps({k: v for k, v in t.items() if k != "seal"}, sort_keys=True)
        yield t
        if write and json.dumps({k: v for k, v in t.items() if k not in ("_keep_approval", "seal")}, sort_keys=True) == before:
            write = False                                   # nothing changed: no new revision, approval kept
        if write:
            keep = t.pop("_keep_approval", False)
            t["rev"] += 1
            t["updated"] = now()
            if not keep:
                t["approved_rev"] = None
                t["approved_hash"] = None
            problem = schema_problem(t)
            if problem:
                die(f"this operation would leave the tree invalid ({problem}); nothing was saved")
            try:
                atomic_write(real, sealed_json(t))
            except OSError as e:
                die(f"save failed ({e.strerror}); the tree on disk is unchanged")
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


NODE_KEYS = {"q": str, "gen": str, "mat": int, "decision": str, "stale": bool, "type": str, "effect": str,
             "a": str, "grounds": str, "warrant": str, "qualifier": str, "rebuttal": str, "reason": str,
             "concession": str, "dup_of": str, "section": str, "order": int, "history": list, "children": list}
TOP_KEYS = {"version": int, "doc": str, "mode": str, "threshold": int, "depth_cap": int, "budget_min": int,
            "max_nodes": int, "created": str, "started": str, "rev": int, "nodes": dict}


def seal_of(t):
    body = {k: v for k, v in t.items() if k != "seal"}
    try:
        return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    except (UnicodeEncodeError, TypeError, ValueError):
        return None                                        # unencodable content can never match a seal


def sealed_json(t):
    t["seal"] = seal_of(t)
    return json.dumps(t, indent=1, ensure_ascii=False)


def schema_problem(t):
    if not isinstance(t, dict):
        return "top level is not an object"
    for k, ty in TOP_KEYS.items():
        if not isinstance(t.get(k), ty) or isinstance(t.get(k), bool) and ty is int:
            return f"missing or bad field {k}"
    if t["version"] != 4:
        return f"format v{t['version']} is not v4"
    if not (1 <= t["threshold"] <= 3 and 1 <= t["depth_cap"] <= 8) or "Q0" not in t["nodes"]:
        return "bad threshold/depth or no root"
    for i, n in t["nodes"].items():
        if not re.fullmatch(r"Q0|Q\d+(\.\d+)*", i) or not isinstance(n, dict):
            return f"bad node id {i!r}"
        for k, ty in NODE_KEYS.items():
            v = n.get(k)
            if not isinstance(v, ty) or (ty is int and isinstance(v, bool)):
                return f"{i}: missing or bad field {k}"
        fam, _, sub = n["gen"].partition(":")
        if fam not in GENS or (GENS[fam] and sub not in GENS[fam]) or (not GENS[fam] and sub):
            return f"{i}: bad generator {n['gen']!r}"
        if t["mode"] not in ("draft", "tutor") or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", t["doc"]) \
                or not re.fullmatch(r"\d\d\.\d\d\.\d{4}", t["created"]):
            return "bad mode, doc slug or created date"
        if n["decision"] not in DECISIONS or n["mat"] not in (1, 2, 3):
            return f"{i}: bad decision or materiality"
        if n["type"] not in ("", "fact", "law", "mixed") or n["effect"] not in ("", "supports", "undermines", "neutral"):
            return f"{i}: bad type or effect"
        if i != "Q0" and n["decision"] == "ANSWERED" and (n["type"] == "" or n["effect"] == ""):
            return f"{i}: answered without a type and effect"
        if i == "Q0" and (n["decision"] != "ANSWERED" or n["stale"] or n["effect"] != "supports" or not n["a"].strip()):
            return "root must be a current, non-blank ANSWERED proposition that supports itself"
        if n["decision"] in ("OUT_OF_SCOPE", "IMMATERIAL", "BLOCKED", "DEFERRED") and not n["reason"].strip():
            return f"{i}: {n['decision']} without a reason"
        if n["decision"] == "CONCEDED" and not n["concession"].strip():
            return f"{i}: CONCEDED without concession text"
        for c in n["children"]:
            if not isinstance(c, str) or c not in t["nodes"] or \
                    c != (f"Q{c[1:].split('.')[-1]}" if i == "Q0" else f"{i}.{c.split('.')[-1]}"):
                return f"{i}: bad child {c!r}"
        if len(set(n["children"])) != len(n["children"]):
            return f"{i}: repeated child"
        if n["decision"] == "DUPLICATE" and n["dup_of"] not in t["nodes"]:
            return f"{i}: duplicate of a missing node"
        for h in n["history"]:
            if not isinstance(h, dict) or any(not isinstance(h.get(k, ""), str) for k in SLOTS + ("type", "effect", "decision", "concession", "reason")):
                return f"{i}: bad history entry"
    # every node reachable from Q0 exactly once (ids encode the parent, so this also rules out cycles)
    seen, stack = set(), ["Q0"]
    while stack:
        x = stack.pop()
        if x in seen:
            return f"{x} reached twice"
        seen.add(x)
        stack.extend(t["nodes"][x]["children"])
    if seen != set(t["nodes"]):
        return f"orphaned node(s) {sorted(set(t['nodes']) - seen)[:5]}"
    try:
        datetime.datetime.strptime(t["created"], "%d.%m.%Y")
    except ValueError:
        return "created is not a real calendar date"
    try:
        if datetime.datetime.fromisoformat(t["started"]).tzinfo is not None:
            return "started timestamp must be local time without a timezone"
    except ValueError:
        return "bad started timestamp"
    return None


def atomic_write(path, text):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".qtree-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as h:
            h.write(text.encode("utf-8"))
            h.flush()
            os.fsync(h.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise


def now():
    return datetime.datetime.now().isoformat(timespec="minutes")


def die(msg, code=1):
    print("✗", msg, file=sys.stderr)
    sys.exit(code)


def blank(s):
    return not (s or "").strip()


# ---------------- tree helpers ----------------
def key(i):
    return tuple(int(x) for x in i[1:].split(".")) if i != "Q0" else ()


def depth(i):
    return len(key(i))


def node(t, i):
    if i not in t["nodes"]:
        die(f"no node {i}")
    return t["nodes"][i]


def walk(t, i="Q0"):
    yield i
    for c in sorted(t["nodes"][i]["children"], key=key):
        yield from walk(t, c)


def descendants(t, i):
    return [d for d in walk(t, i) if d != i]


def is_ancestor(a, d):
    return d != a and (a == "Q0" or d.startswith(a + "."))


def ancestors(t, i):
    return [a for a in t["nodes"] if is_ancestor(a, i)]


def pruned(t, i):
    return any(t["nodes"][a]["decision"] in PRUNING for a in ancestors(t, i))


def status(t, i):
    n = t["nodes"][i]
    return "PRUNED" if pruned(t, i) else ("STALE" if n["stale"] else n["decision"])


def live(t, i):
    return not pruned(t, i)


def canonical(t, i):
    """Follow DUPLICATE links; returns None on a cycle or a missing target."""
    seen = set()
    while t["nodes"][i]["decision"] == "DUPLICATE":
        if i in seen:
            return None
        seen.add(i)
        i = t["nodes"][i]["dup_of"]
        if i not in t["nodes"]:
            return None
    return i


def chain(t, i):
    """Nodes on the duplicate path from i to its canonical node, inclusive; None if broken."""
    path, seen = [i], set()
    while t["nodes"][i]["decision"] == "DUPLICATE":
        if i in seen or t["nodes"][i]["dup_of"] not in t["nodes"]:
            return None
        seen.add(i)
        i = t["nodes"][i]["dup_of"]
        path.append(i)
    return path


def dup_valid(t, i):
    """A live, current duplicate whose target is still a sound answer or concession outside its lineage."""
    n = t["nodes"][i]
    return (n["decision"] == "DUPLICATE" and live(t, i) and not n["stale"]
            and check_duplicate(t, i, n["dup_of"]) is None)


def resolves_soundly(t, i, exclude=None):
    """The node that answers i: i itself if sound, or its duplicate target if the duplicate is valid."""
    n = t["nodes"][i]
    if n["decision"] == "DUPLICATE":
        if not dup_valid(t, i):
            return None
        c = n["dup_of"]
    else:
        c = i if sound(t, i) else None
    return c


def eff_mat(t, i):
    m = t["nodes"][i]["mat"]
    for j, o in t["nodes"].items():
        if j != i and o["decision"] == "DUPLICATE" and live(t, j) and canonical(t, j) == i:
            m = max(m, o["mat"])
    return m


def material(t, i):
    return eff_mat(t, i) >= t["threshold"]


def new_node(q, gen, mat):
    return {"q": q, "gen": gen, "mat": mat, "decision": "OPEN", "stale": False, "type": "", "effect": "",
            "a": "", "grounds": "", "warrant": "", "qualifier": "", "rebuttal": "",
            "reason": "", "concession": "", "dup_of": "", "section": "", "order": 0, "history": [], "children": []}


def defects(n):
    """Support defects of a node's current decision (ANSWERED or CONCEDED)."""
    bad = []
    if n["decision"] == "CONCEDED":
        if blank(n["concession"]):
            bad.append("concession has no text")
        if VERIFY.search(n["concession"]):
            bad.append("concession carries an unresolved [VERIFY]")
        return bad
    for k in SLOTS:
        if VERIFY.search(n[k] or ""):
            bad.append(f"{k} carries an unresolved [VERIFY]")
    if blank(n["a"]):
        bad.append("no answer text")
    if n["type"] in ("fact", "mixed") and blank(n["grounds"]):
        bad.append("factual answer lacks grounds (fact + location)")
    if n["type"] in ("law", "mixed") and blank(n["warrant"]):
        bad.append("legal answer lacks a warrant (authority + pinpoint)")
    return bad


def sound(t, i):
    """A live, non-stale ANSWERED or CONCEDED node with no support defects."""
    n = t["nodes"][i]
    return live(t, i) and not n["stale"] and n["decision"] in ("ANSWERED", "CONCEDED") and not defects(n)


def substance(n):
    return (n["decision"],) + tuple((n[k] or "").strip() for k in SLOTS) + (
        n["type"], n["effect"], n["concession"].strip(), n["dup_of"], n["reason"].strip())


def invalidate(t, i):
    """Mark every decided descendant stale, and every duplicate that relies on i; returns the list."""
    out = []
    for j, o in t["nodes"].items():
        if o["decision"] == "DUPLICATE" and o["dup_of"] == i and not o["stale"]:
            o["stale"] = True
            out.append(j)
    for d in descendants(t, i):
        dn = t["nodes"][d]
        if dn["decision"] != "OPEN" and not dn["stale"]:
            dn["stale"] = True
            out.append(d)
    return out


def check_duplicate(t, i, target):
    """A duplicate means 'answered at <target>': the target must be a current, sound answer or concession
    outside this question's lineage. No chains: a duplicate never points at another duplicate."""
    if not target or target not in t["nodes"] or target == i:
        return "--of must name another existing question"
    if is_ancestor(i, target) or is_ancestor(target, i):
        return f"{target} is in this question's own lineage: a question cannot be answered by itself or its premise"
    if depth(target) > depth(i):
        return (f"{target} sits deeper (depth {depth(target)}) than this question (depth {depth(i)}): "
                f"answer it here, or point at a question no deeper than this one")
    if t["nodes"][target]["decision"] == "DUPLICATE":
        return f"{target} is itself a duplicate of {t['nodes'][target]['dup_of']}: point at that question directly"
    if not sound(t, target):
        return f"{target} is {status(t, target)}, not a current sound answer or concession: answer it first, or answer this question"
    return None


def esc(s):
    """User text is rendered inline, on one line, with HTML and code-span syntax neutralised,
    so it cannot forge headings, sections or the review marker."""
    s = " ⏎ ".join((s or "").splitlines())
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("`", "&#96;")
    return re.sub(r"([\\\[\]*_~|#])", r"\\\1", s)       # Markdown syntax is shown literally, never interpreted


# ---------------- commands ----------------
def cmd_init(a):
    if not 1 <= a.threshold <= 3:
        die("--threshold must be 1..3")
    if not 1 <= a.depth <= 8:
        die("--depth must be 1..8")
    if a.budget_min < 0 or a.max_nodes < 1:
        die("--budget-min must be ≥0 and --max-nodes ≥1")
    if blank(a.root) or VERIFY.search(a.root):
        die("--root must state the proposition (no [VERIFY])")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", a.doc):
        die("--doc must be a short slug, e.g. skeleton-reply")
    os.makedirs(a.prep, exist_ok=True)
    stamp = datetime.date.today().strftime("%d.%m.%Y")
    f = os.path.join(a.prep, f"QTree {a.doc} {stamp}.json")
    root = new_node("What is the proposition?", "self", 3)
    root.update(decision="ANSWERED", type="", effect="supports", a=a.root.strip())
    t = {"version": 4, "doc": a.doc, "mode": a.mode, "threshold": a.threshold, "depth_cap": a.depth,
         "budget_min": a.budget_min, "max_nodes": a.max_nodes, "created": stamp, "started": now(),
         "rev": 0, "approved_rev": None, "approved_hash": None, "nodes": {"Q0": root}}
    if os.path.exists(f):
        die(f"exists: {f} (use another --doc slug or continue that tree)")
    fd, tmp = tempfile.mkstemp(dir=a.prep, prefix=".qtree-", suffix=".init")
    try:
        with os.fdopen(fd, "w") as h:
            h.write(sealed_json(t))
            h.flush()
            os.fsync(h.fileno())
        os.link(tmp, f)                                     # atomic, refuses to overwrite
    except FileExistsError:
        die(f"exists: {f} (use another --doc slug or continue that tree)")
    except OSError as e:
        die(f"could not create the tree ({e.strerror}); nothing was written")
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
    print(f)


def _add(t, parent, q, gen, mat, force=False):
    p = node(t, parent)
    if status(t, parent) != "ANSWERED":
        die(f"{parent} is {status(t, parent)}: follow-up questions hang off a current ANSWERED node")
    if blank(q):
        die("empty question")
    fam, _, sub = gen.partition(":")
    if fam not in GENS or (GENS[fam] and sub not in GENS[fam]) or (not GENS[fam] and sub):
        die(f"bad --gen {gen}; families: " + ", ".join(f"{k}:{'|'.join(v)}" if v else k for k, v in GENS.items()))
    if isinstance(mat, bool) or mat not in (1, 2, 3):
        die("--mat must be 1..3")
    norm = " ".join(q.lower().split())
    for c in p["children"]:
        if " ".join(t["nodes"][c]["q"].lower().split()) == norm:
            o = t["nodes"][c]
            if o["mat"] != mat or o["gen"] != gen:
                die(f"{c} already asks this as {o['gen']} m{o['mat']}; you asked {gen} m{mat}. "
                    f"Use: reclass <file> {c} --mat {mat} --gen {gen}")
            return c, False
    if len(t["nodes"]) - 1 >= t["max_nodes"] and not force:
        die(f"node budget {t['max_nodes']} reached: close or merge questions; --force records an overrun in the residue")
    k = max([key(c)[-1] for c in p["children"]], default=0) + 1
    i = f"Q{k}" if parent == "Q0" else f"{parent}.{k}"
    while i in t["nodes"]:                                   # never overwrite an existing record
        k += 1
        i = f"Q{k}" if parent == "Q0" else f"{parent}.{k}"
    t["nodes"][i] = new_node(q.strip(), gen, mat)
    p["children"].append(i)
    return i, True


def cmd_add(a):
    with txn(a.file) as t:
        i, created = _add(t, a.parent, a.q, a.gen, a.mat, a.force)
        cap = depth(i) > t["depth_cap"]
    print(i if created else f"{i} (exists)", "· beyond depth cap: will be listed as residue" if cap else "")


def cmd_add_many(a):
    try:
        items = json.loads(a.json)
    except ValueError:
        die("--json is not valid JSON")
    if not isinstance(items, list):
        die("--json must be a JSON list of {q, gen, mat}")
    for k, it in enumerate(items):
        if not isinstance(it, dict) or set(it) - {"q", "gen", "mat"}:
            die(f"item {k}: must be an object with keys q, gen, mat")
        if not isinstance(it.get("q"), str) or not isinstance(it.get("gen"), str):
            die(f"item {k}: q and gen must be strings")
        m = it.get("mat", 2)
        if isinstance(m, bool) or not isinstance(m, int) or not 1 <= m <= 3:
            die(f"item {k}: mat must be an integer 1..3")
    with txn(a.file) as t:
        out = [_add(t, a.parent, it["q"], it["gen"], it.get("mat", 2), a.force) for it in items]
    for i, c in out:
        print(i if c else f"{i} (exists)")


def cmd_answer(a):
    if blank(a.a):
        die("--a must state the answer as a proposition")
    with txn(a.file) as t:
        n = node(t, a.id)
        if pruned(t, a.id):
            die(f"{a.id} is pruned (an ancestor is closed): reopen the ancestor first")
        before = substance(n)
        had_decision = n["decision"] != "OPEN"
        proposed = ("ANSWERED",) + tuple((getattr(a, k) or "").strip() for k in SLOTS) + (
            a.type if a.id != "Q0" else "", a.effect, "", "", "")
        if not n["stale"] and before == proposed:
            print(a.id, "ANSWERED (unchanged)")
            return
        if n["a"] or n["decision"] != "OPEN":
            n["history"].append({k: n[k] for k in SLOTS + ("type", "effect", "decision", "concession", "reason")} | {"at": now()})
        for k in SLOTS:
            n[k] = (getattr(a, k) or "").strip()
        if a.id == "Q0":
            if a.effect != "supports":
                die("the root is the proposition itself: --effect must be supports")
            if any(VERIFY.search(getattr(a, k) or "") for k in SLOTS):
                die("the root cannot carry [VERIFY]")
        n.update(decision="ANSWERED", stale=False, type=a.type if a.id != "Q0" else "",
                 effect=a.effect, reason="", concession="", dup_of="")
        stale = invalidate(t, a.id) if (had_decision and substance(n) != before) else []
        d = defects(n) if a.id != "Q0" else []          # the root's support is its first ring, not its own slots
    print(a.id, "ANSWERED", *(f"· {x}" for x in d))
    if stale:
        print(f"· premise changed: {len(stale)} decided follow-up(s) now STALE — confirm or redo: {', '.join(stale[:10])}")


def cmd_close(a):
    st = a.status
    with txn(a.file) as t:
        n = node(t, a.id)
        if a.id == "Q0":
            die("the root cannot be closed; change it with answer Q0 or revisit the strategy card")
        if pruned(t, a.id):
            die(f"{a.id} is pruned: reopen its closed ancestor first")
        if st == "CONCEDED" and (blank(a.concession) or VERIFY.search(a.concession)):
            die("CONCEDED needs --concession: the exact proposition conceded, as drafted (no [VERIFY])")
        if st in ("OUT_OF_SCOPE", "IMMATERIAL", "BLOCKED", "DEFERRED") and blank(a.reason):
            die(f"{st} needs --reason")
        if st == "DEFERRED" and material(t, a.id) and "budget" not in a.reason.lower() and not a.force:
            die("a MATERIAL question can be DEFERRED only for budget/urgency (say so in --reason) or with --force")
        if st == "DUPLICATE":
            err = check_duplicate(t, a.id, a.of)
            if err:
                die("DUPLICATE: " + err)
        before = substance(n)
        had_decision = n["decision"] != "OPEN"
        same = (n["decision"] == st and not n["stale"] and
                ((st == "CONCEDED" and n["concession"] == (a.concession or "").strip()) or
                 (st == "DUPLICATE" and n["dup_of"] == a.of) or
                 (st not in ("CONCEDED", "DUPLICATE") and n["reason"] == (a.reason or "").strip())))
        if same:
            print(a.id, st, "(unchanged)")
            return
        if n["a"] or n["decision"] != "OPEN":
            n["history"].append({k: n[k] for k in SLOTS + ("type", "effect", "decision", "concession", "reason")} | {"at": now()})
        if st == "CONCEDED":                              # the abandoned answer is archived, never exported
            for k in SLOTS:
                n[k] = ""
            n["type"] = n["effect"] = ""
        n.update(decision=st, stale=False, reason=(a.reason or "").strip() if st != "CONCEDED" else "",
                 concession=(a.concession or "").strip() if st == "CONCEDED" else "",
                 dup_of=a.of if st == "DUPLICATE" else "")
        stale = invalidate(t, a.id) if (had_decision and substance(n) != before) else []
        np = sum(1 for d in descendants(t, a.id)) if st in PRUNING else 0
    print(a.id, st, f"· {np} descendant(s) pruned while closed" if np else "",
          f"· {len(stale)} decided follow-up(s) now STALE" if stale else "")


def cmd_reopen(a):
    with txn(a.file) as t:
        n = node(t, a.id)
        if a.id == "Q0":
            die("the root is changed with answer Q0")
        if pruned(t, a.id):
            die(f"{a.id} is pruned: reopen the closed ancestor instead")
        if n["decision"] == "OPEN":
            die(f"{a.id} is already OPEN")
        if n["decision"] == "ANSWERED" and n["stale"]:
            die(f"{a.id} is already STALE (awaiting review): confirm it or answer it")
        n["history"].append({k: n[k] for k in SLOTS + ("type", "effect", "decision", "concession", "reason")} | {"at": now()})
        if n["decision"] == "ANSWERED":
            n["stale"] = True                             # flag the answer for re-review
        elif n["a"] and n["type"] in ("fact", "law", "mixed") and n["effect"] in ("supports", "undermines", "neutral") \
                and n["decision"] in ("BLOCKED", "DEFERRED", "OUT_OF_SCOPE", "IMMATERIAL", "DUPLICATE"):
            n.update(decision="ANSWERED", stale=True, reason="", dup_of="")   # earlier answer back, for review
        elif blank(n["a"]) and any(h.get("a") and h.get("type") in ("fact", "law", "mixed")
                                   and h.get("effect") in ("supports", "undermines", "neutral") for h in n["history"][:-1]):
            h = [h for h in n["history"][:-1] if h.get("a") and h.get("type") in ("fact", "law", "mixed")
                 and h.get("effect") in ("supports", "undermines", "neutral")][-1]   # most recent restorable answer
            for k in SLOTS:
                n[k] = h.get(k, "")
            n.update(decision="ANSWERED", stale=True, type=h.get("type", ""), effect=h.get("effect", ""),
                     reason="", concession="", dup_of="")
        else:
            n.update(decision="OPEN", stale=False, reason="", concession="", dup_of="")
        stale = invalidate(t, a.id)
        st = status(t, a.id)
    print(a.id, st, f"· {len(stale)} decided follow-up(s) now STALE" if stale else "")


def cmd_confirm(a):
    with txn(a.file) as t:
        n = node(t, a.id)
        if pruned(t, a.id):
            die(f"{a.id} is pruned: reopen the closed ancestor first")
        if not n["stale"]:
            die(f"{a.id} is {status(t, a.id)}, not STALE")
        if n["decision"] == "DUPLICATE":
            err = check_duplicate(t, a.id, n["dup_of"])
            if err:
                die(f"cannot confirm DUPLICATE: {err} — close it afresh or answer it")
        if n["decision"] == "ANSWERED" and blank(n["a"]):
            die(f"{a.id} has no answer on file: answer it")
        n["stale"] = False
        d = n["decision"]
    print(a.id, "confirmed:", d)


def cmd_reclass(a):
    with txn(a.file) as t:
        if a.id == "Q0":
            die("the root's materiality is fixed")
        n = node(t, a.id)
        if a.mat is not None:
            if a.mat not in (1, 2, 3):
                die("--mat must be 1..3")
            n["mat"] = a.mat
        if a.gen is not None:
            fam, _, sub = a.gen.partition(":")
            if fam not in GENS or (GENS[fam] and sub not in GENS[fam]) or (not GENS[fam] and sub):
                die(f"bad --gen {a.gen}")
            n["gen"] = a.gen
        m, g = n["mat"], n["gen"]
    print(a.id, f"{g} m{m}")


def cmd_place(a):
    with txn(a.file) as t:
        if a.id == "Q0":
            die("the root is always rendered first as the Conclusion; it is not placed")
        node(t, a.id)
        if status(t, a.id) not in ("ANSWERED", "CONCEDED"):
            die(f"{a.id} is {status(t, a.id)}: only current ANSWERED or CONCEDED nodes go into the document plan")
        if blank(a.section):
            die("--section must name the heading")
        t["nodes"][a.id]["section"], t["nodes"][a.id]["order"] = " ".join(a.section.split()), a.order
    print(a.id, "→", a.section)


def cmd_unplace(a):
    with txn(a.file) as t:
        n = node(t, a.id)
        if not n["section"]:
            die(f"{a.id} is not placed")
        n["section"], n["order"] = "", 0
    print(a.id, "unplaced")


def work_queue(t):
    out = [i for i in walk(t) if status(t, i) in ("OPEN", "STALE") and material(t, i) and depth(i) <= t["depth_cap"]]
    return sorted(out, key=lambda x: (depth(x), -eff_mat(t, x), key(x)))


def cmd_open(a):
    with txn(a.file, write=False) as t:
        q = work_queue(t)
        rows = [{"id": i, "q": t["nodes"][i]["q"], "gen": t["nodes"][i]["gen"], "mat": eff_mat(t, i),
                 "mat_own": t["nodes"][i]["mat"], "status": status(t, i)} for i in q]
    if a.json:
        print(json.dumps(rows, ensure_ascii=False))
    else:
        for r in rows:
            m = f"m{r['mat']}" + (f" (own m{r['mat_own']}, lifted by duplicate)" if r["mat"] != r["mat_own"] else "")
            print(f"{r['id']}  [{r['status']} {m} {r['gen']}]  {esc(r['q'])}")


def cmd_status(a):
    with txn(a.file, write=False) as t:
        node(t, a.id)
        print(status(t, a.id))


def cmd_show(a):
    with txn(a.file, write=False) as t:
        node(t, a.id)
        for p in [p for p in walk(t) if p == a.id or is_ancestor(p, a.id)]:
            n = t["nodes"][p]
            print(f"{'  ' * depth(p)}{p} [{status(t, p)}] Q: {esc(n['q'])}  A: {esc(n['a']) or '—'}")
        n = dict(t["nodes"][a.id])
        n.pop("history")
        n["status"], n["eff_mat"] = status(t, a.id), eff_mat(t, a.id)
        print(json.dumps(n, indent=1, ensure_ascii=False))


def assess(t, timed=True):
    """-> (failures, residue). timed=False omits the clock-dependent budget line (for the render)."""
    F, R = [], []
    N = t["nodes"]
    root = N["Q0"]
    if blank(root["a"]) or any(VERIFY.search(root[k] or "") for k in SLOTS):
        F.append("Q0: root is blank or carries [VERIFY]")
    first = [c for c in root["children"] if live(t, c)]
    if not first:
        F.append("root has no questions")
    q = work_queue(t)
    if q:
        F.append(f"{len(q)} material OPEN/STALE question(s): {', '.join(q[:12])}")
    supports = False
    for i in walk(t):
        if i == "Q0" or pruned(t, i):
            continue
        n, st, mat, d, em = N[i], status(t, i), material(t, i), depth(i), eff_mat(t, i)
        placed = bool(n["section"]) and st in ("ANSWERED", "CONCEDED")
        if st in ("ANSWERED", "CONCEDED"):
            for x in defects(n):
                (F if (mat or placed) else R).append(f"{i}: {x}" + (" (placed in the plan)" if placed and not mat else ""))
        if st == "ANSWERED":
            if n["effect"] == "undermines" and (blank(n["rebuttal"]) or VERIFY.search(n["rebuttal"])):
                (F if (mat or placed) else R).append(f"{i}: answer UNDERMINES the proposition and is unmet (no verified rebuttal) — "
                                         f"rebut it, concede it, or take it back to the strategy card")
            if em == 3:
                ok = [c for c in n["children"] if live(t, c) and resolves_soundly(t, c, exclude=i)]
                if not ok:
                    if d >= t["depth_cap"]:
                        R.append(f"{i}: critical answer at depth cap, not interrogated (budget)")
                    else:
                        F.append(f"{i}: critical answer not interrogated — needs ≥1 follow-up resolving to a sound "
                                 f"answer or concession (BLOCKED, closed, stale or self-referring ones do not count)")
        if d == 1 and live(t, i):
            c = resolves_soundly(t, i)
            if c and N[c]["decision"] == "ANSWERED" and N[c]["effect"] == "supports":
                supports = True
        if st == "BLOCKED":
            (F if mat else R).append(f"{i}: BLOCKED — {esc(n['reason'])}")
        if st == "DEFERRED":
            R.append(f"{i}: DEFERRED{' (MATERIAL)' if mat else ''} — {esc(n['reason'])}")
        if st in ("OPEN", "STALE") and (not mat or d > t["depth_cap"]):
            R.append(f"{i}: {st.lower()} {'beyond depth cap' if d > t['depth_cap'] else 'below threshold'} — {esc(n['q'])}")
        bad_dup = n["decision"] == "DUPLICATE" and not n["stale"] and check_duplicate(t, i, n["dup_of"]) is not None
        if n["decision"] in PRUNING and (n["stale"] or bad_dup):
            hidden = [x for x in descendants(t, i) if material(t, x)]
            if hidden or (mat and d > t["depth_cap"]):
                F.append(f"{i}: {'STALE' if n['stale'] else 'BROKEN'} {n['decision']} still hides material question(s) "
                         f"{', '.join(hidden[:6])} — confirm, re-close or reopen it")
        if n["decision"] == "DUPLICATE" and not n["stale"]:
            err = check_duplicate(t, i, n["dup_of"])
            if err:
                (F if mat else R).append(f"{i}: duplicate no longer answered — {err}")
    if first and not supports:
        F.append("no first-ring question resolves to a sound answer that SUPPORTS the proposition: the root is unsupported")
    count = len(N) - 1
    if count > t["max_nodes"]:
        R.append(f"node budget exceeded: {count} questions of {t['max_nodes']}")
    mins = int((datetime.datetime.now() - datetime.datetime.fromisoformat(t["started"])).total_seconds() // 60) if timed else 0
    if timed and t["budget_min"] and mins > t["budget_min"]:
        R.append(f"time budget exceeded: {mins} min of {t['budget_min']}")
    return F, R


def cmd_check(a):
    with txn(a.file, write=False) as t:
        F, R = assess(t)
    for x in F:
        print("✗", x)
    for x in R:
        print("~", x)
    if F:
        sys.exit(1)
    print("✓ structurally closed" + (" within budget — residue listed above" if R else "") +
          ". Structural only: substance is for the reviewer.")
    sys.exit(2 if R else 0)


def unplaced(t):
    return [i for i in walk(t) if i != "Q0" and status(t, i) in ("ANSWERED", "CONCEDED")
            and material(t, i) and not t["nodes"][i]["section"]]


def fmt_answer(n):
    if n["decision"] == "CONCEDED":
        return f"(Conceded) {esc(n['concession'])}"
    s = esc(n["a"])
    if n["qualifier"]:
        s += f" [Qualifier: {esc(n['qualifier'])}]"
    return s


def support_lines(n):
    if n["decision"] == "CONCEDED":
        return []
    return [f"  - {lab}: {esc(n[k])}" for k, lab in (("grounds", "Evidence"), ("warrant", "Authority"),
                                                      ("rebuttal", "Meets")) if n[k]]


def review_text(t):
    """The reviewable content, built explicitly (tree, plan, reserve). No timestamps, no approval state."""
    N = t["nodes"]
    L = ["*Internal privileged analytical document. Never served.*", "",
         f"**Proposition:** {fmt_answer(N['Q0'])}", "", "## Tree", ""]
    for i in walk(t):
        if i == "Q0":
            continue
        n, ind, st, em = N[i], "  " * (depth(i) - 1), status(t, i), eff_mat(t, i)
        tag = (f"{st} · m{n['mat']}" + (f"→m{em} via duplicate" if em != n["mat"] else "") + f" · {esc(n['gen'])}" +
               (f" · {n['type']}/{n['effect']}" if n["type"] and n["decision"] == "ANSWERED" else ""))
        L.append(f"{ind}- **{i}** [{tag}] {esc(n['q'])}")
        if st == "PRUNED":
            continue
        for k, lab in (("a", "A"), ("grounds", "Grounds"), ("warrant", "Warrant"), ("qualifier", "Qualifier"),
                       ("rebuttal", "Rebuttal"), ("concession", "Concession"), ("reason", "Reason"),
                       ("dup_of", "Duplicate of")):
            if n[k]:
                L.append(f"{ind}  - {lab}: {esc(n[k])}")
    L += ["", "## Document plan (draft from this, never from the tree order)", "", "### Conclusion",
          f"- Q0: {fmt_answer(N['Q0'])}"] + support_lines(N["Q0"])
    placed = [i for i in walk(t) if i != "Q0" and N[i]["section"] and status(t, i) in ("ANSWERED", "CONCEDED")]
    order = lambda x: (N[x]["order"], key(x))
    sections = []
    for i in sorted(placed, key=order):
        if N[i]["section"] not in sections:
            sections.append(N[i]["section"])
    for sec in sections:
        L.append(f"### {esc(sec)}")
        for i in sorted([x for x in placed if N[x]["section"] == sec], key=order):
            L.append(f"- {i}: {fmt_answer(N[i])}")
            L += support_lines(N[i])
    up = unplaced(t)
    L.append(f"- **Unplaced material answers:** {', '.join(up)}" if up else "- all material answers placed")
    L += ["", "## Reserve (answered, below threshold → speaking note / bench questions)", ""]
    res = [i for i in walk(t) if i != "Q0" and status(t, i) == "ANSWERED" and not material(t, i)]
    for i in res:
        L.append(f"- {i}: {esc(N[i]['q'])} → {fmt_answer(N[i])}")
        L += support_lines(N[i])
    if not res:
        L.append("- none")
    return "\n".join(L).rstrip() + "\n"


def digest(t):
    return hashlib.sha256(full_md(t).encode()).hexdigest()


def md_path(f):
    if not f.endswith(".json"):
        die(f"refusing to render: {f} does not end in .json")
    return f[: -len(".json")] + ".md"


def full_md(t):
    """The whole render, deterministic from the tree's analytical content: no timestamps,
    no revision number and no approval state, so ready can demand byte-for-byte equality."""
    F, R = assess(t, timed=False)
    head = (f"# Question tree — {esc(t['doc'])} ({esc(t['created'])}; mode {esc(t['mode'])}; threshold m{t['threshold']}; "
            f"depth {t['depth_cap']}; node budget {t['max_nodes']})")
    closure = ["", "## Closure (structural; run check for the time budget)", ""] + \
              [f"- ✗ {x}" for x in F] + [f"- ~ {x}" for x in R]
    if not F:
        closure.append("- ✓ structurally closed")
    body = review_text(t)
    return head + "\n" + body + "\n".join(closure) + "\n\n" + MARK + hashlib.sha256(body.encode()).hexdigest() + " -->\n"


def render_current(t, f):
    mp = md_path(os.path.realpath(f))
    if not os.path.exists(mp):
        return False
    with open(mp, "rb") as h:
        return h.read() == full_md(t).encode("utf-8")


def cmd_render(a):
    with txn(a.file, write=False) as t:
        atomic_write(md_path(os.path.realpath(a.file)), full_md(t))   # inside the lock: renders publish in order
    print(md_path(os.path.realpath(a.file)))


def cmd_approve(a):
    with txn(a.file) as t:
        if not render_current(t, a.file):
            die("the render on disk is not the current tree: run render, have the reviewer review it, then approve")
        t["approved_rev"] = t["rev"] + 1
        t["approved_hash"] = digest(t)
        t["approved_at"] = now()
        t["_keep_approval"] = True
    print("approved revision", t["approved_rev"])


def cmd_ready(a):
    with txn(a.file, write=False) as t:
        F, R = assess(t)
        appr = t.get("approved_rev") == t["rev"] and t.get("approved_hash") == digest(t)
        fresh = render_current(t, a.file)
        up = unplaced(t)
    bad = False
    if F:
        print("✗ not closed:", len(F), "failure(s) — run check"); bad = True
    if not appr:
        print("✗ not approved at this revision — render, the reviewer reviews, then approve"); bad = True
    if not fresh:
        print("✗ the render on disk does not reproduce the current tree — render again and re-approve"); bad = True
    if up:
        print("✗ material answers not placed in the document plan:", ", ".join(up[:15])); bad = True
    if R:
        print("~ residue:", len(R), "item(s) — carried into the draft cover note")
    if bad:
        sys.exit(1)
    print("✓ ready to linearise")


def check_text(v, where):
    try:
        v.encode("utf-8")
    except UnicodeEncodeError:
        die(f"{where} contains characters that cannot be stored (unpaired surrogates): retype it")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    s = ap.add_subparsers(dest="cmd", required=True)
    p = s.add_parser("init"); p.add_argument("prep"); p.add_argument("--root", required=True)
    p.add_argument("--doc", required=True); p.add_argument("--mode", choices=["draft", "tutor"], default="draft")
    p.add_argument("--threshold", type=int, default=2); p.add_argument("--depth", type=int, default=5)
    p.add_argument("--budget-min", type=int, default=120); p.add_argument("--max-nodes", type=int, default=60)
    p.set_defaults(fn=cmd_init)
    p = s.add_parser("add"); p.add_argument("file"); p.add_argument("parent"); p.add_argument("--q", required=True)
    p.add_argument("--gen", required=True); p.add_argument("--mat", type=int, default=2)
    p.add_argument("--force", action="store_true"); p.set_defaults(fn=cmd_add)
    p = s.add_parser("add-many"); p.add_argument("file"); p.add_argument("parent"); p.add_argument("--json", required=True)
    p.add_argument("--force", action="store_true"); p.set_defaults(fn=cmd_add_many)
    p = s.add_parser("answer"); p.add_argument("file"); p.add_argument("id"); p.add_argument("--a", required=True)
    p.add_argument("--type", choices=["fact", "law", "mixed"], required=True)
    p.add_argument("--effect", choices=["supports", "undermines", "neutral"], required=True)
    for k in ("grounds", "warrant", "qualifier", "rebuttal"):
        p.add_argument(f"--{k}")
    p.set_defaults(fn=cmd_answer)
    p = s.add_parser("close"); p.add_argument("file"); p.add_argument("id")
    p.add_argument("status", choices=["CONCEDED", "OUT_OF_SCOPE", "IMMATERIAL", "DUPLICATE", "BLOCKED", "DEFERRED"])
    p.add_argument("--reason"); p.add_argument("--concession"); p.add_argument("--of")
    p.add_argument("--force", action="store_true"); p.set_defaults(fn=cmd_close)
    for name, fn in (("reopen", cmd_reopen), ("confirm", cmd_confirm), ("unplace", cmd_unplace), ("show", cmd_show),
                     ("status", cmd_status)):
        p = s.add_parser(name); p.add_argument("file"); p.add_argument("id"); p.set_defaults(fn=fn)
    p = s.add_parser("reclass"); p.add_argument("file"); p.add_argument("id")
    p.add_argument("--mat", type=int); p.add_argument("--gen"); p.set_defaults(fn=cmd_reclass)
    p = s.add_parser("place"); p.add_argument("file"); p.add_argument("id"); p.add_argument("--section", required=True)
    p.add_argument("--order", type=int, default=0); p.set_defaults(fn=cmd_place)
    p = s.add_parser("open"); p.add_argument("file"); p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_open)
    for name, fn in (("approve", cmd_approve), ("check", cmd_check), ("ready", cmd_ready), ("render", cmd_render)):
        p = s.add_parser(name); p.add_argument("file"); p.set_defaults(fn=fn)
    a = ap.parse_args()
    for k, v in vars(a).items():
        if isinstance(v, str):
            check_text(v, f"--{k}")
    if a.cmd == "add-many" and isinstance(a.json, str):
        try:
            items = json.loads(a.json)
        except ValueError:
            items = None
        for it in items if isinstance(items, list) else []:
            for k, v in (it.items() if isinstance(it, dict) else []):
                if isinstance(v, str):
                    check_text(v, f"--json item {k}")
    if hasattr(a, "file"):
        if not a.file.endswith(".json") or not os.path.realpath(a.file).endswith(".json"):
            die("tree file (and the file it resolves to) must end in .json")
        if not os.path.exists(a.file):
            die(f"no tree file: {a.file}")
    a.fn(a)


if __name__ == "__main__":
    main()
