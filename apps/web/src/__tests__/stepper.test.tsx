import { afterEach, expect, test } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { Stepper } from "@/components/stepper";

afterEach(cleanup);

test("marks the current step and the finished ones", () => {
  render(<Stepper current="Problem" />);
  const items = screen.getAllByRole("listitem");
  expect(items.map((li) => li.textContent?.replace(/\d/g, ""))).toEqual(["Car (done)", "Problem", "Questions", "Result"]);
  expect(items[1].getAttribute("aria-current")).toBe("step");
  expect(items.filter((li) => li.hasAttribute("aria-current"))).toHaveLength(1);
});
