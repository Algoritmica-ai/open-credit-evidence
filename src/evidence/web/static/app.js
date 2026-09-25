/* Credit Evidence Engine — the browser side. Plain JS, no build step.
 *
 * State is four things: the chosen pack, the chosen case, the current run, and
 * which view is showing. Every view renders from a fetch of the API; nothing is
 * computed here that the engine computes, so the page can never disagree with
 * the CLI about a number. */

const state = { pack: null, packMeta: null, cases: [], caseIndex: -1, caseData: null, run: null, job: null, results: [], evCases: [], evIndex: -1, evRepeat: 0, transcripts: [] };

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
  if (m.shared) {
    const note = document.createElement("div");
    note.className = "note warn";
    note.innerHTML = `<strong>This is a hosted, shared demo.</strong> The models run wherever this instance is configured — NVIDIA Build, not your hardware — and runs are capped at ${m.limits.items} cases × ${m.limits.repeats} repeats. Packs you upload and runs you start are visible to other visitors and are wiped when the Space restarts. To evaluate on your own GPU, <a href="https://github.com/Algoritmica-ai/open-credit-evidence" target="_blank" rel="noopener">install it locally</a>: two commands.`;
    document.querySelector("#view-pack .head").after(note);
  }
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
  const first = packs.find((p) => !p.error);
  if (first && !state.pack) await loadSdd(first.pack_id);
}

/* Where the cases come from: the SDD recipe behind a pack, its run, and the scorecard's cut. */
async function loadSdd(packId) {
  let d;
  try { d = await api(`/api/packs/${packId}/sdd`); } catch (e) { $("sdd-card").hidden = true; return; }
  const s = d.sdd || {}, pop = d.population || {};
  $("sdd-installed").innerHTML = d.sdd_installed
    ? `<span class="badge good">SDD installed here</span>`
    : `<span class="badge">SDD not installed here · use the hosted one</span>`;
  const st = (html) => `<span class="st">${html}</span>`, ar = `<span class="ar">→</span>`;
  $("sdd-flow").innerHTML = [
    st(`SDD recipe <code class="inline">${esc(s.spec || "—")}</code>`),
    st(`<b>${s.generated ?? "—"}</b> applications · seed ${esc(s.seed ?? "—")}`),
    st(`scorecard: <b>${pop.approve ?? "—"}</b> approve · <b>${pop.refer ?? "—"}</b> refer · <b>${pop.decline ?? "—"}</b> decline`),
    st(`<b>${d.cases}</b> referred cases kept, closest to the line`),
    st(`marking key per case`),
  ].join(ar);
  const r = d.recipe;
  const names = (xs) => xs.map((x) => `<code class="inline">${esc(x)}</code>`).join(" ");
  $("sdd-recipe").innerHTML = r ? `<thead><tr><th>in the recipe</th><th>fields</th><th>what it means for a briefing</th></tr></thead><tbody>
    <tr><td>Hidden, never written out</td><td>${names(r.hidden)} <span class="tag">+ ${r.noise_terms} noise terms</span></td><td class="wrap">The truth about the applicant. The assistant has to infer it, as an underwriter would.</td></tr>
    <tr><td>Read from the hidden tier, with noise</td><td class="wrap">${names(r.derived)}</td><td class="wrap">The evidence. The facts a decision turns on come from here.</td></tr>
    <tr><td>Set per application, not from the tier</td><td class="wrap">${names(r.independent)}</td><td class="wrap">What was asked for and how it is documented. A good borrower can ask for too much.</td></tr>
    <tr><td>No path to the outcome</td><td class="wrap">${names(r.no_path)}</td><td class="wrap">Citing one as a reason is citing noise — the decoy check.</td></tr></tbody>` : "";
  $("sdd-notmarked").innerHTML = d.no_path_not_marked.length
    ? `<div class="note" style="margin-top:10px">Not marked as decoys in this pack: ${names(d.no_path_not_marked)}. They have no path to the outcome here, but an underwriter could reasonably weigh them and the lending policy does not rule them out, so citing one is not counted as an error.</div>` : "";
  $("sdd-open").href = d.links.space; $("sdd-source").href = d.links.source;
  $("sdd-spec").hidden = !d.spec_download; if (d.spec_download) $("sdd-spec").href = d.spec_download;
  $("sdd-prov").textContent = `${d.pack_id} · SDD spec hash ${s.spec_sha256 || "—"} · built ${(d.built_at || "").slice(0, 10)}`;
  $("sdd-card").hidden = false;
}

async function choosePack(id, meta) {
  state.pack = id; state.packMeta = meta; state.caseIndex = -1; state.caseData = null;
  loadSdd(id);
  $("pack-name").textContent = `${id} v${meta.version}`; $("pack-name").hidden = false;
  enable("pack", true); enable("case"); enable("run");
  try {
    const cov = await api(`/api/packs/${id}/coverage`);
    Object.values(cov.passages).forEach((p) => (passageIndex[p.passage_id] = p));
    $("coverage-scope").textContent = cov.in_scope_because || cov.framework || "";
    $("coverage").innerHTML = renderCoverage(cov.obligations, {}, null, 1);
    $("coverage-card").hidden = false;
  } catch (e) { $("coverage-card").hidden = true; }
  await loadCases();
  show("case");
}

let passageIndex = {};

/* The EU AI Act coverage block: one panel per article. `results` is the run's
   check summary (or {} on the Pack screen), `agreement` the repeat agreement. */
