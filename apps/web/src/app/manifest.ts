import type { MetadataRoute } from "next";

// The customer site as an installable app: needed for browser alerts on iPhone / iPad (iOS 16.4+ only shows web push
// for sites added to the Home Screen). The mechanic app (/m) has its own manifest (src/app/m/manifest.webmanifest).
export default function manifest(): MetadataRoute.Manifest {
  return {
    id: "/",
    name: "Instant Mechanic",
    short_name: "Instant Mechanic",
    description: "Car problem? Likely causes, safety advice and costs, and a mechanic when you need one. Delhi NCR.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    background_color: "#FFF6EE",
    theme_color: "#D9620F",
    lang: "en-IN",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/icons/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
