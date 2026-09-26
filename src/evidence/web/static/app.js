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
const packFamily = (id) => String(id || "").replace(/-s\d+$/, "");
const packSeed = (id) => (String(id || "").match(/-s(\d+)$/) || [])[1];
function packName(pack) {
  const id = (pack && pack.pack_id) || pack || "";
  const fam = packFamily(id), seed = packSeed(id);
  const base = fam === "underwriter-de" ? "Personal loans, Germany (in euros)"
    : fam === "underwriter-sample" ? "Personal loans, sample (in pounds)" : fam;
  return seed ? `${base}, new cases #${seed}` : base;
}
const rulesName = (pack) => (RULES[PACK_JURISDICTION[packFamily((pack && pack.pack_id) || pack)]] || [])[1] || "";
const SETUP = { as_is: "As today: the case file only", with_figures: "With the figures your systems already calculate" };
const LANE = {
  red: ["Check first", "The rule checks and the AI reviewers both found a problem."],
  amber: ["Worth a look", "Only one of the two found a problem. Your answers here show whether the AI reviewers raise false alarms."],
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
const when = (iso) => (iso ? new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "");
const testName = (r) => (r && r.test_no ? `Test ${r.test_no}` : "Test");
const testLabel = (r) => `${testName(r)} · ${when((r && (r.started_at || r.finished_at)) || "")}`;
const sizeWords = (r) => (r && r.cases && r.repeats ? `${plural(r.cases, "case")} × ${r.repeats === 1 ? "once" : r.repeats === 2 ? "twice" : r.repeats + " times"}` : "");
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
  const showTest = run && !testState && !["cases", "history"].includes(active);
  $steps.innerHTML = [
    showTest ? `<span class="testchip" title="${esc(run.run_id)}"><b>${esc(testName(run))}</b> ${esc(when(run.started_at || run.finished_at))}</span>` : "",
    step("test", 1, testState ? "#/new" : run ? `#/result/${rid}` : "#/new", test[0], test[1], "Test"),
    '<span class="sep" aria-hidden="true"></span>',
    step("review", 2, run ? `#/review/${rid}` : "#/", reviewState, reviewWords, "Review"),
    '<span class="sep" aria-hidden="true"></span>',
    step("improve", 3, run ? `#/improve/${rid}` : "#/", improveState, improveWords, "Improve"),
  ].join("");
  document.querySelectorAll(".history").forEach((a) => a.classList.toggle("on", a.dataset.nav === active));
}

const overview = (run, pending) => api(`/api/overview?${run ? `run=${enc(run)}&` : ""}${pending ? "pending=true" : ""}`);
function page(cls) { $view.className = cls || ""; }

// ----------------------------------------------------------------- home

