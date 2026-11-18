#!/usr/bin/env python3
"""Read-only benchmark of Hermes Lectern indexing against a real vault."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import stat
import time
from pathlib import Path


def fingerprint(root: Path) -> dict[str, tuple[int, int, int, str]]:
    result = {}
    for current, dirs, files in os.walk(root, followlinks=False):
        base = Path(current)
        for name in ["", *dirs, *files]:
            p = base if name == "" else base / name
            try:
                st = p.lstat()
                result[p.relative_to(root).as_posix() or "."] = (st.st_mode, st.st_size, st.st_mtime_ns, os.readlink(p) if p.is_symlink() else "")
            except OSError:
                result[p.relative_to(root).as_posix()] = (-1, -1, -1, "")
    return result


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--home", required=True, type=Path)
    args = parser.parse_args()
    root, home = args.root.expanduser().absolute(), args.home.expanduser().absolute()
    if not root.is_dir():
        parser.error("--root must be an existing directory")
    os.environ["HERMES_HOME"] = str(home)
    core = load_module(Path(__file__).parents[1] / "dashboard" / "vault_core.py", "hermes_lectern_bench_core")
    api = load_module(Path(__file__).parents[1] / "dashboard" / "plugin_api.py", "hermes_lectern_bench_api")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    before = fingerprint(root)
    configured = core.configure(str(root))
    app = FastAPI()
    app.include_router(api.router, prefix="/api/plugins/hermes-lectern")
    client = TestClient(app)
    start = time.perf_counter(); first = client.post("/api/plugins/hermes-lectern/refresh"); first_s = time.perf_counter() - start
    first.raise_for_status()
    start = time.perf_counter(); second = client.post("/api/plugins/hermes-lectern/refresh"); second_s = time.perf_counter() - start
    second.raise_for_status()
    status = client.get("/api/plugins/hermes-lectern/status").json()
    db = core.db_path()
    start = time.perf_counter(); dashboard_response = client.get("/api/plugins/hermes-lectern/dashboard"); dashboard_s = time.perf_counter() - start
    dashboard_response.raise_for_status(); dashboard = dashboard_response.json()
    conn = core._connect(False)
    try:
        first_row = conn.execute("SELECT n.path,f.body FROM notes n JOIN notes_fts f ON f.path=n.path WHERE length(f.body)>0 ORDER BY n.path LIMIT 1").fetchone()
    finally:
        conn.close()
    q = "TaskNotes"
    if first_row and first_row["body"]:
        import re
        candidates = re.findall(r"[A-Za-z0-9]{4,}|[\u3040-\u30ff\u4e00-\u9fff]{4,}", first_row["body"])
        if candidates:
            q = candidates[0]
    start = time.perf_counter(); search_response = client.get("/api/plugins/hermes-lectern/search", params={"q": q, "limit": 20}); search_s = time.perf_counter() - start
    search_response.raise_for_status()
    note_path = first_row["path"] if first_row else ""
    start = time.perf_counter(); note_response = client.get("/api/plugins/hermes-lectern/note", params={"path": note_path}) if note_path else None; note_s = time.perf_counter() - start
    if note_response is not None: note_response.raise_for_status()
    single_save_s = None
    single_save_verified = False
    if note_path:
        source = root / note_path
        raw = source.read_bytes()
        content = raw.decode("utf-8")
        save_root = home / "single-save-vault"
        save_note = save_root / note_path
        save_note.parent.mkdir(parents=True, exist_ok=True)
        (save_root / ".obsidian").mkdir(exist_ok=True)
        shutil.copy2(source, save_note)
        save_home = home / "single-save-home"
        os.environ["HERMES_HOME"] = str(save_home)
        configured_save = client.put("/api/plugins/hermes-lectern/config", json={"root": str(save_root)})
        configured_save.raise_for_status()
        refreshed_save = client.post("/api/plugins/hermes-lectern/refresh")
        refreshed_save.raise_for_status()
        base = client.get("/api/plugins/hermes-lectern/note", params={"path": note_path})
        base.raise_for_status()
        edited = content + "\n\n# benchmark single-save\n"
        start = time.perf_counter(); saved = client.put("/api/plugins/hermes-lectern/note", json={"path": note_path, "content": edited, "base_sha256": base.json()["sha256"]}); single_save_s = time.perf_counter() - start
        saved.raise_for_status()
        verified = client.get("/api/plugins/hermes-lectern/note", params={"path": note_path})
        verified.raise_for_status()
        single_save_verified = verified.json()["content"] == edited and saved.json()["size"] == len(edited.encode("utf-8"))
        if not single_save_verified:
            raise RuntimeError("single-save result did not match the temp copy")
    after = fingerprint(root)
    changed = sorted(set(before) | set(after))
    changed = [p for p in changed if before.get(p) != after.get(p)]
    print(json.dumps({
        "root": str(root), "home": str(home), "notes": status["notes"],
        "first_full_index_seconds": round(first_s, 3), "first_added": first.json().get("added"),
        "second_refresh_seconds": round(second_s, 3), "second_unchanged": second.json().get("unchanged"),
        "index_bytes": db.stat().st_size if db.exists() else 0,
        "dashboard_get_seconds": round(dashboard_s, 4), "search_get_seconds": round(search_s, 4),
        "search_query": q, "search_results": len(search_response.json()),
        "note_get_seconds": round(note_s, 4), "note_path": note_path,
        "single_save_put_seconds": round(single_save_s, 4) if single_save_s is not None else None,
        "single_save_verified": single_save_verified,
        "single_save_test_root": str(home / "single-save-vault") if note_path else None,
        "dashboard_counts": dashboard["counts"], "dashboard_due": len(dashboard["due"]),
        "vault_fingerprint_before": {"files": sum(1 for p,v in before.items() if p != "." and not stat.S_ISDIR(v[0])), "sum_file_sizes": sum(v[1] for p,v in before.items() if p != "." and not stat.S_ISDIR(v[0])), "max_mtime_ns": max((v[2] for v in before.values()),default=0)},
        "vault_fingerprint_after": {"files": sum(1 for p,v in after.items() if p != "." and not stat.S_ISDIR(v[0])), "sum_file_sizes": sum(v[1] for p,v in after.items() if p != "." and not stat.S_ISDIR(v[0])), "max_mtime_ns": max((v[2] for v in after.values()),default=0)},
        "vault_changed_paths": changed,
        "cache_note": "first full pass uses a cold SQLite index; second pass uses a warm index while OS file-cache state is uncontrolled; GETs are end-to-end TestClient timings; single-save PUT uses one copied note in a separate scratch vault with its index prebuilt",
    }, ensure_ascii=False, indent=2))
    if changed:
        print("VAULT MUTATION DETECTED; benchmark exits non-zero", flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
