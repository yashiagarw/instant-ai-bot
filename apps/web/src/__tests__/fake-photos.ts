// A fake photos API on top of the fake diagnosis (unit tests and Playwright). Upload forms point at
// https://storage.test/upload; `reject` makes the next /complete answer 422 with the API's message.

import type { Photo } from "@/lib/api";
import { FakeDiagnosis, type FakeResponse } from "./fake-diagnosis";

export const STORAGE_URL = "https://storage.test/upload";
export const PICTURE_URL = "https://storage.test/photos/";

export class FakePhotos extends FakeDiagnosis {
  photos: Photo[] = [];
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
    if (path === "/api/uploads" && method === "GET") return { status: 200, json: this.photos };
    const one = path.match(/^\/api\/uploads\/([^/]+)$/);
    if (one && method === "DELETE") {
      this.photos = this.photos.filter((p) => p.id !== one[1]);
      return { status: 200, json: {} };
    }
    return super.handle(method, path, body);
  }
}
