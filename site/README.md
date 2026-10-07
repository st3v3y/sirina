# Sirina landing page

Static [Astro](https://astro.build) site for Sirina, deployed on Vercel.

```bash
npm install
npm run dev      # http://localhost:4321
npm run build    # type-check + static build into dist/
```

- Links, version and the beta bar live in [`src/config.ts`](src/config.ts). When a GitHub
  release with a `.dmg` exists, set `hasRelease: true` and the download buttons point to it.
- Fonts are self-hosted via Fontsource, so the page makes no third-party requests.

## Deploying on Vercel

1. Import the `st3v3y/sirina` repository in Vercel.
2. Set **Root Directory** to `site`. Vercel detects Astro; the defaults
   (`npm run build`, output `dist`) are correct.
3. [`vercel.json`](vercel.json) skips deployments when nothing under `site/` changed.
