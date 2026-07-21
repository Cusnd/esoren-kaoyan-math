import { readFile } from 'node:fs/promises';

import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { SITE_ROOT, sitePath } from '../../web/reader/site.js';

const WRITE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

function monitorReadOnlyRequests(page, testInfo) {
  const violations = [];
  const expectedOrigin = new URL(
    testInfo.project.use.baseURL ?? process.env.BASE_URL ?? 'http://127.0.0.1:8787',
  ).origin;
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.origin !== expectedOrigin) violations.push(`cross-origin ${request.method()} ${request.url()}`);
    if (WRITE_METHODS.has(request.method().toUpperCase())) {
      violations.push(`write ${request.method()} ${request.url()}`);
    }
  });
  return violations;
}

test('renders formulas with local MathJax and supports keyboard search', async ({ page }, testInfo) => {
  test.skip((testInfo.project.use.viewport?.width ?? 0) < 1280);
  const requestViolations = monitorReadOnlyRequests(page, testInfo);
  await page.goto(sitePath('calc-01-inverse-hyperbolic-sine'));
  await expect(page.locator('h1')).toHaveCount(1);
  const renderedFormula = page.locator([
    '#reader-main .problem-box mjx-container:visible',
    '#reader-main .solution-box mjx-container:visible',
    '#reader-main .knowledge-box mjx-container:visible',
    '#reader-main .mistake-box mjx-container:visible',
  ].join(', ')).first();
  await expect(renderedFormula).toBeVisible({ timeout: 20_000 });
  const formulaKinds = await page.evaluate(async () => {
    const fixture = document.createElement('section');
    fixture.id = 'mathjax-runtime-fixture';
    fixture.setAttribute('aria-label', 'MathJax runtime test fixture');
    fixture.innerHTML = [
      '<p>\\(a^2+b^2=c^2\\)</p>',
      '<div>\\[\\int_0^1 x^2\\,dx=\\frac13\\]</div>',
      '<div>\\[\\begin{aligned}f(x)&=x^2+1\\\\f\'(x)&=2x\\end{aligned}\\]</div>',
      '<div>\\[\\begin{pmatrix}1&0\\\\0&1\\end{pmatrix}\\]</div>',
    ].join('');
    document.body.append(fixture);
    await window.MathJax.startup.promise;
    await window.MathJax.typesetPromise([fixture]);
    return [...fixture.querySelectorAll('mjx-container')].map((container) => container.getAttribute('display') === 'true');
  });
  expect(formulaKinds).toEqual([false, true, true, true]);
  const visibleText = await page.locator('#reader-main').innerText();
  expect(visibleText).not.toContain('\\frac');
  expect(visibleText).not.toContain('\\sqrt');
  await page.keyboard.press('Control+K');
  await expect(page.locator('#reader-search')).toBeVisible();
  await expect(page.locator('body')).toHaveClass(/reader-modal-open/);
  expect(await page.evaluate(() => getComputedStyle(document.body).overflowY)).toBe('hidden');
  await page.locator('[data-reader-search-input]').fill('MATH1-CALC-0003');
  await expect(page.locator('[data-reader-search-results] a').first()).toBeVisible();
  await expect(page.locator('[data-reader-search-results] a').first()).toHaveAttribute('href', sitePath('calc-01-inverse-hyperbolic-sine'));
  await page.locator('#reader-search [data-reader-action="close-search"]').click();
  await expect(page.locator('#reader-search')).toBeHidden();
  await expect(page.locator('body')).not.toHaveClass(/reader-modal-open/);
  expect(await page.evaluate(() => getComputedStyle(document.body).overflowY)).toBe('auto');
  expect(requestViolations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
});

test('mobile directory is a focus-managed drawer', async ({ page }, testInfo) => {
  test.skip((testInfo.project.use.viewport?.width ?? 9999) > 390);
  await page.goto(sitePath('calc-01-inverse-function'));
  const trigger = page.locator('[data-reader-action="open-nav"]');
  const triggerBox = await trigger.boundingBox();
  expect(triggerBox?.width).toBeGreaterThanOrEqual(44);
  expect(triggerBox?.height).toBeGreaterThanOrEqual(44);
  await trigger.click();
  await expect(page.locator('#reader-toc')).toHaveClass(/is-open/);
  await expect(trigger).toHaveAttribute('aria-expanded', 'true');
  await expect(page.locator('body')).toHaveClass(/reader-drawer-open/);
  expect(await page.evaluate(() => getComputedStyle(document.body).overflowY)).toBe('hidden');
  await page.keyboard.press('Escape');
  await expect(page.locator('#reader-toc')).not.toHaveClass(/is-open/);
  await expect(trigger).toBeFocused();
  await expect(page.locator('body')).not.toHaveClass(/reader-drawer-open/);
  expect(await page.evaluate(() => getComputedStyle(document.body).overflowY)).toBe('auto');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
});

test('preferences persist locally and PDF opens through a static link', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'chrome-1280');
  await page.goto(sitePath('calc-01-inverse-function'));
  await page.locator('[data-reader-action="open-preferences"]').first().click();
  await page.locator('[data-reader-preference="theme"][value="dark"]').click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await expect(page.locator(`a[href="${sitePath('downloads/kaoyan-math1-notes.pdf')}"][target="_blank"]`)).toHaveAttribute('rel', /noopener/);
});

