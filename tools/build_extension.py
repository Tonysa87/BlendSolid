"""Build a per-platform BlendSolid extension zip, with the worker libraries bundled in blendsolid/worker_libs.

Run it with Blender's Python (pip downloads the target platform's binary wheels):
    <blender>/5.2/python/bin/python3.13 tools/build_extension.py --platform windows-x64 --blender <blender>
"""
import argparse
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLATFORM_TAGS = {
    "windows-x64": ["win_amd64"],
    "linux-x64": ["manylinux_2_28_x86_64", "manylinux_2_27_x86_64", "manylinux_2_17_x86_64",
                  "manylinux2014_x86_64", "linux_x86_64"],
    "macos-arm64": ["macosx_14_0_arm64", "macosx_12_0_arm64", "macosx_11_0_arm64"],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", required=True, choices=sorted(PLATFORM_TAGS))
    ap.add_argument("--blender", required=True)
    ap.add_argument("--out", default=os.path.join(ROOT, "dist"))
    args = ap.parse_args()

    stage = os.path.join(args.out, f"stage-{args.platform}", "blendsolid")
    shutil.rmtree(os.path.dirname(stage), ignore_errors=True)
    shutil.copytree(os.path.join(ROOT, "blendsolid"), stage,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "worker_libs"))
    manifest = os.path.join(stage, "blender_manifest.toml")
    with open(manifest, encoding="utf-8") as f:
        text = f.read()
    version = re.search(r'^version = "([^"]+)"', text, re.M).group(1)
    text = re.sub(r"^platforms = \[.*\]$", f'platforms = ["{args.platform}"]', text, flags=re.M)
    with open(manifest, "w", encoding="utf-8") as f:
        f.write(text)

    pip = [sys.executable, "-m", "pip", "install", "--no-cache-dir", "--target", os.path.join(stage, "worker_libs"),
           "--only-binary=:all:", "--python-version", "3.13", "--implementation", "cp"]
    for tag in PLATFORM_TAGS[args.platform]:
        pip += ["--platform", tag]
    subprocess.run(pip + ["-r", os.path.join(ROOT, "tools", "worker-requirements.txt")], check=True)

    os.makedirs(args.out, exist_ok=True)
    zip_path = os.path.join(args.out, f"blendsolid-{version}-{args.platform}.zip")
    subprocess.run([args.blender, "--command", "extension", "build", "--source-dir", stage,
                    "--output-filepath", zip_path], check=True)
    print(f"built {zip_path} ({os.path.getsize(zip_path) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
