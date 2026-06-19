// Build script for the Adjustable Bed Lovelace card.
// Bundles the Lit source into a single self-contained ESM file that ships
// inside the integration (custom_components/adjustable_bed/frontend/dist).
//
// Usage:
//   bun run build          # one-shot production build
//   bun run build.mjs --watch
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as esbuild from "esbuild";

const here = dirname(fileURLToPath(import.meta.url));
const manifest = JSON.parse(
  readFileSync(join(here, "..", "manifest.json"), "utf8"),
);
const watch = process.argv.includes("--watch");

/** @type {import('esbuild').BuildOptions} */
const options = {
  entryPoints: [join(here, "src", "adjustable-bed-card.ts")],
  outfile: join(here, "dist", "adjustable-bed-card.js"),
  bundle: true,
  format: "esm",
  target: "es2021",
  minify: !watch,
  sourcemap: false,
  legalComments: "none",
  define: {
    __CARD_VERSION__: JSON.stringify(manifest.version),
  },
  banner: {
    js: `/* adjustable-bed-card ${manifest.version} — ships with the Adjustable Bed integration. Do not edit; build from frontend/src. */`,
  },
};

if (watch) {
  const ctx = await esbuild.context(options);
  await ctx.watch();
  console.log("watching frontend/src for changes…");
} else {
  await esbuild.build(options);
  console.log(`built dist/adjustable-bed-card.js (v${manifest.version})`);
}
