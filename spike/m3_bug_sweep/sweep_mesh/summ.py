import json, glob, sys, collections
pat = sys.argv[1] if len(sys.argv) > 1 else "r_?.jsonl"
rows = [json.loads(l) for f in sorted(glob.glob(pat)) for l in open(f)]
print("cases", len(rows))
ok = [r for r in rows if r.get("ok") and not r.get("empty")]
err = [r for r in rows if not r.get("ok")]
print("meshed", len(ok), "errors", len(err), "hang", sum(1 for r in rows if r.get("hang")), "crash", sum(1 for r in rows if r.get("crash")))
ec = collections.Counter(r["error"][:90] for r in err)
for e, c in ec.most_common(15): print("  ", c, e)
def flag(r):
    f = []
    if r["open_edges"]: f.append("open")
    if r["nonmanifold_edges"]: f.append("nonmanifold")
    if r["dup_directed"]: f.append("orient")
    if r["zero_area_polys"]: f.append("zeroarea")
    if r["poly_repeat_vertex"]: f.append("repeatv")
    if r["fallbacks"]: f.append("fallback")
    if r["timing"].get("tessellate", 0) > 5: f.append("slow")
    if abs(r["dvol_over_area_tol"]) > 1.0: f.append("vol")
    if r["dev_over_tol"] > 1.5: f.append("dev")
    if r["normal_back"]: f.append("normback")
    if r["curved_lt1"]: f.append("sliver")
    if r["polys"] > 50000: f.append("many")
    return f
cnt = collections.Counter()
clean = 0
byfam = collections.defaultdict(collections.Counter)
for r in ok:
    fl = flag(r)
    r["flags"] = fl
    cnt.update(fl)
    byfam[r["meta"]["family"]].update(fl + ["n"])
    if not fl: clean += 1
print("clean", clean, cnt)
for fam, c in byfam.items(): print(fam, dict(c))
key = sys.argv[2] if len(sys.argv) > 2 else None
if key:
    sel = [r for r in ok if key in r["flags"]]
    sel.sort(key=lambda r: -(r.get("timing",{}).get("tessellate",0) if key in ("slow","many") else r.get(key if key in r else "curved_lt1", 0) or 0))
    for r in sel[:int(sys.argv[3]) if len(sys.argv)>3 else 10]:
        m = r["meta"]
        print(m, {k: r.get(k) for k in ["polys","open_edges","dup_directed","zero_area_polys","fallbacks","dvol_over_area_tol","dev_over_tol","dev_face","curved_lt1","curved_min_angle","normal_back","normal_min_dot","sliver_faces"]}, round(r["timing"].get("tessellate",0),2))
