import http from "node:http";
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
http
  .createServer(async (req, res) => {
    if (req.url.startsWith("/api/") && backend) {
      const target = new URL(req.url.slice(4), backend);
      const chunks = [];
      for await (const chunk of req) chunks.push(chunk);
      const headers = { ...req.headers, host: target.host };
      try {
        const upstream = await fetch(target, {
          method: req.method,
          headers,
          body: ["GET", "HEAD"].includes(req.method)
            ? undefined
            : Buffer.concat(chunks),
          redirect: "manual",
        });
        res.writeHead(upstream.status, Object.fromEntries(upstream.headers));
        res.end(Buffer.from(await upstream.arrayBuffer()));
      } catch {
        res.writeHead(502);
        res.end();
      }
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
    console.log(`Frontend test server http://127.0.0.1:${port}`),
  );
