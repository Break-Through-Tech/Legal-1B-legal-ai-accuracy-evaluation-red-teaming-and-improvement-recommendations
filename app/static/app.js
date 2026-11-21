"use strict";

const $ = (id) => document.getElementById(id);
const SEV_ORDER = { high: 3, medium: 2, low: 1 };
const SEVERITIES = ["high", "medium", "low"];
const STAGES = { existence: "Citations", quote_fidelity: "Quotes" };
const STATUS_LABEL = {
  "Valid/Verified": "Verified",
  "Hallucinated": "Not found",
  "Wrong Case Name": "Wrong case name",
  "Wrong Year": "Wrong year",
  "Mismatched Context/Format": "Outside corpus",
  material_difference: "Altered quote",
  misattributed: "Misattributed",
  not_found: "Quote not found",
  found_elsewhere: "Found in another source",
  verified: "Verified",
  minor_differences: "Minor differences",
  paraphrased: "Paraphrased",
  source_unavailable: "Source unavailable",
  no_source_match: "No source match",
};

const state = {
  report: null,
  severities: new Set(SEVERITIES),
  stages: new Set(Object.keys(STAGES)),
  showClean: false,
  active: null,
};

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
const sevClass = (f) => (f.flagged ? f.severity || "low" : "clean");

/* ---------- Intake ---------- */

function show(view) {
  $("intake").hidden = view !== "intake";
  $("loading").hidden = view !== "loading";
  $("results").hidden = view !== "results";
  $("new-doc").hidden = view !== "results";
}

function intakeError(msg) {
  const el = $("intake-error");
  el.textContent = msg;
  el.hidden = !msg;
}

async function submit(body, headers) {
  intakeError("");
  show("loading");
  try {
    const res = await fetch("/api/check", { method: "POST", body, headers });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
    if (data.risk?.level === "unknown") {
      throw new Error("That file could not be read. Make sure it is a Word .docx document.");
    }
    renderReport(data);
    show("results");
    window.scrollTo(0, 0);
  } catch (err) {
    show("intake");
    intakeError(err.message || String(err));
  }
}

function checkFile(file) {
  if (!file) return;
  if (!/\.docx$/i.test(file.name)) {
    intakeError("Please choose a Word .docx file.");
    return;
  }
  submit(file, { "Content-Type": "application/octet-stream", "X-Filename": encodeURIComponent(file.name) });
}

$("file-input").addEventListener("change", (e) => {
  checkFile(e.target.files[0]);
  e.target.value = "";
});
const dz = $("dropzone");
["dragenter", "dragover"].forEach((t) => dz.addEventListener(t, (e) => { e.preventDefault(); dz.classList.add("over"); }));
["dragleave", "drop"].forEach((t) => dz.addEventListener(t, (e) => { e.preventDefault(); dz.classList.remove("over"); }));
dz.addEventListener("drop", (e) => checkFile(e.dataTransfer.files[0]));

$("paste").addEventListener("input", (e) => { $("check-text").disabled = !e.target.value.trim(); });
$("check-text").addEventListener("click", () => {
  const text = $("paste").value;
  if (text.trim()) submit(JSON.stringify({ text }), { "Content-Type": "application/json" });
});
$("new-doc").addEventListener("click", () => { state.report = null; show("intake"); });

/* ---------- Results ---------- */

function visibleFlags() {
  const r = state.report;
  if (!r) return [];
  return r.flags.filter((f) => {
    if (!state.stages.has(f.stage)) return false;
    if (f.flagged) return state.severities.has(f.severity || "low");
    return state.showClean;
  });
}

function renderReport(report) {
  state.report = report;
  state.active = null;
  state.severities = new Set(SEVERITIES);
  state.stages = new Set(Object.keys(STAGES));
  state.showClean = false;
  $("show-clean").checked = false;

  $("doc-name").textContent = (report.filename || "Document").split(/[\\/]/).pop();
  $("doc-meta").textContent =
    `${report.summary.citations} citations · ${report.summary.quotes} quoted or copied passages · checked in ${Math.round(report.runtime.total_ms)} ms`;

  $("errors").innerHTML = (report.errors || []).map((e) =>
    `<div class="errbox">The <b>${esc(e.stage.replace("_", " "))}</b> step failed (${esc(e.type)}). Results may be incomplete.</div>`
  ).join("");

  renderRisk(report);
  renderFilters();
  renderAll();
}

