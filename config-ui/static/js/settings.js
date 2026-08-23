// Shows a confirmation modal summarizing what's about to change before the
// Foundry Settings form actually submits (and therefore restarts Foundry).
(function () {
    var form = document.getElementById("foundry-form");
    var modal = document.getElementById("restart-modal");
    var list = document.getElementById("restart-change-list");

    function describeChanges() {
        var changes = [];
        form.querySelectorAll("input[data-label]").forEach(function (input) {
            var label = input.dataset.label;
            if (input.type === "password") {
                if (input.value !== "") {
                    changes.push(label + ": will be updated");
                }
                return;
            }
            var original = input.dataset.original || "";
            var current = input.value;
            if (current !== original) {
                var from = original === "" ? "(blank)" : original;
                var to = current === "" ? "(blank)" : current;
                changes.push(label + ": " + from + " → " + to);
            }
        });
        return changes;
    }

    form.addEventListener("submit", function (event) {
        event.preventDefault();
        var changes = describeChanges();
        list.innerHTML = "";
        if (changes.length === 0) {
            var li = document.createElement("li");
            li.textContent = "No settings changed - Foundry will still restart.";
            list.appendChild(li);
        } else {
            changes.forEach(function (change) {
                var li = document.createElement("li");
                li.textContent = change;
                list.appendChild(li);
            });
        }
        modal.classList.add("open");
    });

    document.getElementById("restart-cancel").addEventListener("click", function () {
        modal.classList.remove("open");
    });

    document.getElementById("restart-confirm").addEventListener("click", function () {
        modal.classList.remove("open");
        form.submit();
    });

    modal.addEventListener("click", function (event) {
        if (event.target === modal) {
            modal.classList.remove("open");
        }
    });
})();
