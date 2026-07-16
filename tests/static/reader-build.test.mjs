import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile, readdir, stat } from 'node:fs/promises';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { load } from 'cheerio';
import { controllerChangeTransition } from '../../web/reader/pwa.js';
import { SITE_BASE_PATH, SITE_ROOT, sitePath } from '../../web/reader/site.js';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const PUBLISH = path.join(ROOT, 'build', 'site');
const SITE = path.join(PUBLISH, SITE_BASE_PATH.slice(1));
const SITE_ORIGIN = 'https://pee.esoren.com';

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
  assert.deepEqual((await readdir(PUBLISH)).sort(), ['_headers', '_redirects', SITE_BASE_PATH.slice(1)].sort());
});

test('reader CSS restores document scrolling after the lwarp viewport lock', async () => {
  const manifest = await json('data/content-manifest.json');
  const css = await readFile(path.join(SITE, `assets/${manifest.buildId}/reader/reader.css`), 'utf8');
  const lwarpLock = css.indexOf('overflow-y: hidden');
  const readerDesign = css.indexOf('/* Reader design */');
  assert.ok(lwarpLock >= 0, 'expected the bundled lwarp viewport lock');
  assert.ok(readerDesign > lwarpLock, 'reader overrides must follow lwarp.css');
  const bodyRule = css.slice(readerDesign).match(/body\s*\{([^}]*)\}/)?.[1] ?? '';
  assert.match(bodyRule, /height:\s*auto/);
  assert.match(bodyRule, /overflow-x:\s*hidden/);
  assert.match(bodyRule, /overflow-y:\s*auto/);
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
    assert.equal($('link[rel="canonical"]').attr('href'), `${SITE_ORIGIN}${sitePath(page.slug)}`);
    assert.equal($('link[rel="stylesheet"]').attr('href'), sitePath(`assets/${manifest.buildId}/reader/reader.css`));
    assert.equal($('script[type="module"]').attr('src'), sitePath(`assets/${manifest.buildId}/reader/app.js`));
    assert.equal($('#MathJax-script').attr('src'), sitePath(`assets/${manifest.buildId}/vendor/mathjax-3.2.2/es5/tex-svg.js`));
    const context = JSON.parse($('#reader-page-context').text());
    assert.equal(context.schemaVersion, manifest.schemaVersion);
    assert.equal(context.buildId, manifest.buildId);
    assert.equal(context.basePath, SITE_BASE_PATH);
    assert.equal(context.slug, page.slug);
    assert.equal(context.canonicalUrl, sitePath(page.slug));
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
  assert.equal(homeContext.basePath, SITE_BASE_PATH);
  assert.equal(homeContext.canonicalUrl, SITE_ROOT);
  assert.equal(homeContext.isHome, true);
  assert.equal(home('link[rel="canonical"]').attr('href'), `${SITE_ORIGIN}${SITE_ROOT}`);
  assert.equal(home('[data-reader-continue][hidden]').length, 1);
});

