// Main JavaScript entry point

// Confirmation prompts for destructive actions. The CSP forbids inline
// event-handler attributes (no unsafe-inline in script-src), so this
// delegated listener is the only thing standing between a click and an
// irreversible POST - keep it registered before anything else can fail.
document.addEventListener("submit", (event) => {
    const form = event.target.closest("[data-confirm]");
    if (form && !window.confirm(form.dataset.confirm)) {
        event.preventDefault();
    }
});

(() => {
    const form = document.querySelector("[data-site-builder-form]");
    const preview = document.querySelector("[data-site-preview]");
    if (!form || !preview) return;

    const field = (name) => form.elements.namedItem(name);
    const nameOutput = preview.querySelector("[data-preview-name]");
    const logoOutput = preview.querySelector("[data-preview-logo]");
    const brandOutput = preview.querySelector("[data-preview-brand]");
    const headingOutput = preview.querySelector("[data-preview-heading]");
    const textOutput = preview.querySelector("[data-preview-text]");
    const heroOutput = preview.querySelector("[data-preview-hero]");

    const updateCopy = () => {
        const displayName = field("display_name").value.trim() || "Your group";
        nameOutput.textContent = displayName;
        headingOutput.textContent = field("hero_heading").value.trim() || displayName;
        textOutput.textContent =
            field("hero_text").value.trim() ||
            "Your events, updates, and community all in one place.";
    };

    const updateColors = () => {
        ["primary_color", "secondary_color"].forEach((name) => {
            const input = field(name);
            const cssName = name === "primary_color" ? "--preview-primary" : "--preview-secondary";
            preview.style.setProperty(cssName, input.value);
            const output = document.querySelector(`[data-color-output="${input.id}"]`);
            if (output) output.value = input.value.toUpperCase();
        });
    };

    const updateTemplate = () => {
        const selected = form.querySelector('input[name="template_key"]:checked');
        preview.classList.toggle("gh-site-preview-classic", selected?.value !== "social");
        preview.classList.toggle("gh-site-preview-social", selected?.value === "social");
    };

    const updateTypography = () => {
        const fonts = {
            serif: "Georgia, 'Times New Roman', serif",
            rounded: "'Trebuchet MS', system-ui, sans-serif",
            system: "system-ui, -apple-system, sans-serif",
        };
        preview.style.fontFamily = fonts[field("typography_key").value] || fonts.system;
    };

    const updateBranding = () => {
        const showName = Boolean(field("show_name_in_header")?.checked);
        const showLogo = Boolean(field("show_logo_in_header")?.checked);
        const hasLogo = Boolean(logoOutput?.getAttribute("src"));

        if (nameOutput) {
            nameOutput.hidden = !showName;
        }
        if (logoOutput) {
            logoOutput.hidden = !showLogo || !hasLogo;
        }
        if (brandOutput) {
            const visible = showName || (showLogo && hasLogo);
            brandOutput.hidden = !visible;
        }
    };

    ["display_name", "hero_heading", "hero_text"].forEach((name) => {
        field(name).addEventListener("input", updateCopy);
    });
    ["primary_color", "secondary_color"].forEach((name) => {
        field(name).addEventListener("input", updateColors);
    });
    form.querySelectorAll('input[name="template_key"]').forEach((input) => {
        input.addEventListener("change", updateTemplate);
    });
    field("typography_key").addEventListener("change", updateTypography);
    field("show_logo_in_header")?.addEventListener("change", updateBranding);
    field("show_name_in_header")?.addEventListener("change", updateBranding);
    field("hero_image").addEventListener("change", (event) => {
        const [image] = event.target.files;
        if (!image) return;
        const reader = new FileReader();
        reader.addEventListener("load", () => {
            heroOutput.style.backgroundImage = `linear-gradient(rgba(255,255,255,.78), rgba(255,255,255,.78)), url("${reader.result}")`;
        });
        reader.readAsDataURL(image);
    });
    field("logo")?.addEventListener("change", (event) => {
        const [image] = event.target.files;
        if (!image || !logoOutput) {
            updateBranding();
            return;
        }
        const reader = new FileReader();
        reader.addEventListener("load", () => {
            logoOutput.setAttribute("src", String(reader.result));
            updateBranding();
        });
        reader.readAsDataURL(image);
    });

    updateCopy();
    updateColors();
    updateTemplate();
    updateTypography();
    updateBranding();
})();

