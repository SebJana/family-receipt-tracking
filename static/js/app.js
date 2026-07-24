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
      if (!totalNode) return;
      const selected = selectedPeople();
      const total = selected.reduce((sum, person) => sum + getShare(person), 0);
      const valid = allocationIsValid();
      totalNode.textContent = selected.length ? `Summe: ${total.toFixed(4).replace(".", ",")}` : "Keine Zuordnung";
      totalNode.classList.toggle("is-valid", valid);
      totalNode.classList.toggle("is-invalid", !valid);
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

function chartColors(count) {
  const palette = ["#1d6f5f", "#d14d35", "#5b6ee1", "#c58a18", "#2d9cdb", "#7a5c9e"];
  return Array.from({ length: count }, (_, index) => palette[index % palette.length]);
}

function marketColors(logos) {
  const brandColors = {
    "kaufland.svg": "#e10915",
    "rewe.svg": "#cc071e",
    "norma.svg": "#fa9e00cb",
    "netto.svg": "#ffd400",
    "lidl.svg": "#0050aa",
    "aldi.svg": "#00a8e0",
    "penny.svg": "#e30613",
    "dm.svg": "#002e6d",
    "rossmann.svg": "#d71920",
    "edeka.svg": "#1f35dc",
    "mcdonalds.svg": "#ffbc0d",
    "burger-king.svg": "#d62300",
    "kfc.svg": "#e4002b",
    "subway.svg": "#008c15",
    "dominos.svg": "#006491",
    "pizza-hut.svg": "#e31837",
    "five-guys.svg": "#d71920",
    "dunkin.svg": "#f58220",
    "lieferando.png": "#ff8000",
  };
  return logos.map((logo) => brandColors[logo] || "#1d6f5f");
}

function chartBadgePlugin(images, badges = []) {
  return {
    id: "marketLogos",
    afterDatasetsDraw(chart) {
      const arcs = chart.getDatasetMeta(0).data;
      arcs.forEach((arc, index) => {
        const image = images[index];
        const badge = badges[index] || {};
        const imageReady = image?.complete && image.naturalWidth;
        const angle = arc.endAngle - arc.startAngle;
        const radius = (arc.innerRadius + arc.outerRadius) / 2;
        const availableArc = angle * radius;
        // Badges are omitted when a slice cannot contain them without obscuring its shape.
        const size = Math.min(42, (arc.outerRadius - arc.innerRadius) * 0.72, availableArc * 0.58);
        if (size < 18) return;

        const middleAngle = (arc.startAngle + arc.endAngle) / 2;
        const x = arc.x + Math.cos(middleAngle) * radius;
        const y = arc.y + Math.sin(middleAngle) * radius;
        const boxWidth = size * 1.35;
        const boxHeight = size;
        const context = chart.ctx;

        context.save();
        if (imageReady) {
          const imageRatio = image.naturalWidth / image.naturalHeight;
          const drawWidth = imageRatio > boxWidth / boxHeight ? boxWidth : boxHeight * imageRatio;
          const drawHeight = imageRatio > boxWidth / boxHeight ? boxWidth / imageRatio : boxHeight;
          // A contour preserves icon contrast without covering the slice with a badge box.
          context.filter = "drop-shadow(1px 0 0 #fff) drop-shadow(-1px 0 0 #fff) drop-shadow(0 1px 0 #fff) drop-shadow(0 -1px 0 #fff)";
          context.drawImage(image, x - drawWidth / 2, y - drawHeight / 2, drawWidth, drawHeight);
        } else {
          const label = String(badge.initials || chart.data.labels[index] || "?").trim();
          context.fillStyle = badge.emoji ? "#18202a" : (badge.color || "#18202a");
          context.font = `${badge.emoji ? "500" : "800"} ${Math.max(14, size * (badge.emoji ? 0.72 : 0.55))}px system-ui`;
          context.textAlign = "center";
          context.textBaseline = "middle";
          const badgeLabel = badge.initials || label[0] || "?";
          const renderedLabel = badge.emoji ? badgeLabel : badgeLabel.toLocaleUpperCase();
          context.lineJoin = "round";
          context.lineWidth = Math.max(2, size * 0.1);
          context.strokeStyle = "#fff";
          context.strokeText(renderedLabel, x, y);
          context.fillText(renderedLabel, x, y);
        }
        context.restore();
      });
    },
  };
}

