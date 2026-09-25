"use strict";
// Credit Evidence — the business view, in three steps: Test, Review, Improve.
// The full engine console (packs, corpora, tamper demo) is at /advanced/.

const $view = document.getElementById("view");
const $steps = document.getElementById("steps");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const enc = encodeURIComponent;
const pct = (n, d) => (d ? Math.round((100 * n) / d) : 0);

async function api(path, body) {
  const opts = body === undefined ? undefined
    : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const r = await fetch(path, opts);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch (e) { /* not json */ }
    const err = new Error(msg);
    err.status = r.status;
    throw err;
  }
  return r.json();
}

// ----------------------------------------------------------------- words

const ICON = {
  check: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12l5 5L20 7"/></svg>',
  arrow: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>',
  back: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M19 12H5M11 18l-6-6 6-6"/></svg>',
  lock: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>',
  plus: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>',
  down: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 4v11M7 10l5 5 5-5M5 20h14"/></svg>',
};
const VERDICT = {
  "NO-GO": ["Not ready for use", "b-red"],
  "CONDITIONAL": ["Ready with conditions", "b-amber"],
  "GO": ["Ready for use", "b-green"],
  "INCONCLUSIVE": ["Not enough evidence yet", "b-grey"],
};
const verdictBadge = (v, big) => {
  const [w, c] = VERDICT[v] || ["Not decided", "b-grey"];
  return `<span class="badge ${c}${big ? " big" : ""}">${esc(w)}</span>`;
};
const CHECK = {
  numeric_fidelity: "Figures match the case file",
  decoy_citation: "No irrelevant reasons",
  comparison_fidelity: "Limits compared the right way round",
  claim_consistency: "Claims agree with its own figures",
  flip_accuracy: "Says what would change the outcome",
  material_omission: "Nothing important left out",
};
const CHECK_STATUS = { go: ["Ready", "ok"], conditional: ["With conditions", "amber"], no_go: ["Not ready", "red"] };
const RULES = {
  DE: ["Germany", "German rules", "EU AI Act; Civil Code §§ 505a–505d (creditworthiness checks); Banking Act § 18a; Data Protection Act § 31 (credit scoring); the new consumer credit law (BGBl. 2026 I Nr. 139)"],
  IT: ["Italy", "Italian rules", "EU AI Act; EU Consumer Credit Directive; Italian Banking Act (TUB)"],
  US: ["United States", "US rules", "Federal Reserve guidance SR 26-2 on model risk"],
};
const PACK_JURISDICTION = { "underwriter-de": "DE", "underwriter-sample": "IT" };
function packName(pack) {
  const id = (pack && pack.pack_id) || pack || "";
  if (id === "underwriter-de") return "Personal loans, Germany (in euros)";
  if (id === "underwriter-sample") return "Personal loans, sample (in pounds)";
  return id;
}
const rulesName = (pack) => (RULES[PACK_JURISDICTION[(pack && pack.pack_id) || pack]] || [])[1] || "";
const LANE = {
  red: ["Check first", "The rule checks and the AI reviewers both found a problem."],
  amber: ["Worth a look", "Only one of the two found a problem."],
  green: ["Probably fine", "Nothing was found. Check two or three, to make sure the machine is not missing things."],
};
const REASON = {
  wrong_figure: "The figure is correct",
  wrong_policy_reading: "The policy was read correctly",
  not_material: "It doesn’t change the decision",
  finding_wrong: "The finding itself is mistaken",
};
const ACTION_WORDS = { dispute: "The memo is right", needs_more: "Not sure", raise: "Found another problem", confirm: "The memo is wrong" };
const date = (iso) => (iso ? new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" }) : "");
const shortDate = (iso) => (iso ? new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : "");
const plural = (n, one, many) => `${n} ${n === 1 ? one : many || one + "s"}`;
const memoId = (itemId, repeat) => `${itemId}#r${repeat}`;
const caseOf = (memo) => (memo.split(":")[2] || memo).split("#")[0];
const reviewer = {
  get: () => { try { return localStorage.getItem("reviewer") || ""; } catch (e) { return ""; } },
  set: (v) => { try { localStorage.setItem("reviewer", v); } catch (e) { /* private window */ } },
};

// ----------------------------------------------------------------- header steps

function renderSteps(ov, active, testState) {
  const run = ov && ov.run;
  const st = (ov && ov.stages) || null;
  const rid = run ? enc(run.run_id) : "";
  const dot = (state, n, isActive) => {
    if (state === "done") return `<span class="dot done">${ICON.check}</span>`;
    if (isActive) return `<span class="dot fill">${n}</span>`;
    if (state === "next") return `<span class="dot now">${n}</span>`;
    return `<span class="dot todo">${n}</span>`;
  };
  const test = testState ? ["now", testState] : run ? ["done", "Done"] : ["next", "Not started"];
  const reviewWords = !st ? "" : st.review === "done" ? "Done" : st.review === "in_progress" ? `${st.flagged_checked} of ${st.flagged}` : "Not started";
  const improveWords = !st ? "" : st.improve === "done" ? "Done" : st.improve === "in_progress" ? "In progress" : "Not started";
  const reviewState = st ? (st.review === "done" ? "done" : st.next === "review" ? "next" : "todo") : "todo";
  const improveState = st ? (st.improve === "done" ? "done" : st.next === "improve" ? "next" : "todo") : "todo";
  const step = (key, n, href, state, words, name) => {
    const on = active === key;
    const cls = `step${on ? " on" : ""}${state === "todo" && !on ? " off" : ""}`;
    return `<a class="${cls}" href="${href}"${on ? ' aria-current="step"' : ""}>${dot(state, n, on)}<span class="name">${name}</span>${words ? `<span class="state">${esc(words)}</span>` : ""}</a>`;
  };
  $steps.innerHTML = [
    step("test", 1, testState ? "#/new" : run ? `#/result/${rid}` : "#/new", test[0], test[1], "Test"),
    '<span class="sep" aria-hidden="true"></span>',
    step("review", 2, run ? `#/review/${rid}` : "#/", reviewState, reviewWords, "Review"),
    '<span class="sep" aria-hidden="true"></span>',
    step("improve", 3, run ? `#/improve/${rid}` : "#/", improveState, improveWords, "Improve"),
  ].join("");
  document.querySelector(".history").classList.toggle("on", active === "history");
}

const overview = (run) => api(`/api/overview${run ? `?run=${enc(run)}` : ""}`);
function page(cls) { $view.className = cls || ""; }

// ----------------------------------------------------------------- home

async function viewHome() {
  const ov = await overview();
  renderSteps(ov, null);
  page("");
  const job = (ov.jobs || [])[0];
  const banner = job ? `<a class="note-box blue link" href="#/running/${enc(job.job_id)}" style="text-decoration:none">
      <span class="spinner" style="width:22px;height:22px" aria-hidden="true"></span>
      <span class="grow">A test is running: ${job.phase === "panel" ? "second opinion" : "memos"} ${job.done} of ${job.total}.</span>${ICON.arrow}</a>` : "";
  if (!ov.run) {
    $view.innerHTML = `<div class="stack">${banner}
      <div class="stack tight"><p class="muted small">You are testing</p><h1>Credit memo assistant</h1>
        <p class="muted">The AI that writes a summary for the underwriter when a loan application is referred.</p></div>
      <div class="card stack mid"><h2>No tests yet</h2><p class="muted">Start with a test: the assistant writes memos for made-up loan cases, and each memo is checked against the rules.</p>
        <a class="btn primary large" href="#/new" style="align-self:flex-start">Start a test</a></div></div>`;
    return;
  }
  const r = ov.run, s = ov.stages, rid = enc(r.run_id);
  const flagged = s.flagged;
  const reviewText = s.review === "done" ? `All ${flagged} flagged memos checked.`
    : s.review === "in_progress" ? `A person confirms the mistakes the machine found. ${s.flagged_checked} of ${flagged} flagged memos checked.`
    : `A person confirms the mistakes the machine found. ${plural(flagged, "memo is", "memos are")} flagged.`;
  const improveText = s.improve === "done" ? "Feedback pack built. Test again on new cases to prove the fix worked."
    : s.improve === "in_progress" ? (s.needs_adjudication ? `${plural(s.needs_adjudication, "disagreement")} to settle, then build the feedback pack.` : "Build the feedback pack for the model team.")
    : "Your review answers become a feedback pack for the model team. Then you test again on new cases.";
  const card = (key, n, title, state, text, action) => {
    const next = s.next === key;
    const d = state === "done" ? `<span class="dot big done">${ICON.check}</span>` : next ? `<span class="dot big fill">${n}</span>` : `<span class="dot big todo">${n}</span>`;
    const tag = next ? '<span class="badge b-blue" style="margin-left:auto">Next step</span>'
      : `<span class="small muted" style="margin-left:auto">${state === "done" ? "Done" : state === "in_progress" ? "In progress" : "Not started"}</span>`;
    return `<section class="card stack mid${next ? " strong" : ""}"><div class="row" style="gap:10px">${d}<h3 style="font-size:19px">${title}</h3>${tag}</div>
      <p class="muted grow">${text}</p>${action}</section>`;
  };
  const cta = (key, href, words) => s.next === key
    ? `<a class="btn primary" href="${href}">${words}${ICON.arrow}</a>` : `<a class="link" href="${href}">${words}</a>`;
  $view.innerHTML = `<div class="stack" style="gap:32px">${banner}
    <div class="stack tight"><p class="muted small">You are testing</p><h1 style="font-size:40px">Credit memo assistant</h1>
      <p class="muted" style="font-size:17px">The AI that writes a summary for the underwriter when a loan application is referred.</p></div>
    <section class="card row wrap" aria-label="Current status" style="gap:32px">
      <div class="stack tight grow">${verdictBadge(r.verdict)}
        <p style="font-size:22px;font-weight:600;line-height:1.35">${r.memos_with_error
          ? `${r.memos_with_error} of ${r.memos} test memos had a mistake an underwriter could act on.`
          : `No mistakes found in ${r.memos} test memos.`}</p>
        <p class="muted small">Last test: ${esc(date(r.finished_at))}${rulesName(r.pack) ? " · " + esc(rulesName(r.pack)) : ""}</p></div>
      <a class="btn" href="#/result/${rid}">See the result</a></section>
    <h2 style="margin-bottom:-12px">What to do next</h2>
    <div class="grid3">
      ${card("test", 1, "Test", "done", `The assistant wrote ${r.memos} memos for made-up loan cases. Each memo was checked against the rules.`, `<a class="link" href="#/result/${rid}">See the result</a>`)}
      ${card("review", 2, "Review", s.review, reviewText + (s.review === "in_progress" ? `<span class="bar" style="margin-top:12px;display:block" aria-hidden="true"><span style="width:${pct(s.flagged_checked, flagged)}%"></span></span>` : ""),
        cta("review", `#/review/${rid}`, s.review === "not_started" ? "Start review" : s.review === "done" ? "Open review" : "Continue review"))}
      ${card("improve", 3, "Improve", s.improve, improveText, cta("improve", `#/improve/${rid}`, s.improve === "not_started" ? "How this works" : s.improve === "done" ? "Open feedback pack" : "Continue"))}
    </div>
    <div class="row wrap"><span style="color:var(--green);display:flex">${ICON.lock}</span>
      <p class="muted small grow">Test cases are generated from your credit policy. No customer data is used.</p>
      <a class="btn${s.next === "test" ? " primary" : ""}" href="#/new">${ICON.plus}Start a new test</a></div>
  </div>`;
}

// ----------------------------------------------------------------- new test

async function viewNew() {
  const [ov, meta, packs] = await Promise.all([overview(), api("/api/meta"), api("/api/packs")]);
  renderSteps(ov, "test", "New");
  page("narrow");
  const usable = packs.filter((p) => !p.error && p.items);
  const byJ = {};
  usable.forEach((p) => { const j = p.jurisdiction || PACK_JURISDICTION[p.pack_id] || "other"; (byJ[j] = byJ[j] || []).push(p); });
  const js = Object.keys(byJ).sort((a, b) => (a === "DE" ? -1 : b === "DE" ? 1 : a.localeCompare(b)));
  let chosenJ = js[0];
  const a = meta.roles.assistant;
  $view.innerHTML = `<div class="stack" style="gap:28px">
    <a class="link back" href="#/">${ICON.back}Home</a>
    <div class="stack tight" style="margin-top:-12px"><h1>Start a new test</h1>
      <p class="muted" style="font-size:17px">Answer three questions. The test then runs by itself; it usually finishes within an hour.</p></div>
    <fieldset><legend>1. Which assistant are you testing?</legend>
      <label for="assistant" class="small muted">Assistant</label>
      <select id="assistant"><option>Credit memo assistant (${esc(a.model)})</option></select>
      <p class="tiny muted">${a.where === "on-prem" ? "Runs on your own servers." : "Runs on NVIDIA's cloud."}</p></fieldset>
    <fieldset><legend>2. Which rules must its memos follow?</legend><div class="stack tight" id="rules"></div></fieldset>
    <fieldset><legend>3. Which test cases?</legend><div class="stack tight" id="cases"></div>
      <p class="small muted">Each case is given to the assistant three times, to check it answers the same way each time.</p></fieldset>
    <label class="choice-card"><input type="checkbox" id="panel" checked>
      <span class="stack tight"><span class="t">Also get a second opinion from three AI reviewers</span>
      <span class="small muted">One reads each memo, one challenges it against the case file, one decides. It replaces the single AI judge. Adds time, and helps sort what a person should check first.</span></span></label>
    <div class="note-box"><span style="color:var(--green);display:flex">${ICON.lock}</span>
      <p class="small"><strong>No customer data.</strong> The cases are generated from your credit policy. Nothing from your loan book is used or seen.</p></div>
    <div class="row"><button class="btn primary large" id="start">Start test</button><a class="btn large" href="#/">Cancel</a><span id="msg" class="error"></span></div>
  </div>`;
  const drawRules = () => {
    document.getElementById("rules").innerHTML = js.map((j) => {
      const [name, , text] = RULES[j] || [j, j, ""];
      return `<label class="choice-card"><input type="radio" name="rules" value="${esc(j)}" ${j === chosenJ ? "checked" : ""}>
        <span class="stack tight"><span class="t">${esc(name)}</span><span class="small muted">${esc(text)}</span></span></label>`;
    }).join("");
    document.querySelectorAll("input[name=rules]").forEach((el) => (el.onchange = () => { chosenJ = el.value; drawCases(); }));
  };
  const drawCases = () => {
    const list = byJ[chosenJ] || [];
    document.getElementById("cases").innerHTML = list.map((p, i) => `<label class="choice-card">
      <input type="radio" name="cases" value="${esc(p.pack_id)}" ${i === 0 ? "checked" : ""}>
      <span class="stack tight"><span class="t">${esc(packName(p))}</span><span class="small muted">${p.items} cases, each with a known right answer · ${p.items * 3} memos</span></span></label>`).join("");
  };
  drawRules();
  drawCases();
  document.getElementById("start").onclick = async (ev) => {
    const pack = (document.querySelector("input[name=cases]:checked") || {}).value;
    if (!pack) return;
    ev.target.disabled = true;
    try {
      const j = await api("/api/run", { pack, repeats: 3, judge: true, panel: document.getElementById("panel").checked });
      location.hash = `#/running/${enc(j.job_id)}`;
    } catch (e) {
      document.getElementById("msg").textContent = e.message;
      ev.target.disabled = false;
    }
  };
}

