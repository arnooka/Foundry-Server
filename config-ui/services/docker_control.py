"""Helpers for reading/writing the shared .env file, driving the foundry
service through the Docker CLI over the mounted host socket, and managing
this app's own account (creation, password reset via email)."""

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from secrets import token_hex

from dotenv import dotenv_values, set_key
from werkzeug.security import generate_password_hash

ENV_PATH = "/workspace/.env"
COMPOSE_FILE = "/workspace/docker-compose.yml"
PROJECT_DIR = "/workspace"

# Uses the light-background, transparent-glyph variant, since the email
# card is always white regardless of the recipient's theme and there's no
# way to detect that in email (so no dark counterpart needed, unlike the
# sidebar/login logo). Embedded inline via Content-ID in send_reset_email
# rather than linked, so it still renders for clients that block remote
# images.
_CONFIG_UI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # services/ -> static/ is one level up
LOGO_PATH = os.path.join(_CONFIG_UI_DIR, "static", "img", "logo-light-transparent.png")
LOGO_CID = "foundry-admin-logo"

# Fields on the dashboard's Foundry Settings wizard, grouped into steps:
# (step title, step subtitle, [(env key, label, input type, help text), ...]).
# The grouping is presentation only; EDITABLE_FIELDS below is the flattened
# form actually read/written by /settings and /save in app.py.
SETTINGS_STEPS = [
    (
        "Foundry version & world",
        "Which release to run, and what to load automatically when it starts.",
        [
            ("FOUNDRY_VERSION", "Foundry Version", "text", "e.g. 12.331 - leave blank to use the container image's default"),
            ("FOUNDRY_WORLD", "Auto-launch World", "text", "Leave blank to land on the setup screen"),
            ("FOUNDRY_LANGUAGE", "Language", "text", "Language code plus the module that provides its translation, e.g. en.core (the default) or fr.core"),
        ],
    ),
    (
        "Server identity & admin access",
        "The hostname Foundry's license is tied to, your license key, and the password for its own /setup screens.",
        [
            ("FOUNDRY_HOSTNAME", "Hostname", "text", "License is tied to this - avoid changing it after activation"),
            ("FOUNDRY_LICENSE_KEY", "License Key", "text",
             "From your foundryvtt.com Purchased Licenses page, e.g. K3OX-MWZR-AH18-ZJHQ-ZAMO-SLNY. Activates Foundry automatically on first boot - leave blank to enter it by hand in Foundry's own setup screen instead"),
            ("FOUNDRY_ADMIN_KEY", "Admin Key", "password", "Password for Foundry's /setup screens - set this before going live"),
        ],
    ),
    (
        "Your foundryvtt.com account",
        "Used only at container startup, to download the Foundry release tied to your license.",
        [
            ("FOUNDRY_USERNAME", "Foundry Account Username", "text", "Your foundryvtt.com account"),
            ("FOUNDRY_PASSWORD", "Foundry Account Password", "password", "Used only at startup to fetch your licensed release"),
        ],
    ),
    (
        "Cloudflare domain",
        "Connects the public domain players use to reach your server - see the Cloudflare Tunnel Setup guide for the full walkthrough.",
        [
            ("CLOUDFLARE_TUNNEL_TOKEN", "Tunnel Token", "password",
             "From the Cloudflare Zero Trust dashboard: Networks > Tunnels > your tunnel > install command, the value after --token"),
            ("PUBLIC_HOSTNAME", "Domain", "text",
             "The Public Hostname you set on the tunnel, e.g. play.yourdomain.com. Cosmetic here - it just lets the dashboard show/link it, it doesn't change the tunnel itself"),
        ],
    ),
]

EDITABLE_FIELDS = [field for _title, _subtitle, fields in SETTINGS_STEPS for field in fields]

# The subset of EDITABLE_FIELDS that requires recreating the cloudflared
# container (rather than foundry) to take effect. See save() in app.py.
CLOUDFLARE_FIELD_KEYS = {"CLOUDFLARE_TUNNEL_TOKEN", "PUBLIC_HOSTNAME"}

# Fields on the Foundry Settings wizard that must have a value - either
# already stored, or entered on this submission - before it can be saved.
# Just FOUNDRY_ADMIN_KEY for now: unlike the others, leaving it unset isn't a
# "use a sensible default" situation, it means Foundry's own /setup screens
# are left unprotected. Checked in save() in app.py the same way
# REQUIRED_ACCOUNT_FIELDS is checked in setup(); see settings.html for how
# this renders (required only shown/enforced when there's no current value,
# since blank on an already-configured password field means "keep current").
REQUIRED_SETTINGS_FIELDS = ("FOUNDRY_ADMIN_KEY",)