async function viewHome() {
  const ov = await overview(null, true);
  renderSteps(ov, null);
  page("");
  const job = (ov.jobs || [])[0];
  const banner = job ? `<a class="note-box blue link" href="#/running/${enc(job.job_id)}" style="text-decoration:none">
      <span class="spinner" style="width:22px;height:22px" aria-hidden="true"></span>
      <span class="grow">A test is running: ${job.phase === "panel" ? "second opinion" : "memos"} ${job.done} of ${job.total}. Open it to follow or stop it.</span>${ICON.arrow}</a>` : "";
  const r = ov.run, s = ov.stages;
  const startCard = `<section class="card row wrap${!r || s.next === "test" ? " strong" : ""}" style="gap:24px">
      <span class="dot big fill" aria-hidden="true">${ICON.plus}</span>
      <div class="stack tight grow"><h2>Start a new test</h2>
        <p class="muted small">The assistant writes memos for made-up loan cases, and each memo is checked against the rules. You choose the cases, how many, and how many times each.</p></div>
      <a class="btn primary large" href="#/new">Start a new test${ICON.arrow}</a></section>`;
  const head = `<div class="stack tight"><p class="muted small">You are testing</p><h1 style="font-size:40px">Credit memo assistant</h1>
      <p class="muted" style="font-size:17px">The AI that writes a summary for the underwriter when a loan application is referred.</p></div>`;
  const lock = `<div class="row wrap"><span style="color:var(--green);display:flex">${ICON.lock}</span>
      <p class="muted small grow">Test cases are generated from your credit policy. No customer data is used.</p></div>`;
  if (!r) {
    $view.innerHTML = `<div class="stack" style="gap:32px">${banner}${head}${startCard}${lock}</div>`;
    return;
  }
  const rid = enc(r.run_id);
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
  const pending = (ov.to_review || []).slice(0, 5);
  const more = (ov.to_review || []).length - pending.length;
  const waiting = pending.length ? `<section class="card stack mid" aria-labelledby="waiting"><div class="row wrap" style="justify-content:space-between;align-items:baseline">
      <h2 id="waiting">Waiting for review</h2><span class="small muted">${plural(ov.to_review.length, "test")} with flagged memos still to check${more ? ` · the newest ${pending.length} shown, <a href="#/history">all in Earlier tests</a>` : ""}</span></div>
      <table><thead><tr><th>Test</th><th>Started</th><th class="hide-sm">Cases</th><th>Checked</th><th><span class="visually-hidden">Open</span></th></tr></thead><tbody>
      ${pending.map((t) => `<tr${t.run_id === r.run_id ? ' class="on"' : ""}><td style="font-weight:600;white-space:nowrap">${esc(testName(t))}${t.run_id === r.run_id ? '<div class="tiny muted">Latest</div>' : ""}</td>
        <td style="white-space:nowrap">${esc(when(t.started_at || t.finished_at))}</td>
        <td class="hide-sm small">${esc(rulesName(t.pack) || packName(t.pack))}<div class="tiny muted">${esc(sizeWords(t))}</div></td>
        <td style="min-width:120px"><span class="small">${t.flagged_checked} of ${t.flagged}</span><span class="bar" style="display:block;margin-top:4px" aria-hidden="true"><span style="width:${pct(t.flagged_checked, t.flagged)}%"></span></span></td>
        <td style="text-align:right"><a class="link" href="#/review/${enc(t.run_id)}">${t.flagged_checked ? "Continue" : "Start"} review</a></td></tr>`).join("")}
      </tbody></table></section>` : "";
  $view.innerHTML = `<div class="stack" style="gap:32px">${banner}${head}${startCard}
    <div class="stack tight"><h2>Latest test: ${esc(testName(r))}</h2>
      <p class="muted small">Started ${esc(when(r.started_at || r.finished_at))}${rulesName(r.pack) ? " · " + esc(rulesName(r.pack)) : ""}${sizeWords(r) ? " · " + esc(sizeWords(r)) : ""}</p></div>
    <section class="card row wrap" aria-label="Result of the latest test" style="gap:32px;margin-top:-16px">
      <div class="stack tight grow">${verdictBadge(r.verdict)}
        <p style="font-size:22px;font-weight:600;line-height:1.35">${r.memos_with_error
          ? `${r.memos_with_error} of ${r.memos} test memos had a mistake an underwriter could act on.`
          : `No mistakes found in ${r.memos} test memos.`}</p></div>
      <a class="btn" href="#/result/${rid}">See the result</a></section>
    <div class="grid3">
      ${card("test", 1, "Test", "done", `The assistant wrote ${r.memos} memos for made-up loan cases. Each memo was checked against the rules.`, `<a class="link" href="#/result/${rid}">See the result</a>`)}
      ${card("review", 2, "Review", s.review, reviewText + (s.review === "in_progress" ? `<span class="bar" style="margin-top:12px;display:block" aria-hidden="true"><span style="width:${pct(s.flagged_checked, flagged)}%"></span></span>` : ""),
        cta("review", `#/review/${rid}`, s.review === "not_started" ? "Start review" : s.review === "done" ? "Open review" : "Continue review"))}
      ${card("improve", 3, "Improve", s.improve, improveText, cta("improve", `#/improve/${rid}`, s.improve === "not_started" ? "How this works" : s.improve === "done" ? "Open feedback pack" : "Continue"))}
    </div>
    ${waiting}
    ${lock}
  </div>`;
}

// ----------------------------------------------------------------- new test

async function viewNew(preselect) {
  const [ov, meta, packs] = await Promise.all([overview(), api("/api/meta"), api("/api/packs")]);
  renderSteps(ov, "test", "New");
  page("narrow");
  const usable = packs.filter((p) => !p.error && p.items);
  const byJ = {};
  usable.forEach((p) => { const j = p.jurisdiction || PACK_JURISDICTION[packFamily(p.pack_id)] || "other"; (byJ[j] = byJ[j] || []).push(p); });
  Object.values(byJ).forEach((l) => l.sort((a, b) => (packSeed(a.pack_id) ? 1 : 0) - (packSeed(b.pack_id) ? 1 : 0) || (b.built_at || "").localeCompare(a.built_at || "")));
  let chosenPack = null;
  const js = Object.keys(byJ).sort((a, b) => (a === "DE" ? -1 : b === "DE" ? 1 : a.localeCompare(b)));
  let chosenJ = js[0];
  if (preselect) {
    const hit = usable.find((p) => p.pack_id === preselect);
    if (hit) { chosenJ = hit.jurisdiction || PACK_JURISDICTION[packFamily(hit.pack_id)] || chosenJ; chosenPack = hit.pack_id; }
  }
  const a = meta.roles.assistant;
  const maxRepeats = (meta.limits && meta.limits.repeats) || 5;
  const maxItems = (meta.limits && meta.limits.items) || Infinity;
  $view.innerHTML = `<div class="stack" style="gap:28px">
    <a class="link back" href="#/">${ICON.back}Home</a>
    <div class="stack tight" style="margin-top:-12px"><h1>Start a new test</h1>
      <p class="muted" style="font-size:17px">Answer four questions. The test then runs by itself; a small test takes a few minutes.</p></div>
    <fieldset><legend>1. Which assistant are you testing?</legend>
      <label for="assistant" class="small muted">Assistant</label>
      <select id="assistant"><option>Credit memo assistant (${esc(a.model)})</option></select>
      <p class="tiny muted">${a.where === "on-prem" ? "Runs on your own servers." : "Runs on NVIDIA's cloud."}</p></fieldset>
    <fieldset><legend>2. Which rules must its memos follow?</legend><div class="stack tight" id="rules"></div></fieldset>
    <fieldset><legend>3. Which test cases?</legend><div class="stack tight" id="cases"></div>
      <div class="row wrap" style="gap:12px"><button class="btn" id="fresh">${ICON.plus}Generate new cases</button>
        <span class="small muted" id="freshmsg">Cases the assistant has never seen, made from your credit policy. You choose how many.</span></div></fieldset>
    <fieldset><legend>4. How big a test?</legend>
      <div class="row wrap" style="gap:20px;align-items:flex-end">
        <div class="stack tight"><label class="small" for="ncases"><b>Cases to use</b></label>
          <input type="number" id="ncases" min="1" step="1" style="width:120px"><span class="tiny muted" id="ncasesmax"></span></div>
        <div class="stack tight"><label class="small" for="nrepeats"><b>Times each case is run</b></label>
          <select id="nrepeats" style="width:160px">${[1, 2, 3, 4, 5].filter((n) => n <= maxRepeats).map((n) => `<option value="${n}" ${n === Math.min(3, maxRepeats) ? "selected" : ""}>${n === 1 ? "Once" : n === 2 ? "Twice" : n + " times"}</option>`).join("")}</select></div>
        <p class="grow" id="nmemos" style="font-weight:600"></p></div>
      <p class="small muted">Running a case more than once shows whether the assistant answers the same way each time. A small test (say 5 cases, twice) is quick for trying things out; a larger one gives firmer numbers.</p></fieldset>
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
    if (!list.some((p) => p.pack_id === chosenPack)) chosenPack = list.length ? list[0].pack_id : null;
    document.getElementById("cases").innerHTML = list.map((p) => `<label class="choice-card">
      <input type="radio" name="cases" value="${esc(p.pack_id)}" ${p.pack_id === chosenPack ? "checked" : ""}>
      <span class="stack tight"><span class="t">${esc(packName(p))}</span><span class="small muted">${p.items} cases, each with a known right answer${p.built_at ? ` · made ${esc(when(p.built_at))}` : ""}${packSeed(p.pack_id) ? " · never used before" : ""}</span></span></label>`).join("");
    document.querySelectorAll("input[name=cases]").forEach((el) => (el.onchange = () => { chosenPack = el.value; drawSize(true); }));
    drawSize(true);
  };
  // How many cases from the chosen set, and how many times each: the memos to write.
  const drawSize = (reset) => {
    const p = (byJ[chosenJ] || []).find((x) => x.pack_id === chosenPack);
    const most = Math.min(p ? p.items : 1, maxItems);
    const box = document.getElementById("ncases");
    box.max = String(most);
    if (reset || !+box.value) box.value = String(most);
    box.value = String(Math.max(1, Math.min(most, Math.round(+box.value) || most)));
    document.getElementById("ncasesmax").textContent = `of ${plural(p ? p.items : 0, "case")} in the set`;
    const n = +box.value * +document.getElementById("nrepeats").value;
    document.getElementById("nmemos").textContent = `= ${plural(n, "memo")} to write and check`;
  };
  drawRules();
  drawCases();
  ["ncases", "nrepeats"].forEach((k) => (document.getElementById(k).oninput = () => drawSize(false)));
  document.getElementById("ncases").onchange = () => drawSize(false);
  document.getElementById("fresh").onclick = () => {
    const from = chosenPack || ((byJ[chosenJ] || [])[0] || {}).pack_id;
    if (!from) return;
    const times = +document.getElementById("nrepeats").value;
    generateCases(from, (f, fresh, times) => {
      (byJ[chosenJ] = byJ[chosenJ] || []).unshift(fresh);
      chosenPack = f.pack_id;
      document.getElementById("nrepeats").value = String(times);
      drawCases();
      document.getElementById("freshmsg").innerHTML = `${f.items} new cases (set #${f.seed}) made in ${f.seconds} s and chosen, each run ${times === 1 ? "once" : times === 2 ? "twice" : times + " times"}. ${f.shared_with_other_packs ? `<span class="error">${f.shared_with_other_packs} match earlier cases.</span>` : "None of them appears in an earlier test."}`;
    }, times, maxRepeats);
  };
  document.getElementById("start").onclick = async (ev) => {
    const pack = (document.querySelector("input[name=cases]:checked") || {}).value;
    if (!pack) return;
    ev.target.disabled = true;
    try {
      const j = await api("/api/run", { pack, repeats: +document.getElementById("nrepeats").value, limit: +document.getElementById("ncases").value, judge: true, setup: "as_is", panel: document.getElementById("panel").checked });
      location.hash = `#/running/${enc(j.job_id)}`;
    } catch (e) {
      document.getElementById("msg").textContent = e.message;
      ev.target.disabled = false;
    }
  };
}

