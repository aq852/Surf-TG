# AkMovieVerse 3.1

AkMovieVerse is a self-hosted gateway for organizing and streaming media from **Telegram channels you are authorized to access**. It is the branded, security-focused evolution of Surf-TG maintained by [aq852](https://github.com/aq852).

It keeps the original project's direct workflow—sign in, open a channel, choose a file, and play it—while adding a modern media-library experience and stronger access controls.

## Highlights

- Private channel and collection browser
- HTTP range streaming with correct single-byte, suffix, open-ended, and chunk-boundary handling
- Signed, expiring stream links for VLC, MX Player, browser playback, and downloads
- Multiple Telegram bot clients with least-loaded selection
- Search, pagination, thumbnails, and curated folders
- Viewer and administrator roles
- PBKDF2-SHA256 password hashes and encrypted, persistent cookies
- Authorized-channel enforcement for browsing and thumbnails
- Optional allowlist for Telegram `/start file_...` shortcuts
- Responsive, self-contained UI
- AkMovieVerse branding and original local logo
- Admin-uploaded channel profile pictures
- Admin controls for deleting indexed rows and marking files premium/download-disabled
- Individual free or premium viewer accounts stored as password hashes
- Member profile with expiry countdown, self-service password changes, and Telegram owner support
- Poster-only sponsor banners that can point to a Direct Link, affiliate, or your own promotion
- Eight persistent themes, including Royal Gold, Aurora Glass, AMOLED Black, and Graphite Luxe
- Mobile-first navigation with a compact Menu button on small screens
- Dedicated `/admin` control centre for library, advertising, accounts, premium collections, and global downloads
- Home tabs for channel/category browsing and the latest indexed uploads across every authorized channel
- Premium-only collections, including nested collection protection
- Global download switch that preserves existing individual file policies
- VLC-compatible `.m3u` playlist download for desktop playback
- Conservative filename cleanup for links, handles, and channel promotions
- Optional, clearly labelled ad placement configured by environment variables
- Docker deployment and automated regression tests

## Security changes from Surf-TG 1.x

| Previous behaviour | Surf-TG 2.0 |
|---|---|
| Six-character Telegram unique ID used as a secret | HMAC-SHA256 signed stream capability with expiry |
| Direct stream endpoint accepted arbitrary chat/message coordinates | Coordinates must match a valid signed capability |
| `/send` import endpoint was public | Administrator session, authorized channel, and token validation required |
| Thumbnail/channel routes accepted arbitrary chats | Restricted to configured authorized channels |
| Session encryption key changed after every restart | Stable key derived from deployment `SECRET_KEY` |
| Default `admin/admin` credentials | Startup refuses known default credentials |
| Plain-text passwords only | PBKDF2-SHA256 hashes supported and recommended |
| Unlimited login attempts | Per-address login throttling |
| Message cache keyed only by message ID | Cache keyed by `(chat_id, message_id)` |
| Incorrect inclusive range chunk count | Tested inclusive range planner |
| Blocking MongoDB operations in the event loop | Database calls moved to worker threads |
| Source deleted and replaced from Git on every boot | Self-updater removed completely |
| Remote scripts and developer-tool blocker | Local CSS/JavaScript only |
| Root Docker process with Git in runtime | Minimal non-root runtime image |

## Requirements

- Python 3.11 or 3.12, or Docker
- A MongoDB instance
- Telegram API ID and API hash from `my.telegram.org`
- A Telegram bot that can read each configured channel
- Optional Pyrogram/Pyrofork user session for history browsing

Only use Surf-TG with media and channels you have permission to access. Telegram is not a substitute for appropriate content rights.

## Configuration

Copy `config_sample.env` to `config.env` and fill in the required values.

Generate a deployment secret:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Generate viewer and administrator password hashes:

```bash
python -m bot.helper.security
```

Store the resulting strings as `PASSWORD_HASH` and `ADMIN_PASSWORD_HASH`. The plain-text `VIEWER_PASSWORD` and `ADMIN_PASSWORD` variables exist only for migration and should be removed after hashes are configured.

Important settings:

| Variable | Purpose |
|---|---|
| `AUTH_CHANNEL` | Comma-separated channel IDs such as `-1001234567890` |
| `SECRET_KEY` | At least 32 random characters; changing it signs users out and invalidates links |
| `STREAM_TOKEN_TTL` | Link lifetime in seconds; default is six hours |
| `COOKIE_SECURE` | Keep `true` behind HTTPS; use `false` only for local HTTP development |
| `MULTI_TOKEN1...50` | Optional extra bot tokens used for streaming capacity |
| `SITE_NAME` | Display name; defaults to `AkMovieVerse` |
| `SITE_CREDIT` | Footer credit; defaults to `By AkMovieVerse` |
| `THEME` | Default for new browsers: `midnight`, `cinema`, `ocean`, `royal`, `aurora`, `amoled`, `graphite`, or `light` |
| `FILENAME_CLEANUP_REGEX` | Optional additional case-insensitive regex removed from indexed titles |
| `AD_URL` | Optional initial sponsor-banner HTTP(S) destination (including an approved Direct Link) |
| `AD_IMAGE_URL` | Optional initial desktop sponsor poster URL |
| `AD_MOBILE_IMAGE_URL` | Optional mobile sponsor poster URL |
| `SUPPORT_USERNAME` | Telegram support username; defaults to `AK_ownerbot` |

## Run with Docker

```bash
cp config_sample.env config.env
# Edit config.env first
docker compose up --build
```

Open `http://localhost:8080`. When testing locally over HTTP, set `COOKIE_SECURE=false`. Production deployments should terminate HTTPS at a trusted reverse proxy and keep it enabled.

## Run from Python

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m bot
```

On Windows, activate with `.venv\Scripts\activate`.

## Initial channel indexing

1. Add the bot to every channel in `AUTH_CHANNEL`.
2. Send `/index` in a configured channel once to import existing messages.
3. New document and video messages are indexed automatically.
4. Add a `SESSION_STRING` if you want the UI to browse Telegram history directly instead of relying only on MongoDB's index.

Re-run `/index` after changing filename-cleanup rules. Index batches are committed as they are scanned, so an interruption no longer discards completed progress.

## Accounts and premium access

Sign in as the administrator and open **Admin** to create a unique login for each member. Existing accounts can be opened to change their password, free/premium tier, enabled status, or automatic expiry date. Collections can be created or updated as **Free** or **Premium only**. On a channel page, open a file card's **Manage** panel to rename only its displayed title, mark it free or premium, hide its download button, or remove its indexed row. The channel danger zone can remove every indexed row in that channel at once; neither delete action removes the original Telegram messages.

The **Global downloads** policy in `/admin` can hide download buttons for the entire library while keeping browser streaming active. It does not overwrite per-file download choices, so turning it back on restores the individual settings.

Members can open **Profile** to see their username, plan, and remaining account lifetime, change their own database-backed password, or contact the owner through `@AK_ownerbot`. Built-in environment accounts remain server-managed and do not expose password changes in the browser.

“Watch only” is a policy control, not DRM: any browser that can decode a video receives its bytes and a determined viewer can capture them. AkMovieVerse hides and cryptographically scopes the explicit download action, but it does not claim to make streamed media impossible to copy. Likewise, individual accounts improve accountability, but preventing credential sharing completely requires server-side device/session limits or a paid identity provider.

## Channel art, themes, and ads

Administrators can upload a PNG, JPEG, or WebP channel picture (maximum 5 MB) from the channel page. Library settings choose the default theme for new browsers. Every signed-in page also has a personal theme picker that remembers its selection in that browser. The sun/moon button switches to Ivory Daylight and then restores the viewer's last dark theme.

The administrator can create a manual banner under **Admin**: enter its title, destination URL, and optional image URL, choose whether it appears everywhere, Home, channel, collection, or player pages, then enable it. Values from `config.env` are initial fallbacks; saving the form stores the managed values in MongoDB. Manual and network ads can be enabled independently.

The sponsor banner is a responsive image link, not third-party JavaScript. Set a desktop poster, optional mobile poster, destination URL, and placement in **Admin → Sponsor banner**. The destination may be your own promotion, affiliate URL, or an approved Direct Link. If no valid desktop poster is configured, or the image fails to load, the entire slot disappears. Premium members and administrators never receive sponsor markup.

## Tests

```bash
python -m unittest discover -s tests -v
python -m compileall -q bot tests
```

The regression suite covers password hashes, signed-link tampering and expiry, RFC-style range parsing, the one-byte range case, exact 1 MiB boundaries, and external-script checks.

## Architecture

```text
Browser / player
       │ authenticated pages + signed temporary stream links
       ▼
aiohttp web gateway
       ├── MongoDB: index, collections, settings
       └── Pyrofork clients
               └── Telegram channels
```

This is intentionally a focused file gateway. Rich movie/series metadata and Stremio catalogs belong in the planned next-generation service rather than this small server.

## Compatibility note

Old `?hash=abcdef` stream and watch links are intentionally invalid. Open the file from the upgraded library to obtain a new signed link.

## License, attribution, and credits

GPL-3.0. This project is derived from [weebzone/Surf-TG](https://github.com/weebzone/Surf-TG); the original copyright and license are preserved in `LICENSE`. The AkMovieVerse 2.0/3.1 redesign, security hardening, indexing repairs, access controls, account system, and interface work are maintained by [aq852](https://github.com/aq852) with Codex-assisted implementation. See [the upgrade record](docs/AKMOVIEVERSE_CHANGES.md).
