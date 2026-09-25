"use strict";
// Credit Evidence Engine — the business view: evaluations, review, feedback.
// The full console (packs, corpora, tamper demo) is at /advanced/.

const $view = document.getElementById("view");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (n, d) => (d ? Math.round((100 * n) / d) + "%" : "—");

async function api(path, opts) {
  const r = await fetch(path, opts && opts.body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(opts.body) } : opts);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch (e) { /* not json */ }
    throw new Error(msg);
  }
  return r.json();
}
const post = (path, body) => api(path, { body: body || {} });

function packName(pack) {
  const id = (pack && pack.pack_id) || "";
  if (id.endsWith("-de")) return "Personal loans, Germany (EUR)";
  if (id === "underwriter-sample") return "Personal loans, sample (GBP)";
  return id;
}
const verdictClass = (v) => ({ "GO": "go", "NO-GO": "no-go", "CONDITIONAL": "conditional", "INCONCLUSIVE": "muted" }[v] || "muted");
const verdictWords = (v) => ({
  "GO": "Ready to use under human review",
  "NO-GO": "Not ready: the assistant makes errors a reviewer would rely on",
  "CONDITIONAL": "Usable only with the conditions below",
  "INCONCLUSIVE": "Not enough evidence to decide",
}[v] || "Not decided");
const laneWords = { red: "Needs full review", amber: "Check the disputed points", green: "Looks clean" };

function setNav(name) {
  document.querySelectorAll("[data-nav]").forEach((a) => a.classList.toggle("on", a.dataset.nav === name));
}
function fail(e) { $view.innerHTML = `<div class="card bad">Something went wrong: ${esc(e.message)}</div>`; }

// ----------------------------------------------------------------- evaluations

async function viewRuns() {
  setNav("runs");
  const runs = await api("/api/runs");
  $view.innerHTML = `
    <h1>Evaluations</h1>
    <p class="sub">Each evaluation runs the credit-memo assistant on generated loan cases with known answers, marks every memo, and seals the evidence.</p>
    <div class="rows">${runs.map((r) => `
      <a class="card row" href="#/run/${encodeURIComponent(r.run_id)}">
        <span class="badge ${verdictClass(r.verdict)}">${esc(r.verdict || "—")}</span>
        <div class="grow"><div><b>${esc(packName(r.pack))}</b> · ${esc(r.sut && r.sut.model_id)}</div>
          <div class="meta">${r.memos_with_error} of ${r.memos} memos had an error${r.panel ? " · AI review done" : ""}${r.reviewed ? " · reviewed by people" : ""}</div>
          <div class="meta">${esc((r.finished_at || "").slice(0, 16).replace("T", " "))} · ${esc(r.run_id)}</div></div>
      </a>`).join("")}</div>`;
}

