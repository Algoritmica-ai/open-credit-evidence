/* Credit Evidence Engine — the browser side. Plain JS, no build step.
 *
 * State is four things: the chosen pack, the chosen case, the current run, and
 * which view is showing. Every view renders from a fetch of the API; nothing is
 * computed here that the engine computes, so the page can never disagree with
 * the CLI about a number. */

const state = { pack: null, packMeta: null, case: null, caseData: null, run: null, job: null };

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const api = async (path, opts) => {
  const r = await fetch(path, opts && { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(opts) });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || r.statusText);
  return body;
};
const short = (id) => (id.includes(":") ? id.split(":")[2] : id);
const pct = (n, d) => (d ? `${n}/${d}` : "—");

/* ----------------------------------------------------------------- views */

const steps = [...document.querySelectorAll(".rail .step")];
function show(view) {
  document.querySelectorAll(".view").forEach((v) => (v.hidden = v.id !== `view-${view}`));
  steps.forEach((s) => s.setAttribute("aria-current", s.dataset.view === view ? "true" : "false"));
  window.scrollTo({ top: 0 });
}
function enable(view, done) {
  const s = steps.find((x) => x.dataset.view === view);
  s.disabled = false;
  if (done) s.classList.add("complete");
}
steps.forEach((s) => s.addEventListener("click", () => !s.disabled && show(s.dataset.view)));

/* ------------------------------------------------------------------ pack */

async function loadMeta() {
  const m = await api("/api/meta");
  $("version").textContent = `v${m.version}`;
  $("roles").innerHTML = Object.entries(m.roles)
    .map(([role, r]) => `<div class="stat"><div class="k">${esc(role)} · ${esc(r.where)}</div><div class="v sm">${esc(r.model)}</div><div class="v sm" style="color:var(--ink-3)">${esc(r.endpoint)}</div></div>`)
    .join("");
  const w = m.roles.assistant.where;
  $("sut-where").textContent = `assistant: ${w}`;
  $("sut-where").hidden = false;
  if (!m.has_key && w === "cloud") $("run-error").innerHTML = `<div class="note warn"><strong>NVIDIA_API_KEY is not set.</strong> Runs against NVIDIA Build need it in <code>.env</code>. The gate works without it.</div>`;
}

async function loadPacks() {
  const packs = await api("/api/packs");
  $("packs").innerHTML = packs
    .map((p) => p.error
      ? `<div class="pack"><div class="pack-text"><div class="name">${esc(p.pack_id)}</div><div class="m">${esc(p.error)}</div></div></div>`
      : `<button class="pack" data-pack="${esc(p.pack_id)}"><div class="pack-text"><div class="name">${esc(p.pack_id)} <span class="tag">v${esc(p.version)}</span></div>
           <div class="m">${p.items} cases · ${esc(p.domain)} · checks: ${p.checks.join(", ")}${p.judges.length ? " · judge: " + p.judges.join(", ") : ""}${p.jurisdiction ? " · rule pack: " + esc(p.jurisdiction) : ""}</div></div>
           <span class="pack-id">${p.obligations.filter((o) => o.level === "evidences").map((o) => o.id).join(" · ")}</span></button>`)
    .join("");
  document.querySelectorAll("#packs .pack[data-pack]").forEach((b) =>
    b.addEventListener("click", () => choosePack(b.dataset.pack, packs.find((p) => p.pack_id === b.dataset.pack))));
}

async function choosePack(id, meta) {
  state.pack = id; state.packMeta = meta; state.case = null; state.caseData = null;
  $("pack-name").textContent = `${id} v${meta.version}`; $("pack-name").hidden = false;
  enable("pack", true); enable("case"); enable("run");
  await loadCases();
  show("case");
}

