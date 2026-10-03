import fs from "node:fs/promises";
import path from "node:path";
import crypto from "node:crypto";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

// Optional authoring tool only. The normal build verifies the checked-in output
// and does not install or execute a native image encoder.
const require = createRequire(import.meta.url);
const sharp = require(process.env.MATCHSHO_SHARP_PATH || "sharp");
const encoder = { sharp: "0.35.4", vips: "8.18.6", webp: "1.6.0" };
for (const [library, version] of Object.entries(encoder)) {
  if (sharp.versions[library] !== version)
    throw new Error(`Reproduction requires ${library} ${version}`);
}
const root = fileURLToPath(new URL("../", import.meta.url));
const output = path.join(root, "assets", "original-brand");
const sha256 = (bytes) => crypto.createHash("sha256").update(bytes).digest("hex");
const definitions = [
  { source: "src/Matchsho.jpg", file: "matchsho-logo.webp", kind: "logo", trim: true, width: 192, lossless: true },
  { source: "src/avatar-male.png", file: "avatar-male.webp", kind: "avatar", width: 192 },
  { source: "src/avatar-female-3d.png", file: "avatar-female.webp", kind: "avatar", width: 192 },
  { source: "src/6.jpg", file: "dorm-room.jpg", kind: "illustration" },
  { source: "src/4.jpg", file: "dorm-life.jpg", kind: "illustration" },
  ...[1, 2, 3, 5, 7].map((number) => ({ source: `src/${number}.jpg`, file: `dorm-${number}.jpg`, kind: "illustration" })),
];
await fs.mkdir(output, { recursive: true });
const assets = [];
for (const definition of definitions) {
  const original = await fs.readFile(path.join(root, definition.source));
  const input = await sharp(original).metadata();
  let image = sharp(original);
  if (definition.trim) image = image.trim({ threshold: 8 });
  if (definition.width) image = image.resize({ width: definition.width, withoutEnlargement: true });
  const bytes = definition.width
    ? await image.webp({ lossless: definition.lossless || false, quality: 88, alphaQuality: 100, effort: 6 }).toBuffer()
    : original;
  const metadata = await sharp(bytes).metadata();
  await fs.writeFile(path.join(output, definition.file), bytes);
  assets.push({
    source: definition.source,
    sourceSha256: sha256(original),
    sourceBytes: original.length,
    sourceFormat: input.format,
    file: definition.file,
    kind: definition.kind,
    sha256: sha256(bytes),
    bytes: bytes.length,
    width: metadata.width,
    height: metadata.height,
    transform: !definition.width ? "unchanged copy" : definition.trim
      ? "trim near-transparent border (threshold 8/255); resize width to 192; lossless WebP"
      : "resize width to 192; WebP quality 88, alpha quality 100",
  });
}
await fs.writeFile(path.join(output, "manifest.json"), JSON.stringify({ encoder, assets }, null, 2) + "\n");
console.log(assets.map((asset) => `${asset.file}: ${asset.bytes} bytes (${asset.width}x${asset.height})`).join("\n"));
