# Troubleshooting

General first step for anything below: `docker compose ps` to see container
status, and `docker compose logs <service>` (`foundry`, `nginx`, `config-ui`,
or `cloudflared`) to see why.

## Foundry container keeps restarting / "Unable to install Foundry Virtual Tabletop!"

```
foundry-1 | [error] Unable to install Foundry Virtual Tabletop!
foundry-1 | [error] Either set FOUNDRY_RELEASE_URL.
foundry-1 | [error] Or set FOUNDRY_USERNAME and FOUNDRY_PASSWORD.
foundry-1 | [error] Or set CONTAINER_CACHE to a directory containing foundryvtt-*.zip
```

Expected if `FOUNDRY_USERNAME`/`FOUNDRY_PASSWORD` are blank or wrong: the
container has no way to fetch the actual Foundry software. Set real
credentials (or `FOUNDRY_RELEASE_URL`) in `.env` or through the dashboard,
then Save & Restart. The container retries with a backoff, so it's safe to
leave running while you fix credentials.

## "FOUNDRY_VERSION has been manually set and does not match the container's version"

```
foundry-1 | [warn] FOUNDRY_VERSION has been manually set and does not match the container's version.
foundry-1 | [warn] Expected 14.367 but found <something>
```

Harmless, but two common causes:

