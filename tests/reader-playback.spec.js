const { test, expect } = require('@playwright/test');

const readers = [
  { name: 'bilingual', path: '/lalka-2/chapter-02.html' },
  { name: 'trilingual', path: '/conrad-tajny-agent/chapter-01.html' },
];

for (const reader of readers) {
  test(`${reader.name}: section boundaries and continuous playback`, async ({ page }) => {
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(reader.path);
    const audio = page.locator('#audio');
    const cards = page.locator('.unit');
    await expect(cards.first()).toBeVisible();
    await expect.poll(() => audio.evaluate(el => ({
      ready: el.readyState,
      src: el.currentSrc,
    })), { timeout: 45_000 }).toMatchObject({
      ready: expect.any(Number),
      src: expect.stringMatching(/^blob:/),
    });
    await expect.poll(() => audio.evaluate(el => el.readyState)).toBeGreaterThanOrEqual(1);

    const times = await page.evaluate(() => ({
      start: CHAPTER[0].start,
      boundary: endOf(0),
    }));
    await cards.nth(0).locator('.play').click();
    await expect.poll(() => audio.evaluate(el => !el.paused)).toBe(true);
    const playingAt = await audio.evaluate(el => el.currentTime);
    expect(playingAt).toBeGreaterThanOrEqual(times.start - 0.3);
    expect(playingAt).toBeLessThan(times.boundary);

    await audio.evaluate((el, boundary) => { el.currentTime = boundary - 0.3; }, times.boundary);
    await expect.poll(() => audio.evaluate(el => el.paused), { timeout: 5_000 }).toBe(true);
    const stoppedAt = await audio.evaluate(el => el.currentTime);
    expect(stoppedAt).toBeGreaterThanOrEqual(times.boundary - 0.3);
    expect(stoppedAt).toBeLessThanOrEqual(times.boundary + 0.4);

    await cards.nth(0).locator('.pl').click();
    const continuous = page.locator('#continuous');
    await continuous.click();
    await expect(continuous).toHaveAttribute('aria-pressed', 'true');
    await expect.poll(() => audio.evaluate(el => !el.paused)).toBe(true);
    await audio.evaluate((el, boundary) => { el.currentTime = boundary - 0.3; }, times.boundary);
    await expect(cards.nth(1)).toHaveClass(/is-playing/, { timeout: 5_000 });
    await expect.poll(() => audio.evaluate(el => !el.paused)).toBe(true);
    await continuous.click();
    await expect.poll(() => audio.evaluate(el => el.paused)).toBe(true);
    expect(errors).toEqual([]);
  });
}