// ----------------------------------------------------------------- running

let pollTimer = null;
async function viewRunning(jobId) {
  const ov = await overview();
  renderSteps(ov, "test", "Running");
  page("narrow");
  const draw = (job) => {
    const memosDone = job.phase !== "memos";
    const panelDone = job.phase === "done";
    const line = (state, title, detail, progress) => `<li class="row" style="align-items:flex-start;padding:18px 0;border-bottom:1px solid var(--line-2)">
      ${state === "done" ? `<span class="dot big done">${ICON.check}</span>` : state === "now" ? '<span class="spinner" aria-hidden="true"></span>' : state === "skip" ? '<span class="dot big todo">–</span>' : '<span class="dot big todo"></span>'}
      <span class="stack tight grow"><span style="font-size:17px;font-weight:600${state === "todo" || state === "skip" ? ";color:var(--ink-2)" : ""}">${title}</span>
      ${progress != null ? `<span class="bar"><span style="width:${progress}%"></span></span>` : ""}
      ${detail ? `<span class="small muted">${detail}</span>` : ""}</span></li>`;
    const items = [
      line("done", "Test cases prepared", "Made-up loan cases, each with a known right answer"),
      line(memosDone ? "done" : "now", "The assistant writes its memos, and each is checked against the rules",
        memosDone ? "All memos written and checked" : `${job.done} of ${job.total} memos`, memosDone ? null : pct(job.done, job.total)),
    ];
    if (job.panel) {
      const st = job.phase === "panel" ? "now" : panelDone ? (job.panel_error ? "skip" : "done") : "todo";
      items.push(line(st, "Second opinion from three AI reviewers",
        job.panel_error ? "Could not run this time. The result stands without it." : job.phase === "panel" ? `${job.done} of ${job.total} memos` : "One reads the memo, one challenges it against the case file, one decides",
        job.phase === "panel" ? pct(job.done, job.total) : null));
    }
    items.push(line(job.status === "done" ? "done" : "todo", "Sealing the result", "Every file is fingerprinted, so anyone can check later that nothing was changed"));
    let foot = `<p class="muted">You can close this page. The result will be waiting on the home page.</p>
      ${job.phase === "memos" ? '<button class="btn" id="stop" style="align-self:flex-start">Stop the test</button>' : ""}`;
    if (job.status === "done") foot = `<a class="btn primary large" href="#/result/${enc(job.run_id)}" style="align-self:flex-start">See the result${ICON.arrow}</a>`;
    if (job.status === "cancelled") foot = `<p>The test was stopped. ${job.transcripts ? `The ${job.transcripts} memos written so far are kept.` : ""}</p>${job.transcripts ? `<a class="btn" href="#/result/${enc(job.run_id)}" style="align-self:flex-start">See what was done</a>` : ""}`;
    if (job.status === "error") foot = `<p class="error">The test stopped with an error: ${esc(job.error)}</p><a class="btn" href="#/new" style="align-self:flex-start">Try again</a>`;
    $view.innerHTML = `<div class="stack" style="gap:28px">
      <div class="stack tight"><h1>${job.status === "done" ? "The test is finished" : "Testing the credit memo assistant"}</h1>
        <p class="muted" style="font-size:17px">Started at ${esc((job.started || "").slice(11, 13))}:${esc((job.started || "").slice(13, 15))} UTC</p></div>
      <ol class="card" style="list-style:none;padding:8px 28px;margin:0">${items.join("")}</ol>${foot}</div>`;
    const stop = document.getElementById("stop");
    if (stop) stop.onclick = async () => { stop.disabled = true; await api(`/api/run/${enc(jobId)}/cancel`, {}); };
  };
  const tick = async () => {
    if (!location.hash.startsWith("#/running/")) return;
    let job;
    try { job = await api(`/api/run/${enc(jobId)}`); } catch (e) {
      $view.innerHTML = `<div class="card stack mid"><h2>This test is no longer tracked</h2><p class="muted">The server was restarted. Finished tests are listed under Earlier tests.</p><a class="btn" href="#/history" style="align-self:flex-start">Earlier tests</a></div>`;
      return;
    }
    draw(job);
    if (job.status === "running") pollTimer = setTimeout(tick, 2000);
    else if (job.status === "done") setTimeout(() => { if (location.hash === `#/running/${jobId}`) location.hash = `#/result/${enc(job.run_id)}`; }, 1500);
  };
  tick();
}