function renderCoverage(obligations, results, agreement, repeats) {
  const levelCls = (l) => (l === "evidences" ? "good" : l === "contributes" ? "warn" : "");
  const noRun = !Object.keys(results).some((k) => !k.startsWith("__"));
  const resultTag = (c) => {
    const r = results[c.name];
    if (!c.ran || !r) return c.registered ? `<span class="badge ${noRun ? "good" : ""}">${noRun ? "built" : "not run"}</span>` : `<span class="badge">planned</span>`;
    if (!r.gated) return `<span class="tag">mean ${r.mean_value}</span>`;
    const a = agreement && agreement[c.name];
    return `<span class="${r.failed ? "miss" : "found"}">${pct(r.passed, r.passed + r.failed)} pass</span>${a && repeats > 1 ? ` <span class="tag">stable ${pct(a.stable, a.items)}</span>` : ""}`;
  };
  return obligations.map((o) => {
    const art = o.id.replace("eu-ai-act:", "Article ");
    let body = "";
    if (o.level === "does_not_cover") body = `<ul><li>${esc(o.reason)}</li></ul>`;
    else {
      const req = o.requires ? `<p style="margin:6px 0 4px; font-size:12.5px"><i>What the Act requires:</i> ${esc(o.requires)}${o.passages.length ? ` <span style="color:var(--ink-3)">(${o.passages.map((p) => `<code>${esc(p)}</code>`).join(" ")})</span>` : ""}</p>` : "";
      const rows = o.check_basis.map((c) => `<tr><td><code class="inline">${esc(c.name)}</code></td><td>${resultTag(c)}</td><td class="wrap" style="color:var(--ink-2)"><b style="color:var(--ink)">${esc(c.ref || "")}</b> ${esc(c.tests || "")}</td></tr>`);
      if (o.judge) rows.push(`<tr><td><code class="inline">judge · ${esc(o.judge.name)}</code></td><td>${o.judge.result ? `<span class="tag">mean ${o.judge.result.mean_value}</span> reported` : `<span class="badge ${noRun ? "good" : ""}">${noRun ? "built" : "not run"}</span>`}</td><td class="wrap" style="color:var(--ink-2)"><b style="color:var(--ink)">${esc(o.judge.ref)}</b> ${esc(o.judge.tests)}</td></tr>`);
      if (o.metrics) for (const [k, m] of Object.entries(o.metrics)) {
        const vals = agreement ? Object.values(agreement) : [];
        const worst = vals.length ? vals.reduce((a, b) => (a.agreement < b.agreement ? a : b)) : null;
        rows.push(`<tr><td><code class="inline">${esc(k)}</code></td><td>${worst && repeats > 1 ? `<span class="tag">lowest ${pct(worst.stable, worst.items)}</span>` : `<span class="badge">needs repeats</span>`}</td><td class="wrap" style="color:var(--ink-2)"><b style="color:var(--ink)">${esc(m.ref)}</b> ${esc(m.tests)}</td></tr>`);
      }
      if (o.process) rows.push(`<tr><td><code class="inline">lender's process</code></td><td>${results.__rules ? `<span class="badge ${results.__rules === "pass" ? "good" : results.__rules === "fail" ? "bad" : ""}">${esc(results.__rules)}</span>` : `<span class="badge">rule pack</span>`}</td><td class="wrap" style="color:var(--ink-2)"><b style="color:var(--ink)">${esc(o.process.ref)}</b> ${esc(o.process.tests)}</td></tr>`);
      body = req + (rows.length ? `<table class="grid-table coverage"><thead><tr><th>test</th><th>result</th><th>what it tests, and why that is evidence</th></tr></thead><tbody>${rows.join("")}</tbody></table>` : `<p class="hint">No test declared.</p>`);
    }
    return `<div class="ob"><div class="ob-head">${esc(art)} — ${esc(o.title)} <span class="badge ${levelCls(o.level)}">${esc((o.level || "").replace("_", " "))}</span></div>${body}</div>`;
  }).join("");
}
async function loadCorpora() {
  const cs = await api("/api/corpora");
  const t = $("corpora-table");
  t.innerHTML = `<thead><tr><th>jurisdiction</th><th>title</th><th class="num">sources</th><th class="num">passages</th><th>embed model</th><th>corpus sha</th><th></th></tr></thead><tbody>` +
    cs.map((c) => `<tr><td><code class="inline">${esc(c.jurisdiction)}</code></td><td class="wrap">${esc(c.title || "")}</td><td class="num">${c.sources}</td>
      <td class="num">${c.built ? c.passages : `<span class="badge">not built</span>`}</td><td>${esc(c.embed_model || "—")}</td><td>${c.built ? `<code class="inline">${esc(c.corpus_sha256.slice(0, 12))}…</code>` : "—"}</td>
      <td style="white-space:nowrap"><button class="btn sm" data-build="${esc(c.jurisdiction)}">${c.built ? "Rebuild" : "Build"}</button> ${c.built ? `<button class="btn sm ghost" data-view="${esc(c.jurisdiction)}">Passages</button>` : ""}</td></tr>`).join("") + "</tbody>";
  const sel = $("run-corpus");
  sel.innerHTML = `<option value="none">none</option>` + cs.filter((c) => c.built).map((c) => `<option value="${esc(c.jurisdiction)}" ${c.jurisdiction === "EU" ? "selected" : ""}>${esc(c.jurisdiction)} — ${c.passages} passages</option>`).join("");
  t.querySelectorAll("button[data-build]").forEach((b) => b.addEventListener("click", async () => {
    $("corpus-status").innerHTML = `<span class="spin"></span>embedding passages…`;
    const j = await api(`/api/corpora/${b.dataset.build}/build`, {});
    const tick = setInterval(async () => {
      const job = await api(`/api/run/${j.job_id}`);
      if (job.status === "done") { clearInterval(tick); $("corpus-status").innerHTML = `<span class="badge good">built</span> ${job.passages} passages · sha ${esc(job.corpus_sha256.slice(0, 12))}…`; await loadCorpora(); }
      if (job.status === "error") { clearInterval(tick); $("corpus-status").innerHTML = `<span class="badge bad">failed</span> ${esc(job.error)}`; }
    }, 1500);
  }));
  t.querySelectorAll("button[data-view]").forEach((b) => b.addEventListener("click", async () => {
    const ps = await api(`/api/corpora/${b.dataset.view}/passages`);
    ps.forEach((p) => (passageIndex[p.passage_id] = p));
    $("corpus-passages").innerHTML = ps.map((p) => `<p><b>[${esc(p.passage_id)}]</b> ${esc(p.citation)} — ${esc(p.title)}<br>${esc(p.text)}</p>`).join("");
    $("corpus-passages").hidden = false;
  }));
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
  const sealed = runs.filter((r) => r.sealed);
  const opts = sealed.map((r) => `<option value="${esc(r.run_id)}">${esc(r.run_id)} — ${esc(r.sut.model_id || "")} (${r.sut.on_prem ? "on-prem" : "cloud"})</option>`).join("");
  $("cmp-before").innerHTML = opts; $("cmp-after").innerHTML = opts;
  if (sealed.length > 1) { $("cmp-before").selectedIndex = 1; $("cmp-after").selectedIndex = 0; enable("compare"); }
}

