/* =====================================================================
 *  Novel Timeline — frontend
 * ===================================================================== */
"use strict";

const state = {
    projectId: null,
    data: null,          // { project, characters, threads, locations, events }
    view: "timeline",
    currentDay: 1,
    dayWidth: 26,
    charFilter: new Set(),   // empty = show all
    threadFilter: new Set(), // empty = show all
};

/* ---- tiny helpers -------------------------------------------------- */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const el = (tag, attrs = {}, html = "") => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
        if (k === "class") n.className = v;
        else if (k.startsWith("on") && typeof v === "function")
            n.addEventListener(k.slice(2), v);
        else if (v !== null && v !== undefined) n.setAttribute(k, v);
    }
    if (html) n.innerHTML = html;
    return n;
};
const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
    c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function toast(msg) {
    const t = $("#toast");
    t.textContent = msg;
    t.classList.add("show");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => t.classList.remove("show"), 2200);
}

async function api(path, opts = {}) {
    const res = await fetch(path, {
        headers: { "Content-Type": "application/json" },
        ...opts,
    });
    if (!res.ok) {
        let msg = res.statusText;
        try { msg = (await res.json()).error || msg; } catch (e) {}
        throw new Error(msg);
    }
    return res.status === 204 ? null : res.json();
}

/* lookups into current data */
const chars = () => state.data.characters;
const threads = () => state.data.threads;
const locations = () => state.data.locations;
const events = () => state.data.events;
const charById = (id) => chars().find(c => c.id === id);
const threadById = (id) => threads().find(t => t.id === id);
const locById = (id) => locations().find(l => l.id === id);

/* day range derived from data (with sensible fallback) */
function dayRange() {
    let min = Infinity, max = -Infinity;
    for (const e of events()) { min = Math.min(min, e.day); max = Math.max(max, e.day); }
    for (const c of chars()) {
        if (c.appear_day != null) { min = Math.min(min, c.appear_day); max = Math.max(max, c.appear_day); }
        if (c.exit_day != null) { min = Math.min(min, c.exit_day); max = Math.max(max, c.exit_day); }
    }
    if (!isFinite(min)) { min = 1; max = 20; }
    if (min === max) max = min + 1;
    return { min, max };
}

const unit = () => (state.data?.project?.unit_label || "Day");

/* ---- project bootstrapping ---------------------------------------- */
async function loadProjects() {
    const list = await api("/api/projects");
    const sel = $("#project-select");
    sel.innerHTML = "";
    for (const p of list) sel.appendChild(el("option", { value: p.id }, esc(p.name)));

    if (list.length === 0) {
        const created = await api("/api/projects", {
            method: "POST",
            body: JSON.stringify({ name: "My novel", unit_label: "Day" }),
        });
        return loadProjects();
    }
    if (!state.projectId || !list.some(p => p.id === state.projectId))
        state.projectId = list[0].id;
    sel.value = state.projectId;
    await loadProject();
}

async function loadProject() {
    state.data = await api(`/api/projects/${state.projectId}`);
    state.charFilter.clear();
    state.threadFilter.clear();
    const { min } = dayRange();
    if (state.currentDay < min) state.currentDay = min;
    renderSidebar();
    render();
}

/* ===================================================================== *
 *  Sidebar
 * ===================================================================== */
