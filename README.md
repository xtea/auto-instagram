# auto-instagram

Open-source Instagram publisher that drives `instagram.com` with Playwright and your own imported cookies. Prepare content in a folder, configure your account once, publish.

> **Status:** Alpha. Personal-account use only. Using browser automation violates Instagram's ToS — use a scratch account, conservative pacing, and a residential IP that matches where you got the cookies.

## Why this project

Most Instagram scheduling tools require a Business/Creator account converted to Meta's Graph API. That rules out personal accounts entirely, and even for business accounts you need App Review + Business Verification before distributing a tool. `auto-instagram` takes the opposite approach: automate the website you already use, with the session you already have.

Supported post types (web UI constraints, April 2026):

- Feed image (single)
- Carousel (2–20 items, images or videos)
- Reels (≤ 90s vertical video)

**Not supported:** Stories (instagram.com doesn't support creating Stories — no automation can fix this without switching backends).

## Requirements

- Python 3.11+
- macOS or Linux (tested on macOS)
- A real Chrome/Chromium you can log in from on the same network you'll run the bot on
- (Recommended) a residential proxy if you plan to run this on a different machine from where you logged in

## Install

```bash
# From source
git clone <this-repo> auto-instagram
cd auto-instagram
uv sync                    # or: pip install -e '.[dev]'
patchright install chrome  # downloads the patched Chrome for Playwright
```

## Configure an account

1. Copy the example config to the account name you want to use:

   ```bash
   cp config/account.example.yaml config/demo.yaml
   ```

2. Edit `config/demo.yaml`. The important fields:
   - `handle`: your IG username (for display only)
   - `user_agent`, `viewport`, `locale`, `timezone`: **match the browser you'll log in from**. Drift between these and the cookie's origin is the #1 cause of `challenge_required`.
   - `pacing.max_posts_per_day`: start at 1–3. Hammering a personal account gets it flagged.

## Authenticate

Two paths; pick whichever you prefer.

### Option A — Headed manual login (simplest)

```bash
auto-ig login --account demo
```

A Chrome window opens. Log in by hand (handle 2FA yourself). When the home feed appears, the session is saved to `sessions/demo.json`.

### Option B — Import cookies from your real browser

If you already have a logged-in IG tab in Chrome:

1. Install [Cookie-Editor](https://cookie-editor.com/) (browser extension).
2. Open `instagram.com`, click the extension, "Export" → "Export as JSON" → save to `ig-cookies.json`.
3. Run:

   ```bash
   auto-ig import-cookies ./ig-cookies.json --account demo
   ```

The tool rejects the import if `sessionid`, `csrftoken`, or `ds_user_id` are missing.

### Verify

```bash
auto-ig doctor --account demo
```

Should print `OK: <handle> session is valid.`

## Publish content

### Layout

```
content/
└── my-post/
    ├── post.yaml
    └── media/
        ├── 1.jpg
        └── 2.jpg
```

### `post.yaml` schema

```yaml
type: feed           # feed | carousel | reel
caption: |
  Your caption text. Up to 2200 chars and 30 hashtags.
  #opensource
media:
  - ./media/1.jpg    # paths are relative to this file
schedule: 2026-04-25T14:00:00Z   # optional; UTC or with offset
```

Validation runs before any browser work:

| Type | Rule |
|---|---|
| `feed` | exactly 1 image/video |
| `carousel` | 2–20 items, images and/or videos |
| `reel` | exactly 1 video, `.mp4`/`.mov`/`.m4v` |
| caption | ≤ 2200 chars, ≤ 30 hashtags |

### One-shot publish

```bash
auto-ig publish content/my-post --account demo --dry-run   # safe first run
auto-ig publish content/my-post --account demo             # actually shares
```

`--dry-run` walks the full upload flow and stops before clicking **Share** — useful when patching selectors.

### Scheduled / queued publish

Drop posts with `schedule:` set in the future, then run `auto-ig queue` from cron / launchd / systemd-timer:

```cron
*/5 * * * * cd /path/to/auto-instagram && auto-ig queue --account demo >> sessions/queue.log 2>&1
```

The queue stores state in `sessions/queue.db` (SQLite) with statuses: `queued | running | succeeded | failed | paused`. Use `auto-ig list` to inspect.

## How the Playwright flow works

1. Launch Chrome via [Patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright) (Chromium with CDP/webdriver leaks patched at the binary level). Vanilla `playwright` is detected by Instagram's fingerprinting stack in 2026 — don't use it.
2. Load `sessions/<account>.json` as the Playwright `storage_state`.
3. Navigate to `instagram.com`, confirm the home-feed nav is visible (signal of authenticated state).
4. Click **New post** → (for Reels, select the Reel submenu) → `setInputFiles` into the hidden `<input type=file>`.
5. Click through **Next** → **Next**, fill caption, click **Share**.
6. Wait for the "Your post has been shared" confirmation and extract the `/p/<shortcode>/` if available.

All selectors are in [`src/auto_instagram/publisher/selectors.py`](src/auto_instagram/publisher/selectors.py) — when IG changes the UI, that is the file to patch.

### Adding an alternative backend

The `Publisher` protocol in `publisher/base.py` is deliberately minimal so you can drop in:

- `InstagrapiPublisher` (wrap `instagrapi` for more-robust personal-account posting, including Stories)
- `GraphApiPublisher` (Meta official API, Business/Creator accounts only)

## Pacing & safety

Built-in guardrails, tunable in `config/<account>.yaml`:

- `max_posts_per_day` daily cap (enforced by the queue)
- `min/max_step_delay_seconds` randomized delays between UI actions
- `pre_run_idle_seconds_*` scroll/dwell before the first click

On `challenge_required` / redirect to `/accounts/login/` or `/challenge/`, the runner pauses the job and records the reason. Re-authenticate with `auto-ig login` and retry.

## Known limitations

- **No Stories** — not supported by instagram.com.
- **Selectors rot.** IG ships UI changes every few weeks. Expect periodic patches to `selectors.py`.
- **2FA mid-run.** If IG challenges mid-publish, the tool pauses; manual re-login is required.
- **Shared IP.** Using cookies captured from residence A while running the bot on residence B's IP is the single most reliable way to get challenged.
- **ToS risk.** Browser-driven automation of personal IG accounts is against Instagram's terms. Ban risk is real. Use a scratch account.

## Non-goals (for now)

- Web UI / dashboard (CLI + YAML only)
- Long-running daemon (cron-friendly invocation instead)
- Engagement automation (likes, follows, DMs)

## License

MIT.