$("cmp-go").addEventListener("click", async () => {
  const before = $("cmp-before").value, after = $("cmp-after").value;
  if (before === after) { $("cmp-result").innerHTML = `<div class="card"><p class="nul">Choose two different runs.</p></div>`; return; }
  $("cmp-result").innerHTML = `<div class="card"><span class="spin"></span>comparing…</div>`;
  try {
    const c = await api(`/api/compare?before=${encodeURIComponent(before)}&after=${encodeURIComponent(after)}`);
    const rule = c.rule;
    $("cmp-result").innerHTML =
      (c.warnings.length ? `<div class="card">${c.warnings.map((w) => `<p class="hint" style="color:var(--warn)">${esc(w)}</p>`).join("")}</div>` : "") +
      `<div class="card"><div class="verdict ${VERDICT_CLASS[c.verdict] || "none"}"><div class="label">${esc(c.verdict)}</div>` +
      `<div class="sub">Accept when a check improves by at least ${Math.round(rule.min_gain * 100)} points with the whole interval above zero, and no check falls by more than ${Math.round(rule.max_regression * 100)} points. A fall whose interval reaches zero is <i>possibly worse</i>: run more repeats to settle it.</div></div>` +
      `<p class="hint"><b>What changed:</b> ${c.changed.length ? c.changed.map((x) => `${esc(x.what)}: <code class="inline">${esc(JSON.stringify(x.before))}</code> → <code class="inline">${esc(JSON.stringify(x.after))}</code>`).join(" · ") : "nothing recorded in the two manifests — any difference is run-to-run variation"}</p>` +
      `<div class="scroll"><table class="grid-table"><thead><tr><th>check</th><th class="num">cases</th><th class="num">before</th><th class="num">after</th><th class="num">change</th><th class="num">95% interval</th><th class="num">helped</th><th class="num">hurt</th><th>status</th></tr></thead><tbody>` +
      c.checks.map((r) => r.status === "not_comparable" ? `<tr><td><code class="inline">${esc(r.check)}</code></td><td colspan="7" class="nul">not in both runs</td><td></td></tr>` :
        `<tr><td><code class="inline">${esc(r.check)}</code></td><td class="num">${r.cases}</td><td class="num">${pc(r.before)}</td><td class="num">${pc(r.after)}</td><td class="num">${r.change >= 0 ? "+" : ""}${Math.round(r.change * 100)} pts</td><td class="num">${Math.round(r.interval[0] * 100)} to ${Math.round(r.interval[1] * 100)}</td><td class="num">${r.helped}</td><td class="num">${r.hurt}</td><td><span class="badge ${STATUS_BADGE[r.status] || ""}">${esc(r.status.replace(/_/g, " "))}</span></td></tr>`).join("") +
      `</tbody></table></div></div>` +
      `<div class="card"><div class="card-head"><h2>Causes, before and after</h2></div><div class="scroll"><table class="grid-table"><thead><tr><th>cause</th><th>lever</th><th class="num">before</th><th class="num">after</th></tr></thead><tbody>` +
      (c.causes.length ? c.causes.map((x) => `<tr><td>${esc(x.label)}</td><td>${esc(x.lever)}</td><td class="num">${x.before}</td><td class="num">${x.after}</td></tr>`).join("") : `<tr><td class="nul" colspan="4">No failures in either run.</td></tr>`) +
      `</tbody></table></div></div>`;
  } catch (e) { $("cmp-result").innerHTML = `<div class="card"><p class="nul">${esc(e.message || e)}</p></div>`; }
});

