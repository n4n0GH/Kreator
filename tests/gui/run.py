#!/usr/bin/env python3
"""Kreator's GUI tests: each test drives a real Kreator and checks the result.

    tests/gui/run.py                 all tests
    tests/gui/run.py flow tabs       tests whose name contains "flow" or "tabs"
    tests/gui/run.py -j 4            four at a time
    tests/gui/run.py -v flow_edit    show everything Kreator prints
    tests/gui/run.py --list          list the tests and what they need

Every test runs in a fresh temporary workspace: a copy of fixtures/ (the
files it opens and edits) with its own settings and session folders
(XDG_CONFIG_HOME, XDG_DATA_HOME), so neither the source tree nor your own
settings are touched. Kreator runs offscreen (QT_QPA_PLATFORM=offscreen);
tests that need Kate's editor, a native window, run in a private, invisible
KWin session (kwin_wayland --virtual).

A test file (gui_*.py) is executed inside Kreator by host.py; see there for
what it can use. Its first lines can declare, as plain literals:

    KATE = True             needs Kate's editor (runs in KWin; skipped without it)
    NEEDS = ["qmlls"]       skipped if a program is missing
    PLAIN_EDITOR = True     use the built-in source editor
    SETTINGS = {...}        Kreator settings (like the settings page writes them);
                            or a list: the settings of each run
    RUNS = 2                restart Kreator: each run gets the code after its
                            "# --- run N ---" line (and the code before the
                            first such line); the session carries over
    EXIT = {0: 9}           expected exit codes, by run (default 0)
    TIMEOUT = 120           seconds per run
    ARGS = [[...], ...]     Kreator's command line arguments, by run

and a function `between_runs(run, work)`, called by the runner (not in
Kreator) before run `run` > 0, e.g. to change a file while Kreator is closed.

A test passes when every run exits as expected, at least one check passed,
and nothing failed (FAIL lines, Python tracebacks, timeouts).
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
FIXTURES = os.path.join(HERE, "fixtures")
HOST = os.path.join(HERE, "host.py")
sys.path.insert(0, REPO)

META_KEYS = {"KATE", "NEEDS", "PLAIN_EDITOR", "SETTINGS", "RUNS", "EXIT", "TIMEOUT", "ARGS"}


# --------------------------------------------------------------------------- reading tests

class Test:
    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)[len("gui_"):-len(".py")]
        text = open(path, encoding="utf-8").read()
        tree = ast.parse(text, path)
        meta = {}
        self.between = None
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) \
                    and node.targets[0].id in META_KEYS:
                meta[node.targets[0].id] = ast.literal_eval(node.value)
            elif isinstance(node, ast.FunctionDef) and node.name == "between_runs":
                ns = {}
                exec(compile(ast.Module([node], []), path, "exec"), {"os": os, "shutil": shutil, "json": json}, ns)
                self.between = ns["between_runs"]
        markers = [int(m) for m in re.findall(r"^# --- run (\d+) ---[ \t]*$", text, re.M)]
        self.kate = bool(meta.get("KATE"))
        self.needs = list(meta.get("NEEDS", [])) + (["kwin_wayland"] if self.kate else [])
        self.plain = bool(meta.get("PLAIN_EDITOR"))
        self.runs = int(meta.get("RUNS", max(markers) + 1 if markers else 1))
        settings = meta.get("SETTINGS", {})
        self.settings = settings if isinstance(settings, list) else [settings] * self.runs
        self.exit = {int(k): v for k, v in meta.get("EXIT", {}).items()}
        self.timeout = int(meta.get("TIMEOUT", 120))
        self.args = meta.get("ARGS", [[]] * self.runs)


def discover(patterns):
    tests = sorted(Test(os.path.join(HERE, f)) for f in os.listdir(HERE)
                   if f.startswith("gui_") and f.endswith(".py"))
    if patterns:
        tests = [t for t in tests if any(p in t.name for p in patterns)]
    return tests


Test.__lt__ = lambda a, b: a.name < b.name


# --------------------------------------------------------------------------- requirements

_kate_problem = None


def missing(test) -> str:
    """Why the test can't run here ("" if it can)."""
    global _kate_problem
    for prog in test.needs:
        if prog == "qmlls":
            from kreator.lsp import find_qmlls
            if not find_qmlls(""):
                return "qmlls not found"
        elif not shutil.which(prog):
            return f"{prog} not found"
    if test.kate:
        if _kate_problem is None:
            from kreator import native
            _dir, _kate_problem = native.kate_editor_module(log=lambda msg: print(msg, flush=True))
        if _kate_problem:
            return f"Kate's editor module: {_kate_problem}"
    return ""


# --------------------------------------------------------------------------- running

def write_settings(cfg, settings, plain):
    os.makedirs(os.path.join(cfg, "kreator"), exist_ok=True)
    values = dict(settings)
    if plain:
        values["useKateEditor"] = False
    if values:
        encoded = json.dumps(values).replace("\\", "\\\\").replace('"', '\\"')
        with open(os.path.join(cfg, "kreator", "kreator.conf"), "w", encoding="utf-8") as fh:
            fh.write(f'[General]\nexternalEditors="{encoded}"\n')
    else:
        try:
            os.remove(os.path.join(cfg, "kreator", "kreator.conf"))
        except FileNotFoundError:
            pass


