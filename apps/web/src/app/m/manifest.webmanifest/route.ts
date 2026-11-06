// The mechanic app's own manifest: installs as "IM Mechanic", opens on /m, stays inside /m. Hindi first.
export function GET() {
  const manifest = {
    id: "/m",
    name: "Instant Mechanic: Mechanic",
    short_name: "IM Mechanic",
    description: "Job offers, today's jobs and job updates for Instant Mechanic mechanics.",
    start_url: "/m",
    scope: "/m",
    display: "standalone",
    orientation: "portrait",
    background_color: "#15120F",
    theme_color: "#15120F",
    lang: "hi-IN",
    icons: [
      { src: "/icons/mechanic-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/mechanic-512.png", sizes: "512x512", type: "image/png" },
      { src: "/icons/mechanic-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
  return new Response(JSON.stringify(manifest), {
    headers: { "Content-Type": "application/manifest+json", "Cache-Control": "public, max-age=3600" },
  });
}
