from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import threading
import time
from urllib.parse import unquote
from datetime import date, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any

_LOCK = threading.RLock()
_LINK = re.compile(r"!?\[\[([^\]]+)\]\]")
MAX_ASSET_BYTES = 15 * 1024 * 1024
IMAGE_MIME = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif", "webp": "image/webp",
              "avif": "image/avif", "bmp": "image/bmp", "svg": "image/svg+xml"}
_ASSET_MAPS: dict[str, dict[str, list[str]]] = {}
SCHEMA_VERSION = "4"  # 4: tasks table (note tasks and checkbox tasks); 3: re-read titles after the quoted-# frontmatter fix
MAX_CHECKBOX_TASKS = 5000
TASK_TEXT_LIMIT = 200
DEFAULT_TASKS = {"notes": {"enabled": True, "tag": "tasknote", "folder": None}, "checkboxes": {"enabled": True}}
IN_PROGRESS_STATUSES = {"in-progress", "in progress", "doing", "active", "open"}
WAITING_STATUSES = {"waiting", "blocked"}
DONE_STATUSES = {"done", "completed", "complete", "canceled", "cancelled"}


class VaultError(Exception):
    def __init__(self, code: str, status: int = 400, extra: dict | None = None):
        super().__init__(code)
        self.code, self.status, self.extra = code, status, extra or {}


def home() -> Path:
    return Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))


DATA_DIR = "hermes-lectern"
LEGACY_DATA_DIR = "hermes-vault"  # name before 0.3.0; settings are copied over once


def config_path() -> Path:
    return home() / DATA_DIR / "config.json"


def _migrate_legacy_config() -> None:
    new, old = config_path(), home() / LEGACY_DATA_DIR / "config.json"
    if new.exists() or not old.is_file():
        return
    try:
        new.parent.mkdir(parents=True, exist_ok=True)
        new.write_bytes(old.read_bytes())
    except OSError:
        pass


def load_config() -> dict | None:
    _migrate_legacy_config()
    p = config_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        root = Path(data["root"])
        if not root.is_absolute() or not root.is_dir():
            return None
        try:
            tasks = _normalize_tasks(data.get("tasks"))
        except VaultError:
            tasks = _normalize_tasks(None)
        attention_tag = data.get("attention_tag")
        return {"root": str(root), "exclude": list(data.get("exclude", ["Attachments"])),
                "attention_field": data.get("attention_field"), "inbox_folder": data.get("inbox_folder"),
                "locale": data.get("locale", "auto"), "tasks": tasks,
                "attention_tag": attention_tag if isinstance(attention_tag, str) and attention_tag else None}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def require_config() -> tuple[Path, list[str]]:
    cfg = load_config()
    if cfg is None:
        raise VaultError("not_configured", 409)
    return Path(cfg["root"]), cfg["exclude"]


def _normalize_tag(tag: str) -> str:
    return tag.strip().lstrip("#").strip().casefold()


def _normalize_tasks(tasks: Any) -> dict:
    """Task source settings with defaults filled in; raises bad_tasks_config for anything unexpected."""
    out = {"notes": dict(DEFAULT_TASKS["notes"]), "checkboxes": dict(DEFAULT_TASKS["checkboxes"])}
    if tasks is None:
        return out
    if not isinstance(tasks, dict) or set(tasks) - {"notes", "checkboxes"}:
        raise VaultError("bad_tasks_config")
    notes, boxes = tasks.get("notes"), tasks.get("checkboxes")
    if notes is not None:
        if not isinstance(notes, dict) or set(notes) - {"enabled", "tag", "folder"}:
            raise VaultError("bad_tasks_config")
        if "enabled" in notes:
            if not isinstance(notes["enabled"], bool):
                raise VaultError("bad_tasks_config")
            out["notes"]["enabled"] = notes["enabled"]
        if "tag" in notes:
            tag = notes["tag"]
            if not isinstance(tag, str) or not tag.strip().lstrip("#").strip():
                raise VaultError("bad_tasks_config")
            out["notes"]["tag"] = tag.strip().lstrip("#").strip()
        if notes.get("folder") is not None:
            folder = notes["folder"]
            if not isinstance(folder, str) or not folder.strip().strip("/"):
                raise VaultError("bad_tasks_config")
            out["notes"]["folder"] = folder.strip().strip("/")
    if boxes is not None:
        if not isinstance(boxes, dict) or set(boxes) - {"enabled"} or ("enabled" in boxes and not isinstance(boxes["enabled"], bool)):
            raise VaultError("bad_tasks_config")
        out["checkboxes"]["enabled"] = boxes.get("enabled", True)
    return out


