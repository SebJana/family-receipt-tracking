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

  function applyCategoryItemFilter(dialog) {
    const query = dialog.querySelector("[data-category-item-search]").value.trim().toLocaleLowerCase("de");
    let visible = 0;
    dialog.querySelectorAll(".category-assigned-item").forEach((row) => {
      const matches = !query || row.dataset.article.toLocaleLowerCase("de").includes(query);
      row.hidden = !matches;
      if (matches) visible += 1;
    });
    dialog.querySelector("[data-category-search-empty]").hidden = visible !== 0 || !query;
  }

  function bindCategoryManagement(root) {
    root.querySelectorAll("[data-category-edit-open]").forEach((button) => button.addEventListener("click", () => {
      document.getElementById(button.dataset.categoryEditOpen)?.showModal();
    }));
    root.querySelectorAll(".category-edit-dialog").forEach((dialog) => {
      const symbolInput = dialog.querySelector("[data-edit-category-symbol]");
      const editPicker = dialog.querySelector("[data-edit-emoji-picker]");
      dialog.querySelectorAll("[data-category-edit-close]").forEach((button) => button.addEventListener("click", () => dialog.close()));
      dialog.addEventListener("click", (event) => {
        if (event.target === dialog) dialog.close();
        if (!event.target.closest(".edit-emoji-field")) editPicker.hidden = true;
      });
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
    });

    root.querySelectorAll("[data-category-items-open]").forEach((button) => button.addEventListener("click", () => {
      const dialog = document.getElementById(button.dataset.categoryItemsOpen);
      if (!dialog) return;
      applyCategoryItemFilter(dialog);
      dialog.showModal();
    }));
    root.querySelectorAll(".category-items-dialog").forEach((dialog) => {
      dialog.querySelector("[data-category-items-close]")?.addEventListener("click", () => dialog.close());
      dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
      dialog.querySelector("[data-category-item-search]")?.addEventListener("input", () => applyCategoryItemFilter(dialog));
    });
    root.querySelectorAll(".category-assigned-item").forEach(bindCategoryClear);
  }

  const game = document.querySelector("[data-category-game]");
  const undoButton = game?.querySelector("[data-assignment-undo]");
  const skipButton = game?.querySelector("[data-assignment-skip]");
  const assignmentTab = document.querySelector('[data-category-tab="assign"]');
  let lastAssignment = null;
  const setRemaining = (remaining) => {
    document.querySelector("[data-unassigned-count]").textContent = remaining;
    document.querySelector(".tab-count").textContent = remaining;
    if (assignmentTab) assignmentTab.disabled = Number(remaining) === 0;
  };
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
        const remainingItems = card.querySelectorAll(".category-assigned-item").length;
        card.querySelector("[data-category-count]").textContent = remainingItems;
        card.querySelector("[data-category-items-open]").disabled = remainingItems === 0;
        setRemaining(result.remaining);
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
    card.querySelector("[data-category-items-open]").disabled = false;
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
      setRemaining(result.remaining);
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
        const remainingItems = card.querySelectorAll(".category-assigned-item").length;
        card.querySelector("[data-category-count]").textContent = remainingItems;
        card.querySelector("[data-category-items-open]").disabled = remainingItems === 0;
        if (!card.querySelector(".category-assigned-item")) card.querySelector("[data-category-contents]").innerHTML = '<p class="empty" data-category-empty>Noch leer</p>';
      }
      setRemaining(result.remaining);
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
  bindCategoryManagement(document);
  document.addEventListener("livefilter:update", (event) => {
    if (event.target.matches("#category-list-content")) {
      bindCategoryManagement(event.target);
    }
  });
}
