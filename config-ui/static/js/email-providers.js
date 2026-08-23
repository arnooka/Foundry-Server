// Shared provider presets for email-recovery setup, used by both the
// first-run wizard and the Account & Recovery page's Password Recovery
// wizard (both driven by wizard.js).
// Picking a provider fills in its SMTP host/port and links straight to
// where to generate an app password, instead of leaving people to hunt
// through docs. See docs/admin-ui-guide.md for the same info in prose.
var EMAIL_PROVIDERS = {
    gmail: {
        label: "Gmail",
        host: "smtp.gmail.com",
        port: "587",
        appPasswordUrl: "https://myaccount.google.com/apppasswords",
        instructions: "Turn on 2-Step Verification if it isn't already, then create an app password just for this."
    },
    outlook: {
        label: "Outlook / Hotmail / Live",
        host: "smtp-mail.outlook.com",
        port: "587",
        appPasswordUrl: "https://account.live.com/proofs/AppPassword",
        instructions: "Turn on two-step verification, then create an app password. Microsoft has been tightening this over time - Gmail is the more reliable option if it stops working."
    },
    yahoo: {
        label: "Yahoo Mail",
        host: "smtp.mail.yahoo.com",
        port: "587",
        appPasswordUrl: "https://login.yahoo.com/myaccount/security",
        instructions: "Turn on two-step verification in Yahoo Account Security, then generate an app password from the same page."
    },
    icloud: {
        label: "iCloud Mail",
        host: "smtp.mail.me.com",
        port: "587",
        appPasswordUrl: "https://appleid.apple.com/account/manage",
        instructions: "Turn on two-factor authentication for your Apple ID, then generate an app-specific password."
    },
    other: {
        label: "Other / not listed",
        host: "",
        port: "587",
        appPasswordUrl: "",
        instructions: "Search “your provider + app password” - most providers with two-factor authentication have an equivalent settings page."
    }
};

// Wires a <select> of provider keys to auto-fill host/port fields and
// update an instructions line and "get your app password" link. Pass null
// for any element a given page doesn't have. Respects manual edits to
// host/port: switching providers again won't clobber a value the user
// typed themselves.
//
// Host/port are also fully automatic for any known provider: their field
// (found via .closest(".field")) is hidden and non-required, since the
// dropdown already determines them. Only "Other" needs a person to supply
// them, since there's no preset to fall back on, so that's the one case
// where the field is shown and required.
function bindEmailProviderPicker(selectEl, hostInput, portInput, instructionsEl, linkEl) {
    if (!selectEl) return;

    function apply() {
        var isOther = !EMAIL_PROVIDERS.hasOwnProperty(selectEl.value) || selectEl.value === "other";
        var provider = EMAIL_PROVIDERS[selectEl.value] || EMAIL_PROVIDERS.other;
        if (hostInput && !hostInput.dataset.userEdited) hostInput.value = provider.host;
        if (portInput && !portInput.dataset.userEdited) portInput.value = provider.port;
        [hostInput, portInput].forEach(function (el) {
            if (!el) return;
            var wrapper = el.closest(".field") || el;
            wrapper.hidden = !isOther;
            el.required = isOther;
        });
        if (instructionsEl) instructionsEl.textContent = provider.instructions;
        if (linkEl) {
            if (provider.appPasswordUrl) {
                linkEl.href = provider.appPasswordUrl;
                linkEl.style.display = "inline-flex";
            } else {
                linkEl.style.display = "none";
            }
        }
    }

    [hostInput, portInput].forEach(function (el) {
        if (!el) return;
        el.addEventListener("input", function () { el.dataset.userEdited = "1"; });
    });

    selectEl.addEventListener("change", apply);
    apply();
}