// ----------------------------------------------------------------- result

async function viewResult(id) {
  const [d, ov] = await Promise.all([api(`/api/runs/${enc(id)}`), overview(id)]);
  renderSteps(ov, "test");
  page("");
  const h = d.headline, dec = d.decision || {}, p = d.panel;
  const flagged = ov.stages ? ov.stages.flagged : 0;
  const risks = (dec.risks || []).slice(0, 4);
  const recs = (d.recommendations || []).slice(0, 3);
  const example = recs.find((r) => r.example) || null;
  const lead = h.memos_with_error
    ? `In ${h.memos_with_error} of ${h.memos} memos, the assistant made a mistake an underwriter could act on.`
    : `The assistant made no mistakes the checks could find in ${h.memos} memos.`;
  const caught = p && p.with_failing_checks ? `caught ${p.with_failing_checks.flagged} of the ${p.with_failing_checks.briefings} memos with a mistake` : "";
  const why = "This is why a person should check the flagged memos before anyone relies on them.";
  const support = !caught || p.judge_mean_value == null
    ? `Each memo was checked against rules with a known right answer. ${why}`
    : p.lone_judge === "reader"
      ? `Reading each memo on its own, as a lone AI judge would, the first of our three AI reviewers gave them ${Math.round(100 * p.judge_mean_value)}% on average. Once the second checked them against the case file, the panel ${caught}. ${why}`
      : `A single AI reviewer gave these memos ${Math.round(100 * p.judge_mean_value)}% on average. Our panel of three AI reviewers ${caught}. ${why}`;
  const reports = (d.readers || []).filter((r) => r.available && r.name !== "business");
  $view.innerHTML = `<div class="stack" style="gap:28px">
    <div class="row wrap"><a class="link" href="#/">${ICON.back}Home</a>
      <span class="muted small">Test result · ${esc(date(d.manifest.finished_at))}${rulesName(d.manifest.pack) ? " · " + esc(rulesName(d.manifest.pack)) : ""} · ${h.memos} memos</span></div>
    <section class="card stack mid" style="padding:32px 36px">${verdictBadge(dec.verdict, true)}
      <h1 style="font-size:34px;max-width:900px">${esc(lead)}</h1>
      <p class="muted" style="font-size:17px;max-width:900px">${esc(support)}</p>
      <div class="row wrap" style="gap:12px;margin-top:6px">
        ${flagged ? `<a class="btn primary large" href="#/review/${enc(id)}">Review the ${flagged} flagged memos${ICON.arrow}</a>` : ""}
        <a class="btn large" href="/api/runs/${enc(id)}/pdf/business">${ICON.down}Download the sealed report (PDF)</a></div></section>
    <div class="grid2">
      <section class="card stack" style="gap:18px"><h2 style="font-size:21px">What went wrong</h2>
        ${risks.length ? risks.map((r) => `<div class="stack tight"><div class="row" style="justify-content:space-between"><span style="font-weight:600">${esc(r.label)}</span><span style="font-weight:600;white-space:nowrap">${plural(r.briefings, "memo")}</span></div>
          <span class="bar thick warm" aria-hidden="true"><span style="width:${pct(r.briefings, h.memos)}%"></span></span><p class="small muted">${esc(r.why)}</p></div>`).join("")
          : '<p class="muted">No recurring problem found.</p>'}
        ${example ? `<a class="link" href="#/review/${enc(id)}/memo/${enc(memoId(example.example.item_id, example.example.repeat))}">See an example memo</a>` : ""}</section>
      <section class="card stack" style="gap:18px"><h2 style="font-size:21px">What to change</h2>
        ${recs.length ? `<ol class="stack" style="list-style:none;margin:0;padding:0;gap:18px">${recs.map((r, i) => `<li class="row" style="align-items:flex-start;gap:14px">
          <span class="dot b-blue" style="width:28px;height:28px">${i + 1}</span>
          <span class="stack" style="gap:4px"><span style="font-weight:600;line-height:1.4">${esc(r.title)}</span>
          <span class="small muted">Could fix up to ${plural(r.addresses.briefings, "memo")} · ${r.owner === "bank" ? "your team" : esc(r.owner)}${r.raise_with_vendor ? " · raise with the vendor if it continues" : ""}</span>
          <details class="small"><summary>How</summary><p style="margin-top:6px">${esc(r.action)}</p></details></span></li>`).join("")}</ol>` : '<p class="muted">Nothing to change.</p>'}
        <p class="note-box blue small">Make one change, then test again. We put the two results side by side, so you can see it helped and nothing else got worse.</p></section>
    </div>
    <details class="card"><summary style="font-size:17px">Show the technical detail</summary>
      <div class="stack" style="margin-top:16px">
        <table><thead><tr><th>Check</th><th>Memos that passed</th><th>Result</th></tr></thead><tbody>
          ${(dec.checks || []).map((c) => { const [w, k] = CHECK_STATUS[c.status] || [c.status, ""]; return `<tr><td>${esc(CHECK[c.check] || c.check)}<div class="tiny muted">${esc(c.meaning || "")}</div></td><td>${Math.round(100 * c.pass_rate)}%</td><td class="${k === "red" ? "error" : ""}" style="font-weight:600;color:${k === "ok" ? "var(--green)" : k === "amber" ? "var(--amber)" : ""}">${esc(w)}</td></tr>`; }).join("")}
        </tbody></table>
        ${(dec.conditions || []).length ? `<div class="small"><b>Why:</b><ul>${dec.conditions.map((c) => `<li>${esc(c)}</li>`).join("")}</ul></div>` : ""}
        ${reports.length ? `<div class="stack tight"><b>Other reports</b><div class="row wrap" style="gap:8px">${reports.map((r) => `<a class="btn small" href="/api/runs/${enc(id)}/pdf/${enc(r.name)}">${esc(r.title || r.name)}</a>`).join("")}</div></div>` : ""}
        <div class="stack tight"><b>Is the evidence intact?</b><p class="small muted" id="vres">Every file in this test is sealed. Checking recomputes every result from the recorded memos.</p>
          <button class="btn small" id="verify" style="align-self:flex-start">Check the seal</button></div>
        <p class="tiny muted">Assistant ${esc(d.manifest.sut && d.manifest.sut.model_id)} · test ${esc(id)}</p>
      </div></details>
  </div>`;
  document.getElementById("verify").onclick = async (ev) => {
    const out = document.getElementById("vres");
    ev.target.disabled = true;
    out.textContent = "Checking…";
    try {
      const v = await api(`/api/runs/${enc(id)}/verify`, { recompute: true });
      out.innerHTML = v.ok ? `<b style="color:var(--green)">Intact.</b> ${esc(v.message)}` : `<b class="error">Does not verify.</b> ${esc(v.message)}`;
    } catch (e) { out.innerHTML = `<span class="error">${esc(e.message)}</span>`; }
    ev.target.disabled = false;
  };
}

