import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import { RequestForm } from "@/components/request/request-form";
import { mockApi } from "./api-mock";
import { FakeDiagnosis } from "./fake-diagnosis";

let fake: FakeDiagnosis;

function session(body: Record<string, unknown>, answers: (number | string)[] = []) {
  const id = (fake.handle("POST", "/api/diagnosis/sessions", body)!.json as { session_id: string }).session_id;
  for (const a of answers) {
    const s = fake.sessions.get(id)!;
    fake.handle("POST", `/api/diagnosis/sessions/${id}/answers`, { question_id: s.flow[s.answers.length].id, option_id: a });
  }
  return id;
}

const consentBox = () => screen.getByRole("checkbox", { name: /Instant Mechanic's team may use/ });
const whatsappBox = () => screen.getByRole("checkbox", { name: /updates about my mechanic request on WhatsApp/ });

function fill(fields: Record<string, string>) {
  for (const [label, value] of Object.entries(fields)) fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

beforeEach(() => {
  fake = new FakeDiagnosis();
  mockApi({}, fake);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("prefilled with the car and diagnosis; consent starts unticked; all fields are there", async () => {
  const id = session({ vehicle: { variant_id: 16 }, topic_id: "tyres" }, [85, 91]);
  render(<RequestForm sessionId={id} />);
  expect((await screen.findByTestId("request-car")).textContent).toContain("Maruti Suzuki Swift");
  expect(screen.getByTestId("request-diagnosis").textContent).toBe("Tyres · Likely cause: Slow/pinhole puncture");
  expect(consentBox()).toHaveProperty("checked", false);
  expect(whatsappBox()).toHaveProperty("checked", false); // optional, separate, never pre-ticked
  expect(screen.getByTestId("whatsapp-consent-text").textContent).toContain("by sending STOP");
  expect(screen.getByTestId("consent-text").textContent).toContain("Instant Mechanic's team");
  for (const label of ["Your name", "Mobile number", "Area, sector or landmark", "Pincode", "Address (optional)", "Notes (optional)"]) {
    expect(screen.getByLabelText(label)).toBeDefined();
  }
  expect(screen.getByRole("group", { name: "How should we help?" })).toBeDefined();
  expect(screen.getByRole("group", { name: "Preferred time (optional)" })).toBeDefined();
  expect(screen.getByTestId("helpline").textContent).toContain("Helpline: +91-00000-11111");
});

test("validates name, mobile, service, area, pincode and consent before sending", async () => {
  render(<RequestForm sessionId={null} />);
  fireEvent.click(await screen.findByRole("button", { name: "Request a Mechanic" }));
  for (const msg of [/Type your name/, /10-digit Indian mobile/, /Choose how we should help/, /Type your area/, /6-digit pincode/, /Tick the box/]) {
    expect(screen.getByText(msg)).toBeDefined();
  }
  await waitFor(() => expect(document.activeElement).toBe(screen.getByLabelText("Your name")));
  fill({ "Mobile number": "5876543210" });
  fireEvent.click(screen.getByRole("button", { name: "Request a Mechanic" }));
  expect(screen.getByText(/10-digit Indian mobile/)).toBeDefined();
  expect(fake.requests).toEqual([]);
});

test("sends the request and shows the reference, next steps and the helpline as text", async () => {
  const id = session({ vehicle: { variant_id: 16 }, topic_id: "tyres" }, [85, 91]);
  render(<RequestForm sessionId={id} />);
  await screen.findByTestId("request-car");
  fill({ "Your name": "Asha Verma", "Mobile number": "+91 98765 43210", "Area, sector or landmark": "Sector 62, Noida", Pincode: "201309" });
  fireEvent.click(within(screen.getByRole("group", { name: "How should we help?" })).getByRole("radio", { name: /Workshop visit/ }));
  fireEvent.click(within(screen.getByRole("group", { name: "Preferred time (optional)" })).getByRole("radio", { name: "Tomorrow morning" }));
  fireEvent.click(consentBox());
  fireEvent.click(screen.getByRole("button", { name: "Request a Mechanic" }));

  const done = await screen.findByTestId("confirmation");
  expect(within(done).getByTestId("reference").textContent).toBe("IM-TEST1");
  expect(within(done).getByText("What happens next")).toBeDefined();
  expect(done.textContent).toContain("Helpline: +91-00000-11111");
  expect(within(done).queryByRole("link", { name: /\+91/ })).toBeNull(); // shown as text
  await waitFor(() => expect(document.activeElement?.id).toBe("done-heading"));
  expect(fake.requests[0]).toMatchObject({
    session_id: id,
    name: "Asha Verma",
    service_type: "workshop",
    preferred_time: "tomorrow_morning",
    consent: true,
    consent_text_version: "request-v1",
    whatsapp_optin: false,
    whatsapp_consent_version: null,
    urgent: false,
  });
});

test("WhatsApp updates only when the separate box is ticked, with its wording version", async () => {
  render(<RequestForm sessionId={null} />);
  await screen.findByLabelText("Your name");
  fill({ "Your name": "Asha", "Mobile number": "9876543210", "Area, sector or landmark": "Dwarka", Pincode: "110075" });
  fireEvent.click(screen.getByRole("radio", { name: /At my location/ }));
  fireEvent.click(whatsappBox());
  fireEvent.click(screen.getByRole("button", { name: "Request a Mechanic" }));
  // Ticking WhatsApp is not the consent to share details: that box is still required.
  expect(await screen.findByText("Tick the box so we can share your details with our team.")).toBeDefined();
  expect(fake.requests).toEqual([]);
  fireEvent.click(consentBox());
  fireEvent.click(screen.getByRole("button", { name: "Request a Mechanic" }));
  await screen.findByTestId("confirmation");
  expect(fake.requests[0]).toMatchObject({ whatsapp_optin: true, whatsapp_consent_version: "whatsapp-customer-v1" });
});

test("emergency: helpline at the top, optional fields skipped, pincode optional, marked urgent", async () => {
  const id = session({ vehicle: { variant_id: 16 }, topic_id: "flat_tyre" }, [302]);
  render(<RequestForm sessionId={id} />);
  expect((await screen.findByRole("heading", { level: 1 })).textContent).toBe("Get help now");
  const helpline = screen.getByTestId("helpline");
  expect(helpline.textContent).toContain("+91-00000-11111");
  expect(within(helpline).getByRole("link", { name: "Call now" }).getAttribute("href")).toBe("tel:+910000011111");
  expect(helpline.compareDocumentPosition(screen.getByLabelText("Your name")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  for (const label of ["Address (optional)", "Notes (optional)"]) expect(screen.queryByLabelText(label)).toBeNull();
  expect(screen.queryByRole("group", { name: "Preferred time (optional)" })).toBeNull();
  expect(screen.getByLabelText("Pincode (optional)")).toBeDefined();

  fill({ "Your name": "Ravi", "Mobile number": "9876543210", "Area, sector or landmark": "NH-48 near Manesar toll" });
  fireEvent.click(consentBox());
  fireEvent.click(screen.getByRole("button", { name: "Send urgent request" }));
  expect((await screen.findByTestId("confirmation")).textContent).toContain("(urgent)");
  expect(fake.requests[0]).toMatchObject({ urgent: true, pincode: "", service_type: "at_location", notes: "" });
});

test("a refused request shows the reason and keeps the form", async () => {
  class Busy extends FakeDiagnosis {
    handle(method: string, path: string, body?: unknown) {
      if (path === "/api/service-requests" && method === "POST") return {
          status: 429,
          json: { detail: "Too many requests from this address. Please call the helpline or try again shortly." },
        };
      return super.handle(method, path, body);
    }
  }
  fake = new Busy();
  mockApi({}, fake);
  render(<RequestForm sessionId={null} />);
  await screen.findByLabelText("Your name");
  fill({ "Your name": "Asha", "Mobile number": "9876543210", "Area, sector or landmark": "Dwarka", Pincode: "110075" });
  fireEvent.click(screen.getByRole("radio", { name: /At my location/ }));
  fireEvent.click(consentBox());
  fireEvent.click(screen.getByRole("button", { name: "Request a Mechanic" }));
  expect((await screen.findByRole("alert")).textContent).toMatch(/Too many requests from this address\. Please call the helpline/);
  expect(screen.getByLabelText("Your name")).toHaveProperty("value", "Asha");
});
