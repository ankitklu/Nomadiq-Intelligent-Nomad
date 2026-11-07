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

// =========================
// PDF export
// =========================

const HTML2PDF_SRC = "https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js";
let html2pdfLoader = null;

// Loaded on first use so the page itself stays light
function loadHtml2Pdf() {
    if (window.html2pdf) return Promise.resolve(window.html2pdf);

    html2pdfLoader ??= new Promise((resolve, reject) => {
        const script = document.createElement("script");
        script.src = HTML2PDF_SRC;
        script.onload = () => resolve(window.html2pdf);
        script.onerror = () => {
            html2pdfLoader = null;
            reject(new Error("Couldn't load the PDF library."));
        };
        document.head.appendChild(script);
    });

    return html2pdfLoader;
}

function slugify(text) {
    return text
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "")
        .slice(0, 50) || "trip";
}

function buildPdfDoc(query, answer) {
    const doc = document.createElement("div");
    doc.className = "pdf-doc";

    const date = new Date().toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" });

    doc.innerHTML = `
        <header class="pdf-head">
            <div class="pdf-brand">
                <svg width="24" height="24" viewBox="0 0 32 32" aria-hidden="true">
                    <circle cx="16" cy="16" r="14" fill="#C2553A" />
                    <path d="M16 6l3.5 10L16 26l-3.5-10z" fill="#FFFFFF" />
                </svg>
                Nomadiq
            </div>
            <span class="pdf-date">${escapeHtml(date)}</span>
        </header>
        <p class="pdf-query"><strong>Your request</strong>${escapeHtml(query)}</p>
        <div class="prose">${renderMarkdown(answer)}</div>
    `;

    return doc;
}

async function downloadPdf(query, answer) {
    const html2pdf = await loadHtml2Pdf();

    await html2pdf()
        .set({
            margin: [14, 14, 16, 14],
            filename: `nomadiq-${slugify(query)}.pdf`,
            image: { type: "jpeg", quality: 0.96 },
            // scrollX/Y: without these, html2canvas renders blank pages when the window is scrolled
            html2canvas: { scale: 2, useCORS: true, backgroundColor: "#FFFFFF", scrollX: 0, scrollY: 0 },
            jsPDF: { unit: "mm", format: "a4", orientation: "portrait" },
            pagebreak: { mode: ["css", "legacy"], avoid: ["tr", "blockquote", "li", "h2", "h3"] },
        })
        .from(buildPdfDoc(query, answer))
        .toPdf()
        .get("pdf")
        .then((pdf) => {
            const pages = pdf.internal.getNumberOfPages();
            const { width, height } = pdf.internal.pageSize;

            for (let i = 1; i <= pages; i++) {
                pdf.setPage(i);
                pdf.setFontSize(8);
                pdf.setTextColor(138, 144, 139);
                pdf.text("Planned with Nomadiq", 14, height - 8);
                pdf.text(`${i} / ${pages}`, width - 14, height - 8, { align: "right" });
            }
        })
        .save();
}

// =========================
// Results
// =========================

function addResult(data, elapsedMs, query) {
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

    const pdfBtn = $(".pdf-btn", node);
    const pdfLabel = $("span", pdfBtn);
    pdfBtn.addEventListener("click", async () => {
        pdfBtn.disabled = true;
        pdfLabel.textContent = "Preparing…";
        try {
            await downloadPdf(query, data.answer || "");
            pdfLabel.textContent = "Download PDF";
        } catch (err) {
            console.error(err);
            pdfLabel.textContent = "PDF failed";
            setTimeout(() => (pdfLabel.textContent = "Download PDF"), 2000);
        } finally {
            pdfBtn.disabled = false;
        }
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
        addResult(data, performance.now() - started, message);
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
