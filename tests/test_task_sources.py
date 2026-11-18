import json
import sqlite3
from datetime import date, timedelta

import pytest

from test_index_refresh import vault  # noqa: F401  (fixture)
from test_paths_frontmatter import core


def iso(days):
    return (date.today() + timedelta(days=days)).isoformat()


def write(vault, rel, text):
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def run(vault, **options):
    core.configure(str(vault), **options)
    core.refresh()
    return core.dashboard()


def paths(items):
    return sorted(i["path"] for i in items)


def texts(items):
    return sorted(i["title"] for i in items)


# --- Part 1: trash endpoint is gone -------------------------------------------------

def test_trash_route_is_gone(vault):
    from test_note_api import client
    (vault / "item.md").write_text("# keep")
    response = client.post("/api/plugins/hermes-lectern/note/trash", json={"path": "item.md"})
    assert response.status_code in (404, 405)
    assert (vault / "item.md").exists()
    assert not hasattr(core, "trash_note") and not hasattr(core, "_trash_note_locked")


# --- config ----------------------------------------------------------------------------

def test_config_defaults_and_round_trip(vault):
    configured = core.configure(str(vault))
    assert configured["tasks"] == {"notes": {"enabled": True, "tag": "tasknote", "folder": None}, "checkboxes": {"enabled": True}}
    assert configured["attention_tag"] is None
    configured = core.configure(str(vault), tasks={"notes": {"tag": "#todo", "folder": "Tasks"}, "checkboxes": {"enabled": False}}, attention_tag="#Needs-Me")
    assert configured["tasks"] == {"notes": {"enabled": True, "tag": "todo", "folder": "Tasks"}, "checkboxes": {"enabled": False}}
    assert core.load_config() == configured
    status = core.status()
    assert status["tasks"] == configured["tasks"] and status["attention_tag"] == "#Needs-Me"


def test_config_rejects_bad_task_values(vault):
    for options, code in (({"tasks": "x"}, "bad_tasks_config"), ({"tasks": {"notes": {"enabled": "yes"}}}, "bad_tasks_config"),
                          ({"tasks": {"notes": {"tag": 3}}}, "bad_tasks_config"), ({"tasks": {"notes": {"folder": ""}}}, "bad_tasks_config"),
                          ({"tasks": {"checkboxes": {"enabled": 1}}}, "bad_tasks_config"), ({"tasks": {"other": {}}}, "bad_tasks_config"),
                          ({"attention_tag": 5}, "bad_attention_tag"), ({"attention_tag": ""}, "bad_attention_tag")):
        with pytest.raises(core.VaultError) as raised:
            core.configure(str(vault), **options)
        assert raised.value.code == code, options


def test_config_api_round_trips_tasks(vault):
    from test_note_api import client
    body = {"root": str(vault), "tasks": {"notes": {"tag": "todo"}}, "attention_tag": "needs-me"}
    response = client.put("/api/plugins/hermes-lectern/config", json=body)
    assert response.status_code == 200 and response.json()["tasks"]["notes"]["tag"] == "todo"
    assert response.json()["attention_tag"] == "needs-me"
    assert client.put("/api/plugins/hermes-lectern/config", json={"root": str(vault), "tasks": {"notes": {"enabled": "x"}}}).status_code == 400
    assert client.put("/api/plugins/hermes-lectern/config", json={"root": str(vault), "attention_tag": 7}).status_code == 422


# --- note tasks ------------------------------------------------------------------------

