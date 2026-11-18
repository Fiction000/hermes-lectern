import json
import os
import sqlite3
import threading
from pathlib import Path

import pytest

from test_paths_frontmatter import core


@pytest.fixture
def vault(tmp_path, monkeypatch):
    home = tmp_path / "home"
    root = tmp_path / "vault"
    root.mkdir(); (root / ".obsidian").mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    core.configure(str(root))
    return root


def test_incremental_refresh_and_links(vault):
    (vault / "甲.md").write_text("---\ntitle: 甲\n---\n[[子|alias]] [[子#見出し]] [[Ambiguous]]")
    (vault / "子.md").write_text("# 子")
    (vault / "one").mkdir(); (vault / "two").mkdir()
    (vault / "one" / "Ambiguous.md").write_text("# a")
    (vault / "two" / "Ambiguous.md").write_text("# b")
    (vault / ".hidden").mkdir(); (vault / ".hidden" / "secret.md").write_text("secret")
    (vault / "Attachments").mkdir(); (vault / "Attachments" / "skip.md").write_text("skip")
    first = core.refresh()
    assert first["added"] == 4
    conn = core._connect(False)
    try:
        targets = [r[0] for r in conn.execute("SELECT target FROM links WHERE src='甲.md'")]
        assert targets == ["子.md", "子.md", None]
    finally: conn.close()
    assert first["removed"] == 0
    second = core.refresh()
    assert second["unchanged"] == 4 and second["added"] == 0 and second["updated"] == 0
    (vault / "子.md").write_text("# 子\nchanged")
    assert core.refresh()["updated"] == 1
    (vault / "子.md").unlink()
    assert core.refresh()["removed"] == 1
    db = core._connect(False)
    try:
        rows = list(db.execute("SELECT raw,target FROM links WHERE src='甲.md'"))
        assert [(r["raw"],r["target"]) for r in rows] == [("子|alias",None),("子#見出し",None),("Ambiguous",None)]
    finally: db.close()


def test_unique_basename_resolves(vault):
    (vault / "foo.md").write_text("# Foo")
    (vault / "from.md").write_text("[[foo|alias]]")
    core.refresh()
    conn=core._connect(False)
    try: assert conn.execute("SELECT target FROM links WHERE src='from.md'").fetchone()[0] == "foo.md"
    finally: conn.close()


def test_refresh_migrates_legacy_index_and_stores_only_raw_links(vault):
    (vault/"source.md").write_text("---\ntags: [topic/search]\n---\n[[target]] 日本語検索")
    (vault/"target.md").write_text("# target")
    db_path=core.db_path(); db_path.parent.mkdir(parents=True,exist_ok=True)
    conn=sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE notes(path TEXT PRIMARY KEY,title TEXT,folder TEXT,mtime_ns INTEGER,size INTEGER,tags TEXT,props TEXT,body TEXT);
        CREATE TABLE links(src TEXT,raw TEXT,target TEXT);
        CREATE VIRTUAL TABLE notes_fts USING fts5(path UNINDEXED,title,body,tokenize='trigram');
        CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);
        INSERT INTO notes VALUES('stale.md','stale','',0,0,'[]','{}','stale body');
        INSERT INTO notes_fts VALUES('stale.md','stale','stale body');
        INSERT INTO meta VALUES('indexed_at','old');
    """)
    conn.close()
    result=core.refresh()
    assert result["added"] == 2 and result["removed"] == 0
    conn=sqlite3.connect(db_path); conn.row_factory=sqlite3.Row
    try:
        columns={row["name"] for row in conn.execute("PRAGMA table_info(notes)")}
        assert "body" not in columns and "raw_links" in columns
        assert conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0] == core.SCHEMA_VERSION
        assert conn.execute("SELECT path FROM notes WHERE path='stale.md'").fetchone() is None
        stored=json.loads(conn.execute("SELECT raw_links FROM notes WHERE path='source.md'").fetchone()[0])
        assert stored == ["target"]
        assert conn.execute("SELECT target FROM links WHERE src='source.md'").fetchone()[0] == "target.md"
        assert conn.execute("SELECT body FROM notes_fts WHERE path='source.md'").fetchone()[0].endswith("日本語検索")
    finally: conn.close()
    assert core.search("日本語",20)[0]["path"] == "source.md"


def test_single_note_update_waits_for_active_refresh(vault,monkeypatch):
    note=vault/"race.md"; note.write_text("# old content")
    core.refresh()
    content="# new race marker"
    note.write_text(content)
    original_walk=core._walk
    walking=threading.Event(); resume=threading.Event(); updated=threading.Event()
    errors=[]
    def paused_walk(root,excluded):
        walking.set()
        if not resume.wait(3): raise AssertionError("refresh was not released")
        yield from original_walk(root,excluded)
    monkeypatch.setattr(core,"_walk",paused_walk)
    def refresh_call():
        try: core.refresh()
        except BaseException as error: errors.append(error)
    def update_call():
        try:
            core._update_one("race.md",note,content)
            updated.set()
        except BaseException as error: errors.append(error)
    refresh_thread=threading.Thread(target=refresh_call)
    refresh_thread.start()
    assert walking.wait(3)
    update_thread=threading.Thread(target=update_call)
    update_thread.start()
    blocked=not updated.wait(0.1)
    resume.set()
    refresh_thread.join(3); update_thread.join(3)
    assert blocked
    assert not refresh_thread.is_alive() and not update_thread.is_alive()
    assert errors == []
    assert updated.is_set()
    assert core.search("race marker",20)[0]["path"] == "race.md"


def test_symlinked_notes_pointing_outside_are_not_indexed(vault, tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_text("---\ntitle: secret\n---\nleaked-body-text")
    os.symlink(outside, vault / "link.md")
    (vault / "real.md").write_text("# real")
    core.refresh()
    paths = {n["path"] for n in core.list_notes()}
    assert "real.md" in paths and "link.md" not in paths
    assert core.search("leaked") == []
