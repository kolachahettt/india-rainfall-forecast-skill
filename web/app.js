/* forecast-trust — static one-pager.
   Charts are hand-built SVG: no library, no build step, works from file://.
   Charts re-render on resize so label text keeps its true pixel size instead
   of being scaled down by a viewBox on narrow screens. */
(() => {
"use strict";

const NS = "http://www.w3.org/2000/svg";
const $ = (s) => document.querySelector(s);

/* Reuse the script tag's own ?v= on every data request. Without it the JSON
   is cached independently of the code that reads it, so a re-export leaves
   the browser pairing new code with stale data — which fails in confusing
   places rather than at the fetch. */
const V = (() => {
  const src = document.currentScript && document.currentScript.src;
  const q = src && src.indexOf("?") >= 0 ? src.slice(src.indexOf("?")) : "";
  return q;
})();
const dataURL = (name) => `data/${name}${V}`;

/* Never let a chart be wider than the screen. Measuring a container mid-
   layout can return a stale width, and because these SVGs carry an
   explicit width attribute that then pins the document wider than the
   viewport and every section clips. */
const vwClamp = (holder) => Math.max(260, Math.min(
  holder.clientWidth || 640, document.documentElement.clientWidth));
const css = (v) => getComputedStyle(document.documentElement)
  .getPropertyValue(v).trim();
const fmt = (x, d = 3) => (x === null || x === undefined || Number.isNaN(x))
  ? "—" : Number(x).toFixed(d);
const pct = (x) => (x === null || x === undefined) ? "—" : Math.round(x * 100) + "%";

function e(tag, attrs = {}, parent) {
  const n = document.createElementNS(NS, tag);
  for (const k in attrs) n.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(n);
  return n;
}
function h(tag, attrs = {}, parent) {
  const n = document.createElement(tag);
  for (const k in attrs) {
    if (k === "text") n.textContent = attrs[k];
    else if (k === "html") n.innerHTML = attrs[k];
    else n.setAttribute(k, attrs[k]);
  }
  if (parent) parent.appendChild(n);
  return n;
}

const D = {};
const redrawers = [];
function register(fn) { redrawers.push(fn); fn(); }
let rt;
addEventListener("resize", () => {
  clearTimeout(rt);
  rt = setTimeout(() => redrawers.forEach((f) => { try { f(); } catch (_) {} }), 140);
});

/* ------------------------------------------------------------- line chart */
/* series: [{name, colour, pts:[[x,y]], band:[[x,lo,hi]]|null, label}] */
function lineChart(holder, o) {
  holder.innerHTML = "";
  const W = vwClamp(holder);
  const narrow = W < 460;
  const H = o.height || (narrow ? 250 : 330);
  const m = { t: 14, r: narrow ? 12 : (o.padRight || 54), b: 40, l: narrow ? 42 : 52 };
  const pw = W - m.l - m.r, ph = H - m.t - m.b;
  const svg = e("svg", { class: "chart", width: W, height: H,
    viewBox: `0 0 ${W} ${H}`, role: "img",
    "aria-label": o.aria || o.title || "chart" }, holder);

  const [x0, x1] = o.xDomain, [y0, y1] = o.yDomain;
  const X = (v) => m.l + (v - x0) / (x1 - x0) * pw;
  const Y = (v) => m.t + (1 - (v - y0) / (y1 - y0)) * ph;

  (o.yTicks || []).forEach((t) => {
    e("line", { class: "tickline", x1: m.l, x2: m.l + pw, y1: Y(t), y2: Y(t) }, svg);
    const tx = e("text", { class: "ticktext", x: m.l - 8, y: Y(t) + 4,
      "text-anchor": "end" }, svg);
    tx.textContent = o.yFmt ? o.yFmt(t) : t;
  });
  e("line", { class: "axisline", x1: m.l, x2: m.l + pw, y1: Y(y0), y2: Y(y0) }, svg);
  (o.xTicks || []).forEach((t) => {
    const tx = e("text", { class: "ticktext", x: X(t), y: m.t + ph + 18,
      "text-anchor": "middle" }, svg);
    tx.textContent = o.xFmt ? o.xFmt(t) : t;
  });
  if (o.xLabel) {
    const l = e("text", { class: "axlabel", x: m.l + pw / 2, y: H - 4,
      "text-anchor": "middle" }, svg);
    l.textContent = o.xLabel;
  }
  if (o.yLabel && !narrow) {
    const l = e("text", { class: "axlabel", x: -(m.t + ph / 2), y: 13,
      "text-anchor": "middle", transform: "rotate(-90)" }, svg);
    l.textContent = o.yLabel;
  }
  if (o.zeroLine !== undefined && o.zeroLine >= y0 && o.zeroLine <= y1) {
    e("line", { class: "axisline", x1: m.l, x2: m.l + pw,
      y1: Y(o.zeroLine), y2: Y(o.zeroLine) }, svg);
  }

  o.series.forEach((s) => {
    if (s.band && s.band.length) {
      const up = s.band.map((p) => `${X(p[0])},${Y(p[1])}`);
      const dn = s.band.slice().reverse().map((p) => `${X(p[0])},${Y(p[2])}`);
      e("polygon", { points: up.concat(dn).join(" "), fill: s.colour,
        "fill-opacity": 0.14, stroke: "none" }, svg);
    }
  });
  o.series.forEach((s) => {
    const pl = e("polyline",
      { points: s.pts.map((p) => `${X(p[0])},${Y(p[1])}`).join(" "),
        fill: "none", stroke: s.colour, "stroke-width": s.dash ? 1.7 : 2,
        "stroke-linejoin": "round", "stroke-linecap": "round" }, svg);
    /* a dashed series is a benchmark, not a measurement of the subject —
       keep it visually subordinate: thinner, no markers, lighter */
    if (s.dash) {
      pl.setAttribute("stroke-dasharray", s.dash);
      pl.setAttribute("stroke-opacity", "0.85");
    }
    /* markers only when the series is sparse enough for them to mean
       something — a dot on all 49 alpha steps is noise, not data */
    if (o.markers !== false && !s.dash && s.pts.length <= 12) {
      s.pts.forEach((p) => {
        e("circle", { cx: X(p[0]), cy: Y(p[1]), r: 4.2, fill: s.colour,
          stroke: css("--surface-1"), "stroke-width": 2 }, svg);
      });
    }
    if (!narrow && s.label !== false) {
      /* anchor the label where the series is most separated from its
         neighbours: at its peak for curves that converge at the ends */
      const anchor = o.labelAt === "peak"
        ? s.pts.reduce((a, b) => (b[1] > a[1] ? b : a))
        : s.pts[s.pts.length - 1];
      const atEnd = anchor === s.pts[s.pts.length - 1];
      const t = e("text", { class: "serieslabel",
        x: X(anchor[0]) + (atEnd ? 9 : 0),
        y: Y(anchor[1]) + (atEnd ? 4 : (s.labelDy === undefined ? -9 : s.labelDy)),
        "text-anchor": atEnd ? "start" : "middle", fill: s.colour }, svg);
      t.textContent = s.label || s.name;
    }
  });

  /* hover layer: crosshair + tooltip, snapped to the nearest x */
  if (o.hover !== false) {
    const g = e("g", { visibility: "hidden" }, svg);
    const vline = e("line", { class: "axisline", y1: m.t, y2: m.t + ph }, g);
    const box = e("rect", { rx: 5, fill: css("--surface-1"),
      stroke: css("--axis"), "stroke-width": 1 }, g);
    const txts = o.series.map(() => e("text", { class: "ticktext" }, g));
    const head = e("text", { class: "ticktext", "font-weight": "700" }, g);
    const xs = o.series[0].pts.map((p) => p[0]);
    const hit = e("rect", { x: m.l, y: m.t, width: pw, height: ph,
      fill: "transparent" }, svg);
    const move = (ev) => {
      const r = svg.getBoundingClientRect();
      const cx = (ev.touches ? ev.touches[0].clientX : ev.clientX) - r.left;
      const px = x0 + (cx - m.l) / pw * (x1 - x0);
      let best = xs[0];
      xs.forEach((v) => { if (Math.abs(v - px) < Math.abs(best - px)) best = v; });
      g.setAttribute("visibility", "visible");
      vline.setAttribute("x1", X(best)); vline.setAttribute("x2", X(best));
      head.textContent = (o.hoverHead || ((v) => String(v)))(best);
      const lines = o.series.map((s) => {
        const p = s.pts.find((q) => q[0] === best);
        return { c: s.colour, t: `${s.name}  ${p ? fmt(p[1], o.hoverDigits || 3) : "—"}` };
      });
      let wmax = head.getComputedTextLength ? head.getComputedTextLength() : 60;
      txts.forEach((t, i) => {
        t.textContent = lines[i].t; t.setAttribute("fill", lines[i].c);
        const w = t.getComputedTextLength ? t.getComputedTextLength() : 80;
        if (w > wmax) wmax = w;
      });
      const bw = wmax + 18, bh = 18 + lines.length * 15;
      let bx = X(best) + 12;
      if (bx + bw > m.l + pw) bx = X(best) - bw - 12;
      const by = m.t + 6;
      box.setAttribute("x", bx); box.setAttribute("y", by);
      box.setAttribute("width", bw); box.setAttribute("height", bh);
      head.setAttribute("x", bx + 9); head.setAttribute("y", by + 15);
      head.setAttribute("fill", css("--ink"));
      txts.forEach((t, i) => {
        t.setAttribute("x", bx + 9); t.setAttribute("y", by + 30 + i * 15);
      });
    };
    hit.addEventListener("mousemove", move);
    hit.addEventListener("touchmove", (ev) => { move(ev); }, { passive: true });
    hit.addEventListener("mouseleave", () => g.setAttribute("visibility", "hidden"));
  }
  return svg;
}

/* --------------------------------------------------------- range (window) */
function rangeChart(holder, o) {
  holder.innerHTML = "";
  const W = vwClamp(holder);
  const narrow = W < 460;
  const rowH = 26, H = o.rows.length * rowH + 58;
  const m = { t: 10, r: 14, b: 40, l: narrow ? 46 : 62 };
  const pw = W - m.l - m.r;
  const svg = e("svg", { class: "chart", width: W, height: H,
    viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": o.aria || "range chart" }, holder);
  const X = (v) => m.l + (v - o.xDomain[0]) / (o.xDomain[1] - o.xDomain[0]) * pw;

  (o.xTicks || []).forEach((t) => {
    e("line", { class: "tickline", x1: X(t), x2: X(t), y1: m.t,
      y2: m.t + o.rows.length * rowH }, svg);
    const tx = e("text", { class: "ticktext", x: X(t),
      y: m.t + o.rows.length * rowH + 18, "text-anchor": "middle" }, svg);
    tx.textContent = t;
  });
  o.rows.forEach((r, i) => {
    const y = m.t + i * rowH + rowH / 2;
    const lb = e("text", { class: "ticktext", x: m.l - 10, y: y + 4,
      "text-anchor": "end" }, svg);
    lb.textContent = r.label;
    e("rect", { x: X(r.from), y: y - 6, width: Math.max(2, X(r.to) - X(r.from)),
      height: 12, rx: 4, fill: r.colour, "fill-opacity": 0.85 }, svg);
    if (r.peak !== undefined) {
      e("circle", { cx: X(r.peak), cy: y, r: 4.6, fill: css("--surface-1"),
        stroke: r.colour, "stroke-width": 2.4 }, svg);
    }
  });
  if (o.xLabel) {
    const l = e("text", { class: "axlabel", x: m.l + pw / 2, y: H - 6,
      "text-anchor": "middle" }, svg);
    l.textContent = o.xLabel;
  }
  return svg;
}

/* --------------------------------------------------------------- tables */
function table(host, cols, rows, emphasis) {
  host.innerHTML = "";
  /* wide tables scroll sideways inside their card rather than stretching the
     document — squeezing 7 numeric columns into 375px makes them unreadable */
  host.classList.add("tablewrap");
  const t = h("table", {}, host);
  const th = h("thead", {}, t), tr = h("tr", {}, th);
  cols.forEach((c) => h("th", { text: c, scope: "col" }, tr));
  const tb = h("tbody", {}, t);
  rows.forEach((r) => {
    const x = h("tr", {}, tb);
    r.forEach((v, i) => h("td", { text: v, class: (emphasis === i ? "em" : "") }, x));
  });
  return t;
}

/* ============================================================ SECTION 1 */
function buildFinding() {
  const meta = D.meta, fbl = D.far;
  const rec = (thr, lead, truth = "IMD") => fbl.records.find(
    (r) => r.truth === truth && r.threshold_mm === thr && r.lead_days === lead);

  const p = $("#provenance");
  [["Model", meta.model], ["Truth", "IMD 0.25° gauge grid"],
   ["Period", `${meta.period_start} → ${meta.period_end}`],
   ["Sample", `${meta.n_points} grid cells · ${meta.n_point_days.toLocaleString()} cell-days`],
   ["Rainfall day", meta.rainfall_day]].forEach(([k, v]) => {
    const s = h("span", {}, p); h("b", { text: k + " " }, s);
    s.appendChild(document.createTextNode(v));
  });

  const l1 = rec(1.0, 1), l7 = rec(1.0, 7);
  const ppv1 = 1 - l1.FAR, ppv7 = 1 - l7.FAR;
  const gap1 = l1.NPV - ppv1, gap7 = l7.NPV - ppv7;
  const P = D.persist, BH = meta.bias_headline;
  const prec = (thr, lead) => P.records.find(
    (r) => r.threshold_mm === thr && r.lead_days === lead);

  /* The frequency bias is the finding. Both of the things the page used to
     lead with -- the asymmetry between the directions, and the persistence
     loss at lead 1 -- are consequences of it, measured independently. */
  $("#headSub").textContent =
    `Over ${meta.n_point_days.toLocaleString()} cell-days at ${meta.n_points} ` +
    `locations, ECMWF's model called for rain on ` +
    `${Math.round(BH.forecast_wet_rate * 100)}% of days. Rain fell on ` +
    `${Math.round(BH.observed_wet_rate * 100)}%. That gap — a frequency bias ` +
    `of ${BH.bias.toFixed(2)} — is what produces everything else on this page.`;

  const bh = $("#biasHero");
  const bhl = h("div", {}, bh);
  h("p", { class: "bh-num", text: BH.bias.toFixed(2) + "×" }, bhl);
  h("p", { class: "bh-cap", text: "wet days forecast for every wet day that happened" }, bhl);
  const bhb = h("p", { class: "bh-body" }, bh);
  bhb.innerHTML =
    `The model called rain on <b>${(BH.forecast_wet_rate * 100).toFixed(1)}%</b> ` +
    `of days. Rain fell on <b>${(BH.observed_wet_rate * 100).toFixed(1)}%</b>. ` +
    `That is <b>${BH.excess_wet_days.toLocaleString()}</b> more wet days than ` +
    `happened. The bias barely moves with lead time — ` +
    `${BH.bias_by_lead["1"].toFixed(2)} at one day ahead, ` +
    `${BH.bias_by_lead["7"].toFixed(2)} at seven — so it is a property of the ` +
    `model, not of how far ahead it is reaching.`;

  $("#findingLede").textContent =
    `Everything below follows from that one number. A model that calls rain ` +
    `too often will be wrong more often when it says rain, and right more ` +
    `often when it says dry. It will also lose to any rule that calls rain ` +
    `the right number of times. Both of those happen here, and each was ` +
    `measured separately.`;

  /* consequence one: the two directions */
  const hd = $("#heroDirs");
  [["wet", "When it says rain", ppv1, "of the time it rains"],
   ["dry", "When it says dry", l1.NPV, "of the time it stays dry"]]
    .forEach(([cls, when, val, tail]) => {
      const c = h("div", { class: "dir " + cls }, hd);
      h("p", { class: "dir-when", text: when + ", one day ahead" }, c);
      h("p", { class: "dir-pct", text: Math.round(val * 100) + "%" }, c);
      h("p", { class: "dir-tail", text: tail }, c);
    });

  $("#asymLede").textContent =
    `A one-day-ahead rain forecast was right ${Math.round(ppv1 * 100)}% of ` +
    `the time and a dry forecast ${Math.round(l1.NPV * 100)}% — a gap of ` +
    `${Math.round(gap1 * 100)} percentage points from the same model on the ` +
    `same day. Lead time does not treat the two alike. Over a week the dry ` +
    `direction loses only ${Math.round((l1.NPV - l7.NPV) * 100)} points ` +
    `(${Math.round(l1.NPV * 100)}% to ${Math.round(l7.NPV * 100)}%) while the ` +
    `rain direction loses ${Math.round((ppv1 - ppv7) * 100)} ` +
    `(${Math.round(ppv1 * 100)}% to ${Math.round(ppv7 * 100)}%), so the gap ` +
    `widens from ${gap1.toFixed(2)} to ${gap7.toFixed(2)}. Saying "lead time ` +
    `barely matters" is true of the dry forecast and false of the rain one.`;

  const ex = D.methods.asymmetry;
  $("#asymWhy").textContent =
    `Two things drive it, and neither is the model's handling of rain. Rain ` +
    `falls on ${Math.round(BH.observed_wet_rate * 100)}% of days here, so ` +
    `"dry" is the common outcome and a forecast of dry starts from a ` +
    `position most days vindicate. On top of that the model calls rain ` +
    `${Math.round(BH.excess_pct)}% more often than rain happens, which loads ` +
    `the extra calls onto the rarer side and drags the rain direction down ` +
    `further. The same asymmetry would appear for a well-built model in any ` +
    `dry climate. The test is whether it survives where rain is common, and ` +
    `it mostly does: the dry direction is the more reliable one at ` +
    `${ex.n_cells - ex.n_exception_cells} of the ${ex.n_cells} cells. The ` +
    `exceptions are the two wettest — ` +
    ex.exceptions.map((e) => `${e.lat}°N ${e.lon}°E (rain on `
      + `${Math.round(e.wet_rate * 100)}% of days)`).join(" and ") +
    ` — where rain is the usual outcome and the directions swap round.`;

  /* consequence two: the persistence benchmark, and the lead-1 loss */
  const WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven"];
  const L1 = P.lead1_loss, pl1 = prec(1.0, 1);
  /* where ECMWF's rain-direction margin over persistence is largest --
     derived, so the sentence cannot drift if the numbers move */
  const best = P.records.filter((r) => r.threshold_mm === 1.0)
    .reduce((a, b) => (b.diff.PPV > a.diff.PPV ? b : a));
  $("#persistText").innerHTML =
    `Persistence — "it will do at the target what it did ` +
    `<em>L</em> days before" — calls rain on exactly as many days as it ` +
    `rains, because it is made of observed days: its frequency bias is ` +
    `<b>${pl1.persistence.BIAS.toFixed(2)}</b> against ECMWF's ` +
    `<b>${pl1.ecmwf.BIAS.toFixed(2)}</b>. That costs it detection — it ` +
    `catches ${Math.round(pl1.persistence.POD * 100)}% of rain days against ` +
    `ECMWF's ${Math.round(pl1.ecmwf.POD * 100)}% — but it buys accuracy in ` +
    `the rain direction. At one day ahead persistence is right ` +
    `<b>${Math.round(L1.persistence_PPV * 100)}%</b> of the time when it says ` +
    `rain, against ECMWF's <b>${Math.round(L1.ecmwf_PPV * 100)}%</b>: a gap ` +
    `of ${Math.abs(L1.difference * 100).toFixed(1)} points, 95% CI ` +
    `${Math.abs(L1.ci_hi * 100).toFixed(1)} to ` +
    `${Math.abs(L1.ci_lo * 100).toFixed(1)}, with ECMWF ahead in ` +
    `${Math.round(L1.ecmwf_ahead_in_draws * 4000)} of 4,000 bootstrap draws. ` +
    `<strong>At one day ahead you can beat this model's rain forecast by ` +
    `asking whether it rained yesterday.</strong>`;

  $("#persistBalance").innerHTML =
    `That is one metric at one lead, and it is the only place ECMWF loses. ` +
    `At the same lead it wins the dry direction by ` +
    `${(L1.ecmwf_wins_NPV_by * 100).toFixed(1)} points, overall skill by ` +
    `${(L1.ecmwf_wins_HSS_by * 100).toFixed(1)}, and detection by ` +
    `${(L1.ecmwf_wins_POD_by * 100).toFixed(0)}. From two days ahead it wins ` +
    `the rain direction as well, by up to ` +
    `${(best.diff.PPV * 100).toFixed(1)} points at day ` +
    `${WORDS[best.lead_days]}. ` +
    `<strong>ECMWF's advantage at one day ahead is in the dry direction and ` +
    `in overall skill, not the wet one.</strong> Murphy (1992): a skill score ` +
    `has to be referenced against the most accurate naive method available, ` +
    `and for daily rainfall occurrence at short lead that is persistence, ` +
    `not climatology.`;

  /* Where the forecast stops beating the persistence ceiling. This has to
     be read off the STRATIFIED score, not the pooled one: pooling flatters
     persistence more than it flatters the model, so the pooled comparison
     puts the crossing a day too early. Both are stated. */
  const HJ = D.hj, hx1 = HJ.crossing["1.0"], hx25 = HJ.crossing["2.5"];
  const belowS = hx1.first_lead_below_stratified;
  const belowP = hx1.first_lead_below_pooled;
  const lastAbove = belowS ? belowS - 1 : 7;
  $("#fiveDayHead").textContent = belowS
    ? `Where the forecast stops adding anything: about ${WORDS[lastAbove]} days`
    : "The forecast stays above the persistence ceiling at every lead";
  $("#fiveDayText").innerHTML =
    `The best <em>any</em> persistence rule could do — repeating the most ` +
    `recent observation at every lead, including where that is information ` +
    `you would not actually have — is the ceiling on this comparison. ` +
    `Scored the way a skill score should be, location by location against ` +
    `each location's own climatology, that ceiling is ` +
    `<b>${hx1.ceiling_stratified.toFixed(3)}</b> on the Heidke Skill Score. ` +
    `ECMWF is above it through day ${WORDS[lastAbove]} ` +
    `(${hx1.ecmwf_stratified[lastAbove - 1].toFixed(3)})` +
    (belowS
      ? ` and below it at day ${WORDS[belowS]} ` +
        `(${hx1.ecmwf_stratified[belowS - 1].toFixed(3)}). ` +
        `<strong>Beyond about ${WORDS[lastAbove]} days its overall skill is ` +
        `no better than knowing yesterday's weather.</strong>`
      : " and at every lead out to seven days.") +
    ` At the stricter ≥2.5 mm threshold it holds the line all the way: ` +
    `${hx25.ecmwf_stratified[6].toFixed(3)} at day seven against a ceiling ` +
    `of ${hx25.ceiling_stratified.toFixed(3)} — a dead heat rather than a ` +
    `win. <a href="#hj">Pooled scores put the ≥1 mm crossing a day earlier, ` +
    `at day ${WORDS[belowP]}, because pooling flatters the naive benchmark ` +
    `more than it flatters the model — see the methods note.</a>`;

  $("#scopeText").textContent = meta.scope_caveat;

  const pd = fbl.paired_lead_difference.find((r) => r.threshold_mm === 1.0);
  $("#pairedText").textContent =
    `The confidence bands for day 1 and day 7 overlap, which on its own settles ` +
    `nothing. But both leads are scored on the same days in the same places, so the ` +
    `comparison to make is the paired one: false alarm ratio rises by ` +
    `${fmt(pd.difference, 3)} from day 1 to day 7, 95% CI ${fmt(pd.ci_lo, 3)} to ` +
    `${fmt(pd.ci_hi, 3)}. That excludes zero, so the upward trend is real — it is ` +
    `just small. Adjacent leads (day 3 versus day 4) remain indistinguishable.`;

  /* both directions, national, by lead, each against its persistence
     benchmark. Four lines is the most this chart can carry, but omitting the
     benchmark would hide the one result that goes against the model. */
  register(() => {
    lineChart($("#chartDirs"), {
      xDomain: [1, 7], yDomain: [0.45, 1.0], xTicks: meta.leads,
      yTicks: [0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
      yFmt: (v) => Math.round(v * 100) + "%",
      xLabel: "lead time (days ahead)", yLabel: "how often the forecast is right",
      hoverHead: (v) => `Lead ${v} day${v > 1 ? "s" : ""}`,
      aria: "ECMWF's dry direction stays near 95% at every lead and beats "
          + "persistence throughout; its rain direction falls from 58% to "
          + "52% and is below persistence at one day ahead, above it from "
          + "two days on",
      series: [
        { name: "says dry → stays dry", colour: css("--s1"), label: "says dry",
          pts: meta.leads.map((L) => [L, rec(1.0, L).NPV]),
          band: meta.leads.map((L) => [L, rec(1.0, L).NPV_lo, rec(1.0, L).NPV_hi]) },
        { name: "says rain → rains", colour: css("--s2"), label: "says rain",
          pts: meta.leads.map((L) => [L, 1 - rec(1.0, L).FAR]),
          band: meta.leads.map((L) => [L, 1 - rec(1.0, L).FAR_hi,
                                          1 - rec(1.0, L).FAR_lo]) },
        { name: "yesterday, says dry", colour: css("--s1"), dash: "5 4",
          label: false,
          pts: meta.leads.map((L) => [L, prec(1.0, L).persistence.NPV]) },
        { name: "yesterday, says rain", colour: css("--s2"), dash: "5 4",
          label: false,
          pts: meta.leads.map((L) => [L, prec(1.0, L).persistence.PPV]) },
      ],
    });
  });
  const lgd = $("#legendDirs");
  [["ECMWF says dry → it stayed dry", css("--s1"), false],
   ["ECMWF says rain → it rained", css("--s2"), false],
   ["persistence, dry direction", css("--s1"), true],
   ["persistence, rain direction", css("--s2"), true]]
    .forEach(([nm, colour, dashed]) => {
      const li = h("li", {}, lgd);
      const sw = h("span", { class: "swatch line" + (dashed ? " dash" : "") }, li);
      if (dashed) {
        sw.style.background =
          `repeating-linear-gradient(90deg, ${colour} 0 5px,`
          + ` transparent 5px 9px)`;
      } else {
        sw.style.background = colour;
      }
      li.appendChild(document.createTextNode(nm));
    });

  const ci = (v, lo, hi) => `${v > 0 ? "+" : ""}${fmt(v)} (${fmt(lo)} – ${fmt(hi)})`;
  table($("#tablePersist"),
    ["Wet day", "Lead", "ECMWF rain", "Yesterday rain", "Rain difference (95% CI)",
     "ECMWF dry", "Yesterday dry", "ECMWF HSS", "Yesterday HSS",
     "HSS difference (95% CI)"],
    P.records.map((r) => [`≥${r.threshold_mm} mm`, r.lead_days,
      fmt(r.ecmwf.PPV), fmt(r.persistence.PPV),
      ci(r.diff.PPV, r.diff.PPV_lo, r.diff.PPV_hi),
      fmt(r.ecmwf.NPV), fmt(r.persistence.NPV),
      fmt(r.ecmwf.HSS), fmt(r.persistence.HSS),
      ci(r.diff.HSS, r.diff.HSS_lo, r.diff.HSS_hi)]), 4);

  /* HSS is shown twice on purpose: the pooled figure for continuity with
     everything published before, and the stratified one because the pooled
     figure is inflated by base-rate heterogeneity across the 139 cells. */
  const hjOf = (thr, lead) => HJ.records.find(
    (r) => r.threshold_mm === thr && r.lead_days === lead);
  table($("#tableFar"),
    ["Wet day", "Lead", "FAR", "FAR 95% CI", "POD", "CSI", "HSS (pooled)",
     "HSS (stratified)", "Bias", "Hits", "False alarms", "Misses"],
    fbl.records.filter((r) => r.truth === "IMD")
      .sort((a, b) => a.threshold_mm - b.threshold_mm || a.lead_days - b.lead_days)
      .map((r) => [`≥${r.threshold_mm} mm`, r.lead_days, fmt(r.FAR),
        `${fmt(r.FAR_lo)} – ${fmt(r.FAR_hi)}`, fmt(r.POD), fmt(r.CSI),
        fmt(r.HSS), fmt(hjOf(r.threshold_mm, r.lead_days).HSS.stratified),
        fmt(r.BIAS, 2), r.hits.toLocaleString(),
        r.false_alarms.toLocaleString(), r.misses.toLocaleString()]), 2);
}

/* ============================================================ SECTION 2 */
function buildCostLoss() {
  const cl = D.cl;
  const sum = (thr, lead) => cl.summary.find(
    (s) => s.threshold_mm === thr && s.lead_days === lead);
  const s1 = sum(1.0, 1), s7 = sum(1.0, 7);

  $("#clLede").textContent =
    `Cost–loss ratio α is what protective action costs divided by the loss it avoids. ` +
    `For every lead from one to seven days, acting on the forecast beats the best ` +
    `climatological rule over roughly α = ${fmt(s1.alpha_min_positive, 2)} to ` +
    `${fmt(s1.alpha_max_positive, 2)}. What erodes with lead time is the size of the ` +
    `benefit, not whether there is one: peak value falls from ${fmt(s1.max_V, 2)} at ` +
    `one day to ${fmt(s7.max_V, 2)} at seven. Even at its best the forecast captures ` +
    `about two-thirds of what perfect foresight would be worth.`;

  const picks = [[1, css("--s1")], [4, css("--s2")], [7, css("--s3")]];
  register(() => {
    lineChart($("#chartCl"), {
      xDomain: [0, 1], yDomain: [-0.4, 0.7],
      xTicks: [0, 0.2, 0.4, 0.6, 0.8, 1.0],
      yTicks: [-0.4, -0.2, 0, 0.2, 0.4, 0.6],
      xFmt: (v) => v.toFixed(1), yFmt: (v) => v.toFixed(1), zeroLine: 0,
      xLabel: "cost–loss ratio α  (cost of acting ÷ loss avoided)",
      yLabel: "value vs climatology", padRight: 24, hover: false,
      labelAt: "peak",
      aria: "Value peaks near the climatological base rate and declines with lead time",
      /* the three peaks sit within 0.08 of each other, so only the outer two
         are direct-labelled; the legend carries the middle one */
      series: picks.map(([L, colour], i) => {
        const c = cl.curves.find((x) => x.threshold_mm === 1.0 && x.lead_days === L);
        const pts = c.alpha.map((a, j) => [a, c.V[j]]).filter((p) => p[1] >= -0.4);
        return { name: `lead ${L}`, colour, pts,
          label: i === 1 ? false : `day ${L}`,
          labelDy: i === 0 ? -10 : 20 };
      }),
    });
  });
  const lg = $("#legendCl");
  picks.forEach(([L, colour]) => {
    const li = h("li", {}, lg);
    h("span", { class: "swatch line" }, li).style.background = colour;
    li.appendChild(document.createTextNode(`lead ${L} day${L > 1 ? "s" : ""} (wet day ≥1 mm)`));
  });
  h("li", { text: "above the zero line = worth acting on" }, lg)
    .style.color = css("--muted");

  register(() => {
    rangeChart($("#chartClWindow"), {
      xDomain: [0, 1], xTicks: [0, 0.2, 0.4, 0.6, 0.8, 1.0],
      xLabel: "cost–loss ratio α", aria: "Window of cost-loss ratios where the forecast pays",
      rows: [1, 2, 3, 4, 5, 6, 7].map((L) => {
        const s = sum(1.0, L);
        return { label: `day ${L}`, from: s.alpha_min_positive,
          to: s.alpha_max_positive, peak: s.argmax_alpha, colour: css("--s1") };
      }),
    });
  });

  table($("#tableCl"),
    ["Wet day", "Lead", "α window where it pays", "Peak value", "at α", "V(α=0.10)", "V(α=0.30)"],
    cl.summary.map((s) => {
      const g = (a) => { const c = s.ci_points.find((p) => p.alpha === a);
        return c ? `${fmt(c.V, 2)} (${fmt(c.V_lo, 2)}–${fmt(c.V_hi, 2)})` : "—"; };
      return [`≥${s.threshold_mm} mm`, s.lead_days,
        `${fmt(s.alpha_min_positive, 2)} – ${fmt(s.alpha_max_positive, 2)}`,
        fmt(s.max_V, 3), fmt(s.argmax_alpha, 2), g(0.1), g(0.3)];
    }), 3);

  const ul = $("#clAssumptions");
  cl.assumptions.forEach((a) => h("li", { text: a }, ul));
}

/* ============================================================ SECTION 3 */
function buildSeasonal() {
  const sm = D.season.records;
  const seasons = [...new Set(sm.map((r) => r.season))].sort();
  const mon = seasons.find((s) => /monsoon \(JJAS\)/.test(s));
  const non = seasons.find((s) => s !== mon);
  const get = (se, thr, lead) => sm.find(
    (r) => r.season === se && r.threshold_mm === thr && r.lead_days === lead);

  const m1 = get(mon, 1.0, 1), n1 = get(non, 1.0, 1);
  $("#seasonLede").textContent =
    `In the monsoon it rains on ${pct(m1.base_rate)} of days and ${pct(m1.FAR)} of rain ` +
    `forecasts are false alarms. Outside it, rain falls on just ${pct(n1.base_rate)} of ` +
    `days and the false alarm ratio rises to ${pct(n1.FAR)} — one in two. Yet the Heidke ` +
    `Skill Score moves the other way: ${fmt(n1.HSS, 2)} out of season against ` +
    `${fmt(m1.HSS, 2)} in it.`;
  $("#seasonWhy").textContent =
    `HSS credits correct “no rain” calls. When it rains on only ${pct(n1.base_rate)} of ` +
    `days those are nearly free, so a dry season inflates the score without the ` +
    `forecast being more useful. The farmer never experiences a correct negative as a ` +
    `benefit — they experience the false alarm as a wasted spray. Out of season that ` +
    `error is both more likely and degrades faster with lead time: false alarm ratio ` +
    `climbs ${fmt(get(non, 1.0, 7).FAR - n1.FAR, 3)} from day 1 to day 7, against ` +
    `${fmt(get(mon, 1.0, 7).FAR - m1.FAR, 3)} during the monsoon.`;

  /* Both seasonal HSS figures are pooled across the 139 cells, so both carry
     the base-rate inflation described in the methods. Checked, because the
     inversion is this section's entire claim: it survives. */
  const si = D.hj.seasonal_inversion, ex1 = si.example_lead1;
  $("#seasonHJ").innerHTML =
    `Both HSS figures here are pooled across the 139 cells, which inflates ` +
    `them. <a href="#hj">Scoring each cell against its own climatology and ` +
    `then averaging</a> lowers both — at one day ahead, non-monsoon ` +
    `${ex1.non_monsoon_pooled.toFixed(3)} → ` +
    `${ex1.non_monsoon_stratified.toFixed(3)} and monsoon ` +
    `${ex1.monsoon_pooled.toFixed(3)} → ` +
    `${ex1.monsoon_stratified.toFixed(3)} — but it does not reverse them. ` +
    `The inversion holds at ${si.holds_stratified} of ${si.n_cells} ` +
    `threshold-and-lead combinations either way, so it is a real property of ` +
    `the metric and not an artefact of pooling.`;

  const pal = [[mon, css("--s1")], [non, css("--s2")]];
  const holder = $("#chartSeason");
  register(() => {
    holder.innerHTML = "";
    const grid = h("div", {}, holder);
    grid.style.display = "grid";
    grid.style.gap = "1rem";
    grid.style.gridTemplateColumns = holder.clientWidth >= 700 ? "1fr 1fr" : "1fr";
    const panels = [
      { key: "FAR", dom: [0.3, 0.65], ticks: [0.3, 0.4, 0.5, 0.6],
        title: "False alarm ratio — higher is WORSE" },
      { key: "HSS", dom: [0.25, 0.6], ticks: [0.3, 0.4, 0.5, 0.6],
        title: "Heidke Skill Score — higher is BETTER" },
    ];
    panels.forEach((p) => {
      const cell = h("div", {}, grid);
      const cap = h("p", { class: "chart-sub", text: p.title }, cell);
      cap.style.margin = "0 0 .35rem"; cap.style.fontWeight = "620";
      cap.style.color = css("--ink-2");
      const box = h("div", {}, cell);
      lineChart(box, {
        xDomain: [1, 7], yDomain: p.dom, xTicks: [1, 2, 3, 4, 5, 6, 7],
        yTicks: p.ticks, yFmt: (v) => v.toFixed(2), height: 250,
        xLabel: "lead (days)", padRight: 16,
        hoverHead: (v) => `Lead ${v} day${v > 1 ? "s" : ""}`,
        aria: `${p.key} by lead time for monsoon and non-monsoon`,
        series: pal.map(([se, colour]) => ({
          name: se.replace(/\s*\(.*\)/, ""), colour, label: false,
          pts: [1, 2, 3, 4, 5, 6, 7].map((L) => [L, get(se, 1.0, L)[p.key]]),
        })),
      });
    });
  });
  const lg = $("#legendSeason");
  pal.forEach(([se, colour]) => {
    const li = h("li", {}, lg);
    h("span", { class: "swatch line" }, li).style.background = colour;
    li.appendChild(document.createTextNode(se));
  });

  table($("#tableSeason"),
    ["Season", "Wet day", "Lead", "Base rate", "FAR", "FAR 95% CI", "POD", "CSI", "HSS", "Bias"],
    sm.sort((a, b) => a.season.localeCompare(b.season)
      || a.threshold_mm - b.threshold_mm || a.lead_days - b.lead_days)
      .map((r) => [r.season, `≥${r.threshold_mm} mm`, r.lead_days, pct(r.base_rate),
        fmt(r.FAR), `${fmt(r.FAR_lo)} – ${fmt(r.FAR_hi)}`, fmt(r.POD),
        fmt(r.CSI), fmt(r.HSS), fmt(r.BIAS, 2)]), 4);
}

/* ============================================================ SECTION 5 */
function buildEra5() {
  const fbl = D.far, xm = D.cross;
  const rec = (truth, L) => fbl.records.find(
    (r) => r.truth === truth && r.threshold_mm === 1.0 && r.lead_days === L);
  const ppv = (r) => 1 - r.FAR;
  const d1 = ppv(rec("ERA5", 1)) - ppv(rec("IMD", 1));
  const n1 = rec("ERA5", 1).NPV - rec("IMD", 1).NPV;

  $("#era5Lede").textContent =
    `Rain gauges are scarce and reanalyses are convenient, so it is tempting ` +
    `to verify against ERA5. Doing that here would have moved the rain ` +
    `direction by ${Math.round(d1 * 100)} percentage points — from ` +
    `${Math.round(ppv(rec("IMD", 1)) * 100)}% right up to ` +
    `${Math.round(ppv(rec("ERA5", 1)) * 100)}% — while moving the dry ` +
    `direction by ${Math.round(Math.abs(n1) * 100)} ` +
    `${Math.round(Math.abs(n1) * 100) === 1 ? "point" : "points"}, slightly ` +
    `the wrong way. A reanalysis does not make the forecast look uniformly better: it ` +
    `flatters precisely the direction that was already the weak one, and ` +
    `leaves the trustworthy direction alone. Any study reporting only a false ` +
    `alarm ratio against reanalysis truth is reporting the distorted half.`;

  const pal = [["IMD", css("--s1"), "IMD gauge truth"],
               ["ERA5", css("--s2"), "ERA5 reanalysis truth"]];
  const panels = [
    { key: "rain", title: "When it says rain — higher is better",
      get: (t2, L) => ppv(rec(t2, L)),
      lo: (t2, L) => 1 - rec(t2, L).FAR_hi, hi: (t2, L) => 1 - rec(t2, L).FAR_lo,
      dom: [0.45, 0.95], ticks: [0.5, 0.6, 0.7, 0.8, 0.9] },
    { key: "dry", title: "When it says dry — higher is better",
      get: (t2, L) => rec(t2, L).NPV,
      lo: (t2, L) => rec(t2, L).NPV_lo, hi: (t2, L) => rec(t2, L).NPV_hi,
      dom: [0.45, 0.95], ticks: [0.5, 0.6, 0.7, 0.8, 0.9] },
  ];
  const holder = $("#chartEra5");
  register(() => {
    holder.innerHTML = "";
    const grid = h("div", {}, holder);
    grid.style.display = "grid";
    grid.style.gap = "1rem";
    grid.style.gridTemplateColumns =
      holder.clientWidth >= 700 ? "1fr 1fr" : "1fr";
    panels.forEach((pn) => {
      const cell = h("div", {}, grid);
      const cap = h("p", { class: "chart-sub", text: pn.title }, cell);
      cap.style.cssText = "margin:0 0 .35rem;font-weight:620";
      cap.style.color = css("--ink-2");
      lineChart(h("div", {}, cell), {
        xDomain: [1, 7], yDomain: pn.dom, xTicks: D.meta.leads,
        yTicks: pn.ticks, yFmt: (v) => Math.round(v * 100) + "%",
        height: 250, xLabel: "lead (days)", padRight: 16,
        hoverHead: (v) => `Lead ${v} day${v > 1 ? "s" : ""}`,
        aria: `${pn.key} direction, scored against gauges and against ERA5`,
        series: pal.map(([t2, colour, nm]) => ({
          name: nm, colour, label: false,
          pts: D.meta.leads.map((L) => [L, pn.get(t2, L)]),
          band: D.meta.leads.map((L) => [L, pn.lo(t2, L), pn.hi(t2, L)]),
        })),
      });
    });
  });
  const lg = $("#legendEra5");
  pal.forEach(([, colour, nm]) => {
    const li = h("li", {}, lg);
    h("span", { class: "swatch line" }, li).style.background = colour;
    li.appendChild(document.createTextNode(nm));
  });

  table($("#tableEra5"),
    ["Lead", "Says rain → rained (gauge)", "(ERA5)", "shift",
     "Says dry → stayed dry (gauge)", "(ERA5)", "shift"],
    D.meta.leads.map((L) => {
      const i = rec("IMD", L), e = rec("ERA5", L);
      return [L, fmt(ppv(i)), fmt(ppv(e)),
        (ppv(e) - ppv(i) >= 0 ? "+" : "") + fmt(ppv(e) - ppv(i)),
        fmt(i.NPV), fmt(e.NPV),
        (e.NPV - i.NPV >= 0 ? "+" : "") + fmt(e.NPV - i.NPV)];
    }), 3);

  const ic = xm.records.find((r) => r.model === "ICON" && r.threshold_mm === 1.0 && r.lead_days === 1);
  const gf = xm.records.find((r) => r.model === "GFS" && r.threshold_mm === 1.0 && r.lead_days === 1);
  $("#selfVerifyText").textContent =
    `ERA5 is ECMWF's own reanalysis, produced with the same IFS model family as the ` +
    `forecast being scored — so part of the gap could simply be a model being marked ` +
    `against itself. That is testable: run the same comparison for two models that ` +
    `share nothing with ERA5. DWD's ICON and NCEP's GFS both show a smaller gap than ` +
    `ECMWF, significantly so at every lead — but only by ${fmt(ic.pct_of_ecmwf_gap, 0)}% ` +
    `and ${fmt(gf.pct_of_ecmwf_gap, 0)}% respectively. Self-verification is real and it ` +
    `is the small part; the rest is ERA5 simply being too wet, which flatters every ` +
    `model about equally.`;
  $("#era5Verdict").textContent = xm.verdict;

  table($("#tableCross"),
    ["Model", "Lead", "FAR vs gauge", "FAR vs ERA5", "Gap", "vs ECMWF gap", "95% CI"],
    xm.records.filter((r) => r.threshold_mm === 1.0)
      .sort((a, b) => a.lead_days - b.lead_days
        || ["ECMWF", "ICON", "GFS"].indexOf(a.model) - ["ECMWF", "ICON", "GFS"].indexOf(b.model))
      .map((r) => [r.model === "ECMWF" ? "ECMWF (made ERA5)" : r.model, r.lead_days,
        fmt(r.far_imd), fmt(r.far_era5), fmt(r.gap),
        r.diff_vs_ecmwf === undefined ? "—" : `${fmt(r.diff_vs_ecmwf)} (${fmt(r.pct_of_ecmwf_gap, 0)}%)`,
        r.diff_ci_lo === undefined ? "—" : `${fmt(r.diff_ci_lo)} – ${fmt(r.diff_ci_hi)}`]), 4);
}

/* ============================================================ SECTION 6 */
function buildMethods() {
  const meta = D.meta, me = D.methods;
  const defs = $("#methodDefs");
  [[`Forecast`, `${meta.model}, pinned. Not <code>best_match</code>, which silently switches model by location and date.`],
   [`Truth`, `${meta.truth}, reconstructed from IMD's dated real-time grid files.`],
   [`Rainfall day`, `${meta.rainfall_day}. Verified empirically: shifting the labels by ±1 or ±2 days degrades every metric.`],
   [`Sample`, `${meta.n_points} cells on a 1.5° lattice over IMD land cells; ${meta.n_point_days.toLocaleString()} cell-days.`],
   [`Wet day`, `${meta.thresholds_mm.map((t) => "≥" + t + " mm").join(" and ")}.`],
   [`Uncertainty`, meta.uncertainty + "."],
  ].forEach(([k, v]) => h("li", { html: `<strong>${k}.</strong> ${v}` }, defs));

  $("#spatialText").textContent =
    `Rainfall at two Indian locations is correlated even when they are far apart — the ` +
    `monsoon keeps the country partly in step — so treating ${meta.n_points} cells as ` +
    `${meta.n_points} independent samples would make every interval about half as wide ` +
    `as it should be. Resampling whole ${me.spatial.block_degrees}° blocks instead ` +
    `leaves roughly ${me.spatial.effective_independent_locations} effectively ` +
    `independent locations. Correlation within a single location over time needs no ` +
    `special handling: a cell's whole time series moves with its block.`;

  table($("#tableSpatial"), ["Separation", "Pairs", "Mean correlation"],
    me.spatial.wet_dry_correlation_vs_distance.map(
      (b) => [`${b.km_from}–${b.km_to} km`, b.pairs.toLocaleString(), fmt(b.mean_r, 3)]), 2);

  /* ---- Hamill & Juras: how much of the pooled skill is geography? ---- */
  const HJ = D.hj;
  const hjr = (thr, L) => HJ.records.find(
    (r) => r.threshold_mm === thr && r.lead_days === L);
  const h1 = hjr(1.0, 1), h7 = hjr(1.0, 7), bs = HJ.base_rate_spread;

  $("#hjIntro").innerHTML =
    `A skill score is measured against a climatological expectation. This ` +
    `study pools ${meta.n_points} locations whose wet-day base rates run ` +
    `from <b>${Math.round(bs.min * 100)}%</b> to ` +
    `<b>${Math.round(bs.max * 100)}%</b>, so the pooled expectation is a ` +
    `mixture no single location experiences — and the score then credits ` +
    `the forecast for telling wet <em>places</em> from dry <em>places</em>, ` +
    `which is free. Hamill and Juras (2006) showed this can produce ` +
    `apparent skill from forecasts with none.`;

  $("#hjNull").innerHTML =
    `<strong>Measured on this data.</strong> Replace the forecast at every ` +
    `cell with one that is statistically independent of what happened ` +
    `there, keeping that cell's real forecast rate and real base rate. ` +
    `Every location then has exactly zero skill by construction. Pool those ` +
    `${meta.n_points} tables and the Heidke Skill Score comes out at ` +
    `<b>${HJ.null_check.closed_form.toFixed(3)}</b> — ` +
    `${Math.round(h1.null_share_of_pooled * 100)}% of the ` +
    `${h1.HSS.pooled.toFixed(3)} this study reports at one day ahead, from ` +
    `base-rate spread alone. That figure is exact rather than simulated ` +
    `(independence makes the expected table the outer product of its ` +
    `margins); a ${HJ.null_check.n_sim}-draw simulation agrees at ` +
    `${HJ.null_check.simulated_mean.toFixed(4)} ± ` +
    `${HJ.null_check.simulated_sd.toFixed(4)}.`;

  $("#hjContrast").innerHTML =
    `<strong>It does not hit everything equally, and that is the point.</strong> ` +
    `Scoring each cell against its own climatology and averaging the scores ` +
    `lowers HSS by <b>${h1.HSS.gap.toFixed(3)}</b> at one day ahead ` +
    `(${h1.HSS.pooled.toFixed(3)} → ${h1.HSS.stratified.toFixed(3)}; 95% CI ` +
    `on the gap ${fmt(h1.HSS.gap_lo)} to ${fmt(h1.HSS.gap_hi)}, excluding ` +
    `zero) and by ${h7.HSS.gap.toFixed(3)} at seven days. The same treatment ` +
    `moves the rain direction by only ${h1.PPV.gap.toFixed(3)} and the dry ` +
    `direction by ${h1.NPV.gap.toFixed(3)}. PPV, NPV, POD, FAR and bias have ` +
    `no climatological reference to distort — pooling makes them a ` +
    `frequency-weighted composite, which changes what question they answer, ` +
    `not whether the answer is valid.`;

  table($("#tableHJ"),
    ["Metric", "Wet day", "Lead", "Pooled", "Stratified", "Gap",
     "Gap 95% CI", "Across cells: median", "IQR", "Range"],
    ["HSS", "PPV", "NPV"].flatMap((k) => HJ.records.map((r) => {
      const v = r[k];
      return [k, `≥${r.threshold_mm} mm`, r.lead_days, fmt(v.pooled),
        fmt(v.stratified), (v.gap > 0 ? "+" : "") + fmt(v.gap),
        `${fmt(v.gap_lo)} – ${fmt(v.gap_hi)}`, fmt(v.median), fmt(v.iqr),
        `${fmt(v.min)} – ${fmt(v.max)}`];
    })), 5);

  /* ---- the place lookup: state what it actually covers ---------------- */
  const pc = D.places.coverage;
  const ROUTE_LABEL = {
    seat_fcode: "GeoNames tags a district or sub-district seat inside the "
      + "district, and that seat is used",
    district_name: "no seat tag, but a place inside the district carries the "
      + "district's own name — in India that is normally the headquarters",
    largest_town: "neither of the above, so the district's most populous "
      + "place stands in. These are not claimed to be headquarters: a "
      + "district's largest town often is not its seat",
    district_median: "no seat, no name match and no population figures "
      + "anywhere in the district, so the entry is the median position of "
      + "its indexed places, labelled with the district's name",
    name_nationwide: "the district contains no indexed place at all, so a "
      + "nationwide name match was used",
  };
  $("#placesText").innerHTML =
    `The decision tool turns a typed place name into coordinates so it can ` +
    `snap to the nearest of the ${meta.n_points} grid cells. That lookup is ` +
    `<b>${pc.total.toLocaleString()}</b> entries from ` +
    `<a href="https://www.geonames.org/">GeoNames</a> (CC&nbsp;BY&nbsp;4.0), ` +
    `built by <code>src/build_places.py</code>: one for every one of the ` +
    `<b>${pc.districts_represented}</b> second-order administrative units ` +
    `GeoNames indexes for India — ${pc.districts_in_geonames} districts and ` +
    `${pc.divisions_not_districts} Maharashtra revenue divisions — across ` +
    `${pc.states_and_uts} states and union territories, plus ` +
    `${pc.capitals_added} capitals the district pass missed and the ` +
    `${pc.extra_towns} largest remaining towns. Typing a district name ` +
    `finds it even where the headquarters is called something else: ` +
    `Sirmaur reaches Nahan, Kinnaur reaches its own district entry.`;

  const rl = $("#placesRoutes");
  Object.entries(pc.by_route).sort((a, b) => b[1] - a[1]).forEach(([k, v]) => {
    h("li", { html: `<strong>${v} district${v === 1 ? "" : "s"}</strong> — `
      + (ROUTE_LABEL[k] || k) + "." }, rl);
  });
  $("#placesRouteNote").textContent =
    `Only ${pc.by_route.seat_fcode + pc.by_route.district_name} of the ` +
    `${pc.districts_represented} entries can be called a headquarters with a ` +
    `straight face. The rest are a point inside the right district, which is ` +
    `all this needs to be: the lattice spacing is about 165 km and most ` +
    `Indian districts are smaller than that, so any point inside one usually ` +
    `picks the same cell.`;

  $("#placesCaveat").innerHTML =
    `<strong>No number on this page is derived from it.</strong> It only ` +
    `decides which measured cell you are shown; the measurement is unchanged ` +
    `whether you reach a cell by typing, by map click, or by browser ` +
    `location — and the tool always tells you which cell it picked and how ` +
    `far away it is.`;

  $("#hjConsequence").innerHTML =
    `<strong>What was changed because of this.</strong> The skill-score ` +
    `column in the study table now shows both figures. The ` +
    `<a href="#finding">persistence ceiling</a> is read off the stratified ` +
    `score, which moved the ≥1 mm crossing from day ` +
    `${HJ.crossing["1.0"].first_lead_below_pooled} to day ` +
    `${HJ.crossing["1.0"].first_lead_below_stratified}: pooling inflates the ` +
    `naive benchmark more than it inflates the model ` +
    `(${HJ.crossing["1.0"].ceiling_pooled.toFixed(3)} → ` +
    `${HJ.crossing["1.0"].ceiling_stratified.toFixed(3)} for the ceiling, ` +
    `against ${h1.HSS.pooled.toFixed(3)} → ${h1.HSS.stratified.toFixed(3)} ` +
    `for ECMWF), so the pooled comparison understated the model's advantage. ` +
    `<a href="#seasonal">The seasonal inversion</a> was checked the same way ` +
    `and survives. Nothing on this page now rests on a pooled skill score ` +
    `alone.`;

  const b = me.boundary;
  $("#boundaryText").textContent =
    `${b.n_outside} of the ${b.n_total} cells have centres that fall outside India's ` +
    `drawn boundary. The lattice is derived from IMD's 0.25° land mask, which is ` +
    `coarser than the political border, so coastal and border cells spill over it. ` +
    `The furthest is ${fmt(b.max_km_outside, 1)} km beyond the line and a cell is about ` +
    `${fmt(b.cell_width_km, 0)} km wide, so ${b.within_one_cell_width} of the ` +
    `${b.n_outside} are inside one cell-width of the border — none is deep inside ` +
    `another country. Cells are drawn at their true 0.25° extent, so these straddle ` +
    `the boundary rather than floating outside it. This is a property of gridded data, ` +
    `not a defect: no point was moved, clipped or dropped to tidy up the map.`;
  table($("#tableBoundary"), ["Cell", "Latitude", "Longitude", "km beyond the boundary"],
    b.points.map((p) => [p.point_id, p.lat.toFixed(2) + "°N",
      p.lon.toFixed(2) + "°E", fmt(p.km_outside, 1)]), 3);

  const g = me.known_gaps, gl = $("#methodGaps");
  h("li", { html: `<strong>Forecast:</strong> ${g.forecast_days_missing} of ` +
    `${g.forecast_days_total} days missing (${g.dates.join(", ")}). ${g.note}` }, gl);
  h("li", { html: `<strong>Observations:</strong> ${g.imd_days_missing} of ` +
    `${g.imd_days_total} days missing — the IMD record is complete for this period.` }, gl);

  $("#notCalib").textContent = meta.not_calibration;
  $("#novelty").textContent = meta.novelty_claim;
  const pw = $("#priorWork");
  me.prior_work.forEach((p) => h("li", { html:
    `<a href="${p.url}">${p.scope}</a> — ${p.finding}. <em>${p.cite}</em>` }, pw));

  const at = $("#attribution");
  meta.attribution.forEach((a) => h("li", { text: a }, at));
  h("li", { html: `India outline: DataMeet India community, ` +
    `<a href="https://github.com/datameet/maps/tree/master/Country">india-composite.geojson</a> ` +
    `(CC0), simplified to 0.02°. Shows India's claimed boundary.` }, at);

  $("#footerNote").textContent =
    `Generated ${meta.generated} from ${meta.n_point_days.toLocaleString()} cell-days. ` +
    `${meta.headline_metric_reason} All figures regenerate byte-identically from cached inputs.`;
}

/* ============================================================ SECTION 1 */
/* The decision tool. Everything here is computed for the chosen CELL, not
   nationally: points.json carries FAR, POD and wet-day count per cell, and
   cell-days are a constant, so each cell's 2x2 table can be recovered and
   its own cost-loss curve evaluated. Recombined nationally this reproduces
   results/metrics.csv to 0.03% (rounding in the stored 3dp figures). */
// lead 1 matches the headline pair in the finding section; a different
// default made the same place show two different numbers on one page
const T = { place: null, cell: null, dist: 0, lead: 1 };

function cellDays() {
  return Math.round(D.meta.n_point_days / D.meta.n_points);
}

/** Recover hits / false alarms / misses / correct negatives for one cell. */
function contingency(v) {
  const n = cellDays(), far = v[0], pod = v[3], wet = v[7];
  const a = pod * wet;
  const c = wet - a;
  const b = far < 1 ? a * far / (1 - far) : 0;
  return { a, b, c, d: n - a - b - c, n };
}

const kmBetween = (la1, lo1, la2, lo2) => {
  const r = Math.PI / 180;
  const h = Math.sin((la2 - la1) * r / 2) ** 2
    + Math.cos(la1 * r) * Math.cos(la2 * r) * Math.sin((lo2 - lo1) * r / 2) ** 2;
  return 6371 * 2 * Math.asin(Math.sqrt(h));
};

function nearestCell(lat, lon) {
  let best = null, bd = Infinity;
  D.points.points.forEach((p) => {
    const d = kmBetween(lat, lon, p.lat, p.lon);
    if (d < bd) { bd = d; best = p; }
  });
  return { cell: best, dist: bd };
}

function setPlace(lat, lon, label) {
  const { cell, dist } = nearestCell(lat, lon);
  T.place = label; T.cell = cell; T.dist = dist;
  const out = $("#tLocOut");
  out.innerHTML = "";
  const near = h("span", {}, out);
  near.innerHTML = `Nearest measured cell: <strong>${cell.lat.toFixed(1)}°N, `
    + `${cell.lon.toFixed(1)}°E — ${Math.round(dist)} km from ${label}.</strong>`;
  h("br", {}, out);
  if (dist > 90) {
    h("span", { class: "warn", text:
      `⚠ The nearest cell is ${Math.round(dist)} km away. That is far enough `
      + `that this is a regional hint, not a local answer.` }, out);
  } else {
    h("span", { text: "Rain varies over that distance. Treat this as the "
      + "area around you, not your field." }, out);
  }
  renderAnswer();
}

function renderAnswer() {
  const box = $("#tAnswer");
  box.innerHTML = "";
  if (!T.cell) {
    h("p", { class: "answer-empty", text: "Tell me where you are and I'll "
      + "tell you how often this forecast is right where you are — in both "
      + "directions." }, box);
    return;
  }
  const tk = keyFor(T.cell.m, 1.0);
  const v = T.cell.m[tk][keyFor(T.cell.m[tk], T.lead)];
  const k = contingency(v);
  const ppv = 1 - v[0], pLo = 1 - v[2], pHi = 1 - v[1];
  const npv = v[8], nLo = v[9], nHi = v[10];
  const base = (k.a + k.c) / k.n;
  const saysRain = (k.a + k.b) / k.n;

  /* Both directions, side by side. A spray decision usually hangs on the
     dry forecast, and that is the one the study answers far better — so
     showing only the rain direction would answer the wrong question. */
  const pair = h("div", { class: "dirs" }, box);
  const dir = (cls, when, pctv, lo, hi, tail) => {
    const c = h("div", { class: "dir " + cls }, pair);
    h("p", { class: "dir-when", text: when }, c);
    h("p", { class: "dir-pct", text: Math.round(pctv * 100) + "%" }, c);
    h("p", { class: "dir-tail", text: tail }, c);
    h("p", { class: "dir-ci", text: `${Math.round(lo * 100)}–`
      + `${Math.round(hi * 100)}% on this study's data` }, c);
  };
  dir("wet", "When it says rain", ppv, pLo, pHi, "of the time it rains");
  dir("dry", "When it says dry", npv, nLo, nHi, "of the time it stays dry");

  /* The rain direction at lead 1 is beaten nationally by repeating
     yesterday. The tool defaults to lead 1, so this cannot sit in a
     footnote -- it is shown next to the number it undercuts. */
  const pr = D.persist.records.find(
    (r) => r.threshold_mm === 1.0 && r.lead_days === T.lead);
  if (pr) {
    const note = h("p", { class: "persist" }, box);
    const eP = Math.round(pr.ecmwf.PPV * 100);
    const pP = Math.round(pr.persistence.PPV * 100);
    note.innerHTML = T.lead === 1
      ? `<b>At one day ahead, yesterday is the better guide to rain.</b> `
        + `Nationally, simply repeating yesterday's weather is right `
        + `<b>${pP}%</b> of the time when it calls rain, against this model's `
        + `<b>${eP}%</b>. The model's advantage at one day ahead is in the `
        + `dry direction — ${Math.round(pr.ecmwf.NPV * 100)}% against `
        + `${Math.round(pr.persistence.NPV * 100)}% — and in overall skill, `
        + `not the wet one. It calls rain on `
        + `${Math.round((pr.ecmwf.BIAS - 1) * 100)}% more days than it rains; `
        + `yesterday, being made of real days, calls it on exactly as many. `
        + `<span class="pn">These two comparisons are national; the `
        + `percentages above are for your cell.</span>`
      : `<b>Better than the null benchmark here.</b> At ${T.lead} days ahead, `
        + `repeating the observation from ${T.lead} days before the target is `
        + `right <b>${pP}%</b> of the time when it calls rain; this model is `
        + `right <b>${eP}%</b>. It wins the dry direction too, `
        + `${Math.round(pr.ecmwf.NPV * 100)}% against `
        + `${Math.round(pr.persistence.NPV * 100)}%. `
        + `<span class="pn">That comparison is national; the percentages `
        + `above are for your cell.</span>`;
  }

  /* The verdict has to key off the rain figure itself, not only the gap
     between the two. A cell can clear the gap threshold while still being
     well short of a coin flip in the rain direction -- calling 73% "closer
     to a coin flip" because the dry side is 91% reads as plainly wrong. */
  const gap = npv - ppv;
  const natPPV = 1 - D.far.records.find(
    (r) => r.truth === "IMD" && r.threshold_mm === 1.0
      && r.lead_days === T.lead).FAR;
  const verdict = h("p", { class: "dir-verdict" }, box);
  if (gap <= 0.15) {
    verdict.innerHTML = `<strong>Both directions are about equally reliable `
      + `here</strong>, which is unusual: at most locations the dry forecast `
      + `is markedly the safer one.`;
  } else {
    const p100 = Math.round(ppv * 100);
    const rain = ppv >= 0.65
      ? `, and a rain forecast is better here than in most of the country — `
        + `${p100}% against a national ${Math.round(natPPV * 100)}%.`
      : ppv >= 0.55
        ? `, and a rain forecast is right more often than not — but only `
          + `just, at ${p100}%.`
        : `. A rain forecast is closer to a coin flip, at ${p100}%.`;
    verdict.innerHTML = `<strong>A dry forecast here is worth trusting`
      + rain + `</strong> Both come from the same model on the same day — the `
      + `difference is which way it is pointing, and where you are.`;
  }

  h("p", { class: "context", text: `For context, rain falls here on `
    + `${Math.round(base * 100)}% of days anyway, and this forecast calls for `
    + `rain on ${Math.round(saysRain * 100)}% of days.` }, box);

  const ax = D.methods.asymmetry;
  h("p", { text: `That asymmetry is not a quirk of this cell. The dry `
    + `direction is the more reliable one at `
    + `${ax.n_cells - ax.n_exception_cells} of the ${ax.n_cells} cells, and `
    + `it holds up better as the forecast reaches further ahead. It comes `
    + `from the model calling rain on more days than it rains — nationally, `
    + `${Math.round(D.meta.bias_headline.excess_pct)}% more.` }, box);

  const det = h("details", { class: "tv" }, box);
  h("summary", { text: "Show the numbers behind this" }, det);
  const dl = h("dl", {}, det);
  const row = (a1, b1) => { h("dt", { text: a1 }, dl); h("dd", { text: b1 }, dl); };
  row("Cell", `${T.cell.lat.toFixed(2)}°N, ${T.cell.lon.toFixed(2)}°E`);
  row("Lead", `${T.lead} day${T.lead > 1 ? "s" : ""}`);
  row("Said rain, rained", Math.round(k.a).toLocaleString());
  row("Said rain, stayed dry", Math.round(k.b).toLocaleString());
  row("Said dry, rained", Math.round(k.c).toLocaleString());
  row("Said dry, stayed dry", Math.round(k.d).toLocaleString());
  row("Days counted", k.n.toLocaleString());
  row("Wet-day base rate", `${(base * 100).toFixed(1)}%`);
  h("p", { class: "step-hint", text: "A wet day is at least 1 mm. A single "
    + "cell's rain-direction figure carries roughly ±7 percentage points; the "
    + "dry direction is tighter because far more days fall in it." }, det);
}

function buildTool() {
  const leadRow = $("#tLead");
  D.meta.leads.forEach((L) => {
    const b = h("button", { type: "button", text: String(L),
      "aria-pressed": L === T.lead ? "true" : "false" }, leadRow);
    b.addEventListener("click", () => {
      T.lead = L;
      [...leadRow.children].forEach((x) => x.setAttribute(
        "aria-pressed", x === b ? "true" : "false"));
      renderAnswer();
    });
  });
  h("span", { class: "step-hint", text: "days ahead" }, leadRow)
    .style.cssText = "align-self:center;margin-left:.4rem";

  /* places.json layout: [name, state, district, lat, lon, population].
     `district` is empty when it duplicates the name, which is the usual case
     for a headquarters. */
  const inp = $("#tLoc"), sug = $("#tSuggest");
  const hideSug = () => { sug.hidden = true; sug.innerHTML = ""; };

  /* Rank rather than take the first eight in file order, which is what this
     did before and is why searching felt arbitrary. Every token has to
     appear somewhere in name + district + state, so "nahan himachal" and
     "sirmaur" both reach Nahan; the rank is then how well the query matches
     the NAME, with population breaking ties. */
  const rank = (p, q, toks) => {
    const n = p[0].toLowerCase(), d = (p[2] || "").toLowerCase();
    const s = (p[1] || "").toLowerCase();
    const hay = `${n} ${d} ${s}`;
    if (!toks.every((t) => hay.includes(t))) return null;
    if (n === q) return 0;
    if (n.startsWith(q)) return 1;
    if (d === q || d.startsWith(q)) return 2;
    if (n.includes(q)) return 3;
    if (d.includes(q)) return 4;
    return 5;
  };

  inp.addEventListener("input", () => {
    const q = inp.value.trim().toLowerCase().replace(/\s*,\s*/g, " ");
    if (q.length < 2) return hideSug();
    const toks = q.split(/\s+/).filter(Boolean);
    const scored = [];
    for (const p of D.places.places) {
      const r = rank(p, q, toks);
      if (r !== null) scored.push([r, -(p[5] || 0), p]);
    }
    scored.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    const hits = scored.slice(0, 8).map((x) => x[2]);

    sug.innerHTML = "";
    if (!hits.length) {
      h("button", { type: "button", disabled: "",
        text: "No match — try the district name, or pick on the map."
      }, sug);
    }
    hits.forEach((p) => {
      const b = h("button", { type: "button" }, sug);
      /* GeoNames' Indian admin2 names are not uniform: five are Maharashtra
         revenue divisions and some already carry the word "District". Only
         append the noun when it is actually missing. */
      const d2 = p[2] || "";
      const unit = /\b(District|Division|Region)$/i.test(d2)
        ? d2 : `${d2} district`;
      const where = d2 ? `${unit} · ${p[1]}` : p[1];
      b.innerHTML = `${p[0]} <span class="st">${where}</span>`;
      b.addEventListener("click", () => {
        inp.value = p[0]; hideSug(); setPlace(p[3], p[4], p[0]);
      });
    });
    sug.hidden = false;
  });
  inp.addEventListener("blur", () => setTimeout(hideSug, 160));

  $("#tGeo").addEventListener("click", () => {
    const out = $("#tLocOut");
    if (!navigator.geolocation) {
      out.textContent = "This browser can't share a location."; return;
    }
    out.textContent = "Asking your browser for a location…";
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude: la, longitude: lo } = pos.coords;
        if (la < 6 || la > 38 || lo < 66 || lo > 100) {
          out.textContent = "That's outside the study area."; return;
        }
        inp.value = `${la.toFixed(2)}, ${lo.toFixed(2)}`;
        setPlace(la, lo, "your location");
      },
      () => { out.textContent = "Couldn't get a location — type a place instead."; },
      { timeout: 10000 });
  });

  $("#tPick").addEventListener("click", async () => {
    const wrap = $("#tMapWrap");
    if (!wrap.hidden) { wrap.hidden = true; return; }
    wrap.hidden = false;
    $("#tMap").textContent = "Loading map…";
    if (!D.outline) {
      D.outline = await fetch(dataURL("india_outline.geojson"))
        .then((r) => r.json());
    }
    drawToolMap();
  });

}

/** Compact picker map: the same cells, sized for the tool column. */
function drawToolMap() {
  const holder = $("#tMap");
  holder.innerHTML = "";
  const W = vwClamp(holder);
  const LON0 = 67, LON1 = 98.5, LAT0 = 6, LAT1 = 37.6;
  const H = Math.round(W * (LAT1 - LAT0)
    / ((LON1 - LON0) * Math.cos((LAT0 + LAT1) / 2 * Math.PI / 180)));
  const X = (lon) => (lon - LON0) / (LON1 - LON0) * W;
  const Y = (lat) => (LAT1 - lat) / (LAT1 - LAT0) * H;
  const svg = e("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`,
    role: "group", "aria-label": "Pick a grid cell" }, holder);
  (D.outline.features || []).forEach((f) => {
    const g = f.geometry;
    (g.type === "Polygon" ? [g.coordinates] : g.coordinates).forEach((poly) =>
      poly.forEach((ring) => e("path", { class: "outline",
        d: ring.map((c, i) => `${i ? "L" : "M"}${X(c[0]).toFixed(1)},`
          + `${Y(c[1]).toFixed(1)}`).join("") + "Z" }, svg)));
  });
  const tk0 = keyFor(D.points.points[0].m, 1.0);
  D.points.points.forEach((p) => {
    const v = p.m[tk0][keyFor(p.m[tk0], T.lead)];
    const x = X(p.lon - 0.125), y = Y(p.lat + 0.125);
    const w = Math.max(3, X(p.lon + 0.125) - x);
    const hh = Math.max(3, Y(p.lat - 0.125) - y);
    e("rect", { class: "cell", x, y, width: w, height: hh,
      fill: binColour(v[0]), "pointer-events": "none",
      stroke: T.cell && T.cell.id === p.id ? css("--ink") : css("--surface-1"),
      "stroke-width": T.cell && T.cell.id === p.id ? 2 : 0.6 }, svg);
    const hw = Math.max(w, 24);
    const r = e("rect", { x: x + w / 2 - hw / 2, y: y + hh / 2 - hw / 2,
      width: hw, height: hw, fill: "transparent", class: "hit", tabindex: 0,
      role: "button",
      "aria-label": `${p.lat.toFixed(1)}°N ${p.lon.toFixed(1)}°E` }, svg);
    const pick = () => {
      $("#tLoc").value = `${p.lat.toFixed(2)}, ${p.lon.toFixed(2)}`;
      setPlace(p.lat, p.lon, "the cell you picked");
      drawToolMap();
    };
    r.addEventListener("click", pick);
    r.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); pick(); }
    });
  });
}

