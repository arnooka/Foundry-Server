import secrets
from datetime import timedelta
from functools import wraps

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from services import docker_control as dc
from services import docs as docs_module
from services import traffic

app = Flask(__name__)
app.secret_key = dc.get_or_create_secret_key()
# Now that the admin UI can be reached from the internet (an admin subdomain
# routed through the Cloudflare Tunnel, see docs/cloudflare-tunnel-setup.md),
# sessions get a server-enforced expiry and SameSite=Lax, which stops the
# cookie being sent on cross-site form submits/navigations - the first line
# of defense against CSRF, backed up by the token check below.
app.config.update(
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
)


def client_ip() -> str:
    """The visitor's real IP. Cloudflare's edge sets Cf-Connecting-Ip and
    cloudflared forwards it unmodified; nginx never sees or rewrites it, so
    it's read straight from the request. Falls back to the direct peer
    address for LAN access, where the header is never present."""
    return request.headers.get("Cf-Connecting-Ip", request.remote_addr)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


@app.before_request
def require_setup_first():
    """Gate the whole app on whether an admin account exists yet. A clean
    checkout has no .env, so there's nothing to log into yet: send everything
    to /setup until an account is created, and once one exists, don't let
    /setup be used to take over the instance."""
    endpoint = request.endpoint
    if endpoint in ("static", "setup"):
        return
    if not dc.is_account_configured():
        return redirect(url_for("setup"))


@app.before_request
def enforce_csrf():
    """Every POST must carry back the token the form was rendered with (see
    inject_csrf_token below). Without this, any site the admin's browser
    visits could silently submit a forged request to e.g. /save-account
    using their live session cookie - a real risk once this app is reachable
    from the open internet rather than just the LAN."""
    if request.method == "POST":
        token = session.get("csrf_token")
        submitted = request.form.get("csrf_token", "")
        if not token or not secrets.compare_digest(token, submitted):
            abort(400, description="Missing or invalid CSRF token. Go back and reload the page, then try again.")


@app.context_processor
def inject_csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return {"csrf_token": session["csrf_token"]}


