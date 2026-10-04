[dict(name=f"{nm} {p} {c} rib={rib}", face="+Z", start=s, segs=sg, closed=False, grooves=[dict(width=3.5, depth=3.0, profile=p, corners=c, rib=rib)])
 for nm, s, sg in [("fuzz huge-r arc", (-15.327994, -0.173873), [("L", (-11.878516, -0.922586)), ("A", (-10.761997, -1.164928))]),
                   ("axis huge-r arc 1e-6", (-15.0, 0.0), [("L", (-10.0, 0.0)), ("A", (-5.0, 0.000001))]),
                   ("axis r=2e6", (-15.0, 0.0), [("L", (-10.0, 0.0)), ("A", (-5.0, 0.00000625))]),
                   ("axis r=1e5", (-15.0, 0.0), [("L", (-10.0, 0.0)), ("A", (-5.0, 0.000125))])]
 for p, c, rib in [("circle", "mitre", False), ("circle", "round", True), ("rect", "mitre", False), ("v", "mitre", True), ("round", "mitre", False)]]
