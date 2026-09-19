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
    e("polyline", { points: s.pts.map((p) => `${X(p[0])},${Y(p[1])}`).join(" "),
      fill: "none", stroke: s.colour, "stroke-width": 2,
      "stroke-linejoin": "round", "stroke-linecap": "round" }, svg);
    /* markers only when the series is sparse enough for them to mean
       something — a dot on all 49 alpha steps is noise, not data */
    if (o.markers !== false && s.pts.length <= 12) {
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

  /* Lead with both directions. The rain direction alone was the old headline
     and it understates the forecast badly: the same model on the same day is
     far more trustworthy when it says dry. */
  const hd = $("#heroDirs");
  [["wet", "When it says rain", ppv1, "of the time it rains"],
   ["dry", "When it says dry", l1.NPV, "of the time it stays dry"]]
    .forEach(([cls, when, val, tail]) => {
      const c = h("div", { class: "dir " + cls }, hd);
      h("p", { class: "dir-when", text: when + ", one day ahead" }, c);
      h("p", { class: "dir-pct", text: Math.round(val * 100) + "%" }, c);
      h("p", { class: "dir-tail", text: tail }, c);
    });

  $("#findingLede").textContent =
    `Across ${meta.n_point_days.toLocaleString()} cell-days at ${meta.n_points} ` +
    `locations, a one-day-ahead rain forecast was right ` +
    `${Math.round(ppv1 * 100)}% of the time and a dry forecast ` +
    `${Math.round(l1.NPV * 100)}% of the time — a gap of ` +
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
    `Rain falls on ${Math.round(l1.hits + l1.misses) / l1.n * 100 | 0}% of days ` +
    `in this sample, so "dry" is the common outcome and a forecast of dry ` +
    `starts from a position most days vindicate. "Rain" is the rarer call and ` +
    `has to earn its keep against a base rate working against it. That is ` +
    `arithmetic about how often it rains, not evidence the model handles rain ` +
    `badly — the same asymmetry would appear for a good model in any dry ` +
    `climate. The test is whether it survives where rain is common, and it ` +
    `mostly does: the dry direction is the more reliable one at ` +
    `${ex.n_cells - ex.n_exception_cells} of the ${ex.n_cells} cells. The ` +
    `exceptions are the two wettest — ` +
    ex.exceptions.map((e) => `${e.lat}°N ${e.lon}°E (rain on `
      + `${Math.round(e.wet_rate * 100)}% of days)`).join(" and ") +
    ` — where rain is the usual outcome and the directions swap round.`;

  $("#scopeText").textContent = meta.scope_caveat;

  const pd = fbl.paired_lead_difference.find((r) => r.threshold_mm === 1.0);
  $("#pairedText").textContent =
    `The confidence bands for day 1 and day 7 overlap, which on its own settles ` +
    `nothing. But both leads are scored on the same days in the same places, so the ` +
    `comparison to make is the paired one: false alarm ratio rises by ` +
    `${fmt(pd.difference, 3)} from day 1 to day 7, 95% CI ${fmt(pd.ci_lo, 3)} to ` +
    `${fmt(pd.ci_hi, 3)}. That excludes zero, so the upward trend is real — it is ` +
    `just small. Adjacent leads (day 3 versus day 4) remain indistinguishable.`;

  /* both directions, national, by lead */
  register(() => {
    lineChart($("#chartDirs"), {
      xDomain: [1, 7], yDomain: [0.45, 1.0], xTicks: meta.leads,
      yTicks: [0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
      yFmt: (v) => Math.round(v * 100) + "%",
      xLabel: "lead time (days ahead)", yLabel: "how often the forecast is right",
      hoverHead: (v) => `Lead ${v} day${v > 1 ? "s" : ""}`,
      aria: "The dry direction stays near 95% at every lead; the rain "
          + "direction falls from 58% to 52%",
      series: [
        { name: "says dry → stays dry", colour: css("--s1"), label: "says dry",
          pts: meta.leads.map((L) => [L, rec(1.0, L).NPV]),
          band: meta.leads.map((L) => [L, rec(1.0, L).NPV_lo, rec(1.0, L).NPV_hi]) },
        { name: "says rain → rains", colour: css("--s2"), label: "says rain",
          pts: meta.leads.map((L) => [L, 1 - rec(1.0, L).FAR]),
          band: meta.leads.map((L) => [L, 1 - rec(1.0, L).FAR_hi,
                                          1 - rec(1.0, L).FAR_lo]) },
      ],
    });
  });
  const lgd = $("#legendDirs");
  [["says dry → it stayed dry", css("--s1")],
   ["says rain → it rained", css("--s2")]].forEach(([nm, colour]) => {
    const li = h("li", {}, lgd);
    h("span", { class: "swatch line" }, li).style.background = colour;
    li.appendChild(document.createTextNode(nm));
  });

  const cols = [[1.0, css("--s1"), "≥1 mm"], [2.5, css("--s2"), "≥2.5 mm"]];
  register(() => {
    lineChart($("#chartFar"), {
      xDomain: [1, 7], yDomain: [0.3, 0.6],
      xTicks: [1, 2, 3, 4, 5, 6, 7], yTicks: [0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6],
      yFmt: (v) => Math.round(v * 100) + "%",
      xLabel: "lead time (days ahead)", yLabel: "false alarm ratio",
      hoverHead: (v) => `Lead ${v} day${v > 1 ? "s" : ""}`,
      aria: "False alarm ratio rising slightly with lead time, for two wet-day thresholds",
      series: cols.map(([thr, colour, name]) => ({
        name, colour, label: name,
        pts: meta.leads.map((L) => [L, rec(thr, L).FAR]),
        band: meta.leads.map((L) => [L, rec(thr, L).FAR_lo, rec(thr, L).FAR_hi]),
      })),
    });
  });
  const lg = $("#legendFar");
  cols.forEach(([, colour, name]) => {
    const li = h("li", {}, lg);
    h("span", { class: "swatch line" }, li).style.background = colour;
    li.appendChild(document.createTextNode(`wet day ${name} — IMD gauge truth`));
  });

  table($("#tableFar"),
    ["Wet day", "Lead", "FAR", "FAR 95% CI", "POD", "CSI", "HSS", "Bias", "Hits", "False alarms", "Misses"],
    fbl.records.filter((r) => r.truth === "IMD")
      .sort((a, b) => a.threshold_mm - b.threshold_mm || a.lead_days - b.lead_days)
      .map((r) => [`≥${r.threshold_mm} mm`, r.lead_days, fmt(r.FAR),
        `${fmt(r.FAR_lo)} – ${fmt(r.FAR_hi)}`, fmt(r.POD), fmt(r.CSI),
        fmt(r.HSS), fmt(r.BIAS, 2), r.hits.toLocaleString(),
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
  const g1 = D.gap.find((g) => g.threshold_mm === 1.0 && g.lead_days === 1);

  $("#era5Lede").textContent =
    `Rain gauges are scarce and reanalyses are convenient, so it is tempting to verify ` +
    `against ERA5. Doing that here would have cut the measured false alarm ratio roughly ` +
    `in half — from ${pct(rec("IMD", 1).FAR)} to ${pct(rec("ERA5", 1).FAR)} at one day ` +
    `— and made the forecast look almost unbiased (frequency bias ` +
    `${fmt(rec("ERA5", 1).BIAS, 2)} against ${fmt(rec("IMD", 1).BIAS, 2)}). Every ` +
    `conclusion on this page would have been kinder to the forecast, in the one ` +
    `direction that matters least to a farmer.`;

  const pal = [["IMD", css("--s1"), "IMD gauge truth"],
               ["ERA5", css("--s2"), "ERA5 reanalysis truth"]];
  register(() => {
    lineChart($("#chartEra5"), {
      xDomain: [1, 7], yDomain: [0.1, 0.55], xTicks: [1, 2, 3, 4, 5, 6, 7],
      yTicks: [0.1, 0.2, 0.3, 0.4, 0.5], yFmt: (v) => Math.round(v * 100) + "%",
      xLabel: "lead time (days ahead)", yLabel: "false alarm ratio",
      hoverHead: (v) => `Lead ${v} day${v > 1 ? "s" : ""}`,
      aria: "False alarm ratio is about half as large when scored against ERA5",
      series: pal.map(([t, colour, name]) => ({
        name, colour, label: t === "IMD" ? "gauge" : "ERA5",
        pts: [1, 2, 3, 4, 5, 6, 7].map((L) => [L, rec(t, L).FAR]),
        band: [1, 2, 3, 4, 5, 6, 7].map((L) => [L, rec(t, L).FAR_lo, rec(t, L).FAR_hi]),
      })),
    });
  });
  const lg = $("#legendEra5");
  pal.forEach(([, colour, name]) => {
    const li = h("li", {}, lg);
    h("span", { class: "swatch line" }, li).style.background = colour;
    li.appendChild(document.createTextNode(name));
  });

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

  const gap = npv - ppv;
  const verdict = h("p", { class: "dir-verdict" }, box);
  verdict.innerHTML = gap > 0.15
    ? `<strong>A dry forecast here is worth trusting. A rain forecast is `
      + `closer to a coin flip.</strong> Both come from the same model on the `
      + `same day — the difference is which way it is pointing.`
    : `<strong>Both directions are about equally reliable here</strong>, which `
      + `is unusual: at most locations the dry forecast is markedly the `
      + `safer one.`;

  h("p", { class: "context", text: `For context, rain falls here on `
    + `${Math.round(base * 100)}% of days anyway, and this forecast calls for `
    + `rain on ${Math.round(saysRain * 100)}% of days.` }, box);

  h("p", { text: `That asymmetry is not a quirk of this cell. Across all 139 `
    + `cells the dry direction is the more reliable one at every lead from 1 `
    + `to 7 days, and it holds up better as the forecast reaches further `
    + `ahead.` }, box);

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

  const inp = $("#tLoc"), sug = $("#tSuggest");
  const hideSug = () => { sug.hidden = true; sug.innerHTML = ""; };
  inp.addEventListener("input", () => {
    const q = inp.value.trim().toLowerCase();
    if (q.length < 2) return hideSug();
    const P = D.places.places;
    const starts = [], has = [];
    for (const p of P) {
      const n = p[0].toLowerCase();
      if (n.startsWith(q)) starts.push(p);
      else if (n.includes(q)) has.push(p);
      if (starts.length >= 8) break;
    }
    const hits = starts.concat(has).slice(0, 8);
    sug.innerHTML = "";
    if (!hits.length) {
      h("button", { type: "button", disabled: "",
        text: "No match — try a district or a larger town, or pick on the map."
      }, sug);
    }
    hits.forEach((p) => {
      const b = h("button", { type: "button" }, sug);
      b.innerHTML = `${p[0]} <span class="st">${p[1]}</span>`;
      b.addEventListener("click", () => {
        inp.value = p[0]; hideSug(); setPlace(p[2], p[3], p[0]);
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
                 "methods", "points", "places"];
  const [meta, far, cl, season, cross, methods, points, places] =
    await Promise.all(names.map(
      (n) => fetch(dataURL(n + ".json")).then((r) => r.json())));
  Object.assign(D, { meta, far, cl, season, cross, methods, points, places });
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
