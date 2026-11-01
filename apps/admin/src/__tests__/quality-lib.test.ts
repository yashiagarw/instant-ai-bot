import { expect, test } from "vitest";

import { visibleNav } from "@/lib/nav";
import { accuracyNote, dangerText, llmSpend, pct } from "@/lib/quality";

test("rates, the 30-case rule and danger cases", () => {
  expect([pct(0.6254), pct(1), pct(null), pct(undefined)]).toEqual(["62.5%", "100.0%", "–", "–"]);
  expect(accuracyNote({ cases: 8, enough: false, top1: null, top3: null }, 30)).toBe("Not enough data yet (8 of 30 cases)");
  expect(accuracyNote({ cases: 31, enough: true, top1: 0.5, top3: 0.7 }, 30)).toBeNull();
  expect(dangerText(1, 40)).toBe("1 of 40 danger cases missed");
  expect(dangerText(null, 0)).toBe("No danger cases in this run");
});

test("LLM spend says LLM off instead of zeros", () => {
  expect(llmSpend({ live: false })).toBe("LLM off");
  expect(llmSpend(null)).toBe("");
  const on = { live: true as const, calls: 1, cost_usd: 0.125, daily_cap_usd: 2, failures: 0, failure_rate: 0, fallbacks: 0,
    fallback_rate: 0, by_outcome: { ok: 1 } }; // prettier-ignore
  expect(llmSpend(on)).toBe("$0.13 of $2.00 a day · 1 call");
});

test("Quality is in the menu with quality.read only", () => {
  const labels = (perms: string[]) => visibleNav(perms).map((i) => i.label);
  expect(labels(["self", "content.read"])).not.toContain("Quality");
  expect(labels(["self", "quality.read"])).toEqual(["Overview", "Quality"]);
});
