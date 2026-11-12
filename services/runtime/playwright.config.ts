import { defineConfig } from '@playwright/test';

const baseURL = 'http://127.0.0.1:12937';

export default defineConfig({
  testDir: './tests/browser',
  fullyParallel: false,
  workers: 1,
  timeout: 30000,
  reporter: 'list',
  outputDir: 'test-results',
  use: {
    baseURL,
    channel: 'chrome',
    headless: true,
    locale: 'zh-CN',
    timezoneId: 'UTC',
    viewport: { width: 1440, height: 1000 },
    launchOptions: { args: ['--no-sandbox', '--disable-dev-shm-usage'] },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'bun src/control/cli.ts --demo',
    url: baseURL + '/api/health',
    reuseExistingServer: false,
    env: { CCRB_PORT: '12937', CCRB_MODE: 'demo' },
    gracefulShutdown: { signal: 'SIGTERM', timeout: 10000 },
  },
});
