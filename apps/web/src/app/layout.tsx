import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono, Noto_Sans_Devanagari } from "next/font/google";
import "./globals.css";
import { DevServiceWorkerReset } from "@/components/dev-service-worker-reset";
import { DemoBanner } from "@im/ui/demo-banner";
import { isDemo } from "@im/ui/api-proxy";
import { ErrorReporting } from "@/components/error-reporting";
import { sharedMessages } from "@/i18n/messages";
import { IntlProvider } from "@/i18n/provider";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// Hindi text (the /hi pages, Hindi tile labels, the mechanic app). Not preloaded: its unicode-range means the browser
// downloads it only when a page shows Devanagari, so English pages do not pay for it.
const devanagari = Noto_Sans_Devanagari({
  variable: "--font-devanagari",
  subsets: ["devanagari"],
  preload: false,
  display: "swap",
});

export const metadata: Metadata = {
  title: "Instant Mechanic: AI car diagnosis",
  description:
    "Tell us what's wrong with your car and get likely causes, safety advice and repair cost estimates. Delhi NCR.",
  // The manifest (src/app/manifest.ts) is linked automatically; iPhones also want these for "Add to Home Screen".
  icons: { apple: "/icons/apple-touch-icon.png" },
  appleWebApp: { capable: true, title: "Instant Mechanic", statusBarStyle: "default" },
  // The free demo is never indexed (NEXT_PUBLIC_DEMO; next.config.ts also sends X-Robots-Tag).
  ...(isDemo(process.env) ? { robots: { index: false, follow: false } } : {}),
};

// Empty in the free demo, where the API is reached through this site (API_PROXY_TARGET): nothing to preconnect to.
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const API_ORIGIN = API_URL ? new URL(API_URL).origin : null;
const DEMO = isDemo(process.env);

export const viewport: Viewport = { themeColor: "#D9620F" };

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} ${devanagari.variable} h-full antialiased`}
    >
      <head>
        {/* Phase 5.5: every page calls the API right after it starts (categories, the result, sign-in state): open
            that connection while the page's own files load. The API sends cookies, hence use-credentials. */}
        {API_ORIGIN && <link rel="preconnect" href={API_ORIGIN} crossOrigin="use-credentials" />}
      </head>
      <body className="min-h-full flex flex-col">
        <DemoBanner demo={DEMO} />
        <ErrorReporting />
        <DevServiceWorkerReset />
        {/* Header, footer and other shared parts in English; the /hi pages wrap theirs in Hindi ([locale]/layout). */}
        <IntlProvider locale="en" messages={sharedMessages()}>
          {children}
        </IntlProvider>
      </body>
    </html>
  );
}