function renderRisk(r) {
  const { score, level, drivers, incomplete } = r.risk;
  const pct = score == null ? 0 : score;
  const C = 2 * Math.PI * 32;
  const color = { high: "var(--high)", medium: "var(--medium)", low: "var(--low)", none: "var(--clean)" }[level] || "var(--ink-3)";
  const levelText = { high: "High risk", medium: "Medium risk", low: "Low risk", none: "No problems found", unknown: "Unknown" }[level] || level;
  const s = r.summary;
  $("risk").innerHTML = `
    <div class="risk-top">
      <div class="gauge" role="img" aria-label="Risk score ${score == null ? "unknown" : Math.round(pct * 100)} out of 100">
        <svg width="76" height="76" viewBox="0 0 76 76">
          <circle cx="38" cy="38" r="32" fill="none" stroke="var(--line)" stroke-width="7"/>
          <circle cx="38" cy="38" r="32" fill="none" stroke="${color}" stroke-width="7" stroke-linecap="round"
            stroke-dasharray="${C}" stroke-dashoffset="${C * (1 - pct)}"/>
        </svg>
        <div class="num">${score == null ? "–" : Math.round(pct * 100)}</div>
      </div>
      <div>
        <div class="risk-caption">Document risk</div>
        <div class="risk-level ${esc(level)}">${esc(levelText)}</div>
      </div>
    </div>
    ${drivers?.length ? `<ul class="drivers">${drivers.map((d) => `<li>${esc(d)}</li>`).join("")}</ul>` : ""}
    ${incomplete ? `<div class="incomplete">Some checks failed, so the score may be too low.</div>` : ""}
    <div class="stats">
      <div class="stat"><b>${s.citations_flagged} / ${s.citations}</b><span>citations flagged</span></div>
      <div class="stat"><b>${s.quotes_flagged} / ${s.quotes}</b><span>quotes flagged</span></div>
    </div>`;
}

function chip(label, count, pressed, onClick) {
  const b = document.createElement("button");
  b.className = "chip";
  b.setAttribute("aria-pressed", String(pressed));
  b.innerHTML = `${esc(label)} <span class="count">${count}</span>`;
  b.addEventListener("click", onClick);
  return b;
}

function renderFilters() {
  const flags = state.report.flags;
  const sevRow = $("severity-filters");
  sevRow.replaceChildren(...SEVERITIES.map((sev) => {
    const n = flags.filter((f) => f.flagged && (f.severity || "low") === sev).length;
    return chip(sev[0].toUpperCase() + sev.slice(1), n, state.severities.has(sev), () => {
      state.severities.has(sev) ? state.severities.delete(sev) : state.severities.add(sev);
      renderFilters(); renderAll();
    });
  }));
  const stageRow = $("stage-filters");
  stageRow.replaceChildren(...Object.entries(STAGES).map(([key, label]) => {
    const n = flags.filter((f) => f.stage === key && f.flagged).length;
    return chip(label, n, state.stages.has(key), () => {
      state.stages.has(key) ? state.stages.delete(key) : state.stages.add(key);
      renderFilters(); renderAll();
    });
  }));
}

$("show-clean").addEventListener("change", (e) => { state.showClean = e.target.checked; renderAll(); });

function renderAll() {
  renderList();
  renderDoc();
  if (state.active) highlightActive(false);
}

function renderList() {
  const list = $("flag-list");
  const flags = visibleFlags();
  if (!flags.length) {
    const anyFlagged = state.report.flags.some((f) => f.flagged);
    list.innerHTML = `<div class="empty">${anyFlagged ? "No items match these filters." : "No hallucinated citations or altered quotes were detected."}</div>`;
    return;
  }
  // Flagged items first by severity, then document order.
  const sorted = [...flags].sort((a, b) =>
    (SEV_ORDER[b.flagged ? b.severity : ""] || 0) - (SEV_ORDER[a.flagged ? a.severity : ""] || 0) || a.start - b.start);
  list.innerHTML = sorted.map(flagCard).join("");
  list.querySelectorAll(".flag").forEach((el) =>
    el.addEventListener("click", () => select(el.dataset.id, { scrollDoc: true })));
}

function flagCard(f) {
  const cls = sevClass(f);
  const isCite = f.stage === "existence";
  const kind = isCite ? `${f.citation_type || "citation"} citation` : (f.item_type === "unquoted" ? "copied passage" : "quotation");
  const badge = f.flagged ? `${f.severity} · ${STATUS_LABEL[f.status] || f.status}` : (STATUS_LABEL[f.status] || f.status);
  const active = state.active === f.flag_id;
  return `<button class="flag ${cls}${active ? " active" : ""}" data-id="${esc(f.flag_id)}" aria-expanded="${active}">
    <div class="flag-head"><span class="badge">${esc(badge)}</span><span class="flag-kind">${esc(kind)}</span></div>
    <div class="flag-text ${isCite ? "cite" : "quote"}">${isCite ? esc(f.text) : "“" + esc(f.text) + "”"}</div>
    <div class="flag-msg">${esc(f.message)}</div>
    ${active ? detail(f) : ""}
  </button>`;
}