async function viewRun(id) {
  setNav("runs");
  const [d, runs] = await Promise.all([api(`/api/runs/${encodeURIComponent(id)}`), api("/api/runs")]);
  const h = runs.find((r) => r.run_id === id) || {};
  const dec = d.decision || {};
  const risks = (dec.risks || []).slice(0, 4);
  const recs = (d.recommendations || []).slice(0, 3);
  const checks = dec.checks || [];
  $view.innerHTML = `
    <p class="sub"><a href="#/">Evaluations</a> / ${esc(id)}</p>
    <div class="card verdict">
      <span class="badge ${verdictClass(dec.verdict)}">${esc(dec.verdict || "—")}</span>
      <div><h1>${esc(verdictWords(dec.verdict))}</h1>
        <div class="sub" style="margin:0">${esc(packName(d.manifest.pack))} · assistant ${esc(d.manifest.sut && d.manifest.sut.model_id)} · ${h.memos_with_error ?? "—"} of ${h.memos ?? "—"} memos had at least one error</div></div>
    </div>
    <div class="grid" style="margin-top:14px">
      <div class="card stat"><div class="n">${h.memos ?? "—"}</div><div class="l">memos written (${esc(d.manifest.pack.items)} cases × ${esc(d.manifest.repeats)} tries)</div></div>
      <div class="card stat"><div class="n">${pct(h.memos - h.memos_with_error, h.memos)}</div><div class="l">memos with no error found</div></div>
      <div class="card stat"><div class="n">${checks.filter((c) => c.status === "go").length} / ${checks.length}</div><div class="l">quality checks passed</div></div>
    </div>
    <h2>What went wrong</h2>
    ${risks.length ? `<div class="rows">${risks.map((r) => `<div class="card"><b>${esc(r.label)}</b> — in ${esc(r.briefings)} memos<div class="note">${esc(r.why)}</div></div>`).join("")}</div>` : `<p class="note">No recurring problem found.</p>`}
    <h2>What to change</h2>
    ${recs.length ? `<div class="rows">${recs.map((r) => `<div class="card"><b>${esc(r.title)}</b> <span class="badge muted">${esc(r.owner === "bank" ? "the bank" : r.owner)}</span><div class="note">${esc(r.action)}</div></div>`).join("")}</div>` : `<p class="note">Nothing to change.</p>`}
    <h2>Quality checks</h2>
    <div class="card"><table><tr><th>Check</th><th>What it catches</th><th>Passed</th><th></th></tr>
      ${checks.map((c) => `<tr><td>${esc(c.check.replace(/_/g, " "))}</td><td>${esc(c.meaning)}</td><td>${esc(c.passed)} of ${esc(c.passed + c.failed)}</td><td><span class="badge ${c.status === "go" ? "go" : c.status === "no_go" ? "no-go" : "conditional"}">${esc(c.status.replace("_", "-"))}</span></td></tr>`).join("")}
    </table>${(dec.conditions || []).length ? `<p class="note">Conditions: ${dec.conditions.map(esc).join(" ")}</p>` : ""}</div>
    <h2>Reports</h2>
    <div class="card"><div class="actions" style="margin:0">${(d.readers || []).filter((r) => r.available).map((r) => `<a class="btn" href="/api/runs/${encodeURIComponent(id)}/pdf/${encodeURIComponent(r.name)}">${esc(r.title || r.name)} (PDF)</a>`).join("")}</div>
      <p class="note">One report per reader: business, credit risk, compliance, operations, vendor and audit.</p></div>
    <h2>Evidence integrity</h2>
    <div class="card"><div id="vres" class="note">Every file in this evaluation is sealed. Checking rebuilds every result from the recorded memos.</div>
      <div class="actions"><button id="verify">Check the evidence</button></div></div>
    <div class="actions" style="margin-top:24px"><a class="btn primary" href="#/review/${encodeURIComponent(id)}">Review these memos</a>
      <a class="btn" href="#/feedback/${encodeURIComponent(id)}">Feedback</a></div>`;
  document.getElementById("verify").onclick = async (ev) => {
    ev.target.disabled = true;
    document.getElementById("vres").textContent = "Checking…";
    try {
      const v = await post(`/api/runs/${encodeURIComponent(id)}/verify`, { recompute: true });
      document.getElementById("vres").innerHTML = v.ok ? `<span class="ok">Intact.</span> ${esc(v.message)}` : `<span class="bad">Does not verify.</span> ${esc(v.message)}`;
    } catch (e) { document.getElementById("vres").innerHTML = `<span class="bad">${esc(e.message)}</span>`; }
    ev.target.disabled = false;
  };
}

// ----------------------------------------------------------------- choosing a run

async function viewPick(target) {
  setNav(target);
  const runs = await api("/api/runs");
  const label = target === "review" ? "Choose an evaluation to review" : "Choose an evaluation";
  $view.innerHTML = `<h1>${label}</h1><p class="sub">${target === "review"
    ? "Reviewers test the evidence memo by memo. Their verdicts become data that improves the assistant."
    : "Review results, rulings on disputed verdicts, and the feedback pack for improving the model."}</p>
    <div class="rows">${runs.map((r) => `<a class="card row" href="#/${target}/${encodeURIComponent(r.run_id)}">
      <span class="badge ${verdictClass(r.verdict)}">${esc(r.verdict || "—")}</span>
      <div class="grow"><b>${esc(packName(r.pack))}</b><div class="meta">${esc(r.run_id)} · ${r.memos} memos${r.reviewed ? " · reviewing started" : ""}</div></div></a>`).join("")}</div>`;
}