/* ================================================================== MAP */
const MAP = { mode: "cells", lead: 1, thr: 1.0, sel: null, loaded: false };
const BINS = [
  { to: 0.30, label: "under 30%" },
  { to: 0.40, label: "30–40%" },
  { to: 0.50, label: "40–50%" },
  { to: 0.60, label: "50–60%" },
  { to: Infinity, label: "60% and over" },
];
/* points.json nests by threshold as a Python-formatted string ("1.0"), which
   String(1.0) in JS renders as "1". Match on value, not on spelling. */
const keyFor = (obj, num) => Object.keys(obj).find((k) => parseFloat(k) === num);

const binColour = (v) => {
  const vars = ["--b1", "--b2", "--b3", "--b4", "--b5"];
  for (let i = 0; i < BINS.length; i++) if (v < BINS[i].to) return css(vars[i]);
  return css("--b5");
};

function drawMap() {
  const holder = $("#mapHolder");
  if (!MAP.loaded) return;
  holder.classList.remove("skeleton");
  holder.innerHTML = "";
  const W = vwClamp(holder);
  const LON0 = 67.0, LON1 = 98.5, LAT0 = 6.0, LAT1 = 37.6;
  const meanLat = (LAT0 + LAT1) / 2 * Math.PI / 180;
  const H = Math.round(W * (LAT1 - LAT0) / ((LON1 - LON0) * Math.cos(meanLat)));
  const X = (lon) => (lon - LON0) / (LON1 - LON0) * W;
  const Y = (lat) => (LAT1 - lat) / (LAT1 - LAT0) * H;
  const svg = e("svg", { id: "mapsvg", width: W, height: H, viewBox: `0 0 ${W} ${H}`,
    role: "img", "aria-label":
      `Map of false alarm ratio across India at lead ${MAP.lead} days` }, holder);

  (D.outline.features || []).forEach((f) => {
    const gg = f.geometry;
    const polys = gg.type === "Polygon" ? [gg.coordinates] : gg.coordinates;
    polys.forEach((poly) => poly.forEach((ring) => {
      e("path", { class: "outline",
        d: ring.map((c, i) => `${i ? "L" : "M"}${X(c[0]).toFixed(1)},${Y(c[1]).toFixed(1)}`)
          .join("") + "Z" }, svg);
    }));
  });

  const marks = [];
  if (MAP.mode === "cells") {
    D.points.points.forEach((p) => {
      const tk = keyFor(p.m, MAP.thr);
      const v = p.m[tk][keyFor(p.m[tk], MAP.lead)];
      marks.push({ id: p.id, lat: p.lat, lon: p.lon, half: 0.125, vals: v,
        label: `${p.lat.toFixed(2)}°N ${p.lon.toFixed(2)}°E` });
    });
  } else {
    D.groups.records.filter((r) => r.threshold_mm === MAP.thr
      && r.lead_days === MAP.lead).forEach((r) => {
      const [a, b] = r.cell.split("_").map(Number);
      marks.push({ id: r.cell, lat: a * 3 + 1.5, lon: b * 3 + 1.5, half: 1.5,
        vals: [r.FAR, r.FAR_lo, r.FAR_hi], nPoints: r.n_points,
        label: `${a * 3}–${a * 3 + 3}°N, ${b * 3}–${b * 3 + 3}°E` });
    });
  }
  const HIT = 24;   // minimum pointer/touch target, per accessibility guidance
  marks.forEach((mk) => {
    const x = X(mk.lon - mk.half), y = Y(mk.lat + mk.half);
    const w = Math.max(3, X(mk.lon + mk.half) - x);
    const hh = Math.max(3, Y(mk.lat - mk.half) - y);
    /* visible mark: true 0.25° (or 3°) extent, so border cells straddle the
       outline exactly as the data does */
    e("rect", { class: "cell", x, y, width: w, height: hh,
      fill: binColour(mk.vals[0]), "pointer-events": "none",
      "aria-hidden": "true",
      "stroke-width": MAP.sel === mk.id ? 2 : 0.6,
      stroke: MAP.sel === mk.id ? css("--ink") : css("--surface-1") }, svg);
    /* separate, larger, invisible hit area — a 7px square is not clickable */
    const hw = Math.max(w, HIT), hhh = Math.max(hh, HIT);
    const r = e("rect", { x: x + w / 2 - hw / 2, y: y + hh / 2 - hhh / 2,
      width: hw, height: hhh, fill: "transparent", class: "hit",
      tabindex: 0, role: "button",
      "aria-pressed": MAP.sel === mk.id ? "true" : "false",
      "aria-label": `${mk.label}, false alarm ratio ${pct(mk.vals[0])}` }, svg);
    const pick = () => { MAP.sel = mk.id; showReadout(mk); drawMap(); };
    r.addEventListener("click", pick);
    r.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); pick(); }
    });
    if (MAP.sel === mk.id) showReadout(mk);
  });

  const bd = D.methods.boundary;
  const cap = MAP.mode === "cells"
    ? `Each square is one IMD 0.25° grid cell (about ${fmt(bd.cell_width_km, 0)} km). `
      + `${bd.n_outside} of ${bd.n_total} cells straddle the national boundary because `
      + `IMD's land mask is coarser than the border — none is more than `
      + `${fmt(bd.max_km_outside, 0)} km beyond it. Spacing between squares is the 1.5° `
      + `sampling lattice: this is a sample, not continuous coverage.`
    : `Each square is a 3° grid cell — a plain latitude/longitude grid, NOT an IMD `
      + `meteorological subdivision. There are ${new Set(D.groups.records.map((r) => r.cell)).size} `
      + `of them against IMD's 36, and the boundaries do not correspond.`;
  $("#mapCaption").textContent = cap;
  $("#mapNoDry").textContent = D.methods.asymmetry.map_note;

  const bl = $("#binLegend"); bl.innerHTML = "";
  BINS.forEach((b, i) => {
    const li = h("li", {}, bl);
    h("span", { class: "swatch" }, li).style.background =
      css(["--b1", "--b2", "--b3", "--b4", "--b5"][i]);
    li.appendChild(document.createTextNode(b.label));
  });

  table($("#tableMap"),
    MAP.mode === "cells" ? ["Cell", "Lat", "Lon", "FAR", "95% CI", "POD", "Bias", "Wet days"]
                         : ["3° cell", "Cells inside", "FAR", "95% CI"],
    marks.sort((a, b) => b.vals[0] - a.vals[0]).map((mk) => MAP.mode === "cells"
      ? [mk.id, mk.lat.toFixed(2), mk.lon.toFixed(2), fmt(mk.vals[0]),
         `${fmt(mk.vals[1])} – ${fmt(mk.vals[2])}`, fmt(mk.vals[3]),
         fmt(mk.vals[5], 2), mk.vals[7]]
      : [mk.label, mk.nPoints, fmt(mk.vals[0]), `${fmt(mk.vals[1])} – ${fmt(mk.vals[2])}`]), 3);
}

