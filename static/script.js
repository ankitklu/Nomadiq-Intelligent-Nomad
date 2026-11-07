// =========================
// Elements & state
// =========================

const $ = (sel, root = document) => root.querySelector(sel);

const els = {
    thread: $("#thread"),
    composer: $("#composer"),
    prompt: $("#prompt"),
    sendBtn: $("#sendBtn"),
    newTripBtn: $("#newTripBtn"),
    themeToggle: $("#themeToggle"),
    suggestions: $("#suggestions"),
    userMsgTpl: $("#userMsgTpl"),
    loadingTpl: $("#loadingTpl"),
    resultTpl: $("#resultTpl"),
    errorTpl: $("#errorTpl"),
};

const state = {
    threadId: null,
    busy: false,
};

// Rough timings (ms) for when each agent in the graph usually starts.
// The backend doesn't stream progress yet, so the steps are simulated.
const STEP_TIMINGS = [0, 2500, 4500, 8000];

// =========================
// Theme
// =========================

const storage = {
    get(key) {
        try { return localStorage.getItem(key); } catch { return null; }
    },
    set(key, value) {
        try { localStorage.setItem(key, value); } catch { /* storage unavailable */ }
    },
};

function applyTheme(theme) {
    if (theme) document.documentElement.dataset.theme = theme;
}

