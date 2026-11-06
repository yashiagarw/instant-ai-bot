import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import { NotificationChoices } from "@/components/account/notification-choices";
import { AlertsButton, keyBytes } from "@/components/notify/alerts-button";
import { mockApi } from "./api-mock";
import { FakeSite } from "./fake-account";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }));

// A VAPID public key (65-byte uncompressed P-256 point, base64url).
const KEY = "BEl62iUYgUivxIkv69yViEuiBIa-Ib9-SkvMeAtA3LFgDzkrxZJjSgSnfckjBJuBkr3qBUYIHBQFLXYp5Nksh8U";

let site: FakeSite;

class FakeSubscription {
  endpoint = "https://fcm.googleapis.com/fcm/send/abc";
  unsubscribe = vi.fn(async () => {
    browser.subscription = null;
    return true;
  });
  toJSON() {
    return { endpoint: this.endpoint, keys: { p256dh: "BPubKey".padEnd(40, "x"), auth: "authsecret123456" } };
  }
}

const browser = {
  permission: "default" as NotificationPermission,
  answer: "granted" as NotificationPermission,
  subscription: null as FakeSubscription | null,
  subscribeOptions: null as unknown,
};

function pushCapableBrowser() {
  const pushManager = {
    getSubscription: vi.fn(async () => browser.subscription),
    subscribe: vi.fn(async (opts: unknown) => {
      browser.subscribeOptions = opts;
      browser.subscription = new FakeSubscription();
      return browser.subscription;
    }),
  };
  const reg = { pushManager };
  vi.stubGlobal("PushManager", function PushManager() {});
  const Notification = Object.assign(function Notification() {}, {
    get permission() {
      return browser.permission;
    },
    requestPermission: vi.fn(async () => (browser.permission = browser.answer)),
  });
  vi.stubGlobal("Notification", Notification);
  Object.defineProperty(navigator, "serviceWorker", {
    configurable: true,
    value: { register: vi.fn(async () => reg), ready: Promise.resolve(reg), getRegistration: vi.fn(async () => reg) },
  });
}

beforeEach(() => {
  site = new FakeSite();
  site.notifications.push_public_key = KEY;
  browser.permission = "default";
  browser.answer = "granted";
  browser.subscription = null;
  mockApi({}, site);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  Reflect.deleteProperty(navigator, "serviceWorker");
});

test("the VAPID key becomes the 65 bytes PushManager wants", () => {
  const bytes = keyBytes(KEY);
  expect(bytes.length).toBe(65);
  expect(bytes[0]).toBe(4); // uncompressed point
});

test("hidden when the server has no push key", async () => {
  site.notifications.push_public_key = null;
  pushCapableBrowser();
  const { container } = render(<AlertsButton />);
  await new Promise((r) => setTimeout(r, 20));
  expect(container.textContent).toBe("");
});

test("explains when the browser cannot show alerts", async () => {
  render(<AlertsButton />); // jsdom: no service worker, no PushManager
  expect((await screen.findByTestId("alerts")).textContent).toContain("This browser can't show alerts");
  expect(screen.queryByRole("button", { name: "Turn on alerts" })).toBeNull();
});

test("turn on alerts: permission, subscription with our key, saved on the server; then off again", async () => {
  pushCapableBrowser();
  render(<AlertsButton />);
  fireEvent.click(await screen.findByRole("button", { name: "Turn on alerts" }));
  expect((await screen.findByRole("status")).textContent).toBe("Alerts are on for this browser");
  expect(navigator.serviceWorker.register).toHaveBeenCalledWith("/sw.js", { scope: "/", updateViaCache: "none" });
  const opts = browser.subscribeOptions as { userVisibleOnly: boolean; applicationServerKey: Uint8Array };
  expect(opts.userVisibleOnly).toBe(true);
  expect(Array.from(opts.applicationServerKey)).toEqual(Array.from(keyBytes(KEY)));
  expect(site.pushSubscriptions).toEqual([
    {
      method: "POST",
      endpoint: "https://fcm.googleapis.com/fcm/send/abc",
      keys: { p256dh: "BPubKey".padEnd(40, "x"), auth: "authsecret123456" },
    },
  ]);

  fireEvent.click(screen.getByRole("button", { name: "Turn off" }));
  expect(await screen.findByRole("button", { name: "Turn on alerts" })).toBeDefined();
  expect(site.pushSubscriptions[1]).toMatchObject({ method: "DELETE", endpoint: "https://fcm.googleapis.com/fcm/send/abc" });
});

test("a person who blocks alerts is told how to allow them", async () => {
  pushCapableBrowser();
  browser.answer = "denied";
  render(<AlertsButton />);
  fireEvent.click(await screen.findByRole("button", { name: "Turn on alerts" }));
  expect((await screen.findByTestId("alerts")).textContent).toContain("Alerts are blocked for this site");
  expect(site.pushSubscriptions).toEqual([]);
});

test("account: SMS on / off and the WhatsApp opt-in with its exact wording", async () => {
  site.loggedIn = true;
  render(<NotificationChoices />);
  const card = await screen.findByTestId("notification-choices");
  const sms = await within(card).findByRole("switch", { name: /SMS updates/ });
  const whatsapp = within(card).getByRole("switch", { name: /WhatsApp updates/ });
  expect(sms).toHaveProperty("checked", true);
  expect(whatsapp).toHaveProperty("checked", false);
  expect(card.textContent).toContain("I can stop them at any time by sending STOP.");

  fireEvent.click(whatsapp);
  await waitFor(() => expect(within(card).getByRole("switch", { name: /WhatsApp updates/ })).toHaveProperty("checked", true));
  expect(site.choices.whatsapp.opted_in).toBe(true); // sent with the wording version (the fake refuses without it)
  fireEvent.click(within(card).getByRole("switch", { name: /SMS updates/ }));
  await waitFor(() => expect(site.choices.sms).toBe(false));
});