// The "Generate new cases" window: how many cases, how many times each is run in the test,
// and whether the bank's figures are included. Calls done(result, pack, repeats) once made.
function generateCases(from, done, repeats = 3, maxRepeats = 5) {
  const dlg = document.createElement("dialog");
  dlg.className = "modal";
  dlg.setAttribute("aria-labelledby", "gen-title");
  dlg.innerHTML = `<form method="dialog" class="stack mid">
      <div class="stack tight"><h2 id="gen-title">Generate new cases</h2>
        <p class="small muted">Made-up loan applications the assistant has never seen, generated from your credit policy by the Synthetic Data Designer. Each one has a known right answer. No customer data is used.</p></div>
      <p class="small"><b>Cases like:</b> ${esc(packName(packFamily(from)))}</p>
      <div class="stack tight"><label class="small" for="gen-n"><b>How many cases</b></label>
        <input type="number" id="gen-n" min="5" max="200" step="1" value="20" style="width:120px">
        <span class="tiny muted">Between 5 and 200. 5 is enough to try things out.</span></div>
      <div class="stack tight"><label class="small" for="gen-r"><b>Times each case is run in the test</b></label>
        <select id="gen-r" style="width:160px">${[1, 2, 3, 4, 5].filter((n) => n <= maxRepeats).map((n) => `<option value="${n}" ${n === repeats ? "selected" : ""}>${n === 1 ? "Once" : n === 2 ? "Twice" : n + " times"}</option>`).join("")}</select>
        <span class="tiny muted">The assistant can write a different memo each time for the same case, so running it more than once shows how consistent it is.</span></div>
      <p class="small" id="gen-total" style="font-weight:600"></p>
      <label class="choice-card"><input type="checkbox" id="gen-bank" checked><span class="stack tight"><span class="t">Include the figures your systems calculate</span>
        <span class="small muted">A rules-engine summary in each case file. The assistant only sees it when a test asks for it.</span></span></label>
      <p class="small" id="gen-msg" role="status"></p>
      <div class="row wrap" style="gap:10px"><button type="button" class="btn primary" id="gen-go">Generate</button>
        <button type="button" class="btn" id="gen-cancel">Cancel</button>
        <a class="link small" href="#/cases" style="margin-left:auto">All case sets</a></div></form>`;
  document.body.appendChild(dlg);
  const close = () => { dlg.close(); dlg.remove(); };
  dlg.addEventListener("cancel", (ev) => { if (busy) ev.preventDefault(); });
  dlg.addEventListener("close", () => dlg.remove());
  dlg.querySelector("a[href='#/cases']").onclick = close;
  let busy = false;
  dlg.querySelector("#gen-cancel").onclick = () => { if (!busy) close(); };
  const total = () => {
    const n = Math.round(+dlg.querySelector("#gen-n").value) || 0;
    dlg.querySelector("#gen-total").textContent = `= ${plural(n * +dlg.querySelector("#gen-r").value, "memo")} in the test`;
  };
  dlg.querySelector("#gen-n").oninput = total;
  dlg.querySelector("#gen-r").oninput = total;
  total();
  dlg.querySelector("#gen-go").onclick = async (ev) => {
    const n = Math.round(+dlg.querySelector("#gen-n").value);
    const msg = dlg.querySelector("#gen-msg");
    if (!(n >= 5 && n <= 200)) { msg.innerHTML = '<span class="error">Choose between 5 and 200 cases.</span>'; return; }
    busy = true;
    ev.target.disabled = true;
    dlg.querySelector("#gen-cancel").disabled = true;
    msg.innerHTML = '<span class="row small"><span class="spinner" style="width:18px;height:18px" aria-hidden="true"></span>Generating cases from your credit policy… usually under a minute.</span>';
    try {
      const f = await api("/api/packs/fresh", { from, keep: n, bank_figures: dlg.querySelector("#gen-bank").checked });
      const fresh = (await api("/api/packs")).find((p) => p.pack_id === f.pack_id);
      busy = false;
      if (!dlg.isConnected) return;  // the page was left while the cases were made
      const times = +dlg.querySelector("#gen-r").value;
      close();
      done(f, fresh, times);
    } catch (e) {
      busy = false;
      msg.innerHTML = `<span class="error">${esc(e.message)}</span>`;
      ev.target.disabled = false;
      dlg.querySelector("#gen-cancel").disabled = false;
    }
  };
  dlg.showModal();
  dlg.querySelector("#gen-n").select();
}

// ----------------------------------------------------------------- case sets

