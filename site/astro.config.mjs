// @ts-check
import { defineConfig } from "astro/config";

export default defineConfig({
  // Static site: `npm run build` writes plain HTML/CSS to dist/ (Vercel picks it up as is).
  output: "static",
});
