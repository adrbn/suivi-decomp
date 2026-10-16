const $ = (s) => document.querySelector(s);
const num = (v, d) => v.toLocaleString('fr-FR', { minimumFractionDigits: d, maximumFractionDigits: d });
const pct = (v) => num(v, 2) + ' %';
const size = (b) => (b >= 1e6 ? num(b / 1e6, 2) + ' Mo' : num(b / 1e3, 1) + ' ko');
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
const UNITS = [[31536000, 'an'], [2592000, 'mois'], [604800, 'semaine'], [86400, 'jour'], [3600, 'heure'], [60, 'minute']];

function ago(t) {
  const s = (Date.now() - Date.parse(t)) / 1000;
  for (const [n, u] of UNITS) {
    if (s >= n) {
      const k = Math.floor(s / n);
      return `il y a ${k} ${u}${k > 1 && u !== 'mois' ? 's' : ''}`;
    }
  }
  return "à l'instant";
}

// Plein = entièrement lié ; hachuré = décompilé mais pas encore lié.
function bar(el, matched, complete) {
  el.innerHTML = complete
    ? `<i style="width:${complete}%"></i><b style="width:${Math.max(matched - complete, 0)}%"></b>`
    : `<i style="width:${matched}%"></i>`;
  el.title = `${pct(matched)} décompilé` + (complete ? `, ${pct(complete)} entièrement lié` : '');
}

function paintStatic() {
  document.querySelectorAll('time[datetime]').forEach((t) => (t.textContent = ago(t.dateTime)));
  document.querySelectorAll('.bar[data-m]').forEach((el) => bar(el, +el.dataset.m, +el.dataset.c));
}

function indexPage(list) {
  const cards = [...list.children];
  const keys = {
    updated: (c) => -Date.parse(c.dataset.time), name: (c) => c.dataset.name,
    pct: (c) => -c.dataset.pct, matched: (c) => -c.dataset.matched, total: (c) => -c.dataset.total,
  };
  const apply = () => {
    const key = keys[$('#sort').value], plat = $('#plat').value;
    cards.sort((a, b) => {
      const x = key(a), y = key(b);
      return typeof x === 'string' ? x.localeCompare(y, 'fr') : x - y;
    });
    cards.forEach((c) => { c.hidden = !!plat && c.dataset.plat !== plat; list.append(c); });
  };
  $('#sort').onchange = $('#plat').onchange = apply;
  apply();
}

// Treemap « squarified » : remplit des rangées le long du petit côté tant que
// le pire rapport d'aspect de la rangée s'améliore.
function squarify(items, x, y, w, h, out) {
  let i = 0;
  while (i < items.length && w > 0 && h > 0) {
    const side = Math.min(w, h);
    let j = i, sum = 0, worst = Infinity;
    while (j < items.length) {
      const s = sum + items[j].a;
      const r = Math.max((side * side * items[i].a) / (s * s), (s * s) / (side * side * items[j].a));
      if (r > worst) break;
      worst = r; sum = s; j++;
    }
    const thick = sum / side;
    let off = 0;
    for (let k = i; k < j; k++) {
      const len = items[k].a / thick;
      out.push(w >= h ? { u: items[k].u, x, y: y + off, w: thick, h: len } : { u: items[k].u, x: x + off, y, w: len, h: thick });
      off += len;
    }
    if (w >= h) { x += thick; w -= thick; } else { y += thick; h -= thick; }
    i = j;
  }
}

// Filtre : mots cherchés dans le nom, plus <70% >70% <10ko >10ko.
function matches(u, filter) {
  return filter.trim().split(/\s+/).every((t) => {
    const m = t.match(/^([<>])(\d+(?:[.,]\d+)?)(%|kb|ko)$/i);
    if (!m) return u[0].toLowerCase().includes(t.toLowerCase());
    const v = m[3] === '%' ? u[2] : u[1] / 1e3, lim = +m[2].replace(',', '.');
    return m[1] === '<' ? v < lim : v > lim;
  });
}

const tileColor = (u) => (u[3] ? 'var(--linked)' : u[2] >= 100 ? 'var(--matched)' : `hsl(${u[2] * 0.9} 62% 48%)`);

function treemap(units, cat, filter) {
  const box = $('#treemap'), W = box.clientWidth, H = Math.round(Math.min(W * 0.62, 640));
  const kept = units.filter((u) => (!cat || u[4].includes(cat)) && matches(u, filter)).sort((a, b) => b[1] - a[1]);
  const total = kept.reduce((s, u) => s + u[1], 0);
  const out = [];
  if (total) squarify(kept.map((u) => ({ u, a: (u[1] * W * H) / total })), 0, 0, W, H, out);
  box.style.height = H + 'px';
  box.innerHTML = out.map(({ u, x, y, w, h }) =>
    `<div style="left:${x}px;top:${y}px;width:${w}px;height:${h}px;background:${tileColor(u)}" ` +
    `title="${esc(u[0])}&#10;${size(u[1])} · ${pct(u[2])}${u[3] ? ' · entièrement lié' : ''}"></div>`).join('');
}

