document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-perm-picker]").forEach((root) => {
    const searchInput = root.querySelector("[data-perm-search]");
    const selectAllBtn = root.querySelector("[data-perm-select-all]");
    const clearAllBtn = root.querySelector("[data-perm-clear-all]");
    const badges = root.querySelectorAll("[data-perm-count]");

    function updateCounts() {
      const n = root.querySelectorAll(".perm-checkbox:checked").length;
      badges.forEach((badge) => {
        const template = badge.getAttribute("data-perm-count-format") || "{n} permissions selected";
        badge.textContent = template.replace("{n}", String(n));
      });
    }

    function syncModuleSelectAll(module) {
      const perms = root.querySelectorAll(`.perm-checkbox[data-module="${module}"]`);
      const master = root.querySelector(`.module-select-all[data-module="${module}"]`);
      if (!master || !perms.length) return;
      const checked = [...perms].filter((cb) => cb.checked).length;
      master.checked = checked === perms.length;
      master.indeterminate = checked > 0 && checked < perms.length;
    }

    if (searchInput) {
      searchInput.addEventListener("input", (e) => {
        const term = e.target.value.toLowerCase().trim();
        root.querySelectorAll(".perm-module-card").forEach((card) => {
          const moduleLabel = card.dataset.label || "";
          let rowMatchCount = 0;
          card.querySelectorAll(".perm-row").forEach((row) => {
            const rowLabel = row.dataset.label || "";
            const match = !term || rowLabel.includes(term) || moduleLabel.includes(term);
            row.classList.toggle("hidden", !match);
            if (match) rowMatchCount += 1;
          });
          card.classList.toggle("hidden", !(moduleLabel.includes(term) || rowMatchCount > 0));
        });
      });
    }

    if (selectAllBtn) {
      selectAllBtn.addEventListener("click", () => {
        root.querySelectorAll(".perm-checkbox, .module-select-all").forEach((cb) => {
          cb.checked = true;
          cb.indeterminate = false;
        });
        updateCounts();
      });
    }

    if (clearAllBtn) {
      clearAllBtn.addEventListener("click", () => {
        root.querySelectorAll(".perm-checkbox, .module-select-all").forEach((cb) => {
          cb.checked = false;
          cb.indeterminate = false;
        });
        updateCounts();
      });
    }

    root.querySelectorAll(".module-select-all").forEach((master) => {
      const module = master.dataset.module;
      syncModuleSelectAll(module);
      master.addEventListener("change", () => {
        root.querySelectorAll(`.perm-checkbox[data-module="${module}"]`).forEach((cb) => {
          cb.checked = master.checked;
        });
        master.indeterminate = false;
        updateCounts();
      });
    });

    root.querySelectorAll(".perm-checkbox").forEach((cb) => {
      cb.addEventListener("change", () => {
        syncModuleSelectAll(cb.dataset.module);
        updateCounts();
      });
    });

    updateCounts();
  });
});
