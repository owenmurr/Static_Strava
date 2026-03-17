# 🏃 Strava Static Dashboard

A nightly-generated static HTML dashboard for your Strava profile, automatically deployed to Cloudflare Pages via GitHub Actions.

## What it shows

- **All-time stats** — total runs, distance, time, elevation
- **Year-to-date stats** — YTD runs, distance, time
- **Recent activities feed** — last 20 activities with pace, distance, elevation
- **Best efforts & PRs** — 400m, 1K, 5K, 10K, Half-Marathon, Marathon

---

## Setup

### 1. Strava API credentials

1. Go to [strava.com/settings/api](https://www.strava.com/settings/api) and create an app.
2. Note your **Client ID** and **Client Secret**.
3. Get a refresh token with the right scopes by running a one-time OAuth flow.
   The easiest way is to visit this URL in your browser (replace `YOUR_CLIENT_ID`):

   ```
   https://www.strava.com/oauth/authorize?client_id=YOUR_CLIENT_ID&response_type=code&redirect_uri=http://localhost&approval_prompt=force&scope=read,activity:read_all
   ```

   After approving, copy the `code` param from the redirect URL, then exchange it:

   ```bash
   curl -X POST https://www.strava.com/oauth/token \
     -d client_id=YOUR_CLIENT_ID \
     -d client_secret=YOUR_CLIENT_SECRET \
     -d code=AUTH_CODE \
     -d grant_type=authorization_code
   ```

   Save the `refresh_token` from the response — it does not expire.

### 2. Cloudflare Pages project

1. In the Cloudflare dashboard, create a **Pages** project (use "Direct Upload" mode — no Git integration needed since GitHub Actions handles deployment).
2. Note the **project name** you chose.
3. Create a Cloudflare API token with `Cloudflare Pages: Edit` permissions.
4. Note your Cloudflare **Account ID** (found on the Pages or Workers overview page).

### 3. GitHub repository secrets

In your GitHub repo → **Settings → Secrets and variables → Actions**, add:

| Secret name                   | Value                                     |
|-------------------------------|-------------------------------------------|
| `STRAVA_CLIENT_ID`            | Your Strava app client ID                |
| `STRAVA_CLIENT_SECRET`        | Your Strava app client secret            |
| `STRAVA_REFRESH_TOKEN`        | Long-lived refresh token from step 1     |
| `CLOUDFLARE_API_TOKEN`        | Cloudflare API token from step 2         |
| `CLOUDFLARE_ACCOUNT_ID`       | Your Cloudflare account ID               |
| `CLOUDFLARE_PAGES_PROJECT`    | Cloudflare Pages project name            |

### 4. Push to GitHub

```bash
git add .
git commit -m "Initial Strava dashboard setup"
git push
```

The workflow runs nightly at **02:00 UTC**. You can also trigger it manually from **Actions → Build & Deploy Strava Dashboard → Run workflow**.

---

## Running locally

```bash
pip install -r requirements.txt

export STRAVA_CLIENT_ID=your_id
export STRAVA_CLIENT_SECRET=your_secret
export STRAVA_REFRESH_TOKEN=your_refresh_token

python scripts/generate.py
# Output: dist/index.html
open dist/index.html
```

---

## Project structure

```
.
├── .github/
│   └── workflows/
│       └── deploy.yml       # GitHub Actions workflow
├── scripts/
│   └── generate.py          # Main generator script
├── requirements.txt
└── README.md
```

## Customising

- **Schedule**: Edit the `cron` line in `deploy.yml` (uses UTC).
- **Activity count**: Change `per_page=20` in `generate.py`.
- **Units**: Switch `metres_to_km` → `metres_to_miles` in the card renderer.
- **Colours**: Tweak CSS variables at the top of `generate_html()`.