function renderSidebar() {
    $("#char-count").textContent = chars().length;
    $("#thread-count").textContent = threads().length;
    $("#loc-count").textContent = locations().length;

    const cl = $("#char-list"); cl.innerHTML = "";
    for (const c of chars()) {
        const excluded = state.charFilter.size && !state.charFilter.has(c.id);
        const span = (c.appear_day != null || c.exit_day != null)
            ? `${c.appear_day ?? "…"}–${c.exit_day ?? "…"}` : "—";
        const item = el("div", { class: "row-item" + (excluded ? " dim" : ""), tabindex: "0" });
        item.append(
            el("span", { class: "swatch", style: `background:${esc(c.color)}` }),
            el("span", { class: "label" }, esc(c.name)),
            el("span", { class: "meta" }, span),
            el("button", { class: "icon-btn", title: "Edit", onclick: (e) => { e.stopPropagation(); openCharModal(c); } }, "✎"),
        );
        item.addEventListener("click", () => toggleFilter(state.charFilter, c.id));
        cl.appendChild(item);
    }
    if (!chars().length) cl.appendChild(el("div", { class: "hint", style: "padding:4px 8px" }, "No characters yet."));

    const tl = $("#thread-list"); tl.innerHTML = "";
    for (const t of threads()) {
        const excluded = state.threadFilter.size && !state.threadFilter.has(t.id);
        const item = el("div", { class: "row-item" + (excluded ? " dim" : ""), tabindex: "0" });
        item.append(
            el("span", { class: "swatch", style: `background:${esc(t.color)}` }),
            el("span", { class: "label" }, esc(t.name)),
            el("button", { class: "icon-btn", title: "Edit", onclick: (e) => { e.stopPropagation(); openThreadModal(t); } }, "✎"),
        );
        item.addEventListener("click", () => toggleFilter(state.threadFilter, t.id));
        tl.appendChild(item);
    }
    if (!threads().length) tl.appendChild(el("div", { class: "hint", style: "padding:4px 8px" }, "No threads yet."));

    const ll = $("#loc-list"); ll.innerHTML = "";
    for (const l of locations()) {
        const item = el("div", { class: "row-item", tabindex: "0" });
        item.append(
            el("span", { class: "swatch", style: `background:${esc(l.color)}` }),
            el("span", { class: "label" }, esc(l.name)),
            el("button", { class: "icon-btn", title: "Edit", onclick: (e) => { e.stopPropagation(); openLocModal(l); } }, "✎"),
        );
        ll.appendChild(item);
    }
    if (!locations().length) ll.appendChild(el("div", { class: "hint", style: "padding:4px 8px" }, "No locations yet."));
}

function toggleFilter(set, id) {
    if (set.has(id)) set.delete(id); else set.add(id);
    renderSidebar();
    render();
}

/* which characters/events pass the current filters */
function visibleChars() {
    return chars().filter(c => !state.charFilter.size || state.charFilter.has(c.id));
}
function eventPassesThread(e) {
    return !state.threadFilter.size || (e.thread_id && state.threadFilter.has(e.thread_id));
}

/* ===================================================================== *
 *  View router
 * ===================================================================== */
function render() {
    $$("#tabs .tab").forEach(t => t.classList.toggle("active", t.dataset.view === state.view));
    const v = $("#view");
    v.innerHTML = "";
    if (!state.data) return;
    ({
        timeline: renderTimeline,
        day: renderDayView,
        matrix: renderMatrix,
        events: renderEventsTable,
    }[state.view] || renderTimeline)(v);
}

/* ===================================================================== *
 *  1. Swimlane timeline
 * ===================================================================== */