def test_legacy_config_keeps_tasknote_results_and_turns_checkboxes_on(vault):
    import json as _json
    write(vault, "TaskNotes/wait.md", "---\ntags: [tasknote]\nstatus: waiting\nneeds_review: true\ndue: " + iso(-1) + "\nprojects: ['[[Alpha|A]]']\n---\n# Wait")
    write(vault, "TaskNotes/block.md", "---\ntags: [tasknote]\nstatus: blocked\nneeds_review: true\n---\n# Block")
    write(vault, "TaskNotes/prog.md", "---\ntags: [tasknote]\nstatus: in-progress\nprojects:\n  - '[[Alpha]]'\n---\n# Prog")
    write(vault, "TaskNotes/open.md", "---\ntags: [tasknote]\nstatus: open\n---\n# Open")
    write(vault, "TaskNotes/done.md", "---\ntags: [tasknote]\nstatus: done\ndue: " + iso(-3) + "\n---\n# Done")
    write(vault, "TaskNotes/later.md", "---\ntags: [tasknote]\nstatus: open\ndue: " + iso(30) + "\n---\n# Later")
    write(vault, "plain.md", "# Plain\n- [ ] a checkbox 📅 " + iso(2) + "\n")
    core.config_path().write_text(_json.dumps({"root": str(vault), "attention_field": "needs_review", "inbox_folder": None, "locale": "en"}))
    core.refresh()
    out = core.dashboard()
    assert paths(out["attention"]) == ["TaskNotes/block.md", "TaskNotes/wait.md"]
    assert [i["path"] for i in out["due"] if i["kind"] == "note"] == ["TaskNotes/wait.md"]
    assert [i["overdue"] for i in out["due"] if i["path"] == "TaskNotes/wait.md"] == [True]
    assert sorted(out["in_progress"]) == ["", "Alpha"]
    assert paths(out["in_progress"]["Alpha"]) == ["TaskNotes/prog.md"]
    assert paths(out["in_progress"][""]) == ["TaskNotes/later.md", "TaskNotes/open.md"]
    assert out["sections"]["attention"] is True
    # a checkbox with a due date appears as a checkbox task, because checkboxes default on
    assert any(i["kind"] == "checkbox" and i["path"] == "plain.md" for i in out["due"])
    assert out["counts"]["tasks"] == out["counts"]["tasknotes"] == 6  # five open task notes plus one checkbox
    assert "TaskNotes/done.md" not in {i["path"] for i in out["recent"]} and "TaskNotes/open.md" not in {i["path"] for i in out["recent"]}
    assert "plain.md" in {i["path"] for i in out["recent"]}


def test_note_task_item_shape(vault):
    write(vault, "T/a.md", "---\ntags: [tasknote]\nstatus: waiting\nneeds_me: true\ndue: " + iso(1) + "T09:00\nprojects: '[[Alpha]]'\n---\n# Alpha task")
    out = run(vault, attention_field="needs_me")
    item = out["attention"][0]
    assert item["kind"] == "note" and item["path"] == "T/a.md" and item["title"] == "Alpha task"
    assert item["props"]["status"] == "waiting" and item["props"]["due"] == iso(1)
    assert item["props"]["projects"] == ["[[Alpha]]"]
    assert item.get("line") is None


def test_tag_change_changes_which_notes_are_tasks(vault):
    write(vault, "a.md", "---\ntags: [tasknote]\nstatus: open\n---\n# A")
    write(vault, "b.md", "---\ntags: [todo]\nstatus: open\n---\n# B")
    first = run(vault, tasks={"checkboxes": {"enabled": False}})
    assert paths(first["in_progress"][""]) == ["a.md"]
    second = run(vault, tasks={"notes": {"tag": "todo"}, "checkboxes": {"enabled": False}})
    assert paths(second["in_progress"][""]) == ["b.md"]
    # changing config without a refresh already takes effect on the next dashboard read
    core.configure(str(vault), tasks={"notes": {"tag": "tasknote"}, "checkboxes": {"enabled": False}})
    assert paths(core.dashboard()["in_progress"][""]) == ["a.md"]


def test_folder_based_note_tasks(vault):
    write(vault, "Tasks/x.md", "---\nstatus: doing\nprojects: [P]\n---\n# X")
    write(vault, "Tasks/sub/y.md", "---\nstatus: open\n---\n# Y")
    write(vault, "Tasksheet/z.md", "---\nstatus: open\n---\n# Z")
    write(vault, "other/t.md", "---\ntags: [tasknote]\nstatus: open\n---\n# T")
    out = run(vault, tasks={"notes": {"folder": "Tasks"}, "checkboxes": {"enabled": False}})
    assert paths(out["in_progress"]["P"]) == ["Tasks/x.md"]
    assert paths(out["in_progress"][""]) == ["Tasks/sub/y.md", "other/t.md"]
    assert out["counts"]["tasks"] == 3