// ----------------------------------------------------------------- review queue

async function viewQueue(id, lane) {
  setNav("review");
  const q = await api(`/api/review/${encodeURIComponent(id)}`);
  const s = q.summary;
  const memos = q.memos.filter((m) => !lane || m.lane === lane);
  $view.innerHTML = `
    <p class="sub"><a href="#/review">Review</a> / ${esc(id)}</p>
    <h1>Review queue</h1>
    <p class="sub">Memos are sorted by what the evidence found. Red needs a full review, amber has points where the automatic checks and the AI review disagree, green looks clean and needs a sign-off.</p>
    <div class="lanes">
      <a class="badge ${!lane ? "sel muted" : "muted"}" href="#/review/${encodeURIComponent(id)}">All ${s.memos}</a>
      ${["red", "amber", "green"].map((l) => `<a class="badge ${l}" href="#/review/${encodeURIComponent(id)}/lane/${l}">${laneWords[l]}: ${s.lanes[l]}</a>`).join("")}
      <span class="badge muted">Reviewed: ${s.reviewed} of ${s.memos}</span>
    </div>
    <div class="rows">${memos.map((m) => `
      <a class="card row" href="#/review/${encodeURIComponent(id)}/memo/${encodeURIComponent(m.memo)}">
        <span class="badge ${m.lane}">${m.lane}</span>
        <div class="grow"><b>Case ${esc(m.case)}</b> · memo ${m.repeat + 1}<div class="meta">${m.findings} finding${m.findings === 1 ? "" : "s"} to check</div></div>
        <span class="meta">${m.reviewed ? "✓ reviewed" : ""}</span></a>`).join("")}</div>`;
}

// ----------------------------------------------------------------- one memo

