import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import { checkPhoto, PhotoStep } from "@/components/diagnose/photo-step";
import { mockApi } from "./api-mock";
import { FakePhotos, STORAGE_URL } from "./fake-photos";

let photos: FakePhotos;
let coarse = false;
let xhrStatus = 204;
const sentTo: string[] = [];
const sentKeys: string[][] = [];

/** XMLHttpRequest stand-in: reports upload progress halfway, then answers `xhrStatus` (0 = network error). */
class FakeXHR {
  upload: { onprogress: ((e: { lengthComputable: boolean; loaded: number; total: number }) => void) | null } = {
    onprogress: null,
  };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onabort: (() => void) | null = null;
  status = 0;
  private url = "";
  open(_method: string, url: string) {
    this.url = url;
  }
  abort() {
    this.onabort?.();
  }
  send(body: FormData) {
    sentTo.push(this.url);
    sentKeys.push([...body.keys()]);
    setTimeout(() => {
      this.upload.onprogress?.({ lengthComputable: true, loaded: 50, total: 100 });
      setTimeout(() => {
        this.status = xhrStatus;
        if (xhrStatus === 0) this.onerror?.();
        else this.onload?.();
      }, 30);
    }, 10);
  }
}

function file(name: string, type: string, size = 2000): File {
  const f = new File([new Uint8Array(Math.min(size, 4000))], name, { type });
  Object.defineProperty(f, "size", { value: size });
  return f;
}

function choose(f: File, which: "gallery-input" | "camera-input" = "gallery-input") {
  fireEvent.change(screen.getByTestId(which), { target: { files: [f] } });
}

beforeEach(() => {
  photos = new FakePhotos();
  mockApi({}, photos);
  coarse = false;
  xhrStatus = 204;
  sentTo.length = 0;
  sentKeys.length = 0;
  vi.stubGlobal("XMLHttpRequest", FakeXHR);
  vi.stubGlobal("matchMedia", (q: string) => ({
    matches: coarse && q.includes("coarse"),
    addEventListener() {},
    removeEventListener() {},
  }));
  URL.createObjectURL = vi.fn(() => "blob:preview");
  URL.revokeObjectURL = vi.fn();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("desktop: one 'Choose a photo'; phones: camera and gallery", () => {
  render(<PhotoStep sessionId="s1" />);
  expect(screen.getByRole("button", { name: "Choose a photo" })).toBeDefined();
  expect(screen.queryByRole("button", { name: "Take a photo" })).toBeNull();
  cleanup();
  coarse = true;
  render(<PhotoStep sessionId="s1" />);
  expect(screen.getByRole("button", { name: "Take a photo" })).toBeDefined();
  expect(screen.getByRole("button", { name: "Choose from gallery" })).toBeDefined();
  expect(screen.getByTestId("camera-input").getAttribute("capture")).toBe("environment");
  expect(screen.getByTestId("gallery-input").getAttribute("capture")).toBeNull();
});

test("wrong types and oversize files are refused before anything is sent", () => {
  expect(checkPhoto(file("notes.pdf", "application/pdf"))).toMatch(/JPEG, PNG, WebP or HEIC/);
  expect(checkPhoto(file("big.jpg", "image/jpeg", 11 * 1024 * 1024))).toMatch(/under 10 MB/);
  expect(checkPhoto(file("IMG_0001.HEIC", ""))).toBeNull(); // phones often send HEIC untyped
  render(<PhotoStep sessionId="s1" />);
  choose(file("car.gif", "image/gif"));
  expect(screen.getByRole("alert").textContent).toMatch(/not a photo we can use/);
  choose(file("big.jpg", "image/jpeg", 11 * 1024 * 1024));
  expect(screen.getByRole("alert").textContent).toMatch(/too big/);
  expect(sentTo).toEqual([]);
});

test("preview, retake, upload with progress, then the photo shows from a signed link", async () => {
  coarse = true;
  render(<PhotoStep sessionId="s1" />);
  choose(file("first.jpg", "image/jpeg"), "camera-input");
  expect(screen.getByRole("img", { name: "Preview of your photo" }).getAttribute("src")).toBe("blob:preview");
  expect(screen.getByRole("button", { name: "Retake" })).toBeDefined();
  choose(file("second.jpg", "image/jpeg"), "camera-input"); // retake
  fireEvent.click(screen.getByRole("button", { name: "Use this photo" }));
  const bar = await screen.findByRole("progressbar", { name: "Photo upload" });
  await waitFor(() => expect(bar.getAttribute("aria-valuenow")).toBe("50"));
  await waitFor(() => expect(screen.getByTestId("photo-status").textContent).toMatch(/Photo added/));
  expect(sentTo).toEqual([STORAGE_URL]);
  expect(sentKeys[0].at(-1)).toBe("file"); // the signed policy fields first, the file last
  const shown = within(screen.getByTestId("photos")).getByRole("img", { name: "Your photo 1" });
  expect(shown.getAttribute("src")).toMatch(/^https:\/\/storage\.test\/photos\/.+\?sig=x$/);
});

test("a rejected photo shows the API's reason and can be retried", async () => {
  photos.reject = "We couldn't read this photo. Please take or choose another one.";
  render(<PhotoStep sessionId="s1" />);
  choose(file("odd.png", "image/png"));
  fireEvent.click(screen.getByRole("button", { name: "Use this photo" }));
  expect((await screen.findByRole("alert")).textContent).toBe(
    "We couldn't read this photo. Please take or choose another one.",
  );
  expect(screen.getByRole("button", { name: "Choose another photo" })).toBeDefined();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  await waitFor(() => expect(screen.getByTestId("photo-status").textContent).toMatch(/Photo added/));
});

test("a failed upload or storage being down explains, and you can carry on without a photo", async () => {
  xhrStatus = 0;
  render(<PhotoStep sessionId="s1" />);
  choose(file("car.jpg", "image/jpeg"));
  fireEvent.click(screen.getByRole("button", { name: "Use this photo" }));
  expect((await screen.findByRole("alert")).textContent).toMatch(/didn't upload/);
  xhrStatus = 204;
  photos.storageDown = true;
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  await waitFor(() => expect(screen.getByRole("alert").textContent).toMatch(/carry on without a photo/));
  fireEvent.click(screen.getByRole("button", { name: "Never mind" }));
  expect(screen.queryByRole("alert")).toBeNull();
});

test("HEIC photos have no preview but upload; photos can be removed", async () => {
  render(<PhotoStep sessionId="s1" />);
  choose(file("IMG_0001.HEIC", ""));
  expect(screen.getByText(/preview not available on this device/)).toBeDefined();
  fireEvent.click(screen.getByRole("button", { name: "Use this photo" }));
  await waitFor(() => expect(screen.getByTestId("photos")).toBeDefined());
  fireEvent.click(screen.getByRole("button", { name: "Remove photo 1" }));
  await waitFor(() => expect(screen.queryByTestId("photos")).toBeNull());
  expect(photos.photos).toEqual([]);
});

test("the photo step can be skipped and reopened", async () => {
  render(<PhotoStep sessionId="s1" />);
  await act(async () => undefined);
  fireEvent.click(screen.getByRole("button", { name: "Skip" }));
  expect(screen.queryByTestId("photo-step")).toBeNull();
  expect(screen.getByText("No photo added.")).toBeDefined();
  fireEvent.click(screen.getByRole("button", { name: "Add a photo" }));
  expect(screen.getByTestId("photo-step")).toBeDefined();
});
