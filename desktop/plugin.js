// Hermes Lectern: read, edit and create notes of one Obsidian vault inside Desktop.
// Plain disk-plugin ESM. All file access goes through the plugin's own backend
// (/api/plugins/hermes-lectern); nothing here touches the filesystem or a shell.
import { host, useValue, useQuery, queryClient, Button, Input, Textarea, SearchField, EmptyState,
  ErrorState, Skeleton, Codicon, Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
  ROUTES_AREA, SIDEBAR_NAV_AREA, PALETTE_AREA } from '@hermes/plugin-sdk';
import { useEffect, useMemo, useRef, useState } from 'react';
import { jsx, jsxs } from 'react/jsx-runtime';

export const TOUCH_TOOLS = Object.freeze({ write_file: 'path', patch: 'path' });
export function toVaultRelative(root, rawPath) {
  if (typeof root !== 'string' || typeof rawPath !== 'string' || !root.startsWith('/')) return null;
  if (rawPath.startsWith('~/')) {
    const home = /^\/(Users|home)\/([^/]+)(?:\/|$)/.exec(root);
    if (!home) return null;
    rawPath = `/${home[1]}/${home[2]}${rawPath.slice(1)}`;
  }
  if (!rawPath.startsWith('/')) return null;
  const normalize = value => {
    const parts = [];
    for (const part of value.split('/')) {
      if (!part || part === '.') continue;
      if (part === '..') parts.pop();
      else parts.push(part);
    }
    return `/${parts.join('/')}`;
  };
  const base = normalize(root), target = normalize(rawPath);
  if (target === base || !target.startsWith(`${base}/`)) return null;
  const relative = target.slice(base.length + 1);
  if (!relative.endsWith('.md') || relative.startsWith('.trash/') || relative === '.trash' ||
      relative.startsWith('.obsidian/') || relative === '.obsidian') return null;
  return relative;
}
// Only Markdown notes inside the vault (toVaultRelative's rule) go to the reader; everything else keeps Desktop's preview.
export function vaultOpenTarget(root, absPath) {
  return toVaultRelative(root, absPath);
}
// Escape only leaves a clean draft, so a stray keypress never throws away typing.
export function editKeyAction(e, { editing, dirty }) {
  const mod = e.metaKey || e.ctrlKey;
  if (mod && e.key.toLowerCase() === 'e') return editing ? null : 'edit';
  if (mod && e.key.toLowerCase() === 's') return editing && dirty ? 'save' : null;
  if (e.key === 'Escape') return editing && !dirty ? 'cancel' : null;
  return null;
}
export function noteTitle(path) {
  return String(path).split('/').pop().replace(/\.md$/, '');
}
export function addTouch(list, record) {
  return [record, ...(Array.isArray(list) ? list : []).filter(item => item?.path !== record.path)].slice(0, 50);
}
export function quoteBlock(text, absPath, locale = LOCALE) {
  const lines = String(text).replace(/\s+$/, '').split('\n');
  return `${lines.map(line => line ? `> ${line}` : '>').join('\n')}\n\n${t('source', {}, locale)}: ${absPath}`;
}
export function touchFromEvent(payload, root) {
  if (!payload || !Object.hasOwn(TOUCH_TOOLS, payload.name)) return null;
  const rawPath = payload.args?.[TOUCH_TOOLS[payload.name]];
  let result = payload.result;
  if (typeof result === 'string') {
    try { result = JSON.parse(result); } catch { /* tools may return plain text */ }
  }
  if (typeof rawPath !== 'string' || (result && typeof result === 'object' && result.error)) return null;
  const path = toVaultRelative(root, rawPath);
  return path ? { path, tool: payload.name } : null;
}

// i18n:ja-start
export const STRINGS = {
  en: {
    needs: "Needs you",
    projects: "Projects",
    recent: "Recent",
    touched: "Hermes",
    overdue: "Overdue",
    within7: "Within 7 days",
    source: "Source",
    today: "Today",
    yesterday: "Yesterday",
    monthDay: "{m}/{d}",
    daysOverdue: "{n} d overdue",
    tomorrow: "Tomorrow {md}",
    inDays: "In {n} days",
    unsaved: "Unsaved",
    justNow: "just now",
    minAgo: "{n} min ago",
    hAgo: "{n} h ago",
    dAgo: "{n} d ago",
    loadVaultFail: "Could not load the vault",
    retry: "Try again",
    lateN: "{n} overdue",
    vaultRoot: "vault root",
    stalled: "Blocked",
    noNeeds: "Nothing needs you",
    due: "Due",
    noDue: "Nothing due in the next 7 days",
    noTouched: "Hermes has not changed any notes yet",
    none: "Nothing here",
    close: "Show less",
    moreN: "{n} more",
    properties: "Properties",
    contents: "Contents",
    backlinksN: "Backlinks {n}",
    quoteClipboard: "No chat box was found, so the quote was copied to the clipboard",
    quoteInserted: "Quote added to the chat box",
    linkMissing: "That linked note was not found.",
    openFail: "Could not open this note",
    saved: "Saved.",
    saveFail: "Could not save. Your draft is kept. {err}",
    conflictTitle: "This note changed on disk while you were editing",
    conflictBody: "Hermes or another app saved it at {time}. Your edits are not saved yet. Which version do you want to keep?",
    keepMine: "Keep my version",
    loadDisk: "Load the disk version",
    stopCompare: "Stop comparing",
    compare: "Compare side by side",
    editHint: "Double-click or ⌘E to edit",
    dirty: "Unsaved changes",
    clean: "No changes",
    cancel: "Cancel",
    saveKey: "Save ⌘S",
    mine: "My version",
    disk: "Disk version",
    createdOn: "Created {d}",
    editing: "editing",
    noteBody: "Note text",
    quoteToChat: "Quote in chat",
    createFail: "Could not create the note. Check whether a note with this title already exists and whether the folder is valid. {err}",
    newNote: "New note",
    title: "Title",
    folder: "Folder",
    type: "Type",
    createHint: "New notes start with tags: [type/{type}, state/processing] and created: {today}.",
    create: "Create",
    rootFail: "This folder could not be opened as a vault. {err}",
    setupTitle: "Choose your vault",
    setupHint: "Enter the absolute path of an Obsidian vault folder. Only folders that contain .obsidian can be opened.",
    indexing: "Building the index…",
    useFolder: "Use this folder",
    discard: "You have unsaved edits. Discard them and leave?",
    backendFail: "Cannot reach the Hermes Lectern backend",
    backendHint: "Check that the plugin is enabled and that Hermes Desktop was restarted. ",
    backHome: "Back to Home",
    home: "Home",
    searchNotes: "Search notes",
    todayIs: "Today · {date}",
    notes: "Notes",
    expandList: "Expand list",
    collapseList: "Collapse list",
    notFound: "No matches",
    emptyFolder: "No notes in this folder",
    pickNote: "Choose a note",
    pickNoteHint: "Choose one from the list to read it here.",
    openVault: "Open Lectern",
    paletteQuote: "Hermes Lectern: quote selection in chat",
    noHeadings: "No headings",
    edit: "Edit",
    attentionLabel: "Frontmatter field that marks a task as needing you (optional)",
    inboxLabel: "Inbox folder for new notes (optional)",
    language: "Language",
    settings: "Settings",
    save: "Save",
    unassigned: "(No project)",
    setupEditTitle: "Settings",
  },
  ja: {
    needs: "判断待ち",
    projects: "案件",
    recent: "最近",
    touched: "Hermes",
    overdue: "期限超過",
    within7: "7日以内",
    source: "出典",
    today: "今日",
    yesterday: "昨日",
    monthDay: "{m}月{d}日",
    daysOverdue: "{n}日超過",
    tomorrow: "明日 {md}",
    inDays: "あと {n} 日",
    unsaved: "未保存",
    justNow: "たった今",
    minAgo: "{n}分前",
    hAgo: "{n}時間前",
    dAgo: "{n}日前",
    loadVaultFail: "vault を読み込めませんでした",
    retry: "もう一度",
    lateN: "超過 {n}",
    vaultRoot: "vault 直下",
    stalled: "止まり",
    noNeeds: "判断待ちはありません",
    due: "期限",
    noDue: "7日以内の期限はありません",
    noTouched: "Hermes が触ったノートはまだありません",
    none: "ありません",
    close: "閉じる",
    moreN: "ほか {n} 件",
    properties: "プロパティ",
    contents: "目次",
    backlinksN: "バックリンク {n}",
    quoteClipboard: "会話の入力欄が見つからないので、引用をクリップボードにコピーした",
    quoteInserted: "引用を入力欄に入れた",
    linkMissing: "このリンク先のノートは見つかりませんでした。",
    openFail: "このノートを開けませんでした",
    saved: "保存しました。",
    saveFail: "保存できませんでした。下書きは残っています。{err}",
    conflictTitle: "このノートが、直している間に別の手で書き換えられた",
    conflictBody: "Hermes かディスク側が {time} に保存しました。あなたの直しはまだ保存されていません。どちらを残しますか。",
    keepMine: "自分の版を残す",
    loadDisk: "ディスクの版を読み込む",
    stopCompare: "比べるのをやめる",
    compare: "並べて比べる",
    editHint: "ダブルクリックか ⌘E で編集",
    dirty: "未保存の変更がある",
    clean: "変更なし",
    cancel: "やめる",
    saveKey: "保存 ⌘S",
    mine: "自分の版",
    disk: "ディスクの版",
    createdOn: "作成 {d}",
    editing: "編集中",
    noteBody: "ノートの本文",
    quoteToChat: "会話に引用",
    createFail: "作れませんでした。同じ題名のノートがあるか、保存先を確かめてください。{err}",
    newNote: "新しいノート",
    title: "題名",
    folder: "保存先のフォルダ",
    type: "種類",
    createHint: "作ると先頭に tags: [type/{type}, state/processing]、created: {today} が入る。",
    create: "作る",
    rootFail: "この場所は vault として開けませんでした。{err}",
    setupTitle: "vault の場所を決める",
    setupHint: "Obsidian の vault のフォルダを、先頭の / から書く。中に .obsidian があるフォルダだけ開ける。",
    indexing: "索引を作っています…",
    useFolder: "この場所を使う",
    discard: "保存していない直しがあります。捨てて移りますか。",
    backendFail: "Hermes Lectern の裏側につながりません",
    backendHint: "プラグインが有効か、Hermes Desktop を再起動したか確かめてください。",
    backHome: "ホームに戻る",
    home: "ホーム",
    searchNotes: "ノートを探す",
    todayIs: "今日・{date}",
    notes: "ノート一覧",
    expandList: "一覧を開く",
    collapseList: "一覧を折りたたむ",
    notFound: "見つかりませんでした",
    emptyFolder: "このフォルダにノートはありません",
    pickNote: "ノートを選ぶ",
    pickNoteHint: "左の一覧から選ぶと、ここで読める。",
    openVault: "Lectern を開く",
    paletteQuote: "Hermes Lectern: 選択範囲を会話に引用",
    noHeadings: "見出しはありません",
    edit: "編集",
    attentionLabel: "「判断待ち」を示すフロントマターの項目（任意）",
    inboxLabel: "新しいノートの保存先フォルダ（任意）",
    language: "表示言語",
    settings: "設定",
    save: "保存",
    unassigned: "（未分類）",
    setupEditTitle: "設定",
  },
};
// i18n:ja-end
// Module-level UI locale, set once per render of the app from the vault config.
let LOCALE = 'en';
export function setUiLocale(locale) { LOCALE = locale === 'ja' ? 'ja' : 'en'; }
const L = (key, vars) => t(key, vars, LOCALE);
export function pickLocale(setting, navLang = '') {
  if (setting === 'en' || setting === 'ja') return setting;
  return String(navLang).toLowerCase().startsWith('ja') ? 'ja' : 'en';
}
export function t(key, vars = {}, locale = 'en') {
  const text = STRINGS[locale]?.[key] ?? STRINGS.en[key] ?? key;
  return text.replace(/\{(\w+)\}/g, (_, name) => String(vars[name] ?? ''));
}

