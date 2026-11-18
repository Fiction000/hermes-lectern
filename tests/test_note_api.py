import importlib.util
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from test_paths_frontmatter import core

API_PATH = Path(__file__).parents[1] / "dashboard" / "plugin_api.py"
spec = importlib.util.spec_from_file_location("vault_api_test", API_PATH)
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)
app = FastAPI(); app.include_router(api.router, prefix="/api/plugins/hermes-lectern")
client = TestClient(app)


@pytest.fixture
def setup_vault(tmp_path, monkeypatch):
    home=tmp_path/"home"; root=tmp_path/"vault"; root.mkdir(); (root/".obsidian").mkdir()
    monkeypatch.setenv("HERMES_HOME",str(home))
    response=client.put("/api/plugins/hermes-lectern/config",json={"root":str(root), "inbox_folder":"Inbox"})
    assert response.status_code == 200
    return home,root


def test_note_read_conflict_atomic_save_and_create(setup_vault):
    home,root=setup_vault
    raw="---\ntags: [topic/test]\n---\n# old\n"
    (root/"old.md").write_text(raw)
    assert client.get("/api/plugins/hermes-lectern/note",params={"path":"old.md"}).status_code == 200
    conflict=client.put("/api/plugins/hermes-lectern/note",json={"path":"old.md","content":"overwrite","base_sha256":"0"*64})
    assert conflict.status_code == 409 and conflict.json()["error"] == "conflict"
    assert conflict.json()["disk"]["content"] == raw and (root/"old.md").read_text() == raw
    sha=client.get("/api/plugins/hermes-lectern/note",params={"path":"old.md"}).json()["sha256"]
    content="---\ntags: [topic/test]\n---\n# exact 🐦\r\n"
    saved=client.put("/api/plugins/hermes-lectern/note",json={"path":"old.md","content":content,"base_sha256":sha})
    assert saved.status_code == 200 and (root/"old.md").read_bytes() == content.encode()
    assert client.post("/api/plugins/hermes-lectern/refresh").json()["unchanged"] == 1
    assert client.get("/api/plugins/hermes-lectern/search",params={"q":"exact"}).json()[0]["path"] == "old.md"
    created=client.post("/api/plugins/hermes-lectern/note",json={"path":"new/deep/note.md","content":"# new"})
    assert created.status_code == 200 and (root/"new/deep/note.md").read_text() == "# new"
    duplicate=client.post("/api/plugins/hermes-lectern/note",json={"path":"new/deep/note.md","content":"# no"})
    assert duplicate.status_code == 409 and duplicate.json()["error"] == "exists"


def test_symlink_escape_rejected_for_all_mutating_and_read_routes(setup_vault,tmp_path):
    _,root=setup_vault
    outside=tmp_path/"outside"; outside.mkdir(); (outside/"secret.md").write_text("outside")
    (root/"file.md").symlink_to(outside/"secret.md")
    (root/"dir").symlink_to(outside, target_is_directory=True)
    (root/"dangling.md").symlink_to(outside/"missing.md")
    (root/"dangling_dir").symlink_to(outside/"missing", target_is_directory=True)
    for path in ("file.md","dir/secret.md","dir/new.md","dangling.md","dangling_dir/new.md"):
        assert client.get("/api/plugins/hermes-lectern/note",params={"path":path}).status_code == 400,path
        assert client.put("/api/plugins/hermes-lectern/note",json={"path":path,"content":"x","base_sha256":"x"}).status_code == 400,path
        assert client.post("/api/plugins/hermes-lectern/note",json={"path":path,"content":"x"}).status_code == 400,path
        assert client.post("/api/plugins/hermes-lectern/note/trash",json={"path":path}).status_code == 400,path
    assert (outside/"secret.md").read_text() == "outside"


def test_rejections_and_nested_create(setup_vault):
    _,root=setup_vault
    for path in ("../bad.md","folder/../inside.md",".private.md","folder/.secret.md","Attachments/no.md","a\\b.md","/absolute.md","bad.txt"):
        assert client.get("/api/plugins/hermes-lectern/note",params={"path":path}).status_code == 400
        assert client.post("/api/plugins/hermes-lectern/note",json={"path":path,"content":"x"}).status_code == 400
    assert client.post("/api/plugins/hermes-lectern/note",json={"path":"safe/nested/ok.md","content":"# ok"}).status_code == 200


