/**
 * Post editor: Quill rich-text setup, image upload, slug auto-fill,
 * autosave, and the unsaved-changes guard.
 *
 * Server-side is the real authority here — sanitization happens again in
 * PostForm.clean_content() / the autosave view no matter what this file
 * does, so nothing here is a security boundary.
 */
document.addEventListener("DOMContentLoaded", function () {
    const editorEl = document.getElementById("editor");
    if (!editorEl) return;

    const contentField = document.getElementById("content-raw");
    const form = contentField.closest("form");
    const csrfToken = form.querySelector("[name=csrfmiddlewaretoken]").value;
    const uploadUrl = editorEl.dataset.uploadUrl;

    const quill = new Quill("#editor", {
        theme: "snow",
        modules: {
            toolbar: {
                container: [
                    [{ header: [2, 3, 4, false] }],
                    ["bold", "italic", "underline", "strike"],
                    ["blockquote", "code-block"],
                    [{ list: "ordered" }, { list: "bullet" }],
                    ["link", "image"],
                    ["clean"],
                ],
                handlers: { image: imageHandler },
            },
        },
    });

    if (contentField.value) {
        quill.clipboard.dangerouslyPasteHTML(contentField.value);
    }

    function imageHandler() {
        const input = document.createElement("input");
        input.type = "file";
        input.accept = "image/png,image/jpeg,image/webp";
        input.onchange = async () => {
            const file = input.files[0];
            if (!file) return;
            const altText = window.prompt("Alt text (describe the image for accessibility/SEO):", "") || "";

            const formData = new FormData();
            formData.append("file", file);
            formData.append("alt", altText);

            const range = quill.getSelection(true);
            quill.insertText(range.index, "Uploading image…", { italic: true });

            try {
                const response = await fetch(uploadUrl, {
                    method: "POST",
                    headers: { "X-CSRFToken": csrfToken },
                    body: formData,
                });
                const data = await response.json();
                quill.deleteText(range.index, "Uploading image…".length);
                if (!response.ok) {
                    window.alert(data.error || "Image upload failed.");
                    return;
                }
                quill.insertEmbed(range.index, "image", data.url, "user");
                if (altText) {
                    const [imgNode] = quill.getLeaf(range.index);
                    if (imgNode && imgNode.domNode) imgNode.domNode.setAttribute("alt", altText);
                }
                quill.setSelection(range.index + 1);
            } catch (err) {
                quill.deleteText(range.index, "Uploading image…".length);
                window.alert("Image upload failed.");
            }
        };
        input.click();
    }

    // --- Slug auto-fill: only while the user hasn't touched slug by hand ---
    const titleField = document.getElementById("id_title");
    const slugField = document.getElementById("id_slug");
    let slugTouched = !!slugField.value;
    slugField.addEventListener("input", () => { slugTouched = true; });
    if (titleField) {
        titleField.addEventListener("input", () => {
            if (slugTouched) return;
            // \p{M} keeps combining marks (e.g. Bangla vowel signs) so
            // Unicode titles don't get mangled — matches unicode_slugify().
            slugField.value = titleField.value
                .toLowerCase()
                .trim()
                .replace(/[^\p{L}\p{N}\p{M}\s-]/gu, "")
                .replace(/\s+/g, "-")
                .replace(/-+/g, "-");
        });
    }

    // --- SEO length hints (advisory only — no hard validation client-side) ---
    // Recommendations, not a ranking guarantee: search engines truncate by
    // pixel width, not a fixed character count, so these are guidance only.
    document.querySelectorAll("[data-seo-counter]").forEach((field) => {
        const counter = document.getElementById(field.dataset.seoCounter);
        const min = parseInt(field.dataset.seoMin, 10) || 0;
        const good = parseInt(field.dataset.seoGood, 10);
        const max = parseInt(field.dataset.seoMax, 10);
        const update = () => {
            const len = field.value.length;
            let label, className;
            if (len === 0) {
                label = `0 characters`; className = "text-xs text-slate-400";
            } else if (len < min) {
                label = `${len} characters — Too short`; className = "text-xs text-amber-600 dark:text-amber-400";
            } else if (len <= good) {
                label = `${len} characters — Good`; className = "text-xs text-green-600 dark:text-green-400";
            } else if (len <= max) {
                label = `${len} characters — Getting long`; className = "text-xs text-amber-600 dark:text-amber-400";
            } else {
                label = `${len} characters — Possibly too long`; className = "text-xs text-red-600 dark:text-red-400";
            }
            counter.textContent = label;
            counter.className = className;
        };
        field.addEventListener("input", update);
        update();
    });

    // --- Word count / character count / reading time (client-side only,
    // never a database request — a rough same-formula estimate as the
    // server's `compute_reading_time()`, default 225 WPM) ---
    const wordCountEl = document.getElementById("word-count");
    const charCountEl = document.getElementById("char-count");
    const readingTimeEl = document.getElementById("reading-time-estimate");
    const READING_WPM_ESTIMATE = 225;
    function updateWordCount() {
        if (!wordCountEl) return;
        const text = quill.getText().trim();
        const words = text ? text.split(/\s+/).length : 0;
        const chars = text.length;
        wordCountEl.textContent = `Words: ${words.toLocaleString()}`;
        charCountEl.textContent = `Characters: ${chars.toLocaleString()}`;
        readingTimeEl.textContent = `Reading time: ${words ? Math.max(1, Math.round(words / READING_WPM_ESTIMATE)) : 0} min`;
    }
    quill.on("text-change", updateWordCount);
    updateWordCount();

    // --- Draft recovery: a debounced (stop-typing, not per-keystroke)
    // localStorage snapshot of title/excerpt/content, so a crashed tab or
    // an accidental navigation-away doesn't lose work the server autosave
    // (a periodic timer, not stop-typing-triggered) hasn't reached yet.
    // Only this post's own fields are stored — nothing sensitive, nothing
    // beyond what's already visible in the form.
    const draftKey = editorEl.dataset.draftKey;
    const excerptField = document.getElementById("id_excerpt");
    const banner = document.getElementById("draft-recovery-banner");

    function currentDraftPayload() {
        return {
            title: titleField ? titleField.value : "",
            excerpt: excerptField ? excerptField.value : "",
            content: quill.root.innerHTML,
            savedAt: Date.now(),
        };
    }

    function saveDraftSnapshot() {
        try {
            localStorage.setItem(draftKey, JSON.stringify(currentDraftPayload()));
        } catch (err) {
            /* Storage full/disabled — draft recovery just isn't available this session. */
        }
    }

    let recoveryOffered = false;
    if (banner) {
        try {
            const stored = JSON.parse(localStorage.getItem(draftKey) || "null");
            const serverContent = contentField.value || "";
            if (stored && (stored.title !== titleField.value || stored.content !== serverContent)) {
                banner.hidden = false;
                recoveryOffered = true;
            }
        } catch (err) {
            /* Corrupt/unreadable snapshot — ignore it rather than block the editor. */
        }

        document.getElementById("draft-recovery-recover").addEventListener("click", () => {
            try {
                const stored = JSON.parse(localStorage.getItem(draftKey) || "null");
                if (stored) {
                    if (titleField) titleField.value = stored.title || "";
                    if (excerptField) excerptField.value = stored.excerpt || "";
                    quill.clipboard.dangerouslyPasteHTML(stored.content || "");
                    isDirty = true;
                }
            } finally {
                banner.hidden = true;
            }
        });
        document.getElementById("draft-recovery-discard").addEventListener("click", () => {
            localStorage.removeItem(draftKey);
            banner.hidden = true;
        });
    }

    // Debounce: only snapshot ~1.2s after the user stops typing, never on
    // every keystroke.
    let draftSnapshotTimer = null;
    function scheduleDraftSnapshot() {
        if (recoveryOffered) return; // don't overwrite an unreviewed recovery snapshot
        clearTimeout(draftSnapshotTimer);
        draftSnapshotTimer = setTimeout(saveDraftSnapshot, 1200);
    }
    quill.on("text-change", scheduleDraftSnapshot);
    if (titleField) titleField.addEventListener("input", scheduleDraftSnapshot);
    if (excerptField) excerptField.addEventListener("input", scheduleDraftSnapshot);

    // --- Dirty tracking + unsaved-changes warning ---
    let isDirty = false;
    let submitting = false;
    form.addEventListener("input", () => { isDirty = true; });
    quill.on("text-change", () => { isDirty = true; });
    form.addEventListener("submit", () => { submitting = true; });
    window.addEventListener("beforeunload", (event) => {
        if (!isDirty || submitting) return;
        event.preventDefault();
        event.returnValue = "";
    });

    form.addEventListener("submit", () => {
        contentField.value = quill.root.innerHTML;
        if (draftKey) localStorage.removeItem(draftKey);
    });

    // --- Autosave (edit page only: dataset.postId present, status is draft/scheduled) ---
    const autosaveUrl = editorEl.dataset.autosaveUrl;
    const autosaveStatus = document.getElementById("autosave-status");
    if (autosaveUrl && autosaveStatus) {
        let lastSavedAt = null;
        setInterval(async () => {
            if (!isDirty || submitting) return;
            contentField.value = quill.root.innerHTML;
            try {
                const response = await fetch(autosaveUrl, {
                    method: "POST",
                    headers: { "X-CSRFToken": csrfToken, "Content-Type": "application/json" },
                    body: JSON.stringify({
                        title: titleField.value,
                        excerpt: document.getElementById("id_excerpt").value,
                        content: contentField.value,
                    }),
                });
                if (response.ok) {
                    isDirty = false;
                    lastSavedAt = new Date();
                    autosaveStatus.textContent = "Saved just now";
                    if (draftKey) localStorage.removeItem(draftKey);
                }
            } catch (err) {
                /* Silent — the manual Save button remains the reliable path. */
            }
        }, 45000);

        setInterval(() => {
            if (!lastSavedAt) return;
            const seconds = Math.round((Date.now() - lastSavedAt) / 1000);
            if (seconds < 5) return;
            autosaveStatus.textContent = seconds < 60 ? `Saved ${seconds}s ago` : `Saved ${Math.round(seconds / 60)}m ago`;
        }, 5000);
    }

    // --- Keyboard shortcuts: Ctrl/Cmd+S saves the draft, Ctrl/Cmd+Enter
    // publishes (only where a publish form actually exists on the page).
    // Esc-closes-dialog needs no code here — native <dialog>/showModal()
    // already does that in every browser.
    const publishForm = document.getElementById("publish-form");
    document.addEventListener("keydown", (event) => {
        const modifier = event.metaKey || event.ctrlKey;
        if (!modifier) return;
        if (event.key === "s") {
            event.preventDefault();
            form.requestSubmit();
        } else if (event.key === "Enter" && publishForm) {
            event.preventDefault();
            publishForm.requestSubmit();
        }
    });
});

