import { createHash } from 'node:crypto';
import { cp, mkdir, readFile, readdir, rm, stat, writeFile } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

import { load } from 'cheerio';
import YAML from 'yaml';
import { SITE_BASE_PATH, sitePath } from '../web/reader/site.js';

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(SCRIPT_DIR, '..');
const SOURCE_DIR = path.resolve(process.argv[2] ?? path.join(ROOT, 'build', 'lwarp'));
const PUBLISH_DIR = path.resolve(process.argv[3] ?? path.join(ROOT, 'build', 'site'));
const SITE_DIR = path.join(PUBLISH_DIR, ...SITE_BASE_PATH.slice(1).split('/'));
const PDF_PATH = path.resolve(process.argv[4] ?? path.join(ROOT, 'build', 'pdf', 'main.pdf'));
const SCHEMA_VERSION = 1;
const SITE_ORIGIN = String(process.env.SITE_ORIGIN ?? 'https://pee.esoren.com').replace(/\/$/, '');
const SUBJECT_LABELS = {
  calculus: '高等数学',
  linear_algebra: '线性代数',
  probability: '概率论与数理统计',
  indexes: '复习索引',
  index: '复习索引',
  '索引': '复习索引',
};
const BOX_TYPES = [
  ['problem', '.problem-box', '题目'],
  ['solution', '.solution-box', '题解'],
  ['knowledge', '.knowledge-box', '知识点'],
  ['mistake', '.mistake-box', '易错点'],
];

function fail(message) {
  throw new Error(message);
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function sha256(value) {
  return createHash('sha256').update(value).digest('hex');
}

async function listFiles(directory) {
  const output = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) output.push(...await listFiles(fullPath));
    else if (entry.isFile()) output.push(fullPath);
  }
  return output.sort((a, b) => a.localeCompare(b));
}

function normalizeSubject(value) {
  return SUBJECT_LABELS[value] ?? value ?? '复习索引';
}

function normalizePage(raw, index) {
  const legacyNote = Number(raw.legacy_note ?? raw.legacyNote ?? raw.note ?? index + 1);
  return {
    slug: String(raw.slug ?? '').trim(),
    title: String(raw.title ?? '').trim(),
    lwarpSlug: String(raw.lwarp_slug ?? raw.slug ?? '').trim(),
    subject: normalizeSubject(raw.subject),
    subjectKey: String(raw.subject_key ?? raw.subject ?? 'indexes'),
    lecture: raw.lecture ?? '',
    legacyNote,
    source: raw.source ?? raw.file ?? raw.tex ?? null,
  };
}

async function loadPages() {
  const manifestPath = path.join(ROOT, 'data', 'web_pages.yml');
  const source = await readFile(manifestPath, 'utf8');
  const parsed = YAML.parse(source);
  const rows = Array.isArray(parsed) ? parsed : parsed?.pages;
  if (!Array.isArray(rows)) fail('data/web_pages.yml must contain a pages array.');
  const pages = rows.map(normalizePage);
  if (pages.length !== 52) fail(`Expected 52 reader pages, found ${pages.length}.`);
  const slugs = new Set();
  const notes = new Set();
  for (const page of pages) {
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(page.slug)) fail(`Invalid ASCII slug: ${page.slug}`);
    if (!page.title) fail(`Missing title for ${page.slug}.`);
    if (slugs.has(page.slug)) fail(`Duplicate slug: ${page.slug}`);
    if (!Number.isInteger(page.legacyNote) || page.legacyNote < 1) fail(`Invalid legacy_note for ${page.slug}.`);
    if (notes.has(page.legacyNote)) fail(`Duplicate legacy_note: ${page.legacyNote}`);
    slugs.add(page.slug);
    notes.add(page.legacyNote);
  }
  return { pages, manifestSource: source };
}

function icon(name) {
  const icons = {
    menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
    search: '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4 4"/>',
    theme: '<path d="M20.5 14.2A8 8 0 0 1 9.8 3.5 8.5 8.5 0 1 0 20.5 14.2Z"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H3v-4h.1a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3 1.7 1.7 0 0 0 1-1.6v-.2h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z"/>',
    print: '<path d="M7 9V3h10v6M7 17H5a2 2 0 0 1-2-2v-4a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2h-2"/><path d="M7 14h10v7H7z"/>',
    download: '<path d="M12 3v12m0 0 4-4m-4 4-4-4M4 21h16"/>',
    close: '<path d="m5 5 14 14M19 5 5 19"/>',
    arrowLeft: '<path d="m15 18-6-6 6-6"/>',
    arrowRight: '<path d="m9 18 6-6-6-6"/>',
  };
  return `<svg aria-hidden="true" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${icons[name]}</svg>`;
}