function showReadout(mk) {
  const r = $("#readout");
  r.innerHTML = "";
  h("h4", { text: MAP.mode === "cells" ? "Selected 0.25° cell" : "Selected 3° cell" }, r);
  const dl = h("dl", {}, r);
  const row = (k, v) => { h("dt", { text: k }, dl); h("dd", { text: v }, dl); };
  row("Location", mk.label);
  row("False alarm ratio", pct(mk.vals[0]));
  h("dt", { text: "95% CI" }, dl);
  h("dd", { text: `${fmt(mk.vals[1])} – ${fmt(mk.vals[2])}`, class: "ci" }, dl);
  if (MAP.mode === "cells") {
    row("Hit rate (POD)", pct(mk.vals[3]));
    row("CSI", fmt(mk.vals[4]));
    row("Frequency bias", fmt(mk.vals[5], 2));
    row("HSS", fmt(mk.vals[6]));
    row("Wet days observed", mk.vals[7]);
  } else {
    row("0.25° cells inside", mk.nPoints);
  }
  const p = h("p", { class: "ci" }, r);
  p.style.margin = ".6rem 0 0";
  p.textContent = MAP.mode === "cells"
    ? "A single cell's value carries roughly ±0.07. Read the map as a pattern."
    : "Aggregating to 3° roughly halves the interval, to about ±0.04.";
}