def configure(root: str, exclude: list[str] | None = None, attention_field: str | None = None,
              inbox_folder: str | None = None, locale: str = "auto", tasks: dict | None = None,
              attention_tag: str | None = None) -> dict:
    p = Path(root)
    if not p.is_absolute() or not p.is_dir() or not (p / ".obsidian").is_dir():
        raise VaultError("bad_root")
    excluded = exclude if exclude is not None else ["Attachments"]
    if any(not isinstance(x, str) or not x or "/" in x or x.startswith(".") for x in excluded):
        raise VaultError("bad_exclude")
    if attention_field is not None and (not isinstance(attention_field, str) or not attention_field):
        raise VaultError("bad_attention_field")
    if inbox_folder is not None and (not isinstance(inbox_folder, str) or not inbox_folder or "/" in inbox_folder or inbox_folder.startswith(".")):
        raise VaultError("bad_inbox_folder")
    if locale not in {"auto", "en", "ja"}:
        raise VaultError("bad_locale")
    locale = "auto" if locale is None else locale
    normalized_tasks = _normalize_tasks(tasks)
    if attention_tag is not None and (not isinstance(attention_tag, str) or not _normalize_tag(attention_tag)):
        raise VaultError("bad_attention_tag")
    target = config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    config = {"root": str(p), "exclude": excluded, "attention_field": attention_field,
              "inbox_folder": inbox_folder, "locale": locale, "tasks": normalized_tasks, "attention_tag": attention_tag}
    temp = target.with_suffix(".tmp")
    temp.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, target)
    _rebuild_note_tasks_if_indexed()
    return config


def db_path() -> Path:
    return home() / DATA_DIR / "index.sqlite"


def _validate(path: str, *, note: bool = False, root: Path | None = None, exclude: list[str] | None = None) -> Path:
    if not isinstance(path, str) or not path or "\\" in path or "\x00" in path or path.startswith("/"):
        raise VaultError("bad_path")
    parts = path.split("/")
    if any(part in ("", ".", "..") or (part.startswith(".") and part not in {".", ".."}) for part in parts):
        raise VaultError("bad_path")
    if exclude and parts[0] in exclude:
        raise VaultError("bad_path")
    if note and not path.endswith(".md"):
        raise VaultError("bad_path")
    if root is None:
        root, exclude = require_config()
    root_real = root.resolve()
    candidate = root.joinpath(*parts)
    ancestor = candidate
    missing: list[str] = []
    while not ancestor.exists() and not ancestor.is_symlink():
        missing.insert(0, ancestor.name)
        ancestor = ancestor.parent
    try:
        resolved = ancestor.resolve(strict=True)
        projected = resolved.joinpath(*missing)
        projected.relative_to(root_real)
    except (OSError, RuntimeError, ValueError):
        raise VaultError("bad_path") from None
    if not candidate.exists() and not candidate.is_symlink():
        return candidate
    try:
        candidate.resolve(strict=True).relative_to(root_real)
    except (OSError, RuntimeError, ValueError):
        raise VaultError("bad_path") from None
    return candidate


def parse_scalar(raw: str) -> Any:
    value = raw.strip()
    if not value:
        return ""
    if value.startswith(("'", '"')):
        quote = value[0]
        if value.endswith(quote):
            inner = value[1:-1]
            if quote == "'":
                return inner.replace("''", "'")
            return re.sub(r'\\([nt"\\])', lambda match: {"n":"\n","t":"\t",'"':'"',"\\":"\\"}[match.group(1)], inner)
        return value
    lower = value.lower()
    if lower in {"true", "false"}:
        return lower == "true"
    if lower in {"null", "~"}:
        return None
    if re.fullmatch(r"-?\d+", value):
        try:
            return int(value)
        except ValueError:
            pass
    if re.fullmatch(r"-?\d+\.\d+", value):
        try:
            return float(value)
        except ValueError:
            pass
    return value


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    lines = content.splitlines()
    if not lines or lines[0].lstrip("\ufeff") != "---":
        return {}, content
    end = next((i for i in range(1, len(lines)) if lines[i].strip() in {"---", "..."}), None)
    if end is None:
        return {}, content
    fm: dict[str, Any] = {}
    key: str | None = None
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith(("  - ", "- ")) and key:
            val = line.split("- ", 1)[1].strip()
            if not isinstance(fm.get(key, []), list):
                continue  # a block scalar such as `key: |` followed by dashed lines
            fm.setdefault(key, []).append(parse_scalar(val))
            continue
        m = re.match(r"^([A-Za-z0-9_./-]+):(?:\s*(.*))?$", line)
        if not m:
            key = None
            continue
        key, raw = m.group(1), (m.group(2) or "").strip()
        if raw.startswith("[") and raw.endswith("]"):
            fm[key] = [parse_scalar(x) for x in re.split(r",\s*(?=(?:[^\"']|\"[^\"]*\"|'[^']*')*$)", raw[1:-1]) if x.strip()]
        elif raw:
            # A quoted value may contain " #"; only unquoted values carry trailing comments.
            fm[key] = parse_scalar(raw if raw[0] in "'\"" else raw.split(" #", 1)[0])
        else:
            fm[key] = []
    return fm, "\n".join(lines[end + 1:])


