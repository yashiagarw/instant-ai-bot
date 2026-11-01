// The /api/admin/vehicles catalogue, /api/admin/parts and /api/admin/media part of the fake API (see fake-admin.ts).
// Mirrors the rules the pages rely on: a price needs a source and a date, 20,000 rupees or more needs a second look
// by someone other than who entered it.

type Json = Record<string, unknown>;
type Result = { status: number; json?: unknown; text?: string };

const TODAY = new Date().toISOString().slice(0, 10);

export class FakeParts {
  makes = [
    { id: 1, name: "Maruti Suzuki", aliases: "maruti", edited_by: null as string | null,
      models: [{ id: 10, make_id: 1, name: "Swift", body_type: "hatchback", aliases: "", edited_by: null as string | null,
        generations: [] as Json[],
        variants: [{ id: 100, model_id: 10, generation_id: null, name: "2018-2023 Petrol MT", fuel: "petrol", transmission: "mt", engine: "",
          year_from: 2018, year_to: 2023, price_segment: "budget", features: {}, edited_by: null as string | null }] as Json[] }] },
  ]; // prettier-ignore
  vehicleSaves: { method: string; path: string; body: Json }[] = [];
  parts: Json[] = [
    { key: "PN:bosch:PAD1:1", description: "Front brake pads", part_type: "Brake pad set", brand: "Bosch", brand_kind: "aftermarket",
      part_number: "PAD1", quantity: 1, kind: "part", segment: null, generic: false },
  ]; // prettier-ignore
  prices: Json[] = [
    { key: "PN:bosch:PAD1:1|budget|F11-B_PAD", part_key: "PN:bosch:PAD1:1", part: "Front brake pads", segment: "budget", source: "price_sheet",
      source_ref: "F11-B_PAD", price_inr: 1450, price_max_inr: null, supplier: "Boodmo", source_url: "", checked_on: "2026-10-22",
      verification_status: "checked", gst_included: null, fitting_included: null, model_verified: false, price_basis: "", note: "",
      second_look_by: null, second_look_at: null, edit: null, flagged: false, missing_source: false, entered_by: null },
  ]; // prettier-ignore
  zones: Json[] = ["delhi", "gurugram"].flatMap((z) =>
    ["budget", "mid", "premium"].map((s) => ({ key: `${z}|${s}`, zone: z, zone_label: z[0].toUpperCase() + z.slice(1), segment: s,
      rate_min_inr: null, rate_max_inr: null, source: "", checked_on: null, edit: null })),
  ); // prettier-ignore
  saves: Json[] = [];
  uploads: string[] = [];
  bulk: Json[] = [];
  imports: boolean[] = [];

  private flag(p: Json): Json {
    const big = Math.max(Number(p.price_inr), Number(p.price_max_inr ?? 0)) >= 20000;
    return { ...p, flagged: big && !p.second_look_by, missing_source: !(p.supplier || p.source_url) || !p.checked_on };
  }

