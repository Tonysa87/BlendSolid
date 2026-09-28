"""Why the success-criterion parts fail: non-unique references, flagged/wrong ones, build errors.
PYTHONPATH=.:.dev/pytest $PY spike/m2_criterion/debug.py [part ...] [--insert]"""
import sys, traceback
sys.path[:0] = ["tests/unit", "blendsolid/worker", ".dev/worker_libs"]
import criterion
from criterion_corpus import corpus

names = [a for a in sys.argv[1:] if not a.startswith("--")]
for case in corpus():
    if names and case.name not in names:
        continue
    print(f"== {case.name}")
    try:
        if "--insert" in sys.argv:
            before = criterion.Build(case.source)
            after = criterion.Build(criterion.insert_after_first(case.source, case.insert))
            builds = [before, after]
            mapping = lambda kind: criterion.identical(before, after, kind)
        else:
            builds, mapping = [criterion.Build(case.source)], None
            for change in case.changes:
                start = builds[-1].source
                for s in range(1, criterion.STEPS + 1):
                    src = change.apply(start, s / criterion.STEPS)
                    try:
                        builds.append(criterion.Build(src))
                    except Exception as e:
                        print(f"   build fails at {change} step {s}: {type(e).__name__}: {e}")
                        print("   " + "\n   ".join(l for l in src.split("\n") if "feature:" in l or " = " in l))
                        raise
    except Exception:
        continue
    first, last = builds[0], builds[-1]
    for kind in ("face", "edge"):
        tracked = {i: i for i in range(len(first.entities(kind)))}
        if mapping is None:
            for prev, nxt in zip(builds, builds[1:]):
                tracked = criterion.follow(prev, nxt, kind, tracked)
        else:
            tracked = mapping(kind)
        for i in range(len(first.entities(kind))):
            if i not in first.clickable[kind]:
                continue
            ref = first.refs[kind][i]
            got0 = first.resolve(kind, ref)[0] if ref else None
            if got0 != [i]:
                print(f"   NOT UNIQUE {kind} {i} {ref} -> {got0}  centre {first.desc[kind][i].centre.round(2)}")
                continue
            if i not in tracked:
                print(f"   lost by oracle {kind} {i} {ref}")
                continue
            got, warns = last.resolve(kind, ref)
            if got != [tracked[i]] or warns:
                print(f"   {'FLAGGED' if (got is None or warns) else 'WRONG'} {kind} {ref} -> {got} want {tracked[i]} {warns}")