function groupPages(pages) {
  const groups = [];
  for (const page of pages) {
    let group = groups.at(-1);
    if (!group || group.subject !== page.subject) {
      group = { subject: page.subject, pages: [] };
      groups.push(group);
    }
    group.pages.push(page);
  }
  return groups;
}

function groupByLecture(pages) {
  const groups = [];
  for (const page of pages) {
    if (!page.lecture) {
      groups.push({ lecture: '', pages: [page] });
      continue;
    }
    let group = groups.at(-1);
    if (!group || group.lecture !== page.lecture) {
      group = { lecture: page.lecture, pages: [] };
      groups.push(group);
    }
    group.pages.push(page);
  }
  return groups;
}

function tocMarkup(pages, currentSlug) {
  return groupPages(pages).map((group, subjectIndex) => {
    const subjectIsCurrent = group.pages.some((page) => page.slug === currentSlug);
    const lectures = groupByLecture(group.pages).map((lecture) => {
      const lectureIsCurrent = lecture.pages.some((page) => page.slug === currentSlug);
      if (lecture.pages.length === 1) {
        const page = lecture.pages[0];
        return `<li><a class="reader-toc__link reader-toc__lecture-link" href="${sitePath(page.slug)}"${page.slug === currentSlug ? ' aria-current="page"' : ''}>${escapeHtml(page.title)}</a></li>`;
      }
      const lectureNumber = lecture.lecture.match(/\d+/)?.[0] ?? '';
      const lectureTitle = lecture.pages[0].title;
      const childLinks = lecture.pages.map((page, pageIndex) => {
        const shortTitle = page.title.replace(/^第\s*\d+\s*讲\s*/, '');
        const index = lectureNumber ? `${lectureNumber}.${pageIndex + 1}` : String(pageIndex + 1);
        return `<li><a class="reader-toc__link" href="${sitePath(page.slug)}"${page.slug === currentSlug ? ' aria-current="page"' : ''}><span class="reader-toc__index" aria-hidden="true">${index}</span><span>${escapeHtml(shortTitle)}</span></a></li>`;
      }).join('');
      return `<li><details class="reader-toc__lecture"${lectureIsCurrent ? ' open' : ''}><summary>${escapeHtml(lectureTitle)}</summary><ol>${childLinks}</ol></details></li>`;
    }).join('');
    const open = subjectIsCurrent || (!currentSlug && subjectIndex === 0);
    return `<details class="reader-toc__subject"${open ? ' open' : ''}><summary>${escapeHtml(group.subject)}</summary><ol class="reader-toc__list">${lectures}</ol></details>`;
  }).join('');
}

function offlinePanelMarkup() {
  return `<section class="reader-offline-panel" aria-label="离线阅读">${icon('download')}<div><strong>支持离线阅读</strong><p>完整缓存后，53 页内容无需联网也可打开。</p><button type="button" data-reader-action="open-preferences">管理离线内容</button></div></section>`;
}

function dialogsMarkup() {
  return `
  <dialog id="reader-search" aria-labelledby="reader-search-title">
    <div class="reader-dialog__header"><h2 id="reader-search-title">搜索笔记</h2><button type="button" data-reader-action="close-search" aria-label="关闭搜索">${icon('close')}</button></div>
    <div class="reader-dialog__body"><label for="reader-search-input">搜索题号、标题、讲次、标签、正文或 TeX</label><input id="reader-search-input" type="search" autocomplete="off" data-reader-search-input><p data-reader-search-status aria-live="polite"></p><ol data-reader-search-results></ol></div>
  </dialog>
  <dialog id="reader-preferences" aria-labelledby="reader-preferences-title">
    <div class="reader-dialog__header"><h2 id="reader-preferences-title">阅读偏好</h2><button type="button" data-reader-action="close-preferences" aria-label="关闭阅读偏好">${icon('close')}</button></div>
    <div class="reader-dialog__body">
      <fieldset><legend>主题</legend><button type="button" data-reader-preference="theme" value="light">浅色</button><button type="button" data-reader-preference="theme" value="dark">深色</button><button type="button" data-reader-preference="theme" value="system">跟随系统</button></fieldset>
      <fieldset><legend>字号</legend><button type="button" data-reader-preference="fontScale" value="small">标准</button><button type="button" data-reader-preference="fontScale" value="medium">较大</button><button type="button" data-reader-preference="fontScale" value="large">最大</button></fieldset>
      <fieldset><legend>正文宽度</legend><button type="button" data-reader-preference="contentWidth" value="narrow">窄</button><button type="button" data-reader-preference="contentWidth" value="standard">标准</button><button type="button" data-reader-preference="contentWidth" value="wide">宽</button></fieldset>
      <a class="reader-download-link" href="${sitePath('downloads/kaoyan-math1-notes.pdf')}" download>${icon('download')} 下载完整 PDF</a>
      <button type="button" data-reader-action="install" hidden>安装到设备</button><p data-reader-install-help hidden>在 iPhone 或 iPad 上，请使用“分享 → 添加到主屏幕”。</p>
    </div>
  </dialog>
  <section class="reader-update" data-reader-update hidden aria-live="polite"><p>新版本已准备好。</p><button type="button" data-reader-action="reload-update">刷新使用</button><button type="button" data-reader-action="dismiss-update">稍后</button></section>`;
}

