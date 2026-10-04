/**
 * Cloudflare Worker — High-Speed Streaming Gateway for TelegramStreamer
 * 
 * Proxies HTTP requests (including Range: bytes=X-Y for ADM multi-threading)
 * directly to the Railway backend without buffering or memory overhead.
 */

export default {
  async fetch(request, env, ctx) {
    // 1. Resolve target Railway backend URL from environment variable or fallback
    const backendBase = (env.RAILWAY_URL || "").trim().replace(/\/+$/, "");
    if (!backendBase) {
      return new Response("Error: RAILWAY_URL environment variable is not configured on the Worker.", {
        status: 500,
        headers: { "Content-Type": "text/plain" }
      });
    }

    const clientUrl = new URL(request.url);
    const targetUrl = new URL(clientUrl.pathname + clientUrl.search, backendBase);

    // 2. Clone headers and set Host to Railway domain
    const forwardHeaders = new Headers(request.headers);
    forwardHeaders.set("Host", targetUrl.host);

    // Remove Cloudflare-specific internal headers to avoid upstream confusion
    forwardHeaders.delete("cf-connecting-ip");
    forwardHeaders.delete("cf-ipcountry");
    forwardHeaders.delete("cf-ray");
    forwardHeaders.delete("cf-visitor");

    try {
      // 3. Forward request to Railway (preserves method: GET/HEAD and Range header)
      const upstreamResponse = await fetch(targetUrl.toString(), {
        method: request.method,
        headers: forwardHeaders,
        redirect: "follow",
      });

      // 4. Prepare response headers preserving Range and Content headers
      const responseHeaders = new Headers(upstreamResponse.headers);
      responseHeaders.set("Access-Control-Allow-Origin", "*");
      responseHeaders.set("Access-Control-Allow-Headers", "*");
      responseHeaders.set("Access-Control-Expose-Headers", "Content-Range, Accept-Ranges, Content-Length, Content-Disposition");

      // 5. Stream response body directly to client (ADM)
      return new Response(upstreamResponse.body, {
        status: upstreamResponse.status,
        statusText: upstreamResponse.statusText,
        headers: responseHeaders,
      });
    } catch (err) {
      return new Response(`Gateway error connecting to backend: ${err.message}`, {
        status: 502,
        headers: { "Content-Type": "text/plain" }
      });
    }
  }
};