def test_trash_unique_and_recoverable(setup_vault):
    _,root=setup_vault; trash=root/".trash"; trash.mkdir()
    prior=trash/"item.md"; prior.write_text("do not overwrite")
    note=root/"item.md"; note.write_text("# recover me")
    response=client.post("/api/plugins/hermes-lectern/note/trash",json={"path":"item.md"})
    assert response.status_code == 200
    moved=root/response.json()["trashed"]
    assert moved.read_text() == "# recover me" and prior.read_text() == "do not overwrite" and not note.exists()


def test_trash_rejects_unsafe_trash_directory(setup_vault,tmp_path):
    _,root=setup_vault
    outside=tmp_path/"outside"; outside.mkdir()
    (root/".trash").symlink_to(outside,target_is_directory=True)
    note=root/"keep.md"; note.write_text("# safe")
    response=client.post("/api/plugins/hermes-lectern/note/trash",json={"path":"keep.md"})
    assert response.status_code == 409 and response.json()["error"] == "trash_unavailable"
    assert note.read_text() == "# safe" and list(outside.iterdir()) == []


def test_get_routes_on_fresh_home_do_not_write(tmp_path,monkeypatch):
    home=tmp_path/"fresh"; home.mkdir(); monkeypatch.setenv("HERMES_HOME",str(home))
    before=sorted(str(p.relative_to(home)) for p in home.rglob("*"))
    assert client.get("/api/plugins/hermes-lectern/status").status_code == 200
    for url in ("/tree","/notes","/search","/dashboard","/note?path=x.md"):
        assert client.get("/api/plugins/hermes-lectern"+url).status_code == 409
    assert sorted(str(p.relative_to(home)) for p in home.rglob("*")) == before


def test_public_router_dashboard_tree_search_and_cold_gets(setup_vault):
    home,root=setup_vault
    (root/"folder").mkdir()
    (root/"folder"/"日本語.md").write_text("---\ntags: [tasknote]\nstatus: open\ndue: "+(date.today()-timedelta(days=1)).isoformat()+"\n---\n# 日本語検索")
    (root/"Inbox").mkdir(); (root/"Inbox"/"inbox.md").write_text("# Inbox")
    before=sorted(str(p.relative_to(home)) for p in home.rglob("*"))
    assert client.get("/api/plugins/hermes-lectern/status").json()["index_exists"] is False
    assert client.get("/api/plugins/hermes-lectern/tree").json() == {"folders":[],"notes":[]}
    assert client.get("/api/plugins/hermes-lectern/notes").json() == []
    assert client.get("/api/plugins/hermes-lectern/search",params={"q":"日本語"}).json() == []
    assert client.get("/api/plugins/hermes-lectern/dashboard").json()["counts"]["notes"] == 0
    assert sorted(str(p.relative_to(home)) for p in home.rglob("*")) == before
    assert client.post("/api/plugins/hermes-lectern/refresh").status_code == 200
    assert client.get("/api/plugins/hermes-lectern/tree").json()["folders"][0]["name"] == "Inbox"
    assert client.get("/api/plugins/hermes-lectern/tree",params={"path":"folder"}).json()["notes"][0]["path"] == "folder/日本語.md"
    assert client.get("/api/plugins/hermes-lectern/search",params={"q":"日本語検索"}).json()[0]["path"] == "folder/日本語.md"
    dashboard=client.get("/api/plugins/hermes-lectern/dashboard").json()
    assert dashboard["due"][0]["overdue"] is True and dashboard["inbox"][0]["path"] == "Inbox/inbox.md"


def test_note_links_are_read_from_disk_before_refresh(setup_vault):
    home,root=setup_vault
    (root/"source.md").write_text("[[target|alias]]")
    (root/"target.md").write_text("# Target")
    before=sorted(str(p.relative_to(home)) for p in home.rglob("*"))
    source=client.get("/api/plugins/hermes-lectern/note",params={"path":"source.md"}).json()
    target=client.get("/api/plugins/hermes-lectern/note",params={"path":"target.md"}).json()
    assert source["links"] == ["target.md"] and target["backlinks"] == ["source.md"]
    assert sorted(str(p.relative_to(home)) for p in home.rglob("*")) == before


