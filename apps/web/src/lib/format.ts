// Formatting for prices and dates (en-IN).

const RUPEES = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });

/** Indian digit grouping: 123456 → "₹1,23,456". Show with `tabular-nums` so columns of prices line up. */
export function rupees(amount: number): string {
  return RUPEES.format(amount);
}

/** "₹2,700" or "₹9,800 – ₹12,750". */
export function rupeeRange(low: number, high?: number | null): string {
  return high === undefined || high === null || high === low ? rupees(low) : `${rupees(low)} – ${rupees(high)}`;
}

/** "2026-10-12" → "12 Oct 2026". */
export function shortDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

const PLACEHOLDER = /^\s*(not stated|depends|n\/?a|none|nil|-+|–)\.?\s*$/i;

/** The text, or "" when the source cell only holds a placeholder such as "Not stated" or "Depends.". */
export function informative(text: string | null | undefined): string {
  return text && !PLACEHOLDER.test(text) ? text.trim() : "";
}

/** Towing advice: "No." in the source means towing is not usually needed. */
export function towingText(text: string | null | undefined): string {
  if (text && /^\s*no\.?\s*$/i.test(text)) return "Usually not needed.";
  return informative(text);
}

/** Road-repairable text without the Yes / No / Limited answer word the source column starts with. */
export function roadsideText(text: string | null | undefined): string {
  return informative((text ?? "").replace(/^\s*(yes|no|limited)\b[\s.,:;-]*/i, ""));
}

/** True when `a` already says `b` (same text, or one contains the other). */
export function repeats(a: string, b: string): boolean {
  const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  const x = norm(a);
  const y = norm(b);
  return !!x && !!y && (x === y || x.includes(y) || y.includes(x));
}
