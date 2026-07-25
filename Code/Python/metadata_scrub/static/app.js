/* scrub — front end.
   Flow: stage files -> inspect (read only) -> choose settings -> clean.
   The one piece of visual personality is the progress bar: monospace text,
   the way pv or wget draws one, rather than a styled div. */

(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  const EXT = {
    image: ["jpg","jpeg","jpe","png","gif","bmp","tif","tiff","webp","avif",
            "heic","heif","ppm","tga","ico"],
    video: ["mp4","m4v","mov","mkv","webm","avi","wmv","flv","mpg","mpeg","ts",
            "m2ts","3gp","ogv"],
    audio: ["mp3","m4a","aac","wav","flac","ogg","oga","opus","wma","aiff",
            "aif","alac","mka"],
    pdf: ["pdf"]
  };
  const kindOf = (name) => {
    const ext = (name.split(".").pop() || "").toLowerCase();
    for (const k in EXT) if (EXT[k].indexOf(ext) >= 0) return k;
    return "unknown";
  };
  function human(n) {
    const u = ["B","KB","MB","GB"];
    let i = 0;
    while (n >= 1024 && i < 3) { n /= 1024; i++; }
    return (i === 0 ? n.toFixed(0) : n.toFixed(1)) + " " + u[i];
  }

  let staged = [];
  let job = null;
  let timer = null;
  let phase = "staging";
  const showLow = {};

  /* ---------------- staging ---------------- */

  const drop = $("drop"), picker = $("picker");
  drop.addEventListener("click", () => picker.click());
  drop.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); picker.click(); }
  });
  picker.addEventListener("change", () => { addFiles(picker.files); picker.value = ""; });
  ["dragenter","dragover"].forEach((ev) => drop.addEventListener(ev, (e) => {
    e.preventDefault(); drop.classList.add("is-over"); }));
  ["dragleave","drop"].forEach((ev) => drop.addEventListener(ev, () =>
    drop.classList.remove("is-over")));
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    if (e.dataTransfer && e.dataTransfer.files) addFiles(e.dataTransfer.files);
  });

  function addFiles(list) {
    for (const f of list) staged.push({ file: f, kind: kindOf(f.name) });
    renderStaged();
  }

  function renderStaged() {
    $("staged").innerHTML = staged.map((s, i) =>
      `<li class="${s.kind === "unknown" ? "bad" : ""}">
         <span class="k">${s.kind === "unknown" ? "??" : esc(s.kind)}</span>
         <span class="n">${esc(s.file.name)}</span>
         <span class="s">${human(s.file.size)}</span>
         <button class="x" data-i="${i}" aria-label="Remove ${esc(s.file.name)}">×</button>
       </li>`).join("");
    $("staged").querySelectorAll(".x").forEach((b) => b.addEventListener("click", () => {
      staged.splice(parseInt(b.dataset.i, 10), 1);
      renderStaged();
    }));

    const unknown = staged.filter((s) => s.kind === "unknown").length;
    $("stagednote").hidden = unknown === 0;
    $("stagednote").textContent = unknown
      ? `${unknown} file(s) are not a supported type and will be left alone.` : "";

    const any = staged.length > 0;
    $("inspect-step").hidden = !any || phase !== "staging";
    const c = $("inspectcount");
    if (c) c.textContent = any ? `${staged.length} file${staged.length > 1 ? "s" : ""}` : "";
  }

  /* ---------------- settings ---------------- */

  const CRF = { h264: [40,24], h265: [44,26], vp9: [50,26], av1: [55,30] };
  const CODEC_LABEL = {
    h264: "H.264 — plays everywhere",
    h265: "H.265 — ~40% smaller, needs a recent player",
    av1:  "AV1 — smallest, slow to encode",
    vp9:  "VP9 — webm, good browser support"
  };
  const ACODEC_LABEL = {
    opus: "Opus — best quality per bit",
    aac:  "AAC — plays everywhere",
    mp3:  "MP3 — maximum compatibility",
    flac: "FLAC — lossless, larger"
  };
  const modes = { image: "quality", video: "quality", audio: "quality", pdf: "quality" };

  function bindRange(id, fmt) {
    const el = $(id), out = $(id + "-out");
    const upd = () => { out.textContent = fmt(parseInt(el.value, 10)); };
    el.addEventListener("input", upd); upd();
  }
  bindRange("img-q", String);
  bindRange("img-edge", (v) => v === 0 ? "no limit" : v + " px");
  bindRange("vid-abr", (v) => v + " kbps");
  bindRange("aud-kbps", (v) => v + " kbps");
  bindRange("pdf-q", String);
  bindRange("pdf-edge", (v) => v === 0 ? "no limit" : v + " px");
  bindRange("pdf-len", (v) => v + " chars");

  function updVideoQ() {
    const q = parseInt($("vid-q").value, 10);
    const [floor, span] = CRF[$("vid-codec").value] || CRF.h264;
    $("vid-q-out").textContent = `${q} · crf ${Math.round(floor - (q / 100) * span)}`;
  }
  $("vid-q").addEventListener("input", updVideoQ);
  $("vid-codec").addEventListener("change", updVideoQ);

  document.querySelectorAll(".mode").forEach((btn) => {
    btn.addEventListener("click", () => {
      const group = btn.dataset.mode, value = btn.dataset.v;
      modes[group] = value;
      document.querySelectorAll(`.mode[data-mode="${group}"]`)
        .forEach((b) => b.classList.toggle("is-on", b === btn));
      document.querySelectorAll(`[data-when^="${group}-"]`).forEach((row) => {
        row.hidden = row.dataset.when !== `${group}-${value}`;
      });
    });
  });

  document.querySelectorAll("[data-fill]").forEach((b) =>
    b.addEventListener("click", () => { $(b.dataset.fill).value = b.dataset.mb; }));

  const PRESETS = {
    archive:  { imgQ:95, vidQ:90, audKbps:256, vidAbr:192, pdfQ:92, pdfEdge:0,  imgEdge:0,    vidH:"0" },
    balanced: { imgQ:82, vidQ:70, audKbps:128, vidAbr:128, pdfQ:78, pdfEdge:2000, imgEdge:0,  vidH:"1080" },
    small:    { imgQ:62, vidQ:45, audKbps:64,  vidAbr:96,  pdfQ:58, pdfEdge:1200, imgEdge:2000, vidH:"720" }
  };
  document.querySelectorAll(".preset").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".preset").forEach((b) => b.classList.remove("is-on"));
      btn.classList.add("is-on");
      const p = PRESETS[btn.dataset.preset];
      $("img-q").value = p.imgQ; $("img-edge").value = p.imgEdge;
      $("vid-q").value = p.vidQ; $("vid-abr").value = p.vidAbr;
      $("vid-height").value = p.vidH; $("aud-kbps").value = p.audKbps;
      $("pdf-q").value = p.pdfQ; $("pdf-edge").value = p.pdfEdge;
      ["img-q","img-edge","vid-abr","aud-kbps","pdf-q","pdf-edge"]
        .forEach((id) => $(id).dispatchEvent(new Event("input")));
      updVideoQ();
    });
  });

  $("pdf-imgs").addEventListener("change", () => {
    const on = $("pdf-imgs").checked && modes.pdf === "quality";
    $("pdf-q-row").hidden = !on; $("pdf-edge-row").hidden = !on;
  });
  $("pdf-lock").addEventListener("change", () => {
    $("lockbox").hidden = !$("pdf-lock").checked;
  });

  /* ---------------- password ---------------- */

  let pwTimer = null;
  function armPasswordClear() {
    if (pwTimer) clearTimeout(pwTimer);
    // A generated password sitting in the DOM forever is a loose end.
    pwTimer = setTimeout(() => {
      if ($("pdf-pw").value) {
        $("pdf-pw").value = "";
        $("entropy").textContent = "Cleared from this page after five minutes.";
      }
    }, 300000);
  }
  $("pdf-gen").addEventListener("click", async () => {
    try {
      const r = await fetch("/api/password", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ length: parseInt($("pdf-len").value, 10), symbols: true })
      });
      const d = await r.json();
      $("pdf-pw").value = d.password;
      $("entropy").textContent = `${d.bits} bits of entropy, from the system random source.`;
      armPasswordClear();
    } catch (e) { $("entropy").textContent = "Could not reach the generator."; }
  });
  $("pdf-copy").addEventListener("click", async () => {
    const v = $("pdf-pw").value;
    if (!v) return;
    try {
      await navigator.clipboard.writeText(v);
      $("pdf-copy").textContent = "copied";
      setTimeout(() => { $("pdf-copy").textContent = "copy"; }, 1400);
    } catch (e) { $("pdf-pw").select(); }
  });

  /* ---------------- the bar ---------------- */

  const cells = () => window.innerWidth < 620 ? 14 : 26;
  function bar(pct, label, cls) {
    const n = cells();
    const p = Math.max(0, Math.min(100, Math.round(pct)));
    const filled = Math.round(n * p / 100);
    return `<pre class="bar ${cls || ""}"><span class="lbl">${esc(label)}</span> [` +
      `<span class="fill">${"█".repeat(filled)}</span>` +
      `${"░".repeat(n - filled)}] ${String(p).padStart(3)}%</pre>`;
  }

  /* ---------------- inspect ---------------- */

  $("inspect").addEventListener("click", () => {
    if (!staged.length) return;
    fail("err0", "");
    $("inspect").disabled = true;
    $("upwrap").hidden = false;
    $("upwrap").innerHTML = bar(0, "upload ", "");

    const fd = new FormData();
    staged.forEach((s) => fd.append("files", s.file, s.file.name));

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/jobs");
    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable) $("upwrap").innerHTML = bar(100 * e.loaded / e.total, "upload ", "");
    });
    xhr.addEventListener("load", () => {
      let d = {};
      try { d = JSON.parse(xhr.responseText); } catch (e) { /* below */ }
      if (xhr.status >= 400) {
        fail("err0", d.error || `Upload failed (${xhr.status}).`);
        $("inspect").disabled = false;
        return;
      }
      $("upwrap").innerHTML = bar(100, "upload ", "done");
      job = d.id; phase = "inspecting";
      render(d);
      timer = setInterval(poll, 400);
    });
    xhr.addEventListener("error", () => {
      fail("err0", "Lost the connection to the server.");
      $("inspect").disabled = false;
    });
    xhr.send(fd);
  });

  const SEV_ORDER = { high: 0, active: 1, medium: 2, low: 3 };

  function renderFindings(d) {
    const f = d.findings || {};
    const notable = (f.high || 0) + (f.active || 0);
    const v = $("verdict");
    v.hidden = false;
    v.classList.toggle("clean", notable === 0);
    v.innerHTML = notable === 0
      ? `Nothing identifying found. There is still metadata to remove — `
        + `<span class="count c-medium">${f.medium || 0}</span> equipment or timing `
        + `and <span class="count c-low">${f.low || 0}</span> technical entries.`
      : `Found <span class="count c-high">${f.high || 0}</span> entries that identify `
        + `a person or place`
        + (f.active ? `, <span class="count c-active">${f.active}</span> that run or carry a payload` : "")
        + `, <span class="count c-medium">${f.medium || 0}</span> about equipment or timing, `
        + `and <span class="count c-low">${f.low || 0}</span> technical.`;

    $("findings").innerHTML = d.items.map((it) => {
      const ins = it.inspection || {};
      const all = (ins.findings || []).slice()
        .sort((a, b) => SEV_ORDER[a.severity] - SEV_ORDER[b.severity]);
      const lows = all.filter((x) => x.severity === "low").length;
      const open = !!showLow[it.id];
      const list = all.filter((x) => x.severity !== "low" || open);
      const rows = list.map((x) =>
        `<li class="${x.severity === "low" ? "is-low" : ""}">
           <span class="sev sev-${x.severity}">${x.severity}</span>
           <span class="flabel">${esc(x.label)}</span>
           <span class="fvalue">${esc(x.value)}</span>
           ${x.note ? `<span class="fnote">${esc(x.note)}</span>` : ""}
         </li>`).join("");
      const toggle = lows
        ? `<button class="showlow" data-low="${it.id}">${open ? "hide" : "show"} ${lows} technical entr${lows === 1 ? "y" : "ies"}</button>`
        : "";
      const body = it.status === "inspecting"
        ? `<p class="lede">reading…</p>`
        : (all.length ? `<ul class="flist">${rows}</ul>${toggle}`
                      : `<p class="lede">Nothing found.</p>`);
      return `<div class="finding-file">
          <div class="finding-head">
            <span class="fkind">${esc(it.kind)}</span>
            <span class="fname">${esc(it.name)}</span>
            <span class="sizes">${human(it.size_in)}</span>
          </div>${body}</div>`;
    }).join("");

    $("findings").querySelectorAll(".showlow").forEach((b) =>
      b.addEventListener("click", () => {
        showLow[b.dataset.low] = !showLow[b.dataset.low];
        renderFindings(lastState);
      }));
  }

  /* ---------------- run ---------------- */

  function options() {
    return {
      image_mode: modes.image,
      image_target_mb: parseFloat($("img-mb").value) || 1,
      quality: parseInt($("img-q").value, 10),
      image_format: $("img-fmt").value,
      max_edge: parseInt($("img-edge").value, 10),

      video_mode: modes.video,
      video_target_mb: parseFloat($("vid-mb").value) || 25,
      video_codec: $("vid-codec").value || "h264",
      preset: $("vid-preset").value,
      max_height: parseInt($("vid-height").value, 10),
      video_audio_kbps: parseInt($("vid-abr").value, 10),

      audio_mode: modes.audio,
      audio_target_mb: parseFloat($("aud-mb").value) || 5,
      audio_codec: $("aud-codec").value || "opus",
      audio_kbps: parseInt($("aud-kbps").value, 10),

      pdf_mode: modes.pdf,
      pdf_target_mb: parseFloat($("pdf-mb").value) || 5,
      pdf_compress_images: $("pdf-imgs").checked,
      pdf_quality: parseInt($("pdf-q").value, 10),
      pdf_max_edge: parseInt($("pdf-edge").value, 10),
      pdf_strip_active: $("pdf-active").checked,
      pdf_open_password: $("pdf-open").value,
      pdf_password: $("pdf-lock").checked ? $("pdf-pw").value : "",
      pdf_permissions: {
        print: $("p-print").checked, extract: $("p-extract").checked,
        modify: $("p-modify").checked, annotate: $("p-annotate").checked,
        forms: $("p-forms").checked
      }
    };
  }

  $("go").addEventListener("click", async () => {
    if (!job) return;
    if ($("pdf-lock").checked && !$("pdf-pw").value) {
      fail("err", "Set a password or generate one before locking the PDF.");
      return;
    }
    fail("err", "");
    $("go").disabled = true;
    $("totwrap").hidden = false;
    $("out-step").hidden = false;
    try {
      const r = await fetch(`/api/jobs/${job}/run`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(options())
      });
      const d = await r.json();
      if (!r.ok) { fail("err", d.error || "Could not start."); $("go").disabled = false; return; }
      phase = "processing";
      render(d);
      if (!timer) timer = setInterval(poll, 400);
    } catch (e) {
      fail("err", "Lost the connection to the server.");
      $("go").disabled = false;
    }
  });

  function fail(id, msg) { const e = $(id); e.hidden = !msg; e.textContent = msg; }

  async function poll() {
    if (!job) return;
    try {
      const r = await fetch("/api/jobs/" + job);
      if (!r.ok) { clearInterval(timer); timer = null; return; }
      render(await r.json());
    } catch (e) {
      clearInterval(timer); timer = null;
      fail("err", "Lost contact with the job. It may still be running.");
    }
  }

  const TAGS = {
    done: ["ok","clean"], running: ["run","working"], queued: ["wait","queued"],
    error: ["bad","failed"], skipped: ["bad","skipped"],
    inspecting: ["run","reading"], ready: ["wait","ready"]
  };

  let lastState = null;

  function render(d) {
    lastState = d;

    if (d.phase === "inspecting" || d.phase === "ready") {
      renderFindings(d);
      if (d.phase === "ready") {
        if (timer) { clearInterval(timer); timer = null; }
        const kinds = new Set(d.items.filter((i) => i.status === "ready").map((i) => i.kind));
        $("g-image").hidden = !kinds.has("image");
        $("g-video").hidden = !kinds.has("video");
        $("g-audio").hidden = !kinds.has("audio");
        $("g-pdf").hidden = !kinds.has("pdf");
        $("settings-step").hidden = false;
        $("run-step").hidden = false;
      }
      return;
    }

    const total = d.items.length || 1;
    const avg = d.items.reduce((a, i) => a + (i.pct || 0), 0) / total;
    $("totwrap").innerHTML = bar(avg, "process", d.finished ? "done" : "");

    const open = new Set(Array.from(document.querySelectorAll(".trace:not([hidden])"))
      .map((el) => el.dataset.for));

    $("results").innerHTML = d.items.map((it) => {
      const [cls, word] = TAGS[it.status] || ["wait", it.status];
      const sizes = it.size_out ? `${human(it.size_in)} → ${human(it.size_out)}` : human(it.size_in);
      const delta = (it.delta === null || it.delta === undefined) ? "" :
        `<span class="delta ${it.delta < 0 ? "up" : ""}">${it.delta > 0 ? "−" : "+"}${Math.abs(it.delta)}%</span>`;
      const dl = it.status === "done"
        ? `<a class="mini" href="/api/jobs/${d.id}/files/${it.id}">download</a>` : "";
      const barCls = it.status === "done" ? "done"
        : (it.status === "error" || it.status === "skipped") ? "fail" : "";
      const pct = (it.status === "error" || it.status === "skipped") ? 100 : it.pct;
      const trace = (it.log || []).join("\n") + (it.error ? "\n! " + it.error : "");
      return `<div class="res">
        <div class="resline">
          <span class="tag ${cls}">[${word}]</span>
          <span class="resname">${esc(it.name)}</span>
          <span class="sizes">${sizes}</span>${delta}${dl}
        </div>
        ${bar(pct, it.kind.padEnd(5).slice(0,5), barCls)}
        <button class="toggle" data-t="${it.id}">${open.has(it.id) ? "hide" : "show"} log</button>
        <pre class="trace" data-for="${it.id}" ${open.has(it.id) ? "" : "hidden"}>${esc(trace)}</pre>
      </div>`;
    }).join("");

    document.querySelectorAll(".toggle").forEach((b) => b.addEventListener("click", () => {
      const pre = document.querySelector(`.trace[data-for="${b.dataset.t}"]`);
      pre.hidden = !pre.hidden;
      b.textContent = (pre.hidden ? "show" : "hide") + " log";
    }));

    const anyDone = d.items.some((i) => i.status === "done");
    $("outfoot").hidden = !anyDone;
    $("zip").href = "/api/jobs/" + d.id + "/archive";
    if (d.finished) {
      if (timer) { clearInterval(timer); timer = null; }
      $("go").disabled = false;
      $("ttl").textContent = d.seconds_left === null
        ? "Files are kept until you delete them."
        : `Files are deleted from the server in ${Math.ceil(d.seconds_left / 60)} min.`;
    }
  }

  $("forget").addEventListener("click", async () => {
    if (!job) return;
    await fetch("/api/jobs/" + job + "/forget", { method: "POST" });
    if (timer) { clearInterval(timer); timer = null; }
    job = null; staged = []; phase = "staging"; lastState = null;
    ["results","findings"].forEach((id) => { $(id).innerHTML = ""; });
    ["outfoot","out-step","settings-step","run-step","verdict","totwrap","upwrap"]
      .forEach((id) => { $(id).hidden = true; });
    $("ttl").textContent = "";
    $("inspect").disabled = false;
    $("go").disabled = false;
    renderStaged();
  });

  /* ---------------- boot ---------------- */

  (async function boot() {
    try {
      const c = await (await fetch("/api/capabilities")).json();
      $("vid-codec").innerHTML = c.video_codecs.map((k) =>
        `<option value="${k}"${k === "h264" ? " selected" : ""}>${esc(CODEC_LABEL[k] || k)}</option>`).join("");
      $("aud-codec").innerHTML = c.audio_codecs.map((k) =>
        `<option value="${k}"${k === "opus" ? " selected" : ""}>${esc(ACODEC_LABEL[k] || k)}</option>`).join("");
      updVideoQ();
      const retention = c.keeps_forever
        ? "kept until you delete them"
        : `deleted after <b>${c.ttl_minutes} min</b>`;
      $("sysline").innerHTML =
        `video <b>${c.video_codecs.join(" ")}</b> · audio <b>${c.audio_codecs.join(" ")}</b> · ` +
        `up to <b>${c.max_mb} MB</b> and <b>${c.max_files}</b> files per run · ` +
        `<b>${c.workers}</b> worker(s) × <b>${c.threads_each}</b> thread(s) · files ${retention}`;
    } catch (e) {
      $("sysline").textContent = "Could not read server capabilities.";
    }
  })();
})();
