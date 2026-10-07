import { after, before, describe, test } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { fileURLToPath } from "node:url";
import { gzipSync, gunzipSync } from "node:zlib";

const expires = "Wed, 21 Oct 2037 07:28:00 GMT";
const loginCookies = [
  `access_token=access; Path=/; HttpOnly; SameSite=Lax; Expires=${expires}`,
  `refresh_token=refresh; Path=/; HttpOnly; SameSite=Lax; Expires=${expires}`,
  "csrf_token=csrf; Path=/; SameSite=Lax",
];
const logoutCookies = ["access_token", "refresh_token", "csrf_token"].map(
  (name) => `${name}=; Path=/; Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:00 GMT`,
);

function request(url, { method = "GET", headers = {}, body } = {}) {
  return new Promise((resolve, reject) => {
    const req = http.request(url, { method, headers }, (res) => {
      const chunks = [];
      res.on("data", (chunk) => chunks.push(chunk));
      res.on("error", reject);
      res.on("end", () => resolve({
        status: res.statusCode, headers: res.headers, body: Buffer.concat(chunks),
      }));
    });
    req.on("error", reject);
    req.setTimeout(5000, () => req.destroy(new Error("Proxy request timed out")));
    req.end(body);
  });
}

describe("local API proxy", () => {
  let upstream, proxy, baseURL;
  const seen = [];

  before(async () => {
    upstream = http.createServer(async (req, res) => {
      const chunks = [];
      for await (const chunk of req) chunks.push(chunk);
      seen.push({ path: req.url, headers: req.headers, body: Buffer.concat(chunks).toString() });
      if (req.url === "/auth/login") {
        res.writeHead(200, { "Content-Type": "application/json", "Set-Cookie": loginCookies });
        res.end('{"id":1}');
      } else if (req.url === "/auth/me") {
        const authenticated = req.headers.cookie?.includes("access_token=access");
        res.writeHead(authenticated ? 200 : 401, { "Content-Type": "application/json" });
        res.end(JSON.stringify(authenticated ? { id: 1 } : { detail: "unauthenticated" }));
      } else if (req.url === "/auth/logout") {
        res.writeHead(200, { "Set-Cookie": logoutCookies });
        res.end("{}");
      } else if (req.url === "/compressed") {
        const compressed = gzipSync('{"message":"response from upstream"}');
        res.writeHead(200, {
          "Content-Type": "application/json", "Content-Encoding": "gzip", "Content-Length": compressed.length,
        });
        res.end(compressed);
      } else if (req.url === "/broken") {
        res.destroy();
      } else {
        res.writeHead(404);
        res.end();
      }
    });
    upstream.listen(0, "127.0.0.1");
    await once(upstream, "listening");
    proxy = spawn(process.execPath, ["scripts/serve.mjs"], {
      cwd: fileURLToPath(new URL("../", import.meta.url)),
      env: { ...process.env, PORT: "0", API_TARGET: `http://127.0.0.1:${upstream.address().port}` },
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    });
    baseURL = await new Promise((resolve, reject) => {
      let output = "", errors = "";
      const timer = setTimeout(() => reject(new Error(`Proxy did not start: ${errors}`)), 10000);
      proxy.stderr.on("data", (chunk) => { errors += chunk; });
      proxy.stdout.on("data", (chunk) => {
        output += chunk;
        const url = output.match(/http:\/\/127\.0\.0\.1:\d+/)?.[0];
        if (url) { clearTimeout(timer); resolve(url); }
      });
      proxy.once("error", (error) => { clearTimeout(timer); reject(error); });
      proxy.once("exit", (code) => {
        clearTimeout(timer);
        reject(new Error(`Proxy exited (${code}): ${errors}`));
      });
    });
  });

  after(async () => {
    if (proxy && proxy.exitCode === null) {
      const exited = once(proxy, "exit");
      proxy.kill();
      await exited;
    }
    if (upstream) {
      const closed = once(upstream, "close");
      upstream.close();
      upstream.closeAllConnections();
      await closed;
    }
  });

  test("login preserves separate session cookies and forwards authenticated requests", async () => {
    const body = JSON.stringify({ email: "student@example.test", password: "test-password" });
    const login = await request(`${baseURL}/api/auth/login`, {
      method: "POST", body, headers: { "Content-Type": "application/json", "X-CSRF-Token": "csrf" },
    });
    assert.equal(login.status, 200);
    assert.deepEqual(login.headers["set-cookie"], loginCookies);
    const sent = seen.find((entry) => entry.path === "/auth/login");
    assert.equal(sent.body, body);
    assert.equal(sent.headers["x-csrf-token"], "csrf");
    const cookie = login.headers["set-cookie"].map((value) => value.split(";")[0]).join("; ");
    const me = await request(`${baseURL}/api/auth/me`, { headers: { Cookie: cookie } });
    assert.equal(me.status, 200);
    assert.equal(JSON.parse(me.body).id, 1);
    assert.equal(seen.find((entry) => entry.path === "/auth/me").headers.cookie, cookie);
  });

  test("logout preserves every cookie deletion and unauthenticated status", async () => {
    const logout = await request(`${baseURL}/api/auth/logout`, { method: "POST" });
    assert.equal(logout.status, 200);
    assert.deepEqual(logout.headers["set-cookie"], logoutCookies);
    const me = await request(`${baseURL}/api/auth/me`);
    assert.equal(me.status, 401);
  });

  test("compressed upstream content and response headers remain consistent", async () => {
    const result = await request(`${baseURL}/api/compressed`);
    assert.equal(result.status, 200);
    const encoding = result.headers["content-encoding"];
    const decoded = encoding === "gzip" ? gunzipSync(result.body) : result.body;
    assert.deepEqual(JSON.parse(decoded), { message: "response from upstream" });
    if (result.headers["content-length"])
      assert.equal(Number(result.headers["content-length"]), result.body.length);
  });

  test("upstream connection failure returns a gateway error", async () => {
    const result = await request(`${baseURL}/api/broken`);
    assert.equal(result.status, 502);
  });
});