function renderTimeline(root) {
    const cs = visibleChars();

    const toolbar = el("div", { class: "timeline-toolbar" });
    toolbar.append(
        el("button", { class: "btn small accent", onclick: () => openEventModal(null) }, "+ event"),
        (() => {
            const wrap = el("label", {}, `${esc(unit())} `);
            const rng = el("input", { type: "range" });
            const { min, max } = dayRange();
            rng.min = min; rng.max = max; rng.value = state.currentDay;
            rng.addEventListener("input", () => { state.currentDay = +rng.value; drawPlayhead(); readout.textContent = state.currentDay; });
            const readout = el("span", { class: "day-readout" }, String(state.currentDay));
            wrap.append(rng, " ", readout);
            return wrap;
        })(),
        (() => {
            const wrap = el("label", {}, "zoom ");
            const rng = el("input", { type: "range", min: "12", max: "60", value: String(state.dayWidth) });
            rng.addEventListener("input", () => { state.dayWidth = +rng.value; renderTimeline(root); });
            wrap.appendChild(rng);
            return wrap;
        })(),
    );
    if (state.charFilter.size || state.threadFilter.size) {
        toolbar.appendChild(el("button", { class: "btn small", onclick: () => { state.charFilter.clear(); state.threadFilter.clear(); renderSidebar(); render(); } }, "clear filters"));
    }
    root.appendChild(toolbar);

    if (!cs.length) { root.appendChild(el("div", { class: "empty" }, "No characters to show. Add one from the sidebar, or clear your filters.")); return; }

    const { min, max } = dayRange();
    const gutter = 150, rowH = 34, axisH = 28, padTop = 8, padRight = 24;
    const dw = state.dayWidth;
    const numDays = max - min + 1;
    const width = gutter + numDays * dw + padRight;
    const height = axisH + cs.length * rowH + padTop + 8;
    const xForDay = (d) => gutter + (d - min) * dw;
    const centerX = (d) => xForDay(d) + dw / 2;

    const svgNS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("width", width);
    svg.setAttribute("height", height);
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);

    const mk = (name, attrs) => {
        const n = document.createElementNS(svgNS, name);
        for (const [k, val] of Object.entries(attrs)) n.setAttribute(k, val);
        return n;
    };

    // axis grid + labels
    const tickEvery = dw < 18 ? 5 : (dw < 30 ? 2 : 1);
    for (let d = min; d <= max; d++) {
        const x = xForDay(d);
        const grid = mk("line", { x1: x, y1: axisH, x2: x, y2: height - 8, stroke: "#1c2530", "stroke-width": 1 });
        svg.appendChild(grid);
        if ((d - min) % tickEvery === 0) {
            const label = mk("text", { x: centerX(d), y: 18, fill: "#6b7d8f", "font-size": 11, "text-anchor": "middle", "font-family": "monospace" });
            label.textContent = d;
            svg.appendChild(label);
        }
    }
    // gutter divider
    svg.appendChild(mk("line", { x1: gutter, y1: 0, x2: gutter, y2: height, stroke: "#263341", "stroke-width": 1 }));
    svg.appendChild(mk("line", { x1: 0, y1: axisH, x2: width, y2: axisH, stroke: "#263341", "stroke-width": 1 }));

    // rows
    cs.forEach((c, i) => {
        const y = axisH + i * rowH;
        const cy = y + rowH / 2;
        // row separator
        svg.appendChild(mk("line", { x1: 0, y1: y + rowH, x2: width, y2: y + rowH, stroke: "#171e27", "stroke-width": 1 }));
        // name label
        const nameT = mk("text", { x: 12, y: cy + 4, fill: c.color, "font-size": 12, "font-family": "monospace" });
        nameT.textContent = c.name.length > 20 ? c.name.slice(0, 19) + "…" : c.name;
        svg.appendChild(nameT);

        // lifespan bar
        const a = c.appear_day != null ? c.appear_day : min;
        const b = c.exit_day != null ? c.exit_day : max;
        if (b >= a) {
            const bx = xForDay(a) + 2;
            const bw = Math.max(4, (b - a) * dw + dw - 4);
            const bar = mk("rect", { x: bx, y: cy - 4, width: bw, height: 8, rx: 2, fill: c.color, opacity: 0.22 });
            svg.appendChild(bar);
            // endpoints
            svg.appendChild(mk("rect", { x: bx, y: cy - 7, width: 2, height: 14, fill: c.color, opacity: c.appear_day != null ? 0.9 : 0.3 }));
            svg.appendChild(mk("rect", { x: bx + bw - 2, y: cy - 7, width: 2, height: 14, fill: c.color, opacity: c.exit_day != null ? 0.9 : 0.3 }));
        }

        // event markers for this character
        for (const e of events()) {
            if (!e.character_ids.includes(c.id)) continue;
            if (!eventPassesThread(e)) continue;
            const col = e.thread_id ? (threadById(e.thread_id)?.color || c.color) : c.color;
            const x = centerX(e.day);
            const g = mk("g", { class: "ev-marker", "data-eid": e.id, style: "cursor:pointer" });
            g.appendChild(mk("circle", { cx: x, cy: cy, r: 5, fill: col, stroke: "#0e1116", "stroke-width": 1.5 }));
            svg.appendChild(g);
        }
    });

    // playhead
    const playhead = mk("line", { id: "playhead", x1: centerX(state.currentDay), y1: 0, x2: centerX(state.currentDay), y2: height, stroke: "#e6b34d", "stroke-width": 1.5, "stroke-dasharray": "3 3", opacity: 0.9 });
    svg.appendChild(playhead);
    svg._centerX = centerX; // stash for playhead redraw

    // interactions
    svg.addEventListener("click", (ev) => {
        const g = ev.target.closest(".ev-marker");
        if (g) { const e = events().find(x => x.id === +g.dataset.eid); if (e) openEventModal(e); return; }
        // click on axis area -> move playhead
        const rect = svg.getBoundingClientRect();
        const scaleX = width / rect.width;
        const px = (ev.clientX - rect.left) * scaleX;
        if (px > gutter) {
            const d = Math.round(min + (px - gutter) / dw - 0.5);
            state.currentDay = Math.max(min, Math.min(max, d));
            drawPlayhead();
            const ro = $(".day-readout"); if (ro) ro.textContent = state.currentDay;
            const sld = $('.timeline-toolbar input[type="range"]'); if (sld) sld.value = state.currentDay;
        }
    });
    svg.addEventListener("mousemove", (ev) => {
        const g = ev.target.closest(".ev-marker");
        const tip = $("#tooltip");
        if (g) {
            const e = events().find(x => x.id === +g.dataset.eid);
            if (e) {
                const parts = e.character_ids.map(id => charById(id)?.name).filter(Boolean).join(", ");
                const th = e.thread_id ? threadById(e.thread_id)?.name : null;
                const lo = e.location_id ? locById(e.location_id)?.name : null;
                tip.innerHTML =
                    `<div class="t-title">${unit()} ${e.day} · ${esc(e.title)}</div>` +
                    (parts ? `<div class="t-meta">who: ${esc(parts)}</div>` : "") +
                    (th ? `<div class="t-meta">thread: ${esc(th)}</div>` : "") +
                    (lo ? `<div class="t-meta">place: ${esc(lo)}</div>` : "") +
                    (e.description ? `<div class="t-meta">${esc(e.description).slice(0, 140)}</div>` : "");
                tip.style.display = "block";
                tip.style.left = Math.min(ev.clientX + 14, window.innerWidth - 340) + "px";
                tip.style.top = (ev.clientY + 14) + "px";
            }
        } else { tip.style.display = "none"; }
    });
    svg.addEventListener("mouseleave", () => { $("#tooltip").style.display = "none"; });

    const scroll = el("div", { class: "swimlane-scroll" });
    const lane = el("div", { class: "swimlane" });
    lane.appendChild(svg);
    scroll.appendChild(lane);
    root.appendChild(scroll);

    root.appendChild(el("div", { class: "hint", style: "margin-top:8px" },
        "Click a dot to edit an event · click anywhere on the grid to move the playhead · bars show each character’s on-stage span (faded ends = open-ended)."));
}

