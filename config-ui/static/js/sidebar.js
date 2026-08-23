// Collapses the sidebar to an icon-only rail, remembered across page loads
// via localStorage. The initial "apply before paint" logic lives inline in
// base.html's <head> (see the comment there for why); this just owns the
// click toggle and keeps localStorage in sync with it.
(function () {
    var KEY = "sidebarCollapsed";
    var toggle = document.getElementById("sidebar-collapse-toggle");

    if (toggle) {
        function setCollapsed(collapsed) {
            document.documentElement.classList.toggle("sidebar-collapsed", collapsed);
            toggle.title = collapsed ? "Expand sidebar" : "Collapse sidebar";
            toggle.setAttribute("aria-label", toggle.title);
            try { localStorage.setItem(KEY, collapsed ? "1" : "0"); } catch (e) {}
        }

        // Sync the button's own label with whatever state the inline head
        // script already applied, without re-triggering the open/close animation.
        toggle.title = document.documentElement.classList.contains("sidebar-collapsed") ? "Expand sidebar" : "Collapse sidebar";
        toggle.setAttribute("aria-label", toggle.title);

        toggle.addEventListener("click", function () {
            setCollapsed(!document.documentElement.classList.contains("sidebar-collapsed"));
        });
    }

    // Mobile drawer: the checkbox already gets unchecked by clicking the
    // backdrop or the in-drawer close button (both are <label for>s), but
    // Escape needs its own handler since there's no native input for that.
    var drawerToggle = document.getElementById("sidebar-toggle");
    if (drawerToggle) {
        document.addEventListener("keydown", function (e) {
            if (e.key === "Escape" && drawerToggle.checked) {
                drawerToggle.checked = false;
            }
        });
    }
})();
