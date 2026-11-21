const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests',
  timeout: 60_000,
  use: {
    browserName: 'chromium',
    baseURL: 'http://127.0.0.1:18770',
  },
  webServer: {
    command: 'python3 -m http.server 18770 --bind 127.0.0.1 --directory public',
    url: 'http://127.0.0.1:18770',
    reuseExistingServer: false,
    timeout: 15_000,
  },
});
