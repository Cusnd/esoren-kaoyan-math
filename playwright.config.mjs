import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.BASE_URL ?? 'http://127.0.0.1:8787';
const startServer = process.env.PLAYWRIGHT_START_SERVER === '1';

export default defineConfig({
  testDir: './tests/browser',
  fullyParallel: false,
  retries: 0,
  reporter: 'line',
  timeout: 60_000,
  workers: Number(process.env.PLAYWRIGHT_WORKERS ?? 3),
  use: {
    baseURL,
    trace: 'retain-on-failure',
  },
  webServer: startServer ? {
    command: 'npx wrangler dev --local --ip 127.0.0.1 --port 8787',
    url: baseURL,
    reuseExistingServer: true,
    timeout: 120_000,
  } : undefined,
  projects: [
    { name: 'edge-1440', use: { ...devices['Desktop Edge'], channel: 'msedge', viewport: { width: 1440, height: 960 } } },
    { name: 'chrome-1280', use: { ...devices['Desktop Chrome'], channel: 'chrome', viewport: { width: 1280, height: 900 } } },
    { name: 'firefox-1280', use: { ...devices['Desktop Firefox'], viewport: { width: 1280, height: 900 } } },
    { name: 'edge-768', use: { ...devices['Desktop Edge'], channel: 'msedge', viewport: { width: 768, height: 1024 } } },
    { name: 'edge-390', use: { ...devices['Pixel 5'], channel: 'msedge', viewport: { width: 390, height: 844 } } },
    { name: 'edge-360', use: { ...devices['Pixel 5'], channel: 'msedge', viewport: { width: 360, height: 800 } } },
  ],
});
