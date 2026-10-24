import { expect, type Page } from "@playwright/test";

export async function expectNoSideScroll(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}

/** Every visible button, link and pill toggle on the page is at least 44px tall. */
export async function expectTouchTargets(page: Page) {
  const small = await page.evaluate(() =>
    [...document.querySelectorAll("main button, main a, main input:not([type=radio]), main input[type=radio] + label")]
      .filter((el) => (el as HTMLElement).offsetParent !== null)
      .map((el) => ({ text: el.textContent?.trim().slice(0, 30), h: el.getBoundingClientRect().height }))
      .filter((t) => t.h < 44),
  );
  expect(small).toEqual([]);
}