function highlight(text, cards) {
  let html = esc(text);
  cards.forEach((c) => {
    const s = c.sentence && esc(c.sentence);
    if (s && html.includes(s)) html = html.replace(s, `<mark id="m-${c.card_id}">${s}</mark>`);
  });
  // light markdown for reading: bold, bullets and headings, after the highlights are placed
  return html
    .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
    .replace(/^\s*[*-]\s{1,4}/gm, "• ")
    .replace(/^#{1,4}\s*(.+)$/gm, "<b>$1</b>");
}

async function viewMemo(id, memo) {
  setNav("review");
  const [m, q] = await Promise.all([
    api(`/api/review/${encodeURIComponent(id)}/memo?memo=${encodeURIComponent(memo)}`),
    api(`/api/review/${encodeURIComponent(id)}`),
  ]);
  const started = Date.now();
  const prior = {};
  ((m.review && m.review.verdicts) || []).forEach((v) => (prior[v.card_id] = v));
  const state = {};
  m.cards.forEach((c) => (state[c.card_id] = prior[c.card_id] ? { ...prior[c.card_id] } : { action: null }));
  const raised = [];
  const reasons = { wrong_figure: "The figure is actually right", wrong_policy_reading: "The policy was read correctly", not_material: "True, but it does not matter", finding_wrong: "The finding is simply wrong" };
  const reviewer = localStorage.getItem("reviewer") || "";

  $view.innerHTML = `
    <p class="sub"><a href="#/review/${encodeURIComponent(id)}">Review queue</a> / Case ${esc(m.case)}, memo ${m.repeat + 1}</p>
    <h1>Case ${esc(m.case)} <span class="badge ${m.lane}">${esc(laneWords[m.lane])}</span></h1>
    <p class="sub">Check each finding against the memo and the case file. Confirm real errors and correct the wording; mark findings that are not errors, with a reason.</p>
    <div class="split">
      <div class="card"><h2 style="margin-top:0">The assistant's memo</h2>
        <div class="memo">${highlight(m.text, m.cards)}</div>
        ${m.case_file.length ? `<details><summary>Show the case file</summary>${m.case_file.map((d) => `<h2>${esc(d.title)}</h2><div class="casefile">${esc(d.content)}</div>`).join("")}</details>` : ""}
      </div>
      <div>
        <h2 style="margin-top:0">${m.cards.length ? `Findings to check (${m.cards.length})` : "No findings: sign off if the memo is right"}</h2>
        <div id="cards"></div>
        <div class="finding"><b>Something the checks missed?</b>
          <input type="text" id="r-problem" placeholder="What is wrong" />
          <input type="text" id="r-sentence" placeholder="The sentence in the memo (optional)" />
          <input type="text" id="r-fix" placeholder="How it should read (optional)" />
          <div class="actions"><button id="r-add">Add</button><span id="r-list" class="note"></span></div></div>
        <div class="card"><label class="note">Your name or reviewer id</label><input type="text" id="who" value="${esc(reviewer)}" />
          <div class="actions"><button class="primary" id="submit">Submit review</button><span id="msg" class="note"></span></div></div>
      </div>
    </div>`;

  const renderCards = () => {
    document.getElementById("cards").innerHTML = m.cards.map((c) => {
      const st = state[c.card_id];
      return `<div class="finding ${st.action ? "done" : ""}" data-card="${c.card_id}">
        <div class="kind">${esc(c.kind)} · ${c.known_answer ? "automatic check, known answer" : "AI review panel"}</div>
        <div class="problem">${esc(c.problem)}</div>
        ${c.sentence ? `<div class="quote">${esc(c.sentence)}</div>` : ""}
        ${c.evidence ? `<div class="proof"><span class="note">Evidence:</span> ${esc(c.evidence)}</div>` : ""}
        <div class="choice">
          <button data-a="confirm" class="${st.action === "confirm" ? "sel" : ""}">Confirm the error</button>
          <button data-a="dispute" class="${st.action === "dispute" ? "sel" : ""}">Not an error</button>
          <button data-a="needs_more" class="${st.action === "needs_more" ? "sel" : ""}">Unsure</button>
        </div>
        ${st.action === "confirm" ? `<textarea rows="3" data-fix placeholder="${c.sentence ? "How the sentence should read" : "The fact the memo should state"}">${esc(st.correction ?? c.sentence ?? "")}</textarea>` : ""}
        ${st.action === "dispute" ? `<select data-reason><option value="">Why is it not an error?</option>${Object.entries(reasons).map(([k, v]) => `<option value="${k}" ${st.reason === k ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>` : ""}
      </div>`;
    }).join("");
    document.querySelectorAll("[data-card]").forEach((el) => {
      const cid = el.dataset.card;
      el.querySelectorAll("[data-a]").forEach((b) => (b.onclick = () => { state[cid] = { action: b.dataset.a, correction: state[cid].correction, reason: state[cid].reason }; renderCards(); }));
      const fix = el.querySelector("[data-fix]");
      if (fix) fix.oninput = () => (state[cid].correction = fix.value);
      const rs = el.querySelector("[data-reason]");
      if (rs) rs.onchange = () => (state[cid].reason = rs.value);
      el.onmouseenter = () => { const mk = document.getElementById("m-" + cid); if (mk) mk.classList.add("on"); };
      el.onmouseleave = () => { const mk = document.getElementById("m-" + cid); if (mk) mk.classList.remove("on"); };
    });
  };
  renderCards();

  document.getElementById("r-add").onclick = () => {
    const problem = document.getElementById("r-problem").value.trim();
    if (!problem) return;
    raised.push({ problem, sentence: document.getElementById("r-sentence").value.trim(), correction: document.getElementById("r-fix").value.trim() });
    ["r-problem", "r-sentence", "r-fix"].forEach((i) => (document.getElementById(i).value = ""));
    document.getElementById("r-list").textContent = `${raised.length} added`;
  };

  document.getElementById("submit").onclick = async () => {
    const msg = document.getElementById("msg");
    const who = document.getElementById("who").value.trim();
    const open = m.cards.filter((c) => !state[c.card_id].action);
    const noReason = m.cards.filter((c) => state[c.card_id].action === "dispute" && !state[c.card_id].reason);
    if (!who) { msg.innerHTML = `<span class="bad">Enter your name or reviewer id.</span>`; return; }
    if (open.length) { msg.innerHTML = `<span class="bad">${open.length} finding${open.length === 1 ? "" : "s"} still to check.</span>`; return; }
    if (noReason.length) { msg.innerHTML = `<span class="bad">Say why each disputed finding is not an error.</span>`; return; }
    localStorage.setItem("reviewer", who);
    try {
      await post(`/api/review/${encodeURIComponent(id)}/submit`, {
        memo, reviewer: who, seconds: (Date.now() - started) / 1000, raised,
        verdicts: m.cards.map((c) => ({ card_id: c.card_id, ...state[c.card_id] })),
      });
      const next = q.memos.find((x) => !x.reviewed && x.memo !== memo);
      location.hash = next ? `#/review/${encodeURIComponent(id)}/memo/${encodeURIComponent(next.memo)}` : `#/review/${encodeURIComponent(id)}`;
    } catch (e) { msg.innerHTML = `<span class="bad">${esc(e.message)}</span>`; }
  };
}

// ----------------------------------------------------------------- feedback

async function viewFeedback(id) {
  setNav("feedback");
  const [q, adj] = await Promise.all([api(`/api/review/${encodeURIComponent(id)}`), api(`/api/review/${encodeURIComponent(id)}/adjudication`)]);
  const s = q.summary;
  const sec = s.seconds_per_memo_by_lane;
  const secs = (v) => (v == null ? "—" : `${Math.round(v)} s`);
  $view.innerHTML = `
    <p class="sub"><a href="#/feedback">Feedback</a> / ${esc(id)}</p>
    <h1>Feedback</h1>
    <p class="sub">What the reviewers found, the verdicts that need a ruling, and the feedback pack that improves the assistant. Only verdicts whose truth is settled go into the pack.</p>
    <div class="grid">
      <div class="card stat"><div class="n">${s.reviewed} / ${s.memos}</div><div class="l">memos reviewed</div></div>
      <div class="card stat"><div class="n">${pct(s.agree_with_known_answer, s.known_answer_verdicts)}</div><div class="l">verdicts that agree with the known answer (${s.agree_with_known_answer} of ${s.known_answer_verdicts})</div></div>
      <div class="card stat"><div class="n">${s.automation_bias_memos}</div><div class="l">memos signed off although they had a known error</div></div>
      <div class="card stat"><div class="n">${secs(sec.red)} · ${secs(sec.amber)} · ${secs(sec.green)}</div><div class="l">review time per memo: red · amber · green</div></div>
    </div>
    <h2>Needs a ruling (${adj.length})</h2>
    <p class="note">For model risk: disputes of findings, findings reviewers raised, and verdicts that disagree with the known answer.</p>
    ${adj.length ? `<div class="card"><table><tr><th>Case</th><th>Finding</th><th>Reviewer said</th><th>Ruling</th></tr>${adj.map((x) => `
      <tr data-v="${esc(x.verdict_id)}"><td>${esc(x.memo.split(":")[2] || x.memo)}</td>
        <td><b>${esc(x.card.problem)}</b>${x.card.sentence ? `<div class="note">${esc(x.card.sentence)}</div>` : ""}<div class="note">${esc(x.card.kind)}</div></td>
        <td>${esc({ dispute: "Not an error", needs_more: "Unsure", raise: "Raised a new finding", confirm: "Confirmed" }[x.verdict.action] || x.verdict.action)}${x.verdict.reason ? `<div class="note">${esc(x.verdict.reason.replace(/_/g, " "))}</div>` : ""}</td>
        <td><div class="choice" style="margin:0"><button data-d="uphold">Reviewer is right</button><button data-d="reject">Reviewer is wrong</button></div></td></tr>`).join("")}</table></div>` : `<p class="note">Nothing waiting.</p>`}
    <h2>Feedback pack</h2>
    <div class="card"><div id="fb" class="note">Corrected memos for fine-tuning, before-and-after pairs, checked labels for the AI reviewer, fixes to the automatic checks, and a summary of failures for whoever owns the assistant. No customer data: every case is generated.</div>
      <div class="actions"><button class="primary" id="build">Build the feedback pack</button></div></div>`;

  document.querySelectorAll("[data-v]").forEach((tr) => tr.querySelectorAll("[data-d]").forEach((b) => (b.onclick = async () => {
    const by = localStorage.getItem("reviewer") || "model-risk";
    await post(`/api/review/${encodeURIComponent(id)}/adjudicate`, { verdict_id: tr.dataset.v, decision: b.dataset.d, by });
    viewFeedback(id);
  })));
  document.getElementById("build").onclick = async (ev) => {
    ev.target.disabled = true;
    try {
      const m = await post(`/api/review/${encodeURIComponent(id)}/feedback`);
      const c = m.counts;
      const link = (f, label) => `<a class="btn" href="/api/review/${encodeURIComponent(id)}/feedback/${f}">${label}</a>`;
      const waiting = (m.memos_awaiting_correction || []).length;
      document.getElementById("fb").innerHTML = `<p><b>Built.</b> ${c["sft.jsonl"]} corrected memos, ${c["preferences.jsonl"]} before-and-after pairs, ${c["judge_labels.jsonl"]} checked labels, ${c["check_fixes.jsonl"]} check fixes.</p>
        ${waiting ? `<p class="note">${waiting} memo${waiting === 1 ? " has" : "s have"} a confirmed error without a correction, so ${waiting === 1 ? "it is" : "they are"} not yet training examples. Open ${waiting === 1 ? "it" : "them"} in Review and correct the wording.</p>` : ""}
        ${Object.keys(m.failure_summary).length ? `<p>Most frequent confirmed errors: ${Object.entries(m.failure_summary).slice(0, 4).map(([k, v]) => `${esc(k)} (${v})`).join("; ")}.</p>` : ""}
        <div class="actions">${link("sft.jsonl", "Corrected memos")}${link("preferences.jsonl", "Before-and-after pairs")}${link("judge_labels.jsonl", "Checked labels")}${link("check_fixes.jsonl", "Check fixes")}${link("manifest.json", "Manifest")}</div>`;
    } catch (e) { document.getElementById("fb").innerHTML = `<span class="bad">${esc(e.message)}</span>`; }
    ev.target.disabled = false;
  };
}

// ----------------------------------------------------------------- routing

async function route() {
  const parts = location.hash.replace(/^#\/?/, "").split("/").map(decodeURIComponent);
  try {
    if (!parts[0]) return await viewRuns();
    if (parts[0] === "run" && parts[1]) return await viewRun(parts[1]);
    if (parts[0] === "review" && !parts[1]) return await viewPick("review");
    if (parts[0] === "review" && parts[2] === "memo") return await viewMemo(parts[1], parts.slice(3).join("/"));
    if (parts[0] === "review" && parts[2] === "lane") return await viewQueue(parts[1], parts[3]);
    if (parts[0] === "review") return await viewQueue(parts[1]);
    if (parts[0] === "feedback" && !parts[1]) return await viewPick("feedback");
    if (parts[0] === "feedback") return await viewFeedback(parts[1]);
    return await viewRuns();
  } catch (e) { fail(e); }
}
window.addEventListener("hashchange", () => { window.scrollTo(0, 0); route(); });
route();