test('all same-origin links and fragments resolve to published resources', async () => {
  const manifest = await json('data/content-manifest.json');
  const htmlFiles = ['index.html', ...manifest.pages.map((page) => `${page.slug}.html`)];
  const routeFile = new Map([[SITE_ROOT, 'index.html'], ...manifest.pages.map((page) => [sitePath(page.slug), `${page.slug}.html`])]);
  const targetCache = new Map();
  for (const name of htmlFiles) targetCache.set(name, load(await readFile(path.join(SITE, name), 'utf8')));
  for (const name of htmlFiles) {
    const $ = targetCache.get(name);
    for (const node of $('a[href]').toArray()) {
      const href = $(node).attr('href');
      if (!href || /^(?:https?:|mailto:|tel:)/.test(href)) continue;
      const currentPath = name === 'index.html' ? SITE_ROOT : sitePath(name.replace(/\.html$/, ''));
      const url = new URL(href, `https://reader.test${currentPath}`);
      assert.ok(url.pathname === SITE_BASE_PATH || url.pathname.startsWith(SITE_ROOT), `${name}: escaped ${url.pathname}`);
      const targetName = routeFile.get(url.pathname);
      if (!targetName) {
        const file = path.join(SITE, url.pathname.slice(SITE_ROOT.length));
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
  assert.equal(manifest.basePath, SITE_BASE_PATH);
  assert.equal(manifest.home, SITE_ROOT);
  assert.equal(manifest.pdf.url, sitePath('downloads/kaoyan-math1-notes.pdf'));
  assert.ok(manifest.pages.every((page) => page.url === sitePath(page.slug)));
  const redirects = (await readFile(path.join(PUBLISH, '_redirects'), 'utf8')).trim().split(/\r?\n/);
  assert.equal(redirects.length, 104);
  for (const page of manifest.pages) {
    assert.ok(redirects.includes(`${sitePath(`note-${page.legacyNote}`)} ${sitePath(page.slug)} 301`));
    assert.ok(redirects.includes(`${sitePath(`note-${page.legacyNote}.html`)} ${sitePath(page.slug)} 301`));
  }
  const sw = await readFile(path.join(SITE, 'sw.js'), 'utf8');
  assert.match(sw, new RegExp(`const BUILD_ID = ["']${manifest.buildId}["']`));
  assert.match(sw, new RegExp(`const BASE_PATH = ["']${SITE_BASE_PATH}["']`));
  assert.ok(!sw.includes(sitePath('downloads/kaoyan-math1-notes.pdf')));
  for (const page of manifest.pages) assert.ok(sw.includes(`"${sitePath(page.slug)}"`));
  assert.match(sw, /url\.pathname !== BASE_PATH && !url\.pathname\.startsWith\(`\$\{BASE_PATH\}\/`\)/);
  assert.match(sw, /await cache\.addAll\(PRECACHE\)/);
  assert.match(sw, /catch \(error\)[\s\S]*await caches\.delete\(CACHE_NAME\)/);
  assert.match(sw, /event\.data\?\.type === 'SKIP_WAITING'/);
  assert.match(sw, /name\.startsWith\('math1-reader-'\) && name !== CACHE_NAME/);
  assert.doesNotMatch(sw, /new Request\(url, request\)/);
  const match = sw.match(/const PRECACHE = (\[[\s\S]*?\]);\nconst LEGACY_ROUTES/);
  assert.ok(match, 'precache declaration');
  const urls = JSON.parse(match[1]);
  assert.ok(urls.every((url) => url === SITE_BASE_PATH || url.startsWith(SITE_ROOT)));
  const physical = urls.map((url) => {
    if (url === SITE_ROOT) return path.join(SITE, 'index.html');
    if (manifest.pages.some((page) => page.url === url)) return path.join(SITE, `${url.slice(SITE_ROOT.length)}.html`);
    return path.join(SITE, url.slice(SITE_ROOT.length));
  });
  const bytes = (await Promise.all(physical.map(async (file) => (await stat(file)).size))).reduce((sum, size) => sum + size, 0);
  assert.ok(bytes <= 10 * 1024 * 1024, `precache ${bytes} exceeds 10 MiB`);
  const headers = await readFile(path.join(PUBLISH, '_headers'), 'utf8');
  assert.match(headers, /\/math\/\*[\s\S]*Content-Security-Policy/);
  assert.match(headers, /\/math\/\n  Cache-Control: public, max-age=0, must-revalidate, no-transform/);
  assert.match(headers, /\/math\/sw\.js[\s\S]*no-store/);
  assert.match(headers, /\/math\/downloads\/\*\.pdf[\s\S]*max-age=0, must-revalidate/);
  assert.match(headers, new RegExp(`/math/assets/${manifest.buildId}/\\*[\\s\\S]*immutable`));
  assert.match(headers, /Content-Security-Policy: default-src 'self'/);
  const webManifest = JSON.parse(await readFile(path.join(SITE, 'manifest.webmanifest'), 'utf8'));
  assert.equal(webManifest.id, SITE_ROOT);
  assert.equal(webManifest.start_url, SITE_ROOT);
  assert.equal(webManifest.scope, SITE_ROOT);
  assert.ok(webManifest.icons.every((icon) => icon.src.startsWith(sitePath('assets/icons/v1/'))));
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
  assert.doesNotMatch(offline, /__SITE_ROOT__/);
  assert.match(offline, new RegExp(`/math/assets/${manifest.buildId}/reader/reader\\.css`));
  assert.match(offline, /href="\/math\/"/);
});

test('Wrangler publishes only the /math route and disables workers.dev', async () => {
  const config = JSON.parse(await readFile(path.join(ROOT, 'wrangler.jsonc'), 'utf8'));
  assert.equal(config.name, 'kaoyan-math1-notes');
  assert.equal(config.workers_dev, false);
  assert.deepEqual(config.routes, [{ pattern: 'pee.esoren.com/math/*', zone_name: 'esoren.com' }]);
  assert.equal(config.assets.directory, './build/site');
});
