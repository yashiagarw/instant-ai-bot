import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import Home from "../app/page";
import { mockApi } from "./api-mock";

beforeEach(() => mockApi());
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("home page shows the heading, CTAs and disclaimer", () => {
  render(<Home />);
  expect(screen.getByRole("heading", { level: 1 }).textContent).toMatch(/what's wrong with your car in 2 minutes/i);
  const cta = screen.getByRole("link", { name: /start free diagnosis/i });
  expect(cta.getAttribute("href")).toBe("/diagnose");
  expect(cta.dataset.size).toBe("cta");
  expect(screen.getByRole("link", { name: "How it works" }).getAttribute("href")).toBe("#how-it-works");
  expect(screen.getByText(/not a replacement for a professional inspection/i)).toBeDefined();
});

test("how it works has three steps", () => {
  render(<Home />);
  const section = screen.getByRole("heading", { name: "How it works" }).closest("section")!;
  expect(section.querySelectorAll("ol > li")).toHaveLength(3);
});
