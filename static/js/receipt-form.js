function bindAllocationControls(root) {
  root.querySelectorAll("[data-allocation]").forEach((allocation) => {
    if (allocation.dataset.bound === "true") return;
    allocation.dataset.bound = "true";

    const minShare = 0.0001;
    const people = allocation.querySelectorAll("[data-allocation-person]");
    const checkboxes = allocation.querySelectorAll("[data-allocation-checkbox]");
    const allButton = allocation.querySelector("[data-select-all]");
    const noneButton = allocation.querySelector("[data-select-none]");
    const totalNode = allocation.querySelector("[data-allocation-total]");

    const getControls = (person) => ({
      checkbox: person.querySelector("[data-allocation-checkbox]"),
      number: person.querySelector("[data-weight-number]"),
      slider: person.querySelector("[data-weight-slider]"),
      fixed: person.querySelector("[data-weight-fixed]"),
    });

    const isFixed = (person) => Boolean(getControls(person).fixed?.checked);

    const selectedPeople = () => Array.from(people).filter((person) => {
      const { checkbox } = getControls(person);
      return checkbox && checkbox.checked;
    });

    const parseShare = (value) => {
      const parsed = Number(String(value || "0").replace(",", "."));
      return Number.isFinite(parsed) ? parsed : 0;
    };

    const getShare = (person) => parseShare(person.dataset.share);

    const allocationIsValid = () => {
      const selected = selectedPeople();
      if (!selected.length) return true;
      const total = selected.reduce((sum, person) => sum + getShare(person), 0);
      return Math.abs(total - 1) < 0.00005;
    };

    const updateTotal = () => {
      const selected = selectedPeople();
      const total = selected.reduce((sum, person) => sum + getShare(person), 0);
      const valid = allocationIsValid();
      if (totalNode) {
        totalNode.textContent = selected.length ? `Summe: ${total.toFixed(4).replace(".", ",")}` : "Keine Zuordnung";
        totalNode.classList.toggle("is-valid", valid);
        totalNode.classList.toggle("is-invalid", !valid);
      }
      if (allButton) allButton.disabled = people.length === 0 || selected.length === people.length;
      if (noneButton) noneButton.disabled = selected.length === 0;
    };

    const setShare = (person, value) => {
      const { number, slider } = getControls(person);
      const safeValue = Math.max(0, Math.min(1, value));
      const formatted = safeValue.toFixed(4);
      person.dataset.share = formatted;
      if (number) number.value = formatted;
      if (slider) slider.value = formatted;
    };

    const equalizeSelectedShares = () => {
      const selected = selectedPeople();
      if (selected.length === 0) {
        people.forEach((person) => setShare(person, 0));
        return;
      }
      const equal = 1 / selected.length;
      let assigned = 0;
      selected.forEach((person, index) => {
        if (index === selected.length - 1) {
          setShare(person, 1 - assigned);
          return;
        }
        setShare(person, equal);
        assigned += getShare(person);
      });
    };

    const updatePerson = (person) => {
      const { checkbox, number, slider, fixed } = getControls(person);
      const state = person.querySelector("[data-allocation-state]");
      if (!checkbox) return;

      person.classList.toggle("is-selected", checkbox.checked);
      if (number) number.disabled = !checkbox.checked;
      if (slider) slider.disabled = !checkbox.checked;
      if (fixed) {
        fixed.disabled = !checkbox.checked;
        if (!checkbox.checked) fixed.checked = false;
      }
      person.classList.toggle("is-fixed", checkbox.checked && isFixed(person));
      if (state) {
        state.textContent = checkbox.checked ? "Ausgewählt" : "Nicht zugeordnet";
      }
    };

    const normalizeSelectedShares = () => {
      const selected = selectedPeople();
      if (selected.length === 0) {
        people.forEach((person) => {
          setShare(person, 0);
          updatePerson(person);
        });
        return;
      }

      const total = selected.reduce((sum, person) => sum + getShare(person), 0);
      if (total <= 0) {
        equalizeSelectedShares();
      } else {
        const next = selected.map((person) => getShare(person) / total);
        const minValue = selected.length > 1 ? minShare : 0;
        let lockedMinimum = 0;
        next.forEach((share, index) => {
          if (share < minValue) {
            lockedMinimum += minValue - share;
            next[index] = minValue;
          }
        });
        if (lockedMinimum) {
          const adjustable = next
            .map((share, index) => ({ share, index }))
            .filter((entry) => entry.share > minValue);
          const adjustableTotal = adjustable.reduce((sum, entry) => sum + entry.share, 0);
          adjustable.forEach((entry) => {
            next[entry.index] = entry.share - lockedMinimum * (entry.share / adjustableTotal);
          });
        }
        selected.forEach((person, index) => {
          setShare(person, next[index]);
        });
      }

      const selectedSet = new Set(selected);
      people.forEach((person) => {
        if (!selectedSet.has(person)) setShare(person, 0);
      });
      fixTotal(selected);
      people.forEach((person) => updatePerson(person));
    };

    const fixTotal = (selected, protectedPerson = null) => {
      if (!selected.length) return;
      const total = selected.reduce((sum, person) => sum + getShare(person), 0);
      const difference = 1 - total;
      if (Math.abs(difference) < 0.0000001) return;

      const target = selected.find((person) => person !== protectedPerson && !isFixed(person))
        || (protectedPerson && !isFixed(protectedPerson) ? protectedPerson : null);
      if (!target) return false;
      setShare(target, getShare(target) + difference);
      return true;
    };

    const distributeDeltaEvenly = (targets, delta) => {
      if (targets.length === 0 || Math.abs(delta) < 0.0000001) return;

      let remainingDelta = delta;
      let adjustable = [...targets];
      while (adjustable.length && Math.abs(remainingDelta) >= 0.0000001) {
        const shareDelta = remainingDelta / adjustable.length;
        const nextAdjustable = [];
        let applied = 0;

        adjustable.forEach((person) => {
          const current = getShare(person);
          const next = current + shareDelta;
          if (next < minShare) {
            const clampedDelta = minShare - current;
            setShare(person, minShare);
            applied += clampedDelta;
          } else {
            setShare(person, next);
            applied += shareDelta;
            nextAdjustable.push(person);
          }
        });

        remainingDelta -= applied;
        if (nextAdjustable.length === adjustable.length) break;
        adjustable = nextAdjustable;
      }
    };

    const rebalanceFromPerson = (changedPerson, targetShare) => {
      const selected = selectedPeople();
      if (selected.length === 0) return;
      if (selected.length === 1) {
        setShare(selected[0], 1);
        updatePerson(selected[0]);
        return;
      }

      const fixedOthers = selected.filter((person) => person !== changedPerson && isFixed(person));
      const adjustableOthers = selected.filter((person) => person !== changedPerson && !isFixed(person));
      const fixedTotal = fixedOthers.reduce((sum, person) => sum + getShare(person), 0);
      if (!adjustableOthers.length) {
        setShare(changedPerson, Math.max(minShare, 1 - fixedTotal));
        updateTotal();
        return;
      }
      const maxShare = 1 - fixedTotal - minShare * adjustableOthers.length;
      const oldShare = getShare(changedPerson);
      const nextShare = Math.max(minShare, Math.min(maxShare, targetShare));
      const delta = nextShare - oldShare;
      if (Math.abs(delta) < 0.0000001) {
        setShare(changedPerson, nextShare);
        return;
      }

      setShare(changedPerson, nextShare);
      distributeDeltaEvenly(adjustableOthers, -delta);
      fixTotal(selected, changedPerson);
      updateTotal();
    };

    people.forEach((person) => {
      const { checkbox, slider, number, fixed } = getControls(person);

      if (checkbox) {
        checkbox.addEventListener("change", () => {
          const selected = selectedPeople();
          if (checkbox.checked) {
            const adjustable = selected.filter((entry) => entry !== person && !isFixed(entry));
            if (selected.length > 1 && !adjustable.length) {
              checkbox.checked = false;
              setShare(person, 0);
              people.forEach((entry) => updatePerson(entry));
              updateTotal();
              return;
            }
            setShare(person, 0);
            rebalanceFromPerson(person, 1 / selected.length);
          } else {
            const removedShare = getShare(person);
            const adjustable = selected.filter((entry) => !isFixed(entry));
            if (selected.length && !adjustable.length) {
              checkbox.checked = true;
              people.forEach((entry) => updatePerson(entry));
              updateTotal();
              return;
            }
            setShare(person, 0);
            distributeDeltaEvenly(adjustable, removedShare);
            fixTotal(selected);
          }
          people.forEach((entry) => updatePerson(entry));
          updateTotal();
        });
      }

      fixed?.addEventListener("change", () => {
        updatePerson(person);
        updateTotal();
      });

      if (slider && number) {
        const initialValue = parseShare(number.value);
        if (!Number.isNaN(initialValue) && initialValue > 0) {
          person.dataset.share = String(initialValue);
        }

        slider.addEventListener("input", () => {
          rebalanceFromPerson(person, parseShare(slider.value));
        });

        number.addEventListener("change", () => {
          const value = parseShare(number.value);
          if (Number.isNaN(value) || value <= 0) return;
          rebalanceFromPerson(person, value);
        });
      }

      updatePerson(person);
    });

    normalizeSelectedShares();
    updateTotal();

    if (allButton) {
      allButton.addEventListener("click", () => {
        people.forEach((person) => {
          const { fixed } = getControls(person);
          if (fixed) fixed.checked = false;
        });
        checkboxes.forEach((checkbox) => {
          checkbox.checked = true;
        });
        equalizeSelectedShares();
        people.forEach((person) => updatePerson(person));
        updateTotal();
      });
    }

    if (noneButton) {
      noneButton.addEventListener("click", () => {
        checkboxes.forEach((checkbox) => {
          checkbox.checked = false;
        });
        normalizeSelectedShares();
        updateTotal();
      });
    }

    const form = allocation.closest("form");
    form?.addEventListener("submit", (event) => {
      updateTotal();
      if (allocationIsValid()) return;
      event.preventDefault();
      totalNode?.scrollIntoView({ behavior: "smooth", block: "center" });
      totalNode?.setAttribute("title", "Die ausgewählten Faktoren müssen zusammen genau 1,0000 ergeben.");
    });
  });
}