def command(test, work, run, socket_name):
    cmd = [sys.executable, "-X", "faulthandler", "-u", HOST, test.path, work, str(run), *test.args[run]]
    if not test.kate:
        return cmd, {"QT_QPA_PLATFORM": "offscreen"}
    inner = shlex.join(["env", f"WAYLAND_DISPLAY={socket_name}", "QT_QPA_PLATFORM=wayland", *cmd])
    return ["kwin_wayland", "--virtual", "--socket", socket_name, "--width", "1500", "--height", "950",
            "--no-lockscreen", "--no-global-shortcuts", "--exit-with-session", inner], {}


def run_test(test, verbose=False, keep=False):
    """(status, details, seconds): status is "pass", "fail" or "skip"."""
    why = missing(test)
    if why:
        return "skip", why, 0.0
    t0 = time.time()
    work = tempfile.mkdtemp(prefix=f"kreator-gui-{test.name}-")
    shutil.copytree(FIXTURES, work, dirs_exist_ok=True)
    cfg, data = os.path.join(work, ".config"), os.path.join(work, ".local-share")
    os.makedirs(cfg, exist_ok=True)
    os.makedirs(data, exist_ok=True)
    shutil.move(os.path.join(work, "katerc"), os.path.join(cfg, "katerc"))
    passes, failures, log = 0, [], []
    for run in range(test.runs):
        if run > 0 and test.between:
            test.between(run, work)
        write_settings(cfg, test.settings[run] if run < len(test.settings) else {}, test.plain)
        cmd, extra_env = command(test, work, run, f"kreator-test-{os.getpid()}-{test.name}-{run}")
        env = {**os.environ, "XDG_CONFIG_HOME": cfg, "XDG_DATA_HOME": data, **extra_env}
        env.pop("WAYLAND_DISPLAY", None) if test.kate else None
        proc = subprocess.Popen(cmd, cwd=work, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, errors="replace", start_new_session=True)
        try:
            out, _ = proc.communicate(timeout=test.timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            out, _ = proc.communicate()
            timed_out = True
        status = None
        for line in out.splitlines():
            if verbose:
                print(f"  [{test.name}:{run}] {line}", flush=True)
            if line.startswith("PASS "):
                passes += 1
                log.append(line)
            elif line.startswith("FAIL "):
                failures.append(f"run {run}: {line[5:]}" if test.runs > 1 else line[5:])
                log.append(line)
            elif line.startswith("Traceback ") or line.startswith("Fatal Python error"):
                failures.append(f"run {run}: Python error (see the output with -v {test.name})")
            elif line.startswith("@@exit "):
                status = int(line.split()[1])
        expected = test.exit.get(run, 0)
        if timed_out:
            failures.append(f"run {run}: timed out after {test.timeout} s")
        elif status is None:
            failures.append(f"run {run}: Kreator ended without reporting (crashed?)")
        elif status != expected:
            failures.append(f"run {run}: exit code {status}, expected {expected}")
    if not failures and passes == 0:
        failures.append("no checks were run")
    seconds = time.time() - t0
    if failures or keep:
        details = (failures or []) + [f"workspace kept: {work}"]
    else:
        shutil.rmtree(work, ignore_errors=True)
        details = []
    if failures:
        return "fail", details, seconds
    return "pass", details or [f"{passes} check" + ("" if passes == 1 else "s")], seconds


def main():
    parser = argparse.ArgumentParser(description="Run Kreator's GUI tests.")
    parser.add_argument("patterns", nargs="*", help="run only tests whose name contains one of these")
    parser.add_argument("-j", "--jobs", type=int, default=1, help="tests to run at the same time (default 1)")
    parser.add_argument("-v", "--verbose", action="store_true", help="show everything Kreator prints")
    parser.add_argument("--keep", action="store_true", help="keep the workspaces of passed tests too")
    parser.add_argument("--list", action="store_true", help="list the tests")
    opts = parser.parse_args()

    tests = discover(opts.patterns)
    if opts.list:
        for t in tests:
            what = ", ".join(x for x in ("Kate's editor (KWin)" if t.kate else "offscreen",
                                         "built-in editor" if t.plain else "",
                                         f"{t.runs} runs" if t.runs > 1 else "",
                                         *[f"needs {n}" for n in t.needs if n != "kwin_wayland"]) if x)
            print(f"{t.name:24} {what}")
        return 0
    if not tests:
        print("no tests match")
        return 1
    if any(t.kate for t in tests):
        missing(next(t for t in tests if t.kate))   # build Kate's editor module once, up front

    results = {}

    def one(t):
        r = run_test(t, opts.verbose, opts.keep)
        status, details, seconds = r
        label = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP"}[status]
        lines = [f"{label} {t.name} ({seconds:.0f} s)" if status != "skip" else f"{label} {t.name}"]
        lines += [f"     {d}" for d in details]
        print("\n".join(lines), flush=True)
        results[t.name] = status
    if opts.jobs > 1:
        with ThreadPoolExecutor(opts.jobs) as pool:
            list(pool.map(one, tests))
    else:
        for t in tests:
            one(t)
    counts = {s: sum(1 for v in results.values() if v == s) for s in ("pass", "fail", "skip")}
    print(f"\n{counts['pass']} passed, {counts['fail']} failed, {counts['skip']} skipped")
    return 1 if counts["fail"] else 0


if __name__ == "__main__":
    sys.exit(main())
