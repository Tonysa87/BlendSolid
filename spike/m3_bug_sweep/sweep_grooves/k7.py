import math
cs = []
for nm, start, segs, closed in [
    ("line", (-10.0, 0.0), [("L", (10.0, 0.0))], False),
    ("L 90", (-10.0, -5.0), [("L", (5.0, -5.0)), ("L", (5.0, 5.0))], False),
    ("V 150", (-10.0, -5.0), [("L", (5.0, -5.0)), ("L", (round(5 - 10 * math.cos(math.radians(30)), 6), round(-5 + 10 * math.sin(math.radians(30)), 6)))], False),
    ("arc", (-10.0, -5.0), [("L", (0.0, -5.0)), ("A", (0.0, 5.0)), ("L", (-10.0, 5.0))], False),
    ("tri", (-10.0, -5.0), [("L", (10.0, -5.0)), ("L", (-10.0, 5.0))], True)]:
    for p1, c1, p2, c2 in [("round", "round", "round", "mitre"), ("round", "round", "round", "round"), ("round", "mitre", "round", "mitre"),
                           ("circle", "round", "circle", "round"), ("rect", "mitre", "rect", "mitre"), ("v", "mitre", "v", "mitre"), ("round", "round", "v", "round")]:
        for rib in (True, False):
            cs.append(dict(name=f"{nm} {p1}/{c1} then {p2}/{c2} {'rib' if rib else 'groove'}", face="+Z", start=start, segs=segs, closed=closed,
                           grooves=[dict(width=2.0, depth=2.0, profile=p1, corners=c1, rib=rib), dict(width=1.0, depth=2.0, profile=p2, corners=c2, rib=rib)]))