const KEY = ['hermes-lectern'];
const TYPES = ['reference', 'report', 'review', 'research', 'plan'];
const enc = encodeURIComponent;

// Scoped stylesheet: a disk plugin cannot rely on utility classes the app's
// build did not already emit, so layout lives here and colors come from theme variables.
const CSS = `
.hv{container-type:inline-size;container-name:hv;--hv-page:var(--ui-bg-chrome);--hv-panel:var(--ui-bg-editor);--hv-panel-raised:var(--ui-bg-elevated,var(--ui-bg-quaternary));--hv-line:var(--ui-stroke-tertiary);--hv-ink:var(--ui-text-primary);--hv-muted:var(--ui-text-secondary);--hv-dim:var(--ui-text-tertiary);--hv-red:var(--ui-red);--hv-orange:var(--ui-orange);height:100%;display:flex;flex-direction:column;color:var(--hv-ink);font-size:15px;line-height:1.5;background:var(--hv-page)}
.hv *{box-sizing:border-box;scrollbar-width:none}.hv *::-webkit-scrollbar{display:none}
.hv-scroll{overflow:auto;scrollbar-width:none}.hv-scroll::-webkit-scrollbar{display:none}
.hv-top{display:flex;align-items:center;gap:16px;padding:16px 32px 8px}.hv-top .grow{flex:1;max-width:420px}.hv-tabs{display:none}.hv-home-btn{display:inline-flex;align-items:center;gap:6px;border:0;border-radius:5px;background:none;color:var(--hv-muted);font:inherit;font-size:14px;padding:6px 8px;cursor:pointer;white-space:nowrap;transition:background .18s ease}.hv-back{border:1px solid var(--hv-line,var(--border));color:var(--hv-ink);font-weight:500;padding:6px 12px}.hv-home-btn:hover{background:color-mix(in srgb,var(--chrome-action-hover) 70%,transparent);color:var(--hv-ink)}
.hv-top-tools{flex:1}.hv-top-date{color:var(--hv-dim);font-size:13px;white-space:nowrap}
.hv-home{flex:1;min-height:0;padding:12px 28px 48px;display:flex;flex-direction:column;gap:22px}
.hv-date{display:none}.hv-stats{grid-column:1/-1;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
.hv-stat{position:relative;min-height:78px;padding:10px 14px;background:var(--hv-panel);border:1px solid var(--hv-line);border-radius:7px;color:inherit;text-align:left;cursor:pointer;transition:transform .18s ease,background .18s ease;box-shadow:0 2px 8px color-mix(in srgb,var(--ui-text-primary) 3%,transparent)}
.hv-stat:hover{transform:translateY(-1px);background:var(--hv-panel-raised)}.hv-stat-label{font-size:13px;color:var(--hv-muted)}.hv-stat-line{display:flex;align-items:baseline;gap:7px}.hv-stat-number{font-size:42px;line-height:1.05;font-weight:650;font-variant-numeric:tabular-nums;letter-spacing:-1.5px}.hv-stat-unit{font-size:13px;color:var(--hv-dim)}.hv-stat-arrow{position:absolute;right:12px;top:10px;color:var(--ui-accent);font-size:16px}.hv-stat.red{background:color-mix(in srgb,var(--hv-red) 10%,var(--hv-panel))}.hv-stat.red .hv-stat-number{color:var(--hv-red)}.hv-stat.orange .hv-stat-number{color:var(--hv-orange)}.hv-stat.calm{cursor:default}.hv-stat.calm .hv-stat-number{font-size:17px;letter-spacing:0;font-weight:550}
.hv-primary-stack,.hv-secondary-stack{display:flex;flex-direction:column;gap:12px;min-width:0;min-height:0}
.hv-panel{background:var(--hv-panel);border:1px solid var(--hv-line);border-radius:7px;padding:14px 16px;box-shadow:0 2px 10px color-mix(in srgb,var(--ui-text-primary) 3%,transparent);min-width:0}
.hv-panel.raised{background:var(--hv-panel-raised)}.hv-panel h2,.hv-compact h2{font-size:18px;line-height:24px;font-weight:600;margin:0}.hv-panel-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:10px}.hv-panel-count{font-size:13px;color:var(--hv-dim);font-variant-numeric:tabular-nums}
.hv-h1{font-size:26px;line-height:34px;font-weight:600;margin:0 0 12px}.hv-h2{font-size:19px;line-height:28px;font-weight:600;margin:0 0 10px}
.hv-row{display:flex;align-items:center;gap:9px;width:100%;padding:7px 8px;margin:0;border:0;border-radius:4px;background:none;color:inherit;font:inherit;text-align:left;cursor:pointer;transition:background .18s ease,transform .18s ease}
.hv-row:hover{background:color-mix(in srgb,var(--chrome-action-hover) 70%,transparent);transform:translateY(-1px)}.hv-row[aria-current=true]{background:color-mix(in srgb,var(--ui-accent) 10%,var(--hv-panel));font-weight:600}.hv-row .main{flex:1;min-width:0}
.hv-title{font-size:15px;line-height:21px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.hv-sub{color:var(--hv-dim);font-size:13px;line-height:18px}.hv-meta{color:var(--hv-muted);font-size:13px;white-space:nowrap}.hv-meta.red{color:var(--hv-red);font-weight:600}.hv-meta.orange{color:var(--hv-orange);font-weight:550}
.hv-project{color:var(--hv-dim);font-size:13px;white-space:nowrap;min-width:0}.hv-project-name{display:inline-block;max-width:11em;overflow:hidden;text-overflow:ellipsis;vertical-align:bottom}.hv-project-dot{display:inline-block;width:7px;height:7px;border-radius:50%;flex:none;background:var(--project-color);margin-right:2px}.hv-pill{font-size:13px;padding:2px 7px;border-radius:4px;white-space:nowrap;background:color-mix(in srgb,var(--hv-orange) 14%,transparent);color:var(--hv-orange)}.hv-pill.red{background:color-mix(in srgb,var(--hv-red) 14%,transparent);color:var(--hv-red)}
.hv-overdue{background:color-mix(in srgb,var(--hv-red) 7%,transparent)}.hv-overdue:hover{background:color-mix(in srgb,var(--hv-red) 11%,transparent)}.hv-group{display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:center;gap:8px;padding:4px 2px;min-width:0}.hv-group .name{display:flex;align-items:center;gap:8px;min-width:0;font-size:14px}.hv-group .name span:last-child{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.hv-group-count{font-size:15px;font-variant-numeric:tabular-nums;color:var(--hv-muted)}.hv-group-extra{color:var(--hv-dim);font-size:13px;padding:6px 8px 0}.hv-expand{border:0;background:none;color:var(--hv-muted);font:inherit;cursor:pointer;padding:6px 4px;font-size:13px}.hv-expand:hover{color:var(--hv-ink)}
.hv-compact-row{min-height:0;max-height:160px;overflow:auto;position:relative}.hv-compact{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:24px;grid-column:1/-1;min-width:0}.hv-compact h2{margin-bottom:6px}.hv-compact-list{position:relative;max-height:126px;overflow:auto;mask-image:linear-gradient(to bottom,#000 75%,transparent)}.hv-compact .hv-row{padding:3px 2px}.hv-compact .hv-title{font-size:14px}.hv-loose,.hv-inbox{padding:6px 2px 0}.hv-loose h2,.hv-inbox h2{font-size:18px;line-height:24px;font-weight:600;margin:0 0 6px}.hv-loose .hv-compact-list{max-height:420px}.hv-inbox .hv-row{padding:4px 2px}
.hv-group .name{color:var(--hv-ink)}.hv-sep{border-top:1px solid var(--hv-line);margin:16px 0;padding-top:12px}.hv-day{color:var(--hv-dim);font-size:13px;margin:10px 0 2px}.hv-dot{width:8px;height:8px;border-radius:50%;background:var(--hv-orange);flex:none;margin-top:8px}
.hv-browse{flex:1;min-height:0;display:grid;grid-template-columns:220px 250px minmax(0,1fr)}.hv-browse.collapsed{grid-template-columns:40px 250px minmax(0,1fr)}.hv-col{min-height:0;padding:12px;position:relative}.hv-col.note{background:var(--hv-page);padding:0;min-width:0}.hv-fade:after{content:'';position:sticky;display:block;bottom:0;height:40px;margin-top:-40px;pointer-events:none;background:linear-gradient(transparent,var(--hv-page))}
.hv-folder{font-size:15px;padding:6px 10px;margin:0}.hv-list .hv-row{margin:0;align-items:flex-start}.hv-list .hv-title{font-size:15px;line-height:22px}.hv-bar{display:flex;align-items:center;gap:10px;padding:20px 32px 8px}.hv-bar .crumb{flex:1;color:var(--hv-dim);font-size:13px}.hv-unsaved{flex:1;color:var(--hv-orange);font-size:13px;display:flex;align-items:center;gap:8px}.hv-doc{padding:8px 32px 80px;max-width:860px;margin:0 auto;width:100%}.hv-quote{position:fixed;z-index:20;background:var(--hv-panel-raised);border:1px solid var(--hv-line);border-radius:5px;box-shadow:0 3px 12px color-mix(in srgb,var(--ui-text-primary) 12%,transparent);font-size:13px;padding:5px 10px}
.hv-doc h1{font-size:32px;line-height:42px;font-weight:700;margin:8px 0 2px}.hv-doc h2{font-size:22px;line-height:32px;font-weight:600;margin:28px 0 8px}.hv-doc h3,.hv-doc h4{font-size:18px;line-height:28px;font-weight:550;margin:22px 0 6px}.hv-doc p,.hv-doc li{font-size:16px;line-height:29px}.hv-doc p{margin:0 0 16px}.hv-doc ul,.hv-doc ol{margin:0 0 16px;padding-left:26px}.hv-doc blockquote{margin:0 0 16px;padding-left:16px;border-left:2px solid var(--ui-stroke-secondary);color:var(--hv-muted)}
.hv-doc pre{background:var(--hv-panel);padding:14px 16px;border-radius:5px;overflow:auto;font-size:13px;line-height:20px;margin:0 0 16px}.hv-doc code{background:var(--ui-inline-code-background,var(--hv-panel));padding:1px 5px;border-radius:3px;font-size:.88em}.hv-doc pre code{background:none;padding:0}.hv-doc hr{border:0;border-top:1px solid var(--hv-line);margin:24px 0}.hv-doc table{border-collapse:collapse;margin:0 0 16px;font-size:15px}.hv-doc td,.hv-doc th{border:1px solid var(--hv-line);padding:6px 10px;text-align:left}
.hv-link{color:var(--ui-accent);background:none;border:0;padding:0;font:inherit;cursor:pointer;text-decoration:none}.hv-link.dead{color:var(--hv-dim);cursor:default}.hv-tags{display:flex;flex-wrap:wrap;gap:7px;margin:0 0 18px;align-items:center}.hv-tag{font-size:13px;padding:3px 8px;border-radius:4px;background:var(--ui-bg-quaternary);color:var(--hv-muted)}.hv-field{display:flex;flex-direction:column;gap:6px;font-size:13px;color:var(--hv-muted)}.hv-select{height:32px;border-radius:6px;border:1px solid var(--hv-line);background:var(--hv-panel);color:var(--hv-ink);padding:0 8px;font:inherit}.hv-edit{display:block;width:100%;min-height:60vh;overflow:hidden;resize:none;border:0;outline:0;padding:12px 0;background:transparent;color:var(--hv-ink);font:inherit;font-size:16px;line-height:28px;caret-color:var(--ui-accent)}.hv-read-doc.editing{box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--ui-accent) 35%,transparent);border-radius:8px;background:color-mix(in srgb,var(--hv-panel) 60%,transparent)}.hv-bar-hint{flex:1;color:var(--hv-dim);font-size:13px}.hv-bar{position:sticky;top:0;z-index:2;background:var(--hv-page)}
.hv-warn{margin:16px 32px 0;padding:16px 20px;border:1px solid color-mix(in srgb,var(--hv-orange) 45%,transparent);border-radius:6px;background:color-mix(in srgb,var(--hv-orange) 8%,var(--hv-panel))}.hv-warn h3{font-size:18px;margin:0 0 6px;font-weight:600}.hv-warn p{margin:0 0 14px;color:var(--hv-muted)}.hv-actions{display:flex;gap:8px;flex-wrap:wrap}.hv-diff{display:grid;grid-template-columns:1fr 1fr;gap:16px;padding:8px 32px 80px}.hv-diff pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px;line-height:20px;background:var(--hv-panel);padding:14px;border-radius:5px;margin:6px 0 0}.hv-form{display:flex;flex-direction:column;gap:18px}.hv-form label{display:flex;flex-direction:column;gap:6px;font-size:13px;color:var(--hv-muted)}.hv-chips{display:flex;flex-wrap:wrap;gap:8px}.hv-setup{max-width:560px;margin:80px auto;display:flex;flex-direction:column;gap:14px;padding:0 24px}
.hv-read-layout{height:100%;min-height:0;display:grid;grid-template-columns:230px minmax(0,1fr)}.hv-read-layout.left-collapsed{grid-template-columns:42px minmax(0,1fr)}.hv-read-nav,.hv-rail{min-height:0;overflow:auto;padding:14px 10px;background:var(--hv-panel)}.hv-read-nav{border-right:1px solid var(--hv-line)}.hv-nav-folders{max-height:32%;overflow:auto;border-bottom:1px solid var(--hv-line);padding-bottom:8px;margin-bottom:8px}.hv-nav-notes{height:calc(68vh - 100px);overflow:auto}.hv-note-layout{height:100%;min-height:0;display:grid;grid-template-columns:minmax(0,1fr) 288px}.hv-note-scroll{min-width:0}.hv-row-project{display:flex;align-items:center;gap:8px;flex:none}.hv-row-project .hv-project{display:flex;align-items:center;gap:6px}.hv-rail{border-left:1px solid var(--hv-line);padding:14px 12px}.hv-nav-head{display:flex;align-items:center;gap:8px;padding:0 4px 12px}.hv-nav-title{font-size:13px;color:var(--hv-muted);flex:1}.hv-collapse{border:0;background:none;color:var(--hv-muted);cursor:pointer;padding:4px}.hv-note-main{min-width:0;min-height:0;overflow:auto}.hv-read-doc{padding:22px 38px 80px;max-width:900px}.hv-breadcrumb{font-size:13px;color:var(--hv-dim);margin-bottom:8px}.hv-created{font-size:13px;color:var(--hv-dim);padding-bottom:12px;border-bottom:1px solid var(--hv-line);margin-bottom:16px}.hv-rail-section{margin-bottom:20px}.hv-rail-title{font-size:13px;color:var(--hv-muted);margin:0 0 8px}.hv-prop{display:grid;grid-template-columns:76px minmax(0,1fr);gap:8px;padding:5px 0;font-size:13px}.hv-prop-key{color:var(--hv-dim)}.hv-toc button{width:100%;border:0;border-radius:4px;background:none;color:var(--hv-muted);text-align:left;padding:5px 7px;font:inherit;font-size:13px;cursor:pointer}.hv-toc button[data-active=true]{background:color-mix(in srgb,var(--ui-accent) 12%,var(--hv-panel));color:var(--hv-ink);font-weight:650}.hv-toc button[data-level="3"]{padding-left:18px}.hv-backlinks{font-size:13px;color:var(--hv-muted)}
.hv-d-figs{display:flex;gap:6px;border-bottom:1px solid var(--hv-line);padding-bottom:14px}
.hv-d-fig{flex:1;min-width:0;display:flex;flex-direction:column;align-items:flex-start;gap:2px;padding:6px 10px;border:0;border-radius:6px;background:none;color:inherit;font:inherit;cursor:pointer;transition:background .18s ease}
.hv-d-fig:hover{background:color-mix(in srgb,var(--chrome-action-hover) 70%,transparent)}
.hv-d-num{font-size:30px;line-height:1.1;font-weight:600;font-variant-numeric:tabular-nums;letter-spacing:-.5px}
.hv-d-label{font-size:13px;color:var(--hv-muted)}
.hv-d-fig.red .hv-d-num{color:var(--hv-red)}.hv-d-fig.orange .hv-d-num{color:var(--hv-orange)}.hv-d-fig.zero .hv-d-num{color:var(--hv-dim);font-weight:500}
.hv-d-cols{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:22px 40px;align-items:start}
.hv-d-cols.single{grid-template-columns:minmax(0,1fr)}.hv-d-col{display:flex;flex-direction:column;gap:22px;min-width:0}
.hv-d-section{min-width:0}
.hv-d-h{display:flex;align-items:baseline;gap:8px;font-size:17px;line-height:24px;font-weight:600;margin:0 0 6px}
.hv-d-count{font-size:13px;font-weight:500;color:var(--hv-dim);font-variant-numeric:tabular-nums}
.hv-d-empty{margin:2px 0;color:var(--hv-dim);font-size:14px}
.hv-d-meta{display:flex;align-items:center;gap:10px;min-width:0;margin-top:2px}.hv-d-meta .hv-project{display:inline-flex;align-items:center;gap:6px}
.hv-d-meta .hv-project-name{max-width:16em}
.hv-d-tabs{display:flex;gap:2px;margin:0 0 8px;border-bottom:1px solid var(--hv-line)}
.hv-d-tabs button{border:0;background:none;color:var(--hv-muted);font:inherit;font-size:14px;padding:6px 10px 8px;cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-1px;transition:color .18s ease}
.hv-d-tabs button:hover{color:var(--hv-ink)}
.hv-d-tabs button[aria-selected=true]{color:var(--hv-ink);font-weight:600;border-bottom-color:var(--hv-ink)}
.hv-d-tabcount{margin-left:6px;font-size:12px;color:var(--hv-dim);font-variant-numeric:tabular-nums}
.hv-d-desk .hv-group{padding:8px 8px}
@container hv (max-width:900px){.hv-home{padding:10px 18px 40px}.hv-d-cols{grid-template-columns:minmax(0,1fr)}}
@container hv (max-width:520px){.hv-d-num{font-size:24px}.hv-d-fig{padding:4px 6px}.hv-d-label{font-size:12px}}
@container hv (max-width:1100px){.hv-project-name{max-width:6em}.hv-read-layout,.hv-read-layout.left-collapsed{grid-template-columns:220px minmax(0,1fr)}.hv-note-layout{grid-template-columns:minmax(0,1fr)}.hv-rail{display:none}.hv-home{grid-template-columns:minmax(0,1fr) minmax(300px,.9fr);padding-left:20px;padding-right:20px}.hv-top{padding-left:20px;padding-right:20px}}
@container hv (max-width:900px){.hv-read-layout,.hv-read-layout.left-collapsed{grid-template-columns:minmax(0,1fr)}.hv-read-nav{display:none}.hv-home{grid-template-columns:minmax(0,1fr);grid-template-rows:auto auto auto auto}.hv-secondary-stack{grid-row:auto}.hv-compact{grid-column:1}.hv-inbox{grid-column:1}.hv-stats{grid-template-columns:repeat(2,minmax(0,1fr))}.hv-top{gap:8px;padding:10px 14px}.hv-top .grow{max-width:none}.hv-top-date{display:none}.hv-doc{padding:8px 20px 64px}}
@container hv (max-width:560px){.hv-stats{gap:7px}.hv-stat{padding:8px;min-height:68px}.hv-stat-number{font-size:34px}.hv-compact{grid-template-columns:1fr;gap:16px}.hv-top{flex-wrap:wrap}.hv-top .grow{order:2;flex-basis:100%}.hv-read-doc{padding:18px 18px 60px}}
`;