function topbarMarkup() {
  return `<header class="reader-topbar">
    <button class="reader-mobile-actions" type="button" data-reader-action="open-nav" aria-label="打开目录" aria-controls="reader-toc">${icon('menu')}</button>
    <a class="reader-brand" href="${sitePath()}">考研数学一—满分学习笔记</a>
    <button class="reader-search-trigger" type="button" data-reader-action="open-search" aria-label="搜索笔记">${icon('search')}<span>搜索题目、知识点或公式</span><kbd>Ctrl K</kbd></button>
    <nav class="reader-toolbar" aria-label="阅读工具">
      <button class="reader-preference-font" type="button" data-reader-action="open-preferences" aria-label="调整字号与正文宽度"><span class="reader-font-icon" aria-hidden="true">A</span><span class="reader-action__label">字号</span></button>
      <button class="reader-preference-theme" type="button" data-reader-action="open-preferences" aria-label="调整阅读主题">${icon('theme')}<span class="reader-action__label">主题</span></button>
      <button type="button" data-reader-action="print" aria-label="打印">${icon('print')}<span class="reader-action__label">打印</span></button>
      <a href="${sitePath('downloads/kaoyan-math1-notes.pdf')}" target="_blank" rel="noopener" aria-label="在新窗口打开 PDF"><span class="reader-action__label">PDF</span></a>
    </nav>
  </header>`;
}

function progressMarkup(placement) {
  const label = placement === 'mobile' ? '阅读进度：' : '本讲阅读进度：';
  return `<div class="reader-progress-row reader-progress-row--${placement}"><span>${label} <strong data-reader-progress-label>0%</strong></span><div data-reader-progress role="progressbar" aria-label="阅读进度" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"></div></div>`;
}

function pageNavMarkup(previous, next) {
  const item = (page, direction) => page ? `<a rel="${direction}" href="${sitePath(page.slug)}">${icon(direction === 'prev' ? 'arrowLeft' : 'arrowRight')}<span><small>${direction === 'prev' ? '上一篇' : '下一篇'}</small>${escapeHtml(page.title)}</span></a>` : '<span></span>';
  return `<nav class="reader-page-nav" aria-label="前后篇">${item(previous, 'prev')}<a href="${sitePath()}">全部讲次</a>${item(next, 'next')}</nav>`;
}

function homeMarkup(pages) {
  const groups = groupPages(pages);
  return `<div class="reader-home">
    <header class="reader-page-header"><h1>考研数学一满分学习笔记</h1><p>按教材讲次阅读，公式、题解与复盘内容均来自同一套 LaTeX 文档。</p></header>
    <button class="reader-home-search" type="button" data-reader-action="open-search">${icon('search')} 搜索题目与知识点</button>
    <a class="reader-continue" href="${sitePath(pages[0].slug)}" data-reader-continue hidden>继续阅读：<span data-reader-continue-title>${escapeHtml(pages[0].title)}</span></a>
    <nav class="reader-index-links" aria-label="复习索引">${pages.filter((page) => page.subject === '复习索引').map((page) => `<a href="${sitePath(page.slug)}">${escapeHtml(page.title)}</a>`).join('')}</nav>
    ${groups.filter((group) => group.subject !== '复习索引').map((group) => `<section class="reader-home__subject"><h2>${escapeHtml(group.subject)}</h2><div class="reader-home__lectures">${groupByLecture(group.pages).map((lecture) => `<section class="reader-home__lecture"><h3>${escapeHtml(lecture.lecture)}</h3><ol>${lecture.pages.map((page) => `<li><a href="${sitePath(page.slug)}">${escapeHtml(page.title)}</a></li>`).join('')}</ol></section>`).join('')}</div></section>`).join('')}
  </div>`;
}

