import type { Metadata, Viewport } from "next";

// The mechanic app (/m): its own manifest and icon (installs as "IM Mechanic"), not indexed.
export const metadata: Metadata = {
  title: "IM Mechanic",
  manifest: "/m/manifest.webmanifest",
  robots: { index: false, follow: false },
  icons: { apple: "/icons/mechanic-apple-touch-icon.png" },
  appleWebApp: { capable: true, title: "IM Mechanic", statusBarStyle: "black" },
};

export const viewport: Viewport = { themeColor: "#15120F" };

export default function MechanicLayout({ children }: { children: React.ReactNode }) {
  return children;
}