function drawPlayhead() {
    const svg = $(".swimlane svg");
    if (!svg || !svg._centerX) return;
    const ph = svg.querySelector("#playhead");
    const x = svg._centerX(state.currentDay);
    ph.setAttribute("x1", x); ph.setAttribute("x2", x);
}

/* ===================================================================== *
 *  2. Day / Now view
 * ===================================================================== */
function renderDayView(root) {
    const { min, max } = dayRange();
    const picker = el("div", { class: "day-picker" });
    const rng = el("input", { type: "range", min, max, value: state.currentDay });
    const readout = el("span", { class: "day-readout", style: "min-width:90px" }, `${unit()} ${state.currentDay}`);
    const body = el("div");
    const redraw = () => {
        readout.textContent = `${unit()} ${state.currentDay}`;
        body.innerHTML = "";
        body.appendChild(dayPanels());
    };
    rng.addEventListener("input", () => { state.currentDay = +rng.value; redraw(); });
    picker.append(
        el("button", { class: "btn small", onclick: () => { state.currentDay = Math.max(min, state.currentDay - 1); rng.value = state.currentDay; redraw(); } }, "◀"),
        rng,
        el("button", { class: "btn small", onclick: () => { state.currentDay = Math.min(max, state.currentDay + 1); rng.value = state.currentDay; redraw(); } }, "▶"),
        readout,
    );
    root.append(picker, body);
    redraw();
}

function dayPanels() {
    const d = state.currentDay;
    const grid = el("div", { class: "now-grid" });

    // Acting now (events on this day)
    const dayEvents = events().filter(e => e.day === d && eventPassesThread(e));
    const actingIds = new Set();
    dayEvents.forEach(e => e.character_ids.forEach(id => actingIds.add(id)));

    const left = el("div", { class: "panel" });
    left.appendChild(el("div", { class: "panel-head" }, `Acting on ${esc(unit())} ${d} · ${dayEvents.length} event(s)`));
    const lb = el("div", { class: "panel-body" });
    if (!dayEvents.length) lb.appendChild(el("div", { class: "hint" }, "Nothing scheduled on this day."));
    for (const e of dayEvents) {
        const card = el("div", { class: "event-card", style: e.thread_id ? `border-left-color:${esc(threadById(e.thread_id)?.color || "#33475a")}` : "", onclick: () => openEventModal(e) });
        const who = e.character_ids.map(id => charById(id)).filter(Boolean);
        card.appendChild(el("div", { class: "ec-title" }, esc(e.title)));
        const meta = [];
        if (e.thread_id) meta.push("thread: " + esc(threadById(e.thread_id)?.name || ""));
        if (e.location_id) meta.push("place: " + esc(locById(e.location_id)?.name || ""));
        card.appendChild(el("div", { class: "ec-meta" }, meta.join("  ·  ")));
        const chips = el("div", { style: "margin-top:5px" });
        who.forEach(c => chips.appendChild(el("span", { class: "chip", style: `border-color:${esc(c.color)}` },
            `<span class="swatch" style="background:${esc(c.color)}"></span>${esc(c.name)}`)));
        card.appendChild(chips);
        lb.appendChild(card);
    }
    left.appendChild(lb);

    // On stage (lifespan covers this day)
    const right = el("div", { class: "panel" });
    right.appendChild(el("div", { class: "panel-head" }, "Cast status"));
    const rb = el("div", { class: "panel-body" });
    for (const c of chars()) {
        const a = c.appear_day, b = c.exit_day;
        const onStage = (a == null || a <= d) && (b == null || b >= d);
        const acting = actingIds.has(c.id);
        const status = acting ? "acting" : (onStage ? "on stage" : "off");
        const cls = acting ? "status-on" : (onStage ? "" : "status-off");
        const chip = el("div", { class: "chip", style: `border-color:${esc(c.color)};display:flex;width:100%;margin:3px 0` });
        chip.innerHTML =
            `<span class="swatch" style="background:${esc(c.color)}"></span>` +
            `<span style="flex:1">${esc(c.name)}</span>` +
            `<span class="${cls}">${status}</span>`;
        rb.appendChild(chip);
    }
    if (!chars().length) rb.appendChild(el("div", { class: "hint" }, "No characters yet."));
    right.appendChild(rb);

    grid.append(left, right);
    return grid;
}

