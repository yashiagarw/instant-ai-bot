import { describe, expect, it } from "vitest";

import type { DatasetJob, DatasetVersion } from "@/lib/api";
import { isActive, missed, pct, points, versionState, versionTitle, waitingSeconds } from "@/lib/datasets";

const base: DatasetVersion = {
  id: 7, status: "validated", origin: "upload", category_code: "battery", source_file_no: 8, upload_name: "b.xlsx",
  created_by: "x", created_at: "2026-11-01T10:00:00Z", published_at: null, published_by: null, archived_at: null,
  base_version_id: 6, rollback_of_id: null, override_reason: null, categories: ["battery"], stale: false, validated: true,
  build_error: null, losses: 0, diff_counts: { added: 0, changed: 0, removed: 0 }, gate: null, gate_reasons: [],
}; // prettier-ignore

describe("datasets display helpers", () => {
  it("names the state of a version, worst first", () => {
    expect(versionState({ ...base, status: "published" }).label).toBe("Live");
    expect(versionState({ ...base, build_error: "boom" }).label).toBe("Build failed");
    expect(versionState({ ...base, validated: null }).label).toBe("Building");
    expect(versionState({ ...base, stale: true }).label).toBe("Out of date");
    expect(versionState({ ...base, status: "draft", validated: false }).label).toBe("Needs fixes");
    expect(versionState(base).label).toBe("Validated");
  });

  it("titles versions by what they change", () => {
    expect(versionTitle(base)).toBe("v7 · battery");
    expect(versionTitle({ ...base, origin: "rollback", rollback_of_id: 3 })).toBe("v7 · battery rolled back to v3");
    expect(versionTitle({ ...base, origin: "import", categories: [] })).toBe("v7 · import of every file");
  });

  it("formats rates and changes in points", () => {
    expect(pct(0.98864)).toBe("98.86%");
    expect(pct(null)).toBe("–");
    expect(points(0.75, 0.8)).toBe("-5.00");
    expect(points(0.8155, 0.8)).toBe("+1.55");
    expect(points(0.8, 0.8)).toBe("0.00");
    expect(missed({ safety_n: 176, safety_missed: 2, safety_recall: 0.98864 })).toBe("2 of 176 danger cases missed (98.86%)");
    expect(points(null, 0.8)).toBe("–");
  });

  it("knows active jobs and how long one has waited", () => {
    const job = { status: "queued", created_at: "2026-11-01T10:00:00Z" } as DatasetJob;
    expect(isActive(job)).toBe(true);
    expect(isActive({ ...job, status: "failed" })).toBe(false);
    expect(waitingSeconds(job, Date.parse("2026-11-01T10:00:12Z"))).toBe(12);
    expect(waitingSeconds({ ...job, status: "running" })).toBe(0);
  });
});