def _note_data(path: str, content: str) -> dict:
    fm, body = parse_frontmatter(content)
    title = str(fm.get("title") or "").strip()
    if not title:
        title = next((m.group(1).strip() for line in body.splitlines() if (m := re.match(r"^#\s+(.+?)\s*#*\s*$", line))), Path(path).stem)
    tags = fm.get("tags", [])
    if not isinstance(tags, list):
        tags = [tags] if tags else []
    props = {k: v for k, v in fm.items() if k not in {"tags", "title"} and isinstance(v, (str, int, float, bool, list, type(None)))}
    return {"title": title, "body": body, "tags": tags, "props": props, "links": [m.group(1) for m in _LINK.finditer(content)]}


def _connect(create: bool = True) -> sqlite3.Connection | None:
    p = db_path()
    if not create and not p.exists():
        return None
    if create:
        p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _schema(conn: sqlite3.Connection) -> bool:
    conn.execute("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT)")
    row=conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    if row and row[0] == SCHEMA_VERSION:
        return False
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("DROP TABLE IF EXISTS notes_fts")
        conn.execute("DROP TABLE IF EXISTS links")
        conn.execute("DROP TABLE IF EXISTS tasks")
        conn.execute("DROP TABLE IF EXISTS notes")
        conn.execute("CREATE TABLE notes(path TEXT PRIMARY KEY,title TEXT,folder TEXT,mtime_ns INTEGER,size INTEGER,tags TEXT,props TEXT,raw_links TEXT NOT NULL)")
        conn.execute("CREATE TABLE links(src TEXT,raw TEXT,target TEXT)")
        conn.execute("CREATE TABLE tasks(id INTEGER PRIMARY KEY AUTOINCREMENT,path TEXT NOT NULL,line INTEGER,kind TEXT NOT NULL,text TEXT,status TEXT,due TEXT,project TEXT,tags TEXT)")
        conn.execute("CREATE INDEX tasks_path ON tasks(path)")
        conn.execute("CREATE VIRTUAL TABLE notes_fts USING fts5(path UNINDEXED,title,body,tokenize='trigram')")
        conn.execute("CREATE INDEX links_target ON links(target)")
        conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version',?)",(SCHEMA_VERSION,))
        conn.execute("DELETE FROM meta WHERE key='indexed_at'")
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return True


def _walk(root: Path, excluded: list[str]):
    for current, dirs, files in os.walk(root, followlinks=False):
        rel_dir = Path(current).relative_to(root)
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and not (not rel_dir.parts and d in excluded) and not (Path(current) / d).is_symlink())
        for name in sorted(files):
            p = Path(current) / name
            rel = p.relative_to(root).as_posix()
            if name.endswith(".md") and not p.is_symlink() and not any(s.startswith(".") for s in Path(rel).parts) and not (Path(rel).parts[0] in excluded):
                yield p, rel


def _resolve_link(raw: str, source: str, paths: set[str], by_base: dict[str, list[str]]) -> str | None:
    target = raw.split("|", 1)[0].split("#", 1)[0].strip()
    if not target or target.startswith(("http:", "https:")):
        return None
    target = target.removesuffix(".md")
    exact = target + ".md"
    if exact in paths:
        return exact
    relative = (PurePosixPath(source).parent / exact).as_posix()
    if relative in paths:
        return relative
    matches = by_base.get(PurePosixPath(target).name, [])
    return matches[0] if len(matches) == 1 else None


def _rebuild_links(conn: sqlite3.Connection) -> None:
    rows = list(conn.execute("SELECT path,raw_links FROM notes"))
    paths = {r["path"] for r in rows}
    by_base: dict[str, list[str]] = {}
    for p in paths:
        by_base.setdefault(Path(p).stem, []).append(p)
    conn.execute("DELETE FROM links")
    for r in rows:
        for raw in json.loads(r["raw_links"]):
            conn.execute("INSERT INTO links VALUES(?,?,?)", (r["path"], raw, _resolve_link(raw, r["path"], paths, by_base)))


def _iso_date(raw: Any) -> str | None:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return date.fromisoformat(str(raw).strip()[:10]).isoformat()
    except ValueError:
        return None


def _project_labels(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value]
    return [re.sub(r"^\[\[|\]\]$", "", str(v)).split("|", 1)[0] for v in values if v is not None and v != ""]


