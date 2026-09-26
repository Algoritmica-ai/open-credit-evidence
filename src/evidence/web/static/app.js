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
  const usable = packs.filter((p) => !p.error && p.items && (!packSeed(p.pack_id) || !p.used_in_tests || p.pack_id === preselect));
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
      <p class="muted" style="font-size:17px">Answer three questions. The test then runs by itself; a small test takes a few minutes.</p></div>
    <fieldset><legend>1. Which assistant are you testing?</legend>
      <label for="assistant" class="small muted">Assistant</label>
      <select id="assistant"><option>Credit memo assistant (${esc(a.model)})</option></select>
      <p class="tiny muted">${a.where === "on-prem" ? "Runs on your own servers." : "Runs on NVIDIA's cloud."}</p></fieldset>
    <fieldset><legend>2. Which rules must its memos follow?</legend><div class="stack tight" id="rules"></div></fieldset>
    <fieldset><legend>3. Which test cases?</legend><div class="stack tight" id="cases"></div>
      <div class="row wrap" style="gap:12px"><button class="btn" id="fresh">${ICON.plus}Generate new cases</button>
        <span class="small muted" id="freshmsg">Cases the assistant has never seen, made from your credit policy. You choose how many, and how many times each is run.</span></div>
      <div class="note-box row wrap" style="gap:12px"><p class="grow" id="nmemos" style="font-weight:600"></p><button class="btn small" id="resize">Change</button></div></fieldset>
    <p class="small muted">Every memo is checked against the rules and then gets a second opinion from three AI reviewers: one reads it, one challenges it against the case file, one decides. Their opinion sorts what a person should check first.</p>
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
  const size = { cases: 0, repeats: Math.min(3, maxRepeats) };
  const drawSize = (reset) => {
    const p = (byJ[chosenJ] || []).find((x) => x.pack_id === chosenPack);
    const most = Math.min(p ? p.items : 0, maxItems);
    if (reset || !size.cases) size.cases = most;
    size.cases = Math.max(Math.min(1, most), Math.min(most, size.cases));
    document.getElementById("nmemos").textContent = `This test: ${plural(size.cases, "case")}, each run ${size.repeats === 1 ? "once" : size.repeats === 2 ? "twice" : size.repeats + " times"} = ${plural(size.cases * size.repeats, "memo")}`;
  };
  drawRules();
  drawCases();
  document.getElementById("resize").onclick = () => {
    const p = (byJ[chosenJ] || []).find((x) => x.pack_id === chosenPack);
    if (p) sizeDialog(Math.min(p.items, maxItems), size, maxRepeats, () => drawSize(false));
  };
  document.getElementById("fresh").onclick = () => {
    const from = chosenPack || ((byJ[chosenJ] || [])[0] || {}).pack_id;
    if (!from) return;
    const times = size.repeats;
    generateCases(from, (f, fresh, times) => {
      (byJ[chosenJ] = byJ[chosenJ] || []).unshift(fresh);
      chosenPack = f.pack_id;
      size.repeats = times;
      drawCases();
      document.getElementById("freshmsg").innerHTML = `${f.items} new cases (set #${f.seed}) made in ${f.seconds} s and chosen, each run ${times === 1 ? "once" : times === 2 ? "twice" : times + " times"}. ${f.shared_with_other_packs ? `<span class="error">${f.shared_with_other_packs} match earlier cases.</span>` : "None of them appears in an earlier test."}`;
    }, times, maxRepeats);
  };
  document.getElementById("start").onclick = async (ev) => {
    const pack = (document.querySelector("input[name=cases]:checked") || {}).value;
    if (!pack) return;
    ev.target.disabled = true;
    try {
      const j = await api("/api/run", { pack, repeats: size.repeats, limit: size.cases, judge: true, setup: "as_is", panel: true });
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

// "Change": how many cases of the chosen set to use, and how many times each is run.
function sizeDialog(most, size, maxRepeats, done) {
  const dlg = document.createElement("dialog");
  dlg.className = "modal";
  dlg.setAttribute("aria-labelledby", "size-title");
  dlg.innerHTML = `<form method="dialog" class="stack mid">
      <h2 id="size-title">Test size</h2>
      <div class="stack tight"><label class="small" for="size-n"><b>Cases to use</b></label>
        <input type="number" id="size-n" min="1" max="${most}" step="1" value="${size.cases}" style="width:120px">
        <span class="tiny muted">Up to ${plural(most, "case")} in this set.</span></div>
      <div class="stack tight"><label class="small" for="size-r"><b>Times each case is run</b></label>
        <select id="size-r" style="width:160px">${[1, 2, 3, 4, 5].filter((n) => n <= maxRepeats).map((n) => `<option value="${n}" ${n === size.repeats ? "selected" : ""}>${n === 1 ? "Once" : n === 2 ? "Twice" : n + " times"}</option>`).join("")}</select>
        <span class="tiny muted">The assistant can write a different memo each time for the same case, so running it more than once shows how consistent it is.</span></div>
      <p class="small" id="size-total" style="font-weight:600"></p>
      <div class="row" style="gap:10px"><button type="button" class="btn primary" id="size-ok">Done</button><button type="button" class="btn" id="size-cancel">Cancel</button></div></form>`;
  document.body.appendChild(dlg);
  const n = dlg.querySelector("#size-n"), r = dlg.querySelector("#size-r");
  const total = () => (dlg.querySelector("#size-total").textContent = `= ${plural((Math.round(+n.value) || 0) * +r.value, "memo")}`);
  n.oninput = total; r.oninput = total; total();
  dlg.addEventListener("close", () => dlg.remove());
  dlg.querySelector("#size-cancel").onclick = () => dlg.close();
  dlg.querySelector("#size-ok").onclick = () => {
    const v = Math.round(+n.value);
    if (!(v >= 1 && v <= most)) { n.focus(); return; }
    size.cases = v; size.repeats = +r.value;
    dlg.close();
    done();
  };
  dlg.showModal();
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
    <td>${p.used_in_tests ? plural(p.used_in_tests, "test") : '<span class="muted">Not yet</span>'}</td>
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
    <section class="card" style="padding:8px 20px"><table><thead><tr><th>Case set</th><th>Cases</th><th>Rules</th><th>Bank figures</th><th>Used in</th><th>Made</th><th><span class="visually-hidden">Use</span></th></tr></thead>
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
  // Anchoring: the seal's fingerprint in the Bitcoin blockchain, through OpenTimestamps
  const MILESTONE = { test: "The test", "feedback-pack": "The feedback pack", manual: "Anchored by hand" };
  const anchorLine = (a) => a.status === "confirmed"
    ? `Anchored in Bitcoin block <b>${Number(a.bitcoin.height).toLocaleString("en-GB")}</b>${a.bitcoin.time ? `, ${esc(when(a.bitcoin.time))}` : ""}`
    : a.status === "pending" ? `Waiting for Bitcoin since ${esc(when(a.at))}: usually a few hours`
    : `Not yet sent: the calendars could not be reached (${esc(when(a.at))}); tried again automatically`;
  const anchors = d.anchors || [];
  const lastAnchor = anchors[anchors.length - 1];
  const anchorBadge = lastAnchor ? `<p class="small muted row" style="gap:6px">${ICON.lock}${lastAnchor.status === "confirmed" ? `Sealed and anchored in Bitcoin block ${Number(lastAnchor.bitcoin.height).toLocaleString("en-GB")}` : lastAnchor.status === "pending" ? "Sealed; anchoring in Bitcoin (usually a few hours)" : "Sealed; anchoring will be tried again"}</p>` : "";
  const anchorBox = `<div class="stack tight"><b>Anchored outside our control</b>
      <p class="small muted">The seal's fingerprint (never the data) is written into the Bitcoin blockchain through OpenTimestamps, free of charge. After that, nobody, not even us, can change a memo or a check result without it showing, and anyone can check it with open-source tools.</p>
      ${anchors.length ? `<ul class="small" style="margin:0;padding-left:18px">${anchors.map((a) => `<li>${esc(MILESTONE[a.what] || a.what)}: ${anchorLine(a)}</li>`).join("")}</ul>`
        : d.anchoring ? '<p class="small">Not anchored yet. <button class="btn small" id="anchor-now">Anchor now</button></p>'
        : '<p class="small muted">Anchoring is switched off on this server (EVIDENCE_ANCHOR=off).</p>'}</div>`;
  // Same case, different result: each case ran more than once; did its memos agree?
  const repeats = d.manifest.repeats || 1;
  const agree = Object.entries((d.summary && d.summary.repeat_agreement) || {}).filter(([k]) => CHECK[k]);
  const flipping = [...new Set(agree.flatMap(([, a]) => a.flipping_items || []))];
  const cases = agree.length ? agree[0][1].items : 0;
  const caseName = (item) => (item.split(":")[2] || item);
  const consistency = repeats < 2 ? `<section class="card stack tight"><h2 style="font-size:21px">Same case, different result</h2>
      <p class="muted small">Each case ran once, so this test cannot show whether the assistant answers the same way every time. Run each case at least twice to see it.</p></section>`
    : `<section class="card stack mid"><h2 style="font-size:21px">Same case, different result</h2>
      <p style="font-weight:600">${flipping.length
        ? `In ${flipping.length} of ${cases} cases, the assistant's memos did not agree: a check passed in one run and failed in another.`
        : `In all ${cases} cases, every run of a case got the same result on every check.`}</p>
      <p class="small muted">Each case ran ${repeats === 2 ? "twice" : `${repeats} times`}, each time as a fresh request. The assistant writes a different memo each time, so a mistake can show up in one run and not the next. The more cases that change, the less the assistant can be relied on to give the same answer twice.</p>
      <table><thead><tr><th>Check</th><th>Cases whose result changed between runs</th></tr></thead><tbody>
        ${agree.map(([k, a]) => `<tr><td>${esc(CHECK[k])}</td><td style="min-width:240px"><div class="row" style="gap:10px"><b style="white-space:nowrap">${a.items - a.stable} of ${a.items}</b>
          <span class="bar grow warm" aria-hidden="true"><span style="width:${pct(a.items - a.stable, a.items)}%"></span></span></div>
          ${(a.flipping_items || []).length ? `<div class="tiny muted" style="margin-top:4px">${a.flipping_items.map((it) => `<a href="#/review/${enc(id)}/memo/${enc(memoId(it, 0))}">${esc(caseName(it))}</a>`).join(", ")}</div>` : ""}</td></tr>`).join("")}
      </tbody></table></section>`;
  $view.innerHTML = `<div class="stack" style="gap:28px">
    <div class="row wrap"><a class="link" href="#/">${ICON.back}Home</a>
      <span class="muted small"><b>${esc(testName(ov.run))}</b> · started ${esc(when(d.manifest.started_at || d.manifest.finished_at))}${rulesName(d.manifest.pack) ? " · " + esc(rulesName(d.manifest.pack)) : ""} · ${h.memos} memos${sizeWords(ov.run) ? ` (${esc(sizeWords(ov.run))})` : ""}</span></div>
    <section class="card stack mid" style="padding:32px 36px">${verdictBadge(dec.verdict, true)}
      <h1 style="font-size:34px;max-width:900px">${esc(lead)}</h1>
      <p class="muted" style="font-size:17px;max-width:900px">${esc(support)}</p>
      ${p && p.complete === false && p.planned ? `<p class="note-box amber small">The AI reviewers have answered ${p.answered} of ${p.planned} memos so far; the rest are being reviewed now. Reload this page in a few minutes for the full second opinion.</p>` : ""}
      <div class="row wrap" style="gap:12px;margin-top:6px">
        ${flagged ? `<a class="btn primary large" href="#/review/${enc(id)}">Review the ${flagged} flagged memos${ICON.arrow}</a>` : ""}
        <a class="btn large" href="/api/runs/${enc(id)}/pdf/business">${ICON.down}Download the sealed report (PDF)</a></div>
      ${anchorBadge}</section>
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
    ${consistency}
    <details class="card"><summary style="font-size:17px">Show the technical detail</summary>
      <div class="stack" style="margin-top:16px">
        <table><thead><tr><th>Check</th><th>Memos that passed</th><th>Result</th></tr></thead><tbody>
          ${(dec.checks || []).map((c) => { const [w, k] = CHECK_STATUS[c.status] || [c.status, ""]; return `<tr><td>${esc(CHECK[c.check] || c.check)}<div class="tiny muted">${esc(c.meaning || "")}</div></td><td>${Math.round(100 * c.pass_rate)}%</td><td class="${k === "red" ? "error" : ""}" style="font-weight:600;color:${k === "ok" ? "var(--green)" : k === "amber" ? "var(--amber)" : ""}">${esc(w)}</td></tr>`; }).join("")}
        </tbody></table>
        ${(dec.conditions || []).length ? `<div class="small"><b>Why:</b><ul>${dec.conditions.map((c) => `<li>${esc(c)}</li>`).join("")}</ul></div>` : ""}
        ${reports.length ? `<div class="stack tight"><b>Other reports</b><div class="row wrap" style="gap:8px">${reports.map((r) => `<a class="btn small" href="/api/runs/${enc(id)}/pdf/${enc(r.name)}">${esc(r.title || r.name)}</a>`).join("")}</div></div>` : ""}
        <div class="stack tight"><b>Is the evidence intact?</b><p class="small muted" id="vres">Every file in this test is sealed. Checking recomputes every result from the recorded memos.</p>
          <button class="btn small" id="verify" style="align-self:flex-start">Check the seal</button></div>
        ${anchorBox}
        <p class="tiny muted">Assistant ${esc(d.manifest.sut && d.manifest.sut.model_id)} · test ${esc(id)}</p>
      </div></details>
  </div>`;
  const an = document.getElementById("anchor-now");
  if (an) an.onclick = async () => { an.disabled = true; try { await api(`/api/runs/${enc(id)}/anchor`, { action: "now", what: "test" }); } catch (e) { /* shown on reload */ } viewResult(id); };
  document.getElementById("verify").onclick = async (ev) => {
    const out = document.getElementById("vres");
    ev.target.disabled = true;
    out.textContent = "Checking…";
    try {
      const v = await api(`/api/runs/${enc(id)}/verify`, { recompute: true });
      out.innerHTML = (v.ok ? `<b style="color:var(--green)">Intact.</b> ${esc(v.message)}` : `<b class="error">Does not verify.</b> ${esc(v.message)}`)
        + (v.anchors ? `<br>${v.anchors.ok ? "" : '<b class="error">Anchoring:</b> '}${esc(v.anchors.message)}` : "");
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

// Short names for the case-file figures, for the chips beside the memo's sentences.
const FACT_SHORT = {
  dti: "debt ratio", debt_service: "debt service", income: "annual income", income_monthly: "monthly income",
  commitments: "commitments", instalment: "instalment", room: "largest instalment within 40%", score: "bureau score",
  file_age: "credit file", missed: "missed payments", verified: "income verified", amount: "amount", term: "term",
  purpose: "purpose", employment: "employment", tenure: "time in role", age_band: "age band", dependants: "dependants",
  title: "title", employer: "employer", postcode: "postcode",
};
const factChip = (f) => `<span class="cfchip st-${f.status}" data-fact="${esc(f.key)}">Case file: ${esc(FACT_SHORT[f.key] || f.label)} <b>${esc(f.value)}</b>${f.status === "outside" ? " · outside policy" : f.status === "no_bearing" ? " · not a factor" : ""}</span>`;

function highlight(text, cards, facts) {
  // Findings on the same sentence share one highlight that carries all their numbers,
  // followed by the case file's figures those findings are about.
  const byKey = {};
  (facts || []).forEach((f) => (byKey[f.key] = f));
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
    const keys = [...new Set(m.cards.flatMap((x) => (cards.find((c) => c.card_id === x[0]).facts || [])))].filter((key) => byKey[key]);
    const chips = keys.map((key) => factChip(byKey[key])).join("");
    html = html.replace(`\u0000${k}\u0000`, `<mark data-cards="${m.cards.map((x) => x[0]).join(" ")}"><sup>${m.cards.map((x) => x[1]).join(",")}</sup>${m.s}</mark>${chips ? ` ${chips}` : ""}`);
  });
  return html.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/^\s*[*-]\s{1,4}/gm, "• ").replace(/^#{1,4}\s*(.+)$/gm, "<b>$1</b>");
}

function appStrip(id, memos, current) {
  // Every application in the test in one row, by lane: move between them without losing
  // the page's width. Ticked when reviewed; the open one is highlighted.
  const all = ["red", "amber", "green"].flatMap((lane) => memos.filter((m) => m.lane === lane));
  const i = all.findIndex((m) => m.memo === current);
  const href = (m) => `#/review/${enc(id)}/memo/${enc(m.memo)}`;
  const prev = i > 0 ? all[i - 1] : null, nxt = i >= 0 && i < all.length - 1 ? all[i + 1] : null;
  return `<nav class="appstrip" aria-label="Applications">
    ${prev ? `<a class="btn small" href="${href(prev)}" aria-label="Previous application">${ICON.back}</a>` : '<span class="btn small" aria-hidden="true" style="opacity:.35">' + ICON.back + "</span>"}
    <div class="stripscroll">${all.map((m, k) => `${k === 0 || all[k - 1].lane !== m.lane ? `<span class="striplane"><span class="lane-dot small ld-${m.lane}" aria-hidden="true"></span>${LANE[m.lane][0]}</span>` : ""}<a class="stripitem${m.memo === current ? " on" : ""}${m.reviewed ? " done" : ""}" href="${href(m)}"${m.memo === current ? ' aria-current="page"' : ""} title="Application ${esc(m.case)}, memo ${m.repeat + 1}${m.reviewed ? " (reviewed)" : ""}">${m.reviewed ? ICON.check : ""}${esc(m.case.replace(/^APP0*/, ""))}<span class="muted">·${m.repeat + 1}</span></a>`).join("")}</div>
    ${nxt ? `<a class="btn small" href="${href(nxt)}" aria-label="Next application">${ICON.arrow}</a>` : '<span class="btn small" aria-hidden="true" style="opacity:.35">' + ICON.arrow + "</span>"}</nav>`;
}

// Every run of this case: the assistant got the same case each time as a fresh request.
// Do its memos agree? Each run links to its memo, and any other run can be opened beside it.
function runsRow(m) {
  const runs = m.runs || [];
  if (runs.length < 2) return "";
  const words = (r) => (r.failing_checks.length ? `${plural(r.failing_checks.length, "check")} failed`
    : r.lane === "green" ? "no problems found" : "flagged by the AI reviewers only");
  const same = new Set(runs.map((r) => r.failing_checks.join(","))).size === 1;
  return `<div class="runs note-box ${same ? "" : "amber"} stack tight">
      <p class="small"><b>This case ran ${runs.length} times.</b> ${same
        ? "Every run failed the same checks."
        : "The runs disagree: the assistant wrote a different memo each time, and they did not fail the same checks."}</p>
      <div class="row wrap" style="gap:8px">${runs.map((r) => r.memo === m.memo
        ? `<span class="runchip on"><span class="lane-dot small ld-${r.lane}" aria-hidden="true"></span>Run ${r.repeat + 1} · ${words(r)} · this memo</span>`
        : `<span class="runchip"><span class="lane-dot small ld-${r.lane}" aria-hidden="true"></span><a href="#/review/${enc(m.run_id || "")}" data-run-link="${esc(r.memo)}">Run ${r.repeat + 1}</a> · ${words(r)}${r.reviewed ? " · reviewed" : ""}
            <button type="button" class="linkbtn" data-compare="${esc(r.memo)}">Compare</button></span>`).join("")}</div></div>`;
}

// The case file at a glance: its figures by group, each with its policy line; the ones a
// finding is about are outlined and carry the finding's number.
function factsPanel(facts, groups, cards) {
  if (!facts || !facts.length) return "";
  const nums = {};
  cards.forEach((c, i) => (c.facts || []).forEach((k) => (nums[k] = [...(nums[k] || []), i + 1])));
  const cell = (f) => `<div class="fact st-${f.status}${nums[f.key] ? " hit" : ""}" data-fact="${esc(f.key)}">
      <span class="factlabel">${nums[f.key] ? `<span class="factnum">${nums[f.key].join(",")}</span> ` : ""}${esc(f.label)}</span><b>${esc(f.value)}</b>
      ${f.policy || f.derived ? `<span class="tiny factpol">${f.derived ? `${esc(f.derived)}${f.policy ? " · " : ""}` : ""}${f.policy ? `${f.status === "outside" ? "outside policy: " : f.status === "ok" ? "within policy: " : ""}${esc(f.policy)}` : ""}</span>` : ""}</div>`;
  return `<section class="facts" aria-label="The case file at a glance"><p class="eyebrow">The case file at a glance</p>
      <span class="tiny muted" style="margin-top:-8px">From the documents the assistant was given; ratios worked out exactly. Numbers mark the findings about a figure.</span>
    ${Object.entries(groups || {}).map(([g, name]) => { const list = facts.filter((f) => f.group === g); return list.length ? `<div class="factgroup"><span class="small" style="font-weight:700">${esc(name)}</span><div class="factgrid">${list.map(cell).join("")}</div></div>` : ""; }).join("")}</section>`;
}

async function viewMemo(id, memo) {
  const [m, q, ov] = await Promise.all([api(`/api/review/${enc(id)}/memo?memo=${enc(memo)}`), api(`/api/review/${enc(id)}`), overview(id)]);
  renderSteps(ov, "review");
  page("wide review");
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
  // The coach speaks only when asked: about one finding (after it is answered) or about all
  // the answers. The first answer on each finding is kept, so the review shows what the
  // reviewer thought before the coach said anything.
  const coach = { session: null, turns: [], busy: null, error: "", draft: "" };
  const firstClick = {};

  // The memo and the subbar are drawn once; the findings column redraws on every answer.
  const main = document.createElement("div");
  $view.innerHTML = "";
  const sub = document.createElement("div");
  sub.className = "subbar";
  sub.className = "subbar sticky";
  sub.innerHTML = `<div class="row wrap" style="gap:20px;width:100%"><a class="link" href="#/review/${enc(id)}">${ICON.back}All flagged memos</a>
    <span class="row small" style="gap:8px"><span class="lane-dot small ld-${m.lane}" aria-hidden="true"></span><b>${LANE[m.lane][0]}</b> · memo ${pos} of ${laneList.length}</span>
    <span class="bar grow hide-sm" aria-hidden="true"><span style="width:${pct(laneList.filter((x) => x.reviewed).length, laneList.length)}%"></span></span>
    <span class="small muted">${q.memos.filter((x) => x.reviewed).length} of ${q.memos.length} reviewed</span></div>
    ${appStrip(id, q.memos, memo)}`;
  $view.before(sub);
  const cleanup = () => { sub.remove(); window.removeEventListener("hashchange", cleanup); };
  window.addEventListener("hashchange", cleanup);
  main.className = "review-grid";
  const docsBtn = m.case_file.length ? `<button type="button" class="btn small" id="docs" style="align-self:flex-start">See the original documents</button>` : "";
  main.innerHTML = `${m.facts && m.facts.length ? `<aside class="factcol stack mid">${factsPanel(m.facts, m.groups, m.cards)}${docsBtn}</aside>` : docsBtn ? `<aside class="factcol">${docsBtn}</aside>` : ""}<article class="stack mid">
      <div class="row wrap" style="justify-content:space-between;align-items:baseline;gap:12px">
        <h1 style="font-size:26px">Application ${esc(m.case)} · run ${m.repeat + 1}${(m.runs || []).length > 1 ? ` of ${m.runs.length}` : ""}</h1>
        ${m.cards.length ? `<span class="small muted"><span class="legend-mark">text</span> the machine found a problem here · <span class="cfchip">Case file: …</span> what the case file says</span>` : ""}</div>
      ${runsRow(m)}
      ${m.review ? `<p class="note-box amber small">Checked by ${esc(m.review.reviewer)} on ${esc(shortDate(m.review.submitted_at))}. Saving again records a new review.</p>` : ""}
      <div class="card stack mid" style="padding:28px 32px"><p class="eyebrow">The memo the assistant wrote</p>
        <div class="memo-text">${highlight(m.text, m.cards, m.facts)}</div></div>
      <div id="other"></div>
    </article><aside class="stack mid" id="side"></aside>`;
  $view.appendChild(main);
  const side = main.querySelector("#side");
  // the findings stay in view beside the memo: below the header and the strip, scrolling on their own
  const place = () => {
    const top = Math.max(88, sub.getBoundingClientRect().bottom + 16);
    main.querySelectorAll("aside").forEach((a) => { a.style.top = `${top}px`; a.style.maxHeight = `calc(100vh - ${top + 16}px)`; });
  };
  place();
  window.addEventListener("resize", place);
  const cur = sub.querySelector(".stripitem.on");
  if (cur) cur.scrollIntoView({ block: "nearest", inline: "center" });
  const byFact = {};
  (m.facts || []).forEach((f) => (byFact[f.key] = f));
  // other runs of this case: open one, or set its memo beside this one
  main.querySelectorAll("[data-run-link]").forEach((a) => (a.href = `#/review/${enc(id)}/memo/${enc(a.dataset.runLink)}`));
  main.querySelectorAll("[data-compare]").forEach((b) => (b.onclick = () => {
    const r = m.runs.find((x) => x.memo === b.dataset.compare);
    const box = main.querySelector("#other");
    const open = box.dataset.memo === r.memo;
    main.querySelectorAll("[data-compare]").forEach((x) => (x.textContent = "Compare"));
    if (open) { box.innerHTML = ""; box.dataset.memo = ""; return; }
    b.textContent = "Hide";
    box.dataset.memo = r.memo;
    box.innerHTML = `<div class="card stack mid other-run"><div class="row" style="justify-content:space-between;align-items:baseline">
        <p class="eyebrow">Run ${r.repeat + 1} of this case, for comparison</p><a class="link small" href="#/review/${enc(id)}/memo/${enc(r.memo)}">Review this run</a></div>
      <div class="memo-text">${highlight(r.text, r.cards, m.facts)}</div></div>`;
    box.scrollIntoView({ behavior: "smooth", block: "start" });
  }));
  // the documents the assistant was given, as they were, in a window
  const docs = main.querySelector("#docs");
  if (docs) docs.onclick = () => {
    const dlg = document.createElement("dialog");
    dlg.className = "modal wide";
    dlg.setAttribute("aria-label", "The original documents");
    dlg.innerHTML = `<div class="row" style="justify-content:space-between;align-items:baseline"><h2>The documents the assistant was given</h2>
        <button type="button" class="btn small" id="docs-close">Close</button></div>
      ${m.case_file.map((d) => `<h3 style="margin-top:16px">${esc(d.title)}</h3><div class="casefile">${esc(d.content)}</div>`).join("")}`;
    document.body.appendChild(dlg);
    dlg.addEventListener("close", () => dlg.remove());
    dlg.querySelector("#docs-close").onclick = () => dlg.close();
    dlg.showModal();
  };

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
        ${(c.facts || []).filter((k) => byFact[k]).length ? `<div class="versus">
          ${c.memo_value ? `<div class="stack tight"><span class="tiny muted">The memo says</span><b class="memo-val${c.source === "numeric_fidelity" ? " struck" : ""}">${esc(c.memo_value)}</b></div>` : ""}
          ${(c.facts || []).filter((k) => byFact[k]).map((k) => { const f = byFact[k]; return `<div class="stack tight"><span class="tiny muted">Case file: ${esc(f.label.toLowerCase())}</span><b class="case-val st-${f.status}">${esc(f.value)}</b>${f.policy ? `<span class="tiny factpol st-${f.status}">${f.status === "outside" ? "Outside policy: " : f.status === "ok" ? "Within policy: " : ""}${esc(f.policy)}</span>` : ""}${f.derived ? `<span class="tiny muted">${esc(f.derived)}</span>` : ""}</div>`; }).join("")}</div>` : ""}
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
        ${st.action ? askCoach(c.card_id) : ""}
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
    const thread = coach.turns.filter((t) => !t.about).map((t) => `${t.message ? `<div class="bubble me"><span class="eyebrow">You</span><p>${esc(t.message)}</p></div>` : ""}
      <div class="bubble coachsays"><span class="eyebrow">Coach</span>
        ${t.challenges.length ? t.challenges.map((c) => `<div class="challenge">
          ${c.card_id ? `<a href="#" data-goto="${c.card_id}" class="small" style="font-weight:700">Finding ${[c.finding, ...(c.also || [])].join(" and ")}</a>` : '<span class="small" style="font-weight:700">Not in the findings</span>'}
          <p>${esc(c.question)}</p>${c.evidence ? `<p class="tiny muted">${esc(c.evidence)}</p>` : ""}</div>`).join("") : ""}
        ${t.reply ? `<p class="small">${esc(t.reply)}</p>` : ""}
        ${!t.challenges.length ? '<p class="small" style="color:var(--green);font-weight:600">No questions about your answers.</p>' : ""}</div>`).join("");
    const coachBox = m.cards.length ? `<section class="coach stack mid">
        <div class="stack tight"><h3>Coach</h3><p class="tiny muted">Optional. Unsure about a finding? Answer it, then press <b>Ask the coach</b> under it. The coach points at the evidence and leaves the decision to you; it does not know the right answers.</p></div>
        ${thread}
        ${coach.busy === "all" ? '<div class="row small"><span class="spinner" style="width:20px;height:20px" aria-hidden="true"></span>The coach is reading your answers…</div>' : ""}
        ${coach.error ? `<p class="error small">${esc(coach.error)}</p>` : ""}
        ${!coach.busy && !thread ? `<button class="btn small" id="coach-ask" style="align-self:flex-start" ${answered() < m.cards.length ? "disabled" : ""}>Ask the coach about all my answers</button>${answered() < m.cards.length ? '<p class="tiny muted">Answer every finding first.</p>' : ""}` : ""}
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
        if (!firstClick[cid]) firstClick[cid] = { card_id: cid, action: b.dataset.a, at: new Date().toISOString() };
        state[cid] = { ...state[cid], action: b.dataset.a };
        draw();
      }));
      el.querySelectorAll("[data-r]").forEach((b) => (b.onclick = () => { state[cid].reason = b.dataset.r; draw(); }));
      const fix = el.querySelector("[data-fix]");
      if (fix) fix.oninput = () => (state[cid].correction = fix.value);
      const mk = () => document.querySelector(`mark[data-cards~="${cid}"]`);
      const figs = () => ((m.cards.find((c) => c.card_id === cid) || {}).facts || []).flatMap((k) => [...main.querySelectorAll(`[data-fact="${k}"]`)]);
      el.onmouseenter = () => { const x = mk(); if (x) x.classList.add("on"); figs().forEach((f) => f.classList.add("on")); };
      el.onmouseleave = () => { const x = mk(); if (x) x.classList.remove("on"); figs().forEach((f) => f.classList.remove("on")); };
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
    side.querySelectorAll("[data-ask]").forEach((b) => (b.onclick = () => ask(null, b.dataset.ask)));
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

  // Under an answered finding: the coach's latest word on it, and the button to ask.
  function askCoach(cid) {
    const said = [...coach.turns].reverse().find((t) => t.about === cid);
    const q = said ? said.challenges.filter((x) => x.card_id === cid || (x.also_card_ids || []).includes(cid)) : [];
    return `${said ? `<div class="coachnote" role="status"><span class="eyebrow">Coach</span>
        ${said.reply ? `<p class="small">${esc(said.reply)}</p>` : ""}
        ${q.map((x) => `<p class="small" style="font-weight:600">${esc(x.question)}</p>${x.evidence ? `<p class="tiny muted">${esc(x.evidence)}</p>` : ""}`).join("")}</div>` : ""}
      ${coach.busy === cid ? '<div class="row small"><span class="spinner" style="width:18px;height:18px" aria-hidden="true"></span>The coach is looking at the evidence…</div>'
        : `<button type="button" class="btn small ghost" data-ask="${esc(cid)}" style="align-self:flex-start"${coach.busy ? " disabled" : ""}>${said ? "Ask the coach again" : "Ask the coach about this"}</button>`}`;
  }

  const verdictsNow = () => m.cards.map((c) => ({ card_id: c.card_id, ...state[c.card_id] }));
  async function ask(message, about) {
    coach.busy = about || "all"; coach.error = ""; draw();
    try {
      const r = await api(`/api/review/${enc(id)}/coach`, { memo, session_id: coach.session, verdicts: verdictsNow(), raised, message: message || null, about: about || null });
      coach.session = r.session_id;
      coach.turns.push({ message: message || null, about: r.about || null, challenges: r.challenges, reply: r.reply });
      if (message) coach.draft = "";
    } catch (e) { coach.error = `The coach could not answer: ${e.message}`; }
    coach.busy = null; draw();
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
  renderSteps(ov, "improve");
  page("");
  const s = q.summary, st = ov.stages, ev = q.evaluator || { panel: {}, rule_checks: {} };
  const fix = q.to_correct || [];
  const spots = fix.reduce((n, m) => n + m.spots.length, 0);
  const model = (d.manifest.sut || {}).model_id || "the assistant's model";
  const fixable = (d.recommendations || []).find((r) => r.cause === "miscalculated" || r.cause === "misread_threshold") || null;
  const canBuild = !adj.length && s.settled > 0;
  const stale = !!(fb && q.last_change && q.last_change > fb.built_at);
  const memoLink = (memo, words) => `<a href="#/review/${enc(id)}/memo/${enc(memo)}">${esc(words)}</a>`;
  const runWords = (memo) => { const m = q.memos.find((x) => x.memo === memo); return m ? `${m.case} · run ${m.repeat + 1}` : caseOf(memo); };

  // The five steps, and where each stands: done, next (the one to do now) or waiting.
  const steps = [
    { key: "settle", title: "Settle disagreements", done: s.reviewed > 0 && !adj.length, open: adj.length },
    { key: "correct", title: "Write the corrections", done: s.reviewed > 0 && !spots, open: fix.length },
    // a pack built before the last corrections or rulings is out of date: build it again
    { key: "build", title: "Build the feedback pack", done: !!fb && !adj.length && !spots && !stale, open: 0 },
    { key: "handover", title: "Hand over for fine-tuning", done: !!(fb && fb.handover) && !adj.length && !spots && !stale, open: 0 },
    { key: "prove", title: "Prove the fix on new cases", done: false, open: 0 },
  ];
  const nextStep = !s.reviewed ? null : steps.find((x) => !x.done) || null;
  const state = (x) => (x.done ? "done" : nextStep && nextStep.key === x.key ? "next" : "todo");
  const dot = (x, n) => (state(x) === "done" ? `<span class="dot big done">${ICON.check}</span>` : `<span class="dot big ${state(x) === "next" ? "fill" : "todo"}">${n}</span>`);
  const head = (x, n, extra) => `<div class="row" style="gap:12px">${dot(x, n)}<h2 style="font-size:21px">${x.title}</h2>
      ${state(x) === "next" ? '<span class="badge b-blue" style="margin-left:auto">Do this next</span>' : x.done ? '<span class="small muted" style="margin-left:auto">Done</span>' : ""}${extra || ""}</div>`;

  const headline = !s.reviewed ? "Nothing to improve from yet: no memo has been reviewed."
    : adj.length ? `${plural(adj.length, "disagreement needs", "disagreements need")} a decision before the feedback pack can be built.`
    : spots ? `${plural(fix.length, "memo needs its", "memos need their")} corrected wording before ${fix.length === 1 ? "it can teach" : "they can teach"} the assistant.`
    : !fb ? "Everything is settled. Build the feedback pack for the model team."
    : "The feedback pack is ready for the model team.";
  const nextBtn = !s.reviewed ? `<a class="btn primary large" href="#/review/${enc(id)}">Go to Review${ICON.arrow}</a>`
    : nextStep ? `<a class="btn primary large" href="#step-${nextStep.key}" data-jump="${nextStep.key}">${nextStep.title}${ICON.arrow}</a>` : "";
  const partial = s.reviewed && st.flagged_checked < st.flagged
    ? `<p class="note-box small">You have checked ${st.flagged_checked} of ${st.flagged} flagged memos. The pack can be built from what is checked so far, and built again as you check more. <a href="#/review/${enc(id)}">Continue the review</a></p>` : "";

  const tile = (big, title, text, bad) => `<div class="card stack" style="gap:4px;padding:20px"><span class="small muted" style="font-weight:600">${title}</span>
      <span style="font-size:30px;font-weight:700${bad ? ";color:var(--red)" : ""}">${big}</span><span class="small muted">${text}</span></div>`;
  const trust = s.reviewed ? `<div class="stack tight"><h2 style="font-size:21px">Can the review be trusted?</h2>
      <p class="small muted">Every test case has a known right answer, so the review itself is checked.</p></div>
    <div class="grid3">
      ${tile(s.known_answer_verdicts ? `${pct(s.agree_with_known_answer, s.known_answer_verdicts)}%` : "—", "Answers that match the known answer",
        s.known_answer_verdicts ? `${s.agree_with_known_answer} of ${s.known_answer_verdicts} answers on findings the rule checks are sure of.` : "None of the answered findings has a known answer yet.")}
      ${tile(s.automation_bias_memos, "Mistakes waved through", `${s.automation_bias_memos === 1 ? "Memo" : "Memos"} passed as right although ${s.automation_bias_memos === 1 ? "it has" : "they have"} a known mistake. Above zero means people trust the machine too much.`, s.automation_bias_memos > 0)}
      ${tile(ev.panel.flags_on_rule_clean_memos_reviewed ? `${ev.panel.problems_the_rules_missed} <span style="font-size:17px;font-weight:600">real</span> · ${ev.panel.false_alarms} <span style="font-size:17px;font-weight:600">false</span>` : "—", "What the AI reviewers raised beyond the rules",
        ev.panel.flags_on_rule_clean_memos_reviewed ? `Of ${ev.panel.flags_on_rule_clean_memos_reviewed} flags on memos that passed every rule check: real problems the rules missed, and false alarms.` : "Check memos in Worth a look to see whether their flags are real.")}
    </div>` : "";

  const settle = `<section class="card stack mid" id="step-settle">${head(steps[0], 1, adj.length ? `<span class="badge b-amber">${adj.length} left</span>` : "")}
      <p class="small muted">Where a reviewer disagreed with the machine, was not sure, or found a problem of their own, someone from model risk decides who is right. Only settled answers go into the pack.</p>
      ${adj.length ? adj.map((x) => `<div class="settle" data-v="${esc(x.verdict_id)}">
          <div class="row wrap" style="justify-content:space-between;gap:8px"><b>${memoLink(x.memo, runWords(x.memo))}</b><span class="tiny muted">Reviewed by ${esc(x.reviewer)}</span></div>
          <div class="grid2" style="gap:12px">
            <div class="stack tight"><span class="tiny muted">The machine found</span><span>${x.verdict.action === "raise" ? '<span class="muted">Nothing here</span>' : esc(x.card.problem)}</span></div>
            <div class="stack tight"><span class="tiny muted">The reviewer said</span><span>${esc(ACTION_WORDS[x.verdict.action] || x.verdict.action)}${x.verdict.action === "raise" ? `: ${esc(x.card.problem)}` : ""}${x.verdict.reason ? ` · “${esc(REASON[x.verdict.reason] || x.verdict.reason)}”` : ""}</span></div></div>
          ${x.card.sentence ? `<p class="small muted" style="border-left:3px solid var(--line);padding-left:10px">“${esc(x.card.sentence)}”</p>` : ""}
          <div class="row wrap" style="gap:8px"><span class="small" style="font-weight:600">Who is right?</span><button class="btn small" data-d="uphold">The reviewer</button><button class="btn small" data-d="reject">${x.verdict.action === "raise" ? "It is not a problem" : "The machine"}</button></div></div>`).join("")
        : `<p class="small">${s.reviewed ? "Nothing to settle: every answer agrees with the machine or with the known answer." : "Nothing yet."}</p>`}</section>`;

  const correct = `<section class="card stack mid" id="step-correct">${head(steps[1], 2, spots ? `<span class="badge b-amber">${plural(fix.length, "memo")}</span>` : "")}
      <p class="small muted">A confirmed mistake teaches the assistant only once someone writes how the memo should have read. Write it here: the assistant is trained on the corrected memo.</p>
      ${fix.length ? fix.map((m) => `<div class="stack tight fixmemo"><b>${memoLink(m.memo, `${m.case} · run ${m.repeat + 1}`)}</b>
          ${m.spots.map((sp, k) => `<div class="fixspot stack tight" data-memo="${esc(m.memo)}" data-cards="${esc(sp.card_ids.join(" "))}">
            ${sp.problems.map((pr) => `<span class="small" style="color:var(--red)">${esc(pr)}</span>`).join("")}
            ${sp.sentence ? `<p class="small" style="border-left:3px solid var(--mark-line);padding-left:10px;background:var(--mark)">Now: “${esc(sp.sentence)}”</p>` : ""}
            <label class="small" for="fx-${esc(m.memo)}-${k}"><b>${sp.sentence ? "How should it read?" : "What should the memo add?"}</b></label>
            <textarea id="fx-${esc(m.memo)}-${k}" placeholder="${sp.sentence ? "The sentence as it should read" : "The missing point, in a sentence"}">${sp.sentence ? esc(sp.sentence) : ""}</textarea>
            <div class="row" style="gap:10px"><button class="btn small primary" data-save>Save correction</button><span class="small" data-msg></span></div></div>`).join("")}</div>`).join("")
        : `<p class="small">${s.reviewed ? "Every confirmed mistake has its corrected wording." : "Nothing yet."}</p>`}</section>`;

  const c = fb ? fb.counts : null;
  const count = (k) => (c ? c[k] : "—");
  const small = (n, title, text) => `<div class="stack" style="gap:2px;padding:14px;border:1px solid var(--line-2);border-radius:12px"><span style="font-size:24px;font-weight:700">${n}</span><span class="small" style="font-weight:600">${title}</span><span class="tiny muted">${text}</span></div>`;
  const dl = (f, words) => `<a class="btn small" href="/api/review/${enc(id)}/feedback/${f}">${ICON.down}${words}</a>`;
  const build = `<section class="card stack mid" id="step-build">${head(steps[2], 3)}
      <p class="small muted">Everything settled becomes one sealed pack${fb ? `, last built ${esc(when(fb.built_at))}` : ""}. It holds no customer data, and its fingerprint shows any later change.</p>
      <div class="grid4">
        ${small(count("sft.jsonl"), "Corrected memos", "Each memo as it should have been written.")}
        ${small(count("preferences.jsonl"), "Before-and-after pairs", "The original beside the correction.")}
        ${small(count("judge_labels.jsonl"), "Confirmed findings", "What counts as a real mistake.")}
        ${small(count("check_fixes.jsonl"), "Rule-check fixes", "Where a rule check was itself wrong.")}</div>
      ${fb && (spots || stale) ? `<p class="note-box amber small">${spots ? `${plural(fix.length, "memo is", "memos are")} left out of this pack until ${fix.length === 1 ? "its correction is" : "their corrections are"} written. Then build it again.` : "Answers, rulings or corrections have changed since it was built. Build it again so the pack has them."}</p>` : ""}
      <div class="row wrap" style="gap:12px"><button class="btn ${state(steps[2]) === "next" || (fb && spots === 0 && !steps[2].done) ? "primary " : ""}" id="build" ${canBuild ? "" : "disabled"}>${fb ? "Build it again" : "Build the feedback pack"}</button>
        <span class="small muted" id="bmsg">${canBuild ? (spots ? `${plural(fix.length, "memo")} without corrected wording will be left out.` : "") : adj.length ? `Once the ${plural(adj.length, "disagreement")} ${adj.length === 1 ? "is" : "are"} settled.` : "Once memos have been reviewed."}</span></div>
      ${fb ? `<details><summary class="small">The files in the pack</summary><div class="row wrap" style="gap:8px;margin-top:10px">${dl("sft.jsonl", "Corrected memos")}${dl("preferences.jsonl", "Before-and-after pairs")}${dl("judge_labels.jsonl", "Confirmed findings")}${dl("check_fixes.jsonl", "Rule-check fixes")}${dl("manifest.json", "Contents and fingerprints")}</div></details>` : ""}</section>`;

  const handover = `<section class="card stack mid" id="step-handover">${head(steps[3], 4)}
      <p class="small muted">One zip for the engineering team that fine-tunes the assistant (${esc(model)}): the corrected memos in training formats${fb && fb.handover ? ` (${fb.handover.counts.sft_train} for training, ${fb.handover.counts.sft_validation} for checking, ${fb.handover.counts.dpo} before-and-after pairs)` : ""}, the confirmed findings, a starting configuration, and a README that says where every row came from and how the tuned model will be accepted.</p>
      ${fb && fb.handover ? `<a class="btn primary" href="/api/review/${enc(id)}/handover.zip" style="align-self:flex-start">${ICON.down}Download the handover (zip)</a>` : '<p class="small muted">Available once the feedback pack is built.</p>'}</section>`;

  const prove = `<section class="card stack mid" id="step-prove">${head(steps[4], 5)}
      <p class="small muted">A change is accepted only when it helps on cases the assistant has never seen. We generate new cases, run the assistant as it is and with the change on the same cases, and put the two side by side.</p>
      <div class="grid2" style="gap:12px">
        <div class="stack tight" style="padding:16px;border:1px solid var(--line-2);border-radius:12px"><b>A change your team can make today</b>
          ${fixable ? `<span class="small">${esc(fixable.title)}.</span><span class="small muted">Could fix up to ${plural(fixable.addresses.briefings, "memo")} in this test.</span>
            <button class="btn primary small" id="retest" style="align-self:flex-start;margin-top:6px">Test this change on new cases</button><span class="small error" id="rmsg"></span>`
            : '<span class="small muted">This test points to no change your team can make without the vendor.</span>'}</div>
        <div class="stack tight" style="padding:16px;border:1px solid var(--line-2);border-radius:12px"><b>The fine-tuned model, when it comes back</b>
          <span class="small muted">Run a new test on new cases with the tuned model, then compare it with this test in Earlier tests.</span>
          <div class="row wrap" style="gap:8px;margin-top:6px"><a class="btn small" href="#/new">Start a new test</a><a class="btn small" href="#/history">Earlier tests</a></div></div></div></section>`;

  const secs = s.seconds_per_memo_by_lane || {};
  const t = (v) => (v == null ? null : v >= 60 ? `${Math.floor(v / 60)} min ${Math.round(v % 60)} s` : `${Math.round(v)} s`);
  const times = ["red", "amber", "green"].filter((l) => secs[l] != null).map((l) => `<li>${LANE[l][0]}: ${t(secs[l])} per memo</li>`).join("");
  const more = s.reviewed ? `<details class="card"><summary>More about this review</summary><div class="stack mid" style="margin-top:12px">
      <p class="small">${plural(s.reviewed, "memo")} reviewed by ${esc((s.reviewers || []).join(", ") || "—")}; ${plural(s.settled, "answer")} settled${s.upheld ? `, ${s.upheld} decided for the reviewer` : ""}${s.rejected ? `, ${s.rejected} for the machine` : ""}.</p>
      ${times ? `<div class="small"><b>Time spent</b><ul class="muted" style="margin:4px 0 0;padding-left:18px">${times}</ul></div>` : ""}
      ${ev.rule_checks.findings_settled ? `<p class="small"><b>Rule checks:</b> ${ev.rule_checks.shown_wrong} of ${ev.rule_checks.findings_settled} of their findings were shown to be wrong.</p>` : ""}
      ${ev.panel.memos_with_a_rule_failure != null ? `<p class="small"><b>AI reviewers:</b> flagged ${ev.panel.flagged_with_a_rule_failure} of the ${ev.panel.memos_with_a_rule_failure} memos with a known mistake.</p>` : ""}
      ${s.coach ? `<p class="small"><b>Coach:</b> asked on ${plural(s.coach.memos, "memo")}; ${plural(s.coach.answers_changed, "answer")} changed after it spoke${s.coach.known_answer_findings ? `; agreement with the known answers ${pct(s.coach.agreed_before_coach, s.coach.known_answer_findings)}% before, ${pct(s.coach.agreed_after_coach, s.coach.known_answer_findings)}% after` : ""}.</p>` : ""}
    </div></details>` : "";

  $view.innerHTML = `<div class="stack" style="gap:28px">
    <div class="row wrap"><a class="link" href="#/result/${enc(id)}">${ICON.back}Test result</a>
      <span class="muted small"><b>${esc(testName(ov.run))}</b> · started ${esc(when(ov.run.started_at || ov.run.finished_at))}</span></div>
    <section class="card stack mid" style="padding:32px 36px"><p class="eyebrow">Improve the assistant</p>
      <h1 style="font-size:32px;max-width:900px">${esc(headline)}</h1>
      <p class="muted" style="font-size:17px;max-width:900px">Your review answers become a feedback pack: the corrected memos the model team trains the assistant on. A re-test on new cases then proves the fix worked.</p>
      <ol class="stepline">${steps.map((x, k) => `<li class="${state(x)}"><a href="#step-${x.key}" data-jump="${x.key}">${state(x) === "done" ? ICON.check : `<span>${k + 1}</span>`}${x.title}${x.open ? ` <span class="badge b-amber">${x.open}</span>` : ""}</a></li>`).join("")}</ol>
      ${partial}
      ${nextBtn ? `<div class="row wrap" style="gap:12px">${nextBtn}</div>` : ""}</section>
    ${trust}
    ${s.reviewed ? `${settle}${correct}${build}${handover}${prove}${more}` : ""}
  </div>`;

  // in-page jumps (the hash is the router's)
  $view.querySelectorAll("[data-jump]").forEach((a) => (a.onclick = (e) => {
    e.preventDefault();
    const el = document.getElementById(`step-${a.dataset.jump}`);
    if (el) { el.scrollIntoView({ behavior: "smooth", block: "start" }); el.classList.add("flash"); setTimeout(() => el.classList.remove("flash"), 1400); }
  }));
  $view.querySelectorAll("[data-v]").forEach((box) => box.querySelectorAll("[data-d]").forEach((b) => (b.onclick = async () => {
    b.disabled = true;
    await api(`/api/review/${enc(id)}/adjudicate`, { verdict_id: box.dataset.v, decision: b.dataset.d, by: reviewer.get() || "model-risk" });
    viewImprove(id);
  })));
  $view.querySelectorAll(".fixspot").forEach((box) => (box.querySelector("[data-save]").onclick = async (ev2) => {
    const text = box.querySelector("textarea").value.trim();
    const msg = box.querySelector("[data-msg]");
    const before = box.querySelector("p") ? box.querySelector("p").textContent.replace(/^Now: “|”$/g, "") : "";
    if (!text || text === before) { msg.innerHTML = '<span class="error">Change the wording to how it should read.</span>'; return; }
    ev2.target.disabled = true;
    try {
      await api(`/api/review/${enc(id)}/correct`, { memo: box.dataset.memo, card_ids: box.dataset.cards.split(" "), correction: text, by: reviewer.get() || "reviewer" });
      const y = window.scrollY;
      await viewImprove(id);
      window.scrollTo(0, y);
    } catch (e) { msg.innerHTML = `<span class="error">${esc(e.message)}</span>`; ev2.target.disabled = false; }
  }));
  const rt = document.getElementById("retest");
  if (rt) rt.onclick = async () => {
    rt.disabled = true;
    try { const j = await api("/api/retest", { from_run: id, setup: "with_figures" }); location.hash = `#/retest/${enc(j.job_id)}`; }
    catch (e) { document.getElementById("rmsg").textContent = e.message; rt.disabled = false; }
  };
  const bt = document.getElementById("build");
  if (bt) bt.onclick = async () => {
    bt.disabled = true;
    document.getElementById("bmsg").textContent = "Building…";
    try { await api(`/api/review/${enc(id)}/feedback`, {}); await viewImprove(id); document.getElementById("step-build").scrollIntoView({ block: "start" }); } catch (e) {
      document.getElementById("bmsg").innerHTML = `<span class="error">${esc(e.message)}</span>`;
      bt.disabled = false;
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
