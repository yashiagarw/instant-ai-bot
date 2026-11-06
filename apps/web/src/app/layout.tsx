import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { ErrorReporting } from "@/components/error-reporting";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Instant Mechanic: AI car diagnosis",
  description:
    "Tell us what's wrong with your car and get likely causes, safety advice and repair cost estimates. Delhi NCR.",
  // The manifest (src/app/manifest.ts) is linked automatically; iPhones also want these for "Add to Home Screen".
  icons: { apple: "/icons/apple-touch-icon.png" },
  appleWebApp: { capable: true, title: "Instant Mechanic", statusBarStyle: "default" },
};

export const viewport: Viewport = { themeColor: "#D9620F" };

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <ErrorReporting />
        {children}
      </body>
    </html>
  );
}
