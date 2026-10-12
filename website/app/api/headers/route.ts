// The browser requests this only after a click. The values are headers already
// visible to this origin; the endpoint stores nothing and makes no other calls.
export function GET(request: Request) {
  return Response.json(
    {
      userAgent: request.headers.get("user-agent") || null,
      acceptLanguage: request.headers.get("accept-language") || null,
    },
    { headers: { "Cache-Control": "no-store, max-age=0", "X-Content-Type-Options": "nosniff" } },
  );
}