async function viewCases() {
  const [ov, packs, meta] = await Promise.all([overview(), api("/api/packs"), api("/api/meta")]);
  renderSteps(ov, "cases");
  page("");
  const usable = packs.filter((p) => !p.error && p.items);
  const families = [...new Set(usable.map((p) => packFamily(p.pack_id)))];
  const designer = meta.designer;
  const row = (p) => `<tr><td style="font-weight:600">${esc(packName(p))}</td><td>${p.items}</td>
    <td>${esc(rulesName(p) || p.jurisdiction || "")}</td><td>${p.bank_figures ? "Yes" : '<span class="muted">No</span>'}</td>
    <td class="muted" style="white-space:nowrap">${esc(when(p.built_at))}</td><td style="text-align:right"><a class="link" href="#/new/${enc(p.pack_id)}">Use in a test</a></td></tr>`;
  $view.innerHTML = `<div class="stack">
    <div class="stack tight"><h1>Case sets</h1>
      <p class="muted" style="font-size:17px">Every test case is a made-up loan application with a known right answer, generated from your credit policy by the Synthetic Data Designer. No customer data is used, so a new set can be made at any time.</p></div>
    <div class="grid2">
      <section class="card stack mid"><h2>Create a case set</h2>
        <label class="small" for="fam">Cases like</label>
        <select id="fam">${families.map((f) => `<option value="${esc(f)}">${esc(packName(f))}</option>`).join("")}</select>
        <label class="small" for="keep">How many cases</label>
        <input type="number" id="keep" min="5" max="200" step="1" value="20" style="width:120px"><span class="tiny muted">Between 5 and 200.</span>
        <label class="choice-card"><input type="checkbox" id="bank" checked><span class="stack tight"><span class="t">Include the figures your systems calculate</span>
          <span class="small muted">A rules-engine summary in each case file. Needed to test the recommended change; the assistant only sees it when a test asks for it.</span></span></label>
        <div class="row wrap" style="gap:12px"><button class="btn primary" id="create">Create case set</button><span class="small" id="cmsg"></span></div>
      </section>
      <section class="card stack mid"><h2>Design the recipe</h2>
        <p class="small muted">The designer shows how cases are made: who applies, their incomes, debts and credit files, and how often each happens. Open the <b>credit_underwriting</b> recipe to see it or change it, then export the recipe to build a case set from it.</p>
        ${designer ? `<a class="btn" href="${esc(designer.url)}" target="_blank" rel="noopener" style="align-self:flex-start">Open the Synthetic Data Designer</a>` : '<p class="small error">The Synthetic Data Designer is not installed on this server.</p>'}
        <details><summary class="small">Build a case set from a recipe file</summary>
          <div class="stack tight" style="margin-top:10px">
            <label class="small" for="spec">Recipe (YAML) exported from the designer</label><input type="file" id="spec" accept=".yaml,.yml">
            <label class="small" for="smarket">Market</label><select id="smarket"><option value="de">Germany (in euros)</option><option value="sample">Sample (in pounds)</option></select>
            <div class="row wrap" style="gap:12px"><button class="btn" id="buildspec">Build case set</button><span class="small" id="smsg"></span></div></div></details>
      </section>
    </div>
    <section class="card" style="padding:8px 20px"><table><thead><tr><th>Case set</th><th>Cases</th><th>Rules</th><th>Bank figures</th><th>Made</th><th><span class="visually-hidden">Use</span></th></tr></thead>
      <tbody>${usable.map(row).join("")}</tbody></table></section>
  </div>`;
  document.getElementById("create").onclick = async (ev) => {
    const msg = document.getElementById("cmsg");
    const fam = document.getElementById("fam").value;
    const from = (usable.find((p) => p.pack_id === fam) || usable.find((p) => packFamily(p.pack_id) === fam)).pack_id;
    ev.target.disabled = true;
    msg.textContent = "Generating…";
    try {
      const f = await api("/api/packs/fresh", { from, keep: +document.getElementById("keep").value, bank_figures: document.getElementById("bank").checked });
      msg.innerHTML = `Made ${f.items} new cases (set #${f.seed}) in ${f.seconds} s. <a href="#/new/${enc(f.pack_id)}">Use them in a test</a>`;
      setTimeout(() => viewCases().then(() => { document.getElementById("cmsg").innerHTML = msg.innerHTML; }), 50);
    } catch (e) { msg.innerHTML = `<span class="error">${esc(e.message)}</span>`; ev.target.disabled = false; }
  };
  document.getElementById("buildspec").onclick = async (ev) => {
    const msg = document.getElementById("smsg");
    const file = document.getElementById("spec").files[0];
    if (!file) { msg.textContent = "Choose a recipe file first."; return; }
    const market = document.getElementById("smarket").value;
    const form = new FormData();
    const seed = Math.floor(1000 + Math.random() * 90000);
    form.append("pack_id", `${market === "de" ? "underwriter-de" : "underwriter-sample"}-s${seed}`);
    form.append("n", "700"); form.append("keep", "20"); form.append("seed", String(seed));
    form.append("market", market); form.append("bank_figures", "true"); form.append("spec", file);
    ev.target.disabled = true;
    msg.textContent = "Building…";
    try {
      const r = await fetch("/api/packs/build", { method: "POST", body: form });
      const j = await r.json();
      if (!r.ok) throw new Error(j.detail || r.statusText);
      for (let i = 0; i < 120; i++) {
        const st = await api(`/api/run/${enc(j.job_id)}`);
        if (st.status === "done") { msg.innerHTML = `Built. <a href="#/new/${enc(j.pack_id)}">Use it in a test</a>`; return; }
        if (st.status === "error") throw new Error(st.error);
        await new Promise((res) => setTimeout(res, 1000));
      }
    } catch (e) { msg.innerHTML = `<span class="error">${esc(e.message)}</span>`; }
    ev.target.disabled = false;
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
    let foot = job.cancel
      ? `<div class="row"><span class="spinner" aria-hidden="true"></span><p>Stopping. The AI calls already under way finish first, which can take a minute or two. Everything finished so far is kept.</p></div>`
      : `<p class="muted">You can close this page. The result will be waiting on the home page.</p>
      <button class="btn" id="stop" style="align-self:flex-start">Stop the test</button>`;
    if (job.status === "done") foot = `<a class="btn primary large" href="#/result/${enc(job.run_id)}" style="align-self:flex-start">See the result${ICON.arrow}</a>`;
    if (job.status === "cancelled") foot = `<p>The test was stopped. ${job.transcripts ? `The ${job.transcripts} memos written so far are kept${job.panel ? ", with the second opinions that finished" : ""}.` : "Nothing was written yet."}</p>${job.transcripts ? `<a class="btn" href="#/result/${enc(job.run_id)}" style="align-self:flex-start">See what was done</a>` : ""}`;
    if (job.status === "error") foot = `<p class="error">The test stopped with an error: ${esc(job.error)}</p><a class="btn" href="#/new" style="align-self:flex-start">Try again</a>`;
    $view.innerHTML = `<div class="stack" style="gap:28px">
      <div class="stack tight"><h1>${job.status === "done" ? "The test is finished" : "Testing the credit memo assistant"}</h1>
        <p class="muted" style="font-size:17px">Started ${esc(when(String(job.started || "").replace(/^(\d{4}-\d\d-\d\dT)(\d\d)(\d\d)(\d\d)Z$/, "$1$2:$3:$4Z")))} · ${plural(job.cases && job.repeats ? job.cases * job.repeats : job.total, "memo")}${job.cases ? ` (${esc(sizeWords(job))})` : ""}</p></div>
      <ol class="card" style="list-style:none;padding:8px 28px;margin:0">${items.join("")}</ol>${foot}</div>`;
    const stop = document.getElementById("stop");
    if (stop) stop.onclick = async () => {
      if (!confirm("Stop this test? Everything finished so far is kept.")) return;
      stop.disabled = true;
      await api(`/api/run/${enc(jobId)}/cancel`, {});
    };
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
      <span class="muted small"><b>${esc(testName(ov.run))}</b> · started ${esc(when(d.manifest.started_at || d.manifest.finished_at))}${rulesName(d.manifest.pack) ? " · " + esc(rulesName(d.manifest.pack)) : ""} · ${h.memos} memos${sizeWords(ov.run) ? ` (${esc(sizeWords(ov.run))})` : ""}</span></div>
    <section class="card stack mid" style="padding:32px 36px">${verdictBadge(dec.verdict, true)}
      <h1 style="font-size:34px;max-width:900px">${esc(lead)}</h1>
      <p class="muted" style="font-size:17px;max-width:900px">${esc(support)}</p>
      ${p && p.complete === false && p.planned ? `<p class="note-box amber small">The AI reviewers have answered ${p.answered} of ${p.planned} memos so far; the rest are being reviewed now. Reload this page in a few minutes for the full second opinion.</p>` : ""}
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
      <div class="stack tight"><p class="muted small"><b>${esc(testName(ov.run))}</b> · started ${esc(when(ov.run.started_at || ov.run.finished_at))}</p><h1>Review the flagged memos</h1>
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
  // Findings on the same sentence share one highlight that carries all their numbers.
  let html = esc(text);
  const marks = [];
  cards.forEach((c, i) => {
    const s = c.sentence && esc(c.sentence);
    if (!s) return;
    const same = marks.find((m) => m.s === s);
    if (same) { same.cards.push([c.card_id, i + 1]); return; }
    if (!html.includes(s)) return;
    marks.push({ s, cards: [[c.card_id, i + 1]] });
    html = html.replace(s, `\u0000${marks.length - 1}\u0000`);
  });
  marks.forEach((m, k) => {
    html = html.replace(`\u0000${k}\u0000`, `<mark data-cards="${m.cards.map((x) => x[0]).join(" ")}"><sup>${m.cards.map((x) => x[1]).join(",")}</sup>${m.s}</mark>`);
  });
  return html.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/^\s*[*-]\s{1,4}/gm, "• ").replace(/^#{1,4}\s*(.+)$/gm, "<b>$1</b>");
}

function appNav(id, memos, current, status) {
  // Every application in the test, by lane, to move between them. status(m) gives a short tag.
  const groups = ["red", "amber", "green"].map((lane) => {
    const list = memos.filter((m) => m.lane === lane);
    if (!list.length) return "";
    return `<div class="navgroup"><p class="eyebrow row" style="gap:6px"><span class="lane-dot small ld-${lane}" aria-hidden="true"></span>${LANE[lane][0]} <span class="muted">${list.filter((m) => m.reviewed).length}/${list.length}</span></p>
      ${list.map((m) => { const tag = status(m); return `<a class="navitem${m.memo === current ? " on" : ""}" href="#/review/${enc(id)}/memo/${enc(m.memo)}"${m.memo === current ? ' aria-current="page"' : ""}>
        <span class="grow">${esc(m.case)} <span class="muted">· ${m.repeat + 1}</span></span>${tag}</a>`; }).join("")}</div>`;
  }).join("");
  return `<nav class="appnav hide-md" aria-label="Applications"><p class="small" style="font-weight:700;margin-bottom:8px">Applications</p>${groups}</nav>`;
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
  // The coach prepares a note on every finding as the memo opens; the note for an answer
  // opens under the finding as soon as it is given. The first click on each finding is kept,
  // so the review shows what the reviewer thought before any note was on screen.
  const coach = { session: null, notes: null, reading: m.cards.length > 0, unavailable: "", turns: [], busy: false, error: "", draft: "" };
  const firstClick = {};

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
  const tick = (x) => (x.reviewed ? `<span class="navtick" title="Reviewed">${ICON.check}</span>` : "");
  main.innerHTML = `${appNav(id, q.memos, memo, tick)}<article class="card stack mid" style="padding:32px 36px">
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
    const challenged = new Set(coach.turns.flatMap((t) => t.challenges.flatMap((c) => [c.card_id, ...(c.also_card_ids || [])])).filter(Boolean));
    const cards = m.cards.map((c, i) => {
      const st = state[c.card_id];
      const btn = (a, words) => `<button type="button" data-a="${a}" aria-pressed="${st.action === a}">${words}</button>`;
      return `<section class="finding${st.action ? " answered" : ""}" data-card="${c.card_id}">
        <div class="row" style="gap:10px"><span class="dot num">${i + 1}</span><h3>${esc(c.kind)}</h3></div>
        ${challenged.has(c.card_id) ? '<p class="tiny" style="color:var(--accent);font-weight:600">The coach asked about this answer.</p>' : ""}
        <p>${esc(c.problem)}</p>
        ${c.sentence && !c.span ? `<p class="small muted" style="border-left:3px solid var(--line);padding-left:10px">“${esc(c.sentence)}”</p>` : ""}
        ${c.evidence ? `<div class="proof"><span class="eyebrow">${c.known_answer ? "Proof" : "Why the reviewers think so"}</span><span>${esc(c.evidence)}</span></div>` : ""}
        <p class="tiny muted">${c.known_answer ? "Found by the rule check, which knows the right answer." : "Found by the AI reviewers."}</p>
        <p style="font-weight:700;margin-top:4px">Is the memo wrong here?</p>
        <div class="answers">${btn("confirm", "Yes, it’s wrong")}${btn("dispute", "No, the memo is right")}${btn("needs_more", "Not sure")}</div>
        ${st.action === "confirm" ? `<p class="note-box small">Noted. This mistake goes into the feedback pack.</p>
          <label class="small" for="fix-${c.card_id}"><b>${c.sentence ? "How should this sentence read?" : "What should the memo say?"}</b> <span class="muted">Optional: with it, the model team gets a corrected memo. One correction covers every finding on the same sentence.</span></label>
          ${c.sentence ? `<p class="tiny muted" style="border-left:3px solid var(--line);padding-left:10px">Now: “${esc(c.sentence)}”</p>` : ""}
          <textarea id="fix-${c.card_id}" data-fix placeholder="Write the corrected wording">${esc(st.correction || "")}</textarea>` : ""}
        ${st.action === "dispute" ? `<p class="small" style="font-weight:600">Why is the memo right?</p>
          <div class="answers chips">${Object.entries(REASON).map(([k, w]) => `<button type="button" data-r="${k}" aria-pressed="${st.reason === k}">${esc(w)}</button>`).join("")}</div>` : ""}
        ${st.action === "needs_more" ? '<p class="note-box amber small">Fine. A colleague from model risk will decide.</p>' : ""}
        ${st.action ? coachNote(c.card_id, st.action) : ""}
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
    const num = (cid) => m.cards.findIndex((c) => c.card_id === cid) + 1;
    const thread = coach.turns.map((t) => `${t.message ? `<div class="bubble me"><span class="eyebrow">You</span><p>${esc(t.message)}</p></div>` : ""}
      <div class="bubble coachsays"><span class="eyebrow">Coach</span>
        ${t.challenges.length ? t.challenges.map((c) => `<div class="challenge">
          ${c.card_id ? `<a href="#" data-goto="${c.card_id}" class="small" style="font-weight:700">Finding ${[c.finding, ...(c.also || [])].join(" and ")}</a>` : '<span class="small" style="font-weight:700">Not in the findings</span>'}
          <p>${esc(c.question)}</p>${c.evidence ? `<p class="tiny muted">${esc(c.evidence)}</p>` : ""}</div>`).join("") : ""}
        ${t.reply ? `<p class="small">${esc(t.reply)}</p>` : ""}
        ${!t.challenges.length ? '<p class="small" style="color:var(--green);font-weight:600">No questions about your answers.</p>' : ""}</div>`).join("");
    const coachBox = m.cards.length ? `<section class="coach stack mid">
        <div class="stack tight"><h3>Coach</h3><p class="tiny muted">A second opinion that points at the evidence; the decision is yours. It does not know the right answers, and it writes a note on every answer, so a note is not a sign the answer is wrong.</p></div>
        ${coach.reading ? '<div class="row small"><span class="spinner" style="width:20px;height:20px" aria-hidden="true"></span>Reading the memo and the case file. Its notes open under each finding as you answer.</div>'
          : coach.unavailable ? `<p class="small muted">The coach is not available for this memo (${esc(coach.unavailable)}). You can still answer and save.</p>`
          : '<p class="small muted">Ready. Its note opens under each finding as you answer it.</p>'}
        ${thread}
        ${coach.busy ? '<div class="row small"><span class="spinner" style="width:20px;height:20px" aria-hidden="true"></span>The coach is reading your answers…</div>' : ""}
        ${coach.error ? `<p class="error small">${esc(coach.error)}</p>` : ""}
        ${!coach.turns.length && !coach.busy ? `<button class="btn small" id="coach-ask" style="align-self:flex-start" ${answered() < m.cards.length ? "disabled" : ""}>Check everything with the coach</button>${answered() < m.cards.length ? '<p class="tiny muted">Optional. Answer every finding first; the coach then looks at your answers together.</p>' : ""}` : ""}
        ${coach.turns.length && !coach.busy ? `<label class="small visually-hidden" for="coach-msg">Reply to the coach</label>
          <textarea id="coach-msg" placeholder="Reply to the coach, or change your answers above">${esc(coach.draft)}</textarea>
          <div class="row" style="gap:8px"><button class="btn small" id="coach-send">Send</button><button class="btn small" id="coach-again">Check my answers again</button></div>` : ""}
      </section>` : "";
    side.innerHTML = `<div class="row" style="justify-content:space-between;align-items:baseline">
        <h2>${m.cards.length ? plural(m.cards.length, "thing") + " to check" : "Nothing flagged"}</h2>
        ${m.cards.length ? `<span class="small muted">${answered()} of ${m.cards.length} answered</span>` : ""}</div>
      ${cards}${none}
      ${raised.length ? `<div class="note-box blue small">${plural(raised.length, "extra problem")} added: ${raised.map((r) => esc(r.problem)).join("; ")}</div>` : ""}
      ${raiseForm}
      ${m.cards.length && !showRaise ? `<button class="btn dashed" id="more">${ICON.plus}I found another problem</button>` : ""}
      ${coachBox}
      ${editName ? `<div class="stack tight"><label class="small" for="who-in"><b>Your name</b> <span class="muted">(recorded with your answers)</span></label><input type="text" id="who-in" value="${esc(who)}"></div>`
        : `<p class="small muted">Reviewing as ${esc(who)} · <a href="#" id="change">Change</a></p>`}
      <div class="row" style="gap:10px;padding-top:8px"><button class="btn primary large grow" id="save">Save and open the next memo${ICON.arrow}</button>
        <a class="btn large" href="${nextHref}">Skip</a></div><p id="msg" class="error small"></p>`;
    side.querySelectorAll("[data-card]").forEach((el) => {
      const cid = el.dataset.card;
      el.querySelectorAll("[data-a]").forEach((b) => (b.onclick = () => {
        if (!firstClick[cid]) firstClick[cid] = { card_id: cid, action: b.dataset.a, at: new Date().toISOString(), note_ready: !!coach.notes };
        state[cid] = { ...state[cid], action: b.dataset.a };
        draw();
      }));
      el.querySelectorAll("[data-r]").forEach((b) => (b.onclick = () => { state[cid].reason = b.dataset.r; draw(); }));
      const fix = el.querySelector("[data-fix]");
      if (fix) fix.oninput = () => (state[cid].correction = fix.value);
      const mk = () => document.querySelector(`mark[data-cards~="${cid}"]`);
      el.onmouseenter = () => { const m = mk(); if (m) m.classList.add("on"); };
      el.onmouseleave = () => { const m = mk(); if (m) m.classList.remove("on"); };
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
    on("#coach-ask", () => ask());
    on("#coach-again", () => ask());
    on("#coach-send", () => { const t = side.querySelector("#coach-msg").value.trim(); if (t) ask(t); });
    const draft = side.querySelector("#coach-msg");
    if (draft) draft.oninput = () => (coach.draft = draft.value);
    side.querySelectorAll("[data-goto]").forEach((a) => (a.onclick = (ev) => {
      ev.preventDefault();
      const el = side.querySelector(`[data-card="${a.dataset.goto}"]`);
      if (el) { el.scrollIntoView({ behavior: "smooth", block: "center" }); el.classList.add("flash"); setTimeout(() => el.classList.remove("flash"), 1600); }
    }));
    void num;
  };
  prepareCoach();

  const NOTE_FOR = { confirm: "if_wrong", dispute: "if_right", needs_more: "if_unsure" };
  function coachNote(cid, action) {
    if (coach.reading) return '<div class="coachnote tiny muted"><span class="eyebrow">Coach</span>Still reading this memo; the note opens here in a moment.</div>';
    const n = coach.notes && coach.notes[cid];
    if (!n || !(n.evidence || n[NOTE_FOR[action]])) return "";
    return `<div class="coachnote" role="status"><span class="eyebrow">Coach</span>
      ${n.evidence ? `<p class="small">${esc(n.evidence)}</p>` : ""}
      ${n[NOTE_FOR[action]] ? `<p class="small" style="font-weight:600">${esc(n[NOTE_FOR[action]])}</p>` : ""}</div>`;
  }

  // Prepare the notes now, then the next memo's, so they are ready when it opens.
  async function prepareCoach() {
    if (!m.cards.length) return;
    try {
      const r = await api(`/api/review/${enc(id)}/coach/prepare`, { memo });
      coach.session = coach.session || r.session_id;
      coach.notes = r.notes || {};
    } catch (e) { coach.unavailable = e.message; }
    coach.reading = false;
    if (side.isConnected) draw();
    if (next && next.memo !== memo) api(`/api/review/${enc(id)}/coach/prepare`, { memo: next.memo }).catch(() => {});
  }

  const verdictsNow = () => m.cards.map((c) => ({ card_id: c.card_id, ...state[c.card_id] }));
  async function ask(message) {
    coach.busy = true; coach.error = ""; draw();
    try {
      const r = await api(`/api/review/${enc(id)}/coach`, { memo, session_id: coach.session, verdicts: verdictsNow(), raised, message: message || null });
      coach.session = r.session_id;
      coach.turns.push({ message: message || null, challenges: r.challenges, reply: r.reply });
      if (message) coach.draft = "";
    } catch (e) { coach.error = `The coach could not answer: ${e.message}`; }
    coach.busy = false; draw();
    return coach.turns.length ? coach.turns[coach.turns.length - 1] : null;
  }

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
        verdicts: verdictsNow(), coach_session: coach.session, first_answers: Object.values(firstClick),
      });
      location.hash = nextHref;
    } catch (e) { msg.textContent = e.message; side.querySelector("#save").disabled = false; }
  }
  draw();
}