// ----------------------------------------------------------------- review: groups

const nextInLane = (memos, lane, after) => {
  const list = memos.filter((m) => m.lane === lane);
  const i = after ? list.findIndex((m) => m.memo === after) : -1;
  return list.slice(i + 1).find((m) => !m.reviewed) || list.find((m) => !m.reviewed && m.memo !== after) || null;
};

async function viewQueue(id) {
  const [q, ov] = await Promise.all([api(`/api/review/${enc(id)}`), overview(id)]);
  renderSteps(ov, "review");
  page("");
  const s = ov.stages;
  const who = reviewer.get();
  const group = (lane) => {
    const list = q.memos.filter((m) => m.lane === lane);
    if (!list.length) return "";
    const done = list.filter((m) => m.reviewed).length;
    const next = nextInLane(q.memos, lane);
    const [name, text] = LANE[lane];
    const words = lane === "green" ? "Spot-check" : done ? "Continue" : "Start";
    const action = next
      ? `<a class="btn${lane === "red" || (lane === "amber" && !q.memos.some((m) => m.lane === "red" && !m.reviewed)) ? " primary" : ""}" href="#/review/${enc(id)}/memo/${enc(next.memo)}">${words}${ICON.arrow}</a>`
      : '<span class="badge b-green">All done</span>';
    return `<section class="card stack mid"><div class="row" style="gap:20px"><span class="lane-dot ld-${lane}" aria-hidden="true"></span>
      <div class="stack grow" style="gap:4px"><div class="row" style="gap:12px;align-items:baseline"><h2>${name}</h2><span class="muted">${plural(list.length, "memo")}</span></div>
        <p class="small muted">${text}</p><p class="small" style="font-weight:600;margin-top:4px">${done} of ${list.length} done</p></div>${action}</div>
      <details><summary class="small">Show the memos</summary><table style="margin-top:8px"><tbody>${list.map((m) => `<tr><td><a href="#/review/${enc(id)}/memo/${enc(m.memo)}">Application ${esc(m.case)}, memo ${m.repeat + 1}</a></td>
        <td class="muted">${plural(m.findings, "thing")} to check</td><td>${m.reviewed ? '<span class="badge b-green">Checked</span>' : ""}</td></tr>`).join("")}</tbody></table></details></section>`;
  };
  $view.innerHTML = `<div class="row" style="gap:32px;align-items:flex-start">
    <div class="stack grow">
      <div class="stack tight"><h1>Review the flagged memos</h1>
        <p class="muted" style="font-size:17px">The machine found possible mistakes. You decide whether they are real. Your answers are recorded and become the feedback that improves the assistant.</p></div>
      <div class="stack tight"><div class="row wrap" style="justify-content:space-between"><span style="font-weight:600">${s.flagged_checked} of ${s.flagged} flagged memos checked</span>
        <span class="small muted" id="who">${who ? `Reviewing as ${esc(who)} · <a href="#" id="change">Change</a>` : ""}</span></div>
        <span class="bar thick" aria-hidden="true"><span style="width:${pct(s.flagged_checked, s.flagged)}%"></span></span></div>
      ${["red", "amber", "green"].map(group).join("")}
      ${s.review === "done" ? `<div class="note-box blue row wrap"><p class="grow">Every flagged memo is checked. Next: settle any disagreements and build the feedback pack.</p><a class="btn primary" href="#/improve/${enc(id)}">Go to Improve${ICON.arrow}</a></div>` : ""}
    </div>
    <aside class="card stack mid hide-sm" style="width:340px;flex-shrink:0;margin-top:8px"><h2 style="font-size:18px">How reviewing works</h2>
      <ol class="stack small" style="margin:0;padding-left:20px;gap:10px"><li>Read the highlighted sentence in the memo.</li><li>Read what the machine found, and the proof from the case file.</li>
        <li>Answer one question: is the memo wrong? If you think it is right, say why.</li><li>Spotted something the machine missed? Add it.</li></ol>
      <p class="tiny muted" style="padding-top:12px;border-top:1px solid var(--line-2)">Every test case has a known right answer, so the review itself is checked too.</p></aside>
  </div>`;
  const ch = document.getElementById("change");
  if (ch) ch.onclick = (ev) => { ev.preventDefault(); const v = prompt("Your name", who); if (v && v.trim()) { reviewer.set(v.trim()); viewQueue(id); } };
}

