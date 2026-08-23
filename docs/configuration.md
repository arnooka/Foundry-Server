# Configuration Reference

Every setting lives in one file: `.env` at the repo root. It's gitignored,
never committed, and you don't need to create it yourself. `docker compose
up -d` works fine with no `.env` present; the admin UI's first-run setup
wizard creates it the first time you open `http://localhost:8080` (see
[Admin UI Guide](admin-ui-guide.md#first-run-setup)). `docker-compose.yml`
and the admin UI both read and write this same file, and it's the single
source of truth described in [Architecture](architecture.md).

Two ways to change a value after that:

- **Through this admin UI** (Dashboard tab): covers the day-to-day Foundry
  settings and your account/recovery settings, and handles restarting the
  `foundry` container for you where relevant.
- **By hand in `.env`**: needed for the handful of settings not exposed in
  the dashboard (Cloudflare Tunnel token, or a manual account reset), or if
  you prefer editing the file directly. After a manual edit, run
  `docker compose up -d` from the repo root to apply it. `.env.example`
  documents every variable if you want a reference template.

> **Escaping note:** Docker Compose treats a literal `$` in an `.env` value
> as the start of a variable reference and will silently strip whatever
> follows it. If you type a value directly into `.env` that contains `$`
> (a password hash is the most likely case), write it as `$$` instead.
> Values you edit through the admin web UI don't need this, since the app
> escapes automatically on save and un-escapes when it displays the field
> back to you. See
> [Troubleshooting](troubleshooting.md#a-value-with-a--in-it-got-corrupted).

---

## Foundry VTT

Everything in this section except the two version fields is editable from
the Dashboard.

#### `FOUNDRY_CONTAINER_TAG`
Docker image tag for the `felddy/foundryvtt` image itself, e.g. `release`,
`12`, `13`. Default `release`. Not exposed on the dashboard since it's
rarely changed; edit `.env` directly and run `docker compose up -d --build`
from the host.

#### `FOUNDRY_VERSION`
A specific Foundry **software** version to install, e.g. `12.331`. Leave
blank to use whatever version ships by default with `FOUNDRY_CONTAINER_TAG`.
Don't put an image alias like `release` here: it's passed straight to the
entrypoint, which expects a concrete version number and will log a harmless
mismatch warning otherwise.

Why two separate variables instead of one? See
[Architecture: the two version knobs](architecture.md#the-two-version-knobs).

#### `FOUNDRY_HOSTNAME`
Hostname baked into the container and into Foundry's own config. **Foundry
ties license activation to this value**, so once you've activated against a
given hostname, changing it can require re-activating. Default `foundry`;
leave it unless you have a specific reason to change it.

#### `FOUNDRY_LICENSE_KEY`
Your license key from the **Purchased Licenses** page on foundryvtt.com
(e.g. `K3OX-MWZR-AH18-ZJHQ-ZAMO-SLNY`). Installs and activates Foundry
automatically at container startup. Leave blank and Foundry will prompt for
it in its own web UI on first boot instead - either way works, this just
skips a manual step.

#### `FOUNDRY_ADMIN_KEY`
The password Foundry itself asks for on its `/setup` and `/auth` screens
(separate from this admin UI's login). **Required** - the Foundry Settings
wizard won't save until this is set at least once, since leaving it unset
means those screens are unprotected.

#### `FOUNDRY_USERNAME` / `FOUNDRY_PASSWORD`
Your foundryvtt.com account credentials. Used only at container startup to
download the release your license entitles you to, and not sent anywhere
except foundryvtt.com's own download endpoint. Fill in both or leave both
blank - the dashboard won't save one without the other, since a lone
username or password can't actually authenticate.

If you'd rather not store your account password here at all, leave these two
blank and set `FOUNDRY_RELEASE_URL` directly in `.env` instead: a temporary
presigned download link from your Foundry account page. This isn't exposed
in the dashboard; see the
[felddy/foundryvtt-docker docs](https://github.com/felddy/foundryvtt-docker)
for how to generate one.

#### `FOUNDRY_WORLD`
World folder name to launch automatically on container start. Leave blank to
land on Foundry's setup/world-selection screen instead.

#### `FOUNDRY_LANGUAGE`
Language code plus the module that provides its translation, e.g. `en.core`
(the default) or `fr.core`. Not a small fixed list in the dashboard - which
codes work depends on which language modules are actually installed - so
this stays a free-text field rather than a dropdown.

#### `CONTAINER_PRESERVE_CONFIG`
`true` (default) keeps Foundry's own generated config files across restarts
instead of regenerating them from the env vars above on every restart. Not
exposed on the dashboard; leave it `true` unless you're deliberately
resetting config.

---

## Cloudflare Tunnel

Set from the last step of the Foundry Settings wizard on the dashboard
("Cloudflare domain"), or directly in `.env`. See
[Cloudflare Tunnel Setup](cloudflare-tunnel-setup.md) for how to obtain them.

#### `CLOUDFLARE_TUNNEL_TOKEN`
The token for the tunnel you create in the Cloudflare Zero Trust dashboard
(Networks → Tunnels). Required for `cloudflared` to authenticate and connect
at all. Internally this is mapped to the `TUNNEL_TOKEN` environment variable
`cloudflared` actually reads (see `docker-compose.yml`); it's named with the
`CLOUDFLARE_` prefix here for consistency with the rest of this file. Tunnel
tokens are base64, so the `$` escaping note above doesn't come into play.

#### `PUBLIC_HOSTNAME`
Optional. The hostname you configured as the tunnel's Public Hostname in the
Cloudflare dashboard (e.g. `dndwithfriends.com`). Purely cosmetic: it only
controls what the admin dashboard displays and links to, since Cloudflare
Tunnel has no local API to query this automatically the way ngrok did. Leave
it blank and the dashboard just won't show a link.

---

## Admin UI account

Set by the app itself, not by hand. See
[Admin UI Guide: First-run setup](admin-ui-guide.md#first-run-setup). Listed
here only so you know what they are, in case you ever need to reset one
manually per
[Troubleshooting](troubleshooting.md#im-locked-out-and-never-set-up-email-recovery).

#### `ADMIN_UI_USERNAME`
Login username for this admin UI, set on the `/setup` page on first run.

#### `ADMIN_UI_PASSWORD_HASH`
A werkzeug password hash (never a plaintext password), written by `/setup`
initially and updated by the dashboard's Account & Recovery panel or the
forgot-password flow thereafter.

#### `FLASK_SECRET_KEY`
Random key Flask uses to sign session cookies. Generated automatically the
first time `config-ui` starts with none set, and persisted here so sessions
survive restarts. Nothing to do here yourself.

---

## Password reset via email

All editable from the dashboard's Account & Recovery panel; see
[Admin UI Guide: Forgot your password?](admin-ui-guide.md#forgot-your-password).

#### `ADMIN_UI_RECOVERY_EMAIL`
Destination address for a "forgot password" reset code.

#### `SMTP_HOST` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_FROM_ADDRESS`
Credentials used to send the reset code. STARTTLS on port 587 is assumed
(the default for most providers); implicit TLS on port 465 isn't supported.
For Gmail, `SMTP_PASSWORD` must be an
[App Password](https://myaccount.google.com/apppasswords), not your regular
account password. `SMTP_FROM_ADDRESS` defaults to `SMTP_USERNAME` if left
blank.

---

## Full example

See [`.env.example`](../.env.example) at the repo root for a copy-pasteable
reference template with every variable documented.