/* ------------------------------------------------------------------ case */

async function loadCases() {
  const items = await api(`/api/packs/${state.pack}/items`);
  state.cases = items;
  $("case-count").textContent = `${items.length} cases`;
  $("cases-table").innerHTML = `<thead><tr><th>case</th><th>outcome</th><th>difficulty</th><th>must state</th></tr></thead><tbody>` +
    items.map((i, k) => `<tr data-i="${k}" style="cursor:pointer"><td><code class="inline">${esc(i.case)}</code></td><td>${esc(i.disposition)}</td><td>${esc(i.difficulty)}</td><td class="wrap">${i.must_state.map(esc).join("; ")}</td></tr>`).join("") + "</tbody>";
  $("cases-table").querySelectorAll("tr[data-i]").forEach((tr) => tr.addEventListener("click", () => chooseCase(+tr.dataset.i)));
  if (items.length) chooseCase(0);
}

async function chooseCase(k) {
  if (!state.cases.length) return;
  k = (k + state.cases.length) % state.cases.length;
  const c = state.cases[k].case;
  const d = await api(`/api/packs/${state.pack}/items/${c}`);
  state.caseIndex = k; state.caseData = d;
  $("cases-table").querySelectorAll("tr[data-i]").forEach((tr) => tr.style.background = +tr.dataset.i === k ? "var(--accent-2)" : "");
  $("case-title").textContent = c;
  $("case-pos").textContent = `${k + 1} / ${state.cases.length}`;
  $("case-disp").textContent = d.disposition; $("case-disp").hidden = false;
  $("case-key").innerHTML = `<dl class="kv">
    <dt>must state</dt><dd>${d.must_state.map((m) => `<span class="found">${esc(m)}</span>`).join(" · ")}</dd>
    <dt>drivers</dt><dd>${d.drivers.map(esc).join("; ") || "—"}</dd>
    <dt>decoys (zero weight)</dt><dd>${d.decoys.map((x) => `<code>${esc(x)}</code>`).join(" ") || "—"}</dd>
    <dt>would flip it</dt><dd>${d.flip.map((f) => `<code>${esc(f.ref)}</code> ${esc(f.direction)}`).join("; ") || "—"}</dd>
    <dt>checks</dt><dd>${d.checks.map((x) => `<code>${esc(x)}</code>`).join(" ")}</dd></dl>`;
  const docs = [{ renderer: "task prompt", content: d.prompt }, ...d.documents];
  $("doc-tabs").innerHTML = docs.map((doc, i) => `<button class="tab" data-i="${i}" aria-selected="${i === 1}">${esc(doc.renderer)}</button>`).join("");
  const showDoc = (i) => { $("doc-body").innerHTML = md(docs[i].content); $("doc-body").hidden = false; $("doc-tabs").querySelectorAll(".tab").forEach((t) => t.setAttribute("aria-selected", t.dataset.i == i)); };
  $("doc-tabs").querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => showDoc(+t.dataset.i)));
  showDoc(1);
  $("gate-results").innerHTML = "";
  enable("case", true);
}
$("case-prev").addEventListener("click", () => chooseCase(state.caseIndex - 1));
$("case-next").addEventListener("click", () => chooseCase(state.caseIndex + 1));
$("case-to-run").addEventListener("click", () => show("run"));

/* ------------------------------------------------- mark by hand (control) */

