/**
 * Public site progressive enhancements. Every feature here degrades
 * gracefully — the page is fully readable and navigable with this file
 * absent, per the "minimal JS" requirement.
 */
document.addEventListener("DOMContentLoaded", function () {
    addCopyCodeButtons();
    initReadingProgress();
    initCopyLink();
});

function addCopyCodeButtons() {
    document.querySelectorAll("article pre").forEach(function (pre) {
        if (pre.closest("[data-code-block]")) return; // already wrapped

        const wrapper = document.createElement("div");
        wrapper.setAttribute("data-code-block", "");
        wrapper.className = "relative";
        pre.parentNode.insertBefore(wrapper, pre);
        wrapper.appendChild(pre);

        const button = document.createElement("button");
        button.type = "button";
        button.textContent = "Copy";
        button.className =
            "absolute right-2 top-2 rounded-md border border-slate-700 bg-slate-800/80 px-2.5 py-1 text-xs font-medium text-slate-200 hover:bg-slate-700";
        button.addEventListener("click", function () {
            copyText(pre.innerText).then(function (ok) {
                button.textContent = ok ? "Copied!" : "Copy failed";
                setTimeout(function () { button.textContent = "Copy"; }, 2000);
            });
        });
        wrapper.appendChild(button);
    });
}

function initReadingProgress() {
    const bar = document.querySelector("[data-reading-progress]");
    if (!bar) return;

    let ticking = false;
    function update() {
        const scrollable = document.documentElement.scrollHeight - window.innerHeight;
        const progress = scrollable > 0 ? (window.scrollY / scrollable) * 100 : 0;
        bar.style.width = Math.min(100, Math.max(0, progress)) + "%";
        ticking = false;
    }
    window.addEventListener("scroll", function () {
        if (!ticking) {
            requestAnimationFrame(update);
            ticking = true;
        }
    }, { passive: true });
    update();
}

function initCopyLink() {
    document.querySelectorAll("[data-copy-link]").forEach(function (button) {
        const wrapper = button.closest("[data-share-url]");
        const url = wrapper ? wrapper.dataset.shareUrl : window.location.href;
        const label = button.querySelector("[data-copy-label]") || button;
        const original = label.textContent;

        button.addEventListener("click", function () {
            copyText(url).then(function (ok) {
                label.textContent = ok ? "Link copied!" : "Copy failed";
                setTimeout(function () { label.textContent = original; }, 2000);
            });
        });
    });
}

function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
        return navigator.clipboard.writeText(text).then(() => true).catch(() => false);
    }
    // Fallback for browsers/contexts without the async Clipboard API.
    try {
        const textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.style.position = "fixed";
        textarea.style.left = "-9999px";
        document.body.appendChild(textarea);
        textarea.select();
        const ok = document.execCommand("copy");
        document.body.removeChild(textarea);
        return Promise.resolve(ok);
    } catch (err) {
        return Promise.resolve(false);
    }
}