# Fields on the dashboard's Account & Recovery panel, and (for the required
# ones) the first-run setup wizard too; see app.py's setup(). Worded in
# plain language rather than SMTP jargon, since whoever sets this up may not
# be technical: it's just "which email sends the code, and where does it
# go." SMTP_FROM_ADDRESS is left out, since it already defaults to
# SMTP_USERNAME (see send_reset_email) and that covers most setups.
ACCOUNT_FIELDS = [
    ("ADMIN_UI_RECOVERY_EMAIL", "Your Email Address", "text",
     "Where we'll send a reset code if you ever get locked out. Use an email you can actually check - not the sending account below."),
    ("SMTP_USERNAME", "Sending Email Address", "text",
     "The email account that sends the reset code, e.g. yourname@gmail.com. Most people just use their own Gmail or Outlook address."),
    ("SMTP_PASSWORD", "Email App Password", "password",
     "Not your normal email password. Gmail and Outlook require a separate 16-character \"app password\" made just for this - "
     "search \"create an app password\" for your email provider to generate one."),
    ("SMTP_HOST", "Email Server (advanced)", "text",
     "Leave this as-is for Gmail. Only change it if you're using a different email provider and know its SMTP server address."),
    ("SMTP_PORT", "Email Server Port (advanced)", "text",
     "Leave this as-is unless your email provider's instructions say to use a different port."),
]

# Prefilled when these fields are still blank, so most people never have to
# think about them. Gmail's values are the common case and used as the default.
ACCOUNT_FIELD_DEFAULTS = {
    "SMTP_HOST": "smtp.gmail.com",
    "SMTP_PORT": "587",
}

# The subset of ACCOUNT_FIELDS that must be filled in before an account can
# be created, so "forgot password" is guaranteed to work later instead of
# leaving someone locked out with no way back in.
REQUIRED_ACCOUNT_FIELDS = ("ADMIN_UI_RECOVERY_EMAIL", "SMTP_USERNAME", "SMTP_PASSWORD")


def read_env() -> dict:
    # Compose treats a literal "$" in an env value as a variable reference,
    # so values are stored with "$" escaped as "$$" (see write_env). Undo
    # that here so the dashboard shows/edits the real value.
    return {k: v.replace("$$", "$") if v else v for k, v in dotenv_values(ENV_PATH).items()}


def write_env(values: dict) -> None:
    for key, value in values.items():
        set_key(ENV_PATH, key, value.replace("$", "$$"), quote_mode="never")


def apply_and_restart(service: str) -> tuple[bool, str]:
    """Recreate a single compose service with the current .env values (e.g.
    "foundry" after a Foundry Settings save, "cloudflared" after a tunnel
    token/domain change)."""
    result = subprocess.run(
        [
            "docker", "compose",
            "-f", COMPOSE_FILE,
            "--project-directory", PROJECT_DIR,
            "up", "-d", "--no-deps", service,
        ],
        capture_output=True, text=True, timeout=180,
    )
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode == 0, output.strip()


def _compose_ps_all() -> dict:
    """Returns {service: {"state": ..., "status": ..., "id": ...}} for every
    service in the project, from one `docker compose ps` call. Compose prints
    one JSON object per line (not a JSON array) for --format json."""
    try:
        result = subprocess.run(
            [
                "docker", "compose",
                "-f", COMPOSE_FILE,
                "--project-directory", PROJECT_DIR,
                "ps", "--format", "json",
            ],
            capture_output=True, text=True, timeout=15,
        )
        services = {}
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            services[entry["Service"]] = {
                "state": entry.get("State", "unknown"),
                "status": entry.get("Status", ""),
                "id": entry.get("ID", ""),
            }
        return services
    except Exception:
        return {}


def _normalize_state(state: str | None) -> str:
    """Normalized status for display: running / restarting / stopped / unknown."""
    if state == "running":
        return "running"
    if state == "restarting":
        return "restarting"
    if state in ("exited", "dead", "created", "paused"):
        return "stopped"
    return "unknown"


def get_service_status(service: str) -> str:
    return _normalize_state(_compose_ps_all().get(service, {}).get("state"))