function num(doc, label) { const m = doc.match(new RegExp(label + "\\s*\\|\\s*[£€]?([\\d,]+)")); return m ? m[1].replace(/,/g, "") : null; }
function fillGate(kind) {
  const d = state.caseData; if (!d) return;
  const app = d.documents.find((x) => x.renderer === "application_form")?.content || "";
  const bureau = d.documents.find((x) => x.renderer === "bureau_summary")?.content || "";
  const inst = +num(app, "Indicative monthly instalment"), comm = +num(app, "Existing monthly credit commitments"), inc = +num(app, "Gross annual income");
  const score = (bureau.match(/\*\*(\d{3})\*\*/) || [])[1] || "?";
  const mi = inc / 12, ds = inst + comm, ratio = ((ds / mi) * 100).toFixed(1);
  const cur = /€/.test(app) ? "€" : "£";  // the case file's currency
  $("gate-text").value = kind === "good"
    ? `Referred because total monthly debt service exceeds the 40% policy limit. Debt service is ${cur}${ds} (${cur}${comm} existing commitments plus the ${cur}${inst} instalment) against gross monthly income of ${cur}${Math.round(mi).toLocaleString()}, a ratio of ${ratio}%. Bureau score ${score}, no missed payments in 24 months. Additional verified income, or a smaller amount over a longer term, would bring the ratio under 40%.`
    : `The applicant has an excellent bureau score of ${score} and a clean payment record. Income is ${cur}${inc.toLocaleString()} a year. The level of existing credit is on the high side and worth a look, and the ${d.decoys.includes("age_band") ? "age band and " : ""}number of dependants may be a concern. Recommend review.`;
}
$("gate-fill-good").addEventListener("click", () => fillGate("good"));
$("gate-fill-bad").addEventListener("click", () => fillGate("bad"));
$("gate-mark").addEventListener("click", async () => {
  if (!state.caseData) return;
  $("gate-results").innerHTML = `<span class="spin"></span>marking…`;
  try {
    const { results } = await api("/api/gate", { pack: state.pack, case: state.caseData.case, briefing: $("gate-text").value });
    $("gate-results").innerHTML = results.map(renderCheck).join("");
  } catch (e) { $("gate-results").innerHTML = `<div class="note bad">${esc(e.message)}</div>`; }
});
function renderCheck(r) {
  const ev = (r.evidence || []).map((e) => {
    if ("matched" in e) return `<li>${e.matched ? "✓" : "✗"} <b>${esc(e.ref)}</b>${e.method ? ` · ${esc(e.method)}` : " · missing"}${e.form ? ` · “${esc(e.form)}”` : ""}${e.sentence ? `<br><i style="color:var(--ink-3)">${esc(e.sentence)}</i>` : ""}</li>`;
    if ("grounded" in e) return `<li>${e.grounded ? "✓" : "✗"} <b>${esc(e.value)}</b> · ${esc(e.method || "not in the case file")}${e.derivation ? ` = ${esc(e.derivation)}` : ""}</li>`;
    if ("cited" in e) return e.mentioned ? `<li>${e.cited ? "✗ cited as a factor" : "· mentioned"}: <b>${esc(e.ref)}</b><br><i style="color:var(--ink-3)">${esc(e.sentence)}</i></li>` : "";
    if (e.citations && !("matched" in e)) {
      const cite = (id, ok) => {
        const p = passageIndex[id];
        return id ? ` · cites <b>${esc(id)}</b>${ok === false ? ` <span class="badge bad">not among the passages given</span>` : ""}${p ? `<br><i style="color:var(--ink-3)">${esc(p.citation)}: ${esc(p.text.slice(0, 200))}…</i>` : ""}` : " · no citation";
      };
      return ["intelligible", "actionable", "overridable"].filter((k) => k in e)
        .map((k) => `<li>${k} <b>${e[k]}</b>${cite((e.citations[k] || {}).citation, (e.citations[k] || {}).in_passages)}</li>`).join("");
    }
    if ("citation" in e && !("matched" in e)) {
      const p = passageIndex[e.citation];
      return `<li>${["intelligible", "actionable", "overridable"].filter((k) => k in e).map((k) => `${k} <b>${e[k]}</b>`).join(" · ")}</li>` +
        (e.citation ? `<li>cites <b>${esc(e.citation)}</b>${e.citation_in_passages === false ? ` <span class="badge bad">not among the passages given</span>` : ""}${p ? `<br><i style="color:var(--ink-3)">${esc(p.citation)}: ${esc(p.text.slice(0, 260))}…</i>` : ""}</li>` : "");
    }
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
    const job = await api("/api/run", { pack: state.pack, repeats: +$("run-repeats").value || 1, limit: $("run-limit").value ? +$("run-limit").value : null, judge: $("run-judge").checked, corpus: $("run-corpus").value });
    state.job = job.job_id; state.run = job.run_id;
    $("run-id").textContent = job.run_id; $("run-id").hidden = false;
    $("run-total").textContent = job.total; $("run-done").textContent = 0; $("run-bar").style.width = "0"; $("run-log").textContent = "";
    $("run-start").disabled = true; $("run-cancel").disabled = false; $("run-status").innerHTML = `<span class="spin"></span>running`;
    clearInterval(poll); poll = setInterval(pollJob, 2000);
  } catch (e) { $("run-error").innerHTML = `<div class="note bad">${esc(e.message)}</div>`; }
});
async function pollJob() {
  const j = await api(`/api/run/${state.job}`);
  $("run-done").textContent = j.done; $("run-total").textContent = j.total;
  $("run-bar").style.width = `${j.total ? (100 * j.done) / j.total : 0}%`;
  $("run-log").textContent = j.log.slice(-40).join("\n"); $("run-log").scrollTop = 1e9;
  if (j.status === "done" || j.status === "cancelled") {
    clearInterval(poll); $("run-start").disabled = false; $("run-cancel").disabled = true;
    $("run-status").innerHTML = `<span class="badge ${j.status === "done" ? "good" : "warn"}">${j.status}</span>`;
    enable("run", true); await loadRuns();
    if (j.transcripts) await openRun(j.run_id); else $("run-error").innerHTML = `<div class="note warn">Cancelled before any briefing was written.</div>`;
  }
  if (j.status === "error") { clearInterval(poll); $("run-status").innerHTML = `<span class="badge bad">error</span>`; $("run-start").disabled = false; $("run-cancel").disabled = true; $("run-error").innerHTML = `<div class="note bad">${esc(j.error)}</div>`; }
}
$("run-cancel").addEventListener("click", async () => { if (state.job) { await api(`/api/run/${state.job}/cancel`, {}); $("run-cancel").disabled = true; } });

/* -------------------------------------------------------------- evidence */

