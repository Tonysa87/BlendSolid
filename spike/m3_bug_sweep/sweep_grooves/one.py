"""Run small hand-written cases sequentially: python one.py <file with cases separated by '----'>.
Each case: the lines inside `with BuildPart() as part:` (BOX implied unless it starts with 'XY')."""
import sys, time, os
sys.path[:0] = ["/home/tony/Projects/BlendSolid/blendsolid/worker", "/home/tony/Projects/BlendSolid/.dev/worker_libs"]
import runner, tessellate

info = {}
orig = tessellate.check


def check(shape):
    d = orig(shape)
    info.update(d)
    return d


tessellate.check = check
BOX = '    Box(40, 20, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1\n'
text = open(sys.argv[1]).read()
for block in text.split("----"):
    block = block.strip("\n")
    if not block.strip():
        continue
    title, _, body = block.partition("\n")
    face = "+Z"
    if title.startswith("XY"):
        pre = '    with sketch(Plane.XY) as sketch_1:  # feature: sketch_1\n'
    else:
        face = title.split()[0] if title.split()[0] in ("+Z", "+X", "-Y") else "+Z"
        pre = BOX + f'    with sketch(on_face(face("box_1", "{face}"))) as sketch_1:  # feature: sketch_1\n'
    src = "with BuildPart() as part:\n" + pre + "\n".join("    " + l for l in body.splitlines()) + "\nresult = part.part\n"
    info.clear()
    t0 = time.perf_counter()
    r = runner.run_script(src)
    print(f"## {title}: ok={r.ok} t={time.perf_counter() - t0:.2f} vol={r.volume!r} solids={info.get('solids')} "
          f"err={r.error!r} line={r.line} timing={ {k: round(v, 2) for k, v in r.timing.items()} } faces={r.faces}")