def _note_task_row(path: str, title: str, tags: list, props: dict, tasks_cfg: dict) -> tuple | None:
    """The tasks-table row for a note that is itself a task (tag or folder match), else None."""
    notes_cfg = tasks_cfg["notes"]
    if not notes_cfg["enabled"]:
        return None
    wanted, folder = _normalize_tag(notes_cfg["tag"]), notes_cfg["folder"]
    if not (any(isinstance(t, str) and _normalize_tag(t) == wanted for t in tags) or (folder and path.startswith(folder + "/"))):
        return None
    raw_status = props.get("status")
    status = "" if raw_status is None else str(raw_status).strip().lower()
    labels = _project_labels(props.get("projects")) or _project_labels(props.get("project"))
    return (path, None, "note", title, status, _iso_date(props.get("due")), json.dumps(labels, ensure_ascii=False), json.dumps([t for t in tags if isinstance(t, str)], ensure_ascii=False))


def _rebuild_note_tasks(conn: sqlite3.Connection, tasks_cfg: dict) -> None:
    """Note tasks depend on settings as well as on the note, so they are re-derived from the notes table every time."""
    conn.execute("DELETE FROM tasks WHERE kind='note'")
    rows = []
    for r in conn.execute("SELECT path,title,tags,props FROM notes"):
        row = _note_task_row(r["path"], r["title"], json.loads(r["tags"]), json.loads(r["props"]), tasks_cfg)
        if row:
            rows.append(row)
    conn.executemany("INSERT INTO tasks(path,line,kind,text,status,due,project,tags) VALUES(?,?,?,?,?,?,?,?)", rows)


def _rebuild_note_tasks_if_indexed() -> None:
    cfg = load_config()
    if cfg is None or not db_path().exists():
        return
    with _LOCK:
        conn = _connect(False)
        if conn is None:
            return
        try:
            row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            if row and row[0] == SCHEMA_VERSION:
                _rebuild_note_tasks(conn, cfg["tasks"])
                conn.commit()
        except sqlite3.Error:
            conn.rollback()
        finally:
            conn.close()


_CHECKBOX = re.compile(r"^\s*[-*+] \[(.)\] (.*\S.*)$")
_FENCE_OPEN = re.compile(r"^\s*(`{3,}|~{3,})")
_DUE = re.compile(r"📅\s*(\d{4}-\d{2}-\d{2})|\bdue::\s*(\d{4}-\d{2}-\d{2})")
_TAG = re.compile(r"(?:^|\s)#([\w/-]+)")
_CHECKBOX_STATUS = {" ": "open", "/": "in-progress", "x": "done", "X": "done", "-": "cancelled"}


def _checkbox_tasks(path: str, content: str, data: dict) -> list[dict]:
    """Open and in-progress `- [ ] text` lines outside frontmatter and fenced code, with 1-based line numbers."""
    lines = [line.rstrip("\r") for line in content.split("\n")]
    start = 0
    if lines and lines[0].lstrip("\ufeff") == "---":
        end = next((i for i in range(1, len(lines)) if lines[i].strip() in {"---", "..."}), None)
        if end is not None:
            start = end + 1
    props = data["props"]
    labels = _project_labels(props.get("projects")) or _project_labels(props.get("project")) or [data["title"]]
    found: list[dict] = []
    fence: tuple[str, int] | None = None
    for index in range(start, len(lines)):
        line = lines[index]
        if fence:
            stripped = line.strip()
            if stripped and stripped[0] == fence[0] and len(stripped) >= fence[1] and set(stripped) == {fence[0]}:
                fence = None
            continue
        opened = _FENCE_OPEN.match(line)
        if opened:
            fence = (opened.group(1)[0], len(opened.group(1)))
            continue
        m = _CHECKBOX.match(line)
        if not m:
            continue
        status = _CHECKBOX_STATUS.get(m.group(1), "open")
        if status in {"done", "cancelled"}:
            continue
        text = m.group(2).strip()
        due = next((_iso_date(g) for d in _DUE.finditer(text) for g in d.groups() if g), None)
        tags = [t for t in _TAG.findall(text) if not t.isdigit()]
        found.append({"line": index + 1, "text": text[:TASK_TEXT_LIMIT], "status": status, "due": due, "tags": tags, "project": labels})
    return found


def _store_checkboxes(conn: sqlite3.Connection, path: str, content: str, data: dict) -> None:
    """Replace one note's checkbox rows, honouring the per-vault cap."""
    conn.execute("DELETE FROM tasks WHERE path=? AND kind='checkbox'", (path,))
    room = MAX_CHECKBOX_TASKS - conn.execute("SELECT count(*) FROM tasks WHERE kind='checkbox'").fetchone()[0]
    if room <= 0:
        return
    rows = [(path, t["line"], "checkbox", t["text"], t["status"], t["due"], json.dumps(t["project"], ensure_ascii=False), json.dumps(t["tags"], ensure_ascii=False))
            for t in _checkbox_tasks(path, content, data)[:room]]
    conn.executemany("INSERT INTO tasks(path,line,kind,text,status,due,project,tags) VALUES(?,?,?,?,?,?,?,?)", rows)