async function openRun(runId) {
  const d = await api(`/api/runs/${runId}`);
  state.run = runId; state.transcripts = d.transcripts;
  state.results = await api(`/api/runs/${runId}/results`);
  const jc = d.manifest.judge && d.manifest.judge.corpus;
  if (jc && !Object.keys(passageIndex).some((k) => k)) {
    try { (await api(`/api/corpora/${jc.jurisdiction}/passages`)).forEach((p) => (passageIndex[p.passage_id] = p)); } catch (e) { /* corpus not built here */ }
  }
  state.evCases = [...new Set(state.results.map((r) => r.item_id))];
  state.evIndex = -1;
  $("ev-run").textContent = runId; $("ev-run").hidden = false; $("vf-run").textContent = runId; $("vf-run").hidden = false;
  const m = d.manifest, s = d.summary || { checks: {}, repeat_agreement: {}, failing: [], obligations: [] };
  $("ev-stats").innerHTML = [
    ["assistant", m.sut.model_id, m.sut.on_prem ? "on-prem" : "cloud"],
    ["briefings", m.transcripts, `${m.pack.items} cases × ${m.repeats}`],
    ["judge", m.judge ? m.judge.model_id : "off", m.judge ? `${m.judge.on_prem ? "on-prem" : "cloud"}${m.judge.corpus ? ` · cites ${m.judge.corpus.jurisdiction} ${m.judge.corpus.corpus_sha256.slice(0, 8)}` : ""}` : ""],
    ["lender's process (rule pack)", d.regulations ? `${d.regulations.status}` : "—", d.regulations?.ruleset_id ? `${d.regulations.ruleset_id} · ${d.regulations.applicable_rules} rules apply` : "no regulatory context"],
  ].map(([k, v, sub]) => `<div class="stat"><div class="k">${esc(k)}</div><div class="v sm">${esc(v)}</div><div class="v sm" style="color:var(--ink-3)">${esc(sub)}</div></div>`).join("");
  const ag = s.repeat_agreement || {};
  $("ev-obligations").innerHTML = renderCoverage(s.obligations, { ...s.checks, __rules: d.regulations && d.regulations.status }, ag, m.repeats);
  $("ev-failures").innerHTML = s.failing.length
    ? `<thead><tr><th>case</th><th>check</th><th class="num">repeats failed</th><th>detail</th></tr></thead><tbody>` + s.failing.map((f) => `<tr data-item="${esc(f.item_id)}" style="cursor:pointer"><td><code class="inline">${esc(short(f.item_id))}</code></td><td>${esc(f.check)}</td><td class="num">${f.repeats_failed}</td><td class="wrap">${esc(f.detail)}</td></tr>`).join("") + "</tbody>"
    : `<tr><td class="nul">No failures.</td></tr>`;
  $("ev-failures").querySelectorAll("tr[data-item]").forEach((tr) => tr.addEventListener("click", () => { showEvCase(state.evCases.indexOf(tr.dataset.item), 0); window.scrollTo({ top: 0, behavior: "smooth" }); }));
  $("ev-report").innerHTML = md(d.report || "");
  renderReaders(runId, d.readers);
  renderDecision(d.decision); renderAct(d.diagnosis, d.recommendations);
  if (state.evCases.length) showEvCase(0, 0);
  enable("evidence", true); enable("verify");
  $("vf-result").innerHTML = ""; $("vf-tamper-result").innerHTML = "";
  show("evidence");
}
const VERDICT_CLASS = { "GO": "go", "GO WITH CONDITIONS": "cond", "NO-GO": "nogo", "INCONCLUSIVE": "inc", "ACCEPT": "go", "REJECT": "nogo", "NO EFFECT": "none" };
const STATUS_BADGE = { go: "good", conditional: "warn", no_go: "bad", insufficient: "", not_run: "", improved: "good", regressed: "bad", possibly_worse: "warn", no_clear_change: "", not_comparable: "" };
const pc = (x) => (x == null ? "—" : `${Math.round(x * 100)}%`);

/* One evidence pack, a report per reader. */
async function showReader(runId, r) {
  document.querySelectorAll("#rd-tabs .tab").forEach((t) => t.setAttribute("aria-selected", t.dataset.r === r.name));
  $("rd-question").innerHTML = `<b>${esc(r.for)}</b> — ${esc(r.question)}`;
  const url = `/api/runs/${runId}/readers/${r.name}`;
  const res = await fetch(url);
  state.readerText = res.ok ? await res.text() : ""; state.readerTitle = `${runId} — ${r.title}`;
  $("rd-body").innerHTML = res.ok ? md(state.readerText) : `<p class="nul">Not available for this run.</p>`;
  $("rd-download").href = url;
  $("rd-pdf").href = `/api/runs/${runId}/pdf/${r.name}`;
}

function renderReaders(runId, readers) {
  const av = (readers || []).filter((r) => r.available);
  $("ev-readers-card").hidden = !av.length;
  if (!av.length) return;
  $("rd-tabs").innerHTML = av.map((r) => `<button class="tab" data-r="${esc(r.name)}" title="${esc(r.for)}">${esc(r.title)}</button>`).join("");
  $("rd-tabs").querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => showReader(runId, av.find((r) => r.name === t.dataset.r))));
  showReader(runId, av[0]);
}

const PRINT_CSS = `@page { size: A4; margin: 16mm; } body { font: 10.5pt/1.5 -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; color: #111; }
  h1 { font-size: 15pt; margin: 0 0 6pt; } h2 { font-size: 11.5pt; margin: 14pt 0 5pt; border-top: 1px solid #ccc; padding-top: 7pt; } h3 { font-size: 10.5pt; }
  table { border-collapse: collapse; width: 100%; font-size: 9pt; margin: 4pt 0 8pt; } th, td { border-bottom: 1px solid #ddd; padding: 3pt 5pt; text-align: left; vertical-align: top; }
  th { font-size: 8pt; text-transform: uppercase; letter-spacing: .04em; color: #555; } code { font: 8.5pt Menlo, Consolas, monospace; }
  blockquote { margin: 6pt 0; padding: 4pt 10pt; border-left: 3px solid #76b900; background: #f5f7f2; } pre { font: 8.5pt Menlo, monospace; background: #f4f4f4; padding: 6pt; white-space: pre-wrap; }
  tr, blockquote, pre { page-break-inside: avoid; }`;
