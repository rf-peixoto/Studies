/* scrub — front end.
   The one piece of visual personality here is the progress bar: it is rendered
   as monospace text, the way pv or wget draws one, rather than as a styled div. */

(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  /* ---------- file classification, for showing the right settings ---------- */

  const EXT = {
    image: ["jpg", "jpeg", "jpe", "png", "gif", "bmp", "tif", "tiff", "webp",
            "avif", "heic", "heif", "ppm", "tga", "ico"],
    video: ["mp4", "m4v", "mov", "mkv", "webm", "avi", "wmv", "flv", "mpg",
            "mpeg", "ts", "m2ts", "3gp", "ogv"],
    audio: ["mp3", "m4a", "aac", "wav", "flac", "ogg", "oga", "opus", "wma",
            "aiff", "aif", "alac", "mka"],
    pdf: ["pdf"]
  };

  function kindOf(name) {
    const ext = (name.split(".").pop() || "").toLowerCase();
    for (const k in EXT) if (EXT[k].indexOf(ext) >= 0) return k;
    return "unknown";
  }

  function human(n) {
    const u = ["B", "KB", "MB", "GB"];
    let i = 0;
    while (n >= 1024 && i < 3) { n /= 1024; i++; }
    return (i === 0 ? n.toFixed(0) : n.toFixed(1)) + " " + u[i];
  }

  /* ---------- staging ---------- */

  let staged = [];
  let job = null;
  let timer = null;

  const drop = $("drop");
  const picker = $("picker");

  drop.addEventListener("click", () => picker.click());
  drop.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); picker.click(); }
  });
  picker.addEventListener("change", () => { addFiles(picker.files); picker.value = ""; });

  ["dragenter", "dragover"].forEach((ev) =>
    drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("is-over"); }));
  ["dragleave", "drop"].forEach((ev) =>
    drop.addEventListener(ev, () => drop.classList.remove("is-over")));
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    if (e.dataTransfer && e.dataTransfer.files) addFiles(e.dataTransfer.files);
  });

  function addFiles(list) {
    for (const f of list) staged.push({ file: f, kind: kindOf(f.name) });
    renderStaged();
  }

  function renderStaged() {
    const ul = $("staged");
    ul.innerHTML = staged.map((s, i) =>
      `<li class="${s.kind === "unknown" ? "bad" : ""}">
         <span class="k">${s.kind === "unknown" ? "??" : esc(s.kind)}</span>
         <span class="n">${esc(s.file.name)}</span>
         <span class="s">${human(s.file.size)}</span>
         <button class="x" data-i="${i}" title="remove" aria-label="Remove ${esc(s.file.name)}">×</button>
       </li>`).join("");

    ul.querySelectorAll(".x").forEach((b) => b.addEventListener("click", () => {
      staged.splice(parseInt(b.dataset.i, 10), 1);
      renderStaged();
    }));

    const unknown = staged.filter((s) => s.kind === "unknown").length;
    const note = $("stagednote");
    note.hidden = unknown === 0;
    note.textContent = unknown
      ? `${unknown} file(s) are not a supported type and will be left alone.`
      : "";

    const kinds = new Set(staged.map((s) => s.kind));
    $("g-image").hidden = !kinds.has("image");
    $("g-video").hidden = !kinds.has("video");
    $("g-audio").hidden = !kinds.has("audio");
    $("g-pdf").hidden = !kinds.has("pdf");

    const any = staged.length > 0;
    $("settings-step").hidden = !any;
    $("run-step").hidden = !any;
    const gc = $("gocount");
    if (gc) gc.textContent = any ? `${staged.length} file${staged.length > 1 ? "s" : ""}` : "";
  }

  /* ---------- settings wiring ---------- */

  // Kept in step with VIDEO_ENCODERS in scrub/media.py.
  const CRF = {
    h264: [40, 24], h265: [44, 26], vp9: [50, 26], av1: [55, 30]
  };
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

  function bindRange(id, fmt) {
    const el = $(id), out = $(id + "-out");
    const upd = () => { out.textContent = fmt(parseInt(el.value, 10)); };
    el.addEventListener("input", upd);
    upd();
  }

  bindRange("img-q", (v) => String(v));
  bindRange("img-edge", (v) => (v === 0 ? "no limit" : v + " px"));
  bindRange("vid-abr", (v) => v + " kbps");
  bindRange("aud-kbps", (v) => v + " kbps");
  bindRange("pdf-q", (v) => String(v));
  bindRange("pdf-edge", (v) => (v === 0 ? "no limit" : v + " px"));
  bindRange("pdf-len", (v) => v + " chars");

  function updVideoQ() {
    const q = parseInt($("vid-q").value, 10);
    const c = $("vid-codec").value || "h264";
    const [floor, span] = CRF[c] || CRF.h264;
    $("vid-q-out").textContent = `${q} · crf ${Math.round(floor - (q / 100) * span)}`;
  }
  $("vid-q").addEventListener("input", updVideoQ);
  $("vid-codec").addEventListener("change", updVideoQ);

  const PRESETS = {
    archive:  { imgQ: 95, vidQ: 90, audKbps: 256, vidAbr: 192, pdfQ: 92,
                pdfEdge: 0, imgEdge: 0, vidH: "0" },
    balanced: { imgQ: 82, vidQ: 70, audKbps: 128, vidAbr: 128, pdfQ: 78,
                pdfEdge: 2000, imgEdge: 0, vidH: "1080" },
    small:    { imgQ: 62, vidQ: 45, audKbps: 64,  vidAbr: 96,  pdfQ: 58,
                pdfEdge: 1200, imgEdge: 2000, vidH: "720" }
  };

  document.querySelectorAll(".preset").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".preset").forEach((b) => b.classList.remove("is-on"));
      btn.classList.add("is-on");
      const p = PRESETS[btn.dataset.preset];
      $("img-q").value = p.imgQ;
      $("img-edge").value = p.imgEdge;
      $("vid-q").value = p.vidQ;
      $("vid-abr").value = p.vidAbr;
      $("vid-height").value = p.vidH;
      $("aud-kbps").value = p.audKbps;
      $("pdf-q").value = p.pdfQ;
      $("pdf-edge").value = p.pdfEdge;
      ["img-q", "img-edge", "vid-abr", "aud-kbps", "pdf-q", "pdf-edge"]
        .forEach((id) => $(id).dispatchEvent(new Event("input")));
      updVideoQ();
    });
  });

  $("pdf-imgs").addEventListener("change", () => {
    const on = $("pdf-imgs").checked;
    $("pdf-q-row").hidden = !on;
    $("pdf-edge-row").hidden = !on;
  });

  $("pdf-lock").addEventListener("change", () => {
    $("lockbox").hidden = !$("pdf-lock").checked;
  });

  /* ---------- password ---------- */

  $("pdf-gen").addEventListener("click", async () => {
    try {
      const r = await fetch("/api/password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ length: parseInt($("pdf-len").value, 10), symbols: true })
      });
      const d = await r.json();
      $("pdf-pw").value = d.password;
      $("entropy").textContent =
        `${d.bits} bits of entropy, from the system random source.`;
    } catch (e) {
      $("entropy").textContent = "Could not reach the generator.";
    }
  });

  $("pdf-copy").addEventListener("click", async () => {
    const v = $("pdf-pw").value;
    if (!v) return;
    try {
      await navigator.clipboard.writeText(v);
      $("pdf-copy").textContent = "copied";
      setTimeout(() => { $("pdf-copy").textContent = "copy"; }, 1400);
    } catch (e) {
      $("pdf-pw").select();
    }
  });

  /* ---------- the bar ---------- */

  function cells() { return window.innerWidth < 620 ? 14 : 26; }

  function bar(pct, label, cls) {
    const n = cells();
    const p = Math.max(0, Math.min(100, Math.round(pct)));
    const filled = Math.round(n * p / 100);
    return `<pre class="bar ${cls || ""}"><span class="lbl">${esc(label)}</span> [` +
           `<span class="fill">${"█".repeat(filled)}</span>` +
           `${"░".repeat(n - filled)}] ${String(p).padStart(3)}%</pre>`;
  }

  /* ---------- run ---------- */

  function options() {
    return {
      quality: parseInt($("img-q").value, 10),
      image_format: $("img-fmt").value,
      max_edge: parseInt($("img-edge").value, 10),

      video_codec: $("vid-codec").value,
      preset: $("vid-preset").value,
      max_height: parseInt($("vid-height").value, 10),
      video_audio_kbps: parseInt($("vid-abr").value, 10),

      audio_codec: $("aud-codec").value,
      audio_kbps: parseInt($("aud-kbps").value, 10),

      pdf_compress_images: $("pdf-imgs").checked,
      pdf_quality: parseInt($("pdf-q").value, 10),
      pdf_max_edge: parseInt($("pdf-edge").value, 10),
      pdf_strip_active: $("pdf-active").checked,
      pdf_open_password: $("pdf-open").value,
      pdf_password: $("pdf-lock").checked ? $("pdf-pw").value : "",
      pdf_permissions: {
        print: $("p-print").checked,
        extract: $("p-extract").checked,
        modify: $("p-modify").checked,
        annotate: $("p-annotate").checked,
        forms: $("p-forms").checked
      }
    };
  }

  $("go").addEventListener("click", () => {
    if (!staged.length) return;
    const opts = options();

    if ($("pdf-lock").checked && !$("pdf-pw").value) {
      fail("Set a password or generate one before locking the PDF.");
      return;
    }
    // The video slider drives quality per codec; make sure it is a real one.
    if (!opts.video_codec) opts.video_codec = "h264";

    fail("");
    $("go").disabled = true;
    $("overall").hidden = false;
    $("out-step").hidden = false;

    const fd = new FormData();
    staged.forEach((s) => fd.append("files", s.file, s.file.name));
    fd.append("options", JSON.stringify(opts));

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/jobs");
    xhr.upload.addEventListener("progress", (e) => {
      if (!e.lengthComputable) return;
      $("upwrap").innerHTML = bar(100 * e.loaded / e.total, "upload ", "");
    });
    xhr.addEventListener("load", () => {
      let d = {};
      try { d = JSON.parse(xhr.responseText); } catch (e) { /* handled below */ }
      if (xhr.status >= 400) {
        fail(d.error || `Upload failed (${xhr.status}).`);
        $("go").disabled = false;
        return;
      }
      job = d.id;
      render(d);
      timer = setInterval(poll, 400);
    });
    xhr.addEventListener("error", () => {
      fail("Lost the connection to the server.");
      $("go").disabled = false;
    });
    xhr.send(fd);
  });

  function fail(msg) {
    const e = $("err");
    e.hidden = !msg;
    e.textContent = msg;
  }

  async function poll() {
    if (!job) return;
    try {
      const r = await fetch("/api/jobs/" + job);
      if (!r.ok) { clearInterval(timer); return; }
      const d = await r.json();
      render(d);
      if (d.finished) {
        clearInterval(timer);
        timer = null;
        $("go").disabled = false;
        $("go").innerHTML = 'clean another batch';
      }
    } catch (e) {
      clearInterval(timer);
      fail("Lost contact with the job. It may still be running.");
    }
  }

  const TAGS = {
    done: ["ok", "clean"], running: ["run", "working"],
    queued: ["wait", "queued"], error: ["bad", "failed"],
    skipped: ["bad", "skipped"]
  };

  function render(d) {
    const open = new Set(
      Array.from(document.querySelectorAll(".trace:not([hidden])"))
        .map((el) => el.dataset.for));

    const total = d.items.length || 1;
    const doneish = d.items.reduce((a, i) => a + (i.pct || 0), 0) / total;
    $("totwrap").innerHTML = bar(doneish, "process", d.finished ? "done" : "");

    $("results").innerHTML = d.items.map((it) => {
      const [cls, word] = TAGS[it.status] || ["wait", it.status];
      const sizes = it.size_out
        ? `${human(it.size_in)} → ${human(it.size_out)}`
        : human(it.size_in);
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
          <span class="sizes">${sizes}</span>
          ${delta}
          ${dl}
        </div>
        ${bar(pct, it.kind.padEnd(5).slice(0, 5), barCls)}
        <button class="toggle" data-t="${it.id}">${open.has(it.id) ? "hide" : "show"} log</button>
        <pre class="trace" data-for="${it.id}" ${open.has(it.id) ? "" : "hidden"}>${esc(trace)}</pre>
      </div>`;
    }).join("");

    document.querySelectorAll(".toggle").forEach((b) => {
      b.addEventListener("click", () => {
        const pre = document.querySelector(`.trace[data-for="${b.dataset.t}"]`);
        pre.hidden = !pre.hidden;
        b.textContent = (pre.hidden ? "show" : "hide") + " log";
      });
    });

    const anyDone = d.items.some((i) => i.status === "done");
    $("outfoot").hidden = !anyDone;
    $("zip").href = "/api/jobs/" + d.id + "/archive";
    $("ttl").textContent = d.finished && d.seconds_left
      ? `Files are deleted from the server in ${Math.ceil(d.seconds_left / 60)} min.`
      : "";
  }

  $("forget").addEventListener("click", async () => {
    if (!job) return;
    await fetch("/api/jobs/" + job + "/forget", { method: "POST" });
    $("results").innerHTML = "";
    $("outfoot").hidden = true;
    $("overall").hidden = true;
    $("ttl").textContent = "";
    job = null;
    staged = [];
    $("go").innerHTML = 'clean <span id="gocount"></span>';
    renderStaged();
    $("out-step").hidden = true;
  });

  /* ---------- capabilities ---------- */

  (async function boot() {
    $("upwrap").innerHTML = bar(0, "upload ", "");
    $("totwrap").innerHTML = bar(0, "process", "");

    try {
      const c = await (await fetch("/api/capabilities")).json();
      $("vid-codec").innerHTML = c.video_codecs.map((k) =>
        `<option value="${k}"${k === "h264" ? " selected" : ""}>${esc(CODEC_LABEL[k] || k)}</option>`).join("");
      $("aud-codec").innerHTML = c.audio_codecs.map((k) =>
        `<option value="${k}"${k === "opus" ? " selected" : ""}>${esc(ACODEC_LABEL[k] || k)}</option>`).join("");
      updVideoQ();
      $("sysline").innerHTML =
        `video <b>${c.video_codecs.join(" ")}</b> · audio <b>${c.audio_codecs.join(" ")}</b> · ` +
        `up to <b>${c.max_mb} MB</b> and <b>${c.max_files}</b> files per run · ` +
        `<b>${c.workers}</b> worker(s) · output deleted after <b>${c.ttl_minutes} min</b>`;
    } catch (e) {
      $("sysline").textContent = "Could not read server capabilities.";
    }
  })();
})();