function buildMapControls() {
  /* On a phone a 0.25° cell is about 3px — legible as a pattern only if you
     already know what you are looking at. Default narrow viewports to the 3°
     view, which carries the same data at a readable size. The toggle still
     offers the true-extent cells for anyone who wants them. */
  const room = vwClamp($("#mapHolder"));
  if (room < 460) MAP.mode = "groups";

  const sl = $("#selLead");
  D.meta.leads.forEach((L) => h("option", { value: L,
    text: `${L} day${L > 1 ? "s" : ""} ahead` }, sl));
  sl.value = String(MAP.lead);
  sl.addEventListener("change", () => { MAP.lead = +sl.value; drawMap(); });

  const st = $("#selThr");
  D.meta.thresholds_mm.forEach((t) => h("option", { value: t, text: `≥${t} mm` }, st));
  st.value = String(MAP.thr);
  st.addEventListener("change", () => { MAP.thr = +st.value; drawMap(); });

  const bc = $("#btnCells"), bg = $("#btnGroups");
  const setMode = (m, keepSel) => {
    MAP.mode = m; if (!keepSel) MAP.sel = null;
    bc.setAttribute("aria-pressed", m === "cells" ? "true" : "false");
    bg.setAttribute("aria-pressed", m === "groups" ? "true" : "false");
    const r = $("#readout"); r.innerHTML = "";
    h("h4", { text: "Selected cell" }, r);
    h("p", { class: "empty", text: "Click or tab to any cell to see its numbers and confidence interval." }, r);
    drawMap();
  };
  bc.addEventListener("click", () => setMode("cells"));
  bg.addEventListener("click", () => setMode("groups"));
  // reflect the narrow-viewport default in the buttons
  bc.setAttribute("aria-pressed", MAP.mode === "cells" ? "true" : "false");
  bg.setAttribute("aria-pressed", MAP.mode === "groups" ? "true" : "false");

  $("#mapLede").textContent =
    `False alarm ratio varies a lot across the country, and that variation is real: ` +
    `splitting the record into alternating fortnights and comparing the two halves ` +
    `reproduces the spatial pattern at r = ${fmt(D.points.reliability[0].pearson_r, 2)} ` +
    `(reliability ${fmt(D.points.reliability[0].spearman_brown, 2)}). About 93% of the ` +
    `between-cell variation is signal rather than noise. But a single cell's own value ` +
    `still carries roughly ±0.07, so read the colours as a pattern and click a cell ` +
    `before quoting its number.`;
}

