import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile, readdir, stat } from 'node:fs/promises';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { load } from 'cheerio';
import { controllerChangeTransition } from '../../web/reader/pwa.js';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const SITE = path.join(ROOT, 'build', 'site');

async function json(relativePath) {
  return JSON.parse(await readFile(path.join(SITE, relativePath), 'utf8'));
}

async function listFiles(directory) {
  const files = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const full = path.join(directory, entry.name);
    if (entry.isDirectory()) files.push(...await listFiles(full));
    else if (entry.isFile()) files.push(full);
  }
  return files;
}

test('publishes exactly the canonical 53 HTML documents', async () => {
  const manifest = await json('data/content-manifest.json');
  assert.equal(manifest.schemaVersion, 1);
  assert.equal(manifest.pages.length, 52);
  assert.equal(new Set(manifest.pages.map((page) => page.slug)).size, 52);
  const html = (await readdir(SITE)).filter((name) => name.endsWith('.html')).sort();
  assert.deepEqual(html, ['index.html', 'offline.html', ...manifest.pages.map((page) => `${page.slug}.html`)].sort());
  assert.equal(html.filter((name) => name !== 'offline.html').length, 53);
});

test('page contexts, titles, navigation and local anchors are coherent', async () => {
  const manifest = await json('data/content-manifest.json');
  for (let index = 0; index < manifest.pages.length; index += 1) {
    const page = manifest.pages[index];
    const source = await readFile(path.join(SITE, `${page.slug}.html`), 'utf8');
    const $ = load(source);
    assert.equal($('html[data-reader]').length, 1, page.slug);
    assert.equal($('#reader-main').length, 1, page.slug);
    assert.equal($('h1').length, 1, `${page.slug}: must have one h1`);
    assert.equal($('script[src*="cdn"],link[href*="cdn"]').length, 0, `${page.slug}: CDN resource`);
    assert.equal($('link[rel="canonical"]').attr('href'), `https://kaoyan-math1-notes.sorenliu.workers.dev/${page.slug}`);
    assert.equal($('link[rel="stylesheet"]').attr('href'), `/assets/${manifest.buildId}/reader/reader.css`);
    assert.equal($('script[type="module"]').attr('src'), `/assets/${manifest.buildId}/reader/app.js`);
    assert.equal($('#MathJax-script').attr('src'), `/assets/${manifest.buildId}/vendor/mathjax-3.2.2/es5/tex-svg.js`);
    const context = JSON.parse($('#reader-page-context').text());
    assert.equal(context.schemaVersion, manifest.schemaVersion);
    assert.equal(context.buildId, manifest.buildId);
    assert.equal(context.slug, page.slug);
    assert.equal(context.previous?.slug ?? null, manifest.pages[index - 1]?.slug ?? null);
    assert.equal(context.next?.slug ?? null, manifest.pages[index + 1]?.slug ?? null);
    assert.equal($('[rel="prev"]').attr('href') ?? null, context.previous?.url ?? null);
    assert.equal($('[rel="next"]').attr('href') ?? null, context.next?.url ?? null);
    const ids = $('[id]').map((_, node) => $(node).attr('id')).get();
    assert.equal(new Set(ids).size, ids.length, `${page.slug}: duplicate id`);
    for (const anchor of $('a[href^="#"]').toArray()) {
      const id = decodeURIComponent($(anchor).attr('href').slice(1));
      if (id) assert.ok(ids.includes(id), `${page.slug}: missing #${id}`);
    }
  }
  const home = load(await readFile(path.join(SITE, 'index.html'), 'utf8'));
  const homeContext = JSON.parse(home('#reader-page-context').text());
  assert.equal(homeContext.buildId, manifest.buildId);
  assert.equal(homeContext.isHome, true);
  assert.equal(home('[data-reader-continue][hidden]').length, 1);
});

test('all same-origin links and fragments resolve to published resources', async () => {
  const manifest = await json('data/content-manifest.json');
  const htmlFiles = ['index.html', ...manifest.pages.map((page) => `${page.slug}.html`)];
  const routeFile = new Map([['/', 'index.html'], ...manifest.pages.map((page) => [`/${page.slug}`, `${page.slug}.html`])]);
  const targetCache = new Map();
  for (const name of htmlFiles) targetCache.set(name, load(await readFile(path.join(SITE, name), 'utf8')));
  for (const name of htmlFiles) {
    const $ = targetCache.get(name);
    for (const node of $('a[href]').toArray()) {
      const href = $(node).attr('href');
      if (!href || /^(?:https?:|mailto:|tel:)/.test(href)) continue;
      const currentPath = name === 'index.html' ? '/' : `/${name.replace(/\.html$/, '')}`;
      const url = new URL(href, `https://reader.test${currentPath}`);
      const targetName = routeFile.get(url.pathname);
      if (!targetName) {
        const file = path.join(SITE, url.pathname.slice(1));
        assert.ok((await stat(file)).isFile(), `${name}: missing ${url.pathname}`);
        continue;
      }
      if (url.hash) {
        const id = decodeURIComponent(url.hash.slice(1));
        const target = targetCache.get(targetName);
        assert.equal(target('[id]').filter((_, element) => target(element).attr('id') === id).length, 1, `${name}: unresolved ${href}`);
      }
    }
    assert.doesNotMatch($.html(), /calc-appendix-05-exponential-hyperbolic\.html/);
  }
});

test('search index and content manifest share schema and build identity', async () => {
  const manifest = await json('data/content-manifest.json');
  const search = await json('data/search-index.json');
  assert.equal(search.schemaVersion, manifest.schemaVersion);
  assert.equal(search.buildId, manifest.buildId);
  assert.equal(search.documents.length, 52);
  assert.deepEqual(search.documents.map((document) => document.slug), manifest.pages.map((page) => page.slug));
  assert.ok(search.documents.some((document) => document.problemIds.length > 0));
  assert.ok(search.documents.some((document) => document.tex.length > 0));
});

