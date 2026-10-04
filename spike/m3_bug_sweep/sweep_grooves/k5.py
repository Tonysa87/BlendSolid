import math
cs = []
for turn in [150, 165, 170, 175, 177.5, 179, 179.9, 180]:
    a = math.radians(180 - turn)
    end = (round(5 - 10 * math.cos(a), 6), round(10 * math.sin(a), 6))
    for p in ["rect", "round", "v", "circle"]:
        cs.append(dict(name=f"turn {turn} {p} round", face="+Z", start=(-10.0, 0.0), segs=[("L", (5.0, 0.0)), ("L", end)], closed=False,
                       grooves=[dict(width=2.0, depth=1.5, profile=p, corners="round", rib=False)]))
cs