def _uptime_from_id(container_id: str | None) -> str | None:
    """Human-readable elapsed time since a container last started."""
    if not container_id:
        return None
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.StartedAt}}", container_id],
            capture_output=True, text=True, timeout=10,
        )
        started_at = datetime.fromisoformat(result.stdout.strip())
        delta = datetime.now(timezone.utc) - started_at
        total_seconds = int(delta.total_seconds())
        if total_seconds < 0:
            return None
        days, rem = divmod(total_seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, _ = divmod(rem, 60)
        if days:
            return f"{days}d {hours}h"
        if hours:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"
    except Exception:
        return None


def _stats_from_id(container_id: str | None) -> dict | None:
    """Live CPU/memory for a container, via `docker stats`. This is the
    slowest call here since it needs ~1s to sample a CPU delta, so it's
    always fetched asynchronously via /api/metrics, never inline in a page
    render."""
    if not container_id:
        return None
    try:
        result = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", "{{json .}}", container_id],
            capture_output=True, text=True, timeout=15,
        )
        raw = json.loads(result.stdout.strip())
        mem_usage, _, mem_limit = raw.get("MemUsage", "").partition(" / ")
        net_rx, _, net_tx = raw.get("NetIO", "").partition(" / ")
        return {
            "cpu_percent": raw.get("CPUPerc", "?"),
            "mem_usage": mem_usage.strip(),
            "mem_limit": mem_limit.strip(),
            "mem_percent": raw.get("MemPerc", "?"),
            "net_rx": net_rx.strip(),
            "net_tx": net_tx.strip(),
        }
    except Exception:
        return None


def get_dashboard_metrics() -> dict:
    """Everything the dashboard's metric cards need, in one pass. A single
    `docker compose ps` covers both services' status instead of the four
    separate subprocess calls this used to take, which is what made the
    dashboard slow to open. Called only from /api/metrics, fetched
    asynchronously after the page is already on screen."""
    services = _compose_ps_all()
    foundry = services.get("foundry", {})
    cloudflared = services.get("cloudflared", {})
    return {
        "foundry_status": _normalize_state(foundry.get("state")),
        "foundry_uptime": _uptime_from_id(foundry.get("id")),
        "foundry_stats": _stats_from_id(foundry.get("id")),
        "tunnel_status": _normalize_state(cloudflared.get("state")),
        "public_hostname": get_public_hostname(),
        "nginx_stats": get_nginx_stats(),
    }


_STUB_STATUS_RE = re.compile(
    r"Active connections:\s*(\d+).*?"
    r"(\d+)\s+(\d+)\s+(\d+).*?"
    r"Reading:\s*(\d+)\s+Writing:\s*(\d+)\s+Waiting:\s*(\d+)",
    re.DOTALL,
)


def get_nginx_stats() -> dict | None:
    """Real traffic counters from nginx's stub_status module (see
    nginx/conf.d/status.conf): total requests/connections proxied since
    nginx last started, covering both the Foundry and admin vhosts combined.
    Not reachable outside the Docker network, so this call only ever
    happens container-to-container."""
    try:
        with urllib.request.urlopen("http://nginx:8081/nginx_status", timeout=3) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        match = _STUB_STATUS_RE.search(body)
        if not match:
            return None
        active, accepts, handled, requests, reading, writing, waiting = match.groups()
        return {
            "active_connections": int(active),
            "accepts": int(accepts),
            "handled": int(handled),
            "requests": int(requests),
            "reading": int(reading),
            "writing": int(writing),
            "waiting": int(waiting),
        }
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None


def get_public_hostname() -> str | None:
    """Cloudflare Tunnel has no local API to query the live public hostname
    (unlike ngrok's :4040 API); the mapping lives in the Cloudflare Zero
    Trust dashboard. This just echoes back the PUBLIC_HOSTNAME the user
    recorded in .env for their own reference on the dashboard."""
    return read_env().get("PUBLIC_HOSTNAME") or None


# --- Account setup -----------------------------------------------------

def is_account_configured() -> bool:
    env = read_env()
    return bool(env.get("ADMIN_UI_USERNAME")) and bool(env.get("ADMIN_UI_PASSWORD_HASH"))


def get_or_create_secret_key() -> str:
    """Returns FLASK_SECRET_KEY from .env, generating and persisting one on
    first run so sessions survive restarts without any manual setup step."""
    existing = read_env().get("FLASK_SECRET_KEY")
    if existing:
        return existing
    new_key = token_hex(32)
    write_env({"FLASK_SECRET_KEY": new_key})
    return new_key


