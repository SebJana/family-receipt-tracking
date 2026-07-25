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
  const snapshots = new WeakMap();

  const captureSnapshot = (dialog) => {
    const picker = dialog.querySelector("[data-avatar-picker]");
    const uploadOption = picker?.querySelector(".avatar-upload-option");
    snapshots.set(dialog, {
      choice: picker?.querySelector('input[type="radio"]:checked')?.value || "initials",
      uploadPreview: uploadOption?.querySelector(".person-avatar")?.cloneNode(true) || null,
      uploadLabel: uploadOption?.querySelector(".avatar-upload-label")?.textContent || "",
    });
  };

  const cancelDialog = (dialog) => {
    const snapshot = snapshots.get(dialog);
    const picker = dialog.querySelector("[data-avatar-picker]");
    if (snapshot && picker) {
      const uploadOption = picker.querySelector(".avatar-upload-option");
      const currentPreview = uploadOption?.querySelector(".person-avatar");
      if (currentPreview && snapshot.uploadPreview) {
        currentPreview.replaceWith(snapshot.uploadPreview.cloneNode(true));
      }
      const uploadLabel = uploadOption?.querySelector(".avatar-upload-label");
      if (uploadLabel) uploadLabel.textContent = snapshot.uploadLabel;
      picker.querySelectorAll("[data-avatar-upload]").forEach((input) => {
        input.value = "";
      });
      const originalChoice = picker.querySelector(
        `input[type="radio"][value="${snapshot.choice}"]`
      );
      if (originalChoice) {
        originalChoice.checked = true;
        originalChoice.dispatchEvent(new Event("change", { bubbles: true }));
      }
    }
    dialog.close();
  };

  document.querySelectorAll("[data-avatar-open]").forEach((button) => {
    button.addEventListener("click", () => {
      const dialog = document.getElementById(button.dataset.avatarOpen);
      if (!dialog) return;
      captureSnapshot(dialog);
      dialog.showModal();
    });
  });
  document.querySelectorAll(".avatar-dialog").forEach((dialog) => {
    dialog.querySelectorAll("[data-avatar-cancel]").forEach((button) => {
      button.addEventListener("click", () => cancelDialog(dialog));
    });
    dialog.querySelectorAll("[data-avatar-confirm]").forEach((button) => {
      button.addEventListener("click", () => dialog.close());
    });
    dialog.addEventListener("cancel", (event) => {
      event.preventDefault();
      cancelDialog(dialog);
    });
    dialog.addEventListener("click", (event) => {
      if (event.target !== dialog) return;
      const bounds = dialog.getBoundingClientRect();
      const outside = event.clientX < bounds.left
        || event.clientX > bounds.right
        || event.clientY < bounds.top
        || event.clientY > bounds.bottom;
      if (outside) cancelDialog(dialog);
    });
  });
}