/**
 * Live Google-style search-result preview. An approximation for editor
 * guidance only — real search-result rendering isn't something a page's
 * own JS can predict, and this never claims to be exact.
 */
function initGooglePreview(options) {
    const urlEl = document.getElementById("google-preview-url");
    const titleEl = document.getElementById("google-preview-title");
    const descriptionEl = document.getElementById("google-preview-description");
    if (!urlEl || !titleEl || !descriptionEl) return;

    const slugField = document.getElementById(options.slugFieldId);
    const titleField = document.getElementById(options.titleFieldId);
    const fallbackTitleField = document.getElementById(options.fallbackTitleFieldId);
    const descField = document.getElementById(options.descriptionFieldId);
    const fallbackDescField = document.getElementById(options.fallbackDescriptionFieldId);

    function update() {
        const slug = (slugField && slugField.value) || "your-post-slug";
        urlEl.textContent = `${options.host}/blog/${slug}/`;

        const title = (titleField && titleField.value) || (fallbackTitleField && fallbackTitleField.value) || "Your post title";
        titleEl.textContent = title;

        const description = (descField && descField.value) || (fallbackDescField && fallbackDescField.value) || "Your meta description or excerpt will appear here.";
        descriptionEl.textContent = description;
    }

    [slugField, titleField, fallbackTitleField, descField, fallbackDescField].forEach((field) => {
        if (field) field.addEventListener("input", update);
    });
    update();
}