function bindDatePresets() {
  document.querySelectorAll("[data-date-preset]").forEach((select) => {
    const form = select.closest("form");
    const dateFrom = form?.querySelector("[data-date-from]");
    const dateTo = form?.querySelector("[data-date-to]");
    if (!dateFrom || !dateTo) return;

    const syncSelection = () => {
      const matchingOption = Array.from(select.options).find(
        (option) => option.dataset.from === dateFrom.value && option.dataset.to === dateTo.value,
      );
      select.value = matchingOption?.value || "";
    };

    select.addEventListener("change", () => {
      const option = select.selectedOptions[0];
      if (!option?.dataset.from) return;
      dateFrom.value = option.dataset.from;
      dateTo.value = option.dataset.to;
      form.requestSubmit();
    });
    dateFrom.addEventListener("change", syncSelection);
    dateTo.addEventListener("change", syncSelection);
    syncSelection();
  });
}

function bindLiveFilters() {
  document.querySelectorAll("form[data-live-filter]").forEach((form) => {
    let typingTimer;
    let activeRequest;

    const updateResults = async () => {
      const targetSelector = form.dataset.liveResultsTarget;
      if (!targetSelector) {
        form.requestSubmit();
        return;
      }

      activeRequest?.abort();
      activeRequest = new AbortController();
      const url = new URL(form.action || window.location.href, window.location.href);
      url.search = new URLSearchParams(new FormData(form)).toString();

      try {
        const response = await fetch(url, { signal: activeRequest.signal });
        if (!response.ok) throw new Error(`Filter request failed: ${response.status}`);
        const documentCopy = new DOMParser().parseFromString(await response.text(), "text/html");
        const currentTarget = document.querySelector(targetSelector);
        const newTarget = documentCopy.querySelector(targetSelector);
        if (!currentTarget || !newTarget) throw new Error("Filter result target missing");
        currentTarget.innerHTML = newTarget.innerHTML;
        window.htmx?.process(currentTarget);
        window.history.replaceState({}, "", url);
      } catch (error) {
        if (error.name !== "AbortError") window.location.assign(url);
      }
    };

    form.querySelectorAll("select:not([data-date-preset]), input[type='date']").forEach((control) => {
      control.addEventListener("change", updateResults);
    });

    form.querySelectorAll("input[type='text'], input:not([type])").forEach((control) => {
      control.addEventListener("input", () => {
        window.clearTimeout(typingTimer);
        typingTimer = window.setTimeout(updateResults, 350);
      });
    });
  });
}

function bindCharts() {
  if (!window.Chart) return;

  document.querySelectorAll("canvas[data-chart]").forEach((canvas) => {
    const source = document.getElementById(canvas.dataset.source);
    if (!source) return;
    const data = JSON.parse(source.textContent);
    const type = canvas.dataset.chart;
    const badgeData = canvas.dataset.logoBase
      ? (data.logos || []).map(() => ({ background: "#ffffff" }))
      : (canvas.hasAttribute("data-person-avatars") ? (data.avatars || []) : (canvas.hasAttribute("data-category-emojis") ? (data.badges || []) : []));
    const badgeUrls = canvas.dataset.logoBase
      ? (data.logos || []).map((filename) => filename ? canvas.dataset.logoBase + filename : "")
      : badgeData.map((badge) => badge.url || "");
    const badgeImages = badgeUrls.map((url) => {
          if (!url) return null;
          const image = new Image();
          image.addEventListener("load", () => Chart.getChart(canvas)?.draw());
          image.src = url;
          return image;
        });

    if (type === "stacked") {
      new Chart(canvas, {
        type: "bar",
        data: {
          labels: data.labels,
          datasets: data.datasets.map((dataset, index) => ({
            ...dataset,
            backgroundColor: data.colors?.[index] || chartColors(data.datasets.length)[index],
          })),
        },
        options: {
          responsive: true,
          scales: {
            x: { stacked: true },
            y: { stacked: true, beginAtZero: true },
          },
        },
      });
      return;
    }

    new Chart(canvas, {
      type,
      data: {
        labels: data.labels,
        datasets: [
          {
            data: data.values,
            backgroundColor: data.logos
              ? marketColors(data.logos)
              : (data.colors || chartColors(data.labels.length)),
            borderColor: "#ffffff",
            borderWidth: 2,
          },
        ],
      },
      options: {
        responsive: true,
        plugins: { legend: { display: type !== "bar", position: "bottom" } },
        scales: type === "bar" ? { y: { beginAtZero: true } } : {},
      },
      plugins: badgeImages.length ? [chartBadgePlugin(badgeImages, badgeData)] : [],
    });
  });
}