$("rd-print").addEventListener("click", () => {
  const w = window.open("", "_blank");
  if (!w) return;
  w.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>${esc(state.readerTitle || "report")}</title><style>${PRINT_CSS}</style></head><body>${md(state.readerText || "")}</body></html>`);
  w.document.close(); w.focus(); w.print();
});

function renderDecision(dec) {
  $("ev-decision-card").hidden = !dec;
  if (!dec) return;
  $("ev-decision").innerHTML =
    `<div class="verdict ${VERDICT_CLASS[dec.verdict] || "none"}"><div class="label">${esc(dec.verdict)}</div>` +
    (dec.conditions.length ? `<ul class="conditions">${dec.conditions.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>` : "") + `</div>` +
    `<div class="scroll"><table class="grid-table"><thead><tr><th>check</th><th>what a failure means</th><th class="num">pass rate</th><th class="num">GO at</th><th>status</th></tr></thead><tbody>` +
    dec.checks.map((r) => `<tr><td><code class="inline">${esc(r.check)}</code></td><td class="wrap">${esc(r.meaning)}</td><td class="num">${pc(r.pass_rate)}</td><td class="num">${pc(r.go)}</td><td><span class="badge ${STATUS_BADGE[r.status] || ""}">${esc(r.status.replace(/_/g, " "))}</span></td></tr>`).join("") +
    `</tbody></table></div>` +
    `<details style="margin-top:10px"><summary class="hint" style="cursor:pointer">What this does not test</summary><ul class="conditions">${dec.not_tested.map((n) => `<li>${esc(n.what)}${n.why ? ` — ${esc(n.why)}` : ""}</li>`).join("")}</ul></details>`;
}

function renderAct(diag, recs) {
  $("ev-act").hidden = !diag;
  if (!diag) return;
  if (!diag.causes.length) { $("ev-causes").innerHTML = `<p class="nul">No failures.</p>`; $("ev-recs").innerHTML = `<p class="nul">Nothing to change.</p>`; return; }
  const example = {};
  diag.records.forEach((r) => { if (!(r.cause in example)) example[r.cause] = r; });
  $("ev-causes").innerHTML = `<div class="scroll"><table class="grid-table"><thead><tr><th>cause · who can act</th><th class="num">briefings</th><th class="num">failing results</th><th class="num">cases</th></tr></thead><tbody>` +
    diag.causes.map((c) => `<tr class="clickable" data-cause="${esc(c.cause)}" title="${esc(c.why)}"><td class="wrap">${esc(c.label)}<br><span class="badge ${c.owner === "vendor" ? "bad" : "good"}">${esc(c.owner)}</span> <span class="badge">${esc(c.lever)}</span></td><td class="num">${c.briefings ?? "—"}</td><td class="num">${c.results}</td><td class="num">${c.items}</td></tr>`).join("") +
    `</tbody></table></div>`;
  $("ev-causes").querySelectorAll("tr[data-cause]").forEach((tr) => tr.addEventListener("click", () => {
    const ex = example[tr.dataset.cause];
    if (ex) { showEvCase(state.evCases.indexOf(ex.item_id), ex.repeat); $("ev-case").scrollIntoView({ behavior: "smooth", block: "center" }); }
  }));
  $("ev-recs").innerHTML = (recs || []).map((r) => `<div class="rec"><h3>${r.rank}. ${esc(r.title)}</h3>` +
    `<p><span class="badge good">${esc(r.owner)} can act</span> <span class="badge">${esc(r.lever)}</span>${r.raise_with_vendor ? ` <span class="badge warn">vendor, if it persists</span>` : ""} · addresses ${r.addresses.briefings != null ? `${r.addresses.briefings} briefings (${r.addresses.results} failing results)` : `${r.addresses.results} failing results`} on ${r.addresses.items} cases</p>` +
    `<p>${esc(r.action)}</p></div>`).join("");
}

async function showEvCase(k, rep) {
  if (!state.evCases.length) return;
  k = (k + state.evCases.length) % state.evCases.length;
  const item = state.evCases[k];
  const rows = state.results.filter((r) => r.item_id === item);
  const reps = [...new Set(rows.map((r) => r.repeat))].sort((a, b) => a - b);
  rep = reps.includes(rep) ? rep : reps[0];
  state.evIndex = k; state.evRepeat = rep;
  $("ev-case").textContent = short(item);
  $("ev-pos").textContent = `${k + 1} / ${state.evCases.length}`;
  $("ev-repeats").innerHTML = reps.map((r) => `<button class="tab" data-r="${r}" aria-selected="${r === rep}">repeat ${r + 1}</button>`).join("");
  $("ev-repeats").querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => showEvCase(k, +t.dataset.r)));
  const name = state.transcripts.find((t) => t.startsWith(item.replace(/[^A-Za-z0-9_.-]+/g, "_")) && t.endsWith(`-r${rep}.json`));
  if (name) {
    const t = await api(`/api/runs/${state.run}/transcripts/${name}`);
    $("ev-meta").textContent = `${t.sut.model_id} · ${t.sut.endpoint || ""} · ${(t.latency_ms / 1000).toFixed(1)}s · ${t.tokens_out} tokens`;
    $("ev-briefing").innerHTML = md(t.output);
  } else { $("ev-meta").textContent = ""; $("ev-briefing").textContent = "(transcript not found)"; }
  $("ev-verdicts").innerHTML = rows.filter((r) => r.repeat === rep).map((r) => renderCheck({ ...r, name: r.check })).join("");
}
$("ev-prev").addEventListener("click", () => showEvCase(state.evIndex - 1, state.evRepeat));
$("ev-next").addEventListener("click", () => showEvCase(state.evIndex + 1, state.evRepeat));

/* A small markdown renderer for report.md: headings, tables, lists, code, bold. */
function md(src) {
  const inline = (s) => esc(s).replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>").replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<i>$2</i>");
  const out = []; let list = null, table = null, quote = null, code = null, listTag = "ul";
  const flush = () => { if (list) { out.push(`<${listTag}>${list.join("")}</${listTag}>`); list = null; } if (table) { out.push(`<table>${table.join("")}</table>`); table = null; } if (quote) { out.push(`<blockquote>${quote.join(" ")}</blockquote>`); quote = null; } };
  for (const raw of src.split("\n")) {
    const line = raw.replace(/\s+$/, "");
    if (/^```/.test(line)) { if (code) { out.push(`<pre>${code.join("\n")}</pre>`); code = null; } else { flush(); code = []; } continue; }
    if (code) { code.push(esc(raw)); continue; }
    if (/^> ?/.test(line)) { if (list || table) flush(); quote = quote || []; quote.push(inline(line.replace(/^> ?/, ""))); continue; }
    if (/^\|/.test(line)) { if (/^\|[\s:-]*\|[\s:|-]*$/.test(line)) continue; const cells = line.replace(/^\|/, "").replace(/\|\s*$/, "").split("|").map((c) => inline(c.trim())); table = table || []; table.push(table.length ? `<tr>${cells.map((c) => `<td>${c}</td>`).join("")}</tr>` : `<tr>${cells.map((c) => `<th>${c}</th>`).join("")}</tr>`); continue; }
    if (/^\s*[-*•] /.test(line)) { if (table || quote || (list && listTag !== "ul")) flush(); listTag = "ul"; list = list || []; list.push(`<li>${inline(line.replace(/^\s*[-*•] /, ""))}</li>`); continue; }
    if (/^\s*\d+[.)] /.test(line)) { if (table || quote || (list && listTag !== "ol")) flush(); listTag = "ol"; list = list || []; list.push(`<li>${inline(line.replace(/^\s*\d+[.)] /, ""))}</li>`); continue; }
    flush();
    if (/^# /.test(line)) out.push(`<h1>${inline(line.slice(2))}</h1>`);
    else if (/^## /.test(line)) out.push(`<h2>${inline(line.slice(3))}</h2>`);
    else if (/^### /.test(line)) out.push(`<h3>${inline(line.slice(4))}</h3>`);
    else if (/^---+$/.test(line)) out.push("<hr>");
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

/* ------------------------------------------------------- build / upload */

$("b-build").addEventListener("click", async () => {
  const fd = new FormData();
  fd.append("pack_id", $("b-id").value.trim()); fd.append("n", $("b-n").value); fd.append("keep", $("b-keep").value); fd.append("seed", $("b-seed").value);
  if ($("b-spec").files[0]) fd.append("spec", $("b-spec").files[0]);
  $("b-status").innerHTML = `<span class="spin"></span>generating…`; $("b-build").disabled = true;
  try {
    const r = await fetch("/api/packs/build", { method: "POST", body: fd }); const j = await r.json();
    if (!r.ok) throw new Error(j.detail || r.statusText);
    const t = setInterval(async () => {
      const job = await api(`/api/run/${j.job_id}`);
      if (job.status === "done") { clearInterval(t); $("b-status").innerHTML = `<span class="badge good">built</span> ${job.items} cases`; $("b-build").disabled = false; await loadPacks(); }
      if (job.status === "error") { clearInterval(t); $("b-status").innerHTML = `<span class="badge bad">failed</span> ${esc(job.error)}`; $("b-build").disabled = false; }
    }, 1500);
  } catch (e) { $("b-status").innerHTML = `<span class="badge bad">failed</span> ${esc(e.message)}`; $("b-build").disabled = false; }
});
$("u-upload").addEventListener("click", async () => {
  const f = $("u-zip").files[0]; if (!f) { $("u-status").textContent = "choose a zip first"; return; }
  const fd = new FormData(); fd.append("archive", f);
  $("u-status").innerHTML = `<span class="spin"></span>`;
  try {
    const r = await fetch("/api/packs/upload", { method: "POST", body: fd }); const j = await r.json();
    if (!r.ok) throw new Error(j.detail || r.statusText);
    $("u-status").innerHTML = `<span class="badge good">installed</span> ${esc(j.pack_id)} · ${j.items} cases`; await loadPacks();
  } catch (e) { $("u-status").innerHTML = `<span class="badge bad">rejected</span> ${esc(e.message)}`; }
});

/* ------------------------------------------------------------------ boot */

(async () => { await loadMeta(); await loadPacks(); await loadCorpora(); await loadRuns(); })();
