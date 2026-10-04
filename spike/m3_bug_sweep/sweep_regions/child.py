import sys, json, time, math, traceback
sys.path[:0] = ["/home/tony/Projects/BlendSolid/blendsolid/worker", "/home/tony/Projects/BlendSolid/.dev/worker_libs", "/home/tony/Projects/BlendSolid", "/home/tony/Projects/BlendSolid/tests/unit"]
import runner
def resolve_check(src):
    import criterion
    b = criterion.Build(src)
    bad = []
    for kind in ("face", "edge"):
        for i in sorted(b.clickable[kind]):
            ref = b.refs[kind][i]
            if not ref:
                bad.append((kind, i, ref, "empty")); continue
            if ref.startswith("nearest_"):
                before = len(b.tracker.warnings)
                try:
                    item = eval(ref, b.ns)
                    ids = [j for j, x in enumerate(b.entities(kind)) if x.IsSame(item.wrapped)]; w = []
                except Exception as e:
                    ids, w = None, [repr(e)]
            else:
                ids, w = b.resolve(kind, ref)
            if ids != [i] or w:
                bad.append((kind, i, ref, ids, w))
    return bad
for line in sys.stdin:
    case = json.loads(line); print("CASE", case["id"], file=sys.stderr, flush=True)
    t = time.perf_counter()
    try:
        r = runner.run_script(case["src"])
        out = dict(id=case["id"], ok=r.ok, error=r.error, line=r.line, volume=r.volume, faces=r.faces,
                   nverts=None if r.verts is None else len(r.verts), nloops=None if r.loops is None else len(r.loops),
                   warnings=[list(w) for w in r.warnings],
                   regions=[[g["area"] for g in s["regions"]] for s in r.sketches],
                   inside=[[g["inside"] for g in s["regions"]] for s in r.sketches],
                   loops=[[g["loops"] for g in s["regions"]] for s in r.sketches] if case.get("loops") else None,
                   face_refs=r.face_refs, timing=r.timing)
        if r.ok and case.get("resolve") and r.faces:
            try:
                out["unresolved"] = resolve_check(case["src"])
            except Exception as e:
                out["unresolved"] = [("exc", repr(e))]
    except BaseException as e:
        out = dict(id=case["id"], ok=False, error="HARNESS " + traceback.format_exc(), crash=True)
    out["t"] = time.perf_counter() - t
    print(json.dumps(out), flush=True)