function bindConfirmForms() {
  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) {
        event.preventDefault();
      }
    });
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

function bindAvatarUploads() {
  document.querySelectorAll("[data-avatar-upload]").forEach((input) => {
    input.addEventListener("change", () => {
      if (!input.files?.length) return;
      const picker = input.closest("[data-avatar-picker]");
      const uploadChoice = picker?.querySelector('input[type="radio"][value="upload"]');
      const uploadOption = input.closest(".avatar-upload-option");
      if (uploadChoice) {
        uploadChoice.checked = true;
        const previewUrl = URL.createObjectURL(input.files[0]);
        const currentPreview = uploadOption?.querySelector(".person-avatar");
        if (currentPreview) {
          const previewImage = document.createElement("img");
          previewImage.className = "person-avatar avatar-upload-preview";
          previewImage.src = previewUrl;
          previewImage.alt = "Vorschau des eigenen Avatarbilds";
          currentPreview.replaceWith(previewImage);
        }
        const uploadLabel = uploadOption?.querySelector(".avatar-upload-label");
        if (uploadLabel) uploadLabel.textContent = "Bild ändern";
        previewPersonAvatar(picker, previewUrl, true);
      }
    });
  });
}

function previewPersonAvatar(picker, imageUrl = "", isImage = false) {
  if (!picker) return;
  const personId = picker.dataset.personId;
  const personName = picker.dataset.personName;
  const checked = picker.querySelector('input[type="radio"]:checked');
  const option = checked?.closest(".avatar-option");
  const sourceImage = option?.querySelector("img");
  const sourceInitials = option?.querySelector(".person-avatar-initials");
  const useImage = isImage || Boolean(sourceImage);
  const sourceUrl = imageUrl || sourceImage?.src || "";

  document.querySelectorAll(`[data-person-avatar="${personId}"]`).forEach((current) => {
    const replacement = document.createElement(useImage ? "img" : "span");
    replacement.className = `person-avatar${current.classList.contains("person-avatar-small") ? " person-avatar-small" : ""}${sourceImage?.classList.contains("animal-avatar") ? " animal-avatar" : ""}${useImage ? "" : " person-avatar-initials"}`;
    replacement.dataset.personAvatar = personId;
    if (useImage) {
      replacement.src = sourceUrl;
      replacement.alt = `Avatar von ${personName}`;
    } else {
      replacement.textContent = sourceInitials?.textContent?.trim() || "";
      replacement.style.background = sourceInitials?.style.background || "";
      replacement.setAttribute("aria-label", `Avatar von ${personName}`);
    }
    current.replaceWith(replacement);
  });
}

function bindAvatarChoices() {
  document.querySelectorAll("[data-avatar-picker]").forEach((picker) => {
    picker.querySelectorAll('input[type="radio"]').forEach((choice) => {
      choice.addEventListener("change", () => {
        if (choice.value !== "upload") previewPersonAvatar(picker);
      });
    });
  });
}

