import { StaffShell } from "@/components/staff-shell";

/** Every page behind the staff sign-in. */
export default function StaffLayout({ children }: LayoutProps<"/">) {
  return <StaffShell>{children}</StaffShell>;
}