async function loadRuns() {
  const runs = await api("/api/runs");
  const t = $("runs-table");
  if (!runs.length) { t.innerHTML = `<tr><td class="nul">No runs yet.</td></tr>`; return; }
  const names = [...new Set(runs.flatMap((r) => Object.keys(r.checks)))];
  t.innerHTML = `<thead><tr><th>run</th><th>pack</th><th>assistant</th><th class="num">repeats</th>${names.map((n) => `<th class="num">${esc(n)}</th>`).join("")}<th></th></tr></thead><tbody>` +
    runs.map((r) => `<tr><td><code class="inline">${esc(r.run_id)}</code></td><td>${esc(r.pack.pack_id)} v${esc(r.pack.version)}</td>
      <td>${esc(r.sut.model_id || "")} <span class="badge ${r.sut.on_prem ? "good" : ""}">${r.sut.on_prem ? "on-prem" : "cloud"}</span></td><td class="num">${r.repeats}</td>` +
      names.map((n) => { const c = r.checks[n]; if (!c) return `<td class="nul">—</td>`; return c.gated ? `<td class="num ${c.failed ? "fail" : "pass"}">${pct(c.passed, c.passed + c.failed)}</td>` : `<td class="num">${c.mean_value ?? "—"}</td>`; }).join("") +
      `<td><button class="btn sm" data-run="${esc(r.run_id)}" ${r.sealed ? "" : "disabled"}>Open</button></td></tr>`).join("") + "</tbody>";
  t.querySelectorAll("button[data-run]").forEach((b) => b.addEventListener("click", () => openRun(b.dataset.run)));
}

/* ------------------------------------------------------------------ case */

async function loadCases() {
  const items = await api(`/api/packs/${state.pack}/items`);
  $("case-count").textContent = `${items.length} cases`;
  $("cases-table").innerHTML = `<thead><tr><th>case</th><th>outcome</th><th>difficulty</th><th>must state</th></tr></thead><tbody>` +
    items.map((i) => `<tr data-case="${esc(i.case)}" style="cursor:pointer"><td><code class="inline">${esc(i.case)}</code></td><td>${esc(i.disposition)}</td><td>${esc(i.difficulty)}</td><td class="wrap">${i.must_state.map(esc).join("; ")}</td></tr>`).join("") + "</tbody>";
  $("cases-table").querySelectorAll("tr[data-case]").forEach((tr) => tr.addEventListener("click", () => chooseCase(tr.dataset.case)));
  if (items.length) chooseCase(items[0].case);
}

async function chooseCase(c) {
  const d = await api(`/api/packs/${state.pack}/items/${c}`);
  state.case = c; state.caseData = d;
  $("case-title").textContent = c;
  $("case-disp").textContent = d.disposition; $("case-disp").hidden = false;
  $("case-key").innerHTML = `<dl class="kv">
    <dt>must state</dt><dd>${d.must_state.map((m) => `<span class="found">${esc(m)}</span>`).join(" · ")}</dd>
    <dt>drivers</dt><dd>${d.drivers.map(esc).join("; ") || "—"}</dd>
    <dt>decoys (zero weight)</dt><dd>${d.decoys.map((x) => `<code>${esc(x)}</code>`).join(" ") || "—"}</dd>
    <dt>would flip it</dt><dd>${d.flip.map((f) => `<code>${esc(f.ref)}</code> ${esc(f.direction)}`).join("; ") || "—"}</dd>
    <dt>checks</dt><dd>${d.checks.map((x) => `<code>${esc(x)}</code>`).join(" ")}</dd></dl>`;
  $("doc-tabs").innerHTML = [{ renderer: "task prompt", content: d.prompt }, ...d.documents]
    .map((doc, i) => `<button class="tab" data-i="${i}" aria-selected="${i === 1}">${esc(doc.renderer)}</button>`).join("");
  const docs = [{ renderer: "task prompt", content: d.prompt }, ...d.documents];
  const showDoc = (i) => { $("doc-body").textContent = docs[i].content; $("doc-body").hidden = false; $("doc-tabs").querySelectorAll(".tab").forEach((t) => t.setAttribute("aria-selected", t.dataset.i == i)); };
  $("doc-tabs").querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => showDoc(+t.dataset.i)));
  showDoc(1);
  $("gate-case").textContent = c;
  enable("case", true); enable("gate");
}

/* ------------------------------------------------------------------ gate */

