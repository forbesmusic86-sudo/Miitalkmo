export async function onRequest(context) {
  const url = new URL(context.request.url);
  let key = url.pathname;

  // Normalize asset path
  if (key.startsWith('/assets/')) {
    key = key.slice(8); // Remove "/assets/"
  } else if (key.startsWith('/assets')) {
    key = key.slice(7); // Remove "/assets"
  } else if (key.startsWith('/')) {
    key = key.slice(1); // remove leading slash
  }

  // Look up the asset in Cloudflare KV
  const obj = await context.env.TM_ASSETS.get(key);

  if (obj === null) {
    return new Response("Not found", { status: 404 });
  }

  // Determine content type
  let contentType = "application/octet-stream";

  if (key.endsWith('.js')) {
    contentType = "application/javascript";
  } else if (key.endsWith('.mjs')) {
    contentType = "application/javascript";
  } else if (key.endsWith('.json')) {
    contentType = "application/json";
  } else if (key.endsWith('.css')) {
    contentType = "text/css";
  } else if (key.endsWith('.data')) {
    contentType = "application/octet-stream";
  } else if (key.endsWith('.wasm')) {
    contentType = "application/wasm";
  } else if (key.endsWith('.png')) {
    contentType = "image/png";
  } else if (key.endsWith('.jpg') || key.endsWith('.jpeg')) {
    contentType = "image/jpeg";
  } else if (key.endsWith('.gif')) {
    contentType = "image/gif";
  } else if (key.endsWith('.svg')) {
    contentType = "image/svg+xml";
  } else if (key.endsWith('.html')) {
    contentType = "text/html";
  } else if (key.endsWith('.txt')) {
    contentType = "text/plain";
  } else if (key.endsWith('.wasm')) {
    contentType = "application/wasm";
  }

  // Some browser features (Emscripten/wasm) need these headers
  return new Response(obj.body, {
    headers: {
      "Content-Type": contentType,
      "Cross-Origin-Opener-Policy": "same-origin",
      "Cross-Origin-Embedder-Policy": "require-corp",
      "Access-Control-Allow-Origin": "*",
      "Cache-Control": "public, max-age=86400, immutable",
    }
  });
}
