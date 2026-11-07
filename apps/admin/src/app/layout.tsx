import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { isDemo } from "@im/ui/api-proxy";
import { DemoBanner } from "@im/ui/demo-banner";
import { ErrorReporting } from "@/components/error-reporting";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: { default: "Instant Mechanic admin", template: "%s · Instant Mechanic admin" },
  description: "Staff area of Instant Mechanic.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col bg-warm-white">
        <DemoBanner demo={isDemo(process.env)} />
        <ErrorReporting />
        {children}
      </body>
    </html>
  );
}