/* ===================================================================== *
 *  3. Co-occurrence matrix (shared days)
 * ===================================================================== */
function renderMatrix(root) {
    const cs = chars();
    if (cs.length < 2) { root.appendChild(el("div", { class: "empty" }, "Add at least two characters to see who shares the stage.")); return; }

    // count shared DAYS: for each day, the set of acting characters; every pair +1
    const counts = {};
    const key = (a, b) => a < b ? `${a}:${b}` : `${b}:${a}`;
    const byDay = {};
    for (const e of events()) {
        if (!eventPassesThread(e)) continue;
        (byDay[e.day] = byDay[e.day] || new Set());
        e.character_ids.forEach(id => byDay[e.day].add(id));
    }
    let maxCount = 0;
    for (const set of Object.values(byDay)) {
        const ids = [...set];
        for (let i = 0; i < ids.length; i++)
            for (let j = i + 1; j < ids.length; j++) {
                const k = key(ids[i], ids[j]);
                counts[k] = (counts[k] || 0) + 1;
                maxCount = Math.max(maxCount, counts[k]);
            }
    }

    root.appendChild(el("div", { class: "hint", style: "margin-bottom:10px" },
        "Each cell = number of days both characters are active at the same time. Brighter = more shared days."));

    const wrap = el("div", { class: "matrix-wrap" });
    const table = el("table", { class: "matrix" });
    const thead = el("tr");
    thead.appendChild(el("th", { class: "corner" }, ""));
    cs.forEach(c => thead.appendChild(el("th", { class: "colhead", style: `color:${esc(c.color)}` }, esc(abbr(c.name)))));
    table.appendChild(thead);

    for (const rc of cs) {
        const tr = el("tr");
        tr.appendChild(el("th", { class: "rowhead", style: `color:${esc(rc.color)}` }, esc(rc.name)));
        for (const cc of cs) {
            if (rc.id === cc.id) { tr.appendChild(el("td", { class: "self" }, "·")); continue; }
            const n = counts[key(rc.id, cc.id)] || 0;
            const alpha = maxCount ? (0.12 + 0.88 * n / maxCount) : 0;
            const td = el("td", n ? {
                style: `background:rgba(79,208,214,${alpha.toFixed(2)});color:${alpha > 0.55 ? "#06222b" : "#c5d0da"}`,
                title: `${rc.name} + ${cc.name}: ${n} shared ${unit().toLowerCase()}(s)`,
            } : { style: "color:#33475a" }, n ? String(n) : "·");
            tr.appendChild(td);
        }
        table.appendChild(tr);
    }
    wrap.appendChild(table);
    root.appendChild(wrap);
}
function abbr(name) { return name.length > 6 ? name.slice(0, 5) + "…" : name; }

/* ===================================================================== *
 *  4. Events table
 * ===================================================================== */