const day = ns => new Date(Number(ns) / 1e6);
const sameDay = (a, b) => a.toDateString() === b.toDateString();
function dayLabel(ns, locale = LOCALE) {
  const d = day(ns), now = new Date(), y = new Date(now.getTime() - 864e5);
  return sameDay(d, now) ? t('today', {}, locale) : sameDay(d, y) ? t('yesterday', {}, locale) : t('monthDay', { m: d.getMonth() + 1, d: d.getDate() }, locale);
}
const project = n => n.path.startsWith('Projects/') ? n.path.split('/')[1] : n.path.split('/')[0];
const typeOf = n => ((n.tags || []).find(t => String(t).startsWith('type/')) || '').slice(5);
const clean = v => String(v ?? '').replace(/^\[\[|\]\]$/g, '').split('|')[0].split('/').pop();
const PROJECT_COLORS = Object.freeze(['#7fa6c8', '#9a8ac5', '#78aa9c', '#c18b91', '#b69a70', '#7fa58a', '#bb879f', '#8f9e72']);
function projectName(label) {
  return String(label ?? '').replace(/^\[\[|\]\]$/g, '').split('|')[0].split('/').pop().trim();
}
export function projectColor(label) {
  const name = projectName(label);
  let hash = 2166136261;
  for (const char of name) hash = Math.imul(hash ^ char.codePointAt(0), 16777619);
  return PROJECT_COLORS[(hash >>> 0) % PROJECT_COLORS.length];
}
export function dueLabel(dueISO, todayDate = new Date(), locale = LOCALE) {
  const date = String(dueISO ?? '').slice(0, 10);
  const due = Date.parse(`${date}T00:00:00Z`);
  const todayValue = todayDate instanceof Date ? `${todayDate.getFullYear()}-${String(todayDate.getMonth() + 1).padStart(2, '0')}-${String(todayDate.getDate()).padStart(2, '0')}` : String(todayDate).slice(0, 10);
  const today = Date.parse(`${todayValue}T00:00:00Z`);
  if (!Number.isFinite(due) || !Number.isFinite(today)) return { text: '', tone: 'neutral' };
  const days = Math.round((due - today) / 864e5);
  const d = new Date(due), md = `${d.getUTCMonth() + 1}/${d.getUTCDate()}`;
  if (days < 0) return { text: t('daysOverdue', { n: -days }, locale), tone: 'red' };
  if (days === 0) return { text: t('today', {}, locale), tone: 'orange' };
  if (days === 1) return { text: t('tomorrow', { md }, locale), tone: 'orange' };
  if (days <= 7) return { text: t('inDays', { n: days }, locale), tone: 'orange' };
  return { text: md, tone: 'neutral' };
}
export function headingsOf(markdown) {
  const result = []; let fenced = false;
  for (const line of String(markdown ?? '').split(/\r?\n/)) {
    if (/^\s*(```|~~~)/.test(line)) { fenced = !fenced; continue; }
    if (fenced) continue;
    const m = /^(#{2,3})\s+(.+?)\s*#*\s*$/.exec(line);
    if (m) result.push({ level: m[1].length, text: m[2].trim(), id: `hv-heading-${result.length}` });
  }
  return result;
}
const btn = (label, onClick, props = {}) => jsx(Button, { type: 'button', variant: 'secondary', onClick, ...props, children: label });

// ---- Markdown (read view). Small on purpose: headings, lists, quotes, code,
// tables, links and wikilinks. Anything else falls through as plain text.
function inline(text, open, keyBase) {
  const out = []; let rest = text, i = 0;
  const re = /(`[^`]+`)|(!?\[\[[^\]]+\]\])|(\[[^\]]+\]\((https?:[^)\s]+)\))|(\*\*[^*]+\*\*)/;
  while (rest) {
    const m = re.exec(rest);
    if (!m) { out.push(rest); break; }
    if (m.index) out.push(rest.slice(0, m.index));
    const tok = m[0], k = `${keyBase}-${i++}`;
    if (m[1]) out.push(jsx('code', { children: tok.slice(1, -1) }, k));
    else if (m[2]) {
      const inner = tok.replace(/^!?\[\[|\]\]$/g, ''), target = inner.split('|')[0], label = inner.split('|')[1] || target.split('/').pop();
      out.push(jsx('button', { type: 'button', className: 'hv-link', onClick: () => open(target), children: label }, k));
    } else if (m[3]) {
      const label = tok.slice(1, tok.indexOf(']('));
      out.push(jsx('a', { className: 'hv-link', href: m[4], target: '_blank', rel: 'noreferrer', children: label }, k));
    } else out.push(jsx('strong', { children: tok.slice(2, -2) }, k));
    rest = rest.slice(m.index + tok.length);
  }
  return out;
}
function Markdown({ body, open }) {
  const blocks = useMemo(() => {
    const lines = body.split('\n'), out = []; let i = 0, headingIndex = 0;
    const flush = (tag, items) => out.push(jsx(tag, { children: items.map((t, j) => jsx('li', { children: inline(t, open, `l${out.length}-${j}`) }, j)) }, out.length));
    while (i < lines.length) {
      const line = lines[i];
      if (!line.trim()) { i++; continue; }
      if (line.startsWith('```')) {
        const buf = []; i++;
        while (i < lines.length && !lines[i].startsWith('```')) buf.push(lines[i++]);
        i++; out.push(jsx('pre', { children: jsx('code', { children: buf.join('\n') }) }, out.length)); continue;
      }
      const h = /^(#{1,6})\s+(.*)$/.exec(line);
      if (h) { const level = Math.min(h[1].length, 4), id = level >= 2 && level <= 3 ? `hv-heading-${headingIndex++}` : undefined; out.push(jsx(`h${level}`, { id, children: inline(h[2], open, `h${out.length}`) }, out.length)); i++; continue; }
      if (/^(-{3,}|\*{3,})\s*$/.test(line)) { out.push(jsx('hr', {}, out.length)); i++; continue; }
      if (/^\s*[-*+]\s+/.test(line)) { const it = []; while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) it.push(lines[i++].replace(/^\s*[-*+]\s+/, '')); flush('ul', it); continue; }
      if (/^\s*\d+[.)]\s+/.test(line)) { const it = []; while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) it.push(lines[i++].replace(/^\s*\d+[.)]\s+/, '')); flush('ol', it); continue; }
      if (line.startsWith('>')) { const buf = []; while (i < lines.length && lines[i].startsWith('>')) buf.push(lines[i++].replace(/^>\s?/, '')); out.push(jsx('blockquote', { children: inline(buf.join(' '), open, `q${out.length}`) }, out.length)); continue; }
      if (line.startsWith('|') && /^\|[\s:|-]+\|\s*$/.test(lines[i + 1] || '')) {
        const cells = l => l.replace(/^\||\|\s*$/g, '').split('|').map(c => c.trim());
        const head = cells(line), rows = []; i += 2;
        while (i < lines.length && lines[i].startsWith('|')) rows.push(cells(lines[i++]));
        const n = out.length;
        out.push(jsx('table', { children: [
          jsx('thead', { children: jsx('tr', { children: head.map((c, j) => jsx('th', { children: inline(c, open, `th${n}-${j}`) }, j)) }) }, 'h'),
          jsx('tbody', { children: rows.map((r, a) => jsx('tr', { children: r.map((c, j) => jsx('td', { children: inline(c, open, `td${n}-${a}-${j}`) }, j)) }, a)) }, 'b'),
        ] }, n)); continue;
      }
      const buf = [];
      while (i < lines.length && lines[i].trim() && !/^(#{1,6}\s|```|>|\s*[-*+]\s|\s*\d+[.)]\s|\|)/.test(lines[i])) buf.push(lines[i++]);
      if (!buf.length) buf.push(lines[i++]);
      out.push(jsx('p', { children: inline(buf.join('\n'), open, `p${out.length}`) }, out.length));
    }
    return out;
  }, [body, open]);
  return jsx('div', { children: blocks });
}
const stripFrontmatter = text => {
  if (!text.startsWith('---')) return text;
  const end = text.indexOf('\n---', 3);
  return end < 0 ? text : text.slice(text.indexOf('\n', end + 1) + 1);
};

