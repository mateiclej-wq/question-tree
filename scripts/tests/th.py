#!/usr/bin/env python3
"""Small, explicit test helpers for test_qtree.sh (replaces inline interpreter snippets)."""
import json, os, sys


def load(p):
    with open(p) as f:
        return json.load(f)


def main():
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "approved":            # approval recorded at the current revision
        t = load(args[0]); print(t["approved_rev"] == t["rev"])
    elif cmd == "cleared":           # re-answer emptied Q1's grounds and cleared approval
        t = load(args[0]); print(t["nodes"]["Q1"]["grounds"] == "" and t["approved_rev"] is None)
    elif cmd == "children":          # number of root children, and number of distinct ones
        c = load(args[0])["nodes"]["Q0"]["children"]; print(len(c), len(set(c)))
    elif cmd == "count":             # number of nodes in the tree
        print(len(load(args[0])["nodes"]))
    elif cmd == "realpath":
        print(os.path.realpath(args[0]))
    elif cmd == "matgen":            # materiality and generator from `show` output on stdin
        t = sys.stdin.read(); j = json.loads(t[t.index("{"):]); print(j["mat"], j["gen"])
    elif cmd == "crlf":              # rewrite a file with CRLF line endings
        with open(args[0], "rb") as f:
            b = f.read()
        with open(args[0], "wb") as f:
            f.write(b.replace(b"\n", b"\r\n"))
    elif cmd == "jsontype":          # type name of the JSON value on stdin
        print(type(json.load(sys.stdin)).__name__)
    else:
        sys.exit(f"unknown helper {cmd}")


if __name__ == "__main__":
    main()