function renderEventsTable(root) {
    const bar = el("div", { style: "margin-bottom:10px;display:flex;gap:10px;align-items:center" });
    bar.appendChild(el("button", { class: "btn small accent", onclick: () => openEventModal(null) }, "+ event"));
    bar.appendChild(el("span", { class: "hint" }, `${events().length} event(s) · click a row to edit`));
    root.appendChild(bar);

    const evs = events().filter(eventPassesThread);
    if (!evs.length) { root.appendChild(el("div", { class: "empty" }, "No events yet. Create one to place characters on the timeline.")); return; }

    const table = el("table", { class: "events" });
    table.innerHTML = `<thead><tr>
        <th>${esc(unit())}</th><th>Title</th><th>Thread</th><th>Place</th><th>Characters</th>
    </tr></thead>`;
    const tb = el("tbody");
    for (const e of evs) {
        const tr = el("tr", { onclick: () => openEventModal(e) });
        const th = e.thread_id ? threadById(e.thread_id) : null;
        const lo = e.location_id ? locById(e.location_id) : null;
        const who = e.character_ids.map(id => charById(id)?.name).filter(Boolean).join(", ");
        tr.innerHTML =
            `<td style="color:#e6b34d">${e.day}</td>` +
            `<td>${esc(e.title)}</td>` +
            `<td>${th ? `<span class="tag" style="color:${esc(th.color)}">${esc(th.name)}</span>` : "—"}</td>` +
            `<td>${lo ? `<span class="tag" style="color:${esc(lo.color)}">${esc(lo.name)}</span>` : "—"}</td>` +
            `<td>${esc(who) || "—"}</td>`;
        tb.appendChild(tr);
    }
    table.appendChild(tb);
    root.appendChild(table);
}

/* ===================================================================== *
 *  Modal system
 * ===================================================================== */
function openModal(title, bodyEl, buttons) {
    $("#modal-title").textContent = title;
    const body = $("#modal-body"); body.innerHTML = ""; body.appendChild(bodyEl);
    const foot = $("#modal-foot"); foot.innerHTML = "";
    for (const b of buttons) {
        foot.appendChild(el("button", { class: "btn " + (b.cls || ""), onclick: b.onclick }, b.label));
    }
    $("#modal-backdrop").classList.add("open");
}
function closeModal() { $("#modal-backdrop").classList.remove("open"); }

function fieldText(label, value, opts = {}) {
    const f = el("div", { class: "field" });
    f.appendChild(el("label", {}, esc(label)));
    const input = el("input", { type: opts.type || "text", value: value ?? "" });
    if (opts.placeholder) input.placeholder = opts.placeholder;
    f.appendChild(input);
    return { f, input };
}

/* ---- character editor --------------------------------------------- */
function openCharModal(c) {
    const body = el("div");
    const name = fieldText("Name", c?.name);
    const desc = el("div", { class: "field" });
    desc.appendChild(el("label", {}, "Notes"));
    const descI = el("textarea"); descI.value = c?.description || ""; desc.appendChild(descI);

    const rowSpan = el("div", { class: "field-row" });
    const appear = fieldText(`Appears (${unit()})`, c?.appear_day, { type: "number", placeholder: "e.g. 1" });
    const exit = fieldText(`Exits (${unit()})`, c?.exit_day, { type: "number", placeholder: "blank = stays" });
    rowSpan.append(appear.f, exit.f);

    const colorF = el("div", { class: "field" });
    colorF.appendChild(el("label", {}, "Colour"));
    const color = el("input", { type: "color", value: c?.color || "#6cc46c" });
    colorF.appendChild(color);

    body.append(name.f, rowSpan, colorF, desc);

    const save = async () => {
        const payload = {
            name: name.input.value.trim() || "Character",
            description: descI.value,
            appear_day: appear.input.value,
            exit_day: exit.input.value,
            color: color.value,
            sort_order: c?.sort_order || chars().length,
        };
        if (c) await api(`/api/characters/${c.id}`, { method: "PUT", body: JSON.stringify(payload) });
        else await api(`/api/projects/${state.projectId}/characters`, { method: "POST", body: JSON.stringify(payload) });
        closeModal(); await loadProject(); toast("Character saved");
    };
    const buttons = [{ label: "Cancel", onclick: closeModal }];
    if (c) buttons.push({ label: "Delete", cls: "danger", onclick: async () => {
        if (confirm(`Delete ${c.name}? This removes them from all events.`)) {
            await api(`/api/characters/${c.id}`, { method: "DELETE" });
            closeModal(); await loadProject(); toast("Character deleted");
        }
    }});
    buttons.push({ label: "Save", cls: "accent", onclick: save });
    openModal(c ? "Edit character" : "New character", body, buttons);
    setTimeout(() => name.input.focus(), 30);
}

