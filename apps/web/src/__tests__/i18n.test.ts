import { readdirSync } from "node:fs";
import path from "node:path";
import { describe, expect, test } from "vitest";
import { createTranslator } from "next-intl";

import { isLocalized, localeHref, splitLocale } from "@/i18n/config";
import mEn from "@/i18n/messages/m.en.json";
import mHi from "@/i18n/messages/m.hi.json";
import siteEn from "@/i18n/messages/site.en.json";
import siteHi from "@/i18n/messages/site.hi.json";

type Tree = { [k: string]: string | Tree };
function leaves(tree: Tree, prefix = ""): [string, string][] {
  return Object.entries(tree).flatMap(([k, v]) =>
    typeof v === "string" ? [[`${prefix}${k}`, v] as [string, string]] : leaves(v, `${prefix}${k}.`),
  );
}
const keys = (t: Tree) => leaves(t).map(([k]) => k).sort();
const vars = (s: string) => [...s.matchAll(/\{(\w+)/g)].map((m) => m[1]).sort();

describe.each([
  ["site", siteEn as Tree, siteHi as Tree],
  ["m", mEn as Tree, mHi as Tree],
])("%s messages", (_, en, hi) => {
  test("Hindi has exactly the English keys (nothing missing, nothing extra)", () => {
    expect(keys(hi)).toEqual(keys(en));
  });

  test("the same placeholders in both languages, and every message parses (ICU)", () => {
    const hiMap = Object.fromEntries(leaves(hi));
    for (const [key, text] of leaves(en)) {
      expect(vars(hiMap[key]), key).toEqual(vars(text));
      for (const [locale, messages] of [["en", en], ["hi", hi]] as const) {
        const t = createTranslator({ locale, messages, onError: (e) => { throw e; } });
        const args = Object.fromEntries(vars(text).map((v) => [v, v === "count" ? 2 : "x"]));
        expect(() => t(key as never, args as never), `${locale} ${key}`).not.toThrow();
      }
    }
  });
});

test("only the message files we know about (each is listed in docs/hindi-review.md)", () => {
  const dir = path.join(__dirname, "../i18n/messages");
  expect(readdirSync(dir).sort()).toEqual(["m.en.json", "m.hi.json", "site.en.json", "site.hi.json"]);
});

test("links stay in the page's language; English addresses do not change", () => {
  expect(localeHref("en", "/diagnose")).toBe("/diagnose");
  expect(localeHref("hi", "/")).toBe("/hi");
  expect(localeHref("hi", "/diagnose?topic=ac")).toBe("/hi/diagnose?topic=ac");
  expect(localeHref("hi", "/diagnose/abc/result")).toBe("/hi/diagnose/abc/result");
  expect(localeHref("hi", "/request?session=abc")).toBe("/request?session=abc"); // English only page
  expect(localeHref("hi", "#how-it-works")).toBe("#how-it-works");
  expect(splitLocale("/hi/diagnose")).toEqual({ locale: "hi", path: "/diagnose" });
  expect(splitLocale("/hi")).toEqual({ locale: "hi", path: "/" });
  expect(splitLocale("/diagnose")).toEqual({ locale: "en", path: "/diagnose" });
  expect(isLocalized("/account")).toBe(false);
  expect(isLocalized("/m")).toBe(false);
});
