"""The library page — every brief on disk, one generated HTML file.

`render_library` takes the parsed contents of the `brief.json` files and
injects them into a fixed template. The page is generated, never hand-edited:
regenerating the briefs and re-running `prebrief library` is the only way its
data changes, so it cannot drift from what the repository actually holds.

The relationship sentences in the template mirror `brief.Relationship.sentence`
verbatim — the page renders the same inference the markdown does, never its
own wording.
"""

from __future__ import annotations

import json

__all__ = ["render_library"]


def render_library(briefs: list[dict]) -> str:
    """Inject brief payloads (parsed brief.json dicts) into the page."""
    ordered = sorted(briefs, key=lambda b: (b["entity"]["slug"], b["as_of"]))
    data = json.dumps(ordered, ensure_ascii=False, sort_keys=True)
    # A "</script>" inside a claim string would end the script block early.
    data = data.replace("</", "<\\/")
    return _TEMPLATE.replace("/*__DATA__*/", data, 1)


_TEMPLATE = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Prebrief Library</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600&family=Public+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
  :root{
    --paper:#F7F8F5; --panel:#FFFFFF; --ink:#1B211D; --ink-soft:#4C564F;
    --ink-faint:#79837B; --line:#DCE1DB; --line-soft:#E8ECE6;
    --accent:#21684E; --accent-ink:#FFFFFF; --accent-wash:#EAF2ED;
    --filed:#21684E; --filed-wash:#E3EFE8;
    --reported:#A8730F; --reported-wash:#F6EDDA;
    --self:#5B6B7C; --self-wash:#E7ECF1;
    --hover:#F0F3EE; --sel:#E8EFE9; --shadow:0 1px 3px rgba(27,33,29,.07);
  }
  @media (prefers-color-scheme: dark){
    :root:not([data-theme="light"]){
      --paper:#121714; --panel:#181E1A; --ink:#E6EAE5; --ink-soft:#A9B3AB;
      --ink-faint:#78827A; --line:#2A322C; --line-soft:#232A25;
      --accent:#5FA985; --accent-ink:#0E1411; --accent-wash:#1D2B23;
      --filed:#5FA985; --filed-wash:#1D2B23;
      --reported:#D4A048; --reported-wash:#2C2517;
      --self:#8FA1B3; --self-wash:#20262C;
      --hover:#1E2520; --sel:#223028; --shadow:0 1px 3px rgba(0,0,0,.35);
    }
  }
  :root[data-theme="dark"]{
    --paper:#121714; --panel:#181E1A; --ink:#E6EAE5; --ink-soft:#A9B3AB;
    --ink-faint:#78827A; --line:#2A322C; --line-soft:#232A25;
    --accent:#5FA985; --accent-ink:#0E1411; --accent-wash:#1D2B23;
    --filed:#5FA985; --filed-wash:#1D2B23;
    --reported:#D4A048; --reported-wash:#2C2517;
    --self:#8FA1B3; --self-wash:#20262C;
    --hover:#1E2520; --sel:#223028; --shadow:0 1px 3px rgba(0,0,0,.35);
  }
  *{box-sizing:border-box}
  html,body{margin:0;padding:0}
  body{
    background:var(--paper); color:var(--ink);
    font-family:"Public Sans",system-ui,-apple-system,sans-serif;
    font-size:15px; line-height:1.55;
  }
  .app{display:grid; grid-template-columns:308px minmax(0,1fr); min-height:100vh}

  /* ---------- rail ---------- */
  .rail{
    border-right:1px solid var(--line); background:var(--paper);
    padding:22px 18px; display:flex; flex-direction:column; gap:16px;
    position:sticky; top:0; height:100vh; overflow-y:auto;
  }
  .brand{display:flex; align-items:baseline; gap:8px}
  .brand .name{font-family:"IBM Plex Mono",monospace; font-weight:500; font-size:15px; letter-spacing:.01em}
  .brand .tag{font-size:11px; text-transform:uppercase; letter-spacing:.09em; color:var(--ink-faint); font-weight:600}
  .search{position:relative}
  .search input{
    width:100%; padding:8px 12px 8px 32px; border:1px solid var(--line); border-radius:6px;
    background:var(--panel); color:var(--ink); font:inherit; font-size:13.5px;
  }
  .search input:focus{outline:2px solid var(--accent); outline-offset:-1px; border-color:transparent}
  .search input::placeholder{color:var(--ink-faint)}
  .search svg{position:absolute; left:10px; top:50%; transform:translateY(-50%); color:var(--ink-faint)}
  .rail-label{font-size:11px; text-transform:uppercase; letter-spacing:.09em; color:var(--ink-faint); font-weight:600; margin-bottom:-6px}
  .blist{display:flex; flex-direction:column; gap:8px}
  .bcard{
    text-align:left; width:100%; border:1px solid var(--line); border-radius:8px;
    background:var(--panel); color:var(--ink); padding:12px 14px; cursor:pointer;
    font:inherit; display:flex; flex-direction:column; gap:7px; box-shadow:var(--shadow);
    transition:background .12s;
  }
  .bcard:hover{background:var(--hover)}
  .bcard:focus-visible{outline:2px solid var(--accent); outline-offset:1px}
  .bcard[aria-current="true"]{background:var(--sel); border-color:var(--accent)}
  .bcard .org{font-family:"Newsreader",Georgia,serif; font-weight:600; font-size:16.5px; line-height:1.25; text-wrap:balance}
  .bcard .meta{display:flex; align-items:center; gap:8px; flex-wrap:wrap; font-size:12px; color:var(--ink-soft)}
  .bcard .counts{font-family:"IBM Plex Mono",monospace; font-size:11.5px; color:var(--ink-faint); font-variant-numeric:tabular-nums}
  .tierbar{display:flex; height:3px; border-radius:2px; overflow:hidden; background:var(--line-soft)}
  .tierbar span{display:block; height:100%}
  .nores{color:var(--ink-faint); font-size:13px; padding:6px 2px}
  .rail-foot{margin-top:auto; padding-top:14px; border-top:1px solid var(--line-soft); font-size:12px; color:var(--ink-faint); display:flex; flex-direction:column; gap:5px}
  .rail-foot a{color:var(--ink-soft)}
  .rail-foot .mono{font-family:"IBM Plex Mono",monospace; font-size:11px}

  /* ---------- detail ---------- */
  .detail{padding:34px clamp(22px,5vw,60px) 70px; max-width:880px}
  .crumb{font-family:"IBM Plex Mono",monospace; font-size:11.5px; color:var(--ink-faint); margin-bottom:14px}
  h1{
    font-family:"Newsreader",Georgia,serif; font-weight:600; font-size:clamp(28px,4vw,38px);
    line-height:1.12; margin:0 0 10px; letter-spacing:-.01em; text-wrap:balance;
  }
  .headmeta{display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:6px}
  .desc{color:var(--ink-soft); font-size:15px; margin:2px 0 0; max-width:62ch}
  .headlinks{display:flex; gap:14px; margin-top:10px; font-size:13px}
  .headlinks a{color:var(--accent); text-decoration:none; font-weight:500}
  .headlinks a:hover{text-decoration:underline}

  .pill{
    display:inline-flex; align-items:center; gap:5px; padding:2px 9px; border-radius:999px;
    font-size:11.5px; font-weight:600; letter-spacing:.03em; text-transform:uppercase;
  }
  .pill.kind{background:var(--accent-wash); color:var(--accent)}
  .pill.date{background:transparent; border:1px solid var(--line); color:var(--ink-soft); text-transform:none; font-family:"IBM Plex Mono",monospace; font-weight:500; letter-spacing:0; font-size:11.5px}
  .chip{
    display:inline-block; padding:1px 8px; border-radius:4px; font-size:11px; font-weight:600;
    letter-spacing:.04em;
  }
  .chip.filed{background:var(--filed-wash); color:var(--filed)}
  .chip.reported{background:var(--reported-wash); color:var(--reported)}
  .chip.self-reported{background:var(--self-wash); color:var(--self)}

  section{margin-top:34px}
  h2{
    font-family:"Newsreader",Georgia,serif; font-weight:600; font-size:21px; margin:0 0 4px;
    letter-spacing:-.005em;
  }
  .seccount{font-family:"IBM Plex Mono",monospace; font-size:11px; color:var(--ink-faint); margin-left:8px; font-variant-numeric:tabular-nums}
  .secnote{font-size:12.5px; color:var(--ink-faint); margin:0 0 14px}
  .empty{color:var(--ink-faint); font-size:14px; font-style:italic; border:1px dashed var(--line); border-radius:8px; padding:12px 16px}

  .claims{display:flex; flex-direction:column; gap:10px; margin-top:12px}
  .claim{
    border:1px solid var(--line); border-radius:8px; background:var(--panel);
    padding:13px 16px; box-shadow:var(--shadow);
  }
  .claim .row{display:flex; align-items:baseline; gap:10px; justify-content:space-between; flex-wrap:wrap; margin-bottom:6px}
  .claim .when{font-family:"IBM Plex Mono",monospace; font-size:11.5px; color:var(--ink-faint); font-variant-numeric:tabular-nums}
  .claim .text{margin:0; max-width:68ch}
  .claim .src{margin-top:9px; font-size:13px; display:flex; align-items:center; gap:6px; flex-wrap:wrap}
  .claim .src a{color:var(--accent); text-decoration:none; font-weight:500}
  .claim .src a:hover{text-decoration:underline}
  .claim details{margin-top:9px; border-top:1px solid var(--line-soft); padding-top:8px}
  .claim summary{
    cursor:pointer; font-size:12px; color:var(--ink-faint); font-weight:600;
    text-transform:uppercase; letter-spacing:.07em; list-style:none; display:inline-flex; gap:6px; align-items:center;
  }
  .claim summary::before{content:"▸"; transition:transform .12s; font-size:10px}
  .claim details[open] summary::before{transform:rotate(90deg)}
  .claim summary:hover{color:var(--ink-soft)}
  .claim summary:focus-visible{outline:2px solid var(--accent); outline-offset:2px}
  .snippet{
    font-family:"IBM Plex Mono",monospace; font-size:12.5px; line-height:1.6; color:var(--ink-soft);
    background:var(--paper); border-left:3px solid var(--accent); border-radius:0 6px 6px 0;
    padding:10px 14px; margin:8px 0 2px; overflow-x:auto;
  }
  mark{background:var(--reported-wash); color:inherit; border-radius:2px; padding:0 1px}

  .inference{
    border:1px solid var(--line); border-left:4px solid var(--accent); border-radius:0 8px 8px 0;
    background:var(--accent-wash); padding:14px 18px; margin-top:12px;
  }
  .inference p{margin:0; max-width:66ch}
  .inference .note{font-size:12px; color:var(--ink-soft); margin-top:6px}
  .inference .note .ref{font-family:"IBM Plex Mono",monospace}

  ol.questions{margin:12px 0 0; padding-left:22px; max-width:66ch}
  ol.questions li{margin-bottom:8px; padding-left:4px}

  ul.gaps{list-style:none; margin:12px 0 0; padding:0; display:flex; flex-direction:column; gap:6px}
  ul.gaps li{
    display:flex; gap:10px; align-items:baseline; font-size:13.5px; color:var(--ink-soft);
    border-bottom:1px dashed var(--line-soft); padding-bottom:6px; max-width:74ch;
  }
  ul.gaps .topic{font-weight:600; color:var(--ink); white-space:nowrap}
  ul.gaps li.note{display:block}
  ul.gaps li.note::before{content:"※ "; color:var(--ink-faint)}

  .srcwrap{overflow-x:auto; margin-top:12px; border:1px solid var(--line); border-radius:8px}
  table.sources{border-collapse:collapse; width:100%; font-size:13px; min-width:560px}
  table.sources th{
    text-align:left; font-size:11px; text-transform:uppercase; letter-spacing:.07em;
    color:var(--ink-faint); font-weight:600; padding:9px 14px; border-bottom:1px solid var(--line);
    background:var(--panel);
  }
  table.sources td{padding:9px 14px; border-bottom:1px solid var(--line-soft); vertical-align:top; background:var(--panel)}
  table.sources tr:last-child td{border-bottom:none}
  table.sources .id{font-family:"IBM Plex Mono",monospace; font-size:11.5px; color:var(--ink-faint)}
  table.sources .dt{font-family:"IBM Plex Mono",monospace; font-size:12px; font-variant-numeric:tabular-nums; white-space:nowrap}
  table.sources a{color:var(--accent); text-decoration:none}
  table.sources a:hover{text-decoration:underline}

  .provenance{margin-top:40px; padding-top:16px; border-top:1px solid var(--line); font-size:12.5px; color:var(--ink-faint); max-width:70ch; font-style:italic}

  @media (max-width:820px){
    .app{grid-template-columns:1fr}
    .rail{position:static; height:auto; border-right:none; border-bottom:1px solid var(--line)}
    .detail{padding:26px 18px 60px}
  }
  @media (prefers-reduced-motion:reduce){ *{transition:none!important} }