/* ---- thread editor ------------------------------------------------- */
function openThreadModal(t) {
    const body = el("div");
    const name = fieldText("Name", t?.name);
    const desc = el("div", { class: "field" });
    desc.appendChild(el("label", {}, "Notes"));
    const descI = el("textarea"); descI.value = t?.description || ""; desc.appendChild(descI);
    const colorF = el("div", { class: "field" });
    colorF.appendChild(el("label", {}, "Colour"));
    const color = el("input", { type: "color", value: t?.color || "#e6b34d" });
    colorF.appendChild(color);
    body.append(name.f, colorF, desc);

    const save = async () => {
        const payload = { name: name.input.value.trim() || "Thread", description: descI.value, color: color.value };
        if (t) await api(`/api/threads/${t.id}`, { method: "PUT", body: JSON.stringify(payload) });
        else await api(`/api/projects/${state.projectId}/threads`, { method: "POST", body: JSON.stringify(payload) });
        closeModal(); await loadProject(); toast("Thread saved");
    };
    const buttons = [{ label: "Cancel", onclick: closeModal }];
    if (t) buttons.push({ label: "Delete", cls: "danger", onclick: async () => {
        await api(`/api/threads/${t.id}`, { method: "DELETE" });
        closeModal(); await loadProject(); toast("Thread deleted");
    }});
    buttons.push({ label: "Save", cls: "accent", onclick: save });
    openModal(t ? "Edit thread" : "New thread", body, buttons);
    setTimeout(() => name.input.focus(), 30);
}

/* ---- location editor ----------------------------------------------- */
function openLocModal(l) {
    const body = el("div");
    const name = fieldText("Name", l?.name);
    const colorF = el("div", { class: "field" });
    colorF.appendChild(el("label", {}, "Colour"));
    const color = el("input", { type: "color", value: l?.color || "#4fd0d6" });
    colorF.appendChild(color);
    body.append(name.f, colorF);

    const save = async () => {
        const payload = { name: name.input.value.trim() || "Place", color: color.value };
        if (l) await api(`/api/locations/${l.id}`, { method: "PUT", body: JSON.stringify(payload) });
        else await api(`/api/projects/${state.projectId}/locations`, { method: "POST", body: JSON.stringify(payload) });
        closeModal(); await loadProject(); toast("Location saved");
    };
    const buttons = [{ label: "Cancel", onclick: closeModal }];
    if (l) buttons.push({ label: "Delete", cls: "danger", onclick: async () => {
        await api(`/api/locations/${l.id}`, { method: "DELETE" });
        closeModal(); await loadProject(); toast("Location deleted");
    }});
    buttons.push({ label: "Save", cls: "accent", onclick: save });
    openModal(l ? "Edit location" : "New location", body, buttons);
    setTimeout(() => name.input.focus(), 30);
}

/* ---- event editor -------------------------------------------------- */
function openEventModal(e) {
    const body = el("div");

    const rowTop = el("div", { class: "field-row" });
    const day = fieldText(`${unit()}`, e?.day ?? state.currentDay, { type: "number" });
    const title = fieldText("Title", e?.title);
    day.f.style.maxWidth = "120px";
    rowTop.append(day.f, title.f);

    const rowSel = el("div", { class: "field-row" });
    const threadF = el("div", { class: "field" });
    threadF.appendChild(el("label", {}, "Thread"));
    const threadS = el("select");
    threadS.appendChild(el("option", { value: "" }, "— none —"));
    threads().forEach(t => threadS.appendChild(el("option", { value: t.id }, esc(t.name))));
    threadS.value = e?.thread_id || "";
    threadF.appendChild(threadS);

    const locF = el("div", { class: "field" });
    locF.appendChild(el("label", {}, "Location"));
    const locS = el("select");
    locS.appendChild(el("option", { value: "" }, "— none —"));
    locations().forEach(l => locS.appendChild(el("option", { value: l.id }, esc(l.name))));
    locS.value = e?.location_id || "";
    locF.appendChild(locS);
    rowSel.append(threadF, locF);

    const desc = el("div", { class: "field" });
    desc.appendChild(el("label", {}, "Description"));
    const descI = el("textarea"); descI.value = e?.description || ""; desc.appendChild(descI);

    const charF = el("div", { class: "field" });
    charF.appendChild(el("label", {}, "Characters acting in this event"));
    const checks = el("div", { class: "checks" });
    const selected = new Set(e?.character_ids || []);
    if (!chars().length) checks.appendChild(el("div", { class: "hint" }, "No characters yet — add some first."));
    chars().forEach(c => {
        const lab = el("label", { class: "check" });
        const cb = el("input", { type: "checkbox", value: c.id });
        cb.checked = selected.has(c.id);
        lab.append(cb, el("span", { class: "swatch", style: `background:${esc(c.color)}` }), document.createTextNode(c.name));
        checks.appendChild(lab);
    });
    charF.appendChild(checks);

    body.append(rowTop, rowSel, desc, charF);

    const save = async () => {
        const character_ids = $$("input[type=checkbox]", checks).filter(cb => cb.checked).map(cb => +cb.value);
        const payload = {
            day: day.input.value, title: title.input.value.trim() || "Untitled event",
            description: descI.value,
            thread_id: threadS.value || null, location_id: locS.value || null,
            character_ids,
        };
        if (e) await api(`/api/events/${e.id}`, { method: "PUT", body: JSON.stringify(payload) });
        else await api(`/api/projects/${state.projectId}/events`, { method: "POST", body: JSON.stringify(payload) });
        closeModal(); await loadProject(); toast("Event saved");
    };
    const buttons = [{ label: "Cancel", onclick: closeModal }];
    if (e) buttons.push({ label: "Delete", cls: "danger", onclick: async () => {
        await api(`/api/events/${e.id}`, { method: "DELETE" });
        closeModal(); await loadProject(); toast("Event deleted");
    }});
    buttons.push({ label: "Save", cls: "accent", onclick: save });
    openModal(e ? "Edit event" : "New event", body, buttons);
    setTimeout(() => title.input.focus(), 30);
}