def create_account(username: str, password: str) -> None:
    write_env({
        "ADMIN_UI_USERNAME": username,
        "ADMIN_UI_PASSWORD_HASH": generate_password_hash(password),
    })


def update_password(new_password: str) -> None:
    write_env({"ADMIN_UI_PASSWORD_HASH": generate_password_hash(new_password)})


# --- Password reset via email -------------------------------------------

_RESET_CODE_TTL_SECONDS = 15 * 60
_RESET_MAX_ATTEMPTS = 5
_RESET_SEND_COOLDOWN_SECONDS = 60

# In-memory only, deliberately not persisted to .env or disk: config-ui runs
# as a single Flask process (app.run(), no multi-worker server), so this is
# safe, and it means a live reset code never ends up sitting in a file.
_reset_state = {"code": None, "expires_at": 0.0, "attempts": 0, "last_sent_at": 0.0}


def reset_send_cooldown_remaining() -> int:
    """Seconds until another code can be requested. Anyone who can reach
    /forgot-password - which now includes the public internet, if an admin
    subdomain is routed through the Cloudflare Tunnel, see
    docs/cloudflare-tunnel-setup.md - could otherwise mash "send code"
    repeatedly and spam the recovery inbox or probe the endpoint. Returns 0
    if a new send is allowed right now."""
    remaining = _reset_state["last_sent_at"] + _RESET_SEND_COOLDOWN_SECONDS - time.time()
    return max(0, int(remaining))


def start_reset() -> str:
    code = token_hex(4)
    _reset_state.update(code=code, expires_at=time.time() + _RESET_CODE_TTL_SECONDS, attempts=0)
    return code


def mark_reset_sent() -> None:
    """Starts the resend cooldown. Only called after a real send succeeds,
    so a misconfigured SMTP attempt (wrong password, etc.) doesn't lock you
    out of retrying once it's fixed."""
    _reset_state["last_sent_at"] = time.time()


def verify_reset(submitted_code: str) -> bool:
    if not _reset_state["code"] or time.time() > _reset_state["expires_at"]:
        return False
    if _reset_state["attempts"] >= _RESET_MAX_ATTEMPTS:
        return False
    _reset_state["attempts"] += 1
    if submitted_code.strip() == _reset_state["code"]:
        clear_reset()
        return True
    return False


def clear_reset() -> None:
    _reset_state.update(code=None, expires_at=0.0, attempts=0)


# --- Login throttling ---------------------------------------------------

_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_LOCKOUT_SECONDS = 15 * 60

# In-memory only, same reasoning as _reset_state above (single Flask
# process, resets on restart - acceptable since this only needs to survive
# one bad actor's session, not forever). Keyed by client IP so one bad actor
# doesn't lock out anyone else, e.g. players on the same vhost's tunnel path.
_login_attempts: dict[str, list[float]] = {}


def login_lockout_remaining(ip: str) -> int:
    """Seconds until `ip` may attempt another login. This is what stands
    between the login form and a brute-force script now that the admin UI
    can be reached from the internet."""
    now = time.time()
    attempts = [t for t in _login_attempts.get(ip, []) if now - t < _LOGIN_LOCKOUT_SECONDS]
    _login_attempts[ip] = attempts
    if len(attempts) < _LOGIN_MAX_ATTEMPTS:
        return 0
    return max(0, int(attempts[0] + _LOGIN_LOCKOUT_SECONDS - now))


def record_failed_login(ip: str) -> None:
    _login_attempts.setdefault(ip, []).append(time.time())


def clear_login_attempts(ip: str) -> None:
    _login_attempts.pop(ip, None)


def recovery_is_configured() -> bool:
    env = read_env()
    return bool(env.get("ADMIN_UI_RECOVERY_EMAIL")) and bool(env.get("SMTP_HOST")) and bool(env.get("SMTP_USERNAME"))


def _reset_email_plaintext(code: str) -> str:
    """Plain-text fallback part of the email, for clients that don't render
    HTML."""
    return (
        f"Your Foundry Admin password reset code is:\n\n{code}\n\n"
        f"This code expires in 15 minutes and can only be used once."
    )


