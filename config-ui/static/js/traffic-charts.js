// Renders the dashboard's Request Types pie chart and Network Activity bar
// chart from /api/traffic (see traffic.py), with hover tooltips and a
// legend for the pie. Hand-rolled SVG rather than a charting library, since
// this app has no external/CDN dependencies anywhere else and these two
// charts are simple enough not to need one.
(function () {
    var TRAFFIC_URL = "/api/traffic";
    var REFRESH_MS = 30000;
    var PALETTE = ["#7c5cff", "#3ecf8e", "#ffb020", "#ff6b6b", "#2dd4bf", "#f472b6", "#60a5fa", "#a78bfa"];
    var SVG_NS = "http://www.w3.org/2000/svg";

    var pieSvg = document.getElementById("request-types-pie");
    var pieLegend = document.getElementById("request-types-legend");
    var pieEmpty = document.getElementById("request-types-empty");
    var barsSvg = document.getElementById("traffic-timeseries");
    var tooltip = document.getElementById("chart-tooltip");

    if (!pieSvg && !barsSvg) return;

    function eventCoords(evt) {
        // Touch events carry coordinates on touches/changedTouches instead
        // of directly on the event, so hover and tap can share one path.
        if (evt.touches && evt.touches.length) return evt.touches[0];
        if (evt.changedTouches && evt.changedTouches.length) return evt.changedTouches[0];
        return evt;
    }

    function showTooltip(evt, html) {
        tooltip.innerHTML = html;
        tooltip.style.display = "block";
        moveTooltip(evt);
    }

    function moveTooltip(evt) {
        var pos = eventCoords(evt);
        var pad = 14;
        var tipWidth = tooltip.offsetWidth || 160;
        var left = pos.clientX + pad;
        if (left + tipWidth > window.innerWidth) {
            left = pos.clientX - tipWidth - pad;
        }
        var top = pos.clientY + pad;
        if (top + tooltip.offsetHeight > window.innerHeight) {
            top = pos.clientY - tooltip.offsetHeight - pad;
        }
        tooltip.style.left = left + "px";
        tooltip.style.top = top + "px";
    }

    function hideTooltip() {
        tooltip.style.display = "none";
    }

    // Attaches both hover (desktop) and tap (touch) handling to one chart
    // element: tapping a slice/bar shows its tooltip, tapping anywhere else
    // (handled once, below) dismisses whatever is open.
    function bindTooltip(el, htmlFn) {
        el.addEventListener("mousemove", function (evt) { showTooltip(evt, htmlFn()); });
        el.addEventListener("mouseleave", hideTooltip);
        el.addEventListener("touchstart", function (evt) {
            evt.stopPropagation();
            showTooltip(evt, htmlFn());
        }, { passive: true });
    }

    document.addEventListener("touchstart", function (evt) {
        if (!tooltip.contains(evt.target)) hideTooltip();
    }, { passive: true });

    function renderPie(requestTypes) {
        if (!pieSvg) return;
        var entries = Object.keys(requestTypes).map(function (k) { return [k, requestTypes[k]]; });
        entries.sort(function (a, b) { return b[1] - a[1]; });
        var total = entries.reduce(function (sum, e) { return sum + e[1]; }, 0);

        pieSvg.innerHTML = "";
        pieLegend.innerHTML = "";

        if (total === 0) {
            pieEmpty.style.display = "block";
            pieSvg.style.display = "none";
            pieLegend.style.display = "none";
            return;
        }
        pieEmpty.style.display = "none";
        pieSvg.style.display = "block";
        pieLegend.style.display = "flex";

        var r = 52, cx = 70, cy = 70, strokeWidth = 30;
        var circumference = 2 * Math.PI * r;
        var offset = 0;

        entries.forEach(function (entry, i) {
            var label = entry[0], count = entry[1];
            var color = PALETTE[i % PALETTE.length];
            var fraction = count / total;
            var dash = fraction * circumference;
            var pct = (fraction * 100).toFixed(1);

            var circle = document.createElementNS(SVG_NS, "circle");
            circle.setAttribute("cx", cx);
            circle.setAttribute("cy", cy);
            circle.setAttribute("r", r);
            circle.setAttribute("fill", "none");
            circle.setAttribute("stroke", color);
            circle.setAttribute("stroke-width", strokeWidth);
            circle.setAttribute("stroke-dasharray", dash + " " + (circumference - dash));
            circle.setAttribute("stroke-dashoffset", -offset);
            circle.setAttribute("transform", "rotate(-90 " + cx + " " + cy + ")");
            circle.classList.add("pie-slice");
            bindTooltip(circle, function () {
                return "<strong>" + label + "</strong><br>" + count + " request" + (count !== 1 ? "s" : "") + " (" + pct + "%)";
            });
            pieSvg.appendChild(circle);

            var legendItem = document.createElement("div");
            legendItem.className = "chart-legend-item";
            var swatch = document.createElement("span");
            swatch.className = "chart-legend-swatch";
            swatch.style.background = color;
            legendItem.appendChild(swatch);
            legendItem.appendChild(document.createTextNode(label));
            var countEl = document.createElement("span");
            countEl.className = "chart-legend-count";
            countEl.textContent = count;
            legendItem.appendChild(countEl);
            pieLegend.appendChild(legendItem);

            offset += dash;
        });
    }

    function renderTimeseries(timeseries) {
        if (!barsSvg) return;
        barsSvg.innerHTML = "";

        var width = 640, height = 140;
        var maxCount = Math.max.apply(null, timeseries.map(function (b) { return b.count; }).concat([1]));
        var barGap = 4;
        var barWidth = (width - barGap * (timeseries.length - 1)) / timeseries.length;

        timeseries.forEach(function (bucket, i) {
            var barHeight = bucket.count === 0 ? 0 : Math.max(3, (bucket.count / maxCount) * height);
            var x = i * (barWidth + barGap);
            var y = height - barHeight;

            var rect = document.createElementNS(SVG_NS, "rect");
            rect.setAttribute("x", x);
            rect.setAttribute("y", y);
            rect.setAttribute("width", barWidth);
            rect.setAttribute("height", barHeight);
            rect.setAttribute("rx", 2);
            rect.classList.add("traffic-bar");

            var timeLabel = new Date(bucket.time * 1000).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
            bindTooltip(rect, function () {
                return "<strong>" + timeLabel + "</strong><br>" + bucket.count + " request" + (bucket.count !== 1 ? "s" : "");
            });
            barsSvg.appendChild(rect);
        });
    }

    function refresh() {
        fetch(TRAFFIC_URL)
            .then(function (r) { return r.json(); })
            .then(function (d) {
                renderPie(d.request_types || {});
                renderTimeseries(d.timeseries || []);
            })
            .catch(function () {});
    }

    document.addEventListener("mousemove", function (evt) {
        if (tooltip.style.display === "block") moveTooltip(evt);
    });

    refresh();
    setInterval(refresh, REFRESH_MS);
})();