/* ---- project settings --------------------------------------------- */
function openProjectModal() {
    const p = state.data.project;
    const body = el("div");
    const name = fieldText("Project name", p.name);
    const unitF = fieldText("Time unit label", p.unit_label, { placeholder: "Day / Chapter / Cycle…" });
    const desc = el("div", { class: "field" });
    desc.appendChild(el("label", {}, "Synopsis / notes"));
    const descI = el("textarea"); descI.value = p.description || ""; desc.appendChild(descI);
    body.append(name.f, unitF.f, desc);
    const save = async () => {
        await api(`/api/projects/${state.projectId}`, {
            method: "PUT",
            body: JSON.stringify({ name: name.input.value.trim() || "Untitled novel", unit_label: unitF.input.value.trim() || "Day", description: descI.value }),
        });
        closeModal(); await loadProjects(); toast("Project updated");
    };
    openModal("Project settings", body, [
        { label: "Cancel", onclick: closeModal },
        { label: "Save", cls: "accent", onclick: save },
    ]);
}

/* ===================================================================== *
 *  Import / export
 * ===================================================================== */
function exportProject() {
    window.location = `/api/projects/${state.projectId}/export`;
}
function importProject(file) {
    const reader = new FileReader();
    reader.onload = async () => {
        try {
            const payload = JSON.parse(reader.result);
            const res = await api("/api/projects/import", { method: "POST", body: JSON.stringify(payload) });
            state.projectId = res.project.id;
            await loadProjects();
            toast("Project imported");
        } catch (err) { toast("Import failed: " + err.message); }
    };
    reader.readAsText(file);
}

/* ===================================================================== *
 *  Wiring
 * ===================================================================== */
function wire() {
    $("#tabs").addEventListener("click", (e) => {
        const t = e.target.closest(".tab");
        if (t) { state.view = t.dataset.view; render(); }
    });
    $("#project-select").addEventListener("change", (e) => { state.projectId = +e.target.value; loadProject(); });
    $("#btn-new-project").addEventListener("click", async () => {
        const nm = prompt("Name of the new novel:", "Untitled novel");
        if (nm === null) return;
        const res = await api("/api/projects", { method: "POST", body: JSON.stringify({ name: nm || "Untitled novel" }) });
        state.projectId = res.project.id;
        await loadProjects(); toast("Project created");
    });
    $("#btn-edit-project").addEventListener("click", openProjectModal);
    $("#btn-delete-project").addEventListener("click", async () => {
        if (!confirm(`Delete “${state.data.project.name}” and everything in it? This cannot be undone.`)) return;
        await api(`/api/projects/${state.projectId}`, { method: "DELETE" });
        state.projectId = null; await loadProjects(); toast("Project deleted");
    });
    $("#btn-export").addEventListener("click", exportProject);
    $("#btn-import").addEventListener("click", () => $("#import-file").click());
    $("#import-file").addEventListener("change", (e) => { if (e.target.files[0]) importProject(e.target.files[0]); e.target.value = ""; });

    $("#btn-add-char").addEventListener("click", () => openCharModal(null));
    $("#btn-add-thread").addEventListener("click", () => openThreadModal(null));
    $("#btn-add-loc").addEventListener("click", () => openLocModal(null));

    $("#modal-close").addEventListener("click", closeModal);
    $("#modal-backdrop").addEventListener("click", (e) => { if (e.target.id === "modal-backdrop") closeModal(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });
}

wire();
loadProjects().catch(err => toast("Could not load: " + err.message));
