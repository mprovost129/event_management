// Main JavaScript entry point

(() => {
    const form = document.querySelector("[data-site-builder-form]");
    const preview = document.querySelector("[data-site-preview]");
    if (!form || !preview) return;

    const field = (name) => form.elements.namedItem(name);
    const nameOutput = preview.querySelector("[data-preview-name]");
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
    field("hero_image").addEventListener("change", (event) => {
        const [image] = event.target.files;
        if (!image) return;
        const reader = new FileReader();
        reader.addEventListener("load", () => {
            heroOutput.style.backgroundImage = `linear-gradient(rgba(255,255,255,.78), rgba(255,255,255,.78)), url("${reader.result}")`;
        });
        reader.readAsDataURL(image);
    });

    updateCopy();
    updateColors();
    updateTemplate();
    updateTypography();
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
