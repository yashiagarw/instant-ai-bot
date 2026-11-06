import { JobView } from "@/components/m/job-view";

// Signed-in only: the shell (components/m/shell.tsx) shows this page after it has checked the sign-in in the browser,
// so it cannot be part of an instant navigation. Opted out of Next's dev-only instant-navigation validation.
export const instant = false;

export default function Page() {
  return <JobView />;
}