- You put an image alias like `release` in `FOUNDRY_VERSION`. That field
  wants a concrete version number (e.g. `12.331`), or should be left blank;
  the image tag alias goes in `FOUNDRY_CONTAINER_TAG` instead. See
  [Configuration Reference](configuration.md#foundry-vtt).
- You left `FOUNDRY_VERSION` blank. Compose still defines the variable as an
  empty string rather than leaving it fully unset, which the entrypoint's
  version check treats as "manually set." This is cosmetic; Foundry installs
  its default version regardless.

## A value with a `$` in it got corrupted

Symptom: a password, hash, or key that had a `$` in it comes out truncated or
missing a chunk after being saved to `.env`, and `docker compose` logs a
warning like:

```
level=warning msg="The \"SomeText\" variable is not set. Defaulting to a blank string."
```

This is Docker Compose's variable interpolation treating `$SomeText` inside
your value as a reference to an (undefined) variable named `SomeText`, and
blanking it out. Compose's escape rule is to write a literal `$` as `$$`.

- Anything you edit **through the dashboard** already handles this for you
  (escaped on save, un-escaped when displayed).
- Anything you edit **by hand in `.env`** needs the `$$` doubling done
  yourself. The most likely case is `ADMIN_UI_PASSWORD_HASH` if you're
  resetting it manually (see
  [below](#im-locked-out-and-never-set-up-email-recovery)), since werkzeug
  hashes always contain `$`.

## cloudflared won't connect / tunnel shows "Down" in the dashboard

```
cloudflared-1 | failed to sufficiently increase receive buffer size
cloudflared-1 | Unauthorized: Failed to create new quic connection
```
or the container just restarts repeatedly. `CLOUDFLARE_TUNNEL_TOKEN` is
missing, wrong, or was copied incompletely. Re-copy the token from the
Cloudflare Zero Trust dashboard (Networks → Tunnels → your tunnel → the
install-command page) and set it in `.env`, then
`docker compose up -d --force-recreate cloudflared`. See
[Cloudflare Tunnel Setup](cloudflare-tunnel-setup.md).

## Public hostname loads a Cloudflare error page (1016, 522, or similar)

Usually one of:

- **DNS hasn't finished propagating** after adding your domain to Cloudflare
  or adding the Public Hostname. Can take a few minutes to a few hours.
- **The Public Hostname's Service URL is wrong**: double check it's exactly
  `http://nginx:80` (Type `HTTP`), matching the internal Docker service name,
  not `localhost` or an external IP.
- **`cloudflared` isn't actually running**: check
  `docker compose ps cloudflared` and its logs.

## A file upload to Foundry fails around 100MB

Cloudflare's proxy caps individual file uploads at ~100MB on the free plan.
This applies to any traffic proxied through Cloudflare, including Tunnel,
and isn't something this stack's config controls. It only affects unusually
large single files, like a big map image or an uncompressed audio track;
compressing the asset or splitting it is the practical workaround. See
[Cloudflare Tunnel Setup](cloudflare-tunnel-setup.md#why-cloudflare-tunnel-instead-of-ngrok).

## Players connect but the game is stuck loading / chat doesn't update

Usually a WebSocket proxying issue. Foundry needs a persistent WebSocket
connection through the whole chain (browser → Cloudflare → nginx → foundry).
If you've modified [`nginx/conf.d/foundry.conf`](../nginx/conf.d/foundry.conf),
make sure it still has:

```nginx
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection $connection_upgrade;
```

## Admin UI container won't start

Check `docker compose logs config-ui`. The most likely cause if you've
customized the compose file: **`can't open file '/app/app.py'`** or similar
path errors. That usually means the container's working directory got
changed away from the Dockerfile's `WORKDIR` (e.g. by adding a `working_dir:`
override in `docker-compose.yml`). `services/docker_control.py` uses
absolute paths for every `docker compose` call specifically so this
container never needs its own working directory changed; leave it alone if
you're customizing the compose file.

## I'm locked out and never set up email recovery

If you never configured `ADMIN_UI_RECOVERY_EMAIL`/SMTP (so
[Forgot password?](admin-ui-guide.md#forgot-your-password) isn't available)
and can't remember your password, reset it directly:

1. Open `.env` and delete the `ADMIN_UI_USERNAME` and `ADMIN_UI_PASSWORD_HASH`
   lines entirely, not just blank them out (see
   [Configuration Reference](configuration.md#admin-ui-account)).
2. `docker compose up -d --force-recreate config-ui` from the host.
3. Open `http://localhost:8080`. With no account configured, it serves the
   first-run `/setup` page again instead of a login form. Create a new
   account the same way you did the first time.

This doesn't touch any Foundry settings, only the admin UI's own login.

## Reset email never arrives

Check `docker compose logs config-ui` right after clicking **Send reset
code** on `/forgot-password`; a failed send flashes the underlying error on
the page too. Common causes:

- **Wrong SMTP port/host, or a regular password instead of an app
  password**: for Gmail specifically, `SMTP_PASSWORD` must be an
  [App Password](https://myaccount.google.com/apppasswords). Your normal
  account password will be rejected if 2FA is enabled, which Gmail now
  largely requires.
- **Port 465 (implicit TLS) instead of 587**: only STARTTLS on 587 is
  supported. See [Configuration Reference](configuration.md#password-reset-via-email).
- **Landed in spam**: check there before assuming the send failed.

## "Save & Restart" fails, or changes don't seem to apply

The flash message on the dashboard includes the raw output from the `docker
compose` command it ran; that's the first place to look. The most likely
underlying cause is a **Docker socket not reachable** error. On Windows,
confirm Docker Desktop is running and its Linux-container backend is what's
running this stack (WSL2 or Hyper-V backend both work; Windows containers
mode does not, since `/var/run/docker.sock` won't exist the same way).

## Foundry asks me to re-activate my license after I changed a setting

Foundry ties license activation to `FOUNDRY_HOSTNAME`. If you changed it
after already activating, that's expected: either change it back or
re-activate against the new hostname. See
[Configuration Reference](configuration.md#foundry_hostname).

## Port 80 or 8080 is already in use

Something else on your machine (IIS, Skype, another dev server, a previous
run of this stack, etc.) is bound to the same port. Stop the other process,
or change the left-hand side of the `ports:` mapping for `nginx` in
`docker-compose.yml` (e.g. `8081:8080` for the admin UI); just remember to
update the URL you use to reach it accordingly.