</style>
</head>
<body>
<div class="app">
  <aside class="rail">
    <div class="brand"><span class="name">prebrief</span><span class="tag">library</span></div>
    <div class="search">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true"><circle cx="11" cy="11" r="7"></circle><path d="m20 20-3.5-3.5"></path></svg>
      <input id="q" type="search" placeholder="Search organizations and claims" aria-label="Search organizations and claims">
    </div>
    <div class="rail-label" id="listlabel">Briefs</div>
    <nav class="blist" id="blist" aria-labelledby="listlabel"></nav>
    <div class="rail-foot">
      <span id="totals"></span>
      <span>Every sentence traceable to a URL. Nothing asserted without a source.</span>
      <a class="mono" href="https://github.com/antoinemlt10/prebrief" target="_blank" rel="noopener">github.com/antoinemlt10/prebrief ↗</a>
    </div>
  </aside>
  <main class="detail" id="detail"></main>
</div>

<script>
const BRIEFS = /*__DATA__*/;

const SECTIONS = [
  {key:"identity",   title:"Who they are",             note:"Structural facts — the records that establish what this organization is."},
  {key:"movement",   title:"What moved",               note:"Dated activity inside the window, newest first."},
  {key:"check_first",title:"Check before the meeting", note:"Self-reported claims — verify before relying on them."}
];