function num(doc, label) { const m = doc.match(new RegExp(label + "\\s*\\|\\s*£?([\\d,]+)")); return m ? m[1].replace(/,/g, "") : null; }
function fillGate(kind) {
  const d = state.caseData; if (!d) return;
  const app = d.documents.find((x) => x.renderer === "application_form")?.content || "";
  const bureau = d.documents.find((x) => x.renderer === "bureau_summary")?.content || "";
  const inst = +num(app, "Indicative monthly instalment"), comm = +num(app, "Existing monthly credit commitments"), inc = +num(app, "Gross annual income");
  const score = (bureau.match(/\*\*(\d{3})\*\*/) || [])[1] || "?";
  const mi = inc / 12, ds = inst + comm, ratio = ((ds / mi) * 100).toFixed(1);
  $("gate-text").value = kind === "good"
    ? `Referred because total monthly debt service exceeds the 40% policy limit. Debt service is £${ds} (£${comm} existing commitments plus the £${inst} instalment) against gross monthly income of £${Math.round(mi).toLocaleString()}, a ratio of ${ratio}%. Bureau score ${score}, no missed payments in 24 months. Additional verified income, or a smaller amount over a longer term, would bring the ratio under 40%.`
    : `The applicant has an excellent bureau score of ${score} and a clean payment record. Income is £${inc.toLocaleString()} a year. The level of existing credit is on the high side and worth a look, and the ${d.decoys.includes("age_band") ? "age band and " : ""}number of dependants may be a concern. Recommend review.`;
}
$("gate-fill-good").addEventListener("click", () => fillGate("good"));
$("gate-fill-bad").addEventListener("click", () => fillGate("bad"));
$("gate-mark").addEventListener("click", async () => {
  if (!state.case) return;
  $("gate-results").innerHTML = `<span class="spin"></span>marking…`;
  try {
    const { results } = await api("/api/gate", { pack: state.pack, case: state.case, briefing: $("gate-text").value });
    $("gate-results").innerHTML = results.map(renderCheck).join("");
    enable("gate", true);
  } catch (e) { $("gate-results").innerHTML = `<div class="note bad">${esc(e.message)}</div>`; }
});
function renderCheck(r) {
  const ev = (r.evidence || []).map((e) => {
    if ("matched" in e) return `<li>${e.matched ? "✓" : "✗"} <b>${esc(e.ref)}</b>${e.method ? ` · ${esc(e.method)}` : " · missing"}${e.form ? ` · “${esc(e.form)}”` : ""}${e.sentence ? `<br><i style="color:var(--ink-3)">${esc(e.sentence)}</i>` : ""}</li>`;
    if ("grounded" in e) return `<li>${e.grounded ? "✓" : "✗"} <b>${esc(e.value)}</b> · ${esc(e.method || "not in the case file")}${e.derivation ? ` = ${esc(e.derivation)}` : ""}</li>`;
    if ("cited" in e) return e.mentioned ? `<li>${e.cited ? "✗ cited as a factor" : "· mentioned"}: <b>${esc(e.ref)}</b><br><i style="color:var(--ink-3)">${esc(e.sentence)}</i></li>` : "";
    if ("expected" in e) return `<li>${e.found && e.direction === e.expected ? "✓" : "✗"} <b>${esc(e.ref)}</b> · expected ${esc(e.expected)}${e.sentence ? `<br><i style="color:var(--ink-3)">${esc(e.sentence)}</i>` : " · not named"}</li>`;
    return `<li>${esc(JSON.stringify(e))}</li>`;
  }).join("");
  const gated = r.passed !== null && r.passed !== undefined;
  return `<div class="ob"><div class="ob-head"><code class="inline">${esc(r.name || r.check)}</code>
    ${gated ? `<span class="badge ${r.passed ? "good" : "bad"}">${r.passed ? "pass" : "fail"}</span>` : `<span class="badge">reported</span>`}
    <span class="tag">${r.value === null ? "—" : Number(r.value).toFixed(2)}</span>${r.needs_audit ? `<span class="badge warn">audit</span>` : ""}
    <span class="spacer"></span></div><div style="font-size:12.5px;color:var(--ink-2);margin-top:4px">${esc(r.detail)}</div>${ev ? `<ul>${ev}</ul>` : ""}</div>`;
}

/* ------------------------------------------------------------------- run */

let poll = null;
$("run-start").addEventListener("click", async () => {
  $("run-error").innerHTML = "";
  try {
    const job = await api("/api/run", { pack: state.pack, repeats: +$("run-repeats").value || 1, limit: $("run-limit").value ? +$("run-limit").value : null, judge: $("run-judge").checked });
    state.job = job.job_id; state.run = job.run_id;
    $("run-id").textContent = job.run_id; $("run-id").hidden = false;
    $("run-total").textContent = job.total; $("run-done").textContent = 0; $("run-bar").style.width = "0"; $("run-log").textContent = "";
    $("run-start").disabled = true; $("run-status").innerHTML = `<span class="spin"></span>running`;
    clearInterval(poll); poll = setInterval(pollJob, 2000);
  } catch (e) { $("run-error").innerHTML = `<div class="note bad">${esc(e.message)}</div>`; }
});
async function pollJob() {
  const j = await api(`/api/run/${state.job}`);
  $("run-done").textContent = j.done; $("run-total").textContent = j.total;
  $("run-bar").style.width = `${j.total ? (100 * j.done) / j.total : 0}%`;
  $("run-log").textContent = j.log.slice(-40).join("\n"); $("run-log").scrollTop = 1e9;
  if (j.status === "done") { clearInterval(poll); $("run-status").innerHTML = `<span class="badge good">done</span>`; $("run-start").disabled = false; enable("run", true); await loadRuns(); await openRun(j.run_id); }
  if (j.status === "error") { clearInterval(poll); $("run-status").innerHTML = `<span class="badge bad">error</span>`; $("run-start").disabled = false; $("run-error").innerHTML = `<div class="note bad">${esc(j.error)}</div>`; }
}