function detail(f) {
  const ev = f.evidence || {};
  const rows = [];
  if (f.stage === "existence") {
    if (ev.mismatches?.length) {
      rows.push(["Mismatch", ev.mismatches.map((m) =>
        `<div class="diff-row">${esc(String(m.field || "").replace(/_/g, " "))}: ` +
        `<span class="diff-add" title="In the document">${esc(m.cited)}</span> → ` +
        `<span class="diff-del" title="In the corpus">${esc(m.corpus)}</span></div>`
      ).join("")]);
    }
    if (ev.matched_citations?.length) rows.push(["Matched in corpus", ev.matched_citations.map(esc).join("<br>")]);
    if (ev.authority) rows.push(["Authority key", `<span class="mono">${esc(ev.authority)}</span>`]);
  } else {
    if (ev.matched_source?.citation || ev.cited_raw) {
      rows.push(["Source", esc(ev.matched_source?.citation || ev.cited_raw)]);
    }
    if (ev.matched_text) rows.push(["Source text", `<div class="src">${esc(ev.matched_text)}</div>`]);
    if (ev.diffs?.length) {
      rows.push(["Differences", ev.diffs.map((d) => {
        const parts = [];
        if (d.source_text) parts.push(`<span class="diff-del" title="In the source">${esc(d.source_text)}</span>`);
        if (d.source_text && d.quote_text) parts.push(" → ");
        if (d.quote_text) parts.push(`<span class="diff-add" title="In the document">${esc(d.quote_text)}</span>`);
        const label = esc(String(d.type || "").replace(/_/g, " "));
        return `<div class="diff-row">${label}${d.material ? " (material)" : ""}: ${parts.join("")}</div>`;
      }).join("")]);
    }
    if (typeof ev.match_score === "number") rows.push(["Match score", `${Math.round(ev.match_score * 100)}%`]);
    if (ev.related_flag) rows.push(["Related", `See flag ${esc(ev.related_flag)}`]);
  }
  if (f.reason) rows.push(["Reason", esc(f.reason)]);
  if (!rows.length) return "";
  return `<dl class="detail">${rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`).join("")}</dl>`;
}

/* Build highlighted document. Spans may overlap (a citation inside a quote),
   so split the text at every span boundary and mark each piece with the most
   severe span covering it. */
function renderDoc() {
  const text = state.report.text || "";
  const spans = visibleFlags().filter((f) => f.end > f.start);
  const cuts = new Set([0, text.length]);
  spans.forEach((f) => { cuts.add(f.start); cuts.add(f.end); });
  const points = [...cuts].filter((p) => p >= 0 && p <= text.length).sort((a, b) => a - b);

  let html = "";
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i], b = points[i + 1];
    const piece = esc(text.slice(a, b));
    const cover = spans.filter((f) => f.start <= a && f.end >= b);
    if (!cover.length) { html += piece; continue; }
    // Most severe first; ties go to the narrower span (the citation inside a quote).
    cover.sort((x, y) =>
      (SEV_ORDER[y.flagged ? y.severity : ""] || 0) - (SEV_ORDER[x.flagged ? x.severity : ""] || 0) ||
      (x.end - x.start) - (y.end - y.start));
    const top = cover[0];
    const ids = cover.map((f) => f.flag_id).join(" ");
    const title = cover.map((f) => `${f.flagged ? f.severity.toUpperCase() + ": " : ""}${f.message}`).join("\n");
    html += `<mark class="${sevClass(top)}" data-id="${esc(top.flag_id)}" data-ids="${esc(ids)}" title="${esc(title)}">${piece}</mark>`;
  }
  const doc = $("doc");
  doc.innerHTML = html;
  doc.querySelectorAll("mark").forEach((m) =>
    m.addEventListener("click", () => select(m.dataset.id, { scrollList: true })));
}

function select(id, { scrollDoc = false, scrollList = false } = {}) {
  state.active = state.active === id && !scrollList ? null : id;
  renderList();
  highlightActive(scrollDoc);
  if (scrollList && state.active) {
    document.querySelector(`.flag[data-id="${CSS.escape(id)}"]`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
}

function highlightActive(scroll) {
  document.querySelectorAll(".doc mark.active").forEach((m) => m.classList.remove("active", "pulse"));
  if (!state.active) return;
  const marks = [...document.querySelectorAll(".doc mark")].filter((m) => m.dataset.ids.split(" ").includes(state.active));
  marks.forEach((m) => m.classList.add("active"));
  if (scroll && marks[0]) {
    marks[0].scrollIntoView({ block: "center", behavior: "smooth" });
    marks.forEach((m) => { void m.offsetWidth; m.classList.add("pulse"); });
  }
}