function NoteRow({ note, onOpen, sub, right, current, dirty, className = '' }) {
  return jsxs('button', { type: 'button', className: `hv-row ${className}`, 'aria-current': current ? 'true' : undefined, onClick: () => onOpen(note.path), children: [
    jsxs('span', { className: 'main', children: [
      jsx('div', { className: 'hv-title', children: note.title }),
      sub && jsx('div', { className: 'hv-sub', children: sub }),
    ] }),
    dirty && jsx('span', { className: 'hv-dot', 'aria-label': L('unsaved') }),
    right,
  ] });
}

function relativeTouchTime(at) {
  const minutes = Math.max(0, Math.floor((Date.now() - at) / 60000));
  if (minutes < 1) return L('justNow');
  if (minutes < 60) return L('minAgo', { n: minutes });
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return L('hAgo', { n: hours });
  return L('dAgo', { n: Math.floor(hours / 24) });
}
function useTouched(store) {
  const [records, setRecords] = useState(store.get());
  useEffect(() => store.subscribe(setRecords), [store]);
  return records;
}

const DESK_TABS = [['projects', 'projects'], ['recent', 'recent'], ['touched', 'touched']];

// The desk is built to live beside the chat at roughly half the window, so it
// shows one list at a time instead of every section at once.
function Home({ api, onOpen, touchedStore }) {
  const q = api.useRead('/dashboard');
  const touched = useTouched(touchedStore);
  const [tab, setTab] = useState(() => { const saved = api.storage?.get('desk-tab', 'projects'); return DESK_TABS.some(([id]) => id === saved) ? saved : 'projects'; });
  const [more, setMore] = useState(false);
  const deskRef = useRef(null);
  useEffect(() => { api.storage?.set('desk-tab', tab); setMore(false); }, [tab]);
  if (q.isPending) return jsx('div', { className: 'hv-home', role: 'status', children: jsx(Skeleton, { className: 'h-40 w-full' }) });
  if (q.isError) return jsx('div', { className: 'hv-home', children: jsx(ErrorState, { title: L('loadVaultFail'), description: String(q.error?.message || ''), children: btn(L('retry'), () => q.refetch()) }) });
  const d = q.data, now = new Date(), locale = pickLocale(d.locale || api.locale, navigator.language), needs = d.attention || [], due = d.due || [], hasTasks = Number(d.counts?.tasknotes ?? 0) > 0, sections = d.sections || {};
  const overdue = due.filter(n => n.overdue), soon = due.filter(n => !n.overdue && dueLabel(n.props?.due, now).tone === 'orange');
  const groups = Object.entries(d.in_progress || {}).sort((x, y) => y[1].length - x[1].length || projectName(x[0]).localeCompare(projectName(y[0]), 'en'));
  const visibleTabs = DESK_TABS.filter(([id]) => id !== 'projects' || groups.length > 0);
  const effectiveTab = hasTasks ? (visibleTabs.some(([id]) => id === tab) ? tab : 'recent') : 'recent';
  const recent = d.recent || [];
  const projectMark = label => label && jsxs('span', { className: 'hv-project', title: projectName(label), children: [jsx('i', { className: 'hv-project-dot', style: { '--project-color': projectColor(label) } }), jsx('span', { className: 'hv-project-name', children: projectName(label) })] });
  const meta = (label, tail, tone = '') => jsxs('span', { className: 'hv-d-meta', children: [projectMark(label), tail && jsx('span', { className: `hv-meta ${tone}`, children: tail })] });
  const figure = (count, label, tone, onClick) => jsxs('button', { type: 'button', className: `hv-d-fig ${count ? tone : 'zero'}`, onClick, children: [
    jsx('span', { className: 'hv-d-num', children: count }), jsx('span', { className: 'hv-d-label', children: label }),
  ] });
  const lists = {
    projects: groups.map(([name, items]) => {
      const late = due.filter(n => n.overdue && (n.props?.projects || []).some(p => projectName(p) === projectName(name))).length;
      return jsxs('div', { className: 'hv-group', children: [
        jsxs('div', { className: 'name', children: [jsx('i', { className: 'hv-project-dot', style: { '--project-color': projectColor(name) } }), jsx('span', { children: projectName(name) || L('unassigned') })] }),
        late > 0 && jsx('span', { className: 'hv-meta red', children: L('lateN', { n: late }) }),
        jsx('span', { className: 'hv-group-count', children: items.length }),
      ] }, name);
    }),
    recent: recent.map(n => jsx(NoteRow, { note: n, onOpen, sub: project(n) }, n.path)),
    touched: touched.map(r => jsx(NoteRow, { note: { path: r.path, title: noteTitle(r.path) }, onOpen,
      sub: `${relativeTouchTime(r.at)} · ${r.path.split('/').slice(0, -1).join(' / ') || L('vaultRoot')}` }, r.path)),
  };
  const counts = { projects: groups.length, recent: recent.length, touched: touched.length };
  const current = lists[effectiveTab] || [];
  const LIMIT = 6;
  const section = (title, items, empty) => jsxs('section', { className: 'hv-d-section', children: [
    jsxs('h2', { className: 'hv-d-h', children: [title, items.length > 0 && jsx('span', { className: 'hv-d-count', children: items.length })] }),
    items.length ? items : jsx('p', { className: 'hv-d-empty', children: empty }),
  ] });
  return jsxs('div', { className: 'hv-home hv-scroll', children: [
    hasTasks && jsxs('div', { className: 'hv-d-figs', children: [
      sections.attention && figure(needs.length, t('needs', {}, locale), '', () => document.getElementById('hv-d-needs')?.scrollIntoView({ behavior: 'smooth' })),
      figure(overdue.length, t('overdue', {}, locale), 'red', () => document.getElementById('hv-d-due')?.scrollIntoView({ behavior: 'smooth' })),
      figure(soon.length, t('within7', {}, locale), 'orange', () => document.getElementById('hv-d-due')?.scrollIntoView({ behavior: 'smooth' })),
    ] }),
    jsxs('div', { className: `hv-d-cols${hasTasks ? '' : ' single'}`, children: [
      hasTasks && jsxs('div', { className: 'hv-d-col', children: [
        hasTasks && sections.attention && jsx('div', { id: 'hv-d-needs', children: section(L('needs'), needs.map(n => {
          const blocked = n.props?.status === 'blocked', label = dueLabel(n.props?.due, now);
          return jsx(NoteRow, { note: n, onOpen, sub: meta((n.props?.projects || [])[0], blocked ? L('stalled') : label.text, blocked ? 'red' : label.tone) }, n.path);
        }), L('noNeeds')) }),
        hasTasks && jsx('div', { id: 'hv-d-due', children: section(L('due'), due.map(n => {
          const label = dueLabel(n.props?.due, now);
          return jsx(NoteRow, { note: n, onOpen, className: n.overdue ? 'hv-overdue' : '', sub: meta((n.props?.projects || [])[0], label.text, label.tone) }, n.path);
        }), L('noDue')) }),
      ] }),
      jsxs('section', { className: 'hv-d-section hv-d-desk', ref: deskRef, children: [
        jsx('div', { className: 'hv-d-tabs', role: 'tablist', children: visibleTabs.map(([id, label]) => jsxs('button', { type: 'button', role: 'tab', 'aria-selected': tab === id ? 'true' : 'false', onClick: () => setTab(id), children: [L(label), counts[id] > 0 && jsx('span', { className: 'hv-d-tabcount', children: counts[id] })] }, id)) }),
        current.length ? (more ? current : current.slice(0, LIMIT)) : jsx('p', { className: 'hv-d-empty', children: effectiveTab === 'touched' ? L('noTouched') : L('none') }),
        current.length > LIMIT && jsx('button', { type: 'button', className: 'hv-expand', onClick: () => setMore(v => !v), children: more ? L('close') : L('moreN', { n: current.length - LIMIT }) }),
      ] }),
    ] }),
  ] });
}