test('legacy redirects and service worker precache are complete and bounded', async () => {
  const manifest = await json('data/content-manifest.json');
  const redirects = (await readFile(path.join(SITE, '_redirects'), 'utf8')).trim().split(/\r?\n/);
  assert.equal(redirects.length, 104);
  for (const page of manifest.pages) {
    assert.ok(redirects.includes(`/note-${page.legacyNote} /${page.slug} 301`));
    assert.ok(redirects.includes(`/note-${page.legacyNote}.html /${page.slug} 301`));
  }
  const sw = await readFile(path.join(SITE, 'sw.js'), 'utf8');
  assert.match(sw, new RegExp(`const BUILD_ID = ["']${manifest.buildId}["']`));
  assert.ok(!sw.includes('/downloads/kaoyan-math1-notes.pdf'));
  for (const page of manifest.pages) assert.ok(sw.includes(`"/${page.slug}"`));
  assert.match(sw, /await cache\.addAll\(PRECACHE\)/);
  assert.match(sw, /catch \(error\)[\s\S]*await caches\.delete\(CACHE_NAME\)/);
  assert.match(sw, /event\.data\?\.type === 'SKIP_WAITING'/);
  assert.match(sw, /name\.startsWith\('math1-reader-'\) && name !== CACHE_NAME/);
  assert.doesNotMatch(sw, /new Request\(url, request\)/);
  const match = sw.match(/const PRECACHE = (\[[\s\S]*?\]);\nconst LEGACY_ROUTES/);
  assert.ok(match, 'precache declaration');
  const urls = JSON.parse(match[1]);
  const physical = urls.map((url) => {
    if (url === '/') return path.join(SITE, 'index.html');
    if (manifest.pages.some((page) => `/${page.slug}` === url)) return path.join(SITE, `${url.slice(1)}.html`);
    return path.join(SITE, url.slice(1));
  });
  const bytes = (await Promise.all(physical.map(async (file) => (await stat(file)).size))).reduce((sum, size) => sum + size, 0);
  assert.ok(bytes <= 10 * 1024 * 1024, `precache ${bytes} exceeds 10 MiB`);
  const headers = await readFile(path.join(SITE, '_headers'), 'utf8');
  assert.match(headers, /\/sw\.js[\s\S]*no-store/);
  assert.match(headers, /\/downloads\/\*\.pdf[\s\S]*max-age=0, must-revalidate/);
  assert.match(headers, new RegExp(`/assets/${manifest.buildId}/\\*[\\s\\S]*immutable`));
  assert.match(headers, /Content-Security-Policy: default-src 'self'/);
  const webManifest = JSON.parse(await readFile(path.join(SITE, 'manifest.webmanifest'), 'utf8'));
  assert.equal(webManifest.background_color, '#ffffff');
  assert.equal(webManifest.theme_color, '#111111');
});

test('service worker updates reload every already-controlled tab', () => {
  let state = controllerChangeTransition(false, false);
  assert.deepEqual(state, { hasBeenControlled: true, shouldReload: false });

  state = controllerChangeTransition(state.hasBeenControlled, false);
  assert.deepEqual(state, { hasBeenControlled: true, shouldReload: true });

  assert.equal(controllerChangeTransition(true, true).shouldReload, true);
  assert.equal(controllerChangeTransition(false, true).shouldReload, true);
});

test('PDF is valid and hash is recorded', async () => {
  const manifest = await json('data/content-manifest.json');
  const pdf = await readFile(path.join(SITE, 'downloads', 'kaoyan-math1-notes.pdf'));
  assert.equal(pdf.subarray(0, 5).toString('ascii'), '%PDF-');
  assert.equal(createHash('sha256').update(pdf).digest('hex'), manifest.pdf.sha256);
  assert.equal(pdf.length, manifest.pdf.bytes);
});

test('JavaScript parses, stays ASCII-quoted and MathJax is fully self-hosted', async () => {
  const manifest = await json('data/content-manifest.json');
  const jsFiles = (await listFiles(SITE)).filter((file) => file.endsWith('.js'));
  for (const file of jsFiles) {
    const source = await readFile(file, 'utf8');
    assert.doesNotMatch(source, /[‘’“”]/u, path.relative(SITE, file));
    const result = spawnSync(process.execPath, ['--check', file], { encoding: 'utf8' });
    assert.equal(result.status, 0, `${path.relative(SITE, file)}: ${result.stderr}`);
  }
  const mathRoot = `assets/${manifest.buildId}/vendor/mathjax-3.2.2`;
  for (const relative of [
    `${mathRoot}/lwarp-config.js`,
    `${mathRoot}/es5/tex-svg.js`,
    `${mathRoot}/es5/input/tex/extensions/tagformat.js`,
    `${mathRoot}/es5/input/tex/extensions/textmacros.js`,
    `${mathRoot}/es5/input/tex/extensions/mathtools.js`,
    `${mathRoot}/es5/input/tex/extensions/textcomp.js`,
    `${mathRoot}/es5/input/tex/extensions/extpfeil.js`,
    `${mathRoot}/es5/output/svg/fonts/tex.js`,
  ]) assert.ok((await stat(path.join(SITE, relative))).isFile(), relative);
  const offline = await readFile(path.join(SITE, 'offline.html'), 'utf8');
  assert.doesNotMatch(offline, /__ASSET_ROOT__/);
  assert.match(offline, new RegExp(`/assets/${manifest.buildId}/reader/reader\\.css`));
});