test('review reminders stay browser-local and synchronize across tabs', async ({ page, context }, testInfo) => {
  test.skip(!['chrome-1280', 'edge-1440'].includes(testInfo.project.name));
  await page.goto(sitePath('calc-01-inverse-hyperbolic-sine'));
  await expect(page.locator('[data-reader-relations]')).toBeVisible();
  await expect(page.getByRole('heading', { name: '可用方法' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '关联主库题' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '关联练习题' })).toBeVisible();
  await expect(page.locator('[data-reader-relations] .reader-relations__evidence a').first()).toContainText('MATH1-CALC-0003');
  await page.locator('[data-reader-action="open-review"]').first().click();
  await expect(page.locator('#reader-review')).toBeVisible();
  const exportButton = page.locator('#reader-review [data-reader-action="export-review-state"]');
  await exportButton.focus();
  await page.keyboard.press('Tab');
  const fileInput = page.locator('#reader-review [data-reader-review-import]');
  await expect(fileInput).toBeFocused();
  const fileButton = page.locator('#reader-review .reader-file-button');
  expect(await fileButton.evaluate((element) => getComputedStyle(element).outlineStyle)).not.toBe('none');
  await page.locator('#reader-review details > summary').click();
  const add = page.locator('#reader-review [data-reader-review-action="add"]').first();
  await expect(add).toBeVisible();
  const nodeId = await add.getAttribute('data-reader-review-node');
  await add.click();
  await expect.poll(() => page.evaluate((key) => JSON.parse(localStorage.getItem(key) || '{}').items ?? {}, 'math1.reader.reviews.v1'))
    .toHaveProperty(nodeId);

  const downloadPromise = page.waitForEvent('download');
  await exportButton.click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/^math1-learning-state-\d{4}-\d{2}-\d{2}\.json$/);
  const downloadPath = await download.path();
  expect(downloadPath).toBeTruthy();
  const importPayload = JSON.parse(await readFile(downloadPath, 'utf8'));
  expect(importPayload).toMatchObject({
    schemaVersion: 1,
    type: 'math1-reader-state',
  });
  expect(importPayload.reviews.items).toHaveProperty(nodeId);

  await fileInput.setInputFiles({
    name: download.suggestedFilename(),
    mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify(importPayload)),
  });
  await expect(page.locator('[data-reader-review-import-preview]')).toContainText('确认前不会修改浏览器状态');
  const applyImport = page.locator('[data-reader-action="apply-review-import"]');
  await expect(applyImport).toBeVisible();
  await applyImport.click();
  await expect(page.locator('#reader-review [data-reader-review-status]')).toContainText('导入已应用');

  await fileInput.setInputFiles({
    name: download.suggestedFilename(),
    mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify(importPayload)),
  });
  await expect(applyImport).toBeVisible();

  const second = await context.newPage();
  await second.goto(sitePath('calc-01-inverse-hyperbolic-sine'));
  await second.locator('[data-reader-action="open-review"]').first().click();
  const remove = second.locator(`[data-review-node="${nodeId}"] [data-reader-review-action="remove"]`).first();
  await expect(remove).toBeVisible();

  await remove.click();
  await expect(page.locator('[data-reader-review-import-preview]')).toContainText('导入预览已失效');
  await expect(applyImport).toBeHidden();
  await expect.poll(() => page.evaluate(({ key, id }) => JSON.parse(localStorage.getItem(key)).items[id].state, {
    key: 'math1.reader.reviews.v1',
    id: nodeId,
  })).toBe('removed');
  await second.close();
});

