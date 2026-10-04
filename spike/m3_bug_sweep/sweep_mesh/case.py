import sys, gen
src, meta = gen.make(int(sys.argv[1]))
open(f"case_{sys.argv[1]}.py","w").write(src); print(meta); print(src)
