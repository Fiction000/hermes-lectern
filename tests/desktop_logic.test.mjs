import test from 'node:test';
import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';

const stubs = new Map([
  ['@hermes/plugin-sdk', new URL('./stubs/plugin-sdk.mjs', import.meta.url)],
  ['react', new URL('./stubs/react.mjs', import.meta.url)],
  ['react/jsx-runtime', new URL('./stubs/jsx-runtime.mjs', import.meta.url)],
]);
registerHooks({ resolve(specifier, context, nextResolve) {
  const url = stubs.get(specifier);
  return url ? { url: url.href, shortCircuit: true } : nextResolve(specifier, context);
} });
const plugin = await import('../desktop/plugin.js');
const { addTouch, quoteBlock, toVaultRelative, TOUCH_TOOLS, touchFromEvent } = plugin;
const { projectColor, dueLabel, headingsOf } = plugin;

test('projectColor hashes labels deterministically without personal project tables', () => {
  assert.equal(projectColor('[[Alpha|Alpha project]]'), projectColor('Alpha'));
  assert.equal(projectColor('A project'), projectColor('A project'));
  assert.match(projectColor('A project'), /^#[0-9a-f]{6}$/i);
  assert.equal(plugin.KNOWN_PROJECTS, undefined);
});

test('dueLabel handles overdue, today, tomorrow, seven-day and neutral dates', () => {
  const today = '2026-11-16';
  assert.deepEqual(dueLabel('2026-11-15', today, 'ja'), { text: '1日超過', tone: 'red' });
  assert.deepEqual(dueLabel('2026-11-16', today, 'ja'), { text: '今日', tone: 'orange' });
  assert.deepEqual(dueLabel('2026-11-17', today, 'ja'), { text: '明日 11/17', tone: 'orange' });
  assert.deepEqual(dueLabel('2026-11-23', today, 'ja'), { text: 'あと 7 日', tone: 'orange' });
  assert.deepEqual(dueLabel('2026-11-24', today, 'ja'), { text: '11/24', tone: 'neutral' });
  assert.deepEqual(dueLabel('2026-11-17', today), { text: 'Tomorrow 11/17', tone: 'orange' });
});

test('headingsOf returns h2/h3 headings outside fenced code blocks', () => {
  assert.deepEqual(headingsOf('## First\n### Nested\n```md\n## ignored\n```\n~~~\n### also ignored\n~~~\n# not in toc'), [
    { level: 2, text: 'First', id: 'hv-heading-0' },
    { level: 3, text: 'Nested', id: 'hv-heading-1' },
  ]);
});

test('toVaultRelative enforces normalized vault containment and markdown policy', () => {
  const root = '/Users/alex/Notes Vault';
  assert.equal(toVaultRelative(root, `${root}/Projects/a.md`), 'Projects/a.md');
  assert.equal(toVaultRelative(root, '/Users/alex/Documents/out.md'), null);
  assert.equal(toVaultRelative(root, `${root}/../escape.md`), null);
  assert.equal(toVaultRelative(root, `${root}2/x.md`), null);
  assert.equal(toVaultRelative(root, '~/Notes Vault/Projects/a.md'), 'Projects/a.md');
  assert.equal(toVaultRelative('/vault', '~/a.md'), null);
  assert.equal(toVaultRelative(root, `${root}/a.txt`), null);
  assert.equal(toVaultRelative(root, `${root}/.trash/a.md`), null);
  assert.equal(toVaultRelative(root, `${root}/.obsidian/a.md`), null);
  assert.equal(toVaultRelative(root, `${root}//Projects/./a.md`), 'Projects/a.md');
});

test('addTouch deduplicates newest-first and caps at fifty', () => {
  const records = Array.from({ length: 51 }, (_, i) => ({ path: `n${i}.md`, at: i }));
  const result = addTouch(records, { path: 'n10.md', at: 99 });
  assert.equal(result.length, 50);
  assert.deepEqual(result[0], { path: 'n10.md', at: 99 });
  assert.equal(result.filter(x => x.path === 'n10.md').length, 1);
  assert.equal(result[1].path, 'n0.md');
});

test('quoteBlock prefixes lines and cites absolute source', () => {
  assert.equal(quoteBlock('alpha\n\nbeta  \n', '/vault/Notes/a.md'), '> alpha\n>\n> beta\n\nSource: /vault/Notes/a.md');
  assert.equal(quoteBlock('alpha', '/v/a.md', 'ja'), '> alpha\n\n\u51fa\u5178: /v/a.md');
});

test('TOUCH_TOOLS only accepts successful known writes to vault markdown paths', () => {
  assert.deepEqual(TOUCH_TOOLS, { write_file: 'path', patch: 'path' });
  const root = '/vault';
  assert.deepEqual(touchFromEvent({ name: 'write_file', args: { path: '/vault/A.md' }, result: { success: true } }, root), { path: 'A.md', tool: 'write_file' });
  assert.equal(touchFromEvent({ name: 'patch', args: { path: '/vault/A.md' }, result: { error: 'failed' } }, root), null);
  assert.equal(touchFromEvent({ name: 'write_file', args: { path: '/vault/A.md' }, result: '{"error":"failed"}' }, root), null);
  assert.equal(touchFromEvent({ name: 'read_file', args: { path: '/vault/A.md' }, result: {} }, root), null);
});

test('noteTitle strips folder and .md for touched rows', async () => {
  const { noteTitle } = await import('../desktop/plugin.js');
  assert.equal(noteTitle('Projects/Plans/計画.md'), '計画');
  assert.equal(noteTitle('a.mdx.md'), 'a.mdx');
});

test('palette quote command runs without an open note', async () => {
  const plugin = (await import('../desktop/plugin.js')).default;
  const contributions = [];
  const ctx = { source: 'plugin:hermes-lectern', storage: { get: (_k, d) => d, set() {} }, onEvent() {}, onDispose() {},
    setTimeout: () => () => {}, rest: async () => ({}), os: {}, registerMany: cs => contributions.push(...cs) };
  plugin.register(ctx);
  const quote = contributions.find(c => c.id === 'quote');
  assert.ok(quote, 'quote command registered');
  assert.doesNotThrow(() => quote.data.run());
});

test('vaultOpenTarget accepts only Markdown notes inside the vault', async () => {
  const { vaultOpenTarget } = await import('../desktop/plugin.js');
  const root = '/Users/alex/Notes Vault';
  assert.equal(vaultOpenTarget(root, `${root}/Projects/計画.md`), 'Projects/計画.md');
  assert.equal(vaultOpenTarget(root, `${root}/Projects/計画.MD`), null);  // the backend only serves .md
  assert.equal(vaultOpenTarget(root, `${root}/Attachments/a.png`), null);
  assert.equal(vaultOpenTarget(root, '/Users/alex/Documents/Main/a.md'), null);
  assert.equal(vaultOpenTarget(root, `${root}/../Main/a.md`), null);
  assert.equal(vaultOpenTarget(null, `${root}/a.md`), null);
});

test('file opener claims vault notes once the root is known and opens them in the Vault page', async () => {
  const { host } = await import('@hermes/plugin-sdk');
  const navigated = [];
  host.navigate = to => navigated.push(to);
  const plugin = (await import('../desktop/plugin.js')).default;
  const contributions = [];
  const root = '/v/Notes Vault';
  const ctx = { source: 'plugin:hermes-lectern', storage: { get: (_k, d) => d, set() {} }, onEvent() {}, onDispose() {},
    setTimeout: () => () => {}, os: {}, registerMany: cs => contributions.push(...cs),
    rest: async path => (path === '/status' ? { configured: true, root } : {}) };
  plugin.register(ctx);
  const opener = contributions.find(c => c.area === 'preview.fileOpener');
  assert.ok(opener, 'file opener registered');
  await new Promise(r => setTimeout(r, 0));
  assert.equal(opener.data.claims(`${root}/A/b.md`), true);
  assert.equal(opener.data.claims(`${root}/A/b.png`), false);
  assert.equal(opener.data.claims('/elsewhere/b.md'), false);
  opener.data.open(`${root}/A/b.md`);
  assert.deepEqual(navigated, ['/lectern']);
});

test('editKeyAction maps reader shortcuts', async () => {
  const { editKeyAction } = await import('../desktop/plugin.js');
  const k = (key, mods = {}) => ({ key, metaKey: false, ctrlKey: false, ...mods });
  assert.equal(editKeyAction(k('e', { metaKey: true }), { editing: false, dirty: false }), 'edit');
  assert.equal(editKeyAction(k('e', { metaKey: true }), { editing: true, dirty: false }), null);
  assert.equal(editKeyAction(k('s', { metaKey: true }), { editing: true, dirty: true }), 'save');
  assert.equal(editKeyAction(k('s', { ctrlKey: true }), { editing: true, dirty: false }), null);
  assert.equal(editKeyAction(k('Escape'), { editing: true, dirty: false }), 'cancel');
  assert.equal(editKeyAction(k('Escape'), { editing: true, dirty: true }), null);
  assert.equal(editKeyAction(k('s'), { editing: true, dirty: true }), null);
});


test('pickLocale honors explicit settings and auto detects Japanese', () => {
  const { pickLocale } = plugin;
  assert.equal(pickLocale('en', 'ja-JP'), 'en');
  assert.equal(pickLocale('ja', 'en-US'), 'ja');
  assert.equal(pickLocale('auto', 'ja-JP'), 'ja');
  assert.equal(pickLocale('auto', 'en-US'), 'en');
});

test('English and Japanese string tables have identical keys', () => {
  const { STRINGS } = plugin;
  assert.deepEqual(Object.keys(STRINGS.en).sort(), Object.keys(STRINGS.ja).sort());
});

test('plugin source contains Japanese only in its ja string table', async () => {
  const { readFile } = await import('node:fs/promises');
  const source = await readFile(new URL('../desktop/plugin.js', import.meta.url), 'utf8');
  const outsideJa = source.replace(/\/\/ i18n:ja-start[\s\S]*?\/\/ i18n:ja-end/, '');
  assert.doesNotMatch(outsideJa, /[\u3040-\u30ff\u4e00-\u9fff]/);
});

test('every t() key used in plugin.js exists in the English table', async () => {
  const { readFile } = await import('node:fs/promises');
  const source = await readFile(new URL('../desktop/plugin.js', import.meta.url), 'utf8');
  const used = [...source.matchAll(/\bL\('([\w.]+)'/g)].map(m => m[1]);
  assert.ok(used.length > 40, `expected many translated strings, got ${used.length}`);
  const missing = [...new Set(used)].filter(k => !(k in plugin.STRINGS.en));
  assert.deepEqual(missing, []);
});

test('plugin is named Hermes Lectern and lives at /lectern', async () => {
  const plugin = (await import('../desktop/plugin.js')).default;
  assert.equal(plugin.id, 'hermes-lectern');
  assert.equal(plugin.name, 'Hermes Lectern');
  const contributions = [];
  const ctx = { source: 'plugin:hermes-lectern', storage: { get: (_k, d) => d, set() {} }, onEvent() {}, onDispose() {},
    setTimeout: () => () => {}, os: {}, registerMany: cs => contributions.push(...cs), rest: async () => ({}) };
  plugin.register(ctx);
  assert.equal(contributions.find(c => c.id === 'page').data.path, '/lectern');
  assert.equal(contributions.find(c => c.id === 'nav').data.label, 'Lectern');
});

test('new notes start in the browsed folder, else the configured inbox, else the vault root', async () => {
  const { newNoteFolder } = await import('../desktop/plugin.js');
  assert.equal(newNoteFolder('Projects', 'Inbox'), 'Projects');
  assert.equal(newNoteFolder('', 'Inbox'), 'Inbox');
  assert.equal(newNoteFolder('', null), '');
  assert.equal(newNoteFolder(undefined, undefined), '');
});

test('parseImageEmbed reads wikilink and Markdown image embeds', () => {
  const { parseImageEmbed } = plugin;
  assert.deepEqual(parseImageEmbed('![[x.png]]'), { kind: 'image', target: 'x.png', width: null, alt: 'x.png' });
  assert.deepEqual(parseImageEmbed('![[x.png|300]]'), { kind: 'image', target: 'x.png', width: 300, alt: 'x.png' });
  assert.deepEqual(parseImageEmbed('![[a/b.png]]'), { kind: 'image', target: 'a/b.png', width: null, alt: 'b.png' });
  assert.deepEqual(parseImageEmbed('![[x.png|a caption]]'), { kind: 'image', target: 'x.png', width: null, alt: 'a caption' });
  assert.deepEqual(parseImageEmbed('![[Shot.PNG]]'), { kind: 'image', target: 'Shot.PNG', width: null, alt: 'Shot.PNG' });
  assert.deepEqual(parseImageEmbed('![alt](rel/x.png)'), { kind: 'image', target: 'rel/x.png', width: null, alt: 'alt' });
  assert.deepEqual(parseImageEmbed('![alt](<a b.png>)'), { kind: 'image', target: 'a b.png', width: null, alt: 'alt' });
  assert.deepEqual(parseImageEmbed('![alt](a%20b.png)'), { kind: 'image', target: 'a%20b.png', width: null, alt: 'alt' });
  assert.deepEqual(parseImageEmbed('![](x.svg)'), { kind: 'image', target: 'x.svg', width: null, alt: 'x.svg' });
  assert.deepEqual(parseImageEmbed('![pic|120](x.webp)'), { kind: 'image', target: 'x.webp', width: 120, alt: 'pic' });
});

test('parseImageEmbed leaves note embeds and non-images alone', () => {
  const { parseImageEmbed } = plugin;
  assert.equal(parseImageEmbed('![[Some note]]'), null);
  assert.equal(parseImageEmbed('![[Some note|alias]]'), null);
  assert.equal(parseImageEmbed('![doc](file.pdf)'), null);
  assert.equal(parseImageEmbed('[[x.png]]'), null);
  assert.equal(parseImageEmbed('plain text'), null);
});

test('parseImageEmbed turns remote images into links and never into images', () => {
  const { parseImageEmbed } = plugin;
  assert.deepEqual(parseImageEmbed('![cat](https://example.com/c.png)'), { kind: 'link', href: 'https://example.com/c.png', label: 'cat' });
  assert.deepEqual(parseImageEmbed('![](http://example.com/c.png)'), { kind: 'link', href: 'http://example.com/c.png', label: 'http://example.com/c.png' });
  assert.deepEqual(parseImageEmbed('![x](<https://example.com/a b.png>)'), { kind: 'link', href: 'https://example.com/a b.png', label: 'x' });
  assert.equal(parseImageEmbed('![x](javascript:alert(1))'), null);
  assert.equal(parseImageEmbed('![x](data:image/png;base64,AAAA)'), null);
});

test('loadAsset asks the backend once per note and target', async () => {
  const { loadAsset, clearAssetCache } = plugin;
  clearAssetCache();
  const calls = [];
  const rest = async path => { calls.push(path); return { mime: 'image/png', data: 'QQ==' }; };
  const a = await loadAsset(rest, 'N/n.md', 'x.png');
  await loadAsset(rest, 'N/n.md', 'x.png');
  await loadAsset(rest, 'N/other.md', 'x.png');
  assert.equal(calls.length, 2);
  assert.equal(calls[0], '/asset?path=x.png&from=N%2Fn.md');
  assert.equal(a.mime, 'image/png');
  const failing = async () => { throw new Error('asset_not_found'); };
  await assert.rejects(loadAsset(failing, 'N/n.md', 'gone.png'));
  let retried = 0;
  await loadAsset(async () => { retried++; return { mime: 'image/png', data: '' }; }, 'N/n.md', 'gone.png');
  assert.equal(retried, 1);
});

test('image UI strings exist in both languages', () => {
  assert.equal(plugin.t('imageLoading'), 'Loading image…');
  assert.equal(plugin.t('imageMissing', { name: 'a.png' }), 'Image not found: a.png');
  assert.equal(plugin.t('imageLoading', {}, 'ja'), '画像を読み込み中…');
  assert.equal(plugin.t('imageMissing', { name: 'a.png' }, 'ja'), '画像が見つかりません: a.png');
});