def test_notes_source_can_be_disabled(vault):
    write(vault, "a.md", "---\ntags: [tasknote]\nstatus: open\n---\n# A")
    out = run(vault, tasks={"notes": {"enabled": False}, "checkboxes": {"enabled": False}})
    assert out["in_progress"] == {} and out["counts"]["tasks"] == 0


def test_status_vocabulary(vault):
    write(vault, "T/doing.md", "---\ntags: [tasknote]\nstatus: Doing\n---\n# doing")
    write(vault, "T/active.md", "---\ntags: [tasknote]\nstatus: active\n---\n# active")
    write(vault, "T/inprog.md", "---\ntags: [tasknote]\nstatus: in progress\n---\n# inprog")
    write(vault, "T/completed.md", "---\ntags: [tasknote]\nstatus: Completed\ndue: " + iso(-2) + "\n---\n# completed")
    write(vault, "T/cancelled.md", "---\ntags: [tasknote]\nstatus: cancelled\ndue: " + iso(-2) + "\n---\n# cancelled")
    write(vault, "T/complete.md", "---\ntags: [tasknote]\nstatus: complete\ndue: " + iso(-2) + "\n---\n# complete")
    write(vault, "T/todo.md", "---\ntags: [tasknote]\nstatus: todo\ndue: " + iso(-2) + "\n---\n# todo")
    out = run(vault, tasks={"checkboxes": {"enabled": False}})
    assert paths(out["in_progress"][""]) == ["T/active.md", "T/doing.md", "T/inprog.md"]
    assert paths(out["due"]) == ["T/todo.md"]  # done/completed/complete/cancelled never show as due
    assert out["counts"]["tasks"] == 4


# --- checkbox tasks --------------------------------------------------------------------

def test_checkbox_due_syntaxes(vault):
    write(vault, "n.md", "\n".join([
        "# Note",
        f"- [ ] emoji 📅 {iso(1)}",
        f"* [ ] inline [due:: {iso(2)}]",
        f"+ [ ] paren (due:: {iso(3)})",
        f"  - [ ] bare due:: {iso(4)} nested",
        "- [ ] no date",
        f"- [ ] far 📅 {iso(40)}",
        f"- [ ] late 📅 {iso(-1)}",
        "- [ ]not a task",
        "-[ ] not a task either",
    ]))
    out = run(vault)
    by = {i["title"].split(" ")[0]: i for i in out["due"]}
    assert set(by) == {"emoji", "inline", "paren", "bare", "late"}
    assert [by[k]["props"]["due"] for k in ("emoji", "inline", "paren", "bare")] == [iso(1), iso(2), iso(3), iso(4)]
    assert by["late"]["overdue"] is True and by["emoji"]["overdue"] is False
    assert by["emoji"]["kind"] == "checkbox" and by["emoji"]["path"] == "n.md" and by["emoji"]["line"] == 2
    assert by["bare"]["line"] == 5
    assert by["emoji"]["title"] == f"emoji 📅 {iso(1)}"
    assert out["counts"]["tasks"] == 7  # every open checkbox, dated or not


def test_checkbox_status_chars_done_and_cancelled_excluded(vault):
    write(vault, "n.md", "# Note\n- [ ] open\n- [/] doing\n- [x] done\n- [X] DONE\n- [-] cancelled\n- [?] question\n- [!] bang\n- [>] forwarded\n")
    out = run(vault)
    assert sorted(i["title"] for i in out["in_progress"]["Note"]) == ["doing"]
    assert out["counts"]["tasks"] == 5
    conn = core._connect(False)
    try:
        rows = {r["text"]: r["status"] for r in conn.execute("SELECT text,status FROM tasks WHERE kind='checkbox'")}
    finally:
        conn.close()
    assert rows == {"open": "open", "doing": "in-progress", "question": "open", "bang": "open", "forwarded": "open"}