function bindDynamicRows() {
  const form = document.querySelector("[data-row-form]");
  if (!form) return;

  const rows = form.querySelector("[data-rows]");
  const countInput = form.querySelector("[data-row-count]");
  const template = form.querySelector("[data-row-template]");
  const addButton = form.querySelector("[data-add-row]");

  if (!rows || !countInput || !template || !addButton) return;

  addButton.addEventListener("click", () => {
    const index = Number(countInput.value || "0");
    const wrapper = document.createElement("div");
    wrapper.innerHTML = template.innerHTML.replaceAll("__index__", String(index)).trim();
    const node = wrapper.firstElementChild;
    rows.appendChild(node);
    countInput.value = String(index + 1);
    bindAllocationControls(node);
    bindRowActions(node);
  });
}

function bindReceiptTotal() {
  const form = document.querySelector("[data-row-form]");
  const totalNode = form?.querySelector("[data-receipt-total]");
  if (!form || !totalNode) return;

  const priceCents = (value) => {
    const normalized = String(value || "")
      .replace(/€/g, "")
      .replace(/\s/g, "")
      .replace(/\./g, "")
      .replace(",", ".");
    const amount = Number(normalized);
    return Number.isFinite(amount) ? Math.round(amount * 100) : 0;
  };

  const update = () => {
    const total = [...form.querySelectorAll("[data-row]:not(.is-deleted)")].reduce((sum, row) => {
      const price = row.querySelector('input[name$="-price"]');
      return sum + priceCents(price?.value);
    }, 0);
    totalNode.textContent = `${(total / 100).toFixed(2).replace(".", ",")} €`;
  };

  form.addEventListener("input", (event) => {
    if (event.target.matches('input[name$="-price"]')) update();
  });
  form.addEventListener("click", (event) => {
    if (event.target.closest("[data-add-row], [data-remove-row], [data-delete-existing]")) {
      queueMicrotask(update);
    }
  });
  update();
}

