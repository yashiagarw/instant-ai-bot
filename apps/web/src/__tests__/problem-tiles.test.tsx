import { afterEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { ProblemTiles } from "@/components/landing/problem-tiles";
import { mockApi } from "./api-mock";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("shows skeletons, then problem tiles and the emergency row linking to the diagnosis", async () => {
  mockApi();
  render(<ProblemTiles />);
  expect(screen.getByRole("status").textContent).toMatch(/loading problems/i);
  const tyres = await screen.findByRole("link", { name: "Tyres" });
  expect(tyres.getAttribute("href")).toBe("/diagnose?topic=tyres");
  const urgent = screen.getByRole("heading", { name: /need help right now/i }).closest("section")!;
  const labels = [...urgent.querySelectorAll("a")].map((a) => a.textContent);
  expect(labels).toHaveLength(9);
  expect(labels.slice(0, 2)).toEqual(["Battery dead", "Flat tyre"]);
  expect(screen.queryByRole("link", { name: "Flat tyre" })?.getAttribute("href")).toBe("/diagnose?topic=flat_tyre");
});

test("shows a clear error with a working retry", async () => {
  const fetchMock = mockApi({ "/api/categories": "offline" });
  render(<ProblemTiles />);
  expect((await screen.findByRole("alert")).textContent).toMatch(/couldn't reach our server/i);
  mockApi();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByRole("link", { name: "AC not cooling" })).toBeDefined();
  expect(fetchMock).toHaveBeenCalledTimes(1);
});
