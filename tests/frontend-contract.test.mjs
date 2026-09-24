import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

const packageManifest = JSON.parse(readFileSync("package.json", "utf8"));
const tailwindConfig = readFileSync("tailwind.config.js", "utf8");
const prelineModule = readFileSync("static/src/js/preline.js", "utf8");

function filesUnder(root) {
  const found = [];
  for (const entry of readdirSync(root, { withFileTypes: true })) {
    const path = join(root, entry.name);
    if (entry.isDirectory()) found.push(...filesUnder(path));
    else if (statSync(path).isFile()) found.push(path);
  }
  return found;
}

test("frontend dependencies and build tools use exact versions", () => {
  for (const version of [
    ...Object.values(packageManifest.dependencies),
    ...Object.values(packageManifest.devDependencies),
  ]) {
    assert.match(version, /^\d+\.\d+\.\d+$/);
  }
  assert.equal(packageManifest.dependencies.preline, "5.0.0");
  assert.equal(packageManifest.dependencies["chart.js"], "4.5.1");
  assert.equal(packageManifest.dependencies.lucide, "1.44.0");
  assert.equal("geist" in packageManifest.dependencies, false);
});

test("official Geist font files are self-hosted", () => {
  for (const filename of [
    "Geist-Regular.woff2",
    "Geist-Medium.woff2",
    "Geist-SemiBold.woff2",
    "Geist-Bold.woff2",
    "GeistMono-Regular.woff2",
  ]) {
    assert.equal(existsSync(`static/src/fonts/geist/${filename}`), true, filename);
  }
});

test("Tailwind exposes only the approved responsive screen keys", () => {
  for (const [name, size] of Object.entries({
    xs: "475px",
    sm: "640px",
    md: "768px",
    lg: "1024px",
    xl: "1280px",
    "2xl": "1536px",
  })) {
    assert.match(tailwindConfig, new RegExp(`(?:${name}|[\"']${name}[\"']): [\"']${size}[\"']`));
  }
});

test("Preline initializes after DOM readiness", () => {
  assert.match(prelineModule, /DOMContentLoaded/);
  assert.match(prelineModule, /HSStaticMethods\.autoInit\(\)/);
});

test("authored frontend has no dark-mode trigger", () => {
  const authoredFiles = [
    ...filesUnder("templates"),
    ...filesUnder("static/src"),
  ];
  const forbidden = /dark:|\.dark\s*\{|data-theme\s*=\s*["']dark|prefers-color-scheme\s*:\s*dark/i;
  for (const path of authoredFiles) {
    assert.doesNotMatch(readFileSync(path, "utf8"), forbidden, path);
  }
});