// ----------------------------------------------------------------- review: one memo

function highlight(text, cards) {
  let html = esc(text);
  cards.forEach((c, i) => {
    const s = c.sentence && esc(c.sentence);
    if (s && html.includes(s)) html = html.replace(s, `<mark id="m-${c.card_id}"><sup>${i + 1}</sup>${s}</mark>`);
  });
  return html.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/^\s*[*-]\s{1,4}/gm, "• ").replace(/^#{1,4}\s*(.+)$/gm, "<b>$1</b>");
}

async function viewMemo(id, memo) {
  const [m, q, ov] = await Promise.all([api(`/api/review/${enc(id)}/memo?memo=${enc(memo)}`), api(`/api/review/${enc(id)}`), overview(id)]);
  renderSteps(ov, "review");
  page("wide");
  const started = Date.now();
  const laneList = q.memos.filter((x) => x.lane === m.lane);
  const pos = laneList.findIndex((x) => x.memo === memo) + 1;
  const next = nextInLane(q.memos, m.lane, memo);
  const nextHref = next ? `#/review/${enc(id)}/memo/${enc(next.memo)}` : `#/review/${enc(id)}`;
  const prior = {};
  ((m.review && m.review.verdicts) || []).forEach((v) => (prior[v.card_id] = v));
  const state = {};
  m.cards.forEach((c) => (state[c.card_id] = prior[c.card_id] ? { ...prior[c.card_id] } : { action: null }));
  const raised = [];
  let signOff = false;
  let showRaise = false;
  let editName = !reviewer.get();

  // The memo and the subbar are drawn once; the findings column redraws on every answer.
  const main = document.createElement("div");
  $view.innerHTML = "";
  const sub = document.createElement("div");
  sub.className = "subbar";
  sub.innerHTML = `<a class="link" href="#/review/${enc(id)}">${ICON.back}All flagged memos</a>
    <span class="row small" style="gap:8px"><span class="lane-dot small ld-${m.lane}" aria-hidden="true"></span><b>${LANE[m.lane][0]}</b> · memo ${pos} of ${laneList.length}</span>
    <span class="bar grow hide-sm" aria-hidden="true"><span style="width:${pct(laneList.filter((x) => x.reviewed).length, laneList.length)}%"></span></span>`;
  $view.before(sub);
  const cleanup = () => { sub.remove(); window.removeEventListener("hashchange", cleanup); };
  window.addEventListener("hashchange", cleanup);
  main.className = "review-grid";
  main.innerHTML = `<article class="card stack mid" style="padding:32px 36px">
      <p class="eyebrow">Memo written by the assistant</p>
      <h1 style="font-size:26px">Application ${esc(m.case)} · memo ${m.repeat + 1}</h1>
      ${m.review ? `<p class="note-box amber small">Checked by ${esc(m.review.reviewer)} on ${esc(shortDate(m.review.submitted_at))}. Saving again records a new review.</p>` : ""}
      <div class="memo-text">${highlight(m.text, m.cards)}</div>
      ${m.case_file.length ? `<details style="border-top:1px solid var(--line-2);padding-top:16px"><summary>Show the case file</summary>${m.case_file.map((d) => `<h3 style="margin-top:16px">${esc(d.title)}</h3><div class="casefile">${esc(d.content)}</div>`).join("")}</details>` : ""}
    </article><aside class="stack mid" id="side"></aside>`;
  $view.appendChild(main);
  const side = main.querySelector("#side");

  const answered = () => m.cards.filter((c) => state[c.card_id].action).length;
  const draw = () => {
    const who = reviewer.get();
    const cards = m.cards.map((c, i) => {
      const st = state[c.card_id];
      const btn = (a, words) => `<button type="button" data-a="${a}" aria-pressed="${st.action === a}">${words}</button>`;
      return `<section class="finding${st.action ? " answered" : ""}" data-card="${c.card_id}">
        <div class="row" style="gap:10px"><span class="dot num">${i + 1}</span><h3>${esc(c.kind)}</h3></div>
        <p>${esc(c.problem)}</p>
        ${c.sentence && !c.span ? `<p class="small muted" style="border-left:3px solid var(--line);padding-left:10px">“${esc(c.sentence)}”</p>` : ""}
        ${c.evidence ? `<div class="proof"><span class="eyebrow">${c.known_answer ? "Proof" : "Why the reviewers think so"}</span><span>${esc(c.evidence)}</span></div>` : ""}
        <p class="tiny muted">${c.known_answer ? "Found by the rule check, which knows the right answer." : "Found by the AI reviewers."}</p>
        <p style="font-weight:700;margin-top:4px">Is the memo wrong here?</p>
        <div class="answers">${btn("confirm", "Yes, it’s wrong")}${btn("dispute", "No, the memo is right")}${btn("needs_more", "Not sure")}</div>
        ${st.action === "confirm" ? `<p class="note-box small">Noted. This mistake goes into the feedback pack.</p>
          <label class="small" for="fix-${c.card_id}"><b>${c.sentence ? "How should this sentence read?" : "What should the memo say?"}</b> <span class="muted">Optional: with it, the model team gets a corrected memo.</span></label>
          ${c.sentence ? `<p class="tiny muted" style="border-left:3px solid var(--line);padding-left:10px">Now: “${esc(c.sentence)}”</p>` : ""}
          <textarea id="fix-${c.card_id}" data-fix placeholder="Write the corrected wording">${esc(st.correction || "")}</textarea>` : ""}
        ${st.action === "dispute" ? `<p class="small" style="font-weight:600">Why is the memo right?</p>
          <div class="answers chips">${Object.entries(REASON).map(([k, w]) => `<button type="button" data-r="${k}" aria-pressed="${st.reason === k}">${esc(w)}</button>`).join("")}</div>` : ""}
        ${st.action === "needs_more" ? '<p class="note-box amber small">Fine. A colleague from model risk will decide.</p>' : ""}
      </section>`;
    }).join("");
    const none = !m.cards.length ? `<section class="finding"><h3>Nothing was found in this memo</h3>
      <p class="muted small">Read it. Is it right as written?</p>
      <div class="answers"><button type="button" id="ok" aria-pressed="${signOff}">Yes, it’s right</button><button type="button" id="notok" aria-pressed="${showRaise}">No, I found a problem</button></div></section>` : "";
    const raiseForm = showRaise ? `<section class="finding stack mid"><h3>What did the machine miss?</h3>
      <label class="small" for="r-problem">What is wrong</label><input type="text" id="r-problem">
      <label class="small" for="r-sentence">Which sentence <span class="muted">(optional; paste it from the memo)</span></label><input type="text" id="r-sentence">
      <label class="small" for="r-fix">How it should read <span class="muted">(optional)</span></label><input type="text" id="r-fix">
      <button class="btn small" id="r-add" style="align-self:flex-start">Add this problem</button></section>` : "";
    side.innerHTML = `<div class="row" style="justify-content:space-between;align-items:baseline">
        <h2>${m.cards.length ? plural(m.cards.length, "thing") + " to check" : "Nothing flagged"}</h2>
        ${m.cards.length ? `<span class="small muted">${answered()} of ${m.cards.length} answered</span>` : ""}</div>
      ${cards}${none}
      ${raised.length ? `<div class="note-box blue small">${plural(raised.length, "extra problem")} added: ${raised.map((r) => esc(r.problem)).join("; ")}</div>` : ""}
      ${raiseForm}
      ${m.cards.length && !showRaise ? `<button class="btn dashed" id="more">${ICON.plus}I found another problem</button>` : ""}
      ${editName ? `<div class="stack tight"><label class="small" for="who-in"><b>Your name</b> <span class="muted">(recorded with your answers)</span></label><input type="text" id="who-in" value="${esc(who)}"></div>`
        : `<p class="small muted">Reviewing as ${esc(who)} · <a href="#" id="change">Change</a></p>`}
      <div class="row" style="gap:10px;padding-top:8px"><button class="btn primary large grow" id="save">Save and open the next memo${ICON.arrow}</button>
        <a class="btn large" href="${nextHref}">Skip</a></div><p id="msg" class="error small"></p>`;
    side.querySelectorAll("[data-card]").forEach((el) => {
      const cid = el.dataset.card;
      el.querySelectorAll("[data-a]").forEach((b) => (b.onclick = () => { state[cid] = { ...state[cid], action: b.dataset.a }; draw(); }));
      el.querySelectorAll("[data-r]").forEach((b) => (b.onclick = () => { state[cid].reason = b.dataset.r; draw(); }));
      const fix = el.querySelector("[data-fix]");
      if (fix) fix.oninput = () => (state[cid].correction = fix.value);
      el.onmouseenter = () => { const mk = document.getElementById("m-" + cid); if (mk) mk.classList.add("on"); };
      el.onmouseleave = () => { const mk = document.getElementById("m-" + cid); if (mk) mk.classList.remove("on"); };
    });
    const on = (sel, fn) => { const el = side.querySelector(sel); if (el) el.onclick = fn; };
    on("#ok", () => { signOff = true; showRaise = false; draw(); });
    on("#notok", () => { signOff = false; showRaise = true; draw(); });
    on("#more", () => { showRaise = true; draw(); });
    on("#change", (ev) => { ev.preventDefault(); editName = true; draw(); });
    on("#r-add", () => {
      const problem = side.querySelector("#r-problem").value.trim();
      if (!problem) { side.querySelector("#r-problem").focus(); return; }
      raised.push({ problem, sentence: side.querySelector("#r-sentence").value.trim(), correction: side.querySelector("#r-fix").value.trim() });
      showRaise = false;
      draw();
    });
    const whoIn = side.querySelector("#who-in");
    if (whoIn) whoIn.oninput = () => reviewer.set(whoIn.value.trim());
    on("#save", save);
  };

  async function save() {
    const msg = side.querySelector("#msg");
    const who = reviewer.get();
    const open = m.cards.filter((c) => !state[c.card_id].action).length;
    const noReason = m.cards.filter((c) => state[c.card_id].action === "dispute" && !state[c.card_id].reason).length;
    if (!who) { msg.textContent = "Enter your name first."; return; }
    if (open) { msg.textContent = `${plural(open, "finding")} still to answer.`; return; }
    if (noReason) { msg.textContent = "Say why the memo is right, for each finding you answered No."; return; }
    if (!m.cards.length && !signOff && !raised.length) { msg.textContent = "Say whether the memo is right, or add the problem you found."; return; }
    side.querySelector("#save").disabled = true;
    try {
      await api(`/api/review/${enc(id)}/submit`, {
        memo, reviewer: who, seconds: (Date.now() - started) / 1000, raised,
        verdicts: m.cards.map((c) => ({ card_id: c.card_id, ...state[c.card_id] })),
      });
      location.hash = nextHref;
    } catch (e) { msg.textContent = e.message; side.querySelector("#save").disabled = false; }
  }
  draw();
}