def _reset_email_html(code: str) -> str:
    """HTML part of the reset email: same facts as the plain-text version
    above (same code, same 15-minute/single-use expiry), just formatted.
    Inline styles and table layout throughout since that's what renders
    consistently across email clients, and the logo is attached inline via
    Content-ID rather than linked, so nothing is fetched over the network."""
    return f"""\
<!doctype html>
<html>
<body style="margin:0; padding:32px 16px; background:#f4f5f7; font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" style="max-width:480px; background:#ffffff; border-radius:8px;" cellpadding="0" cellspacing="0">
          <tr>
            <td style="padding:32px 40px 20px;">
              <img src="cid:{LOGO_CID}" width="40" height="40" alt="" style="display:block; margin-bottom:10px;">
              <span style="font-size:20px; font-weight:700; color:#7c5cff;">Foundry Admin</span>
            </td>
          </tr>
          <tr><td style="padding:0 40px;"><hr style="border:none; border-top:1px solid #e2e4e9; margin:0;"></td></tr>
          <tr>
            <td style="padding:28px 40px 0; color:#3c4257; font-size:15px; line-height:1.6; font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
              Hello,
            </td>
          </tr>
          <tr>
            <td style="padding:12px 40px 0; color:#3c4257; font-size:15px; line-height:1.6; font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
              We received a request to reset the password for your Foundry Admin dashboard. No changes have been made to your account yet.
            </td>
          </tr>
          <tr>
            <td style="padding:12px 40px 0; color:#3c4257; font-size:15px; line-height:1.6; font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
              Enter this code on the reset password page to continue:
            </td>
          </tr>
          <tr>
            <td style="padding:20px 40px 0;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f5f7; border:1px solid #e2e4e9; border-radius:8px;">
                <tr>
                  <td align="center" style="padding:20px;">
                    <span style="font-family:Consolas,'SFMono-Regular',Menlo,monospace; font-size:26px; font-weight:700; letter-spacing:4px; color:#1a1d23;">{code}</span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:20px 40px 0; color:#3c4257; font-size:15px; line-height:1.6; font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
              This code expires in 15 minutes and can only be used once.
            </td>
          </tr>
          <tr>
            <td style="padding:12px 40px 32px; color:#3c4257; font-size:15px; line-height:1.6; font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
              If you didn't request this, you can safely ignore this email - your password won't be changed.
            </td>
          </tr>
          <tr><td style="padding:0 40px;"><hr style="border:none; border-top:1px solid #e2e4e9; margin:0;"></td></tr>
          <tr>
            <td style="padding:20px 40px 32px; color:#8a94a6; font-size:12px; line-height:1.5; font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
              Sent from your self-hosted Foundry Admin panel.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


def send_reset_email(code: str) -> tuple[bool, str]:
    env = read_env()
    to_addr = env.get("ADMIN_UI_RECOVERY_EMAIL")
    host = env.get("SMTP_HOST")
    username = env.get("SMTP_USERNAME")
    password = env.get("SMTP_PASSWORD")
    from_addr = env.get("SMTP_FROM_ADDRESS") or username
    try:
        port = int(env.get("SMTP_PORT") or 587)
    except ValueError:
        return False, f"SMTP_PORT is not a valid number: {env.get('SMTP_PORT')!r}"

    if not (to_addr and host and username):
        return False, "Recovery email/SMTP settings aren't fully configured yet."

    from email.mime.image import MIMEImage
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    import smtplib

    # multipart/related wrapping multipart/alternative: a plain-text
    # fallback alongside the styled HTML version (with its inline logo),
    # for clients that don't render HTML.
    alternative = MIMEMultipart("alternative")
    alternative.attach(MIMEText(_reset_email_plaintext(code), "plain"))
    alternative.attach(MIMEText(_reset_email_html(code), "html"))

    message = MIMEMultipart("related")
    message.attach(alternative)
    try:
        with open(LOGO_PATH, "rb") as f:
            logo = MIMEImage(f.read())
        logo.add_header("Content-ID", f"<{LOGO_CID}>")
        logo.add_header("Content-Disposition", "inline", filename="foundry-admin-logo.png")
        message.attach(logo)
    except OSError:
        pass  # missing logo asset shouldn't block a password reset

    message["Subject"] = "Foundry Admin password reset code"
    message["From"] = from_addr
    message["To"] = to_addr

    try:
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.starttls()
            server.login(username, password)
            server.sendmail(from_addr, [to_addr], message.as_string())
        return True, ""
    except smtplib.SMTPAuthenticationError as exc:
        if b"application-specific password required" in exc.smtp_error.lower() or "invalidsecondfactor" in str(exc).lower():
            return False, (
                "Gmail rejected the regular password - it requires an App Password instead. "
                "Create one at https://myaccount.google.com/apppasswords and paste it into "
                "\"Email App Password\" (not your normal Gmail password)."
            )
        return False, str(exc)
    except Exception as exc:
        return False, str(exc)