def test_checkbox_in_progress_grouped_by_note_title_or_frontmatter_project(vault):
    write(vault, "plain.md", "# Plain title\n- [/] first\n")
    write(vault, "fm.md", "---\nproject: '[[Big Project|BP]]'\n---\n# Heading\n- [/] second\n")
    write(vault, "fm2.md", "---\nprojects: [A, B]\n---\n- [/] third\n")
    out = run(vault)
    assert texts(out["in_progress"]["Plain title"]) == ["first"]
    assert texts(out["in_progress"]["Big Project"]) == ["second"]
    assert texts(out["in_progress"]["A"]) == ["third"] and texts(out["in_progress"]["B"]) == ["third"]
    item = out["in_progress"]["Plain title"][0]
    assert item["note_title"] == "Plain title" and item["props"]["status"] == "in-progress"


def test_fenced_code_and_frontmatter_are_ignored(vault):
    write(vault, "n.md", "---\ntitle: T\nchecklist:\n  - [ ] not here\nnote: |\n- [ ] nor here\n---\n# T\n```\n- [ ] in fence\n```\n~~~md\n- [ ] in tilde fence\n~~~\n- [ ] real one\n````\n```\n- [ ] still fenced\n````\n- [ ] after fences\n")
    out = run(vault)
    conn = core._connect(False)
    try:
        rows = [(r["text"], r["line"]) for r in conn.execute("SELECT text,line FROM tasks WHERE kind='checkbox' ORDER BY line")]
    finally:
        conn.close()
    assert rows == [("real one", 15), ("after fences", 20)]
    assert out["counts"]["tasks"] == 2


def test_task_text_trimmed_and_tags_stored(vault):
    long = "x" * 300
    write(vault, "n.md", f"# N\n- [ ] {long} #a #B/c\n- [ ] short #needs-me 📅 {iso(1)}\n")
    run(vault)
    conn = core._connect(False)
    try:
        rows = list(conn.execute("SELECT text,tags FROM tasks WHERE kind='checkbox' ORDER BY line"))
    finally:
        conn.close()
    assert len(rows[0]["text"]) == 200
    assert json.loads(rows[1]["tags"]) == ["needs-me"]
    assert rows[1]["text"] == f"short #needs-me 📅 {iso(1)}"


def test_checkboxes_disabled_gives_no_checkbox_tasks(vault):
    write(vault, "n.md", f"# N\n- [/] doing 📅 {iso(1)} #needs-me\n")
    out = run(vault, tasks={"checkboxes": {"enabled": False}}, attention_tag="needs-me")
    assert out["due"] == [] and out["in_progress"] == {} and out["attention"] == [] and out["counts"]["tasks"] == 0
    out = run(vault, attention_tag="needs-me")
    assert len(out["due"]) == 1 and len(out["attention"]) == 1


# --- needs you via attention_tag ---------------------------------------------------------

@pytest.mark.parametrize("configured", ["needs-me", "#needs-me", "#Needs-Me", "NEEDS-ME"])
def test_attention_tag_with_and_without_hash(vault, configured):
    write(vault, "n.md", "# N\n- [ ] ask Alex #needs-me\n- [/] decide #Needs-Me\n- [x] finished #needs-me\n- [-] dropped #needs-me\n- [ ] other #needs-me-not\n- [ ] plain\n")
    out = run(vault, attention_tag=configured)
    assert sorted(i["title"] for i in out["attention"]) == ["ask Alex #needs-me", "decide #Needs-Me"]
    assert all(i["kind"] == "checkbox" for i in out["attention"])
    assert out["sections"]["attention"] is True


def test_sections_attention_is_false_without_field_or_tag(vault):
    write(vault, "n.md", "# N\n- [ ] x #needs-me\n")
    out = run(vault)
    assert out["sections"]["attention"] is False and out["attention"] == []
    assert run(vault, attention_field="f")["sections"]["attention"] is True
    assert run(vault, attention_tag="needs-me")["sections"]["attention"] is True


def test_attention_field_still_requires_waiting_status(vault):
    write(vault, "T/a.md", "---\ntags: [tasknote]\nstatus: open\nf: true\n---\n# A")
    write(vault, "T/b.md", "---\ntags: [tasknote]\nstatus: Blocked\nf: true\n---\n# B")
    out = run(vault, attention_field="f", tasks={"checkboxes": {"enabled": False}})
    assert paths(out["attention"]) == ["T/b.md"]


# --- refresh behaviour -----------------------------------------------------------------