(() => {
    document.querySelectorAll("[data-count-for]").forEach((output) => {
        const input = document.getElementById(output.dataset.countFor);
        if (!input) return;
        const update = () => {
            const maximum = input.maxLength > 0 ? ` / ${input.maxLength}` : " characters";
            output.value = `${input.value.length}${maximum}`;
        };
        input.addEventListener("input", update);
        update();
    });

    const editor = document.querySelector("[data-blog-editor]");
    if (!editor) return;
    const title = editor.elements.namedItem("title");
    const slug = editor.elements.namedItem("slug");
    let slugWasEdited = slug.value.trim() !== "";
    slug.addEventListener("input", () => {
        slugWasEdited = true;
    });
    title.addEventListener("input", () => {
        if (slugWasEdited) return;
        slug.value = title.value
            .toLowerCase()
            .trim()
            .replace(/[^a-z0-9]+/g, "-")
            .replace(/^-+|-+$/g, "")
            .slice(0, 180);
    });
})();

(() => {
    const editor = document.querySelector("[data-campaign-editor]");
    if (!editor) return;

    const updateChannel = () => {
        const channel = editor.elements.namedItem("channel").value;
        editor.querySelectorAll('[data-campaign-section="email"]').forEach((section) => {
            section.hidden = channel !== "email";
        });
        const help = editor.querySelector("[data-channel-help]");
        if (help) {
            help.textContent =
                channel === "sms"
                    ? "Keep SMS announcements concise. A stop-messages instruction is added automatically."
                    : "A unique unsubscribe link is added automatically.";
        }
    };

    const updateAudience = () => {
        const audience = editor.elements.namedItem("audience").value;
        editor.querySelectorAll('[data-audience-section="tag"]').forEach((section) => {
            section.hidden = audience !== "tag";
        });
        editor.querySelectorAll('[data-audience-section="event"]').forEach((section) => {
            section.hidden = !["event_invitees", "response"].includes(audience);
        });
        editor.querySelectorAll('[data-audience-section="response"]').forEach((section) => {
            section.hidden = audience !== "response";
        });
    };

    editor.querySelectorAll('input[name="channel"]').forEach((input) => {
        input.addEventListener("change", updateChannel);
    });
    editor.elements.namedItem("audience").addEventListener("change", updateAudience);
    updateChannel();
    updateAudience();
})();

(() => {
    const editor = document.querySelector("[data-event-editor]");
    if (!editor) return;

    const title = editor.elements.namedItem("title");
    const slug = editor.elements.namedItem("slug");
    let slugWasEdited = slug.value.trim() !== "";
    slug.addEventListener("input", () => {
        slugWasEdited = true;
    });
    title.addEventListener("input", () => {
        if (slugWasEdited) return;
        slug.value = title.value
            .toLowerCase()
            .trim()
            .replace(/[^a-z0-9]+/g, "-")
            .replace(/^-+|-+$/g, "")
            .slice(0, 180);
    });

    const updateRecurrence = () => {
        const repeats = editor.elements.namedItem("recurrence").value !== "none";
        editor.querySelectorAll("[data-recurrence-section]").forEach((section) => {
            section.hidden = !repeats;
        });
    };
    editor.querySelectorAll('input[name="recurrence"]').forEach((input) => {
        input.addEventListener("change", updateRecurrence);
    });

    const startDate = editor.elements.namedItem("start_date");
    const endDate = editor.elements.namedItem("end_date");
    startDate.addEventListener("change", () => {
        if (!endDate.value) endDate.value = startDate.value;
    });
    updateRecurrence();
})();

(() => {
    const picker = document.querySelector("[data-invite-picker]");
    if (!picker) return;
    const choices = [...picker.querySelectorAll("[data-contact-choice]")];
    const search = picker.querySelector("[data-invite-search]");
    const selectAll = picker.querySelector("[data-select-all]");
    const count = picker.querySelector("[data-selected-count]");
    const noResults = picker.querySelector("[data-no-contact-results]");

    const visibleChoices = () => choices.filter((choice) => !choice.hidden);
    const updateCount = () => {
        const selected = choices.filter((choice) => choice.querySelector("input").checked).length;
        if (count) count.value = `${selected} selected`;
        if (selectAll) {
            const visible = visibleChoices();
            const allVisibleSelected = visible.length > 0 && visible.every((choice) => choice.querySelector("input").checked);
            selectAll.textContent = allVisibleSelected ? "Clear shown" : "Select all shown";
        }
    };

    choices.forEach((choice) => {
        choice.querySelector("input").addEventListener("change", updateCount);
    });
    search?.addEventListener("input", () => {
        const query = search.value.trim().toLowerCase();
        choices.forEach((choice) => {
            choice.hidden = query !== "" && !choice.textContent.toLowerCase().includes(query);
        });
        if (noResults) noResults.hidden = visibleChoices().length !== 0;
        updateCount();
    });
    selectAll?.addEventListener("click", () => {
        const visible = visibleChoices();
        const shouldSelect = !visible.every((choice) => choice.querySelector("input").checked);
        visible.forEach((choice) => {
            choice.querySelector("input").checked = shouldSelect;
        });
        updateCount();
    });
    updateCount();
})();