test('representative learning flows reject unsafe imports without network writes or local mutation', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'chrome-1280');
  const requestViolations = monitorReadOnlyRequests(page, testInfo);
  const storageKeys = [
    'math1.reader.preferences.v1',
    'math1.reader.progress.v1',
    'math1.reader.reviews.v1',
  ];
  const snapshot = () => page.evaluate((keys) => Object.fromEntries(
    keys.map((key) => [key, localStorage.getItem(key)]),
  ), storageKeys);

  await page.goto(SITE_ROOT);
  await page.locator('[data-reader-action="open-search"]').first().click();
  for (const [query, label, title] of [
    ['K001', '知识节点', '函数表示'],
    ['T05', '知识节点', '递推数列极限'],
    ['K044', '边界知识', '一致连续性'],
  ]) {
    await page.locator('[data-reader-search-input]').fill(query);
    const match = page.locator('[data-reader-search-results] a').first();
    await expect(match).toBeVisible();
    await expect(match.locator('.reader-search-result__title')).toContainText(title);
    await expect(match.locator('.reader-search-result__meta')).toContainText(label);
  }
  await page.locator('[data-reader-search-input]').fill('MATH1-CALC-0003');
  const result = page.locator('[data-reader-search-results] a').first();
  await expect(result).toBeVisible();
  await expect(result.locator('.reader-search-result__title')).toContainText('反双曲正弦');
  await result.click();
  await expect(page.locator('h1')).toContainText('反双曲正弦');
  await page.goto(sitePath('practice-calc-01'));
  await expect(page.locator('html')).toHaveAttribute('data-collection', 'practice');
  await page.locator('[data-reader-action="open-review"]').first().click();
  await page.locator('#reader-review details > summary').click();
  await page.locator('#reader-review [data-reader-review-action="add"]').first().click();

  const fileInput = page.locator('#reader-review [data-reader-review-import]');
  const applyImport = page.locator('[data-reader-action="apply-review-import"]');
  const before = await snapshot();
  await fileInput.setInputFiles({
    name: 'malformed.json',
    mimeType: 'application/json',
    buffer: Buffer.from('{"broken"'),
  });
  await expect(page.locator('[data-reader-review-import-preview]')).toContainText('导入失败');
  await expect(applyImport).toBeHidden();
  expect(await snapshot()).toEqual(before);

  const boundaryImport = await page.evaluate(async ({ manifestUrl, relationsUrl }) => {
    const [manifest, relations] = await Promise.all([
      fetch(manifestUrl).then((response) => response.json()),
      fetch(relationsUrl).then((response) => response.json()),
    ]);
    const boundary = relations.nodes.find((node) => node.reviewable === false);
    const now = new Date().toISOString();
    const reviews = JSON.parse(localStorage.getItem('math1.reader.reviews.v1'));
    reviews.updatedAt = now;
    reviews.items[boundary.id] = {
      state: 'active',
      step: 0,
      dueOn: now.slice(0, 10),
      lastReviewedOn: null,
      reviewCount: 0,
      snoozeCount: 0,
      labelSnapshot: boundary.title,
      updatedAt: now,
    };
    return {
      boundaryId: boundary.id,
      payload: {
        schemaVersion: 1,
        type: 'math1-reader-state',
        buildId: manifest.buildId,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'local',
        exportedAt: now,
        preferences: JSON.parse(localStorage.getItem('math1.reader.preferences.v1') || '{"schemaVersion":1,"theme":"light","fontScale":"medium","contentWidth":"standard"}'),
        progress: JSON.parse(localStorage.getItem('math1.reader.progress.v1') || '{"schemaVersion":1,"recentSlug":null,"pages":{}}'),
        reviews,
      },
    };
  }, {
    manifestUrl: sitePath('data/content-manifest.json'),
    relationsUrl: sitePath('data/relation-index.json'),
  });
  await expect(page.locator(`#reader-review [data-review-node="${boundaryImport.boundaryId}"]`)).toHaveCount(0);
  await fileInput.setInputFiles({
    name: 'boundary.json',
    mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify(boundaryImport.payload)),
  });
  await expect(page.locator('[data-reader-review-import-preview]')).toContainText('边界知识不能导入复习状态');
  await expect(applyImport).toBeHidden();
  expect(await snapshot()).toEqual(before);

  const unsafe = await page.evaluate(async (manifestUrl) => {
    const manifest = await fetch(manifestUrl).then((response) => response.json());
    const now = new Date().toISOString();
    const slug = 'practice-calc-01';
    return {
      schemaVersion: 1,
      type: 'math1-reader-state',
      buildId: manifest.buildId,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'local',
      exportedAt: now,
      preferences: JSON.parse(localStorage.getItem('math1.reader.preferences.v1') || '{"schemaVersion":1,"theme":"light","fontScale":"medium","contentWidth":"standard"}'),
      progress: {
        schemaVersion: 1,
        recentSlug: slug,
        pages: {
          [slug]: {
            maxRatio: 0,
            lastAnchor: '',
            complete: false,
            title: '练习库',
            url: 'javascript:alert(1)',
            updatedAt: now,
          },
        },
      },
      reviews: JSON.parse(localStorage.getItem('math1.reader.reviews.v1')),
    };
  }, sitePath('data/content-manifest.json'));
  await fileInput.setInputFiles({
    name: 'unsafe.json',
    mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify(unsafe)),
  });
  await expect(page.locator('[data-reader-review-import-preview]')).toContainText('/math/ 同源相对路径');
  await expect(applyImport).toBeHidden();
  expect(await snapshot()).toEqual(before);
  await page.waitForLoadState('networkidle');
  expect(requestViolations).toEqual([]);
});

