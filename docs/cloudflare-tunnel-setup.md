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

`cloudflared` only knows about the one Public Hostname → `http://nginx:80`
mapping you created in step 4. It has no route to `nginx:8080` (the admin
vhost) at all, because that port was never configured as a destination. See
[Architecture](architecture.md#why-two-nginx-vhosts-not-one) for the full
reasoning behind keeping the admin UI off any public path.