function bindAvatarDialogs() {
  document.querySelectorAll("[data-avatar-open]").forEach((button) => {
    button.addEventListener("click", () => {
      document.getElementById(button.dataset.avatarOpen)?.showModal();
    });
  });
  document.querySelectorAll(".avatar-dialog").forEach((dialog) => {
    dialog.querySelectorAll("[data-avatar-close]").forEach((button) => {
      button.addEventListener("click", () => dialog.close());
    });
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });
  });
}

function bindCategoryGame() {
  const game = document.querySelector("[data-category-game]");
  if (!game) return;
  const csrf = document.querySelector('[name="csrfmiddlewaretoken"]')?.value || "";
  const count = document.querySelector("[data-unassigned-count]");
  const pool = game.querySelector("[data-item-pool]");
  let dragged = null;

  async function update(action, article, categoryId = "") {
    const body = new FormData();
    body.set("csrfmiddlewaretoken", csrf);
    body.set("action", action);
    body.set("article", article);
    if (categoryId) body.set("category_id", categoryId);
    const response = await fetch(window.location.href, { method: "POST", body, headers: { "X-Requested-With": "XMLHttpRequest" } });
    if (!response.ok) throw new Error("Kategorie konnte nicht aktualisiert werden.");
    return response.json();
  }

  game.querySelectorAll(".category-item").forEach((item) => {
    item.addEventListener("dragstart", () => { dragged = item; item.classList.add("dragging"); });
    item.addEventListener("dragend", () => { item.classList.remove("dragging"); dragged = null; });
  });
  game.querySelectorAll("[data-dropzone]").forEach((zone) => {
    zone.addEventListener("dragover", (event) => { event.preventDefault(); zone.classList.add("drag-over"); });
    zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
    zone.addEventListener("drop", async (event) => {
      event.preventDefault(); zone.classList.remove("drag-over");
      if (!dragged) return;
      const droppedItem = dragged;
      const card = zone.closest("[data-category-id]");
      const article = droppedItem.dataset.article;
      try {
        const result = await update("assign", article, card.dataset.categoryId);
        droppedItem.remove(); count.textContent = result.remaining;
        const contents = card.querySelector("[data-category-contents]");
        contents.querySelector(".empty")?.remove();
        const row = document.createElement("div");
        row.className = "category-assigned-item"; row.dataset.article = article;
        row.innerHTML = `<span></span><button type="button" class="text-button" data-clear-item>Entfernen</button>`;
        row.querySelector("span").textContent = article;
        contents.append(row);
        card.querySelector("[data-category-count]").textContent = contents.querySelectorAll(".category-assigned-item").length;
        bindClear(row);
        if (!pool.querySelector(".category-item")) pool.innerHTML = '<p class="empty">🎉 Alles einsortiert!</p>';
      } catch (error) { window.alert(error.message); }
    });
  });
  function bindClear(row) {
    row.querySelector("[data-clear-item]")?.addEventListener("click", async () => {
      try { await update("clear", row.dataset.article); window.location.reload(); }
      catch (error) { window.alert(error.message); }
    });
  }
  game.querySelectorAll(".category-assigned-item").forEach(bindClear);
}

