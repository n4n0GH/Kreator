"""Round-trip every QML file found on the system through the parser.

Usage: python3 tests/test_qml_roundtrip.py [dir ...]
Checks that parse -> serialize keeps the token stream intact (ignoring
whitespace and statement separators) and that serialisation is idempotent.
"""
import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from kreator import qmldoc  # noqa: E402


def sig(text):
    return [t.text for t in qmldoc.tokenize(text) if t.kind != "newline" and t.text not in (";",)]


def check(path):
    src = open(path, encoding="utf-8").read()
    doc = qmldoc.parse(src)
    out = doc.to_text()
    a, b = sig(src), sig(out)
    if a != b:
        for i, (x, y) in enumerate(zip(a, b)):
            if x != y:
                return f"token mismatch at {i}: {a[max(0,i-8):i+4]} vs {b[max(0,i-8):i+4]}"
        return f"token count {len(a)} vs {len(b)}"
    out2 = qmldoc.parse(out).to_text()
    if out2 != out:
        return "not idempotent"
    return None


if __name__ == "__main__":
    dirs = sys.argv[1:] or ["/usr/lib64/qt6/qml", "/usr/share/plasma"]
    files = [f for d in dirs for f in glob.glob(os.path.join(d, "**/*.qml"), recursive=True)]
    fails = 0
    for f in files:
        try:
            err = check(f)
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
        if err:
            fails += 1
            if fails <= 25:
                print(f"{f}: {err}")
    print(f"{len(files) - fails}/{len(files)} files round-trip OK")
    sys.exit(1 if fails else 0)