function chart(points) {
  const W = 800, H = 240, L = 46, R = 12, T = 12, B = 26;
  const vals = points.flatMap((p) => [p.m.matched_code_percent, p.m.complete_code_percent || p.m.matched_code_percent]);
  let lo = Math.floor(Math.min(...vals) / 5) * 5, hi = Math.ceil(Math.max(...vals) / 5) * 5;
  if (hi - lo < 5) { lo = Math.max(0, hi - 5); hi = lo + 5; }
  const t0 = Date.parse(points[0].time), t1 = Date.parse(points[points.length - 1].time);
  const x = (t) => L + (t1 > t0 ? ((Date.parse(t) - t0) / (t1 - t0)) * (W - L - R) : (W - L - R) / 2);
  const y = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
  const date = (t) => new Date(t).toLocaleDateString('fr-FR');
  const series = (key, cls, label) => {
    const pts = points.filter((p) => p.m[key]);
    if (!pts.length) return '';
    return `<polyline class="${cls}" points="${pts.map((p) => `${x(p.time)},${y(p.m[key])}`).join(' ')}"/>` +
      pts.map((p) => `<circle class="${cls}" cx="${x(p.time)}" cy="${y(p.m[key])}" r="3.5"><title>` +
        `${date(p.time)} · ${esc(p.sha.slice(0, 7))} ${esc(p.message)}&#10;${pct(p.m[key])} ${label}</title></circle>`).join('');
  };
  const grid = [lo, (lo + hi) / 2, hi].map((v) =>
    `<line class="grid" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${num(v, 0)} %</text>`).join('');
  $('#chart').innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Historique de la progression">${grid}` +
    `<text x="${L}" y="${H - 6}">${date(points[0].time)}</text>` +
    `<text x="${W - R}" y="${H - 6}" text-anchor="end">${date(points[points.length - 1].time)}</text>` +
    series('complete_code_percent', 'c', 'entièrement lié') + series('matched_code_percent', 'm', 'décompilé') + '</svg>';
}

function commits(repo, points) {
  const rows = points.slice().reverse().slice(0, 60).map((p, i, all) => {
    const prev = all[i + 1], d = prev ? p.m.matched_code_percent - prev.m.matched_code_percent : 0;
    const delta = Math.abs(d) >= 0.005 ? ` <span class="${d > 0 ? 'up' : 'down'}">${d > 0 ? '+' : '−'}${num(Math.abs(d), 2)}</span>` : '';
    return `<tr><td>${new Date(p.time).toLocaleDateString('fr-FR')}</td>` +
      `<td><a href="https://github.com/${esc(repo)}/commit/${esc(p.sha)}"><code>${esc(p.sha.slice(0, 7))}</code></a></td>` +
      `<td class="msg">${esc(p.message)}</td><td>${pct(p.m.matched_code_percent)}${delta}</td></tr>`;
  });
  $('#commits').innerHTML = rows.join('');
}

function projectPage(d) {
  const sel = $('#cat');
  for (const [id, name] of Object.entries(d.categories)) sel.add(new Option(name, id));
  const draw = () => {
    const cat = sel.value;
    const points = d.history.map((h) => ({ ...h, m: cat ? h.categories[cat] : h.measures })).filter((p) => p.m);
    const m = points[points.length - 1].m;
    $('#bars').innerHTML =
      `<h3>Code <small>(${size(m.total_code)})</small></h3><div class="bar code"></div>` +
      `<p class="muted">${pct(m.matched_code_percent)} décompilé${m.complete_code_percent ? ' · ' + pct(m.complete_code_percent) + ' entièrement lié' : ''}` +
      ` · ${num(m.matched_functions, 0)} / ${num(m.total_functions, 0)} fonctions</p>` +
      (m.total_data ? `<h3>Données <small>(${size(m.total_data)})</small></h3><div class="bar data"></div>` +
        `<p class="muted">${pct(m.matched_data_percent)} décompilé${m.complete_data_percent ? ' · ' + pct(m.complete_data_percent) + ' entièrement lié' : ''}</p>` : '');
    const [code, data] = document.querySelectorAll('#bars .bar');
    bar(code, m.matched_code_percent, m.complete_code_percent);
    if (data) bar(data, m.matched_data_percent, m.complete_data_percent);
    chart(points);
    commits(d.repo, points);
    treemap(d.units, cat, $('#filter').value);
  };
  sel.onchange = draw;
  $('#filter').oninput = () => treemap(d.units, sel.value, $('#filter').value);
  window.addEventListener('resize', () => treemap(d.units, sel.value, $('#filter').value));
  draw();
}

paintStatic();
if ($('#projects')) indexPage($('#projects'));
if ($('#data')) projectPage(JSON.parse($('#data').textContent));