// ----------------------------------------------------------------- improve

async function viewImprove(id) {
  const [q, adj, ov, fb] = await Promise.all([
    api(`/api/review/${enc(id)}`), api(`/api/review/${enc(id)}/adjudication`), overview(id),
    api(`/api/review/${enc(id)}/feedback/manifest.json`).catch(() => null),
  ]);
  renderSteps(ov, "improve");
  page("");
  const s = q.summary;
  const canBuild = !adj.length && s.settled > 0;
  const c = fb ? fb.counts : null;
  const n = (k) => (c ? c[k] : "—");
  const content = (count, title, text) => `<div class="stack" style="gap:4px;padding:16px;border:1px solid var(--line-2);border-radius:12px">
    <span style="font-size:26px;font-weight:700">${count}</span><span style="font-weight:600">${title}</span><span class="tiny muted">${text}</span></div>`;
  const secs = s.seconds_per_memo_by_lane || {};
  const t = (v) => (v == null ? null : v >= 60 ? `${Math.floor(v / 60)} min ${Math.round(v % 60)} s` : `${Math.round(v)} s`);
  const times = ["red", "amber", "green"].filter((l) => secs[l] != null).map((l) => `<li>${LANE[l][0]}: ${t(secs[l])} per memo</li>`).join("");
  const dl = (f, words) => `<a class="btn small" href="/api/review/${enc(id)}/feedback/${f}">${ICON.down}${words}</a>`;
  $view.innerHTML = `<div class="row" style="gap:32px;align-items:flex-start">
    <div class="stack grow">
      <div class="stack tight"><h1>Improve the assistant</h1>
        <p class="muted" style="font-size:17px">Your review becomes a feedback pack: the material the model team needs to fix the assistant. Then you test again on new cases to prove the fix worked.</p></div>
      ${!s.reviewed ? `<div class="note-box amber row wrap"><p class="grow">Nobody has reviewed a memo in this test yet. Start with the review.</p><a class="btn" href="#/review/${enc(id)}">Go to Review</a></div>` : ""}
      <section class="card stack mid"><div class="row" style="gap:12px"><span class="dot big ${adj.length ? "fill" : "done"}">${adj.length ? "1" : ICON.check}</span><h2>Settle disagreements</h2>
        ${adj.length ? `<span class="badge b-amber">${adj.length} left</span>` : ""}</div>
        <p class="small muted">Where a reviewer disagreed with the machine, was unsure, or found a new problem, someone from model risk makes the final call. Only settled answers go into the pack.</p>
        ${adj.length ? `<table><thead><tr><th>Memo</th><th>The machine found</th><th>The reviewer said</th><th>Who is right?</th></tr></thead><tbody>${adj.map((x) => `<tr data-v="${esc(x.verdict_id)}">
          <td><a href="#/review/${enc(id)}/memo/${enc(x.memo)}">${esc(caseOf(x.memo))}</a></td>
          <td>${x.verdict.action === "raise" ? '<span class="muted">Nothing</span>' : esc(x.card.problem)}</td>
          <td>${esc(ACTION_WORDS[x.verdict.action] || x.verdict.action)}${x.verdict.action === "raise" ? `: ${esc(x.card.problem)}` : ""}${x.verdict.reason ? `<div class="tiny muted">“${esc(REASON[x.verdict.reason] || x.verdict.reason)}”</div>` : ""}<div class="tiny muted">${esc(x.reviewer)}</div></td>
          <td><div class="row" style="gap:6px"><button class="btn small" data-d="uphold">Reviewer</button><button class="btn small" data-d="reject">${x.verdict.action === "raise" ? "Not a problem" : "Machine"}</button></div></td></tr>`).join("")}</tbody></table>`
          : `<p class="small">${s.reviewed ? "Nothing to settle." : "Nothing yet."}</p>`}</section>
      <section class="card stack mid"><div class="row" style="gap:12px"><span class="dot big ${fb ? "done" : canBuild ? "fill" : "todo"}">${fb ? ICON.check : "2"}</span><h2>Build the feedback pack</h2></div>
        <p class="small muted">What the model team receives${fb ? ` (built ${esc(shortDate(fb.built_at))})` : ""}:</p>
        <div class="grid2" style="gap:12px">
          ${content(n("sft.jsonl"), "Corrected memos", "Each memo as it should have been written.")}
          ${content(n("preferences.jsonl"), "Before-and-after pairs", "The original next to the corrected memo, so the model learns the difference.")}
          ${content(n("judge_labels.jsonl"), "Confirmed findings", "Teach the AI reviewers what counts as a real mistake.")}
          ${content(n("check_fixes.jsonl"), "Fixes to the rule checks", "Where a reviewer showed a rule check was itself wrong.")}</div>
        ${fb && fb.memos_awaiting_correction.length ? `<p class="note-box amber small">${plural(fb.memos_awaiting_correction.length, "memo has", "memos have")} a confirmed mistake but no corrected wording, so ${fb.memos_awaiting_correction.length === 1 ? "it is" : "they are"} not yet a corrected memo. Open ${fb.memos_awaiting_correction.length === 1 ? "it" : "them"} in Review and write how the sentence should read.</p>` : ""}
        <div class="note-box small"><span style="color:var(--green);display:flex">${ICON.lock}</span><p>No customer data. The pack is sealed with a fingerprint, so any later change shows.</p></div>
        <div class="row wrap" style="gap:12px"><button class="btn primary large" id="build" ${canBuild ? "" : "disabled"}>${fb ? "Build it again" : "Build feedback pack"}</button>
          <span class="small muted" id="bmsg">${canBuild ? "" : adj.length ? `Available once the ${plural(adj.length, "disagreement")} ${adj.length === 1 ? "is" : "are"} settled.` : "Available once memos have been reviewed."}</span></div>
        ${fb ? `<div class="row wrap" style="gap:8px">${dl("sft.jsonl", "Corrected memos")}${dl("preferences.jsonl", "Before-and-after pairs")}${dl("judge_labels.jsonl", "Confirmed findings")}${dl("check_fixes.jsonl", "Rule-check fixes")}${dl("manifest.json", "Contents and fingerprints")}</div>` : ""}</section>
      <section class="card stack mid"><div class="row" style="gap:12px"><span class="dot big ${fb ? "fill" : "todo"}">3</span><h2>Test again on new cases</h2></div>
        <p class="small muted">When the model team has updated the assistant, run a new test with cases it has never seen. We put the two results side by side, so you can see whether the fix worked and nothing else got worse.</p>
        <a class="btn${fb ? " primary" : ""}" href="#/new" style="align-self:flex-start">Start a re-test</a></section>
    </div>
    <aside class="card stack hide-sm" style="width:320px;flex-shrink:0;margin-top:8px;gap:16px"><h2 style="font-size:18px">How reliable was the review?</h2>
      ${s.known_answer_verdicts ? `<div class="stack" style="gap:2px"><span style="font-size:30px;font-weight:700">${pct(s.agree_with_known_answer, s.known_answer_verdicts)}%</span><span class="small muted">of answers matched the known right answer (${s.agree_with_known_answer} of ${s.known_answer_verdicts})</span></div>
        <div class="stack" style="gap:2px;padding-top:14px;border-top:1px solid var(--line-2)"><span style="font-size:30px;font-weight:700${s.automation_bias_memos ? ";color:var(--red)" : ""}">${s.automation_bias_memos}</span><span class="small muted">${s.automation_bias_memos === 1 ? "memo was" : "memos were"} approved although ${s.automation_bias_memos === 1 ? "it" : "they"} had a known mistake. A high number means people trust the machine too much.</span></div>
        ${times ? `<div class="stack tight" style="padding-top:14px;border-top:1px solid var(--line-2)"><span class="small" style="font-weight:600">Time spent</span><ul class="small muted" style="margin:0;padding-left:18px">${times}</ul></div>` : ""}`
        : '<p class="small muted">Shown once memos have been reviewed. Every test case has a known right answer, so each answer can be checked.</p>'}
    </aside>
  </div>`;
  document.querySelectorAll("[data-v]").forEach((tr) => tr.querySelectorAll("[data-d]").forEach((b) => (b.onclick = async () => {
    b.disabled = true;
    await api(`/api/review/${enc(id)}/adjudicate`, { verdict_id: tr.dataset.v, decision: b.dataset.d, by: reviewer.get() || "model-risk" });
    viewImprove(id);
  })));
  const build = document.getElementById("build");
  build.onclick = async () => {
    build.disabled = true;
    document.getElementById("bmsg").textContent = "Building…";
    try { await api(`/api/review/${enc(id)}/feedback`, {}); viewImprove(id); } catch (e) {
      document.getElementById("bmsg").innerHTML = `<span class="error">${esc(e.message)}</span>`;
      build.disabled = false;
    }
  };
}

