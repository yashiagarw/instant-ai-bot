const DATE_TIME = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "Asia/Kolkata",
});
const DATE = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: "Asia/Kolkata" });

/** India time, e.g. "1 Nov 2026, 09:30 am". */
export const dateTime = (iso: string | null) => (iso ? DATE_TIME.format(new Date(iso)) : "Never");
export const date = (iso: string | null) => (iso ? DATE.format(new Date(iso)) : "");

/** A staff account's state, worst first. */
export function staffStatus(s: { active: boolean; locked: boolean; two_factor: boolean; must_change_password: boolean }) {
  if (!s.active) return "Disabled";
  if (s.locked) return "Locked";
  if (!s.two_factor) return "Two-factor not set up";
  if (s.must_change_password) return "Temporary password";
  return "Active";
}