  handle(method: string, path: string, body: Json, perms: Set<string>, me: string, raw: string | null, url?: URL): Result | null {
    const denied = { status: 403, json: { detail: "You don't have access to this" } };
    if (path.startsWith("/vehicles/") && path !== "/vehicles/unlisted" && path !== "/vehicles/makes" && !path.startsWith("/vehicles/unlisted/")) {
      if (!perms.has("content.read")) return denied;
      if (path === "/vehicles/catalogue") return { status: 200, json: { makes: this.makes, features: { start_stop: "automatic engine start-stop" } } };
      if (!perms.has("vehicles.manage")) return denied;
      this.vehicleSaves.push({ method, path, body });
      const m = path.match(/^\/vehicles\/(makes|models|generations|variants)(?:\/(\d+))?$/)!;
      const model = this.makes[0].models[0];
      if (m[1] === "generations" && method === "POST") {
        const g = { id: 50 + model.generations.length, model_id: model.id, edited_by: me, ...body };
        model.generations.push(g);
        return { status: 201, json: g };
      }
      if (m[1] === "variants" && method === "PUT") {
        const v = model.variants.find((x) => x.id === Number(m[2]))!;
        Object.assign(v, body, { edited_by: me });
        return { status: 200, json: v };
      }
      if (m[1] === "variants" && method === "DELETE") return { status: 409, json: { detail: "3 diagnoses or saved cars use this variant: change it instead (e.g. its years) of deleting it." } };
      return { status: 200, json: body };
    }
    if (path === "/media/pictures") {
      if (!perms.has("knowledge.edit")) return denied;
      const sha = "a".repeat(39) + String(this.uploads.length);
      this.uploads.push(sha);
      return { status: 201, json: { sha1: sha, url: `/media/uploaded/${sha}.jpg`, caption: "uploaded" } };
    }
    if (path.match(/^\/knowledge\/versions\/50\/signoff\/bulk$/)) {
      if (!perms.has("knowledge.edit")) return denied;
      this.bulk.push(body);
      return { status: 200, json: { signed_off: (body.items as unknown[]).length, skipped: [] } };
    }
    if (!path.startsWith("/parts/")) return null;
    if (!perms.has("content.read")) return denied;
    const v = "/parts/versions/50";
    if (path === `${v}/parts`) {
      return { status: 200, json: this.parts.map((p) => {
        const mine = this.prices.filter((x) => x.part_key === p.key).map((x) => this.flag(x));
        return { key: p.key, description: p.description, part_type: p.part_type, brand: p.brand, part_number: p.part_number, kind: p.kind,
          prices: mine.length, price_min: mine.length ? Math.min(...mine.map((x) => Number(x.price_inr))) : null,
          price_max: mine.length ? Math.max(...mine.map((x) => Number(x.price_max_inr ?? x.price_inr))) : null,
          second_look: mine.filter((x) => x.flagged).length, fits: 0, edited: this.saves.some((s) => String(s.key).startsWith(String(p.key))) };
      }) }; // prettier-ignore
    }
    const part = path.match(/^\/parts\/versions\/50\/parts\/(.+)$/);
    if (part) {
      const key = decodeURIComponent(part[1]);
      const p = this.parts.find((x) => x.key === key);
      if (!p) return { status: 404, json: { detail: "Part not found" } };
      const { key: _k, ...data } = p;
      void _k;
      return { status: 200, json: { key, part: data, part_edit: null, prices: this.prices.filter((x) => x.part_key === key).map((x) => this.flag(x)),
        fits: [], images: [], images_edit: null } }; // prettier-ignore
    }
    if (path === `${v}/prices`) return { status: 200, json: this.prices.map((x) => this.flag(x)) };
    if (path === `${v}/labour`) return { status: 200, json: { zones: this.zones, research: [] } };
    if (path === `${v}/prices/second-look`) {
      const p = this.prices.find((x) => x.key === body.key)!;
      if (p.entered_by === me) return { status: 422, json: { detail: "A second person must check this price: you entered it." } };
      Object.assign(p, { second_look_by: me, second_look_at: TODAY });
      return { status: 200, json: p };
    }
    if (path === `${v}/import`) {
      this.imports.push(url?.searchParams.get("commit") === "true");
      const lines = (raw ?? "").trim().split("\n").slice(1);
      return { status: 200, json: { summary: { rows: lines.length, valid: 1, errors: lines.length - 1, flagged: 0 },
        rows: lines.map((l, i) => ({ line: i + 2, row: { description: l.split(",")[1], segment: l.split(",")[5], price_inr: l.split(",")[6] },
          errors: i === 0 ? [] : ["checked_on: Field required"], part_key: null, flagged: false })) } }; // prettier-ignore
    }
    return { status: 404, json: { detail: "Not Found" } };
  }

  /** A price / zone edit saved through /knowledge/versions/50/edits (called by FakeKnowledge). */
  save(entity: string, key: string, data: Json | null, me: string): Result | null {
    if (entity === "part_price") {
      this.saves.push({ entity, key, data });
      if (data && !(data.supplier || data.source_url)) return { status: 422, json: { detail: "item: a price needs its source: the supplier or a link" } };
      const [partKey, segment, tag] = key.split("|");
      const finalKey = tag ? key : `${partKey}|${segment}|editor-${this.prices.length + 1}`;
      const existing = this.prices.find((x) => x.key === finalKey);
      const row = { ...(existing ?? { key: finalKey, part_key: partKey, part: this.parts.find((p) => p.key === partKey)?.description, segment,
        source: "team_csv", source_ref: tag || "editor" }), ...data, entered_by: me, second_look_by: null, edit: 1 }; // prettier-ignore
      if (existing) Object.assign(existing, row);
      else this.prices.push(row);
      const flagged = this.flag(row).flagged;
      return { status: 200, json: { key: finalKey, item: row, edit: { id: 1, safety: false },
        warning: flagged ? "This price is 20,000 rupees or more: it is flagged until a second person checks it (Parts & Prices, Prices, 'Second look')." : null } }; // prettier-ignore
    }
    if (entity === "zone_rate" || entity === "part" || entity === "part_images" || entity === "fault_images") {
      this.saves.push({ entity, key, data });
      if (entity === "zone_rate") Object.assign(this.zones.find((z) => z.key === key)!, data, { edit: 1 });
      return { status: 200, json: { key: key || "ADM:new", item: data, edit: { id: 1, safety: false }, warning: null } };
    }
    return null;
  }
}