// Mirrors brief.Relationship.sentence — same inference, same wording.
const REL = {
  buyer:        org => `${org} appears on the buying side: it holds a mandate and a budget for what we sell.`,
  investor:     org => `${org} appears on the capital side: it holds or could hold a position.`,
  competitor:   org => `${org} competes for the same contracts or the same customers.`,
  partner:      org => `${org} sits adjacent: a supplier, reseller, or joint-delivery relationship.`,
  regulator:    org => `${org} sets or enforces rules that bind how we operate.`,
  undetermined: org => `The public record does not establish how ${org} relates to us. Treat the relationship as an open question in the meeting.`
};

const $ = (sel, el=document) => el.querySelector(sel);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

let current = 0, query = "";
try { const saved = localStorage.getItem("prebrief.selected");
      const i = BRIEFS.findIndex(b => b.entity.slug === saved);
      if (i >= 0) current = i; } catch (e) {}

function claimById(brief){ const m = {}; brief.claims.forEach(c => m[c.id] = c); return m; }
function domain(url){ try { return new URL(url).hostname.replace(/^www\./,""); } catch(e){ return url; } }
function tierCounts(brief){
  const t = {filed:0, reported:0, "self-reported":0};
  brief.claims.forEach(c => { if (c.tier in t) t[c.tier]++; });
  return t;
}
function matches(brief, q){
  if (!q) return true;
  const hay = [brief.entity.name, brief.entity.description || "",
               ...brief.claims.map(c => c.text + " " + c.snippet)].join(" ").toLowerCase();
  return hay.includes(q);
}
function hl(text, q){
  if (!q) return esc(text);
  const i = text.toLowerCase().indexOf(q);
  if (i < 0) return esc(text);
  return esc(text.slice(0,i)) + "<mark>" + esc(text.slice(i, i+q.length)) + "</mark>" + esc(text.slice(i+q.length));
}

