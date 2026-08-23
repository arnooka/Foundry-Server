// Theme and motion toggle buttons on the Account & Recovery page. Both are
// per-browser preferences stored in localStorage, not sent to the server.
// The "apply before paint" logic that reads them lives inline in base.html's
// <head>; this just owns the buttons and keeps localStorage and classes in
// sync.
(function () {
    var THEME_KEY = "theme";
    var MOTION_KEY = "reduceMotion";

    function markActive(groupEl, datasetKey, currentValue) {
        if (!groupEl) return;
        groupEl.querySelectorAll(".pref-toggle-btn").forEach(function (btn) {
            btn.classList.toggle("active", btn.dataset[datasetKey] === currentValue);
        });
    }

    var themeGroup = document.getElementById("theme-toggle-group");
    var motionGroup = document.getElementById("motion-toggle-group");
    if (!themeGroup && !motionGroup) return;

    markActive(themeGroup, "themeValue", document.documentElement.classList.contains("theme-light") ? "light" : "dark");
    markActive(motionGroup, "motionValue", document.documentElement.classList.contains("reduce-motion") ? "off" : "on");

    if (themeGroup) {
        themeGroup.querySelectorAll(".pref-toggle-btn").forEach(function (btn) {
            btn.addEventListener("click", function () {
                var value = btn.dataset.themeValue; // "dark" or "light"
                document.documentElement.classList.toggle("theme-light", value === "light");
                try { localStorage.setItem(THEME_KEY, value); } catch (e) {}
                markActive(themeGroup, "themeValue", value);
            });
        });
    }

    if (motionGroup) {
        motionGroup.querySelectorAll(".pref-toggle-btn").forEach(function (btn) {
            btn.addEventListener("click", function () {
                var value = btn.dataset.motionValue; // "on" or "off"
                var reduce = value === "off";
                document.documentElement.classList.toggle("reduce-motion", reduce);
                try { localStorage.setItem(MOTION_KEY, reduce ? "1" : "0"); } catch (e) {}
                markActive(motionGroup, "motionValue", value);
            });
        });
    }
})();
