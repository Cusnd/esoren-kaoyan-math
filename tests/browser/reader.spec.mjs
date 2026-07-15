import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('renders formulas with local MathJax and supports keyboard search', async ({ page }, testInfo) => {
  test.skip((testInfo.project.use.viewport?.width ?? 0) < 1280);
  const externalRequests = [];
  const expectedOrigin = new URL(testInfo.project.use.baseURL ?? process.env.BASE_URL ?? 'http://127.0.0.1:8787').origin;
  page.on('request', (request) => {
    if (new URL(request.url()).origin !== expectedOrigin) externalRequests.push(request.url());
  });
  await page.goto('/calc-01-inverse-hyperbolic-sine');
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
  await page.locator('[data-reader-search-input]').fill('MATH1-CALC-0003');
  await expect(page.locator('[data-reader-search-results] a').first()).toBeVisible();
  await expect(page.locator('[data-reader-search-results] a').first()).toHaveAttribute('href', '/calc-01-inverse-hyperbolic-sine');
  expect(externalRequests).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
});

test('mobile directory is a focus-managed drawer', async ({ page }, testInfo) => {
  test.skip((testInfo.project.use.viewport?.width ?? 9999) > 390);
  await page.goto('/calc-01-inverse-function');
  const trigger = page.locator('[data-reader-action="open-nav"]');
  const triggerBox = await trigger.boundingBox();
  expect(triggerBox?.width).toBeGreaterThanOrEqual(44);
  expect(triggerBox?.height).toBeGreaterThanOrEqual(44);
  await trigger.click();
  await expect(page.locator('#reader-toc')).toHaveClass(/is-open/);
  await expect(trigger).toHaveAttribute('aria-expanded', 'true');
  await page.keyboard.press('Escape');
  await expect(page.locator('#reader-toc')).not.toHaveClass(/is-open/);
  await expect(trigger).toBeFocused();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
});

test('preferences persist locally and PDF opens through a static link', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'chrome-1280');
  await page.goto('/calc-01-inverse-function');
  await page.locator('[data-reader-action="open-preferences"]').first().click();
  await page.locator('[data-reader-preference="theme"][value="dark"]').click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await expect(page.locator('a[href="/downloads/kaoyan-math1-notes.pdf"][target="_blank"]')).toHaveAttribute('rel', /noopener/);
});

test('layout has no horizontal overflow across the viewport matrix', async ({ page }) => {
  await page.goto('/calc-01-inverse-function');
  await expect(page.locator('h1')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
});

test('200% zoom equivalent and reduced motion remain usable', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'edge-1440');
  await page.setViewportSize({ width: 720, height: 480 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/calc-01-inverse-function');
  await expect(page.locator('[data-reader-action="open-nav"]')).toBeVisible();
  await expect(page.locator('#reader-main')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  expect(await page.evaluate(() => getComputedStyle(document.documentElement).scrollBehavior)).toBe('auto');
});

test('print mode hides reader chrome', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'edge-1440');
  await page.goto('/calc-01-inverse-function');
  await page.emulateMedia({ media: 'print' });
  await expect(page.locator('.reader-topbar')).toBeHidden();
  await expect(page.locator('#reader-toc')).toBeHidden();
  await expect(page.locator('#reader-outline')).toBeHidden();
});

test('representative pages have no serious or critical axe violations', async ({ page }, testInfo) => {
  test.skip(!['edge-1440', 'edge-390'].includes(testInfo.project.name));
  test.setTimeout(90_000);
  await page.goto('/calc-01-inverse-function');
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
  await page.goto('/');
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
    if (!navigator.serviceWorker.controller) {
      await new Promise((resolve) => navigator.serviceWorker.addEventListener('controllerchange', resolve, { once: true }));
    }
  });
  const manifest = await page.evaluate(() => fetch('/data/content-manifest.json').then((response) => response.json()));
  await context.setOffline(true);
  try {
    const statuses = await page.evaluate(async (pages) => Promise.all(
      ['/', ...pages.map((item) => item.url)].map(async (url) => (await fetch(url)).status),
    ), manifest.pages);
    expect(statuses).toEqual(Array(53).fill(200));
    const legacy = await page.evaluate(() => fetch('/note-1.html').then((response) => response.text()));
    expect(legacy).toContain('第 1 讲 函数极限与连续');
    await page.goto('/note-1.html');
    await expect(page.locator('h1')).toContainText('第 1 讲 函数极限与连续');
    const unknown = await page.evaluate(() => fetch('/this-route-does-not-exist', {
      headers: { Accept: 'text/html' },
    }).then(async (response) => ({ status: response.status, body: await response.text() })));
    expect(unknown.status).toBe(200);
    expect(unknown.body).toContain('尚未保存在设备上');
  } finally {
    await context.setOffline(false);
  }
});