/* -------------------------------------------------------------- evidence */

async function openRun(runId) {
  const d = await api(`/api/runs/${runId}`);
  state.run = runId;
  $("ev-run").textContent = runId; $("ev-run").hidden = false; $("vf-run").textContent = runId; $("vf-run").hidden = false;
  const m = d.manifest, s = d.summary || { checks: {}, repeat_agreement: {}, failing: [], obligations: [] };
  $("ev-stats").innerHTML = [
    ["assistant", m.sut.model_id, m.sut.on_prem ? "on-prem" : "cloud"],
    ["briefings", m.transcripts, `${m.pack.items} cases × ${m.repeats}`],
    ["judge", m.judge ? m.judge.model_id : "off", m.judge ? (m.judge.on_prem ? "on-prem" : "cloud") : ""],
    ["rule pack", d.regulations ? `${d.regulations.status}` : "—", d.regulations?.ruleset_id || ""],
  ].map(([k, v, sub]) => `<div class="stat"><div class="k">${esc(k)}</div><div class="v sm">${esc(v)}</div><div class="v sm" style="color:var(--ink-3)">${esc(sub)}</div></div>`).join("");
  const ag = s.repeat_agreement || {};
  $("ev-obligations").innerHTML = s.obligations.map((o) => {
    const level = (o.level || "").replace("_", " ");
    const cls = o.level === "evidences" ? "good" : o.level === "contributes" ? "warn" : "";
    const lines = o.level === "does_not_cover" ? `<ul><li>${esc(o.reason)}</li></ul>` :
      `<ul>${o.checks.map((n) => { const c = s.checks[n]; if (!c) return ""; if (!c.gated) return `<li><b>${esc(n)}</b> mean ${c.mean_value} · reported, not gated</li>`;
        const a = ag[n]; return `<li><b>${esc(n)}</b> <span class="${c.failed ? "miss" : "found"}">${pct(c.passed, c.passed + c.failed)} pass</span> · mean ${c.mean_value}${c.needs_audit ? ` · ${c.needs_audit} audit` : ""}${a && m.repeats > 1 ? ` · stable ${pct(a.stable, a.items)}` : ""}</li>`; }).join("")}
        ${o.not_run.length ? `<li style="color:var(--ink-3)">declared, not run: ${o.not_run.join(", ")}</li>` : ""}</ul>`;
    return `<div class="ob"><div class="ob-head">${esc(o.title)} <span class="tag">${esc(o.id)}</span> <span class="badge ${cls}">${esc(level)}</span></div>${lines}</div>`;
  }).join("");
  const extra = Object.keys(s.checks).filter((n) => !s.obligations.some((o) => o.checks.includes(n)));
  if (extra.length) $("ev-obligations").innerHTML += `<div class="ob"><div class="ob-head">Reported outside the grid</div><ul>${extra.map((n) => `<li><b>${esc(n)}</b> mean ${s.checks[n].mean_value}</li>`).join("")}</ul></div>`;
  $("ev-failures").innerHTML = s.failing.length
    ? `<thead><tr><th>case</th><th>check</th><th class="num">repeats failed</th><th>detail</th></tr></thead><tbody>` + s.failing.map((f) => `<tr data-item="${esc(f.item_id)}" style="cursor:pointer"><td><code class="inline">${esc(short(f.item_id))}</code></td><td>${esc(f.check)}</td><td class="num">${f.repeats_failed}</td><td class="wrap">${esc(f.detail)}</td></tr>`).join("") + "</tbody>"
    : `<tr><td class="nul">No failures.</td></tr>`;
  $("ev-failures").querySelectorAll("tr[data-item]").forEach((tr) => tr.addEventListener("click", () => openTranscript(runId, d.transcripts.find((t) => t.startsWith(tr.dataset.item.replace(/[^A-Za-z0-9_.-]+/g, "_"))))));
  $("ev-report").innerHTML = md(d.report || "");
  $("ev-transcript").hidden = true;
  enable("evidence", true); enable("verify");
  $("vf-result").innerHTML = ""; $("vf-tamper-result").innerHTML = "";
  show("evidence");
}
async function openTranscript(runId, name) {
  if (!name) return;
  const t = await api(`/api/runs/${runId}/transcripts/${name}`);
  $("ev-transcript-name").textContent = `${name} · ${t.sut.model_id} · ${t.sut.endpoint || ""} · ${(t.latency_ms / 1000).toFixed(1)}s`; $("ev-transcript-name").hidden = false;
  $("ev-transcript").textContent = t.output; $("ev-transcript").hidden = false;
  $("ev-transcript").scrollIntoView({ behavior: "smooth", block: "center" });
}
/* A small markdown renderer for report.md: headings, tables, lists, code, bold. */
function md(src) {
  const inline = (s) => esc(s).replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
  const out = []; let list = null, table = null;
  const flush = () => { if (list) { out.push(`<ul>${list.join("")}</ul>`); list = null; } if (table) { out.push(`<table>${table.join("")}</table>`); table = null; } };
  for (const raw of src.split("\n")) {
    const line = raw.replace(/\s+$/, "");
    if (/^\|/.test(line)) { if (/^\|\s*-/.test(line)) continue; const cells = line.slice(1, -1).split("|").map((c) => inline(c.trim())); table = table || []; table.push(table.length ? `<tr>${cells.map((c) => `<td>${c}</td>`).join("")}</tr>` : `<tr>${cells.map((c) => `<th>${c}</th>`).join("")}</tr>`); continue; }
    if (/^\s*- /.test(line)) { if (table) flush(); list = list || []; list.push(`<li>${inline(line.replace(/^\s*- /, ""))}</li>`); continue; }
    flush();
    if (/^# /.test(line)) out.push(`<h1>${inline(line.slice(2))}</h1>`);
    else if (/^## /.test(line)) out.push(`<h2>${inline(line.slice(3))}</h2>`);
    else if (line) out.push(`<p>${inline(line)}</p>`);
  }
  flush(); return out.join("");
}

/* ---------------------------------------------------------------- verify */

function renderVerification(v) {
  const rows = [["files checked", v.files_checked], ["mismatched", v.mismatched.join(", ") || "none"], ["missing", v.missing.join(", ") || "none"], ["not in checksums", v.unlisted.join(", ") || "none"]];
  if (v.recomputed) rows.push(["check results re-derived", v.recomputed], ["disagreements", v.disagreements.length]);
  return `<div class="note ${v.ok ? "good" : "bad"}"><strong>${v.ok ? "OK" : "FAIL"}</strong> — ${esc(v.message)}<dl class="kv" style="margin-top:8px">${rows.map(([k, x]) => `<dt>${esc(k)}</dt><dd>${esc(x)}</dd>`).join("")}</dl></div>`;
}
$("vf-verify").addEventListener("click", async () => { $("vf-result").innerHTML = `<span class="spin"></span>`; $("vf-result").innerHTML = renderVerification(await api(`/api/runs/${state.run}/verify`, { recompute: false })); enable("verify", true); });
$("vf-recompute").addEventListener("click", async () => { $("vf-result").innerHTML = `<span class="spin"></span>re-deriving…`; $("vf-result").innerHTML = renderVerification(await api(`/api/runs/${state.run}/verify`, { recompute: true })); enable("verify", true); });
$("vf-tamper").addEventListener("click", async () => {
  $("vf-tamper-result").innerHTML = `<span class="spin"></span>`;
  try {
    const r = await api(`/api/runs/${state.run}/tamper-demo`, {});
    $("vf-tamper-result").innerHTML = `<p class="hint" style="margin:10px 0 6px">Edited <code class="inline">${esc(r.edit.transcript)}</code> in the copy <code class="inline">${esc(r.copy)}</code>: <code class="inline">${esc(r.edit.from)}</code> → <code class="inline">${esc(r.edit.to)}</code></p>
      <div class="grid two"><div><div class="badge">original</div>${renderVerification(r.original)}</div><div><div class="badge">tampered copy</div>${renderVerification(r.tampered)}</div></div>`;
  } catch (e) { $("vf-tamper-result").innerHTML = `<div class="note bad">${esc(e.message)}</div>`; }
});

/* ------------------------------------------------------------------ boot */

(async () => { await loadMeta(); await loadPacks(); await loadRuns(); })();