def refresh() -> dict:
    root, excluded = require_config()
    tasks_cfg = (load_config() or {}).get("tasks") or _normalize_tasks(None)
    with _LOCK:
        _ASSET_MAPS.clear()
    started = time.monotonic()
    with _LOCK:
        conn = _connect()
        assert conn
        _schema(conn)
        old = {r["path"]: (r["mtime_ns"], r["size"]) for r in conn.execute("SELECT path,mtime_ns,size FROM notes")}
        added = updated = unchanged = 0
        changed: list[str] = []
        try:
            files = list(_walk(root, excluded))
            seen = {rel for _, rel in files}
            removed_paths = set(old) - seen
            for rel in removed_paths:
                conn.execute("DELETE FROM notes WHERE path=?", (rel,))
                conn.execute("DELETE FROM notes_fts WHERE path=?", (rel,))
                conn.execute("DELETE FROM tasks WHERE path=?", (rel,))
                changed.append(rel)
            for p, rel in files:
                st = p.stat()
                prev = old.get(rel)
                if prev == (st.st_mtime_ns, st.st_size):
                    unchanged += 1
                    continue
                content = p.read_text(encoding="utf-8", errors="replace")
                data = _note_data(rel, content)
                conn.execute("INSERT OR REPLACE INTO notes(path,title,folder,mtime_ns,size,tags,props,raw_links) VALUES(?,?,?,?,?,?,?,?)", (rel, data["title"], str(Path(rel).parent) if "/" in rel else "", st.st_mtime_ns, st.st_size, json.dumps(data["tags"], ensure_ascii=False), json.dumps(data["props"], ensure_ascii=False), json.dumps(data["links"],ensure_ascii=False)))
                conn.execute("DELETE FROM notes_fts WHERE path=?", (rel,))
                conn.execute("INSERT INTO notes_fts(path,title,body) VALUES(?,?,?)", (rel, data["title"], data["body"]))
                _store_checkboxes(conn, rel, content, data)
                changed.append(rel)
                if prev is None: added += 1
                else: updated += 1
            _rebuild_links(conn)
            _rebuild_note_tasks(conn, tasks_cfg)
            stamp = datetime.now().astimezone().isoformat()
            conn.execute("INSERT OR REPLACE INTO meta VALUES('indexed_at',?)", (stamp,))
            conn.commit()
        finally:
            conn.close()
    return {"added": added, "updated": updated, "removed": len(removed_paths), "unchanged": unchanged, "duration_ms": round((time.monotonic()-started)*1000, 2), "changed": changed[:200]}


def _hidden_or_odd(parts: list[str]) -> bool:
    return any(part in ("", ".", "..") or part.startswith(".") for part in parts)


def _asset_map(root: Path) -> dict[str, list[str]]:
    """Image file name -> vault-relative paths. Walks excluded folders too; skips dot entries and symlinks."""
    key = str(root)
    with _LOCK:
        cached = _ASSET_MAPS.get(key)
        if cached is not None:
            return cached
        _ASSET_MAPS.clear()
        found: dict[str, list[str]] = {}
        for current, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if not d.startswith(".") and not (Path(current) / d).is_symlink())
            for name in sorted(files):
                p = Path(current) / name
                if name.startswith(".") or "." not in name or name.rsplit(".", 1)[-1].lower() not in IMAGE_MIME or p.is_symlink():
                    continue
                found.setdefault(name, []).append(p.relative_to(root).as_posix())
        _ASSET_MAPS[key] = found
        return found


def _asset_file(root: Path, rel: str) -> Path | None:
    """The file at a vault-relative path, None if absent. Refuses symlinks and real paths outside the root."""
    cur = root
    for part in rel.split("/"):
        cur = cur / part
        if cur.is_symlink():
            raise VaultError("bad_asset_path")
    if not cur.exists():
        return None
    try:
        cur.resolve(strict=True).relative_to(root.resolve())
    except (OSError, RuntimeError, ValueError):
        raise VaultError("bad_asset_path") from None
    return cur if cur.is_file() else None