function FolderLevel({ api, path, depth, folder, setFolder, open, setOpen }) {
  const q = api.useRead(`/tree?path=${enc(path)}`);
  return (q.data?.folders || []).map(f => jsxs('div', { children: [
    jsxs('button', { type: 'button', className: 'hv-row hv-folder', style: { paddingLeft: 10 + depth * 16 }, 'aria-current': folder === f.path ? 'true' : undefined,
      onClick: () => { setFolder(f.path); setOpen(s => { const n = new Set(s); n.has(f.path) && folder === f.path ? n.delete(f.path) : n.add(f.path); return n; }); },
      children: [jsx(Codicon, { name: open.has(f.path) ? 'folder-opened' : 'folder' }), jsx('span', { className: 'main', children: f.name })] }),
    open.has(f.path) && jsx(FolderLevel, { api, path: f.path, depth: depth + 1, folder, setFolder, open, setOpen }),
  ] }, f.path));
}
function Folders({ api, folder, setFolder }) {
  const ancestors = p => p ? p.split('/').map((_, i, a) => a.slice(0, i + 1).join('/')) : [];
  const [open, setOpen] = useState(() => new Set(ancestors(folder)));
  useEffect(() => { setOpen(s => { const n = new Set(s); ancestors(folder).forEach(p => n.add(p)); return n; }); }, [folder]);
  return jsx(FolderLevel, { api, path: '', depth: 0, folder, setFolder, open, setOpen });
}

