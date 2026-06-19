# IndexNow

SmarterVote can notify Bing and other IndexNow participants after the public web deploy publishes a fresh sitemap.

## Setup

1. Generate an IndexNow API key in Bing Webmaster Tools or at the official IndexNow key generator.
2. Add the key as the GitHub Actions secret `INDEXNOW_KEY`.
3. Run the Cloudflare Pages deploy workflow.

The deploy workflow writes the key file to the deployed site as:

```text
https://smarter.vote/<INDEXNOW_KEY>.txt
```

After Cloudflare Pages deploys, the workflow runs:

```bash
cd web
npm run submit:indexnow
```

The script reads `web/static/sitemap.xml`, submits only `smarter.vote` URLs, and chunks requests at 10,000 URLs per POST.

## Local Dry Run

```bash
cd web
$env:INDEXNOW_KEY = "your-key"
$env:INDEXNOW_DRY_RUN = "true"
npm run submit:indexnow
```

Use `INDEXNOW_HOST`, `INDEXNOW_KEY_LOCATION`, `INDEXNOW_ENDPOINT`, or `INDEXNOW_SITEMAP_PATH` only if the production host or file locations change.
