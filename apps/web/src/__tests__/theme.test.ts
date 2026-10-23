import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "vitest";

const css = readFileSync(join(__dirname, "../app/globals.css"), "utf8");

// Colour tokens from CLAUDE.md "Design".
const BRAND = {
  "--color-brand": "#f07a2a",
  "--color-cta": "#d9620f",
  "--color-orange-text": "#b4500d",
  "--color-ink": "#15120f",
  "--color-warm-white": "#fff6ee",
  "--color-danger": "#c62828",
};

test.each(Object.entries(BRAND))("theme defines %s as %s", (token, value) => {
  expect(css.toLowerCase()).toContain(`${token}: ${value};`);
});

test("shadcn primary is the CTA fill, destructive is danger, focus ring is orange text", () => {
  expect(css).toContain("--primary: var(--color-cta);");
  expect(css).toContain("--primary-foreground: #ffffff;");
  expect(css).toContain("--destructive: var(--color-danger);");
  expect(css).toContain("--ring: var(--color-orange-text);");
});
