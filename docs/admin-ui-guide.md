# Admin UI Guide

This is the Flask app you're using right now: a small dashboard for
changing Foundry's settings and checking on the stack, without touching a
terminal. It's reachable at `http://localhost:8080` (or
`http://<your-lan-ip>:8080` from another device on your network) and is
intentionally **LAN-only**. See [Architecture](architecture.md#why-two-nginx-vhosts-not-one)
for why, and don't forward port 8080 through your router.

## First-run setup

There's no default password, and you don't create one by hand. On a clean
checkout, with no `.env` at all, the very first thing `http://localhost:8080`
shows you is a **Create your admin account** page (`/setup`) instead of a
login form: pick a username, password, and optionally a recovery email right
there in the browser. Submitting it writes `ADMIN_UI_USERNAME` and
`ADMIN_UI_PASSWORD_HASH` (and a freshly generated `FLASK_SECRET_KEY`, so your
session survives restarts) to `.env` and logs you straight in.

Once an account exists, `/setup` stops being offered. Visiting it again just
redirects to the normal login page, so a second person on your LAN can't use
it to take over the instance. From then on, use the dashboard's **Account &
Recovery** panel (see below) to change your password or update recovery
settings, rather than editing `.env` directly.

## Forgot your password?

If you configured a recovery email and SMTP settings (either during setup or
later from the dashboard's Account & Recovery panel), the login page has a
**Forgot password?** link that:

1. Emails a one-time code (`/forgot-password`) to your recovery address,
   valid for 15 minutes.
2. Lets you enter that code plus a new password (`/reset-password`) to
   regain access.

The code is checked in memory by the running `config-ui` process (never
written to disk), expires after 15 minutes, and is invalidated after 5 wrong
attempts or a fresh request; request a new one if it lapses. Requesting a
new code is also capped at one per 60 seconds, and only after a successful
send - a failed attempt, e.g. while you're still fixing a password below,
doesn't count against it.

If you never configured recovery email/SMTP, or the account you'd reset into
is otherwise unreachable, there's no self-service option. See
[Troubleshooting](troubleshooting.md#im-locked-out-and-never-set-up-email-recovery)
for the manual `.env` fallback.

### Setting up the sending email account

The "Sending Email Address" and "Email App Password" fields (Account &
Recovery panel, or during first-run setup) are **not your regular email
login**. Every major provider now blocks third-party apps, this one
included, from signing in with your normal password once two-factor
authentication is on, so you need to generate a separate, single-purpose
password just for this - the same requirement you'd hit setting up any mail
client or script against that account.

**Gmail** (recommended: the most tested path, and defaults are already set
for it):
1. Turn on 2-Step Verification if it isn't already: https://myaccount.google.com/signinoptions/two-step-verification
2. Generate an app password: https://myaccount.google.com/apppasswords
   (name it anything, e.g. "Foundry Admin")
3. Paste the 16-character result into **Email App Password**, removing the
   spaces Google displays it with.
4. Leave **Email Server** / **Email Server Port** as the defaults
   (`smtp.gmail.com` / `587`).

**Outlook.com / Hotmail / Live**:
1. Turn on two-step verification: https://account.live.com/proofs/manage
2. Generate an app password: https://account.live.com/proofs/AppPassword
3. Email Server: `smtp-mail.outlook.com`, Port: `587`.

Microsoft has been tightening restrictions on this kind of basic-password
SMTP access for consumer accounts, so this path is more likely to stop
working over time than Gmail's. If it doesn't work, Gmail is the more
reliable fallback.

**Yahoo Mail**:
1. Turn on two-step verification in Yahoo Account Security.
2. Generate an "app password" from the same Account Security page.
3. Email Server: `smtp.mail.yahoo.com`, Port: `587`.

**iCloud Mail**:
1. Turn on two-factor authentication for your Apple ID if it isn't already.
2. Generate an app-specific password at https://appleid.apple.com/account/manage
3. Email Server: `smtp.mail.me.com`, Port: `587`.

**Any other provider**: search "`<your provider>` app password" or
"`<your provider>` SMTP third-party app." Nearly every provider that
supports two-factor authentication has an equivalent settings page. If yours
doesn't, Gmail is a reasonable free account to set up just for this purpose.

If you paste in a real app password and it still doesn't work, the error
shown on the Forgot Password page is the provider's own SMTP rejection
message, which usually says exactly what's wrong (wrong password, app
password required, etc.).

## The dashboard

After logging in you'll see:

- **Status row**: whether the `foundry` container is currently running, and
  the public hostname you recorded in `PUBLIC_HOSTNAME`. Cloudflare Tunnel
  has no local API to query this live the way ngrok did, so this is just an
  echo of what you set in `.env`, not a health check of the tunnel itself.
- **Foundry Settings wizard**: one step per group of related fields (version
  & world, server identity & admin access - including your license key, your
  foundryvtt.com account, and Cloudflare domain - see
  [Configuration Reference](configuration.md#foundry-vtt) and
  [Cloudflare Tunnel](configuration.md#cloudflare-tunnel)), ending in a
  **Save & Restart** button. A few fields are required before it'll save -
  currently just the Admin Key, and either both or neither of the
  foundryvtt.com username/password - marked with a `*` and enforced both in
  the browser and on the server.
- **Account & Recovery panel**: your recovery email and SMTP settings (for
  the forgot-password flow above), plus a change-password field, saved
  separately via its own button so editing these never restarts Foundry.

Password-type fields (admin key, account password) show as blank with a
"leave blank to keep current" placeholder rather than echoing the stored
secret back to you in the page source. Leaving one blank and saving does not
clear it; it's left untouched. To actually clear one, you'd need to edit
`.env` by hand.

## What "Save & Restart" actually does

1. Writes your changes into `.env` (the same file `docker-compose.yml`
   reads).
2. Runs `docker compose up -d --no-deps foundry` against the host's Docker
   engine. `foundry` restarts on every save, regardless of which step you
   edited.
3. If the Cloudflare domain step's Tunnel Token or Domain changed, also runs
   the same command against `cloudflared`, so the tunnel picks up the new
   token/hostname immediately instead of waiting for its next natural
   restart.

`nginx` and `config-ui` are never touched by this, so your session stays
logged in. Expect a short window, usually well under a minute, where Foundry
(and, if the tunnel restarted too, the public URL) is unreachable while the
affected container(s) restart. A flash message on the dashboard reports
success or shows the raw Docker output if a restart failed.

Because Foundry (and cloudflared) only read their configuration from
environment variables at container startup, there's no "live reload";
every settings change means a restart. If players are mid-session, warn
them first.

## Docs viewer

The **Docs** tab in the nav renders this repo's `README.md` and everything
under `docs/` directly in the browser, so you don't need to leave the admin
UI to look something up. Once an account exists, it's reachable without
logging in, since no secrets live in the docs themselves, but it's still
only reachable on the LAN vhost like the rest of this app. Before an account
exists, it redirects to `/setup` like everything else does. The same files
render normally if you open them on GitHub or any other Markdown viewer;
there's nothing admin-UI-specific in them.