// ----------------------------------------------------------------- improve

async function viewImprove(id) {
  const [q, adj, ov, fb, d] = await Promise.all([
    api(`/api/review/${enc(id)}`), api(`/api/review/${enc(id)}/adjudication`), overview(id),
    api(`/api/review/${enc(id)}/feedback/manifest.json`).catch(() => null), api(`/api/runs/${enc(id)}`),
  ]);
  const d_model = (d.manifest.sut || {}).model_id || "the assistant's model";
  const ruling = new Set(adj.map((x) => x.memo));
  const awaiting = new Set((fb && fb.memos_awaiting_correction) || []);
  const improveTag = (x) => (ruling.has(x.memo) ? '<span class="badge b-amber navbadge">Ruling</span>'
    : awaiting.has(x.memo) ? '<span class="badge b-blue navbadge">Correct</span>'
    : x.reviewed ? `<span class="navtick" title="Reviewed">${ICON.check}</span>` : "");
  const fixable = (d.recommendations || []).find((r) => r.cause === "miscalculated" || r.cause === "misread_threshold") || null;
  const ev = q.evaluator || { panel: {}, rule_checks: {} };
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
    ${appNav(id, q.memos, null, improveTag)}
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
      ${fb && fb.handover ? `<section class="card stack mid"><div class="row" style="gap:12px"><span class="dot big done">${ICON.check}</span><h2>Hand over for fine-tuning</h2></div>
        <p class="small muted">One zip for the engineering team that fine-tunes the assistant: the corrected memos in training formats (${fb.handover.counts.sft_train} for training, ${fb.handover.counts.sft_validation} for validation, ${fb.handover.counts.dpo} preference pairs), the finding labels, a starting LoRA configuration for ${esc(d_model)}, and a README that says where every row came from and how the tuned model will be accepted: a re-test on new cases.</p>
        <a class="btn primary" href="/api/review/${enc(id)}/handover.zip" style="align-self:flex-start">${ICON.down}Download the fine-tuning handover (zip)</a></section>` : ""}
      <section class="card stack mid"><div class="row" style="gap:12px"><span class="dot big ${fb ? "fill" : "todo"}">3</span><h2>Test a change on new cases</h2></div>
        <p class="small muted">Prove a change helps before anyone relies on it. We generate cases the assistant has never seen, run the assistant as it is and with the change on those same cases, and put the two side by side.</p>
        ${fixable ? `<div class="note-box blue stack tight" style="gap:6px"><b>${esc(fixable.title)}</b><span class="small">${esc(fixable.action)}</span><span class="small muted">Your team can make this change today, without the vendor. Could fix up to ${plural(fixable.addresses.briefings, "memo")} in this test.</span></div>
          <button class="btn primary" id="retest" style="align-self:flex-start">Test this change on new cases</button><span class="small error" id="rmsg"></span>` : ""}
        <p class="small muted">A fine-tuned model from the engineering team is tested the same way: <a href="#/new">start a test</a> with <b>Generate new cases</b>, then compare it with the current model in <a href="#/history">Earlier tests</a>.</p></section>
    </div>
    <aside class="stack hide-sm" style="width:320px;flex-shrink:0;margin-top:8px;gap:16px"><div class="card stack" style="gap:16px"><h2 style="font-size:18px">How reliable was the review?</h2>
      ${s.known_answer_verdicts ? `<div class="stack" style="gap:2px"><span style="font-size:30px;font-weight:700">${pct(s.agree_with_known_answer, s.known_answer_verdicts)}%</span><span class="small muted">of answers matched the known right answer (${s.agree_with_known_answer} of ${s.known_answer_verdicts})</span></div>
        <div class="stack" style="gap:2px;padding-top:14px;border-top:1px solid var(--line-2)"><span style="font-size:30px;font-weight:700${s.automation_bias_memos ? ";color:var(--red)" : ""}">${s.automation_bias_memos}</span><span class="small muted">${s.automation_bias_memos === 1 ? "memo was" : "memos were"} approved although ${s.automation_bias_memos === 1 ? "it" : "they"} had a known mistake. A high number means people trust the machine too much.</span></div>
        ${times ? `<div class="stack tight" style="padding-top:14px;border-top:1px solid var(--line-2)"><span class="small" style="font-weight:600">Time spent</span><ul class="small muted" style="margin:0;padding-left:18px">${times}</ul></div>` : ""}
        ${s.coach ? `<div class="stack tight" style="padding-top:14px;border-top:1px solid var(--line-2)"><span class="small" style="font-weight:600">The coach</span>
          <p class="small muted">Used on ${plural(s.coach.memos, "memo")}; ${plural(s.coach.answers_changed, "answer")} changed after its questions.</p>
          ${s.coach.known_answer_findings ? `<p class="small">Agreement with the known answers: <b>${pct(s.coach.agreed_before_coach, s.coach.known_answer_findings)}%</b> before the coach, <b>${pct(s.coach.agreed_after_coach, s.coach.known_answer_findings)}%</b> after.</p>` : ""}</div>` : ""}`
        : '<p class="small muted">Shown once memos have been reviewed. Every test case has a known right answer, so each answer can be checked.</p>'}
    </div>
    <div class="card stack" style="gap:14px"><h2 style="font-size:18px">How good are the checks and the AI reviewers?</h2>
      ${ev.panel.memos_with_a_rule_failure != null ? `<p class="small"><b>${ev.panel.flagged_with_a_rule_failure} of ${ev.panel.memos_with_a_rule_failure}</b> <span class="muted">memos with a known mistake were flagged by the AI reviewers.</span></p>
      <p class="small"><b>${ev.panel.flagged_passing_every_rule} of ${ev.panel.memos_passing_every_rule}</b> <span class="muted">memos that pass every rule check were flagged anyway: either a problem the rules miss or a false alarm.</span></p>
      <p class="small">${ev.panel.flags_on_rule_clean_memos_reviewed ? `<b>${ev.panel.problems_the_rules_missed}</b> <span class="muted">real problems the rules missed,</span> <b>${ev.panel.false_alarms}</b> <span class="muted">false alarms, from the ${ev.panel.flags_on_rule_clean_memos_reviewed} of those a person has checked.</span>` : `<span class="muted">Review the memos in <a href="#/review/${enc(id)}">Worth a look</a> to tell the two apart.</span>`}</p>` : '<p class="small muted">Shown for tests with the AI reviewers’ second opinion.</p>'}
      ${ev.rule_checks.findings_settled ? `<p class="small" style="padding-top:12px;border-top:1px solid var(--line-2)"><b>${ev.rule_checks.shown_wrong}</b> <span class="muted">of ${ev.rule_checks.findings_settled} rule-check findings shown to be wrong by a reviewer and model risk.</span></p>` : ""}
    </div>
    </aside>
  </div>`;
  document.querySelectorAll("[data-v]").forEach((tr) => tr.querySelectorAll("[data-d]").forEach((b) => (b.onclick = async () => {
    b.disabled = true;
    await api(`/api/review/${enc(id)}/adjudicate`, { verdict_id: tr.dataset.v, decision: b.dataset.d, by: reviewer.get() || "model-risk" });
    viewImprove(id);
  })));
  const rt = document.getElementById("retest");
  if (rt) rt.onclick = async () => {
    rt.disabled = true;
    try { const j = await api("/api/retest", { from_run: id, setup: "with_figures" }); location.hash = `#/retest/${enc(j.job_id)}`; }
    catch (e) { document.getElementById("rmsg").textContent = e.message; rt.disabled = false; }
  };
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

