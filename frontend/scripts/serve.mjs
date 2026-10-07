import http from "node:http";
import https from "node:https";
import fs from "node:fs/promises";
import path from "node:path";
const root = path.resolve("dist");
const port = Number(process.env.PORT || 4173);
const backend = process.env.API_TARGET;
const types = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".woff2": "font/woff2",
  ".json": "application/json",
  ".jpg": "image/jpeg",
  ".webp": "image/webp",
};
const server = http
  .createServer(async (req, res) => {
    if (req.url.startsWith("/api/") && backend) {
      const target = new URL(req.url.slice(4), backend);
      const headers = { ...req.headers, host: target.host };
      const transport = target.protocol === "https:" ? https : http;
      const upstreamRequest = transport.request(
        target,
        {
          method: req.method,
          headers,
        },
        (upstream) => {
          // Preserve each Set-Cookie header and the encoded response bytes together.
          res.writeHead(upstream.statusCode, upstream.headers);
          upstream.on("error", () => res.destroy());
          upstream.pipe(res);
        },
      );
      upstreamRequest.on("error", () => {
        if (res.headersSent) res.destroy();
        else res.writeHead(502).end();
      });
      req.on("aborted", () => upstreamRequest.destroy());
      res.on("close", () => upstreamRequest.destroy());
      req.pipe(upstreamRequest);
      return;
    }
    const requested = new URL(req.url, "http://localhost").pathname;
    const file = path.resolve(
      root,
      `.${requested === "/" ? "/index.html" : requested}`,
    );
    if (!file.startsWith(root + path.sep)) {
      res.writeHead(403);
      res.end();
      return;
    }
    try {
      const body = await fs.readFile(file);
      res.writeHead(200, {
        "Content-Type": types[path.extname(file)] || "application/octet-stream",
        "Cache-Control": "no-store",
      });
      res.end(body);
    } catch {
      res.writeHead(404);
      res.end("Not found");
    }
  })
  .listen(port, "127.0.0.1", () =>
    console.log(`Frontend test server http://127.0.0.1:${server.address().port}`),
  );