test('review actions disclose when browser storage rejects persistence', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'chrome-1280');
  await page.addInitScript((reviewKey) => {
    const original = Storage.prototype.setItem;
    Storage.prototype.setItem = function setItem(key, value) {
      if (key === reviewKey) throw new DOMException('Mock quota failure', 'QuotaExceededError');
      return original.call(this, key, value);
    };
  }, 'math1.reader.reviews.v1');
  await page.goto(sitePath('calc-01-inverse-hyperbolic-sine'));
  const action = page.locator('[data-reader-relations] .reader-relations__current [data-reader-review-action="add"]').first();
  await expect(action).toBeVisible();
  await action.click();
  await expect(page.locator('[data-reader-relations] [data-reader-review-status]')).toContainText('仅在本次页面打开期间临时保存');
  await expect(page.locator('[data-reader-relations] .reader-relations__current [data-reader-review-action="remove"]').first()).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem('math1.reader.reviews.v1'))).toBeNull();
  await page.reload();
  await expect(page.locator('[data-reader-relations] .reader-relations__current [data-reader-review-action="add"]').first()).toBeVisible();
});

test('a resident review page refreshes when the local calendar crosses midnight', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'chrome-1280');
  await page.clock.install({ time: new Date(2026, 6, 18, 23, 55, 0) });
  await page.goto(sitePath('calc-01-inverse-hyperbolic-sine'));
  const add = page.locator('[data-reader-relations] .reader-relations__current [data-reader-review-action="add"]').first();
  await expect(add).toBeVisible();
  const nodeId = await add.getAttribute('data-reader-review-node');
  await add.click();
  await page.locator('[data-reader-action="open-review"]').first().click();
  const dueRow = page.locator(`[data-reader-review-due] [data-review-node="${nodeId}"]`);
  await expect(dueRow).toBeVisible();
  await page.clock.pauseAt(new Date(2026, 6, 18, 23, 59, 58));
  await dueRow.locator('[data-reader-review-action="tomorrow"]').click();
  await expect(dueRow).toHaveCount(0);

  await page.clock.runFor(3_000);
  await expect(page.locator(`[data-reader-review-due] [data-review-node="${nodeId}"]`)).toBeVisible();
});

