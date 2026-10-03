import fs from "node:fs/promises";
import path from "node:path";
import crypto from "node:crypto";
const root = process.cwd(),
  output = path.join(root, "dist");
async function files(dir) {
  const entries = await fs.readdir(dir, { withFileTypes: true });
  const results = [];
  for (const e of entries) {
    const full = path.join(dir, e.name);
    if (e.isDirectory()) results.push(...(await files(full)));
    else results.push(full);
  }
  return results;
}
const jsFiles = (await files(path.join(root, "js"))).sort();
const fonts = ["IRANYekanXFaNum-Regular.woff2", "IRANYekanXFaNum-Bold.woff2"];
const brandDirectory = path.join(root, "assets", "original-brand");
const provenanceFile = path.join(brandDirectory, "manifest.json");
const provenance = JSON.parse(await fs.readFile(provenanceFile, "utf8"));
const sha256 = (bytes) => crypto.createHash("sha256").update(bytes).digest("hex");
for (const asset of provenance.assets) {
  const original = await fs.readFile(path.join(root, asset.source));
  const optimized = await fs.readFile(path.join(brandDirectory, asset.file));
  if (sha256(original) !== asset.sourceSha256 || sha256(optimized) !== asset.sha256 || optimized.length !== asset.bytes)
    throw new Error(`Original asset provenance mismatch: ${asset.file}. Run the documented asset preparation command.`);
  if (asset.kind === "logo" && asset.bytes > 40 * 1024)
    throw new Error(`Logo budget exceeded: ${asset.file}`);
  if (asset.kind === "avatar" && asset.bytes > 80 * 1024)
    throw new Error(`Avatar budget exceeded: ${asset.file}`);
}
const assetFiles = [
  path.join(root, "styles.css"),
  path.join(root, "landing.css"),
  path.join(root, "tailwind.css"),
  ...jsFiles,
  ...fonts.map((f) => path.join(root, "src", "fonts", f)),
  path.join(root, "src", "fonts", "FontLicense.txt"),
  ...provenance.assets.map((asset) => path.join(brandDirectory, asset.file)),
  provenanceFile,
];
const digest = crypto.createHash("sha256");
for (const file of assetFiles) {
  digest.update(path.relative(root, file).replaceAll("\\", "/") + "\0");
  digest.update(await fs.readFile(file));
  digest.update("\0");
}
const version = digest.digest("hex").slice(0, 12);
if (path.dirname(output) !== root || path.basename(output) !== "dist")
  throw new Error("Invalid build directory");
await fs.rm(output, { recursive: true, force: true });
await fs.mkdir(output, { recursive: true });
const prefix = `/assets/${version}`;
const rewriteBrandAssets = (text) => text.replaceAll("/assets/original-brand/", `${prefix}/assets/original-brand/`);
for (const source of assetFiles) {
  const rel = path.relative(root, source);
  const dest = path.join(output, "assets", version, rel);
  await fs.mkdir(path.dirname(dest), { recursive: true });
  if (source.endsWith(".css") || source.endsWith(".js"))
    await fs.writeFile(
      dest,
      rewriteBrandAssets(await fs.readFile(source, "utf8")).replaceAll(
        "/src/fonts/",
        `${prefix}/src/fonts/`,
      ),
    );
  else await fs.copyFile(source, dest);
}
const pages = [
  "index.html",
  "about.html",
  "privacy.html",
  "dashboard/index_dashboard.html",
  "dashboard/admin.html",
];
for (const page of pages) {
  let content = await fs.readFile(path.join(root, page), "utf8");
  content = content
    .replaceAll('href="/styles.css"', `href="${prefix}/styles.css"`)
    .replaceAll('href="/landing.css"', `href="${prefix}/landing.css"`)
    .replaceAll('href="/tailwind.css"', `href="${prefix}/tailwind.css"`)
    .replaceAll('src="/js/', `src="${prefix}/js/`);
  content = rewriteBrandAssets(content);
  const dest = path.join(output, page);
  await fs.mkdir(path.dirname(dest), { recursive: true });
  await fs.writeFile(dest, content);
}
// Preserve existing search-engine verification files without shipping legacy application scripts.
for (const name of await fs.readdir(root)) {
  if (/^google[a-zA-Z0-9]+\.html$/.test(name) || name === "sitemap.xml") {
    await fs.copyFile(path.join(root, name), path.join(output, name));
  }
}
const landingHTML = await fs.readFile(path.join(output, "index.html"), "utf8");
const landingAssets = [...new Set([...landingHTML.matchAll(/(?:href|src)="([^"#]+)"/g)]
  .map((match) => match[1])
  .filter((reference) => reference.startsWith(prefix + "/")))];
const manifest = {
  version,
  assetPrefix: prefix,
  files: assetFiles.map((f) => path.relative(root, f).replaceAll("\\", "/")),
  landingRawBytes:
    (await fs.stat(path.join(output, "index.html"))).size +
    (await Promise.all(landingAssets.map(async (reference) =>
      (await fs.stat(path.join(output, reference.slice(1)))).size))).reduce((sum, bytes) => sum + bytes, 0) +
    (
      await Promise.all(
        fonts.map(
          async (f) => (await fs.stat(path.join(root, "src", "fonts", f))).size,
        ),
      )
    ).reduce((a, b) => a + b, 0),
  landingAssets,
  logoBytes: Math.max(...provenance.assets.filter((asset) => asset.kind === "logo").map((asset) => asset.bytes)),
  avatarBytes: Math.max(...provenance.assets.filter((asset) => asset.kind === "avatar").map((asset) => asset.bytes)),
  totalAvatarBytes: provenance.assets.filter((asset) => asset.kind === "avatar").reduce((sum, asset) => sum + asset.bytes, 0),
  originalAssets: provenance.assets,
};
await fs.writeFile(
  path.join(output, "asset-manifest.json"),
  JSON.stringify(manifest, null, 2),
);
if (manifest.landingRawBytes > 600 * 1024)
  throw new Error("Landing asset budget exceeded");
console.log(
  `Built ${pages.length} pages; assets ${version}; landing ${Math.ceil(manifest.landingRawBytes / 1024)} KiB raw including fonts.`,
);
