const { test, expect } = require('@playwright/test');

const readers = [
  { name: 'bilingual', path: '/lalka-2/chapter-02.html', english: false },
  { name: 'trilingual', path: '/conrad-tajny-agent/chapter-01.html', english: true },
];

for (const reader of readers) {
  test(`${reader.name}: translations, keyboard, footnotes and anchors`, async ({ page }) => {
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`${reader.path}#u-2`);

    const cards = page.locator('.unit');
    await expect(cards.nth(1)).toHaveAttribute('id', 'u-2');
    await expect(cards.nth(1)).toHaveClass(/is-selected/);
    const first = cards.first();
    const ukrainian = first.locator('.stack.ua');
    const uaButton = first.getByRole('button', { name: /^UA/ });
    await expect(ukrainian).toBeHidden();
    await uaButton.click();
    await expect(ukrainian).toBeVisible();
    await expect(uaButton).toHaveAttribute('aria-expanded', 'true');
    await uaButton.click();
    await expect(ukrainian).toBeHidden();

    const english = first.locator('.stack.en');
    if (reader.english) {
      const enButton = first.getByRole('button', { name: /^EN/ });
      await expect(english).toBeHidden();
      await enButton.click();
      await expect(english).toBeVisible();
      await expect(enButton).toHaveAttribute('aria-expanded', 'true');
      await enButton.click();
      await expect(english).toBeHidden();
    } else {
      await expect(english).toHaveCount(0);
      await expect(page.locator('#toggleEn')).toHaveCount(0);
    }

    await page.locator('body').focus();
    await page.keyboard.press('u');
    await expect(ukrainian).toBeVisible();
    if (reader.english) {
      await page.keyboard.press('e');
      await expect(english).toBeVisible();
    }

    const footnote = page.locator('.footnote-ref').first();
    const tooltip = footnote.locator('[role="tooltip"]');
    await expect(footnote).toHaveAttribute('tabindex', '0');
    await footnote.focus();
    await expect(tooltip).toBeVisible();
    await expect(tooltip.locator('.note-pl')).not.toBeEmpty();
    await expect(tooltip.locator('.note-ua')).not.toBeEmpty();
    await footnote.blur();
    await expect(tooltip).toBeHidden();
    await footnote.hover();
    await expect(tooltip).toBeVisible();
    expect(errors).toEqual([]);
  });
}
