const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { execFileSync } = require('node:child_process');
const { test, expect } = require('@playwright/test');

const root = path.resolve(__dirname, '..');
const readers = [
  { name: 'bilingual', file: 'public/lalka-2/chapter-02.html', english: false },
  { name: 'trilingual', file: 'public/conrad-tajny-agent/chapter-01.html', english: true },
];

for (const reader of readers) {
  test(`${reader.name}: local file loads shared assets and plays audio`, async ({ page }) => {
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(pathToFileURL(path.join(root, reader.file)).href);
    const cards = page.locator('.unit');
    await expect(cards.first()).toBeVisible();
    const assets = await page.evaluate(() => ({
      script: document.querySelector('script[src]')?.src,
      stylesheet: document.querySelector('link[rel="stylesheet"]')?.href,
      stylesheetLoaded: Array.from(document.styleSheets).some(sheet =>
        sheet.href && sheet.href.endsWith('/reader/reader.css')),
      english: document.querySelectorAll('.stack.en').length,
    }));
    expect(assets.script).toMatch(/^file:.*\/reader\/reader-bundle\.js\?v=[0-9a-f]{16}$/);
    expect(assets.stylesheet).toMatch(/^file:.*\/reader\/reader\.css$/);
    expect(assets.stylesheetLoaded).toBe(true);
    expect(assets.english > 0).toBe(reader.english);

    const audio = page.locator('#audio');
    await expect.poll(() => audio.evaluate(el => el.readyState), { timeout: 30_000 }).toBeGreaterThanOrEqual(1);
    expect(await audio.evaluate(el => el.currentSrc)).toMatch(/^file:.*\.webm$/);
    await cards.first().locator('.play').click();
    await expect.poll(() => audio.evaluate(el => !el.paused)).toBe(true);
    await expect.poll(() => audio.evaluate(el => el.currentTime)).toBeGreaterThan(0);
    await cards.first().locator('.play').click();
    await expect.poll(() => audio.evaluate(el => el.paused)).toBe(true);
    expect(errors).toEqual([]);
  });
}

test('shared bundle and versioned references are current', () => {
  expect(() => execFileSync('python3', ['scripts/build_reader_bundle.py', '--check'], {
    cwd: root,
    encoding: 'utf8',
  })).not.toThrow();
});
