// Progressively enhances every <select> into a themed dropdown with an
// open/close animation that matches the rest of the admin UI. A native
// <select>'s options popup is drawn by the OS/browser, so it can't be
// restyled or animated with CSS in any browser this app needs to support.
// The original <select> stays in the document (invisible, but with a live
// .value), so anything that already reads or writes it, like
// email-providers.js's auto-fill logic or wizard.js's step focus, keeps
// working unmodified. This just builds a themed trigger and menu in front
// of it and keeps the two in sync via the select's own "change" event.
(function () {
    function svgChevron() {
        var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("viewBox", "0 0 24 24");
        svg.setAttribute("class", "custom-select-chevron");
        svg.setAttribute("aria-hidden", "true");
        var path = document.createElementNS("http://www.w3.org/2000/svg", "path");
        path.setAttribute("d", "M6 9l6 6 6-6");
        path.setAttribute("fill", "none");
        path.setAttribute("stroke", "currentColor");
        path.setAttribute("stroke-width", "2");
        path.setAttribute("stroke-linecap", "round");
        path.setAttribute("stroke-linejoin", "round");
        svg.appendChild(path);
        return svg;
    }

    function enhance(select) {
        var wrap = document.createElement("div");
        wrap.className = "custom-select";
        select.parentNode.insertBefore(wrap, select);
        wrap.appendChild(select);

        var triggerId = (select.id || "select-" + Math.random().toString(36).slice(2)) + "-trigger";
        var trigger = document.createElement("button");
        trigger.type = "button";
        trigger.id = triggerId;
        trigger.className = "custom-select-trigger";
        trigger.setAttribute("aria-haspopup", "listbox");
        trigger.setAttribute("aria-expanded", "false");

        var valueSpan = document.createElement("span");
        valueSpan.className = "custom-select-value";
        trigger.appendChild(valueSpan);
        trigger.appendChild(svgChevron());
        wrap.appendChild(trigger);

        // A <label for="..."> pointed at the original select would now focus
        // a hidden, non-interactive element. Repoint it at the trigger so
        // clicking the label still opens the picker like it did for the
        // native <select>.
        if (select.id) {
            var label = document.querySelector('label[for="' + select.id + '"]');
            if (label) label.setAttribute("for", triggerId);
        }

        select.tabIndex = -1;
        select.setAttribute("aria-hidden", "true");

        // Appended to <body> rather than left nested in .custom-select; see
        // the .custom-select-menu comment in style.css (the wizard's sliding
        // track transform would otherwise hijack its fixed positioning).
        var menu = document.createElement("ul");
        menu.className = "custom-select-menu";
        menu.setAttribute("role", "listbox");
        menu.setAttribute("aria-labelledby", triggerId);
        document.body.appendChild(menu);

        var optionEls = Array.prototype.map.call(select.options, function (opt) {
            var li = document.createElement("li");
            li.className = "custom-select-option";
            li.setAttribute("role", "option");
            li.dataset.value = opt.value;
            li.textContent = opt.textContent;
            li.addEventListener("mousedown", function (evt) {
                // mousedown, not click, so this fires before the
                // document-level mousedown listener below closes the menu
                // and treats it as a click-outside.
                evt.preventDefault();
                choose(opt.value);
            });
            li.addEventListener("mouseenter", function () { highlight(li); });
            menu.appendChild(li);
            return li;
        });

        function highlight(li) {
            optionEls.forEach(function (el) { el.classList.toggle("highlighted", el === li); });
        }

        function highlightedOrSelected() {
            var found = null;
            optionEls.forEach(function (el) {
                if (el.classList.contains("highlighted")) found = el;
            });
            if (found) return found;
            optionEls.forEach(function (el) {
                if (el.classList.contains("selected")) found = el;
            });
            return found || optionEls[0];
        }

        function syncFromSelect() {
            var opt = select.options[select.selectedIndex];
            valueSpan.textContent = opt ? opt.textContent : "";
            optionEls.forEach(function (li) {
                var isSelected = li.dataset.value === select.value;
                li.classList.toggle("selected", isSelected);
                li.setAttribute("aria-selected", isSelected ? "true" : "false");
            });
        }
        syncFromSelect();
        // Also picks up value changes made by other code that assigns
        // select.value directly (e.g. account.html pre-selecting the saved
        // provider), as long as it dispatches "change". That's the same
        // contract a native <select> already has with the rest of this
        // codebase.
        select.addEventListener("change", syncFromSelect);

        function choose(value) {
            if (select.value !== value) {
                select.value = value;
                select.dispatchEvent(new Event("change", { bubbles: true }));
            }
            close(true);
        }

        function positionMenu() {
            var rect = trigger.getBoundingClientRect();
            menu.style.width = rect.width + "px";
            menu.style.left = rect.left + "px";
            // Flip above the trigger when there isn't room below (e.g. a
            // step near the bottom of a short viewport).
            var menuHeight = menu.offsetHeight;
            var fitsBelow = rect.bottom + 6 + menuHeight <= window.innerHeight;
            menu.style.top = fitsBelow ? (rect.bottom + 6) + "px" : (rect.top - 6 - menuHeight) + "px";
            menu.style.transformOrigin = fitsBelow ? "top center" : "bottom center";
        }

        function onDocPointerDown(evt) {
            if (wrap.contains(evt.target) || menu.contains(evt.target)) return;
            close(false);
        }
        function onScrollOrResize() { close(false); }
        function onKeydown(evt) {
            if (evt.key === "Escape") { close(true); return; }
            if (evt.key === "Enter" || evt.key === " ") {
                evt.preventDefault();
                choose(highlightedOrSelected().dataset.value);
                return;
            }
            if (evt.key === "ArrowDown" || evt.key === "ArrowUp") {
                evt.preventDefault();
                var index = optionEls.indexOf(highlightedOrSelected());
                var nextIndex = evt.key === "ArrowDown"
                    ? Math.min(optionEls.length - 1, index + 1)
                    : Math.max(0, index - 1);
                highlight(optionEls[nextIndex]);
                optionEls[nextIndex].scrollIntoView({ block: "nearest" });
            }
        }

        function open() {
            if (wrap.classList.contains("open")) return;
            positionMenu();
            wrap.classList.add("open");
            menu.classList.add("open");
            trigger.setAttribute("aria-expanded", "true");
            highlight(highlightedOrSelected());
            document.addEventListener("mousedown", onDocPointerDown, true);
            document.addEventListener("keydown", onKeydown, true);
            window.addEventListener("scroll", onScrollOrResize, true);
            window.addEventListener("resize", onScrollOrResize);
        }

        function close(focusTrigger) {
            if (!wrap.classList.contains("open")) return;
            wrap.classList.remove("open");
            menu.classList.remove("open");
            trigger.setAttribute("aria-expanded", "false");
            document.removeEventListener("mousedown", onDocPointerDown, true);
            document.removeEventListener("keydown", onKeydown, true);
            window.removeEventListener("scroll", onScrollOrResize, true);
            window.removeEventListener("resize", onScrollOrResize);
            if (focusTrigger) trigger.focus();
        }

        trigger.addEventListener("click", function () {
            if (wrap.classList.contains("open")) close(false); else open();
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        Array.prototype.forEach.call(document.querySelectorAll("select"), enhance);
    });
})();
