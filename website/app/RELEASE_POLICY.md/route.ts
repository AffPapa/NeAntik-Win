import releasePolicy from "../../RELEASE_POLICY.md?raw";

const headers = {
  "Content-Type": "text/markdown; charset=utf-8",
  "Cache-Control": "public, max-age=0, must-revalidate",
  "X-Content-Type-Options": "nosniff",
};

export function GET() {
  return new Response(releasePolicy, { headers });
}

export function HEAD() {
  return new Response(null, { headers });
}