function PropertiesRail({ note, headings, active, onHeading, onOpen }) {
  const props = note.props || {};
  return jsxs('aside', { className: 'hv-rail', children: [
    jsxs('section', { className: 'hv-rail-section', children: [jsx('h2', { className: 'hv-rail-title', children: L('properties') }),
      jsx('div', { className: 'hv-tags', children: (note.tags || []).map((tag, i) => jsx('span', { className: 'hv-tag', children: String(tag) }, `${tag}-${i}`)) }),
      Object.entries(props).filter(([key]) => key !== 'tags').map(([key, value]) => jsxs('div', { className: 'hv-prop', children: [jsx('span', { className: 'hv-prop-key', children: key }), jsx('span', { children: Array.isArray(value) ? value.map(clean).join(' · ') : String(value ?? '') })] }, key)),
    ] }),
    jsxs('section', { className: 'hv-rail-section', children: [jsx('h2', { className: 'hv-rail-title', children: L('contents') }),
      headings.length ? jsx('div', { className: 'hv-toc', children: headings.map(item => jsx('button', { type: 'button', 'data-level': item.level, 'data-active': active === item.id ? 'true' : 'false', onClick: () => onHeading(item.id), children: item.text }, item.id)) }) : jsx('span', { className: 'hv-sub', children: L('noHeadings') }),
    ] }),
    jsxs('section', { className: 'hv-rail-section', children: [jsx('h2', { className: 'hv-rail-title', children: L('backlinksN', { n: note.backlinks?.length || 0 }) }),
      (note.backlinks || []).slice(0, 20).map(path => jsx('div', { className: 'hv-backlinks', children: jsx('button', { type: 'button', className: 'hv-link', onClick: () => onOpen(path), children: noteTitle(path) }) }, path)),
    ] }),
  ] });
}

