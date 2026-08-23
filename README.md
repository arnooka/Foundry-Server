# Foundry VTT Self-Hosted Stack

A self-hosted, containerized Foundry VTT server for running games with friends.

- **Foundry VTT** runs in Docker ([`felddy/foundryvtt-docker`](https://github.com/felddy/foundryvtt-docker)), configured entirely through environment variables.
- A small **local admin UI** (Flask) lets you change Foundry's settings (version, admin key, credentials, hostname, auto-launch world) from a browser instead of the command line.
- **nginx** sits in front of both, keeping game traffic and admin traffic on separate ports so they can't cross paths.
- **Cloudflare Tunnel** hands out a free, unlimited-bandwidth, SSL-secured public URL on your own domain. No paid plan needed.

## Architecture

```
Players (internet) -> Cloudflare Tunnel (your domain, TLS) -> nginx:80  -> foundry:30000
You (LAN only)                                              -> nginx:8080 -> config-ui:5000 (Flask)
                                                                                  |
                                                                    writes .env + docker socket
                                                                                  v
                                                                      recreates `foundry` service
```

The admin UI is never exposed through the tunnel. Only port 80 (Foundry) is configured as a tunnel destination; port 8080 (admin) stays reachable on your local network only. Full write-up: [docs/architecture.md](docs/architecture.md).

## Documentation

This README covers getting started. Everything else lives in [`docs/`](docs/),
and the same Markdown files are also browsable inside the admin UI itself
(the **Docs** tab, once the stack is running).

| Doc | Covers |
|-----|--------|
| [Architecture](docs/architecture.md) | Why five containers, the two nginx vhosts, the Docker-socket pattern, data persistence, the two version knobs |
| [Configuration Reference](docs/configuration.md) | Every `.env` variable, what it does, and its default |
| [Admin UI Guide](docs/admin-ui-guide.md) | First-run setup, forgot-password recovery, what's on the dashboard, what Save & Restart does |
| [Cloudflare Tunnel Setup](docs/cloudflare-tunnel-setup.md) | Adding your domain to Cloudflare, creating the tunnel, why it beats ngrok's free tier here |
| [Troubleshooting](docs/troubleshooting.md) | Fixes for the specific errors you're most likely to hit |

## Prerequisites

- Docker Desktop (with Compose v2 built in)
- A [Foundry VTT](https://foundryvtt.com/) account with a purchased license
- A domain name you own, and a free [Cloudflare](https://dash.cloudflare.com/sign-up) account

## Setup

You don't need to create a `.env` file by hand. `docker compose up` works fine with none present.

1. **Start the stack:**

   ```
   docker compose up -d --build
   ```

2. **Open the admin UI** at `http://localhost:8080` (or `http://<your-lan-ip>:8080`
   from another device on your network). A clean start lands on a
   **Create your admin account** page instead of a login form: pick a
   username, password, and optionally a recovery email (for "forgot
   password" later), right there in the browser. This writes `.env` for you,
   nothing to copy or hand-edit.

3. **Configure Foundry** from the dashboard's Foundry Settings wizard: version, admin key, your
   foundryvtt.com account credentials, hostname, auto-launch world. Finishing the wizard
   rewrites `.env` and recreates the `foundry` container.

4. **Set up your Cloudflare Tunnel** so players can reach it:
   - Add your domain to Cloudflare (free plan) and point its nameservers there.
   - Create a tunnel in the Zero Trust dashboard (Networks → Tunnels), add a Public Hostname pointing at `http://nginx:80`.
   - Full walkthrough: [docs/cloudflare-tunnel-setup.md](docs/cloudflare-tunnel-setup.md). It gets players a stable HTTPS URL on your own domain with no bandwidth cap.
   - Paste the tunnel token and domain into the Foundry Settings wizard's last step, **Cloudflare domain**. Saving rewrites `.env` and recreates the `cloudflared` container to pick it up; no manual `docker compose up -d` needed.

5. **Share the public hostname** you configured in Cloudflare (also shown on the admin dashboard, from the Cloudflare domain step above) with your players.

Stuck at any point? The **Docs** tab in the admin UI has the full reference documentation.

## Notes

- Foundry's persistent data (worlds, modules, config) lives in the `foundry-data` named Docker volume. Back it up before major changes (see [docs/architecture.md](docs/architecture.md#data-persistence) for the backup command).
- Foundry ties license activation to the container's `hostname` (`FOUNDRY_HOSTNAME`). Avoid changing it once you've activated.
- `.env` holds real credentials and secrets. It's gitignored, and it should stay that way.
- Keep port 8080 off any router port-forward or UPnP rule; it's meant to stay LAN-only. Only port 80 should ever be reachable from the internet, and only through the Cloudflare Tunnel.
- Don't want to store your foundryvtt.com password in `.env`? Leave `FOUNDRY_USERNAME`/`FOUNDRY_PASSWORD` blank and set `FOUNDRY_RELEASE_URL` instead: a temporary presigned download link from your Foundry account page. See the [felddy/foundryvtt-docker docs](https://github.com/felddy/foundryvtt-docker) for how to get one.
- Forgot your admin UI password? Use the **Forgot password?** link on the login page if you set up recovery email, or see [docs/troubleshooting.md](docs/troubleshooting.md#im-locked-out-and-never-set-up-email-recovery) for the manual fallback.
