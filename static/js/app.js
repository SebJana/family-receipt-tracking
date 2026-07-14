function bindAllocationControls(root) {
  root.querySelectorAll("[data-allocation]").forEach((allocation) => {
    if (allocation.dataset.bound === "true") return;
    allocation.dataset.bound = "true";

    const minShare = 0.0001;
    const people = allocation.querySelectorAll("[data-allocation-person]");
    const checkboxes = allocation.querySelectorAll("[data-allocation-checkbox]");
    const allButton = allocation.querySelector("[data-select-all]");
    const noneButton = allocation.querySelector("[data-select-none]");

    const getControls = (person) => ({
      checkbox: person.querySelector("[data-allocation-checkbox]"),
      number: person.querySelector("[data-weight-number]"),
      slider: person.querySelector("[data-weight-slider]"),
    });

    const selectedPeople = () => Array.from(people).filter((person) => {
      const { checkbox } = getControls(person);
      return checkbox && checkbox.checked;
    });

    const parseShare = (value) => {
      const parsed = Number(String(value || "0").replace(",", "."));
      return Number.isFinite(parsed) ? parsed : 0;
    };

    const getShare = (person) => parseShare(person.dataset.share);

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
      const { checkbox, number, slider } = getControls(person);
      const state = person.querySelector("[data-allocation-state]");
      if (!checkbox) return;

      person.classList.toggle("is-selected", checkbox.checked);
      if (number) number.disabled = !checkbox.checked;
      if (slider) slider.disabled = !checkbox.checked;
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

      const target = selected.find((person) => person !== protectedPerson) || selected[0];
      setShare(target, getShare(target) + difference);
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

      const others = selected.filter((person) => person !== changedPerson);
      const maxShare = 1 - minShare * others.length;
      const oldShare = getShare(changedPerson);
      const nextShare = Math.max(minShare, Math.min(maxShare, targetShare));
      const delta = nextShare - oldShare;
      if (Math.abs(delta) < 0.0000001) {
        setShare(changedPerson, nextShare);
        return;
      }

      setShare(changedPerson, nextShare);
      distributeDeltaEvenly(others, -delta);
      fixTotal(selected, changedPerson);
    };

    people.forEach((person) => {
      const { checkbox, slider, number } = getControls(person);

      if (checkbox) {
        checkbox.addEventListener("change", () => {
          const selected = selectedPeople();
          if (checkbox.checked) {
            setShare(person, 0);
            rebalanceFromPerson(person, 1 / selected.length);
          } else {
            const removedShare = getShare(person);
            setShare(person, 0);
            distributeDeltaEvenly(selected, removedShare);
            normalizeSelectedShares();
          }
          people.forEach((entry) => updatePerson(entry));
        });
      }

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

    if (allButton) {
      allButton.addEventListener("click", () => {
        checkboxes.forEach((checkbox) => {
          checkbox.checked = true;
        });
        equalizeSelectedShares();
        people.forEach((person) => updatePerson(person));
      });
    }

    if (noneButton) {
      noneButton.addEventListener("click", () => {
        checkboxes.forEach((checkbox) => {
          checkbox.checked = false;
        });
        normalizeSelectedShares();
      });
    }
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
    "norma.svg": "#f2cc00",
    "netto.svg": "#ffd400",
    "lidl.svg": "#0050aa",
    "aldi.svg": "#00a8e0",
    "penny.svg": "#e30613",
    "dm.svg": "#002e6d",
    "rossmann.svg": "#d71920",
    "edeka.svg": "#005ca9",
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
        const size = Math.min(42, (arc.outerRadius - arc.innerRadius) * 0.72, availableArc * 0.58);
        if (size < 18) return;

        const middleAngle = (arc.startAngle + arc.endAngle) / 2;
        const x = arc.x + Math.cos(middleAngle) * radius;
        const y = arc.y + Math.sin(middleAngle) * radius;
        const boxWidth = size * 1.35;
        const boxHeight = size;
        const context = chart.ctx;

        context.save();
        context.fillStyle = imageReady ? (badge.background || "rgba(255, 255, 255, 0.92)") : (badge.color || "#1d6f5f");
        context.fillRect(x - boxWidth / 2 - 3, y - boxHeight / 2 - 3, boxWidth + 6, boxHeight + 6);
        if (imageReady) {
          const imageRatio = image.naturalWidth / image.naturalHeight;
          const drawWidth = imageRatio > boxWidth / boxHeight ? boxWidth : boxHeight * imageRatio;
          const drawHeight = imageRatio > boxWidth / boxHeight ? boxWidth / imageRatio : boxHeight;
          context.drawImage(image, x - drawWidth / 2, y - drawHeight / 2, drawWidth, drawHeight);
        } else {
          const label = String(badge.initials || chart.data.labels[index] || "?").trim();
          context.fillStyle = "#fff";
          context.font = `800 ${Math.max(14, size * 0.55)}px system-ui`;
          context.textAlign = "center";
          context.textBaseline = "middle";
          context.fillText((badge.initials || label[0] || "?").toLocaleUpperCase(), x, y);
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
      : (canvas.hasAttribute("data-person-avatars") ? (data.avatars || []) : []);
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

document.addEventListener("DOMContentLoaded", () => {
  bindDatePresets();
  bindLiveFilters();
  bindAllocationControls(document);
  bindDynamicRows();
  bindRowActions(document);
  bindConfirmForms();
  bindCopyButtons();
  bindFactorTooltips();
  bindAvatarUploads();
  bindAvatarChoices();
  bindAvatarDialogs();
  bindCharts();
});
