import { afterEach, expect, test } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import Home from "../app/page";

afterEach(cleanup);

test("home page shows the heading, CTA and disclaimer", () => {
  render(<Home />);
  expect(screen.getByRole("heading", { level: 1 }).textContent).toMatch(/what's wrong with your car/i);
  const cta = screen.getByRole("button", { name: "Start free diagnosis" });
  expect(cta.dataset.size).toBe("cta");
  expect(screen.getByText(/not a replacement for a professional inspection/i)).toBeDefined();
});