test('layout has no horizontal overflow across the viewport matrix', async ({ page }) => {
  await page.goto(sitePath('calc-01-inverse-function'));
  await expect(page.locator('h1')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
});

test('long chapters scroll and update progress across the viewport matrix', async ({ page }) => {
  await page.goto(sitePath('calc-01-inverse-function'));
  await expect(page.locator('h1')).toBeVisible();
  const initial = await page.evaluate(() => ({
    height: document.documentElement.scrollHeight,
    viewport: window.innerHeight,
    y: window.scrollY,
    overflowY: getComputedStyle(document.body).overflowY,
  }));
  expect(initial.height).toBeGreaterThan(initial.viewport);
  expect(initial.y).toBe(0);
  expect(initial.overflowY).toBe('auto');

  const viewport = page.viewportSize();
  await page.mouse.move((viewport?.width ?? 800) / 2, (viewport?.height ?? 600) / 2);
  await page.mouse.wheel(0, 720);
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(0);
  await expect.poll(() => page.evaluate(() => Math.max(
    ...[...document.querySelectorAll('[data-reader-progress]')]
      .map((element) => Number(element.getAttribute('aria-valuenow')) || 0),
  ))).toBeGreaterThan(0);
});

test('200% zoom equivalent and reduced motion remain usable', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'edge-1440');
  await page.setViewportSize({ width: 720, height: 480 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto(sitePath('calc-01-inverse-function'));
  await expect(page.locator('[data-reader-action="open-nav"]')).toBeVisible();
  await expect(page.locator('#reader-main')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  expect(await page.evaluate(() => getComputedStyle(document.documentElement).scrollBehavior)).toBe('auto');
});

test('print mode hides reader chrome', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'edge-1440');
  await page.goto(sitePath('calc-01-inverse-function'));
  await page.emulateMedia({ media: 'print' });
  await expect(page.locator('.reader-topbar')).toBeHidden();
  await expect(page.locator('#reader-toc')).toBeHidden();
  await expect(page.locator('#reader-outline')).toBeHidden();
});

test('representative pages have no serious or critical axe violations', async ({ page }, testInfo) => {
  test.skip(!['edge-1440', 'edge-390'].includes(testInfo.project.name));
  test.setTimeout(90_000);
  await page.goto(sitePath('calc-01-inverse-function'));
  await expect(page.locator('#reader-main')).toBeVisible();
  await page.evaluate(() => window.MathJax?.startup?.promise);
  const results = await new AxeBuilder({ page })
    .exclude('[data-nosnippet]')
    .withTags(['wcag2a', 'wcag2aa'])
    .analyze();
  const blocking = results.violations.filter((violation) => ['serious', 'critical'].includes(violation.impact));
  expect(blocking, blocking.map((violation) => `${violation.id}: ${violation.help}`).join('\n')).toEqual([]);
});

test('complete corpus and legacy routes remain available offline', async ({ page, context }, testInfo) => {
  test.skip(testInfo.project.name !== 'edge-1440');
  await page.goto(SITE_ROOT);
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
    if (!navigator.serviceWorker.controller) {
      await new Promise((resolve) => navigator.serviceWorker.addEventListener('controllerchange', resolve, { once: true }));
    }
  });
  const manifest = await page.evaluate((url) => fetch(url).then((response) => response.json()), sitePath('data/content-manifest.json'));
  await context.setOffline(true);
  try {
    const statuses = await page.evaluate(async ({ home, pages }) => Promise.all(
      [home, ...pages.map((item) => item.url)].map(async (url) => (await fetch(url)).status),
    ), manifest);
    expect(statuses).toEqual(Array(manifest.pages.length + 1).fill(200));
    const legacy = await page.evaluate((url) => fetch(url).then((response) => response.text()), sitePath('note-1.html'));
    expect(legacy).toContain('第 1 讲 函数极限与连续');
    await page.goto(sitePath('note-1.html'));
    await expect(page.locator('h1')).toContainText('第 1 讲 函数极限与连续');
    const unknown = await page.evaluate((url) => fetch(url, {
      headers: { Accept: 'text/html' },
    }).then(async (response) => ({ status: response.status, body: await response.text() })), sitePath('this-route-does-not-exist'));
    expect(unknown.status).toBe(200);
    expect(unknown.body).toContain('尚未保存在设备上');
  } finally {
    await context.setOffline(false);
  }
});