function bindMarketComboboxes(root = document) {
  root.querySelectorAll("[data-market-combobox]").forEach((combobox) => {
    if (combobox.dataset.bound === "true") return;
    combobox.dataset.bound = "true";

    const input = combobox.querySelector("[data-market-input]");
    const dropdown = combobox.querySelector("[data-market-options]");
    const preview = combobox.querySelector("[data-market-preview]");
    const options = [...combobox.querySelectorAll("[data-market-option]")];
    const newOption = combobox.querySelector("[data-market-new-option]");
    if (!input || !dropdown || !preview || !newOption) return;

    let activeIndex = -1;
    const normalized = (value) => String(value || "").trim().toLocaleLowerCase("de");

    const updatePreview = () => {
      const value = input.value.trim();
      const exact = options.find((option) => normalized(option.dataset.name) === normalized(value));
      const noIcon = exact?.dataset.noIcon === "true";
      preview.replaceChildren();
      preview.hidden = noIcon;
      combobox.classList.toggle("has-no-preview", noIcon);
      preview.classList.toggle("is-fallback", !noIcon && !exact?.dataset.logo);
      if (noIcon) {
        return;
      } else if (exact?.dataset.logo) {
        const image = document.createElement("img");
        image.src = exact.dataset.logo;
        image.alt = "";
        preview.append(image);
      } else {
        preview.textContent = exact?.dataset.fallback
          || value.charAt(0).toLocaleUpperCase("de")
          || "?";
      }
    };

    const visibleChoices = () => [
      ...options.filter((option) => !option.hidden),
      ...(newOption.hidden ? [] : [newOption]),
    ];

    const setActive = (index) => {
      const choices = visibleChoices();
      choices.forEach((choice) => {
        choice.classList.remove("is-active");
        choice.setAttribute("aria-selected", "false");
      });
      if (!choices.length) {
        activeIndex = -1;
        return;
      }
      activeIndex = Math.max(0, Math.min(index, choices.length - 1));
      choices[activeIndex].classList.add("is-active");
      choices[activeIndex].setAttribute("aria-selected", "true");
      choices[activeIndex].scrollIntoView({ block: "nearest" });
    };

    const filterOptions = () => {
      const query = normalized(input.value);
      let hasExact = false;
      options.forEach((option) => {
        const name = normalized(option.dataset.name);
        option.hidden = Boolean(query) && !name.includes(query);
        if (name === query) hasExact = true;
      });
      const allowNew = combobox.dataset.allowNew !== "false";
      newOption.hidden = !allowNew || !query || hasExact;
      newOption.textContent = input.value.trim()
        ? `Neuen Markt verwenden: ${input.value.trim()}`
        : "";
      activeIndex = -1;
    };

    const openDropdown = () => {
      filterOptions();
      dropdown.hidden = false;
      input.setAttribute("aria-expanded", "true");
    };

    const closeDropdown = () => {
      dropdown.hidden = true;
      input.setAttribute("aria-expanded", "false");
      activeIndex = -1;
    };

    const selectOption = (option) => {
      if (option !== newOption) input.value = option.dataset.name;
      updatePreview();
      closeDropdown();
      input.focus();
      input.dispatchEvent(new Event("change", { bubbles: true }));
      input.dispatchEvent(new Event("input", { bubbles: true }));
    };

    options.forEach((option) => {
      option.addEventListener("mousedown", (event) => event.preventDefault());
      option.addEventListener("click", () => selectOption(option));
    });
    newOption.addEventListener("mousedown", (event) => event.preventDefault());
    newOption.addEventListener("click", () => selectOption(newOption));

    input.addEventListener("focus", openDropdown);
    input.addEventListener("click", openDropdown);
    input.addEventListener("input", () => {
      updatePreview();
      openDropdown();
    });
    input.addEventListener("keydown", (event) => {
      const choices = visibleChoices();
      if (event.key === "ArrowDown") {
        event.preventDefault();
        if (dropdown.hidden) openDropdown();
        setActive(activeIndex + 1);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        if (dropdown.hidden) openDropdown();
        setActive(activeIndex < 0 ? choices.length - 1 : activeIndex - 1);
      } else if (event.key === "Enter" && !dropdown.hidden && activeIndex >= 0) {
        event.preventDefault();
        selectOption(visibleChoices()[activeIndex]);
      } else if (event.key === "Escape") {
        closeDropdown();
      }
    });
    input.addEventListener("blur", () => window.setTimeout(closeDropdown, 100));
    updatePreview();
  });
}