def resolve_asset(target: str, from_note: str = "") -> dict:
    root, _ = require_config()
    if not isinstance(target, str):
        raise VaultError("bad_asset_path")
    name = unquote(target.split("|", 1)[0].split("#", 1)[0].strip()).strip()
    if name.startswith("<") and name.endswith(">"):
        name = name[1:-1].strip()
    if not name or "\\" in name or "\x00" in name or name.startswith("/"):
        raise VaultError("bad_asset_path")
    parts = name.split("/")
    if _hidden_or_odd(parts):
        raise VaultError("bad_asset_path")
    last = parts[-1]
    ext = last.rsplit(".", 1)[-1].lower() if "." in last else ""
    if ext not in IMAGE_MIME:
        raise VaultError("not_image", 415)
    note_parts = from_note.split("/")[:-1] if isinstance(from_note, str) and "\\" not in from_note else []
    folder = "" if _hidden_or_odd(note_parts) else "/".join(note_parts)
    if len(parts) > 1:
        candidates = ([f"{folder}/{name}"] if folder else []) + [name]
    else:
        candidates = sorted(_asset_map(root).get(name, []),
                            key=lambda r: (0 if r.rpartition("/")[0] == folder else 1, r.count("/"), r))
    path, rel = None, ""
    for rel in candidates:
        path = _asset_file(root, rel)
        if path is not None:
            break
    if path is None:
        raise VaultError("asset_not_found", 404)
    try:
        if path.stat().st_size > MAX_ASSET_BYTES:
            raise VaultError("asset_too_large", 413)
        data = path.read_bytes()
    except OSError:
        raise VaultError("asset_not_found", 404) from None
    if len(data) > MAX_ASSET_BYTES:
        raise VaultError("asset_too_large", 413)
    return {"path": rel, "mime": IMAGE_MIME[ext], "data": base64.b64encode(data).decode("ascii"), "size": len(data)}


def status() -> dict:
    cfg = load_config()
    exists = db_path().exists()
    count, indexed = 0, None
    if exists:
        conn = _connect(False)
        if conn:
            try:
                count = conn.execute("SELECT count(*) FROM notes").fetchone()[0]
                row = conn.execute("SELECT value FROM meta WHERE key='indexed_at'").fetchone()
                indexed = row[0] if row else None
            except sqlite3.Error:
                pass
            finally: conn.close()
    return {"configured": cfg is not None, "root": cfg["root"] if cfg else None, "notes": count,
            "indexed_at": indexed, "index_exists": exists,
            "exclude": cfg["exclude"] if cfg else [],
            "attention_field": cfg["attention_field"] if cfg else None,
            "inbox_folder": cfg["inbox_folder"] if cfg else None,
            "locale": cfg["locale"] if cfg else "auto",
            "tasks": cfg["tasks"] if cfg else _normalize_tasks(None),
            "attention_tag": cfg["attention_tag"] if cfg else None}


def _row_note(row: sqlite3.Row) -> dict:
    return {"path": row["path"], "title": row["title"], "folder": row["folder"], "mtime_ns": row["mtime_ns"], "size": row["size"], "tags": json.loads(row["tags"]), "props": json.loads(row["props"])}


def tree(path: str = "") -> dict:
    root, excluded = require_config()
    if path:
        _validate(path, root=root, exclude=excluded)
    folder = path
    conn = _connect(False)
    if conn is None:
        return {"folders": [], "notes": []}
    try:
        prefix = folder + "/" if folder else ""
        rows = conn.execute("SELECT * FROM notes WHERE folder=? OR path LIKE ?", (folder, prefix+"%"))
        folders: dict[str, int] = {}
        notes = []
        for row in rows:
            rel = row["path"][len(prefix):]
            if "/" in rel:
                name = rel.split("/",1)[0]
                folders[name] = folders.get(name,0)+1
            elif row["folder"] == folder:
                notes.append({"path": row["path"], "title": row["title"], "mtime_ns": row["mtime_ns"], "tags": json.loads(row["tags"])})
        return {"folders": [{"name": n,"path": f"{prefix}{n}","note_count": c} for n,c in sorted(folders.items())], "notes": sorted(notes,key=lambda x:x["title"].lower())}
    finally: conn.close()


def list_notes(folder: str = "", tag: str = "", sort: str = "mtime", limit: int = 100, offset: int = 0) -> list[dict]:
    root, excluded = require_config()
    if folder: _validate(folder, root=root, exclude=excluded)
    if sort not in {"mtime", "title"}: raise VaultError("bad_sort")
    conn = _connect(False)
    if conn is None: return []
    try:
        conn.create_function("casefold",1,lambda value: str(value or "").casefold(),deterministic=True)
        filters=[]
        params=[]
        if folder:
            filters.append("folder=?")
            params.append(folder)
        if tag:
            filters.append("EXISTS (SELECT 1 FROM json_each(notes.tags) WHERE json_each.value=?)")
            params.append(tag)
        where=" WHERE "+" AND ".join(filters) if filters else ""
        order="casefold(title) ASC,path ASC" if sort=="title" else "mtime_ns DESC,path ASC"
        rows=conn.execute(f"SELECT * FROM notes{where} ORDER BY {order} LIMIT ? OFFSET ?",(*params,limit,offset)).fetchall()
        return [_row_note(row) for row in rows]
    finally: conn.close()


