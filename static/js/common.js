function bindConfirmForms(root = document) {
  root.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) {
        event.preventDefault();
      }
    });
  });
}

function bindSearchClearFields(root = document) {
  root.querySelectorAll("[data-search-field]").forEach((field) => {
    if (field.dataset.searchFieldBound === "true") return;
    field.dataset.searchFieldBound = "true";
    const input = field.querySelector("input[type='search']");
    const clearButton = field.querySelector("[data-search-clear]");
    const updateClearButton = () => {
      if (clearButton) clearButton.hidden = !input?.value;
    };
    input?.addEventListener("input", updateClearButton);
    clearButton?.addEventListener("click", () => {
      input.value = "";
      updateClearButton();
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.focus();
    });
  });
}

function bindFormActionStates(root = document) {
  const isBlankNewRow = (row) => {
    const id = row.querySelector('input[name$="-id"]')?.value.trim();
    if (id) return false;
    const article = row.querySelector('input[name$="-article"]')?.value.trim();
    const price = row.querySelector('input[name$="-price"]')?.value.trim();
    const hasAllocation = Boolean(row.querySelector("[data-allocation-checkbox]:checked"));
    return !article && !price && !hasAllocation;
  };

  const formState = (form) => Array.from(form.elements)
    .filter((control) => {
      if (!control.name || control.name === "csrfmiddlewaretoken" || control.matches("[type='submit'], [type='button']")) return false;
      if (control.matches("[data-row-count]")) return false;
      const row = control.closest("[data-row]");
      return !row || !isBlankNewRow(row);
    })
    .map((control) => {
      if (control.type === "checkbox" || control.type === "radio") {
        return `${control.name}:${control.checked ? "1" : "0"}:${control.value}`;
      }
      if (control.type === "file") {
        const files = Array.from(control.files || [])
          .map((file) => `${file.name}:${file.size}:${file.lastModified}`)
          .join(",");
        return `${control.name}:${files}`;
      }
      return `${control.name}:${control.value}`;
    })
    .join("|");

  const receiptActionIsUseful = (form) => {
    if (!form.matches("[data-row-form]")) return true;
    return Array.from(form.querySelectorAll("[data-row]")).some((row) => {
      if (row.classList.contains("is-deleted") && row.querySelector('input[name$="-id"]')?.value.trim()) return true;
      if (row.classList.contains("is-deleted")) return false;
      const article = row.querySelector('input[name$="-article"]')?.value.trim();
      const price = row.querySelector('input[name$="-price"]')?.value.trim();
      return Boolean(article && price);
    });
  };

  const hasMeaningfulContent = (form) => Array.from(form.elements).some((control) => {
    if (!control.name || control.disabled || control.type === "hidden" || control.matches("[type='submit'], [type='button']")) return false;
    if (control.type === "file") return Boolean(control.files?.length);
    if (control.type === "checkbox" || control.type === "radio") return control.checked;
    return String(control.value || "").trim() !== "";
  });

  const stateButtons = (form, selector) => Array.from(root.querySelectorAll(selector))
    .filter((button) => button.form === form);

  root.querySelectorAll("form[data-dirty-form]").forEach((form) => {
    const initialState = formState(form);
    const buttons = stateButtons(form, "[data-dirty-submit]");
    const update = () => {
      const available = formState(form) !== initialState && form.checkValidity() && receiptActionIsUseful(form);
      buttons.forEach((button) => { button.disabled = !available; });
      form.dataset.submitAvailable = available ? "true" : "false";
    };
    form.addEventListener("input", update);
    form.addEventListener("change", update);
    form.addEventListener("click", () => queueMicrotask(update));
    form.addEventListener("submit", (event) => {
      if ((!event.submitter || event.submitter.matches("[data-dirty-submit]")) && form.dataset.submitAvailable !== "true") {
        event.preventDefault();
      }
    });
    update();
  });

  root.querySelectorAll("form[data-content-form]").forEach((form) => {
    const buttons = stateButtons(form, "[data-state-submit]");
    const update = () => {
      const available = hasMeaningfulContent(form) && form.checkValidity();
      buttons.forEach((button) => { button.disabled = !available; });
      form.dataset.submitAvailable = available ? "true" : "false";
    };
    form.addEventListener("input", update);
    form.addEventListener("change", update);
    form.addEventListener("click", () => queueMicrotask(update));
    form.addEventListener("submit", (event) => {
      if (form.dataset.submitAvailable !== "true") event.preventDefault();
    });
    update();
  });
}

function bindCopyButtons() {
  document.querySelectorAll("[data-copy-target]").forEach((button) => {
    button.addEventListener("click", async () => {
      const source = document.getElementById(button.dataset.copyTarget);
      if (!source) return;
      try {
        await navigator.clipboard.writeText(source.value || source.textContent || "");
      } catch (_error) {
        source.focus();
        source.select();
        document.execCommand("copy");
      }
      const originalLabel = button.dataset.copyLabel || button.textContent.trim();
      button.textContent = "Kopiert";
      const status = button.closest("section")?.querySelector("[data-copy-status]");
      if (status) status.textContent = "Prompt wurde in die Zwischenablage kopiert.";
      window.setTimeout(() => { button.textContent = originalLabel; }, 1600);
    });
  });
}

function bindPromptBuyerSelectors() {
  document.querySelectorAll("[data-prompt-buyer]").forEach((select) => {
    const prompt = document.getElementById(select.dataset.promptTarget);
    if (!prompt) return;

    const placeholder = "[KÄUFERNAME]";
    const template = prompt.value;
    const updatePrompt = () => {
      const buyerName = select.value || placeholder;
      prompt.value = template.split(placeholder).join(buyerName);
    };

    select.addEventListener("change", updatePrompt);
    updatePrompt();
  });
}

function bindFactorTooltips() {
  const segments = document.querySelectorAll(".factor-segment[data-tooltip]");
  if (!segments.length) return;
  const tooltip = document.createElement("div");
  tooltip.className = "factor-tooltip";
  tooltip.setAttribute("role", "tooltip");
  document.body.appendChild(tooltip);

  const show = (segment) => {
    tooltip.textContent = segment.dataset.tooltip;
    tooltip.classList.add("is-visible");
    const segmentRect = segment.getBoundingClientRect();
    const tooltipRect = tooltip.getBoundingClientRect();
    const left = Math.max(8, Math.min(window.innerWidth - tooltipRect.width - 8, segmentRect.left + segmentRect.width / 2 - tooltipRect.width / 2));
    const top = segmentRect.top >= tooltipRect.height + 10
      ? segmentRect.top - tooltipRect.height - 7
      : segmentRect.bottom + 7;
    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;
  };
  const hide = () => tooltip.classList.remove("is-visible");

  segments.forEach((segment) => {
    segment.addEventListener("mouseenter", () => show(segment));
    segment.addEventListener("mouseleave", hide);
    segment.addEventListener("focus", () => show(segment));
    segment.addEventListener("blur", hide);
  });
}