def _task_rows(where="1"):
    conn = core._connect(False)
    try:
        return [(r["path"], r["line"], r["kind"], r["text"]) for r in conn.execute(f"SELECT path,line,kind,text FROM tasks WHERE {where} ORDER BY path,line")]
    finally:
        conn.close()


def test_schema_version_is_4_and_tasks_table_exists(vault):
    assert core.SCHEMA_VERSION == "4"
    core.refresh()
    conn = core._connect(False)
    try:
        columns = [r[1] for r in conn.execute("PRAGMA table_info(tasks)")]
    finally:
        conn.close()
    assert columns == ["id", "path", "line", "kind", "text", "status", "due", "project", "tags"]


def test_refresh_reparses_changed_notes_and_deletes_removed_notes_tasks(vault):
    a = write(vault, "a.md", "# A\n- [ ] one\n- [ ] two\n")
    write(vault, "b.md", "# B\n- [ ] bee\n")
    core.configure(str(vault))
    core.refresh()
    assert _task_rows("kind='checkbox'") == [("a.md", 2, "checkbox", "one"), ("a.md", 3, "checkbox", "two"), ("b.md", 2, "checkbox", "bee")]
    a.write_text("# A\n\n- [ ] one\n- [x] two\n- [ ] three\n")
    parsed = []
    original = core._checkbox_tasks
    core._checkbox_tasks = lambda *args, **kw: (parsed.append(args[0]), original(*args, **kw))[1]
    try:
        core.refresh()
    finally:
        core._checkbox_tasks = original
    assert parsed == ["a.md"]  # only the changed note was parsed again
    assert _task_rows("kind='checkbox'") == [("a.md", 3, "checkbox", "one"), ("a.md", 5, "checkbox", "three"), ("b.md", 2, "checkbox", "bee")]
    (vault / "b.md").unlink()
    core.refresh()
    assert [r[0] for r in _task_rows("kind='checkbox'")] == ["a.md", "a.md"]


def test_saving_a_note_updates_its_tasks(vault):
    from test_note_api import client
    write(vault, "a.md", "# A\n- [ ] old\n")
    core.configure(str(vault)); core.refresh()
    sha = core.read_note("a.md")["sha256"]
    core.save_note("a.md", "# A\n- [ ] new\n- [/] newer\n", sha)
    assert [r[3] for r in _task_rows("kind='checkbox'")] == ["new", "newer"]
    core.create_note("c.md", "- [ ] created\n")
    assert ("c.md", 1, "checkbox", "created") in _task_rows()


def test_note_task_rows_follow_note_edits(vault):
    p = write(vault, "t.md", "---\ntags: [tasknote]\nstatus: open\n---\n# T")
    core.configure(str(vault), tasks={"checkboxes": {"enabled": False}}); core.refresh()
    assert core.dashboard()["counts"]["tasks"] == 1
    sha = core.read_note("t.md")["sha256"]
    core.save_note("t.md", "---\ntags: [tasknote]\nstatus: done\n---\n# T", sha)
    assert core.dashboard()["counts"]["tasks"] == 0


def test_checkbox_cap_sets_truncated_flag(vault, monkeypatch):
    monkeypatch.setattr(core, "MAX_CHECKBOX_TASKS", 3)
    write(vault, "a.md", "# A\n" + "".join(f"- [ ] t{i}\n" for i in range(5)))
    out = run(vault)
    assert out["counts"]["tasks"] == 3 and out["counts"]["truncated"] is True
    write(vault, "a.md", "# A\n- [ ] only\n")
    core.refresh()
    again = core.dashboard()
    assert again["counts"]["tasks"] == 1 and again["counts"]["truncated"] is False


def test_cap_counts_across_notes(vault, monkeypatch):
    monkeypatch.setattr(core, "MAX_CHECKBOX_TASKS", 4)
    write(vault, "a.md", "# A\n- [ ] 1\n- [ ] 2\n- [ ] 3\n")
    write(vault, "b.md", "# B\n- [ ] 4\n- [ ] 5\n")
    out = run(vault)
    assert out["counts"]["tasks"] == 4 and out["counts"]["truncated"] is True


def test_dashboard_without_index_has_task_counts(vault):
    out = core.dashboard()
    assert out["counts"]["tasks"] == 0 and out["counts"]["tasknotes"] == 0
