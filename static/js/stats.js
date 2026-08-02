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

function bindPersistedFilters() {
  document.querySelectorAll("form[data-persist-filters]").forEach((form) => {
    const storageKey = form.dataset.persistFilters;
    const namedControls = Array.from(form.elements).filter((control) => control.name);
    const filterNames = new Set(namedControls.map((control) => control.name));
    const currentUrl = new URL(window.location.href);
    const hasExplicitFilters = Array.from(currentUrl.searchParams.keys())
      .some((name) => filterNames.has(name));

    const filterValues = () => Object.fromEntries(
      namedControls.map((control) => [control.name, control.value]),
    );
    const saveFilters = () => {
      try {
        window.localStorage.setItem(storageKey, JSON.stringify(filterValues()));
      } catch (_error) {
        // Filtering still works when browser storage is unavailable or disabled.
      }
    };

    if (!hasExplicitFilters) {
      try {
        const savedFilters = JSON.parse(window.localStorage.getItem(storageKey) || "null");
        if (savedFilters && typeof savedFilters === "object") {
          namedControls.forEach((control) => {
            if (Object.hasOwn(savedFilters, control.name)) {
              currentUrl.searchParams.set(control.name, String(savedFilters[control.name]));
            }
          });
          window.location.replace(currentUrl);
          return;
        }
      } catch (_error) {
        // Ignore invalid or inaccessible saved data and use the server defaults.
      }
    }

    saveFilters();
    form.addEventListener("submit", saveFilters);
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
        currentTarget.dispatchEvent(new CustomEvent("livefilter:update", {
          bubbles: true,
          detail: { url },
        }));
      } catch (error) {
        if (error.name !== "AbortError") window.location.assign(url);
      }
    };

    form.querySelectorAll("select:not([data-date-preset]), input[type='date']").forEach((control) => {
      control.addEventListener("change", updateResults);
    });

    form.querySelectorAll("input[type='text'], input[type='search'], input:not([type])").forEach((control) => {
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
    const badgeData = canvas.hasAttribute("data-market-logos")
      ? (data.logos || []).map(() => ({ background: "#ffffff" }))
      : (canvas.hasAttribute("data-person-avatars") ? (data.avatars || []) : (canvas.hasAttribute("data-category-emojis") ? (data.badges || []) : []));
    const badgeUrls = canvas.hasAttribute("data-market-logos")
      ? (data.logos || [])
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
            backgroundColor: data.logo_keys
              ? marketColors(data.logo_keys)
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