// ----------------------------------------------------------------- earlier tests

async function viewHistory() {
  const [runs, ov] = await Promise.all([api("/api/runs"), overview()]);
  renderSteps(ov, "history");
  page("");
  const list = runs.filter((r) => r.sealed && r.transcripts).sort((a, b) => (b.finished_at || "").localeCompare(a.finished_at || ""));
  $view.innerHTML = `<div class="stack">
    <a class="link back" href="#/">${ICON.back}Home</a>
    <div class="row wrap" style="align-items:flex-end;gap:24px;margin-top:-8px"><div class="stack tight grow"><h1>Earlier tests</h1>
      <p class="muted" style="font-size:17px">Every test is sealed and can be re-checked at any time. Tick two to compare them.</p></div>
      <button class="btn primary" id="cmp" disabled>Compare the 2 ticked tests</button></div>
    <div class="card" style="padding:8px 20px"><table><thead><tr><th style="width:44px"><span class="visually-hidden">Compare</span></th><th>Date</th><th>Test cases</th><th>Result</th><th>Memos with a mistake</th><th class="hide-sm">Reviewed</th><th><span class="visually-hidden">Open</span></th></tr></thead><tbody>
      ${list.map((r) => `<tr><td><input type="checkbox" data-run="${esc(r.run_id)}" aria-label="Compare the test of ${esc(date(r.finished_at))}" style="width:20px;height:20px;accent-color:var(--accent)"></td>
        <td style="font-weight:600;white-space:nowrap">${esc(shortDate(r.finished_at))}${ov.run && ov.run.run_id === r.run_id ? '<div class="tiny muted">Latest</div>' : ""}</td>
        <td>${esc(packName(r.pack))}</td><td>${verdictBadge(r.verdict)}</td><td>${r.memos_with_error} of ${r.memos}</td>
        <td class="hide-sm">${r.reviewed ? "Yes" : '<span class="muted">No</span>'}</td>
        <td style="text-align:right"><a class="link" href="#/result/${enc(r.run_id)}">Open</a></td></tr>`).join("")}
    </tbody></table></div></div>`;
  const boxes = [...document.querySelectorAll("[data-run]")];
  const cmp = document.getElementById("cmp");
  boxes.forEach((b) => (b.onchange = () => {
    const on = boxes.filter((x) => x.checked);
    if (on.length > 2) b.checked = false;
    cmp.disabled = boxes.filter((x) => x.checked).length !== 2;
  }));
  cmp.onclick = () => {
    const ids = boxes.filter((x) => x.checked).map((x) => x.dataset.run);
    const when = (rid) => (list.find((r) => r.run_id === rid) || {}).finished_at || "";
    ids.sort((a, b) => when(a).localeCompare(when(b)));
    location.hash = `#/compare/${enc(ids[0])}/${enc(ids[1])}`;
  };
}