function renderList(){
  const list = $("#blist");
  const visible = BRIEFS.map((b,i)=>({b,i})).filter(({b}) => matches(b, query));
  if (!visible.length){ list.innerHTML = '<div class="nores">Nothing matches. The honest result.</div>'; return; }
  list.innerHTML = visible.map(({b,i}) => {
    const t = tierCounts(b), n = b.claims.length || 1;
    const bar = ["filed","reported","self-reported"].map(k =>
      t[k] ? `<span style="width:${(t[k]/n*100).toFixed(1)}%;background:var(--${k === "self-reported" ? "self" : k})"></span>` : ""
    ).join("");
    return `<button class="bcard" aria-current="${i === current}" data-i="${i}">
      <span class="org">${esc(b.entity.name)}</span>
      <span class="meta"><span class="pill kind">${esc(b.entity.kind)}</span>
        <span class="counts">${b.claims.length} claims · ${b.gaps.length} gaps</span></span>
      <span class="tierbar">${bar}</span>
    </button>`;
  }).join("");
  list.querySelectorAll(".bcard").forEach(el => el.addEventListener("click", () => select(+el.dataset.i)));
}

function select(i){
  current = i;
  try { localStorage.setItem("prebrief.selected", BRIEFS[i].entity.slug); } catch (e) {}
  renderList(); renderDetail();
  $("#detail").scrollIntoView({block:"start"});
}