function NotePane({ api, path, onOpen, dirtyRef, touchedStore, setQuoteAction, os }) {
  const q = api.useRead(`/note?path=${enc(path)}`);
  const [draft, setDraft] = useState(null);      // null = reading
  const [base, setBase] = useState(null);        // sha256 the draft started from
  const [disk, setDisk] = useState(null);        // newer on-disk version, when it diverged
  const [compare, setCompare] = useState(false);
  const [busy, setBusy] = useState(false);
  const note = q.data;
  const dirty = draft !== null && note && draft !== note.content;
  const docRef = useRef(null);
  const [quotePos, setQuotePos] = useState(null);
  const [selectedText, setSelectedText] = useState('');
  const headingItems = headingsOf(note?.content ? stripFrontmatter(note.content) : '');
  const [activeHeading, setActiveHeading] = useState('');
  dirtyRef.current = dirty ? path : null;

  useEffect(() => {
    const root = docRef.current?.closest('.hv-note-main');
    if (!root || !headingItems.length || typeof IntersectionObserver === 'undefined') return undefined;
    const observer = new IntersectionObserver(entries => {
      const visible = entries.filter(entry => entry.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
      if (visible[0]) setActiveHeading(visible[0].target.id);
    }, { root, rootMargin: '-12% 0px -72% 0px', threshold: 0 });
    for (const item of headingItems) { const el = docRef.current.querySelector(`#${item.id}`); if (el) observer.observe(el); }
    return () => observer.disconnect();
  }, [path, note?.content]);

  useEffect(() => {
    const update = () => {
      const selection = window.getSelection();
      const range = selection?.rangeCount ? selection.getRangeAt(0) : null;
      if (draft !== null || !range || !docRef.current?.contains(range.commonAncestorContainer)) {
        setQuotePos(null); setSelectedText(''); return;
      }
      const text = selection.toString(), rect = range.getBoundingClientRect();
      if (!text.trim() || !rect.width || !rect.height) { setQuotePos(null); setSelectedText(''); return; }
      setSelectedText(text);
      const below = rect.bottom + 8, top = below + 34 <= window.innerHeight ? below : Math.max(8, rect.top - 42);
      setQuotePos({ left: Math.max(8, Math.min(rect.left, window.innerWidth - 132)), top });
    };
    document.addEventListener('selectionchange', update);
    return () => document.removeEventListener('selectionchange', update);
  }, [draft, path]);
  async function quoteSelection() {
    const text = selectedText;
    if (!text.trim() || draft !== null) return;
    const quoted = quoteBlock(text, `${api.root.replace(/\/+$/, '')}/${path}`);
    let inserted = false;
    try { inserted = await host.composer.insertText(null, quoted, { mode: 'block' }); } catch { /* clipboard fallback */ }
    if (!inserted) {
      const sessionId = host.state.focusedSessionId.get();
      if (sessionId) try { inserted = await host.composer.insertText(sessionId, quoted, { mode: 'block' }); } catch { /* clipboard fallback */ }
    }
    if (!inserted) {
      await os.writeClipboard(quoted);
      host.notify({ kind: 'info', message: L('quoteClipboard') });
    } else {
      host.notify({ kind: 'success', message: L('quoteInserted') });
      host.composer.focus(null);
    }
    setQuotePos(null);
  }
  useEffect(() => { setQuoteAction(quoteSelection); return () => setQuoteAction(null); }, [path, selectedText, draft]);

  useEffect(() => {
    let seen = null;
    return touchedStore.subscribe(records => {
      const record = records.find(item => item.path === path);
      if (!record || record.at === seen) return;
      seen = record.at;
      void (async () => {
        try {
          const current = await api.rest(`/note?path=${enc(path)}`);
          if (dirty) { if (current.sha256 !== base) setDisk(current); }
          else if (draft !== null) { setDraft(current.content); setBase(current.sha256); setDisk(null); }
          else { await q.refetch(); }
        } catch { /* the next index refresh or poll can retry */ }
      })();
    });
  }, [touchedStore, path, draft, base, dirty]);

  // While a draft is open, notice when Hermes or Obsidian rewrites the same file.
  useEffect(() => {
    if (draft === null || disk) return undefined;
    const id = setInterval(async () => {
      try { const now = await api.rest(`/note?path=${enc(path)}`); if (now.sha256 !== base) setDisk(now); } catch { /* next tick */ }
    }, 8000);
    return () => clearInterval(id);
  }, [draft === null, disk, base, path]);

  const keysRef = useRef(null);
  useEffect(() => {
    const onKey = e => keysRef.current?.(e);
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
  const openLink = useMemo(() => target => {
    const hit = (note?.links || []).find(p => p === `${target}.md` || p.endsWith(`/${target.split('#')[0]}.md`) || p === target);
    if (hit) onOpen(hit); else host.notify({ kind: 'info', message: L('linkMissing') });
  }, [note, onOpen]);

  if (q.isPending) return jsx('div', { className: 'hv-doc', role: 'status', children: jsx(Skeleton, { className: 'h-40 w-full' }) });
  if (q.isError) return jsx(ErrorState, { title: L('openFail'), description: String(q.error?.message || ''), children: btn(L('retry'), () => q.refetch()) });

  const done = fresh => { setDraft(null); setDisk(null); setCompare(false); setBase(null); queryClient.invalidateQueries({ queryKey: api.cache }); return fresh; };
  async function save(overwriteSha) {
    setBusy(true);
    try {
      await api.rest('/note', { method: 'PUT', body: { path, content: draft, base_sha256: overwriteSha || base } });
      done(); host.notify({ kind: 'success', message: L('saved') });
    } catch (error) {
      // A refused save may be a conflict; read the disk to tell it apart from a real failure.
      try { const now = await api.rest(`/note?path=${enc(path)}`); if (now.sha256 !== (overwriteSha || base)) { setDisk(now); return; } } catch { /* fall through */ }
      host.notify({ kind: 'error', message: L('saveFail', { err: error?.message || '' }) });
    } finally { setBusy(false); }
  }

  const startEdit = () => { setDraft(note.content); setBase(note.sha256); };
  keysRef.current = e => {
    const action = editKeyAction(e, { editing: draft !== null, dirty });
    if (!action) return;
    e.preventDefault();
    if (action === 'edit') startEdit();
    else if (action === 'save' && !busy) save();
    else if (action === 'cancel') done();
  };
  const crumb = path.split('/').slice(0, -1).join(' / ');
  const markdownBody = stripFrontmatter(note.content);
  const titleLine = markdownBody.indexOf('# ');
  const body = titleLine >= 0 ? markdownBody.slice(markdownBody.indexOf('\n', titleLine) + 1).trimStart() : markdownBody;
  return jsxs('div', { className: 'hv-note-layout', children: [jsxs('div', { className: 'hv-scroll hv-note-scroll', style: { height: '100%' }, children: [
    disk && jsxs('div', { className: 'hv-warn', role: 'alert', children: [
      jsx('h3', { children: L('conflictTitle') }),
      jsx('p', { children: L('conflictBody', { time: day(disk.mtime_ns).toLocaleTimeString(LOCALE, { hour: '2-digit', minute: '2-digit' }) }) }),
      jsxs('div', { className: 'hv-actions', children: [
        btn(L('keepMine'), () => save(disk.sha256), { variant: 'default', disabled: busy }),
        btn(L('loadDisk'), () => done()),
        btn(compare ? L('stopCompare') : L('compare'), () => setCompare(v => !v), { variant: 'ghost' }),
      ] }),
    ] }),
    jsxs('div', { className: 'hv-bar', children: draft === null ? [jsx('span', { className: 'hv-bar-hint', children: L('editHint') }, 'h'), jsxs(Button, { type: 'button', variant: 'outline', size: 'sm', onClick: startEdit, children: [jsx(Codicon, { name: 'edit' }), ` ${L('edit')}`] }, 'e')]
      : [jsxs('span', { className: 'hv-unsaved', children: dirty ? [jsx('span', { className: 'hv-dot', style: { margin: 0 } }, 'd'), L('dirty')] : L('clean') }, 'u'),
        btn(L('cancel'), () => done(), { key: 'x', variant: 'ghost' }),
        btn(L('saveKey'), () => save(), { key: 's', variant: 'default', disabled: busy || !dirty })] }),
    compare && disk ? jsxs('div', { className: 'hv-diff', children: [
      jsxs('div', { children: [jsx('div', { className: 'hv-sub', children: L('mine') }), jsx('pre', { children: draft })] }),
      jsxs('div', { children: [jsx('div', { className: 'hv-sub', children: L('disk') }), jsx('pre', { children: disk.content })] }),
    ] }) : jsxs('div', { className: `hv-doc hv-read-doc${draft === null ? '' : ' editing'}`, ref: docRef, onDoubleClick: draft === null ? e => { if (!window.getSelection()?.toString()) startEdit(); } : undefined, children: draft === null ? [
      jsx('div', { className: 'hv-breadcrumb', children: crumb }, 'c'),
      jsx('h1', { children: note.title }, 't'),
      jsx('div', { className: 'hv-created', children: L('createdOn', { d: String(note.props?.created || '').slice(0, 10) }) }, 'created'),
      jsx(Markdown, { body, open: openLink }, 'm'),
    ] : [jsx('div', { className: 'hv-breadcrumb', children: `${crumb} · ${L('editing')}` }, 'c'), jsx('textarea', { className: 'hv-edit', value: draft, spellCheck: false, autoFocus: true, 'aria-label': L('noteBody'), ref: el => { if (el) { el.style.height = 'auto'; el.style.height = `${el.scrollHeight}px`; } }, onChange: e => setDraft(e.target.value) }, 'ed')] }),
    quotePos && jsx(Button, { type: 'button', className: 'hv-quote', style: quotePos, onMouseDown: e => e.preventDefault(), onClick: quoteSelection, children: L('quoteToChat') }),
  ] }), jsx(PropertiesRail, { note, headings: headingItems, active: activeHeading, onHeading: id => docRef.current?.querySelector(`#${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }), onOpen })] });
}

// The folder being browsed wins; otherwise new notes go to the configured inbox, else the vault root.
export function newNoteFolder(current, inbox) {
  return current || inbox || '';
}

function NewNote({ api, folder, open, onClose, onCreated }) {
  const [title, setTitle] = useState('');
  const [dir, setDir] = useState(folder || '');
  const [type, setType] = useState('reference');
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) { setTitle(''); setDir(folder || ''); } }, [open, folder]);
  const today = new Date().toLocaleDateString('sv-SE');
  const name = title.trim().replace(/[\\/:*?"<>|#^[\]]/g, ' ').replace(/\s+/g, ' ').trim();
  async function create() {
    setBusy(true);
    const path = `${dir.replace(/^\/+|\/+$/g, '')}/${name}.md`;
    const content = `---\ntags:\n  - type/${type}\n  - state/processing\ncreated: ${today}\n---\n\n# ${title.trim()}\n\n`;
    try { await api.rest('/note', { method: 'POST', body: { path, content } }); queryClient.invalidateQueries({ queryKey: api.cache }); onCreated(path); }
    catch (error) { host.notify({ kind: 'error', message: L('createFail', { err: error?.message || '' }) }); }
    finally { setBusy(false); }
  }
  return jsx(Dialog, { open, onOpenChange: v => { if (!v) onClose(); }, children: jsxs(DialogContent, { children: [
    jsx(DialogHeader, { children: jsx(DialogTitle, { children: L('newNote') }) }),
    jsxs('div', { className: 'hv-form', children: [
      jsxs('label', { children: [L('title'), jsx(Input, { value: title, autoFocus: true, onChange: e => setTitle(e.target.value) })] }),
      jsxs('label', { children: [L('folder'), jsx(Input, { value: dir, onChange: e => setDir(e.target.value) })] }),
      jsxs('div', { children: [
        jsx('div', { className: 'hv-sub', style: { marginBottom: 6 }, children: L('type') }),
        jsx('div', { className: 'hv-chips', children: TYPES.map(t => btn(`type/${t}`, () => setType(t), { key: t, size: 'sm', variant: type === t ? 'default' : 'secondary', 'aria-pressed': type === t })) }),
      ] }),
      jsx('p', { className: 'hv-sub', children: L('createHint', { type, today }) }),
    ] }),
    jsxs(DialogFooter, { children: [btn(L('cancel'), onClose, { variant: 'ghost' }), btn(L('create'), create, { variant: 'default', disabled: busy || !name || !dir.trim() })] }),
  ] }) });
}

function Setup({ api, initial, onDone }) {
  const [root, setRoot] = useState(initial?.root || '');
  const [busy, setBusy] = useState(false);
  const [attentionField, setAttentionField] = useState(initial?.attention_field || '');
  const [inboxFolder, setInboxFolder] = useState(initial?.inbox_folder || '');
  const [locale, setLocale] = useState(initial?.locale || 'auto');
  async function apply() {
    setBusy(true);
    try { await api.rest('/config', { method: 'PUT', body: { root: root.trim(), ...(initial?.exclude ? { exclude: initial.exclude } : {}), attention_field: attentionField.trim() || null, inbox_folder: inboxFolder.trim() || null, locale } }); await api.rest('/refresh', { method: 'POST' }); queryClient.invalidateQueries({ queryKey: api.cache }); onDone?.(); }
    catch (error) { host.notify({ kind: 'error', message: L('rootFail', { err: error?.message || '' }) }); }
    finally { setBusy(false); }
  }
  return jsxs('div', { className: 'hv-setup', children: [
    jsx('h2', { className: 'hv-h1', children: initial ? L('setupEditTitle') : L('setupTitle') }),
    jsx('p', { className: 'hv-sub', children: L('setupHint') }),
    jsx(Input, { value: root, placeholder: '/path/to/your/vault', onChange: e => setRoot(e.target.value) }),
    jsxs('label', { className: 'hv-field', children: [L('attentionLabel'), jsx(Input, { value: attentionField, placeholder: 'needs_review', onChange: e => setAttentionField(e.target.value) })] }),
    jsxs('label', { className: 'hv-field', children: [L('inboxLabel'), jsx(Input, { value: inboxFolder, placeholder: 'Inbox', onChange: e => setInboxFolder(e.target.value) })] }),
    jsxs('label', { className: 'hv-field', children: [L('language'), jsx('select', { className: 'hv-select', value: locale, onChange: e => setLocale(e.target.value), children: [jsx('option', { value: 'auto', children: 'Auto' }), jsx('option', { value: 'en', children: 'English' }), jsx('option', { value: 'ja', children: '\u65e5\u672c\u8a9e' })] })] }),
    jsx('div', { style: { display: 'flex', gap: 8 }, children: [onDone && btn(L('cancel'), onDone, { key: 'c', variant: 'ghost' }), btn(busy ? L('indexing') : initial ? L('save') : L('useFolder'), apply, { variant: 'default', key: 'a', disabled: busy || !root.trim().startsWith('/') })] }),
  ] });
}

function Page({ api }) {
  const status = api.useRead('/status');
  const [view, setView] = useState('home');
  const [folder, setFolder] = useState('');
  const [path, setPath] = useState(null);
  const [search, setSearch] = useState('');
  const [creating, setCreating] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [navCollapsed, setNavCollapsed] = useState(() => api.storage?.get('read-nav-collapsed', false) === true);
  useEffect(() => { api.storage?.set('read-nav-collapsed', navCollapsed); }, [navCollapsed]);
  const dirtyRef = useRef(null);
  const configured = status.data?.configured;
  api.locale = pickLocale(status.data?.locale || 'auto', navigator.language);
  setUiLocale(api.locale);
  api.root = status.data?.root || api.root;

  // One incremental index refresh per visit; it only re-reads notes that changed.
  useEffect(() => {
    if (!configured) return;
    let live = true;
    api.rest('/refresh', { method: 'POST' }).then(() => { if (live) queryClient.invalidateQueries({ queryKey: api.cache }); }).catch(() => {});
    return () => { live = false; };
  }, [configured]);

  const term = search.trim();
  const list = api.useRead(term ? `/search?q=${enc(term)}&limit=50` : `/notes?folder=${enc(folder)}&sort=mtime&limit=200`, configured && (view === 'browse' || !!term));
  function open(next) {
    if (dirtyRef.current && dirtyRef.current !== next && !window.confirm(L('discard'))) return;
    setPath(next); setFolder(next.split('/').slice(0, -1).join('/')); setSearch(''); setView('browse');
  }
  const openRef = useRef(open);
  openRef.current = open;
  useEffect(() => {
    if (!configured || !api.openStore) return undefined;
    const take = () => { const next = api.openStore.take(); if (next) openRef.current(next); };
    take();
    return api.openStore.subscribe(take);
  }, [configured]);
  function goHome() { if (dirtyRef.current && !window.confirm(L('discard'))) return; setPath(null); setSearch(''); setView('home'); }
  function goFolder(next) { if (dirtyRef.current && !window.confirm(L('discard'))) return; setFolder(next); setPath(null); setSearch(''); setView('browse'); }

  if (status.isPending) return jsx('div', { className: 'hv', role: 'status', children: jsx(Skeleton, { className: 'h-40 w-full' }) });
  if (status.isError) return jsx(ErrorState, { title: L('backendFail'), description: L('backendHint') + String(status.error?.message || ''), children: btn(L('retry'), () => status.refetch()) });
  if (!configured) return jsxs('div', { className: 'hv', children: [jsx('style', { children: CSS }), jsx(Setup, { api })] });

  const rows = list.data || [];
  const showList = view === 'browse' || term;
  return jsxs('div', { className: 'hv', children: [
    jsx('style', { children: CSS }),
    jsxs('div', { className: 'hv-top', children: [
      showList && jsx('button', { type: 'button', className: 'hv-home-btn hv-back', 'aria-label': L('backHome'), title: L('backHome'), onClick: goHome, children: [jsx(Codicon, { name: 'home' }, 'i'), ` ${L('home')}`] }),
      jsx('div', { className: 'grow', children: jsx(SearchField, { placeholder: L('searchNotes'), 'aria-label': L('searchNotes'), value: search, onChange: setSearch }) }),
      jsx('span', { className: 'hv-top-tools' }),
      jsx('span', { className: 'hv-top-date', children: L('todayIs', { date: new Date().toLocaleDateString(LOCALE, { month: 'long', day: 'numeric', weekday: 'short' }) }) }),
      jsx('button', { type: 'button', className: 'hv-home-btn', 'aria-label': L('settings'), title: L('settings'), onClick: () => setSettingsOpen(v => !v), children: jsx(Codicon, { name: 'settings-gear' }) }),
      btn([jsx(Codicon, { name: 'add' }, 'i'), ` ${L('newNote')}`], () => setCreating(true), { variant: 'default' }),
    ] }),
    settingsOpen ? jsx(Setup, { api, initial: status.data, onDone: () => setSettingsOpen(false) }) : !showList ? jsx(Home, { api, onOpen: open, touchedStore: api.touchedStore }) : jsxs('div', { className: `hv-read-layout${navCollapsed ? ' left-collapsed' : ''}`, children: [
      jsxs('div', { className: 'hv-read-nav', children: [
        jsxs('div', { className: 'hv-nav-head', children: [jsx('span', { className: 'hv-nav-title', children: navCollapsed ? '' : L('notes') }), jsx('button', { type: 'button', className: 'hv-collapse', 'aria-label': navCollapsed ? L('expandList') : L('collapseList'), onClick: () => setNavCollapsed(v => !v), children: jsx(Codicon, { name: navCollapsed ? 'chevron-right' : 'chevron-left' }) })] }),
        !navCollapsed && jsxs('div', { children: [
          jsx('div', { className: 'hv-nav-folders', children: jsx(Folders, { api, folder, setFolder: goFolder }) }),
          jsx('div', { className: 'hv-nav-notes hv-scroll hv-list', children: list.isPending ? jsx(Skeleton, { className: 'h-24 w-full' })
            : rows.length ? rows.map(n => jsx(NoteRow, { note: n, onOpen: open, current: n.path === path, dirty: dirtyRef.current === n.path,
              sub: term ? n.path.split('/').slice(0, -1).join(' / ') : `${dayLabel(n.mtime_ns)}${typeOf(n) ? ` · ${typeOf(n)}` : ''}` }, n.path))
            : jsx(EmptyState, { title: term ? L('notFound') : L('emptyFolder') }) }),
        ] }),
      ] }),
      jsx('div', { className: 'hv-note-main', children: path ? jsx(NotePane, { api, path, onOpen: open, dirtyRef,
        touchedStore: api.touchedStore, setQuoteAction: fn => { api.quoteAction.current = fn; }, os: api.os }, path)
        : jsx(EmptyState, { title: L('pickNote'), description: L('pickNoteHint') }) }),
    ] }),
    jsx(NewNote, { api, folder: newNoteFolder(folder, status.data?.inbox_folder), open: creating, onClose: () => setCreating(false), onCreated: p => { setCreating(false); open(p); } }),
  ] });
}

export default {
  id: 'hermes-lectern', name: 'Hermes Lectern', defaultEnabled: true,
  register(ctx) {
    let disposed = false, vaultRoot = null, refreshCancel = null;
    const quoteAction = { current: null };  // set by the open NotePane; read by the palette command
    // A file opened elsewhere in Desktop waits here until the Lectern page takes it.
    let pendingOpen = null;
    const openListeners = new Set();
    const openStore = {
      take() { const next = pendingOpen; pendingOpen = null; return next; },
      subscribe(fn) { openListeners.add(fn); return () => openListeners.delete(fn); },
    };
    // claims() must answer synchronously, so learn the root up front.
    ctx.rest('/status').then(status => {
      if (!disposed && status?.configured && typeof status.root === 'string') vaultRoot = status.root;
    }).catch(() => {});
    const cache = [...KEY, ctx.source];
    let touched = ctx.storage.get('touched', []);
    if (!Array.isArray(touched)) touched = [];
    const listeners = new Set();
    const touchedStore = {
      get: () => touched,
      subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); },
    };
    const publishTouches = next => {
      touched = next; ctx.storage.set('touched', touched);
      for (const listener of listeners) listener(touched);
    };
    const scheduleRefresh = () => {
      refreshCancel?.();
      refreshCancel = ctx.setTimeout(async () => {
        refreshCancel = null;
        try { await ctx.rest('/refresh', { method: 'POST' }); queryClient.invalidateQueries({ queryKey: cache }); } catch { /* the next visit refreshes */ }
      }, 1500);
    };
    ctx.onEvent('tool.complete', async event => {
      if (disposed || !event?.payload || !Object.hasOwn(TOUCH_TOOLS, event.payload.name)) return;
      if (!vaultRoot) {
        try {
          const status = await ctx.rest('/status');
          if (disposed || !status?.configured || typeof status.root !== 'string') return;
          vaultRoot = status.root;
        } catch { return; }
      }
      const candidate = touchFromEvent(event?.payload, vaultRoot);
      if (!candidate) return;
      try {
        const verified = await ctx.rest(`/note?path=${enc(candidate.path)}`);
        if (disposed || !verified || typeof verified.content !== 'string') return;
        const record = { path: candidate.path, sessionId: typeof event.session_id === 'string' ? event.session_id : null,
          tool: candidate.tool, at: Date.now() };
        publishTouches(addTouch(touched, record));
        scheduleRefresh();
      } catch { /* missing, outside-vault and non-text paths are not touches */ }
    });
    function Scoped() {
      const connection = useValue(host.state.connectionId) || 'local';
      const profile = useValue(host.state.profile) || 'default';
      const scopeCache = [...cache, connection, profile];
      const api = {
        cache: scopeCache, root: vaultRoot || '', touchedStore, openStore, os: ctx.os, quoteAction, storage: ctx.storage,
        rest: (path, opts) => ctx.rest(path, opts),
        useRead: (path, enabled = true) => useQuery({ queryKey: [...scopeCache, path], enabled: enabled && !disposed, retry: false, queryFn: () => ctx.rest(path) }),
      };
      return jsx(Page, { api }, `${connection}/${profile}`);
    }
    ctx.onDispose(() => {
      disposed = true; refreshCancel?.(); listeners.clear(); openListeners.clear();
      void queryClient.cancelQueries({ queryKey: cache }); queryClient.removeQueries({ queryKey: cache });
    });
    ctx.registerMany([
      { id: 'page', area: ROUTES_AREA, data: { path: '/lectern' }, render: () => jsx(Scoped, {}) },
      // Literal area id: older Desktop builds do not export FILE_OPENER_AREA and simply ignore it.
      { id: 'vault-notes', area: 'preview.fileOpener', data: {
        claims: path => !disposed && vaultOpenTarget(vaultRoot, path) !== null,
        open: path => {
          pendingOpen = vaultOpenTarget(vaultRoot, path);
          for (const listener of openListeners) listener();
          host.navigate('/lectern');
        },
      } },
      { id: 'nav', area: SIDEBAR_NAV_AREA, data: { path: '/lectern', label: 'Lectern', codicon: 'notebook' } },
      { id: 'open', area: PALETTE_AREA, data: { id: 'hermes-lectern.open', label: L('openVault'), keywords: ['lectern', 'vault', 'obsidian', 'notes'], run: () => host.navigate('/lectern') } },
      { id: 'quote', area: PALETTE_AREA, data: { id: 'hermes-lectern.quote', label: L('paletteQuote'), keywords: ['quote', 'vault'], run: () => quoteAction.current?.() } },
    ]);
  },
};
