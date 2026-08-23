# Architecture

This stack is five containers on one Docker Compose project, wired so that
Foundry's game traffic and the admin tooling never share a path.

```
Players (internet) --> Cloudflare Tunnel (your domain, TLS) --> nginx:80   --> foundry:30000
You (LAN only)                                              --> nginx:8080 --> config-ui:5000 (Flask)
                                                                                  |
                                                                    writes .env + Docker socket
                                                                                  v
                                                                      recreates the `foundry` service
```

## The containers

| Container     | Image                                | Role |
|---------------|---------------------------------------|------|
| `foundry`     | `ghcr.io/felddy/foundryvtt`            | Runs Foundry VTT itself. Config is entirely env-var driven; see [Configuration Reference](configuration.md). |
| `nginx`       | `nginx:stable-alpine`                  | Reverse proxy, with two independent server blocks (vhosts), one per audience. See below. |
| `config-ui`   | built from `config-ui/`                | Flask app, the admin dashboard you're reading this in. Edits `.env` and recreates the `foundry` container. |
| `cloudflared` | `cloudflare/cloudflared`               | Opens the public tunnel that gives players a stable HTTPS URL on your own domain, with no bandwidth cap. |

They share one Docker network (`foundry-net`) and talk to each other by
service name; Docker's embedded DNS resolves `foundry`, `nginx`, `config-ui`,
and `cloudflared` for you. Nothing here is reachable by IP address, and
nothing except `nginx`'s two published ports is reachable from outside the
Docker network at all.

## Why two nginx vhosts, not one

[`nginx/conf.d/foundry.conf`](../nginx/conf.d/foundry.conf) listens on port 80
and proxies to `foundry:30000`, with WebSocket upgrade headers. Foundry's
canvas and chat rely on a persistent WebSocket connection, so this is the one
nginx setting that will silently break the whole app if it's missing.

[`nginx/conf.d/admin.conf`](../nginx/conf.d/admin.conf) listens on port 8080
and proxies to `config-ui:5000`. No WebSocket handling or special timeouts
needed; it's a plain admin form.

Splitting these into two vhosts/ports, rather than one nginx server routing
by path (e.g. `/admin`), enforces the separation structurally: **only port 80
is ever configured as a Cloudflare Tunnel destination.** Port 8080 has no
code path that reaches the public internet. It's not a permissions check
that could have a bug in it; it's a tunnel that was simply never told that
port exists. See [Admin UI Guide](admin-ui-guide.md) for what this means for
you day to day, and don't forward port 8080 through your router. Keep it
LAN-only.

## Why `config-ui` needs the Docker socket

Foundry's own settings (admin key, version, credentials, hostname...) are
read from environment variables at container startup, and there's no way to
change them on a running container. So "change a setting" necessarily means
"recreate the `foundry` container with new environment variables."

`config-ui` does this by:

1. Writing the new values into the shared `.env` file (bind-mounted into it
   at `/workspace/.env`, same file `docker-compose.yml` uses).
2. Running `docker compose up -d --no-deps foundry` via the Docker CLI,
   which it can do because `/var/run/docker.sock` is bind-mounted into it
   too. That socket is a direct line to the *host's* Docker engine, not a
   sandboxed one inside the container.

This is the standard "Docker-outside-of-Docker" pattern. One consequence is
worth knowing: **`config-ui` can, in principle, control any container on
your host, not just `foundry`**, since the socket doesn't scope access to
one Compose project. That's why it's not exposed to the internet (see
above).

A second consequence shaped how `foundry`'s data is stored. Bind-mount paths
in a compose file are resolved by whichever client issues the `docker
compose` command, relative to *its own* filesystem. `config-ui`'s copy of
that command runs from inside its own container, where a path like
`./foundry-data` would mean `/workspace/foundry-data` - meaningless to the
*host* Docker engine actually asked to create the mount. Rather than manage
a host path manually, `foundry-data` is a named Docker volume instead of a
bind mount: named volumes resolve by name, not by client-relative path, so
`config-ui`'s in-container `docker compose` and your own host shell always
agree on where it points.

## Why the Compose project name is pinned

`docker-compose.yml` starts with `name: foundry-server`. Compose normally
derives the project name from the directory it's run in, but `config-ui`
runs its `docker compose` commands from `/workspace` (its own mount point),
which would otherwise resolve to a different project name than the one
created when *you* ran `docker compose up` from the repo root on the host.
Pinning the name keeps both invocations pointed at the same containers
regardless of which path they're run from.

## Data persistence

Foundry's worlds, modules, systems, and its own config live in the
`foundry-data` named Docker volume, mounted to `/data` in the `foundry`
container (see above for why it's a named volume rather than a folder in
this repo). It's the one thing you actually need to back up; everything
else here is reproducible from the compose file and `.env`. To back it up:
`docker run --rm -v foundry-server_foundry-data:/data -v "$PWD":/backup alpine tar czf /backup/foundry-data.tar.gz -C / data`
(volume name may differ if you renamed the compose project; check with
`docker volume ls`).

## No `.env` required to start

All three services' `env_file: - .env` entries are marked `required: false`
(a Compose Specification feature), so `docker compose up -d` succeeds even
when `.env` doesn't exist at all - every `${VAR}` reference in
`docker-compose.yml` just falls back to its default or an empty string.
That's what makes the first-run setup wizard possible: `config-ui` comes up
with no credentials configured, detects that, and serves `/setup` instead of
crashing or showing an unusable login form. See
[Admin UI Guide: First-run setup](admin-ui-guide.md#first-run-setup).

## The two version knobs

The stack tracks two independent things that are easy to conflate:

- `FOUNDRY_CONTAINER_TAG`: which build of the *felddy/foundryvtt-docker*
  image/entrypoint you're running (e.g. `release`, `13`).
- `FOUNDRY_VERSION`: which actual *Foundry VTT software* version the
  entrypoint downloads inside that container (e.g. `12.331`).

They're kept as separate variables, rather than one as the upstream image's
own example suggests, because passing an image alias like `release` as
`FOUNDRY_VERSION` makes the entrypoint log a version-mismatch warning: it
expects a concrete version number there. See
[Configuration Reference](configuration.md#foundry-vtt) for details.
