// The app's own health check (Docker and the uptime monitor): the Next.js server answers. It does not call the API,
// so an API outage shows up on the API's own checks (/api/health/ready), not as this app being down.
export function GET() {
  return Response.json({ status: "ok" }, { headers: { "Cache-Control": "no-store" } });
}
