from datetime import date, timedelta

from test_index_refresh import vault
from test_paths_frontmatter import core


def test_japanese_search_tree_and_notes(vault):
    (vault/"folder").mkdir()
    (vault/"folder"/"検索対象.md").write_text("---\ntags: [topic/japanese]\n---\n# 日本語検索\nこれは二文字と四文字の検索テストです")
    (vault/"folder"/"other.md").write_text("# Other")
    core.refresh()
    assert core.search("検索",20)[0]["path"] == "folder/検索対象.md"
    assert core.search("日本語検",20)[0]["path"] == "folder/検索対象.md"
    row=core.tree("folder")
    assert row["folders"] == [] and len(row["notes"]) == 2
    assert core.list_notes("folder",tag="topic/japanese")[0]["path"] == "folder/検索対象.md"


def test_dashboard_rules_and_overdue(vault):
    past=(date.today()-timedelta(days=1)).isoformat()
    near=(date.today()+timedelta(days=7)).isoformat()
    later=(date.today()+timedelta(days=8)).isoformat()
    def task(name,status,due="",needs=False,projects='"[[Projects/Reader]]"'):
        props=f"status: {status}\n"
        if due: props+=f"due: {due}\n"
        if needs: props+="needs_me: true\n"
        return f"---\ntags: [tasknote]\n{props}projects: [{projects}]\n---\n# {name}"
    (vault/"wait.md").write_text(task("wait","waiting",past,True))
    (vault/"blocked.md").write_text(task("blocked","blocked",near,True))
    (vault/"open.md").write_text(task("open","open",near))
    (vault/"later.md").write_text(task("later","open",later))
    (vault/"done.md").write_text(task("done","done",past,True))
    (vault/"ordinary.md").write_text("# ordinary")
    (vault/"Inbox").mkdir(); (vault/"Inbox"/"inbox.md").write_text("# inbox")
    core.configure(str(vault), attention_field="needs_me", inbox_folder="Inbox")
    core.refresh(); data=core.dashboard()
    assert {n["path"] for n in data["attention"]} == {"wait.md","blocked.md"}
    due={n["path"]:n["overdue"] for n in data["due"]}
    assert due == {"wait.md":True,"blocked.md":False,"open.md":False}
    assert set(data["in_progress"]) == {"Projects/Reader"}
    assert {n["path"] for n in data["in_progress"]["Projects/Reader"]} == {"open.md","later.md"}
    assert {n["path"] for n in data["recent"]} == {"ordinary.md","Inbox/inbox.md"}
    assert data["inbox"][0]["path"] == "Inbox/inbox.md"
    assert data["counts"] == {"notes":7,"tasks":4,"tasknotes":4,"truncated":False}  # open tasks only; done.md no longer counts
