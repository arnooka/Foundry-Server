# Cloudflare Tunnel Setup

Players reach your Foundry server through a Cloudflare Tunnel: `nginx:80`
(the Foundry vhost only, see [Architecture](architecture.md)) is exposed to
the internet at a stable HTTPS URL on a domain you own, without opening any
ports on your router or needing a public IP.

## Why Cloudflare Tunnel instead of ngrok

This stack originally used ngrok's free static domain. That works, but
ngrok's free plan caps out at **1GB of data transfer and 20k requests per
month**. Foundry pushes map images, tokens, and audio to every connected
client, and a single real session can plausibly exceed that - at which point
the tunnel stops working entirely until the next monthly reset.

Cloudflare Tunnel's free tier has no such cap: no bandwidth limit, no
request-count limit, and no expiring or rotating domain to manage, as long
as you already have (or are willing to register) a domain and point its DNS
to Cloudflare. The one real limitation worth knowing: Cloudflare's proxy
caps **individual file uploads at 100MB**, a general constraint on proxied
traffic and not specific to Tunnel. That only matters if a GM uploads an
unusually large map image or long audio file through Foundry's file
manager; it's irrelevant for normal play.

## Prerequisites

- A domain name you own (any registrar). If you don't have one, you'll need
  to buy one. This is the one genuinely unavoidable cost in this setup,
  typically ~$10-15/year, and it's a domain registration fee, not a
  Cloudflare charge.
- A free [Cloudflare](https://dash.cloudflare.com/sign-up) account.

## Setup steps

1. **Add your domain to Cloudflare** (free plan): in the Cloudflare
   dashboard, "Add a site," enter your domain, and follow the prompts. You'll
   be given two nameservers to set at your domain registrar, replacing
   whatever nameservers it uses today. This can take anywhere from a few
   minutes to a few hours to propagate.

2. **Create a tunnel:** in the Cloudflare dashboard, go to
   **Zero Trust** → **Networks** → **Tunnels** → **Create a tunnel**, choose
   the **Cloudflared** connector type, and give it a name (e.g.
   `foundry-server`).

3. **Copy the tunnel token.** The setup page shows an install command
   containing a long token string after `--token`. Copy just the token value
   and put it in `.env` as `CLOUDFLARE_TUNNEL_TOKEN`.

4. **Add a Public Hostname** on the tunnel (same setup page, or
   Tunnels → your tunnel → **Public Hostname** tab):
   - **Subdomain / Domain:** whatever you want players to type, e.g.
     `dndwithfriends.com` or `play.dndwithfriends.com`.
   - **Service:** Type `HTTP`, URL `nginx:80`. This is the internal Docker
     service name and port; `cloudflared` reaches it over the
     `foundry-net` Docker network the same way `nginx` reaches `foundry`.
     See [Architecture](architecture.md#the-containers).

5. **(Optional) record it for the dashboard:** set `PUBLIC_HOSTNAME` in
   `.env` to the hostname you chose in step 4, purely so the admin UI's
   dashboard can show/link it. This is cosmetic only; it doesn't affect the
   actual tunnel.

6. **Start (or restart) the stack:**
   ```
   docker compose up -d
   ```

7. **Confirm the tunnel is live.** Either the tunnel's status in the
   Cloudflare dashboard should show "Healthy," or check:
   ```
   docker compose logs cloudflared
   ```
   A successful connection logs lines like
   `Registered tunnel connection ... connIndex=0`.

## Sharing it with players

Give players the hostname you configured in step 4 directly, as a normal
`https://` URL. Cloudflare terminates TLS automatically, so no port number
is needed. It doesn't change across restarts; there's nothing to re-share
unless you deliberately reconfigure the Public Hostname.

## What the tunnel can and can't see

By default, `cloudflared` only knows about the one Public Hostname →
`http://nginx:80` mapping you created in step 4. It has no route to
`nginx:8080` (the admin vhost) at all, because that port was never
configured as a destination. See
[Architecture](architecture.md#why-two-nginx-vhosts-not-one) for the full
reasoning behind keeping the admin UI off any public path by default.

## Exposing the admin UI (optional)

You can add a second Public Hostname on the same tunnel - e.g.
`admin.yourdomain.com` → Service `HTTP`, URL `nginx:8080` - to reach the
admin UI without being on the LAN. Nothing else needs to change: `admin.conf`
already has its own vhost and login, and `cloudflared` can already reach
`nginx:8080` over the `foundry-net` Docker network regardless of the host
port mapping.

Do this deliberately, though: `config-ui` holds the Docker socket (see
[Architecture](architecture.md#why-config-ui-needs-the-docker-socket)), so
its login is effectively the only thing between the internet and full
control of this host. The app has its own defenses - CSRF tokens, a
per-IP login lockout, rate limiting at the nginx layer - but none of that
is a substitute for the two things below:

1. **Put a Cloudflare Access policy in front of the admin hostname.** This
   gates the request *before* it ever reaches nginx or Flask - a stolen or
   brute-forced admin password alone isn't enough to get in.

   In the Cloudflare dashboard: **Zero Trust** → **Access controls** →
   **Applications** → **Add an application** → **Self-hosted and private**
   → **Public DNS** tab → **Continue with Self-hosted and private**.
   - **Destinations:** under Public hostnames, enter the admin subdomain
     (e.g. `admin`) and pick your domain - this should match the Public
     Hostname you already created on the tunnel, not a new one.
   - **Access policies:** click **Create new policy**. Give it any name
     (e.g. `Admins only`), leave **Action** as `Allow`, and under the
     **Include** rule set the selector to `Emails` and the value to your own
     email address. Add another `Emails` include rule per person if more
     than one of you needs access - matching any one rule is enough to get
     in. Save the policy.
   - **Authentication:** the defaults (accept all available identity
     providers) are fine - Cloudflare will email a one-time PIN to whatever
     address the visitor enters, and only the email(s) from your policy
     above will be let through.
   - **Details:** name it whatever you like, and optionally shorten
     **Session Duration** from the 24-hour default if you want to be
     re-prompted more often.
   - Click **Create**.

   Once saved, visiting the admin hostname prompts for that email + PIN
   first; only after that does the request reach the Foundry Admin UI's own
   username/password login, unchanged.
2. **Use a strong, unique admin password**, and keep `.env` off any machine
   or backup you don't fully control - it holds `ADMIN_UI_PASSWORD_HASH`,
   `FLASK_SECRET_KEY` (which can forge a logged-in session if it leaks), and
   your `CLOUDFLARE_TUNNEL_TOKEN`. It's already excluded via `.gitignore`;
   don't paste its contents anywhere, including into chat tools or issue
   trackers.

If you'd rather not manage an Access policy, leave the admin UI on the LAN
side only and use `docker compose exec`/SSH to your host when you need it
remotely - the port-8080-never-a-tunnel-destination default is the safer
choice for anyone who doesn't need remote admin access often.