function claimCard(c, q){
  const snip = c.snippet && c.snippet.trim();
  return `<article class="claim">
    <div class="row"><span class="chip ${esc(c.tier)}">${esc(c.tier)}</span>
      <span class="when">${esc(c.published || "undated")}</span></div>
    <p class="text">${hl(c.text, q)}</p>
    <div class="src"><a href="${esc(c.source_url)}" target="_blank" rel="noopener">${esc(c.source_title)} ↗</a></div>
    ${snip ? `<details><summary>Verbatim snippet</summary>
      <div class="snippet">${hl(snip, q)}</div></details>` : ""}
  </article>`;
}

function cap(s){ return s.charAt(0).toUpperCase() + s.slice(1); }

function renderDetail(){
  const b = BRIEFS[current], by = claimById(b), q = query;
  const e = b.entity;
  const relFn = REL[b.relationship.value] || REL.undetermined;

  const sectionsHtml = SECTIONS.map(s => {
    const ids = b.sections[s.key] || [];
    const cards = ids.map(id => by[id]).filter(Boolean).map(c => claimCard(c, q)).join("");
    if (s.key === "check_first" && !ids.length) return "";
    return `<section aria-label="${esc(s.title)}">
      <h2>${esc(s.title)}<span class="seccount">${ids.length}</span></h2>
      <p class="secnote">${esc(s.note)}</p>
      ${cards || `<div class="empty">Nothing found in the window.</div>`}
    </section>`;
  }).join("");

  const support = b.relationship.supported_by.map(id =>
    `<span class="ref">[${esc(id)}]</span>`).join(", ");

  const gapsHtml = [
    ...b.gaps.map(g => `<li><span class="topic">${esc(g.topic)}</span>
      <span>${g.searched.length ? "searched " + esc(g.searched.join(", ")) + ", nothing found" : "no source in this run covers it"}</span></li>`),
    ...b.run_notes.map(n => `<li class="note">${esc(n)}</li>`)
  ].join("");

  const srcRows = b.claims.map(c => `<tr>
      <td class="id">${esc(c.id)}</td>
      <td><a href="${esc(c.source_url)}" target="_blank" rel="noopener">${esc(c.source_title)}</a></td>
      <td><span class="chip ${esc(c.tier)}">${esc(c.tier)}</span></td>
      <td class="dt">${esc(c.published || "undated")}</td>
    </tr>`).join("");

  $("#detail").innerHTML = `
    <div class="crumb">briefs / ${esc(e.slug)} / ${esc(b.as_of)}</div>
    <h1>${esc(e.name)}</h1>
    <div class="headmeta">
      <span class="pill kind">${esc(e.kind)}</span>
      <span class="pill date">as of ${esc(b.as_of)}</span>
      <span class="pill date">${b.claims.length} sourced statements</span>
      ${e.thin ? '<span class="pill date">thin public record</span>' : ""}
    </div>
    ${e.description ? `<p class="desc">${esc(cap(e.description))}.</p>` : ""}
    <div class="headlinks">
      ${e.homepage ? `<a href="${esc(e.homepage)}" target="_blank" rel="noopener">${esc(domain(e.homepage))} ↗</a>` : ""}
      ${e.qid ? `<a href="https://www.wikidata.org/wiki/${esc(e.qid)}" target="_blank" rel="noopener">Wikidata ${esc(e.qid)} ↗</a>` : ""}
    </div>

    ${sectionsHtml.replace('</section>', `</section>
    <section aria-label="Why they matter">
      <h2>Why they matter</h2>
      <p class="secnote">The one inference in this brief. Everything else is sourced.</p>
      <div class="inference"><p>${esc(relFn(e.name))}</p>
        ${support ? `<div class="note">Resting on: ${support}</div>` : ""}</div>
    </section>`)}

    <section aria-label="Questions to ask">
      <h2>Questions to ask</h2>
      <p class="secnote">Derived from the gaps — a question is well-formed exactly when the public record cannot answer it.</p>
      <ol class="questions">${b.questions.map(x => `<li>${esc(x)}</li>`).join("")}</ol>
    </section>

    <section aria-label="What could not be found">
      <h2>What I could not find</h2>
      <ul class="gaps">${gapsHtml}</ul>
    </section>

    <section aria-label="Sources">
      <h2>Sources<span class="seccount">${b.claims.length}</span></h2>
      <div class="srcwrap"><table class="sources">
        <thead><tr><th>Claim ID</th><th>Source</th><th>Tier</th><th>Published</th></tr></thead>
        <tbody>${srcRows}</tbody>
      </table></div>
    </section>

    <p class="provenance">Nothing above is asserted without a source. Records marked
      <strong>filed</strong> come from a statutory record; <strong>reported</strong> from press;
      <strong>self-reported</strong> from the organization itself.</p>`;
}

function renderTotals(){
  const claims = BRIEFS.reduce((n,b) => n + b.claims.length, 0);
  const filed = BRIEFS.reduce((n,b) => n + b.claims.filter(c => c.tier === "filed").length, 0);
  $("#totals").textContent = `${BRIEFS.length} briefs · ${claims} sourced claims (${filed} filed)`;
  const dates = [...new Set(BRIEFS.map(b => b.as_of))].sort();
  $("#listlabel").textContent = dates.length === 1 ? `Briefs · as of ${dates[0]}` : "Briefs";
}

$("#q").addEventListener("input", e => {
  query = e.target.value.trim().toLowerCase();
  renderList(); renderDetail();
});

if (current >= BRIEFS.length) current = 0;
renderTotals(); renderList(); renderDetail();
</script>
</body>
</html>
'''
