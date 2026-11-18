# Hermes Lectern

Read and edit an Obsidian vault inside Hermes Desktop, next to your conversation with Hermes.

Hermes Lectern adds a Lectern page to Desktop. It opens to a dashboard of recent notes and the notes Hermes has changed. With TaskNotes, it also lists the tasks that need you. Notes open in a reader with properties, contents and backlinks, and you can edit and save them in place. It is built to sit in half of the Desktop window while you talk to Hermes in the other half.

## What it does

- **Dashboard.** Tabs for recent notes and for notes Hermes changed with its `write_file` and `patch` tools. If you use [TaskNotes](https://github.com/callumalpass/tasknotes), it also shows overdue tasks, tasks due within 7 days, and tasks in progress grouped by project. Set an attention field to add the tasks that need you.
- **Reader and editor.** Rendered Markdown with wikilinks, image embeds that display, a properties and contents rail, and backlinks. Click Edit, double-click the text or press ⌘E. ⌘S saves, and Esc leaves edit mode when nothing has changed. On Linux, use Ctrl instead of ⌘.
- **Safe saves.** If Hermes or another app changes a note while you are editing it, Hermes Lectern keeps your draft and lets you keep your version, load the disk version or compare them side by side.
- **Works with the conversation.** Select text in a note and quote it into the chat with the note's full file path. When Hermes writes to a note, the dashboard lists it and an open copy reloads.
- **Open from anywhere.** A vault note opened from elsewhere in Desktop opens in Lectern, on Hermes builds that provide the `preview.fileOpener` area. Older builds ignore this and use the normal file preview.
- **Languages.** English and Japanese UI. The language follows your system unless you pick one in Settings.

## Requirements

- Hermes Agent 0.21.6 or newer, with Hermes Desktop.
- Tested on macOS. Linux should work but is untested. Windows is not supported yet: the vault path must start with `/`.
- An Obsidian vault: a folder that contains `.obsidian/`.

## Install

```sh
hermes plugins install Fiction000/hermes-lectern
hermes plugins enable hermes-lectern
```

Restart Hermes Desktop, open **Lectern** in the sidebar and enter the absolute path of your vault. The first index reads every note: a 5,500-note vault took about 40 seconds on a Mac. Later refreshes only read changed notes; the same vault took under a second when nothing had changed.

## Settings

Open Settings with the gear icon at the top of the Lectern page.

| Setting | What it does | Default |
| --- | --- | --- |
| Vault folder | The vault to read and edit | none |
| Attention field | A frontmatter field that marks a TaskNote as needing you. A task appears under Needs you when this field is true and its status is `waiting` or `blocked` | off |
| Inbox folder | Top-level folder where new notes start when you are not browsing a folder | vault root |
| Language | Auto, English or Japanese | Auto |

The top-level `Attachments` folder is left out of the index by default. To change this, edit `exclude` (a list of top-level folder names) in `$HERMES_HOME/hermes-lectern/config.json`.

## What it reads, writes and stores

- **Your vault.** It reads Markdown files in the vault folder you choose and writes only when you save or create a note. It has no delete button. It skips hidden folders and symlinks, so files outside the vault never enter the index. It also reads image files inside the vault to display them, including folders left out of the index.
- **Its own data.** Settings live in `$HERMES_HOME/hermes-lectern/config.json`. The search index is a SQLite file in the same folder, outside your vault, and can be deleted at any time. For a 5,500-note vault it is about 170 MB.
- **Hermes events.** The Desktop side of the plugin listens to Hermes `tool.complete` events for `write_file` and `patch` calls, to notice which notes Hermes wrote. The 50 most recent are kept in Desktop's local storage on your computer.
- **Clipboard.** Quoting writes to the clipboard only when no chat box is open.
- **Network and hooks.** It only talks to Hermes' own API. It adds no agent tools or hooks, sends no telemetry and never updates itself. Remote images in notes are not loaded; they show as links.

## Development

```sh
node --test tests/
uv run --python 3.14 --with pytest --with fastapi --with httpx pytest -q
```

To benchmark a real vault without writing to it, use a fresh scratch home:

```sh
uv run --python 3.14 --with fastapi --with httpx python scripts/bench_real_vault.py \
  --root "/path/to/vault" --home "/path/to/fresh/hermes-home"
```
