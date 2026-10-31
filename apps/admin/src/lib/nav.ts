// The sidebar. An item shows when the staff member has ANY of its permissions (docs/permissions.md, "Admin app
// menu"); its page also refuses without them. Hiding is for convenience only: the API checks every call.

import type { LucideIcon } from "lucide-react";
import {
  BadgeCheck,
  BookOpen,
  Car,
  ClipboardList,
  Database,
  LayoutDashboard,
  ScrollText,
  Tags,
  Users,
  Wrench,
} from "lucide-react";

export interface NavItem {
  key: string;
  label: string;
  href: string;
  icon: LucideIcon;
  anyOf: string[];
  /** Not built yet: the page says so. */
  placeholder?: string;
}

export const NAV: NavItem[] = [
  { key: "overview", label: "Overview", href: "/", icon: LayoutDashboard, anyOf: ["self"] },
  { key: "requests", label: "Requests", href: "/requests", icon: ClipboardList, anyOf: ["requests.read"],
    placeholder: "Mechanic requests from customers: status, contact and assignment." },
  { key: "mechanics", label: "Mechanics", href: "/mechanics", icon: Wrench, anyOf: ["requests.read", "staff.read"],
    placeholder: "Mechanics, their areas and their assigned jobs." },
  { key: "knowledge", label: "Knowledge", href: "/knowledge", icon: BookOpen, anyOf: ["content.read"],
    placeholder: "Faults, questions, safety rules and photo labels, with review." },
  { key: "vehicles", label: "Vehicles", href: "/vehicles", icon: Car, anyOf: ["content.read"],
    placeholder: "The car catalogue: makes, models, variants and price segments." },
  { key: "parts", label: "Parts & Prices", href: "/parts", icon: Tags, anyOf: ["content.read"],
    placeholder: "Parts, prices, labour rates and their check dates." },
  { key: "datasets", label: "Datasets", href: "/datasets", icon: Database, anyOf: ["content.read"],
    placeholder: "Imported dataset versions and import reports." },
  { key: "quality", label: "Quality", href: "/quality", icon: BadgeCheck, anyOf: ["content.read"],
    placeholder: "Evaluation reports, customer feedback and items waiting for review." },
  { key: "users", label: "Users", href: "/users", icon: Users, anyOf: ["staff.read", "customers.read"] },
  { key: "audit", label: "Audit log", href: "/audit", icon: ScrollText, anyOf: ["audit.read"] },
]; // prettier-ignore

export function can(permissions: string[], anyOf: string[]): boolean {
  return anyOf.some((p) => permissions.includes(p));
}

export function visibleNav(permissions: string[]): NavItem[] {
  return NAV.filter((item) => can(permissions, item.anyOf));
}

export function navItem(key: string): NavItem {
  const item = NAV.find((i) => i.key === key);
  if (!item) throw new Error(`no nav item ${key}`);
  return item;
}
