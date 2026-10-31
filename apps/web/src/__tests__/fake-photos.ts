// A fake photos API on top of the fake diagnosis (unit tests and Playwright). Upload forms point at
// https://storage.test/upload; `reject` makes the next /complete answer 422 with the API's message. /analyze answers
// `analysis(mode)`: by default "unavailable" (no vision provider, as in development); "error" answers 500.

import type { Finding, Photo, PhotoMode, SafetyAlert } from "@/lib/api";
import { FakeDiagnosis, type FakeResponse } from "./fake-diagnosis";

export const STORAGE_URL = "https://storage.test/upload";
export const PICTURE_URL = "https://storage.test/photos/";

export const OIL_ALERT: SafetyAlert = {
  rule_id: 7007,
  risk: "high",
  reason: "Possible in your photo: engine oil pressure light",
  source: "photo",
  roadside_action: "Stop now and switch off the engine. Do not drive while the light is on.",
  stop_driving_trigger: "Stop now: red oil light.",
  towing: "Yes, if the light stays on.",
  fault_key: "F10-DW-23",
};

export function finding(uploadId: string, mode: PhotoMode, over: Partial<Finding> = {}): Finding {
  return {
    upload_id: uploadId,
    mode,
    status: "unavailable",
    message: "A mechanic will look at your photo.",
    labels: [],
    safety: [],
    ...over,
  };
}

export const RED_OIL_LIGHT = (uploadId: string, mode: PhotoMode): Finding =>
  finding(uploadId, mode, {
    status: "found",
    message: "Photos can be misleading. A mechanic will check this before any repair.",
    labels: [
      {
        code: "oil_pressure",
        name: "Engine oil pressure light",
        meaning: "Red oil light means oil pressure is too low.",
        severity: "red",
        confidence: 0.9,
        reviewed: false,
      },
    ],
    safety: [OIL_ALERT],
  });

export class FakePhotos extends FakeDiagnosis {
  photos: Photo[] = [];
  analysis: (uploadId: string, mode: PhotoMode) => Finding | "error" = (id, mode) => finding(id, mode);
  analyzed: PhotoMode[] = [];
  reject: string | null = null;
  storageDown = false;
  private n = 0;

  handle(method: string, path: string, body?: unknown): FakeResponse | null {
    const b = (body ?? {}) as Record<string, unknown>;
    if (path === "/api/uploads" && method === "POST") {
      if (!String(b.content_type).startsWith("image/")) {
        return { status: 422, json: { detail: "This file is not a photo we can use." } };
      }
      if (this.photos.length >= 5) {
        return { status: 409, json: { detail: "You can add up to 5 photos to one diagnosis." } };
      }
      const id = `00000000-0000-4000-8000-${String(++this.n).padStart(12, "0")}`;
      return {
        status: 201,
        json: {
          upload_id: id,
          url: STORAGE_URL,
          fields: { key: `incoming/${id}`, policy: "p" },
          max_bytes: 10485760,
          expires_in: 600,
        },
      };
    }
    const complete = path.match(/^\/api\/uploads\/([^/]+)\/complete$/);
    if (complete && method === "POST") {
      if (this.storageDown) {
        return {
          status: 503,
          json: { detail: "We couldn't reach our photo storage. Please try again, or carry on without a photo." },
        };
      }
      if (this.reject) {
        const detail = this.reject;
        this.reject = null;
        return { status: 422, json: { detail } };
      }
      const photo: Photo = {
        id: complete[1],
        status: "ready",
        width: 2000,
        height: 1500,
        url: `${PICTURE_URL}${complete[1]}.jpg?sig=x`,
        expires_in: 300,
      };
      this.photos.push(photo);
      return { status: 200, json: photo };
    }
    const analyze = path.match(/^\/api\/uploads\/([^/]+)\/analyze$/);
    if (analyze && method === "POST") {
      const mode = b.mode as PhotoMode;
      this.analyzed.push(mode);
      const out = this.analysis(analyze[1], mode);
      if (out === "error") return { status: 500, json: { detail: "error" } };
      const photo = this.photos.find((p) => p.id === analyze[1]);
      if (photo) photo.findings = [out];
      return { status: 200, json: out };
    }
    if (path === "/api/uploads" && method === "GET") return { status: 200, json: this.photos };
    const one = path.match(/^\/api\/uploads\/([^/]+)$/);
    if (one && method === "DELETE") {
      this.photos = this.photos.filter((p) => p.id !== one[1]);
      return { status: 200, json: {} };
    }
    return super.handle(method, path, body);
  }
}
