// This endpoint is called only when a visitor explicitly requests the IP check.
// It does not write a database record or make any third-party request.
export function GET(request: Request) {
  const ip = request.headers.get("cf-connecting-ip");
  const country = request.headers.get("cf-ipcountry");
  return Response.json(
    { ip: ip || null, country: country || null },
    {
      headers: {
        "Cache-Control": "no-store, max-age=0",
        "X-Content-Type-Options": "nosniff",
      },
    },
  );
}