function canonicalLink(href, byLegacy, bySlug, byLwarpSlug) {
  if (!href || /^(?:https?:|mailto:|tel:|javascript:)/i.test(href) || href.startsWith('#')) return href;
  const [target, hash = ''] = href.split('#', 2);
  if (/^(?:\.\/)?index(?:\.html)?$/.test(target)) return `${sitePath()}${hash ? `#${hash}` : ''}`;
  const note = target.match(/(?:^|\/)note-(\d+)(?:\.html)?$/);
  if (note && byLegacy.has(Number(note[1]))) return `${sitePath(byLegacy.get(Number(note[1])).slug)}${hash ? `#${hash}` : ''}`;
  const basename = target.replace(/^\.\//, '').replace(/\.html$/, '');
  if (bySlug.has(basename)) return `${sitePath(basename)}${hash ? `#${hash}` : ''}`;
  if (byLwarpSlug.has(basename)) return `${sitePath(byLwarpSlug.get(basename).slug)}${hash ? `#${hash}` : ''}`;
  return href;
}

function removeLwarpChrome($, main) {
  $('script').remove();
  main.find('h1').first().remove();
  main.find('.knowledge-box').filter((_, node) => {
    const text = $(node).text();
    return text.includes('\\require {mathtools}') || text.includes('Lwarp-macros') || text.includes('MathJax customizations');
  }).remove();
}

function prepareContent($, main, page) {
  removeLwarpChrome($, main);
  main.find('h2,h3,h4,h5,h6').each((_, node) => {
    const clone = $(node).clone();
    clone.find('.sectionnumber').remove();
    const text = clone.text().replace(/[\s\u2003\u00a0]+/g, ' ').trim();
    const compact = text.replace(/\s+/g, '');
    if (compact === page.title.replace(/\s+/g, '') || compact === page.subject.replace(/\s+/g, '')) $(node).remove();
  });
  main.find('h4,h5,h6').each((_, node) => { node.tagName = 'h2'; });
  const anchors = [];
  for (const [type, selector, label] of BOX_TYPES) {
    main.find(selector).each((index, node) => {
      const problemId = $(node).text().match(/MATH1-[A-Z]+-\d+/)?.[0]?.toLowerCase();
      const id = index === 0 ? type : (problemId ?? `${type}-${index + 1}`);
      $(node).attr('id', id);
      if (index === 0) anchors.push({ id, label, type });
    });
  }
  return anchors;
}

function outlineMarkup($, main, anchors) {
  const items = [];
  main.find('h2,h3').each((index, node) => {
    const text = $(node).text().replace(/^\s*[\d.]+\s*/, '').trim();
    if (!text) return;
    const id = $(node).attr('id') || `section-${index + 1}`;
    $(node).attr('id', id);
    items.push({ id, label: text });
  });
  const all = [...items, ...anchors];
  return all.length ? `<nav aria-label="本页大纲"><h2>本页大纲</h2><ol>${all.map((item, index) => `<li><a href="#${item.id}" data-reader-anchor${index === 0 ? ' aria-current="location"' : ''}>${escapeHtml(item.label)}</a></li>`).join('')}</ol></nav>` : '';
}

function contextJson(context) {
  return JSON.stringify(context).replaceAll('<', '\\u003c');
}

function documentHtml({ bodyContent, featuredMeta = '', page, pages, buildId, previous, next, anchors, outline, isHome = false }) {
  const title = isHome ? '考研数学一满分学习笔记' : `${page.title}｜考研数学一`;
  const header = isHome ? '' : `<nav class="reader-breadcrumbs" aria-label="面包屑"><a href="${sitePath()}">首页</a><span aria-hidden="true">/</span><span>${escapeHtml(page.subject)}</span><span aria-hidden="true">/</span><span aria-current="page">${escapeHtml(page.title)}</span></nav><header class="reader-page-header"><p class="reader-page-meta">${escapeHtml(page.subject)}${page.lecture !== '' ? ` · ${escapeHtml(page.lecture)}` : ''}</p><h1>${escapeHtml(page.title)}</h1>${progressMarkup('desktop')}</header>${featuredMeta ? `<div class="reader-featured-meta">${featuredMeta}</div>` : ''}${anchors.length ? `<nav class="reader-anchor-nav" aria-label="内容类型">${anchors.map((item, index) => `<a href="#${item.id}" data-reader-anchor${index === 0 ? ' aria-current="location"' : ''}>${item.label}</a>`).join('')}</nav>` : ''}`;
  const context = isHome ? { schemaVersion: SCHEMA_VERSION, buildId, basePath: SITE_BASE_PATH, slug: 'index', title, isHome: true, canonicalUrl: sitePath() } : {
    schemaVersion: SCHEMA_VERSION,
    buildId,
    basePath: SITE_BASE_PATH,
    slug: page.slug,
    title: page.title,
    subject: page.subject,
    lecture: page.lecture,
    legacyNote: page.legacyNote,
    canonicalUrl: sitePath(page.slug),
    previous: previous ? { slug: previous.slug, title: previous.title, url: sitePath(previous.slug) } : null,
    next: next ? { slug: next.slug, title: next.title, url: sitePath(next.slug) } : null,
    anchors,
    isHome: false,
  };
  const canonicalPath = isHome ? sitePath() : sitePath(page.slug);
  const assetRoot = sitePath(`assets/${buildId}`);
  const html = `<!DOCTYPE html><html lang="zh-CN" data-reader><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#ffffff"><meta name="description" content="考研数学一满分学习笔记与题解库"><link rel="canonical" href="${SITE_ORIGIN}${canonicalPath}"><link rel="manifest" href="${sitePath('manifest.webmanifest')}"><link rel="apple-touch-icon" sizes="180x180" href="${sitePath('assets/icons/v1/icon-180.png')}"><title>${escapeHtml(title)}</title><script src="${assetRoot}/reader/preflight.js"></script><link rel="stylesheet" href="${assetRoot}/reader/reader.css"><script defer src="${assetRoot}/vendor/mathjax-3.2.2/lwarp-config.js"></script><script defer id="MathJax-script" src="${assetRoot}/vendor/mathjax-3.2.2/es5/tex-svg.js"></script><script type="module" src="${assetRoot}/reader/app.js"></script></head><body><a class="reader-skip-link" href="#reader-main">跳到正文</a>${topbarMarkup()}${isHome ? '' : progressMarkup('mobile')}<div class="reader-shell"><aside id="reader-toc" data-reader-drawer="toc" aria-label="讲次目录"><div class="reader-toc__header"><strong>全部章节</strong><button class="reader-mobile-actions" type="button" data-reader-action="close-nav" aria-label="关闭目录">${icon('close')}</button></div><button class="reader-toc__search reader-search-trigger" type="button" data-reader-action="open-search">${icon('search')}<span>搜索题目、知识点或公式</span></button>${tocMarkup(pages, isHome ? null : page.slug)}${offlinePanelMarkup()}</aside><div class="reader-content"><main id="reader-main" tabindex="-1">${header}${bodyContent}${isHome ? '' : pageNavMarkup(previous, next)}</main></div><aside id="reader-outline">${outline}</aside></div><button class="reader-backdrop" type="button" data-reader-backdrop data-reader-action="close-nav" aria-label="关闭目录" hidden></button><p class="reader-pwa-status" data-reader-pwa-status aria-live="polite"></p>${dialogsMarkup()}<script type="application/json" id="reader-page-context">${contextJson(context)}</script></body></html>`;
  return { html, context };
}

async function extractMathJaxConfig() {
  const raw = await readFile(path.join(SOURCE_DIR, 'lwarp_mathjax.txt'), 'utf8');
  const match = raw.match(/<script[^>]*>([\s\S]*?)<\/script>/i);
  const code = (match?.[1] ?? raw).trim() + '\n';
  if (/[‘’“”]/u.test(code)) fail('lwarp_mathjax.txt contains smart quotes.');
  return code;
}

async function copyAssets(buildId) {
  const assetsDir = path.join(SITE_DIR, 'assets');
  await rm(assetsDir, { recursive: true, force: true });
  const versionDir = path.join(assetsDir, buildId);
  const readerDir = path.join(versionDir, 'reader');
  await mkdir(readerDir, { recursive: true });
  await cp(path.join(ROOT, 'web', 'reader'), readerDir, { recursive: true, force: true });
  const lwarpCss = await readFile(path.join(SOURCE_DIR, 'lwarp.css'), 'utf8');
  const readerCss = await readFile(path.join(ROOT, 'web', 'math1-web.css'), 'utf8');
  await writeFile(path.join(readerDir, 'reader.css'), `${lwarpCss}\n/* Reader design */\n${readerCss}`, 'utf8');
  const mathRoot = path.join(versionDir, 'vendor', 'mathjax-3.2.2');
  await mkdir(path.join(mathRoot, 'es5', 'input', 'tex', 'extensions'), { recursive: true });
  await mkdir(path.join(mathRoot, 'es5', 'output', 'svg', 'fonts'), { recursive: true });
  await writeFile(path.join(mathRoot, 'lwarp-config.js'), await extractMathJaxConfig(), 'utf8');
  const mathSource = path.join(ROOT, 'node_modules', 'mathjax', 'es5');
  await cp(path.join(mathSource, 'tex-svg.js'), path.join(mathRoot, 'es5', 'tex-svg.js'));
  // mathtools loads extpfeil dynamically; keep the full dependency chain
  // local so formula rendering never falls back to the network.
  for (const extension of ['tagformat', 'textmacros', 'mathtools', 'textcomp', 'extpfeil']) {
    await cp(path.join(mathSource, 'input', 'tex', 'extensions', `${extension}.js`), path.join(mathRoot, 'es5', 'input', 'tex', 'extensions', `${extension}.js`));
  }
  await cp(path.join(mathSource, 'output', 'svg', 'fonts', 'tex.js'), path.join(mathRoot, 'es5', 'output', 'svg', 'fonts', 'tex.js'));
  return buildId;
}

function assertMathJaxPackages(rawPages) {
  const required = new Set();
  for (const { source } of rawPages) {
    for (const match of source.matchAll(/\\require\s*\{([^}]+)\}/g)) required.add(match[1].trim());
  }
  const supported = new Set(['mathtools', 'textcomp']);
  const unsupported = [...required].filter((name) => !supported.has(name));
  if (unsupported.length) fail(`Unsupported MathJax \\require packages: ${unsupported.join(', ')}`);
}

