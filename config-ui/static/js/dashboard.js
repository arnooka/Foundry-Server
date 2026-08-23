// Polls /api/metrics on an interval and patches only the values that
// changed, so the dashboard page itself can render instantly with loading
// skeletons instead of waiting on Docker calls (see app.py's dashboard route
// and docker_control.get_dashboard_metrics).
(function () {
    var METRICS_URL = "/api/metrics";
    var REFRESH_MS = 6000;
    var statusEl = document.getElementById("live-status");
    var secondsSinceRefresh = 0;
    var tickTimer = null;

    function flash(el) {
        el.classList.remove("metric-flash");
        void el.offsetWidth; // restart the animation even if it just ran
        el.classList.add("metric-flash");
    }

    function setText(key, text) {
        document.querySelectorAll('[data-metric="' + key + '"]').forEach(function (el) {
            // The skeleton class/child can end up either on this element
            // itself or on a nested placeholder span depending on the
            // markup. Clear it from both so real text never ends up
            // rendered with the skeleton's color:transparent.
            var hadSkeleton = el.classList.contains("skeleton") || el.querySelector(".skeleton") !== null;
            if (hadSkeleton || el.textContent !== text) {
                el.classList.remove("skeleton");
                el.textContent = text;
                flash(el);
            }
        });
    }

    function setDot(key, status) {
        document.querySelectorAll('[data-dot="' + key + '"]').forEach(function (el) {
            el.className = "dot " + status;
        });
    }

    function capitalize(s) {
        return s.charAt(0).toUpperCase() + s.slice(1);
    }

    function startTicking() {
        if (tickTimer) return;
        tickTimer = setInterval(function () {
            secondsSinceRefresh += 1;
            statusEl.textContent = "Live — updated " + secondsSinceRefresh + "s ago";
        }, 1000);
    }

    function refreshMetrics() {
        fetch(METRICS_URL)
            .then(function (r) { return r.json(); })
            .then(function (d) {
                setDot("foundry", d.foundry_status);
                setText("foundry-status", capitalize(d.foundry_status));
                setText("foundry-sub", (d.foundry_status === "running" && d.foundry_uptime) ? ("Up " + d.foundry_uptime) : "Container not serving yet");

                setDot("tunnel", d.tunnel_status);
                setText("tunnel-status", capitalize(d.tunnel_status));
                setText("tunnel-sub", d.public_hostname || "No hostname recorded (see Docs → Cloudflare Tunnel Setup)");

                setText("cpu-value", d.foundry_stats ? d.foundry_stats.cpu_percent : "—");

                setText("mem-value", d.foundry_stats ? d.foundry_stats.mem_usage : "—");
                setText("mem-sub", d.foundry_stats ? ("of " + d.foundry_stats.mem_limit + " (" + d.foundry_stats.mem_percent + ")") : "Foundry container");

                setText("requests-value", d.nginx_stats ? String(d.nginx_stats.requests) : "—");
                setText("requests-sub", d.nginx_stats ? (d.nginx_stats.active_connections + " active connection" + (d.nginx_stats.active_connections !== 1 ? "s" : "")) : "Metrics unavailable");

                secondsSinceRefresh = 0;
                statusEl.textContent = "Live — updated just now";
                startTicking();
            })
            .catch(function () {
                statusEl.textContent = "Couldn't load metrics — retrying…";
            });
    }

    refreshMetrics();
    setInterval(refreshMetrics, REFRESH_MS);
})();