function bindCategoryAssignmentPage() {
  if (!document.querySelector("[data-category-panel]")) return;
  document.querySelectorAll("[data-category-tab]").forEach((tab) => tab.addEventListener("click", () => {
    document.querySelectorAll("[data-category-tab]").forEach((item) => {
      const active = item === tab;
      item.classList.toggle("active", active);
      item.setAttribute("aria-selected", active ? "true" : "false");
    });
    document.querySelectorAll("[data-category-panel]").forEach((panel) => { panel.hidden = panel.dataset.categoryPanel !== tab.dataset.categoryTab; });
  }));

  const picker = document.querySelector("[data-emoji-picker]");
  const emojiInput = document.querySelector("#category-emoji");
  const openCreateEmojiPicker = () => {
    picker.hidden = false;
    window.requestAnimationFrame(() => picker.querySelector("[data-emoji-search]")?.focus());
  };
  const segmenter = window.Intl?.Segmenter ? new Intl.Segmenter("de", { granularity: "grapheme" }) : null;
  emojiInput?.addEventListener("input", () => {
    // Grapheme segmentation treats flags and joined emoji as one visible category icon.
    let symbol = emojiInput.value;
    const graphemes = segmenter ? [...segmenter.segment(symbol)].map((part) => part.segment) : Array.from(symbol);
    symbol = graphemes[0] || "";
    if (/^\p{L}$/u.test(symbol)) symbol = symbol.toLocaleUpperCase("de");
    const valid = /^\p{Lu}$/u.test(symbol) || /\p{Extended_Pictographic}/u.test(symbol) || /^\p{Regional_Indicator}{2}$/u.test(symbol);
    emojiInput.value = valid ? symbol : "";
  });
  document.querySelector("[data-emoji-toggle]")?.addEventListener("click", () => {
    if (picker.hidden) openCreateEmojiPicker(); else picker.hidden = true;
  });
  emojiInput?.addEventListener("click", openCreateEmojiPicker);
  document.addEventListener("click", (event) => {
    if (picker && !event.target.closest(".emoji-field")) picker.hidden = true;
  });
  picker?.querySelectorAll("button").forEach((button) => button.addEventListener("click", () => {
    emojiInput.value = button.textContent.trim(); picker.hidden = true; emojiInput.focus();
  }));
  picker?.querySelector("[data-emoji-search]")?.addEventListener("input", (event) => {
    const query = event.target.value.trim().toLocaleLowerCase("de");
    let visible = 0;
    picker.querySelectorAll("[data-keywords]").forEach((button) => {
      const matches = !query || button.dataset.keywords.toLocaleLowerCase("de").includes(query);
      button.hidden = !matches;
      if (matches) visible += 1;
    });
    picker.querySelector("[data-emoji-no-results]").hidden = visible !== 0;
  });

  document.querySelectorAll("[data-category-edit-open]").forEach((button) => button.addEventListener("click", () => {
    document.getElementById(button.dataset.categoryEditOpen)?.showModal();
  }));
  document.querySelectorAll(".category-edit-dialog").forEach((dialog) => {
    const symbolInput = dialog.querySelector("[data-edit-category-symbol]");
    const editPicker = dialog.querySelector("[data-edit-emoji-picker]");
    dialog.querySelectorAll("[data-category-edit-close]").forEach((button) => button.addEventListener("click", () => dialog.close()));
    dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
    const openEditEmojiPicker = () => {
      editPicker.hidden = false;
      window.requestAnimationFrame(() => editPicker.querySelector("[data-edit-emoji-search]")?.focus());
    };
    dialog.querySelector("[data-edit-emoji-toggle]")?.addEventListener("click", () => {
      if (editPicker.hidden) openEditEmojiPicker(); else editPicker.hidden = true;
    });
    symbolInput?.addEventListener("click", openEditEmojiPicker);
    symbolInput?.addEventListener("input", () => {
      const graphemes = segmenter ? [...segmenter.segment(symbolInput.value)].map((part) => part.segment) : Array.from(symbolInput.value);
      let symbol = graphemes[0] || "";
      if (/^\p{L}$/u.test(symbol)) symbol = symbol.toLocaleUpperCase("de");
      const valid = /^\p{Lu}$/u.test(symbol) || /\p{Extended_Pictographic}/u.test(symbol) || /^\p{Regional_Indicator}{2}$/u.test(symbol);
      symbolInput.value = valid ? symbol : "";
    });
    editPicker.querySelectorAll("[data-keywords]").forEach((button) => button.addEventListener("click", () => {
      symbolInput.value = button.textContent.trim(); editPicker.hidden = true; symbolInput.focus();
    }));
    editPicker.querySelector("[data-edit-emoji-search]")?.addEventListener("input", (event) => {
      const query = event.target.value.trim().toLocaleLowerCase("de");
      let visible = 0;
      editPicker.querySelectorAll("[data-keywords]").forEach((button) => {
        const matches = !query || button.dataset.keywords.toLocaleLowerCase("de").includes(query);
        button.hidden = !matches;
        if (matches) visible += 1;
      });
      editPicker.querySelector("[data-edit-emoji-no-results]").hidden = visible !== 0;
    });
    document.addEventListener("click", (event) => {
      if (!event.target.closest(".edit-emoji-field")) editPicker.hidden = true;
    });
  });

  document.querySelectorAll("[data-category-items-open]").forEach((button) => button.addEventListener("click", () => {
    document.getElementById(button.dataset.categoryItemsOpen)?.showModal();
  }));
  document.querySelectorAll(".category-items-dialog").forEach((dialog) => {
    dialog.querySelector("[data-category-items-close]")?.addEventListener("click", () => dialog.close());
    dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
    dialog.querySelector("[data-category-item-search]")?.addEventListener("input", (event) => {
      const query = event.target.value.trim().toLocaleLowerCase("de");
      let visible = 0;
      dialog.querySelectorAll(".category-assigned-item").forEach((row) => {
        const matches = !query || row.dataset.article.toLocaleLowerCase("de").includes(query);
        row.hidden = !matches;
        if (matches) visible += 1;
      });
      dialog.querySelector("[data-category-search-empty]").hidden = visible !== 0 || !query;
    });
  });

  const game = document.querySelector("[data-category-game]");
  const undoButton = game?.querySelector("[data-assignment-undo]");
  const skipButton = game?.querySelector("[data-assignment-skip]");
  let lastAssignment = null;
  const csrf = document.querySelector('[name="csrfmiddlewaretoken"]')?.value || "";
  async function update(action, article, categoryId = "") {
    const body = new FormData();
    body.set("csrfmiddlewaretoken", csrf); body.set("action", action); body.set("article", article);
    if (categoryId) body.set("category_id", categoryId);
    const response = await fetch(window.location.href, { method: "POST", body, headers: { "X-Requested-With": "XMLHttpRequest" } });
    if (!response.ok) throw new Error("Kategorie konnte nicht aktualisiert werden.");
    return response.json();
  }
  function bindCategoryClear(row) {
    row.querySelector("[data-clear-item]")?.addEventListener("click", async () => {
      try {
        const result = await update("clear", row.dataset.article);
        const card = row.closest("[data-category-id]");
        row.remove();
        card.querySelector("[data-category-count]").textContent = card.querySelectorAll(".category-assigned-item").length;
        document.querySelector("[data-unassigned-count]").textContent = result.remaining;
        document.querySelector(".tab-count").textContent = result.remaining;
        if (lastAssignment?.article === row.dataset.article) {
          lastAssignment = null;
          undoButton.hidden = true;
        }
        if (!card.querySelector(".category-assigned-item")) card.querySelector("[data-category-contents]").innerHTML = '<p class="empty" data-category-empty>Noch leer</p>';
        if (game && result.next_article) {
          game.querySelector("[data-current-article]").textContent = result.next_article;
          game.querySelector("[data-current-item]").hidden = false;
          skipButton.hidden = false;
          game.querySelector("[data-assignment-categories]").hidden = false;
          game.querySelector("[data-assignment-complete]").hidden = true;
        }
      } catch (error) { window.alert(error.message); }
    });
  }
  function addCategoryItem(categoryId, article) {
    // The management tab mirrors assignments immediately so its counts remain trustworthy
    // when tabs are changed without a page reload.
    const card = document.querySelector(`[data-category-id="${categoryId}"]`);
    if (!card) return;
    const contents = card.querySelector("[data-category-contents]");
    contents.querySelector("[data-category-empty]")?.remove();
    const row = document.createElement("div");
    row.className = "category-assigned-item";
    row.dataset.article = article;
    const label = document.createElement("span");
    label.textContent = article;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "button secondary small";
    remove.dataset.clearItem = "";
    remove.textContent = "Entfernen";
    row.append(label, remove);
    contents.append(row);
    card.querySelector("[data-category-count]").textContent = card.querySelectorAll(".category-assigned-item").length;
    bindCategoryClear(row);
  }
  game?.querySelectorAll("[data-assign-category]").forEach((button) => button.addEventListener("click", async () => {
    const articleNode = game.querySelector("[data-current-article]");
    const article = articleNode.textContent.trim();
    if (!article) return;
    const choices = game.querySelectorAll("[data-assign-category]");
    choices.forEach((choice) => { choice.disabled = true; });
    try {
      const result = await update("assign", article, button.dataset.assignCategory);
      document.querySelector("[data-unassigned-count]").textContent = result.remaining;
      document.querySelector(".tab-count").textContent = result.remaining;
      addCategoryItem(button.dataset.assignCategory, article);
      lastAssignment = { article, categoryId: button.dataset.assignCategory };
      undoButton.hidden = false;
      if (result.next_article) articleNode.textContent = result.next_article;
      else {
        game.querySelector("[data-current-item]").hidden = true;
        skipButton.hidden = true;
        game.querySelector("[data-assignment-categories]").hidden = true;
        game.querySelector("[data-assignment-complete]").hidden = false;
      }
    } catch (error) { window.alert(error.message); }
    finally { choices.forEach((choice) => { choice.disabled = false; }); }
  }));
  skipButton?.addEventListener("click", async () => {
    const articleNode = game.querySelector("[data-current-article]");
    const article = articleNode.textContent.trim();
    if (!article) return;
    skipButton.disabled = true;
    try {
      const result = await update("skip", article);
      if (result.next_article) articleNode.textContent = result.next_article;
    } catch (error) { window.alert(error.message); }
    finally { skipButton.disabled = false; }
  });
  undoButton?.addEventListener("click", async () => {
    if (!lastAssignment) return;
    undoButton.disabled = true;
    try {
      const result = await update("clear", lastAssignment.article);
      const card = document.querySelector(`[data-category-id="${lastAssignment.categoryId}"]`);
      const assignedRow = [...(card?.querySelectorAll(".category-assigned-item") || [])].find((row) => row.dataset.article === lastAssignment.article);
      assignedRow?.remove();
      if (card) {
        card.querySelector("[data-category-count]").textContent = card.querySelectorAll(".category-assigned-item").length;
        if (!card.querySelector(".category-assigned-item")) card.querySelector("[data-category-contents]").innerHTML = '<p class="empty" data-category-empty>Noch leer</p>';
      }
      document.querySelector("[data-unassigned-count]").textContent = result.remaining;
      document.querySelector(".tab-count").textContent = result.remaining;
      // The restored article is shown again because undo should permit an immediate
      // correction rather than sending the item back into a random queue position.
      game.querySelector("[data-current-article]").textContent = lastAssignment.article;
      game.querySelector("[data-current-item]").hidden = false;
      skipButton.hidden = false;
      game.querySelector("[data-assignment-categories]").hidden = false;
      game.querySelector("[data-assignment-complete]").hidden = true;
      lastAssignment = null;
      undoButton.hidden = true;
    } catch (error) { window.alert(error.message); }
    finally { undoButton.disabled = false; }
  });
  document.querySelectorAll(".category-assigned-item").forEach(bindCategoryClear);
}

document.addEventListener("DOMContentLoaded", () => {
  bindDatePresets();
  bindLiveFilters();
  bindAllocationControls(document);
  bindDynamicRows();
  bindReceiptTotal();
  bindMarketComboboxes();
  bindRowActions(document);
  bindConfirmForms();
  bindCopyButtons();
  bindFactorTooltips();
  bindAvatarUploads();
  bindAvatarChoices();
  bindAvatarDialogs();
  bindCharts();
  bindCategoryAssignmentPage();
});
document.addEventListener("click", (event) => {
  const row = event.target.closest(".receipt-item-row[data-href]");
  if (!row || event.target.closest("a, button, input, select, textarea")) return;
  window.location.href = row.dataset.href;
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" && event.key !== " ") return;
  const row = event.target.closest(".receipt-item-row[data-href]");
  if (!row) return;
  event.preventDefault();
  window.location.href = row.dataset.href;
});