(() => {
    const editor = document.querySelector("[data-contact-editor]");
    if (!editor) return;
    const memberStatus = editor.elements.namedItem("member_tracking");
    const updateMemberFields = () => {
        editor.querySelectorAll("[data-member-fields]").forEach((section) => {
            section.hidden = memberStatus.value === "contact_only";
        });
    };
    memberStatus.addEventListener("change", updateMemberFields);
    updateMemberFields();
})();

(() => {
    const form = document.querySelector("[data-manager-response]");
    if (!form) return;

    const guestSection = form.querySelector("[data-guest-section]");
    const guestCount = form.elements.namedItem("guest_count");
    const responseInputs = [...form.querySelectorAll('input[name="response"]')];

    const selectedResponse = () => responseInputs.find((input) => input.checked)?.value;
    const updateGuests = () => {
        if (!guestSection || !guestCount) return;
        const isGoing = selectedResponse() === "going";
        guestSection.hidden = !isGoing;
        const count = isGoing ? Number.parseInt(guestCount.value || "0", 10) : 0;
        form.querySelectorAll("[data-guest-group]").forEach((group) => {
            group.hidden = Number.parseInt(group.dataset.guestGroup, 10) > count;
        });
    };

    responseInputs.forEach((input) => input.addEventListener("change", updateGuests));
    guestCount?.addEventListener("input", updateGuests);
    updateGuests();
})();

/* Photo album: upload feedback and drag-to-reorder.
   Progressive enhancement. Without JavaScript the form still uploads and
   photos keep whatever order they were added in. */
(() => {
    const uploadForm = document.querySelector("[data-photo-upload]");
    if (uploadForm) {
        const input = uploadForm.querySelector('input[type="file"]');
        const counter = uploadForm.querySelector("[data-upload-count]");
        const submit = uploadForm.querySelector("[data-upload-submit]");

        input?.addEventListener("change", () => {
            const count = input.files?.length ?? 0;
            if (!counter) return;
            counter.hidden = count === 0;
            counter.textContent =
                count === 1 ? "1 photo selected" : `${count} photos selected`;
        });

        uploadForm.addEventListener("submit", () => {
            if (!submit) return;
            const count = input?.files?.length ?? 0;
            submit.disabled = true;
            submit.textContent =
                count > 1 ? `Uploading ${count} photos...` : "Uploading...";
        });
    }

    const grid = document.querySelector("[data-photo-reorder]");
    if (!grid) return;
    const cards = () => [...grid.querySelectorAll("[data-photo-id]")];
    if (cards().length < 2) return;

    const status = document.querySelector("[data-reorder-status]");
    const url = grid.dataset.reorderUrl;
    const csrf = document.querySelector('[name="csrfmiddlewaretoken"]')?.value;
    let dragged = null;
    let saveTimer = null;

    grid.querySelectorAll("[data-reorder-controls]").forEach((controls) => {
        controls.hidden = false;
    });

    const announce = (message) => {
        if (status) status.textContent = message;
    };

    const save = () => {
        window.clearTimeout(saveTimer);
        saveTimer = window.setTimeout(async () => {
            const body = new FormData();
            cards().forEach((card) => body.append("photo_ids", card.dataset.photoId));
            announce("Saving order...");
            try {
                const response = await fetch(url, {
                    method: "POST",
                    headers: { "X-CSRFToken": csrf, "X-Requested-With": "fetch" },
                    body,
                });
                announce(
                    response.ok
                        ? "Order saved."
                        : "That order could not be saved. Reload and try again."
                );
            } catch {
                announce("That order could not be saved. Check your connection.");
            }
        }, 400);
    };

    grid.addEventListener("dragstart", (event) => {
        dragged = event.target.closest("[data-photo-id]");
        if (!dragged) return;
        dragged.classList.add("is-dragging");
        event.dataTransfer.effectAllowed = "move";
    });

    grid.addEventListener("dragend", () => {
        dragged?.classList.remove("is-dragging");
        dragged = null;
        save();
    });

    grid.addEventListener("dragover", (event) => {
        if (!dragged) return;
        event.preventDefault();
        const target = event.target.closest("[data-photo-id]");
        if (!target || target === dragged) return;
        const { left, width } = target.getBoundingClientRect();
        const after = event.clientX > left + width / 2;
        grid.insertBefore(dragged, after ? target.nextSibling : target);
    });

    grid.addEventListener("click", (event) => {
        const button = event.target.closest("[data-move]");
        if (!button) return;
        const card = button.closest("[data-photo-id]");
        const order = cards();
        const index = order.indexOf(card);
        const target = button.dataset.move === "up" ? index - 1 : index + 1;
        if (target < 0 || target >= order.length) return;
        if (button.dataset.move === "up") {
            grid.insertBefore(card, order[target]);
        } else {
            grid.insertBefore(order[target], card);
        }
        button.focus();
        announce(`Moved to position ${target + 1} of ${order.length}.`);
        save();
    });
})();