def test_search_treats_fts_queries_as_literal_text_through_rest(setup_vault):
    _,root=setup_vault
    (root/"literal.md").write_text('# Literal\nHermes-vault a:b AND (test; He said "yes".')
    assert client.post("/api/plugins/hermes-lectern/refresh").status_code == 200
    for query in ("Hermes-vault", "a:b", "AND", "(test", 'He said "yes"'):
        response=client.get("/api/plugins/hermes-lectern/search",params={"q":query})
        assert response.status_code == 200, (query,response.text)
        assert isinstance(response.json(),list)
    found=client.get("/api/plugins/hermes-lectern/search",params={"q":"Hermes-vault"}).json()
    assert any(row["path"] == "literal.md" for row in found)
    quoted=client.get("/api/plugins/hermes-lectern/search",params={"q":'He said "yes"'}).json()
    assert any(row["path"] == "literal.md" for row in quoted)


def test_notes_sort_by_casefolded_title_and_apply_folder_window(setup_vault):
    _,root=setup_vault
    folder=root/"group"; folder.mkdir()
    values=(("z.md","zeta",100),("a.md","Alpha",200),("b.md","beta",300))
    for filename,title,timestamp in values:
        path=folder/filename
        path.write_text(f"---\ntags: [topic/keep]\n---\n# {title}")
        import os
        os.utime(path,ns=(timestamp,timestamp))
    other=root/"elsewhere.md"; other.write_text("# Other")
    assert client.post("/api/plugins/hermes-lectern/refresh").status_code == 200
    response=client.get("/api/plugins/hermes-lectern/notes",params={"folder":"group","sort":"title","tag":"topic/keep","limit":1,"offset":1})
    assert response.status_code == 200
    assert [row["title"] for row in response.json()] == ["beta"]
    newest=client.get("/api/plugins/hermes-lectern/notes",params={"folder":"group","sort":"mtime","limit":2})
    assert [row["title"] for row in newest.json()] == ["beta","Alpha"]


def test_read_non_utf8_note_returns_415_without_writing(setup_vault):
    home,root=setup_vault
    note=root/"binary.md"; raw=b"#\xff\xfe"
    note.write_bytes(raw)
    before=sorted(str(path.relative_to(home)) for path in home.rglob("*"))
    response=client.get("/api/plugins/hermes-lectern/note",params={"path":"binary.md"})
    assert response.status_code == 415 and response.json() == {"error":"not_text"}
    assert note.read_bytes() == raw
    assert sorted(str(path.relative_to(home)) for path in home.rglob("*")) == before


def test_get_does_not_migrate_a_legacy_index(setup_vault):
    home,_=setup_vault
    db_path=home/"hermes-lectern"/"index.sqlite"
    conn=sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE notes(path TEXT PRIMARY KEY,title TEXT,folder TEXT,mtime_ns INTEGER,size INTEGER,tags TEXT,props TEXT,body TEXT);
        CREATE TABLE links(src TEXT,raw TEXT,target TEXT);
        CREATE VIRTUAL TABLE notes_fts USING fts5(path UNINDEXED,title,body,tokenize='trigram');
        CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);
        INSERT INTO notes VALUES('legacy.md','legacy','',0,0,'[]','{}','legacy body');
        INSERT INTO notes_fts VALUES('legacy.md','legacy','legacy body');
        INSERT INTO meta VALUES('indexed_at','old');
    """)
    conn.close()
    before=db_path.read_bytes()
    assert client.get("/api/plugins/hermes-lectern/status").json()["notes"] == 1
    assert client.get("/api/plugins/hermes-lectern/search",params={"q":"legacy"}).status_code == 200
    assert db_path.read_bytes() == before
    conn=sqlite3.connect(db_path)
    try:
        assert "body" in {row[1] for row in conn.execute("PRAGMA table_info(notes)")}
        assert conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone() is None
    finally: conn.close()
