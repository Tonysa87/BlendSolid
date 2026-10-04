import json, re, sys, glob
RAW = re.compile(r"Standard_|StdFail|BRep_API|BRepSweep|TopoDS|Geom_|_NotDone|BOPAlgo|gp_|Precision|Exception:|AttributeError|TypeError|IndexError|KeyError|ZeroDivision|ValueError:|RuntimeError|DraftAngleError")
tot = passed = 0
cats = {}
def add(cat, item): cats.setdefault(cat, []).append(item)
for fn in sorted(glob.glob(sys.argv[1] if len(sys.argv) > 1 else "fuzz_p2_*.json")):
    d = json.load(open(fn))
    p1 = json.load(open(fn.replace("p2", "p1")))
    for c in p1["phase1"]:
        x = p1["r1"][c["id"]]; tot += 1
        if x.get("hang"): add("HANG sketch", c["id"]); continue
        if not x["ok"]: add("sketch fail", (c["id"], x["error"][:150])); continue
        if x["t"] > 10: add("slow sketch", (c["id"], x["t"]))
        passed += 1
    for n in d["notes"]: add("note " + n[1], n[:4])
    for c in d["phase2"]:
        x = d["r2"][c["id"]]; tot += 1; bad = False
        kind = c["id"].rsplit("_", 1)[1]
        if x.get("hang"): add("HANG", c["id"]); continue
        if x.get("crash"): add("CRASH", (c["id"], x["error"][-300:])); continue
        if x.get("t", 0) > 10: add("SLOW", (c["id"], round(x["t"], 1))); bad = True
        if not x["ok"]:
            e = x["error"]
            if RAW.search(e): add("RAW " + re.sub(r"[\d.]+", "#", e)[:90], (c["id"], e[:200], x.get("line"))); bad = True
            elif x.get("line") is None: add("NOLINE " + e[:60], (c["id"], e[:200])); bad = True
            elif c["extra"] == "crosses" or c["extra"] == "err-ok": pass
            elif c["vol"] is not None: add("ERR where volume expected: " + re.sub(r"[\d.()-]+", "#", e)[:80], (c["id"], e[:200])); bad = True
            else: add("err(other) " + re.sub(r"[\d.()-]+", "#", e)[:70], (c["id"], e[:160]))
        else:
            v = x["volume"]
            if c["extra"] == "crosses": add("revolve crossing axis accepted", (c["id"], v)); bad = True
            if c["vol"] is not None and not ("extrude_0" in c["src"] and kind in ("cut", "symcut")):
                tol = 1e-6 * max(1, abs(c["vol"])) + (3e-3 * abs(c["vol"]) if kind == "revolve" else 1e-3)
                if abs(v - c["vol"]) > tol: add("VOLUME " + kind, (c["id"], v, c["vol"], v - c["vol"])); bad = True
            ex = c["extra"]
            if kind == "taper" and ex:
                t, Ah = ex[0], ex[1]; V0 = ex[2] if len(ex) > 2 else 0.0
                added = v - V0
                if (t > 0 and not (0 < added < Ah * (1 + 1e-9))) or (t < 0 and not added > Ah * (1 - 1e-9)):
                    add("TAPER volume out of bounds", (c["id"], t, added, Ah)); bad = True
            if kind == "tapercut" and ex:
                _, t, Ah, V0 = ex; removed = V0 - v
                if (t > 0 and not (0 < removed < Ah * (1 + 1e-9))) or (t < 0 and not removed > Ah * (1 - 1e-9)):
                    add("TAPERCUT volume out of bounds", (c["id"], t, removed, Ah)); bad = True
            if x["faces"] and not x["nverts"]: add("NO MESH", c["id"]); bad = True
            if x.get("unresolved"):
                for u in x["unresolved"]:
                    add("REF " + str(u[2])[:40].split("(")[0] + " " + (str(u[4])[:50] if len(u) > 4 else str(u[3])[:50]), (c["id"], u)); 
                bad = True
            if x["warnings"]: add("warning " + x["warnings"][0][1][:50], (c["id"], x["warnings"]))
        if not bad: passed += 1
print("total", tot, "passed", passed)
for k in sorted(cats, key=lambda k: -len(cats[k])):
    print(f"== {k}  [{len(cats[k])}]")
    for it in cats[k][:3]: print("    ", str(it)[:400])