const COMPARE = {
  ACCEPT: ["The change helped, and nothing got worse", "b-green"],
  REJECT: ["The change made something worse", "b-red"],
  INCONCLUSIVE: ["Something may have got worse. Not safe to accept yet", "b-amber"],
  "NO EFFECT": ["No clear difference", "b-grey"],
};
const CMP_STATUS = { improved: "Better", regressed: "Worse", possibly_worse: "Possibly worse", no_clear_change: "No clear change", not_comparable: "Not comparable" };

async function viewCompare(before, after) {
  const [c, ov] = await Promise.all([api(`/api/compare?before=${enc(before)}&after=${enc(after)}`), overview()]);
  renderSteps(ov, "history");
  page("narrow");
  const [words, cls] = COMPARE[c.verdict] || [c.verdict, "b-grey"];
  const p = (v) => (v == null ? "—" : `${Math.round(100 * v)}%`);
  $view.innerHTML = `<div class="stack">
    <a class="link back" href="#/history">${ICON.back}Earlier tests</a>
    <section class="card stack mid"><span class="badge big ${cls}">${esc(words)}</span>
      <h1 style="font-size:30px">${esc(shortDate(c.before.finished_at))} compared with ${esc(shortDate(c.after.finished_at))}</h1>
      ${c.changed.length ? `<p class="muted">What changed between the two: ${c.changed.map((x) => esc(x.what)).join(", ")}.</p>` : ""}
      ${c.warnings.map((w) => `<p class="note-box amber small">${esc(w)}</p>`).join("")}</section>
    <section class="card"><table><thead><tr><th>Check</th><th>Before</th><th>After</th><th>Change</th></tr></thead><tbody>
      ${c.checks.map((k) => `<tr><td>${esc(CHECK[k.check] || k.check)}</td><td>${p(k.before)}</td><td>${p(k.after)}</td>
        <td style="font-weight:600;color:${k.status === "improved" ? "var(--green)" : k.status === "regressed" || k.status === "possibly_worse" ? "var(--red)" : "var(--ink-2)"}">${esc(CMP_STATUS[k.status] || k.status)}</td></tr>`).join("")}
    </tbody></table></section>
    ${c.causes.length ? `<section class="card stack mid"><h2>Mistakes by type</h2><table><thead><tr><th>Mistake</th><th>Before</th><th>After</th></tr></thead><tbody>
      ${c.causes.map((k) => `<tr><td>${esc(k.label)}</td><td>${k.before}</td><td>${k.after}</td></tr>`).join("")}</tbody></table></section>` : ""}
  </div>`;
}

// ----------------------------------------------------------------- routing

async function route() {
  clearTimeout(pollTimer);
  const parts = location.hash.replace(/^#\/?/, "").split("/").map(decodeURIComponent);
  try {
    if (!parts[0]) return await viewHome();
    if (parts[0] === "new") return await viewNew();
    if (parts[0] === "running" && parts[1]) return await viewRunning(parts[1]);
    if (parts[0] === "result" && parts[1]) return await viewResult(parts[1]);
    if (parts[0] === "review" && parts[1] && parts[2] === "memo") return await viewMemo(parts[1], parts.slice(3).join("/"));
    if (parts[0] === "review" && parts[1]) return await viewQueue(parts[1]);
    if (parts[0] === "improve" && parts[1]) return await viewImprove(parts[1]);
    if (parts[0] === "history") return await viewHistory();
    if (parts[0] === "compare" && parts[2]) return await viewCompare(parts[1], parts[2]);
    location.hash = "#/";
  } catch (e) {
    page("narrow");
    $view.innerHTML = `<div class="card stack mid"><h2>Something went wrong</h2><p class="error">${esc(e.message)}</p><a class="btn" href="#/" style="align-self:flex-start">Home</a></div>`;
  }
}
window.addEventListener("hashchange", () => { window.scrollTo(0, 0); route(); });
route();
