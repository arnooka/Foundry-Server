// Generic slide-wizard engine: one focused step per screen, sliding
// transitions, dot progress, and a Back button. Shared by the first-run
// setup wizard (setup.html) and the Account page's Password Recovery
// wizard (account.html). Both wrap a single real <form> that only submits
// once, at the end; this only changes how the steps are presented, never
// when anything actually saves. Each page supplies its own per-step
// validation via the validateStep callback.
//
// root is the .wizard element; it must contain a <form> (wrapping a
// .wizard-track of .wizard-step sections), .wizard-dot indicators, and
// optionally a .wizard-back button.
function initWizard(root, validateStep) {
    var form = root.querySelector("form");
    var track = root.querySelector(".wizard-track");
    var viewport = root.querySelector(".wizard-viewport");
    var steps = Array.prototype.slice.call(root.querySelectorAll(".wizard-step"));
    var dots = Array.prototype.slice.call(root.querySelectorAll(".wizard-dot"));
    var backBtn = root.querySelector(".wizard-back");
    if (!form || !track || steps.length === 0) return null;

    var current = 0;

    // Steps sit side by side in .wizard-track (only shifted off-screen via
    // transform), so the viewport's natural height is the tallest of all of
    // them. Pin it to just the active step instead, and keep it in sync via
    // ResizeObserver so it also tracks in-place height changes on the
    // current step, like a validation error appearing or disappearing, or
    // text reflowing on window resize, not just step changes.
    function syncHeight() {
        if (viewport) viewport.style.height = steps[current].offsetHeight + "px";
    }
    if (viewport && window.ResizeObserver) {
        var ro = new ResizeObserver(syncHeight);
        steps.forEach(function (step) { ro.observe(step); });
    }

    function showStepError(step, message) {
        var errEl = step.querySelector("[data-step-error]");
        if (!errEl) return;
        errEl.textContent = message || "";
        errEl.style.display = message ? "block" : "none";
    }

    function go(index) {
        index = Math.max(0, Math.min(steps.length - 1, index));
        current = index;
        track.style.transform = "translateX(-" + (current * 100) + "%)";
        steps.forEach(function (step, i) {
            step.classList.toggle("step-active", i === current);
        });
        dots.forEach(function (dot, i) {
            dot.classList.toggle("active", i === current);
            dot.classList.toggle("done", i < current);
        });
        if (backBtn) backBtn.hidden = current === 0;
        syncHeight();
        // select is excluded once custom-select.js has hidden it (marked
        // aria-hidden) in favor of its .custom-select-trigger replacement.
        // Focusing the native element underneath would move focus invisibly
        // instead of landing on the themed control shown on screen.
        var firstInput = steps[current].querySelector("input:not([hidden]):not([type=hidden]), select:not([aria-hidden]), .custom-select-trigger");
        if (firstInput) firstInput.focus({ preventScroll: true });
    }

    root.querySelectorAll("[data-next]").forEach(function (btn) {
        btn.addEventListener("click", function () {
            var step = btn.closest(".wizard-step");
            var index = steps.indexOf(step);
            var error = validateStep ? validateStep(index) : null;
            showStepError(step, error);
            if (error) return;
            showStepError(step, null);
            go(index + 1);
        });
    });

    if (backBtn) {
        backBtn.addEventListener("click", function () { go(current - 1); });
    }

    form.addEventListener("submit", function (evt) {
        var lastIndex = steps.length - 1;
        var error = validateStep ? validateStep(lastIndex) : null;
        showStepError(steps[lastIndex], error);
        if (error) evt.preventDefault();
    });

    go(0);
    return { go: go };
}