async function writeDeploymentFiles(pages, buildId) {
  const pwaRoot = path.join(ROOT, 'web', 'pwa');
  const webManifest = (await readFile(path.join(pwaRoot, 'manifest.webmanifest'), 'utf8'))
    .replaceAll('__SITE_ROOT__', sitePath())
    .replaceAll('__SITE_BASE_PATH__', SITE_BASE_PATH);
  await writeFile(path.join(SITE_DIR, 'manifest.webmanifest'), webManifest, 'utf8');
  const offline = (await readFile(path.join(pwaRoot, 'offline.html'), 'utf8'))
    .replaceAll('__ASSET_ROOT__', sitePath(`assets/${buildId}`))
    .replaceAll('__SITE_ROOT__', sitePath());
  await writeFile(path.join(SITE_DIR, 'offline.html'), offline, 'utf8');
  await mkdir(path.join(SITE_DIR, 'assets', 'icons', 'v1'), { recursive: true });
  await cp(path.join(pwaRoot, 'icons'), path.join(SITE_DIR, 'assets', 'icons', 'v1'), { recursive: true, force: true });

  const redirectLines = pages.flatMap((page) => [
    `${sitePath(`note-${page.legacyNote}`)} ${sitePath(page.slug)} 301`,
    `${sitePath(`note-${page.legacyNote}.html`)} ${sitePath(page.slug)} 301`,
  ]);
  if (redirectLines.length !== 104) fail(`Expected 104 legacy redirects, found ${redirectLines.length}.`);
  await writeFile(path.join(PUBLISH_DIR, '_redirects'), `${redirectLines.join('\n')}\n`, 'utf8');

  const htmlHeaders = [sitePath(), ...pages.map((page) => sitePath(page.slug)), sitePath('offline.html'), sitePath('manifest.webmanifest'), sitePath('data/*')]
    .map((url) => `${url}\n  Cache-Control: public, max-age=0, must-revalidate, no-transform`)
    .join('\n\n');
  const headers = `${sitePath('*')}
  Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'self'; manifest-src 'self'; worker-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'
  Referrer-Policy: strict-origin-when-cross-origin
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()

${sitePath('sw.js')}
  Cache-Control: no-store, no-cache, must-revalidate

${htmlHeaders}

${sitePath('downloads/*.pdf')}
  Cache-Control: public, max-age=0, must-revalidate

${sitePath(`assets/${buildId}/*`)}
  Cache-Control: public, max-age=31536000, immutable

${sitePath('assets/icons/v1/*')}
  Cache-Control: public, max-age=31536000, immutable
`;
  await writeFile(path.join(PUBLISH_DIR, '_headers'), headers, 'utf8');

  const assetFiles = await listFiles(path.join(SITE_DIR, 'assets'));
  const precache = [
    sitePath(),
    ...pages.map((page) => sitePath(page.slug)),
    sitePath('offline.html'),
    sitePath('manifest.webmanifest'),
    sitePath('data/content-manifest.json'),
    sitePath('data/search-index.json'),
    ...assetFiles.map((file) => sitePath(path.relative(SITE_DIR, file).replaceAll('\\', '/'))),
  ];
  const physicalFiles = [
    path.join(SITE_DIR, 'index.html'),
    ...pages.map((page) => path.join(SITE_DIR, `${page.slug}.html`)),
    path.join(SITE_DIR, 'offline.html'),
    path.join(SITE_DIR, 'manifest.webmanifest'),
    path.join(SITE_DIR, 'data', 'content-manifest.json'),
    path.join(SITE_DIR, 'data', 'search-index.json'),
    ...assetFiles,
  ];
  const totalBytes = (await Promise.all(physicalFiles.map(async (file) => (await stat(file)).size))).reduce((sum, bytes) => sum + bytes, 0);
  const limit = 10 * 1024 * 1024;
  if (totalBytes > limit) fail(`PWA precache is ${totalBytes} bytes, above the 10 MiB limit.`);
  const legacyRoutes = Object.fromEntries(pages.flatMap((page) => [
    [sitePath(`note-${page.legacyNote}`), sitePath(page.slug)],
    [sitePath(`note-${page.legacyNote}.html`), sitePath(page.slug)],
  ]));
  const template = await readFile(path.join(pwaRoot, 'sw.template.js'), 'utf8');
  const serviceWorker = template
    .replace('__BUILD_ID__', JSON.stringify(buildId))
    .replace('__BASE_PATH__', JSON.stringify(SITE_BASE_PATH))
    .replace('__PRECACHE__', JSON.stringify(precache, null, 2))
    .replace('__LEGACY_ROUTES__', JSON.stringify(legacyRoutes, null, 2));
  await writeFile(path.join(SITE_DIR, 'sw.js'), serviceWorker, 'utf8');
  return { precache, totalBytes };
}

async function readProblemRegistry() {
  try {
    const parsed = YAML.parse(await readFile(path.join(ROOT, 'data', 'problem_registry.yml'), 'utf8'));
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function texPageFragment(page, source) {
  const marker = `\\studySubsection{${page.slug}}`;
  const start = source.indexOf(marker);
  if (start < 0) return source;
  const next = source.indexOf('\\studySubsection{', start + marker.length);
  return source.slice(start, next < 0 ? source.length : next);
}

async function main() {
  const { pages, manifestSource } = await loadPages();
  await mkdir(SITE_DIR, { recursive: true });
  const pdf = await readFile(PDF_PATH);
  if (pdf.subarray(0, 5).toString('ascii') !== '%PDF-') fail(`Invalid PDF output: ${PDF_PATH}`);
  const generatedHtml = (await readdir(SOURCE_DIR))
    .filter((name) => name.endsWith('.html') && !['index.html', 'main-web_html.html'].includes(name))
    .sort();
  const expectedHtml = pages.map((page) => `${page.lwarpSlug}.html`).sort();
  const missingHtml = expectedHtml.filter((name) => !generatedHtml.includes(name));
  const extraHtml = generatedHtml.filter((name) => !expectedHtml.includes(name));
  if (missingHtml.length || extraHtml.length) {
    fail(`Unexpected lwarp split pages. Missing: ${missingHtml.join(', ') || 'none'}; extra: ${extraHtml.join(', ') || 'none'}.`);
  }
  const rawPages = [];
  for (const page of pages) {
    const candidates = [path.join(SOURCE_DIR, `${page.lwarpSlug}.html`), path.join(SOURCE_DIR, `${page.slug}.html`), path.join(SOURCE_DIR, `note-${page.legacyNote}.html`)];
    let sourcePath;
    for (const candidate of candidates) {
      try { if ((await stat(candidate)).isFile()) { sourcePath = candidate; break; } } catch { /* next */ }
    }
    if (!sourcePath) fail(`Missing lwarp page for ${page.slug} (legacy note-${page.legacyNote}).`);
    rawPages.push({ page, sourcePath, source: await readFile(sourcePath, 'utf8') });
  }
  assertMathJaxPackages(rawPages);
  // PDF metadata may contain build timestamps. The downloadable PDF keeps its
  // own SHA-256 in content-manifest.json, but must not trigger a false SW update.
  const buildSeed = [SITE_ORIGIN, SITE_BASE_PATH, manifestSource, ...rawPages.flatMap(({ page, source }) => [page.slug, source])];
  const seedFiles = [
    path.join(ROOT, 'scripts', 'postprocess_web.mjs'),
    path.join(ROOT, 'web', 'math1-web.css'),
    ...await listFiles(path.join(ROOT, 'web', 'reader')),
    ...await listFiles(path.join(ROOT, 'web', 'pwa')),
  ];
  for (const asset of seedFiles) {
    buildSeed.push(path.relative(ROOT, asset), await readFile(asset));
  }
  const buildId = sha256(Buffer.concat(buildSeed.map((item) => Buffer.isBuffer(item) ? item : Buffer.from(item)))).slice(0, 20);
  await copyAssets(buildId);
  await mkdir(path.join(SITE_DIR, 'data'), { recursive: true });
  await mkdir(path.join(SITE_DIR, 'downloads'), { recursive: true });
  await writeFile(path.join(SITE_DIR, 'downloads', 'kaoyan-math1-notes.pdf'), pdf);

  const byLegacy = new Map(pages.map((page) => [page.legacyNote, page]));
  const bySlug = new Map(pages.map((page) => [page.slug, page]));
  const byLwarpSlug = new Map(pages.map((page) => [page.lwarpSlug, page]));
  const registry = await readProblemRegistry();
  const searchDocuments = [];

  for (let index = 0; index < rawPages.length; index += 1) {
    const { page, source } = rawPages[index];
    const $ = load(source, { decodeEntities: false });
    const originalMain = $('main.bodycontainer').first();
    if (!originalMain.length) fail(`Missing main.bodycontainer in ${page.slug}.`);
    $('a[href]').each((_, node) => $(node).attr('href', canonicalLink($(node).attr('href'), byLegacy, bySlug, byLwarpSlug)));
    const anchors = prepareContent($, originalMain, page);
    const outline = outlineMarkup($, originalMain, anchors);
    const featuredMetaNode = originalMain.find('.problem-meta').first();
    const featuredMetaText = featuredMetaNode.text().replace(/\s+/g, ' ').trim();
    const featuredMeta = featuredMetaNode.length ? $.html(featuredMetaNode) : '';
    featuredMetaNode.remove();
    const bodyContent = originalMain.html() ?? '';
    const previous = pages[index - 1] ?? null;
    const next = pages[index + 1] ?? null;
    const rendered = documentHtml({ $, bodyContent, featuredMeta, page, pages, buildId, previous, next, anchors, outline });
    await writeFile(path.join(SITE_DIR, `${page.slug}.html`), rendered.html, 'utf8');
    const fragment = load(`<main>${bodyContent}</main>`);
    fragment('[data-nosnippet]').remove();
    const headings = fragment('h2,h3').map((_, node) => fragment(node).text().trim()).get();
    const body = `${featuredMetaText} ${fragment('main').text()}`.replace(/\s+/g, ' ').trim();
    let tex = '';
    if (page.source) {
      try { tex = texPageFragment(page, await readFile(path.join(ROOT, page.source), 'utf8')); } catch { /* optional */ }
    }
    const problems = registry.filter((entry) => entry.id && (body.includes(entry.id) || tex.includes(entry.id)));
    searchDocuments.push({
      slug: page.slug,
      url: sitePath(page.slug),
      title: page.title,
      subject: page.subject,
      lecture: page.lecture,
      problemIds: problems.map((entry) => entry.id).filter(Boolean),
      tags: [...new Set(problems.flatMap((entry) => entry.tags ?? []))],
      difficulty: [...new Set(problems.map((entry) => entry.difficulty).filter(Boolean))],
      headings,
      body,
      tex,
    });
  }

  const home = documentHtml({ bodyContent: homeMarkup(pages), page: null, pages, buildId, previous: null, next: null, anchors: [], outline: '', isHome: true });
  await writeFile(path.join(SITE_DIR, 'index.html'), home.html, 'utf8');
  const pdfSha256 = sha256(pdf);
  const publicPages = pages.map((page, index) => ({ ...page, url: sitePath(page.slug), previous: pages[index - 1]?.slug ?? null, next: pages[index + 1]?.slug ?? null }));
  const assetRoot = sitePath(`assets/${buildId}`);
  await writeFile(path.join(SITE_DIR, 'data', 'content-manifest.json'), JSON.stringify({ schemaVersion: SCHEMA_VERSION, buildId, basePath: SITE_BASE_PATH, home: sitePath(), assets: { root: assetRoot, reader: `${assetRoot}/reader`, mathjax: `${assetRoot}/vendor/mathjax-3.2.2` }, pages: publicPages, pdf: { url: sitePath('downloads/kaoyan-math1-notes.pdf'), sha256: pdfSha256, bytes: pdf.length } }, null, 2), 'utf8');
  await writeFile(path.join(SITE_DIR, 'data', 'search-index.json'), JSON.stringify({ schemaVersion: SCHEMA_VERSION, buildId, documents: searchDocuments }), 'utf8');
  const { precache, totalBytes } = await writeDeploymentFiles(pages, buildId);
  console.log(`Postprocessed 53 HTML documents (build ${buildId}).`);
  console.log(`PWA precache: ${precache.length} URLs, ${totalBytes} bytes.`);
}

await main();