function iconMarkup(name) {
  return `<svg class="icon" aria-hidden="true" focusable="false"><use href="#icon-${name}"></use></svg>`;
}

function setRowInputsDisabled(row, disabled) {
  row.querySelectorAll("input, select, textarea").forEach((input) => {
    if (input.matches("[data-delete-input]") || input.name.endsWith("-id")) return;
    input.disabled = disabled;
  });
}

function bindRowActions(root) {
  root.querySelectorAll("[data-remove-row]").forEach((button) => {
    button.addEventListener("click", () => {
      const row = button.closest("[data-row]");
      if (row) row.remove();
    });
  });

  root.querySelectorAll("[data-delete-existing]").forEach((button) => {
    button.addEventListener("click", () => {
      const row = button.closest("[data-row]");
      if (!row) return;
      const deleteInput = row.querySelector("[data-delete-input]");
      const shouldDelete = !row.classList.contains("is-deleted");
      row.classList.toggle("is-deleted", shouldDelete);
      if (deleteInput) deleteInput.value = shouldDelete ? "on" : "";
      button.innerHTML = shouldDelete
        ? `${iconMarkup("restore")} Löschen zurücknehmen`
        : `${iconMarkup("trash")} Artikel löschen`;
      setRowInputsDisabled(row, shouldDelete);
    });
  });

  root.querySelectorAll("[data-row].is-deleted").forEach((row) => {
    setRowInputsDisabled(row, true);
  });
}