def search(q: str, limit: int = 50) -> list[dict]:
    require_config()
    conn = _connect(False)
    if conn is None or not q: return []
    try:
        if len(q) >= 3:
            fts_query='"'+q.replace('"','""')+'"'
            rows = conn.execute("SELECT n.path,n.title,snippet(notes_fts,2,'<b>','</b>','…',12) snippet FROM notes_fts JOIN notes n ON n.path=notes_fts.path WHERE notes_fts MATCH ? LIMIT ?", (fts_query,limit)).fetchall()
        else:
            pat = "%"+q+"%"
            rows = conn.execute("SELECT path,title,substr(body,1,240) snippet FROM notes_fts WHERE title LIKE ? OR body LIKE ? LIMIT ?", (pat,pat,limit)).fetchall()
        return [dict(r) for r in rows]
    finally: conn.close()


def _disk_links(root: Path, excluded: list[str], source: str) -> tuple[list[str], list[str]]:
    files = list(_walk(root, excluded))
    paths = {rel for _, rel in files}
    by_base: dict[str, list[str]] = {}
    for rel in paths:
        by_base.setdefault(Path(rel).stem, []).append(rel)
    links: list[str] = []
    backlinks: list[str] = []
    for p, rel in files:
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        resolved = [_resolve_link(raw, rel, paths, by_base) for raw in _note_data(rel, content)["links"]]
        if rel == source:
            links = [target for target in resolved if target is not None]
        if source in resolved:
            backlinks.append(rel)
    return links, backlinks


def read_note(path: str) -> dict:
    root, excluded = require_config()
    p = _validate(path,note=True,root=root,exclude=excluded)
    try: content = p.read_text(encoding="utf-8")
    except FileNotFoundError: raise VaultError("not_found",404) from None
    except UnicodeDecodeError: raise VaultError("not_text",415) from None
    st = p.stat(); data = _note_data(path,content); sha = hashlib.sha256(p.read_bytes()).hexdigest()
    conn = _connect(False); links=[]; backlinks=[]
    if conn:
        try:
            links=[r[0] for r in conn.execute("SELECT target FROM links WHERE src=? AND target IS NOT NULL",(path,))]
            backlinks=[r[0] for r in conn.execute("SELECT src FROM links WHERE target=?",(path,))]
        finally: conn.close()
    else:
        links, backlinks = _disk_links(root, excluded, path)
    return {"path":path,"title":data["title"],"content":content,"mtime_ns":st.st_mtime_ns,"size":st.st_size,"sha256":sha,"tags":data["tags"],"props":data["props"],"links":links,"backlinks":backlinks}


def _update_one(path: str, p: Path, content: str) -> None:
    with _LOCK:
        conn=_connect(); assert conn
        try:
            if _schema(conn):
                conn.close()
                refresh()
                return
            st=p.stat(); data=_note_data(path,content)
            conn.execute("INSERT OR REPLACE INTO notes(path,title,folder,mtime_ns,size,tags,props,raw_links) VALUES(?,?,?,?,?,?,?,?)",(path,data["title"],str(Path(path).parent) if "/" in path else "",st.st_mtime_ns,st.st_size,json.dumps(data["tags"],ensure_ascii=False),json.dumps(data["props"],ensure_ascii=False),json.dumps(data["links"],ensure_ascii=False)))
            conn.execute("DELETE FROM notes_fts WHERE path=?",(path,)); conn.execute("INSERT INTO notes_fts VALUES(?,?,?)",(path,data["title"],data["body"]))
            _store_checkboxes(conn,path,content,data)
            _rebuild_links(conn); _rebuild_note_tasks(conn,(load_config() or {}).get("tasks") or _normalize_tasks(None)); conn.commit()
        finally: conn.close()


def save_note(path: str, content: str, base_sha256: str) -> dict:
    root, excluded=require_config(); p=_validate(path,note=True,root=root,exclude=excluded)
    if not p.is_file(): raise VaultError("not_found",404)
    current=p.read_bytes(); sha=hashlib.sha256(current).hexdigest()
    if sha != base_sha256:
        st=p.stat(); raise VaultError("conflict",409,{"disk":{"content":current.decode("utf-8",errors="replace"),"sha256":sha,"mtime_ns":st.st_mtime_ns}})
    mode=p.stat().st_mode
    fd,tmp=tempfile.mkstemp(prefix=".hermes-lectern-",dir=p.parent)
    try:
        with os.fdopen(fd,"wb") as f: f.write(content.encode("utf-8")); f.flush(); os.fsync(f.fileno())
        os.chmod(tmp,mode); os.replace(tmp,p)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
    _update_one(path,p,content)
    raw=p.read_bytes(); return {"sha256":hashlib.sha256(raw).hexdigest(),"mtime_ns":p.stat().st_mtime_ns,"size":len(raw)}