/* -------------------------------------------------------- lazy map load */
async function ensureMap() {
  if (MAP.loaded) return;
  MAP.loaded = "pending";
  try {
    const [grp, out] = await Promise.all([
      fetch(dataURL("groups.json")).then((r) => r.json()),
      D.outline ? Promise.resolve(D.outline)
                : fetch(dataURL("india_outline.geojson")).then((r) => r.json()),
    ]);
    D.groups = grp; D.outline = out;
    MAP.loaded = true;
    buildMapControls();
    drawMap();
    redrawers.push(() => { if (MAP.loaded === true) drawMap(); });
  } catch (err) {
    /* a map that silently stays blank is worse than one that says why */
    MAP.loaded = false;
    console.error("map failed:", err);
    const holder = $("#mapHolder");
    holder.classList.remove("skeleton");
    holder.textContent = "The map could not be drawn: " + (err && err.message);
    holder.style.cssText = "padding:2rem;color:#c0392b;font-size:.85rem";
  }
}

/* ------------------------------------------------------------------ boot */
async function boot() {
  const names = ["meta", "far_by_lead", "costloss", "seasonal", "crossmodel",
                 "methods", "points", "places", "persistence", "hamilljuras"];
  const [meta, far, cl, season, cross, methods, points, places, persist, hj] =
    await Promise.all(names.map(
      (n) => fetch(dataURL(n + ".json")).then((r) => r.json())));
  Object.assign(D, { meta, far, cl, season, cross, methods, points, places,
                     persist, hj });
  // truth-source gap is derived, not a separate file
  D.gap = far.records.filter((r) => r.truth === "ERA5").map((r) => {
    const i = far.records.find((q) => q.truth === "IMD"
      && q.threshold_mm === r.threshold_mm && q.lead_days === r.lead_days);
    return { threshold_mm: r.threshold_mm, lead_days: r.lead_days,
      gap: r.FAR - i.FAR };
  });

  /* One section failing must not take the rest of the page (or the map's
     observer) down with it — that turned a stale-cache problem into a blank
     map with no visible cause. */
  [["tool", buildTool], ["finding", buildFinding], ["cost-loss", buildCostLoss],
   ["seasonal", buildSeasonal], ["ERA5", buildEra5],
   ["methods", buildMethods]].forEach(([name, fn]) => {
    try { fn(); } catch (err) { console.error(`section "${name}" failed:`, err); }
  });

  const sec = $("#map");
  if ("IntersectionObserver" in window) {
    const io = new IntersectionObserver((ents) => {
      if (ents.some((x) => x.isIntersecting)) { io.disconnect(); ensureMap(); }
    }, { rootMargin: "300px 0px" });
    io.observe(sec);
  } else {
    ensureMap();
  }

  /* Deep links have to be re-applied by hand. The browser resolves the
     fragment while the page is still an empty shell, so by the time these
     sections have content the target has moved and the scroll is lost. */
  let hash = null;
  try { hash = location.hash && document.querySelector(location.hash); }
  catch (_) { hash = null; }          // a non-selector hash must not throw
  if (hash) {
    // the browser also restores its own scroll position after load, which
    // lands after this; opt out so it cannot undo the jump
    if ("scrollRestoration" in history) history.scrollRestoration = "manual";
    if (hash === sec) ensureMap();
    const jump = () => hash.scrollIntoView({ behavior: "instant", block: "start" });
    requestAnimationFrame(jump);
    setTimeout(jump, 120);
    setTimeout(jump, 600);            // again once the map has drawn
  }
}

boot().catch((err) => {
  console.error(err);
  const p = document.createElement("p");
  p.style.cssText = "padding:2rem;color:#c0392b";
  p.textContent = "Could not load the data files. Serve this directory over HTTP "
    + "(for example: python -m http.server) rather than opening index.html directly.";
  document.body.prepend(p);
});
})();
