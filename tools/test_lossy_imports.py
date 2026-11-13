#!/usr/bin/env python3
"""Tests for tools/lossy_imports.py. Run: python3 -I tools/test_lossy_imports.py"""
import os
import subprocess
import sys
import tempfile

TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lossy_imports.py")
TEX = '[remap]\n\nimporter="texture"\ntype="CompressedTexture2D"\n\n[params]\n\ncompress/mode=0\ncompress/lossy_quality=0.7\nmipmaps/generate=false\nroughness/mode=0\n'
SCENE = '[remap]\n\nimporter="scene"\n\n[params]\n\ncompress/mode=0\nmipmaps/generate=false\n'

failed = 0


def ok(cond, msg):
    global failed
    if not cond:
        failed += 1
        print("FAIL", msg)


def run(*args):
    return subprocess.run([sys.executable, "-I", TOOL, *args], capture_output=True, text=True)


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


with tempfile.TemporaryDirectory() as root:
    tex = write(root, "pbr-library/pbr_x/albedo.png.import", TEX)
    scene = write(root, "model-library/m/m.glb.import", SCENE)
    outside = write(root, "courses/t.png.import", TEX)
    ok(run("--check", root).returncode == 1, "--check should fail before the fix")
    r = run(root)
    ok(r.returncode == 0 and "1 texture import" in r.stdout, f"fix run: {r.stdout}{r.stderr}")
    t = read(tex)
    ok("compress/mode=1\n" in t and "mipmaps/generate=true\n" in t, "texture made lossy with mipmaps")
    ok("compress/lossy_quality=0.7\n" in t and "roughness/mode=0\n" in t, "other params kept")
    ok(read(scene) == SCENE, "scene import untouched")
    ok(read(outside) == TEX, "file outside the stores untouched")
    ok(run("--check", root).returncode == 0, "--check should pass after the fix")

print(f"test_lossy_imports: {failed} failed")
sys.exit(1 if failed else 0)