@app.route("/setup", methods=["GET", "POST"])
def setup():
    if dc.is_account_configured():
        return redirect(url_for("login"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        account_updates = {}
        missing = []
        for key, label, _input_type, _help in dc.ACCOUNT_FIELDS:
            value = request.form.get(key, "").strip()
            if key in dc.REQUIRED_ACCOUNT_FIELDS and not value:
                missing.append(label)
            if value:
                account_updates[key] = value
            elif key in dc.ACCOUNT_FIELD_DEFAULTS:
                account_updates[key] = dc.ACCOUNT_FIELD_DEFAULTS[key]

        if not username or not password:
            flash("Username and password are required.", "error")
        elif password != confirm:
            flash("Passwords don't match.", "error")
        elif len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
        elif missing:
            flash("Please fill in: " + ", ".join(missing) + " - these are required so you can recover your account later.", "error")
        else:
            dc.create_account(username, password)
            dc.write_env(account_updates)
            session["logged_in"] = True
            session.permanent = True
            flash("Account created.", "success")
            return redirect(url_for("dashboard"))

    return render_template(
        "setup.html",
        account_fields=dc.ACCOUNT_FIELDS,
        required_fields=dc.REQUIRED_ACCOUNT_FIELDS,
        field_defaults=dc.ACCOUNT_FIELD_DEFAULTS,
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        ip = client_ip()
        cooldown = dc.login_lockout_remaining(ip)
        if cooldown:
            flash(f"Too many failed login attempts. Try again in {cooldown}s.", "error")
        else:
            username = request.form.get("username", "")
            password = request.form.get("password", "")
            env = dc.read_env()
            if username == env.get("ADMIN_UI_USERNAME") and check_password_hash(env.get("ADMIN_UI_PASSWORD_HASH", ""), password):
                dc.clear_login_attempts(ip)
                session.clear()
                session["logged_in"] = True
                session.permanent = True
                return redirect(url_for("dashboard"))
            dc.record_failed_login(ip)
            flash("Invalid username or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    configured = dc.recovery_is_configured()
    sent = False
    if request.method == "POST" and configured:
        cooldown = dc.reset_send_cooldown_remaining()
        if cooldown:
            flash(f"A code was already sent recently. Please wait {cooldown}s before requesting another.", "error")
        else:
            code = dc.start_reset()
            ok, error = dc.send_reset_email(code)
            if ok:
                dc.mark_reset_sent()
                flash("A reset code has been sent to your recovery email.", "success")
                sent = True
            else:
                flash(f"Couldn't send the reset email: {error}", "error")
    return render_template("forgot_password.html", configured=configured, sent=sent)


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if request.method == "POST":
        code = request.form.get("code", "")
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        if not dc.verify_reset(code):
            flash("That code is invalid or has expired. Request a new one.", "error")
        elif password != confirm:
            flash("Passwords don't match.", "error")
        elif len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
        else:
            dc.update_password(password)
            flash("Password updated. Log in with your new password.", "success")
            return redirect(url_for("login"))

    return render_template("reset_password.html")


@app.route("/docs")
def docs_index():
    return redirect(url_for("docs_page", slug=docs_module.PAGES[0][0]))


@app.route("/docs/<slug>")
def docs_page(slug):
    result = docs_module.render_page(slug)
    if result is None:
        return "Not found", 404
    title, html = result
    return render_template(
        "docs.html",
        pages=docs_module.PAGES,
        active_slug=slug,
        page_title=title,
        content_html=html,
    )


@app.route("/api/docs/<slug>")
def api_docs_page(slug):
    """Backs docs.html's client-side page switching: fetched in place of a
    full navigation so moving between doc pages feels like the tabs on the
    Account page instead of a page reload. Same access level as
    /docs/<slug> (no login_required) since the docs are public there too."""
    result = docs_module.render_page(slug)
    if result is None:
        return jsonify(error="not found"), 404
    title, html = result
    return jsonify(title=title, html=html)


@app.route("/")
@login_required
def dashboard():
    # No Docker/nginx calls here on purpose: the page renders instantly with
    # loading placeholders and fills them in via /api/metrics.
    return render_template("dashboard.html")


@app.route("/api/metrics")
@login_required
def api_metrics():
    """Polled by the dashboard's auto-refresh and by its initial load. The
    dashboard page itself renders instantly with no Docker calls, then
    fetches this in the background so slow calls (docker stats especially)
    never block the page from opening."""
    return jsonify(dc.get_dashboard_metrics())


@app.route("/api/traffic")
@login_required
def api_traffic():
    """Backs the dashboard's Request Types pie chart and Network Activity
    graph. See services/traffic.py for how nginx's access log becomes this."""
    return jsonify(traffic.get_traffic_stats())


@app.route("/settings")
@login_required
def settings():
    return render_template(
        "settings.html",
        steps=dc.SETTINGS_STEPS,
        env_values=dc.read_env(),
        required_fields=dc.REQUIRED_SETTINGS_FIELDS,
    )


@app.route("/save", methods=["POST"])
@login_required
def save():
    previous = dc.read_env()

    def has_value(key):
        return bool(request.form.get(key) or previous.get(key))

    missing = []
    for key in dc.REQUIRED_SETTINGS_FIELDS:
        if not has_value(key):
            label = next(label for k, label, _t, _h in dc.EDITABLE_FIELDS if k == key)
            missing.append(label)

    # Both halves of the foundryvtt.com login are needed together, or the
    # container startup download fails; neither is individually required
    # since leaving both blank is valid too (see FOUNDRY_RELEASE_URL in
    # docs/configuration.md).
    if has_value("FOUNDRY_USERNAME") != has_value("FOUNDRY_PASSWORD"):
        missing.append("Foundry Account Username and Password (fill in both, or leave both blank to use FOUNDRY_RELEASE_URL instead)")

    if missing:
        flash("Please fill in: " + ", ".join(missing), "error")
        return redirect(url_for("settings"))

    updates = {}
    for key, _label, _type, _help in dc.EDITABLE_FIELDS:
        if key in request.form:
            value = request.form[key]
            # Don't overwrite a saved secret with a blank field left untouched.
            if _type == "password" and value == "":
                continue
            updates[key] = value

    dc.write_env(updates)

    # Text fields round-trip through the form on every submit whether or not
    # they were touched, so "key present in updates" alone would restart
    # cloudflared every time. Only count a field as changed if its value
    # differs from what was stored before this submit. A re-typed but
    # identical password still counts as changed, since there's no way to
    # tell that apart from a real one.
    changed = {key for key, value in updates.items() if value != previous.get(key, "")}

    # Foundry always restarts on save, since its container is the only thing
    # this form used to touch. cloudflared only gets recreated on top of that
    # when a Cloudflare field actually changed, so a Foundry-only edit
    # doesn't also bounce the public tunnel.
    restarts = [("Foundry", "foundry")]
    if dc.CLOUDFLARE_FIELD_KEYS & changed:
        restarts.append(("Cloudflare Tunnel", "cloudflared"))

    failures = []
    for label, service in restarts:
        success, output = dc.apply_and_restart(service)
        if not success:
            failures.append(f"{label}: {output}")

    if not failures:
        names = " and ".join(label for label, _service in restarts)
        flash(f"Settings saved. {names} restarting with the new configuration.", "success")
    else:
        flash("Settings saved, but restarting failed:\n" + "\n".join(failures), "error")

    return redirect(url_for("settings"))


@app.route("/account")
@login_required
def account():
    return render_template(
        "account.html",
        account_fields=dc.ACCOUNT_FIELDS,
        field_defaults=dc.ACCOUNT_FIELD_DEFAULTS,
        env_values=dc.read_env(),
    )


@app.route("/save-account", methods=["POST"])
@login_required
def save_account():
    updates = {}
    for key, _label, _type, _help in dc.ACCOUNT_FIELDS:
        if key in request.form:
            value = request.form[key]
            if _type == "password" and value == "":
                continue
            updates[key] = value
    dc.write_env(updates)

    new_password = request.form.get("new_password", "")
    if new_password:
        confirm = request.form.get("confirm_new_password", "")
        if new_password != confirm:
            flash("New passwords don't match - other account settings were saved.", "error")
            return redirect(url_for("account"))
        if len(new_password) < 8:
            flash("New password must be at least 8 characters - other account settings were saved.", "error")
            return redirect(url_for("account"))
        dc.update_password(new_password)

    flash("Account settings saved.", "success")
    return redirect(url_for("account"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