// ----------------------------------------------------------------- re-test a change

async function viewRetest(jobId) {
  const ov = await overview();
  renderSteps(ov, "improve");
  page("narrow");
  const tick = async () => {
    if (!location.hash.startsWith("#/retest/")) return;
    let j;
    try { j = await api(`/api/run/${enc(jobId)}`); } catch (e) {
      $view.innerHTML = `<div class="card stack mid"><h2>This re-test is no longer tracked</h2><p class="muted">The server was restarted. Finished tests are listed under Earlier tests.</p><a class="btn" href="#/history" style="align-self:flex-start">Earlier tests</a></div>`;
      return;
    }
    const order = ["cases", "before", "after", "compare", "done"];
    const at = order.indexOf(j.phase);
    const state = (k) => (j.status === "error" && order.indexOf(k) === at ? "todo" : order.indexOf(k) < at || j.phase === "done" ? "done" : order.indexOf(k) === at ? "now" : "todo");
    const line = (k, title, detail) => { const st = state(k); return `<li class="row" style="align-items:flex-start;padding:18px 0;border-bottom:1px solid var(--line-2)">
      ${st === "done" ? `<span class="dot big done">${ICON.check}</span>` : st === "now" ? '<span class="spinner" aria-hidden="true"></span>' : '<span class="dot big todo"></span>'}
      <span class="stack tight grow"><span style="font-size:17px;font-weight:600${st === "todo" ? ";color:var(--ink-2)" : ""}">${title}</span>
      ${st === "now" && j.total ? `<span class="bar"><span style="width:${pct(j.done, j.total)}%"></span></span>` : ""}
      <span class="small muted">${detail}</span></span></li>`; };
    const words = WORDS_VERDICT[j.verdict];
    let foot = j.cancel && j.status === "running" ? `<div class="row"><span class="spinner" aria-hidden="true"></span><p>Stopping.</p></div>`
      : `<button class="btn" id="stop" style="align-self:flex-start">Stop</button>`;
    if (j.status === "done" && j.before && j.after) foot = `<div class="note-box ${j.verdict === "ACCEPT" ? "" : j.verdict === "REJECT" ? "red" : "amber"}"><p><b>${esc(words ? words[0] : j.verdict)}</b></p></div>
      <a class="btn primary large" href="#/compare/${enc(j.before)}/${enc(j.after)}" style="align-self:flex-start">See the comparison${ICON.arrow}</a>`;
    if (j.status === "cancelled") foot = "<p>Stopped. What finished is kept under Earlier tests.</p>";
    if (j.status === "error") foot = `<p class="error">The re-test stopped with an error: ${esc(j.error)}</p>`;
    $view.innerHTML = `<div class="stack" style="gap:28px">
      <div class="stack tight"><h1>Testing the change on new cases</h1>
        <p class="muted" style="font-size:17px">${esc(SETUP[j.setup] || j.setup)}, against the assistant as it is today.</p></div>
      <ol class="card" style="list-style:none;padding:8px 28px;margin:0">
        ${line("cases", "New cases generated", j.seed ? `Set #${j.seed} from your credit policy, by the <a href="/sdd/" target="_blank" rel="noopener">Synthetic Data Designer</a>. ${j.shared_with_other_packs ? `${j.shared_with_other_packs} match earlier cases.` : "None appears in an earlier test."}` : "Cases the assistant has never seen")}
        ${line("before", "The assistant as it is today", state("before") === "now" ? `${j.done} of ${j.total} memos` : "Writes a memo for every case; each is checked against the rules")}
        ${line("after", "The assistant with the change", state("after") === "now" ? `${j.done} of ${j.total} memos` : "The same cases, with the figures your systems calculate")}
        ${line("compare", "The two side by side", "Case by case: did the change help, and did anything get worse?")}
      </ol>${foot}</div>`;
    const stop = document.getElementById("stop");
    if (stop) stop.onclick = async () => { if (confirm("Stop this re-test?")) { stop.disabled = true; await api(`/api/run/${enc(jobId)}/cancel`, {}); } };
    if (j.status === "running") pollTimer = setTimeout(tick, 2000);
  };
  tick();
}

// ----------------------------------------------------------------- earlier tests

async function viewHistory() {
  const [runs, ov] = await Promise.all([api("/api/runs"), overview(null, true)]);
  const open = {};
  (ov.to_review || []).forEach((t) => (open[t.run_id] = t));
  renderSteps(ov, "history");
  page("");
  const list = runs.filter((r) => r.sealed && r.transcripts).sort((a, b) => (b.finished_at || "").localeCompare(a.finished_at || ""));
  $view.innerHTML = `<div class="stack">
    <a class="link back" href="#/">${ICON.back}Home</a>
    <div class="row wrap" style="align-items:flex-end;gap:24px;margin-top:-8px"><div class="stack tight grow"><h1>Earlier tests</h1>
      <p class="muted" style="font-size:17px">Every test is sealed and can be re-checked at any time. Tick two to compare them.</p></div>
      <button class="btn primary" id="cmp" disabled>Compare the 2 ticked tests</button></div>
    <div class="card" style="padding:8px 20px"><table><thead><tr><th style="width:44px"><span class="visually-hidden">Compare</span></th><th>Test</th><th>Test cases</th><th>Result</th><th>Memos with a mistake</th><th class="hide-sm">Flagged memos checked</th><th><span class="visually-hidden">Open</span></th></tr></thead><tbody>
      ${list.map((r) => `<tr><td><input type="checkbox" data-run="${esc(r.run_id)}" aria-label="Compare ${esc(testLabel(r))}" style="width:20px;height:20px;accent-color:var(--accent)"></td>
        <td style="white-space:nowrap"><b>${esc(testName(r))}</b>${ov.run && ov.run.run_id === r.run_id ? ' <span class="tiny muted">Latest</span>' : ""}<div class="small muted">${esc(when(r.started_at || r.finished_at))}</div></td>
        <td>${esc(packName(r.pack))}<div class="tiny muted">${esc(sizeWords(r))}</div></td><td>${verdictBadge(r.verdict)}</td><td>${r.memos_with_error} of ${r.memos}</td>
        <td class="hide-sm">${open[r.run_id] ? `${open[r.run_id].flagged_checked} of ${open[r.run_id].flagged} · <a class="link" href="#/review/${enc(r.run_id)}">${open[r.run_id].flagged_checked ? "Continue" : "Start"}</a>` : '<span style="color:var(--green);font-weight:600">All checked</span>'}</td>
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

const WORDS_VERDICT = {
  ACCEPT: ["The change helped, and nothing got worse"],
  REJECT: ["The change made something worse"],
  INCONCLUSIVE: ["Something may have got worse. Not safe to accept yet"],
  "NO EFFECT": ["No clear difference"],
};
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
      <h1 style="font-size:30px">${esc(when(c.before.started_at || c.before.finished_at))} compared with ${esc(when(c.after.started_at || c.after.finished_at))}</h1>
      ${c.changed.filter((x) => x.what === "assistant setup").map((x) => `<p><b>The change:</b> ${esc(SETUP[x.before] || x.before)} → ${esc(SETUP[x.after] || x.after)}.</p>`).join("")}
      ${c.changed.some((x) => x.what === "pack") ? "" : `<p class="muted">Both on the same cases${packSeed(c.after.pack) ? `: new set #${packSeed(c.after.pack)}, never used before` : ""}, compared case by case.</p>`}
      ${c.changed.filter((x) => !["assistant setup", "engine commit"].includes(x.what)).length ? `<p class="muted small">Also different between the two: ${c.changed.filter((x) => !["assistant setup", "engine commit"].includes(x.what)).map((x) => esc(x.what)).join(", ")}.</p>` : ""}
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
  document.querySelectorAll("dialog.modal").forEach((d) => d.remove());  // a window left open on the page before
  const parts = location.hash.replace(/^#\/?/, "").split("/").map(decodeURIComponent);
  try {
    if (!parts[0]) return await viewHome();
    if (parts[0] === "new") return await viewNew(parts[1]);
    if (parts[0] === "cases") return await viewCases();
    if (parts[0] === "running" && parts[1]) return await viewRunning(parts[1]);
    if (parts[0] === "result" && parts[1]) return await viewResult(parts[1]);
    if (parts[0] === "review" && parts[1] && parts[2] === "memo") return await viewMemo(parts[1], parts.slice(3).join("/"));
    if (parts[0] === "review" && parts[1]) return await viewQueue(parts[1]);
    if (parts[0] === "improve" && parts[1]) return await viewImprove(parts[1]);
    if (parts[0] === "retest" && parts[1]) return await viewRetest(parts[1]);
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
