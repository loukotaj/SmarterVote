# Smarter.Vote visual system

`Smarter.Vote Brand Assets.dc.html` is the editable source for the brand artwork. Its social-banner canvases are shown scaled down for review, so a full-page screenshot is not a valid export.

From `web/`, regenerate the social PNGs with:

```powershell
npm run export:brand-assets
```

The command renders each named banner canvas at its intended platform dimensions in `exports/banners/`.