function currentTheme() {
    const explicit = document.documentElement.dataset.theme;
    if (explicit) return explicit;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

applyTheme(storage.get("nomadiq-theme"));

els.themeToggle.addEventListener("click", () => {
    const next = currentTheme() === "dark" ? "light" : "dark";
    applyTheme(next);
    storage.set("nomadiq-theme", next);
});

// =========================
// Rendering helpers
// =========================

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

function linkify(html) {
    return html.replace(
        /(https?:\/\/[^\s<]+[^\s<.,;:!?)\]'"])/g,
        '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>'
    );
}

function renderMarkdown(text) {
    if (!window.marked || !window.DOMPurify) {
        return linkify(escapeHtml(text)).replace(/\n/g, "<br>");
    }

    const html = DOMPurify.sanitize(marked.parse(text, { gfm: true, breaks: false }));
    const tmp = document.createElement("div");
    tmp.innerHTML = html;

    tmp.querySelectorAll("table").forEach((table) => {
        const wrap = document.createElement("div");
        wrap.className = "table-wrap";
        table.replaceWith(wrap);
        wrap.appendChild(table);
    });

    tmp.querySelectorAll("a").forEach((a) => {
        a.target = "_blank";
        a.rel = "noopener noreferrer";
    });

    return tmp.innerHTML;
}

function renderRaw(text) {
    return linkify(escapeHtml(text.trim()));
}

function scrollToBottom() {
    window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
}

function cloneTpl(tpl) {
    return tpl.content.firstElementChild.cloneNode(true);
}

// =========================
// Messages
// =========================

function addUserMessage(text) {
    const node = cloneTpl(els.userMsgTpl);
    $(".bubble", node).textContent = text;
    els.thread.appendChild(node);
}

function addLoading() {
    const node = cloneTpl(els.loadingTpl);
    const steps = [...node.querySelectorAll(".steps li")];

    const setStep = (index) => {
        steps.forEach((li, i) => {
            li.classList.toggle("is-done", i < index);
            li.classList.toggle("is-active", i === index);
        });
    };

    const timers = STEP_TIMINGS.map((ms, i) => setTimeout(() => setStep(i), ms));
    els.thread.appendChild(node);

    return {
        remove() {
            timers.forEach(clearTimeout);
            node.remove();
        },
    };
}

function addResult(data, elapsedMs) {
    const node = cloneTpl(els.resultTpl);

    const sections = {
        answer: { text: data.answer, render: renderMarkdown },
        itinerary: { text: data.itinerary, render: renderMarkdown },
        flights: { text: data.flight_results, render: renderRaw },
        hotels: { text: data.hotel_results, render: renderRaw },
    };

    Object.entries(sections).forEach(([key, { text, render }]) => {
        const panel = $(`[data-panel="${key}"]`, node);
        const tab = $(`[data-tab="${key}"]`, node);

        if (text && text.trim()) {
            panel.innerHTML = render(text);
        } else {
            panel.innerHTML = '<p class="empty-note">Nothing to show here.</p>';
            if (key !== "answer") tab.disabled = true;
        }
    });

    node.querySelectorAll(".tab").forEach((tab) => {
        tab.addEventListener("click", () => {
            node.querySelectorAll(".tab").forEach((t) => t.classList.toggle("is-active", t === tab));
            node.querySelectorAll(".panel").forEach((p) =>
                p.classList.toggle("is-active", p.dataset.panel === tab.dataset.tab)
            );
        });
    });

    const seconds = (elapsedMs / 1000).toFixed(1);
    $(".meta", node).textContent = `${data.llm_calls || 4} agent steps · ${seconds}s`;

    const copyBtn = $(".copy-btn", node);
    copyBtn.addEventListener("click", async () => {
        const active = $(".tab.is-active", node).dataset.tab;
        try {
            await navigator.clipboard.writeText(sections[active].text || "");
            $("span", copyBtn).textContent = "Copied";
        } catch {
            $("span", copyBtn).textContent = "Copy failed";
        }
        setTimeout(() => ($("span", copyBtn).textContent = "Copy"), 1600);
    });

    els.thread.appendChild(node);
}

function addError(message, retryText) {
    const node = cloneTpl(els.errorTpl);
    $(".error-text", node).textContent = message;

    $(".retry-btn", node).addEventListener("click", () => {
        node.remove();
        // Drop the original user bubble too; send() adds it back
        els.thread.lastElementChild?.remove();
        send(retryText);
    });

    els.thread.appendChild(node);
}

// =========================
// Sending
// =========================

function setBusy(busy) {
    state.busy = busy;
    els.prompt.disabled = busy;
    updateSendState();
}

function updateSendState() {
    els.sendBtn.disabled = state.busy || !els.prompt.value.trim();
}

async function send(text) {
    const message = text.trim();
    if (!message || state.busy) return;

    document.body.classList.add("has-thread");
    addUserMessage(message);
    const loading = addLoading();
    scrollToBottom();
    setBusy(true);

    const started = performance.now();

    try {
        const res = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message, thread_id: state.threadId }),
        });

        const data = await res.json().catch(() => ({}));

        if (!res.ok) {
            throw new Error(data.error || `Server responded with ${res.status}`);
        }

        state.threadId = data.thread_id;
        loading.remove();
        addResult(data, performance.now() - started);
    } catch (err) {
        loading.remove();
        addError(err.message || "Something went wrong. Please try again.", message);
    } finally {
        setBusy(false);
        els.prompt.focus();
        scrollToBottom();
    }
}

// =========================
// Composer
// =========================

function autosize() {
    els.prompt.style.height = "auto";
    els.prompt.style.height = `${Math.min(els.prompt.scrollHeight, 200)}px`;
}

els.prompt.addEventListener("input", () => {
    autosize();
    updateSendState();
});

els.prompt.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
        e.preventDefault();
        els.composer.requestSubmit();
    }
});

els.composer.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = els.prompt.value;
    if (!text.trim() || state.busy) return;

    els.prompt.value = "";
    autosize();
    send(text);
});

els.suggestions.addEventListener("click", (e) => {
    const chip = e.target.closest(".chip");
    if (chip) send(chip.dataset.prompt);
});

els.newTripBtn.addEventListener("click", () => {
    if (state.busy) return;
    state.threadId = null;
    els.thread.innerHTML = "";
    document.body.classList.remove("has-thread");
    els.prompt.value = "";
    autosize();
    updateSendState();
    els.prompt.focus();
    window.scrollTo({ top: 0 });
});

els.prompt.focus();