def create_note(path: str, content: str) -> dict:
    root, excluded=require_config(); p=_validate(path,note=True,root=root,exclude=excluded)
    p.parent.mkdir(parents=True,exist_ok=True)
    try:
        fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o644)
    except FileExistsError: raise VaultError("exists",409) from None
    with os.fdopen(fd,"wb") as f: f.write(content.encode("utf-8")); f.flush(); os.fsync(f.fileno())
    _update_one(path,p,content)
    raw=p.read_bytes(); return {"sha256":hashlib.sha256(raw).hexdigest(),"mtime_ns":p.stat().st_mtime_ns,"size":len(raw)}


def _task_state(kind: str, status: str | None) -> str:
    """progress | waiting | done | open. Checkbox statuses are already normalised; note statuses use the free-form vocabulary."""
    if kind == "checkbox":
        return "progress" if status == "in-progress" else "open"
    s = (status or "").strip().lower()
    if s in IN_PROGRESS_STATUSES: return "progress"
    if s in WAITING_STATUSES: return "waiting"
    if s in DONE_STATUSES: return "done"
    return "open"


def dashboard() -> dict:
    root, excluded = require_config()
    cfg = load_config() or {}
    attention_field, inbox_folder = cfg.get("attention_field"), cfg.get("inbox_folder")
    tag_cfg = cfg.get("attention_tag"); attention_tag = _normalize_tag(tag_cfg) if tag_cfg else None
    boxes_on = bool(((cfg.get("tasks") or {}).get("checkboxes") or {}).get("enabled", True))
    sections = {"attention": bool(attention_field or attention_tag)}
    conn=_connect(False)
    if conn is None: return {"attention":[],"due":[],"in_progress":{},"recent":[],"inbox":[],"sections":sections,"counts":{"notes":0,"tasks":0,"tasknotes":0,"truncated":False}}
    try:
        try: task_rows=conn.execute("SELECT t.*,n.title AS ntitle,n.folder AS nfolder,n.mtime_ns AS nmtime,n.size AS nsize,n.tags AS ntags,n.props AS nprops FROM tasks t JOIN notes n ON n.path=t.path ORDER BY t.path,COALESCE(t.line,0)").fetchall()
        except sqlite3.OperationalError: task_rows=[]  # index from before 0.5: the next refresh builds the tasks table
        today=date.today(); horizon=today+timedelta(days=7)
        needs=[]; due=[]; projects:dict[str,list]={}; total=0; boxes=0
        for r in task_rows:
            kind=r["kind"]
            if kind=="checkbox":
                boxes+=1
                if not boxes_on: continue
            state=_task_state(kind,r["status"])
            if state=="done": continue
            total+=1
            labels=json.loads(r["project"] or "[]"); tags=json.loads(r["tags"] or "[]")
            if kind=="note":
                props=json.loads(r["nprops"]); raw=props.get("projects")
                if raw in (None,"",[]): raw=props.get("project")
                if raw not in (None,"",[]): props["projects"]=raw if isinstance(raw,list) else [raw]
                item={"kind":"note","path":r["path"],"title":r["ntitle"],"folder":r["nfolder"],"mtime_ns":r["nmtime"],"size":r["nsize"],"tags":json.loads(r["ntags"]),"props":{**props,"status":r["status"],"due":r["due"]}}
                if attention_field and props.get(attention_field) and state=="waiting": needs.append(item)
            else:
                item={"kind":"checkbox","path":r["path"],"title":r["text"],"note_title":r["ntitle"],"line":r["line"],"folder":r["nfolder"],"mtime_ns":r["nmtime"],"size":r["nsize"],"tags":tags,"props":{"status":r["status"],"due":r["due"],"projects":labels}}
                if attention_tag and attention_tag in {str(t).casefold() for t in tags}: needs.append(item)
            if r["due"]:
                d=date.fromisoformat(r["due"])
                if d<=horizon: due.append({**item,"overdue":d<today})
            if state=="progress":
                for label in labels or [""]: projects.setdefault(label,[]).append(item)
        due.sort(key=lambda i:(i["props"]["due"],i["path"],i.get("line") or 0))
        note_task_paths={r["path"] for r in task_rows if r["kind"]=="note"}
        count=0; recent=[]; inbox=[]
        for row in conn.execute("SELECT * FROM notes ORDER BY mtime_ns DESC,path ASC"):
            count+=1
            if len(recent)<30 and row["path"] not in note_task_paths: recent.append(_row_note(row))
            if inbox_folder and row["path"].startswith(inbox_folder + "/"): inbox.append(_row_note(row))
        return {"attention":needs,"due":due,"in_progress":projects,"recent":recent,"inbox":inbox,
                "sections":sections,"counts":{"notes":count,"tasks":total,"tasknotes":total,"truncated":boxes_on and boxes>=MAX_CHECKBOX_TASKS}}
    finally: conn.close()

