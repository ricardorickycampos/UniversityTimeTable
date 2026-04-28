/* ── UCTP Solver — Frontend App ──────────────────────────────────────────── */

const DAYS      = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];
const DAY_SHORT = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
const DISPLAY_START = 84;   // 7:00 AM in 5-min slots
const DISPLAY_END   = 264;  // 10:00 PM in 5-min slots

// ── State ─────────────────────────────────────────────────────────────────────
const State = {
  mode: 'static',            // 'live' | 'static'
  manifest: null,
  currentP1Log: null,
  currentP2Log: null,
  currentP2Assignment: null,
  currentSchedule: null,
  currentAnalysis: null,
  scalingData: null,
  activeDay: 0,
  csvFiles: {},
  charts: { p1: null, p2: null, rooms: null, fillDist: null, conflictDeg: null, scaling: null },
  eventSource: null,
};

// ── Utilities ─────────────────────────────────────────────────────────────────
function fmt(n, decimals = 0) {
  if (n == null || n === undefined) return '—';
  return Number(n).toLocaleString(undefined, { maximumFractionDigits: decimals });
}
function el(id) { return document.getElementById(id); }
function slotToTime(slot) {
  const min = slot * 5, h = Math.floor(min / 60), m = min % 60;
  const ampm = h < 12 ? 'AM' : 'PM';
  const h12  = h === 0 ? 12 : h > 12 ? h - 12 : h;
  return `${h12}:${String(m).padStart(2,'0')} ${ampm}`;
}

// ── API layer (auto-switches between live and static) ─────────────────────────
const API = {
  async get(path) {
    const r = await fetch(path);
    if (!r.ok) throw new Error(`HTTP ${r.status}: ${path}`);
    return r.json();
  },

  async listResults() {
    if (State.mode === 'live') return API.get('/api/results/list');
    return State.manifest;
  },

  async getResult(filename) {
    if (State.mode === 'live') return API.get(`/api/results/${filename}`);
    return API.get(`results/${filename}`);
  },

  async getSchedule(runId) {
    if (State.mode === 'live') return API.get(`/api/schedule/${runId}`);
    return API.get(`results/schedule_${runId}.json`);
  },

  async getAnalysis(runId) {
    if (State.mode === 'live') return API.get(`/api/analyze/${runId}`);
    return API.get(`results/analysis_${runId}.json`);
  },

  async getScaling() {
    if (State.mode === 'live') return API.get('/api/scaling');
    return API.get('results/scaling.json');
  },
};

// ── File download helper ───────────────────────────────────────────────────────
function downloadFile(name, content, type = 'text/plain') {
  const blob = new Blob([content], { type });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href = url; a.download = name;
  document.body.appendChild(a); a.click();
  document.body.removeChild(a); URL.revokeObjectURL(url);
}

// ── DSATUR ordering (greedy graph coloring) ────────────────────────────────────
function computeDSATUR(adj, degrees, classes, limit = 10) {
  const n      = classes.length;
  const colors = new Int32Array(n).fill(-1);
  const sat    = new Int32Array(n);
  const result = [];

  for (let step = 0; step < Math.min(limit, n); step++) {
    let best = -1, bSat = -1, bDeg = -1;
    for (let i = 0; i < n; i++) {
      if (colors[i] !== -1) continue;
      if (sat[i] > bSat || (sat[i] === bSat && degrees[i] > bDeg)) {
        best = i; bSat = sat[i]; bDeg = degrees[i];
      }
    }
    if (best === -1) break;

    // Assign smallest available color
    const used = new Set();
    adj[best].forEach(nb => { if (colors[nb] !== -1) used.add(colors[nb]); });
    let c = 0; while (used.has(c)) c++;
    colors[best] = c;

    // Update saturation of uncolored neighbors
    adj[best].forEach(nb => {
      if (colors[nb] !== -1) return;
      const nbUsed = new Set();
      adj[nb].forEach(nb2 => { if (colors[nb2] !== -1) nbUsed.add(colors[nb2]); });
      sat[nb] = nbUsed.size;
    });

    result.push({
      step: step + 1,
      class_id:    classes[best].class_id,
      department:  classes[best].department,
      degree:      degrees[best],
      saturation:  bSat,
      color_group: c,
    });
  }
  return result;
}

// ── Mode detection ────────────────────────────────────────────────────────────
async function detectMode() {
  try {
    const ctrl = new AbortController();
    setTimeout(() => ctrl.abort(), 1500);
    const r = await fetch('/api/status', { signal: ctrl.signal });
    if (r.ok) { State.mode = 'live'; return 'live'; }
  } catch (_) { /* static mode */ }
  return 'static';
}

// ── Bootstrap ─────────────────────────────────────────────────────────────────
const App = {
  async init() {
    const mode = await detectMode();
    State.mode = mode;

    // Sync theme button icon with current theme
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
    el('theme-toggle').innerHTML = currentTheme === 'dark' 
    ? '<ion-icon name="sunny"></ion-icon>' 
    : '<ion-icon name="moon"></ion-icon>';

    // Update mode badge
    const badge = el('mode-badge');
    if (mode === 'live') {
      badge.textContent = '⬤ Live mode';
      badge.className = 'badge badge-live';
      el('btn-quick').style.display = '';
      el('btn-full').style.display  = '';
      el('run-controls').style.display = '';
      el('csv-live-badge').style.display = '';
      el('btn-upload-csv').disabled = false;
    }

    // Load manifest / result list
    try {
      if (mode === 'static') {
        State.manifest = await API.get('results/manifest.json');
      } else {
        State.manifest = await API.listResults();
      }
    } catch (e) {
      console.warn('Could not load manifest:', e);
      State.manifest = { phase1: [], phase2_logs: [], phase2_assignments: [], schedules: [] };
    }

    App.buildRunDropdown();
    App.updateConfigPreview();
    App.buildResultsBrowser();

    // Auto-load the latest run
    const { phase1 } = State.manifest;
    if (phase1 && phase1.length > 0) {
      await App.loadRun(phase1[phase1.length - 1]);
    }

    // Load scaling data (non-critical)
    try {
      const scaling = await API.getScaling();
      State.scalingData = scaling;
      if (scaling.runs?.length) App.renderScalingChart(scaling);
    } catch (_) {}
  },

  // ── Run dropdown ─────────────────────────────────────────────────────────
  buildRunDropdown() {
    const sel = el('run-select');
    sel.innerHTML = '<option value="">— select a run —</option>';
    const { phase1 = [] } = State.manifest;
    phase1.forEach(name => {
      const opt = document.createElement('option');
      opt.value = name;
      opt.textContent = name.replace('.json', '');
      sel.appendChild(opt);
    });
    sel.onchange = () => { if (sel.value) App.loadRun(sel.value); };
  },

  // ── Load a Phase 1 run ────────────────────────────────────────────────────
  async loadRun(filename) {
    try {
      const log = await API.getResult(filename);
      State.currentP1Log = log;

      // Sync dropdown
      const sel = el('run-select');
      if (sel.value !== filename) sel.value = filename;

      App.renderScheduleMetrics(log);
      App.renderDataSummary(log);
      App.renderP1Chart(log);
      App.renderFeasibilityReport(log);

      // Try to load the schedule JSON
      const runId = filename.replace('.json', '');
      try {
        const sched = await API.getSchedule(runId);
        State.currentSchedule = sched;
        App.renderScheduleGrid(sched);
      } catch (_) {
        el('schedule-placeholder').style.display = 'flex';
        el('schedule-placeholder').innerHTML = `
          <div style="font-size:28px;margin-bottom:10px;">📅</div>
          <div style="font-weight:500;margin-bottom:6px;">Schedule grid not available</div>
          <div style="font-size:11px;color:var(--text-secondary);">
            Run <code>python scripts/export_schedule.py</code> to generate it,
            then refresh the page.
          </div>`;
      }

      // Load matching Phase 2 run
      await App.loadMatchingP2(filename);

      // Load analysis (room usage, violations, section load)
      try {
        const analysis = await API.getAnalysis(runId);
        State.currentAnalysis = analysis;
        App.renderRoomUsageChart(analysis);
        App.renderOverCapacity(analysis);
        App.renderSectionLoad(analysis);
      } catch (_) { /* analysis not yet exported — non-critical */ }

      // Enable export buttons now that data is loaded
      el('btn-export-csv').disabled     = !State.currentSchedule;
      el('btn-export-metrics').disabled  = !State.currentP1Log;
      el('btn-export-report').disabled   = !State.currentP1Log;

    } catch (e) {
      console.error('Failed to load run:', e);
    }
  },

  // ── Find and load the Phase 2 run linked to this Phase 1 run ─────────────
  async loadMatchingP2(p1Filename) {
    const { phase2_logs = [], phase2_assignments = [] } = State.manifest;
    const stem = p1Filename.replace('.json', '');

    // Find a Phase 2 log that references this genome
    for (const logName of phase2_logs) {
      try {
        const log = await API.getResult(logName);
        const src = log.phase1_genome_source || '';
        if (src.includes(stem) || phase2_logs.length === 1) {
          State.currentP2Log = log;
          App.renderP2Chart(log);
          App.renderP2Analytics(log);
          break;
        }
      } catch (_) {}
    }

    for (const asgn of phase2_assignments) {
      try {
        const data = await API.getResult(asgn);
        const src  = data.phase1_genome_source || '';
        if (src.includes(stem) || phase2_assignments.length === 1) {
          State.currentP2Assignment = data;
          break;
        }
      } catch (_) {}
    }
  },

  // ── Theme toggle ──────────────────────────────────────────────────────────
  toggleTheme() {
    const html    = document.documentElement;
    const current = html.getAttribute('data-theme') || 'light';
    const next    = current === 'dark' ? 'light' : 'dark';

    html.setAttribute('data-theme', next);
    localStorage.setItem('uctp-theme', next);

    el('theme-toggle').innerHTML = next === 'dark' 
    ? '<ion-icon name="sunny"></ion-icon>' 
    : '<ion-icon name="moon"></ion-icon>';
    // Re-render charts so their axis/grid colors update
    if (State.currentP1Log)    App.renderP1Chart(State.currentP1Log);
    if (State.currentP2Log)    App.renderP2Chart(State.currentP2Log);
    if (State.currentAnalysis) {
      App.renderRoomUsageChart(State.currentAnalysis);
      if (State.currentAnalysis.phase2) App.renderSectionLoad(State.currentAnalysis);
    }
    if (State.currentSchedule) App.renderConflictGraph(State.currentSchedule);
    if (State.scalingData)     App.renderScalingChart(State.scalingData);
  },

  // ── Tab switching ─────────────────────────────────────────────────────────
  switchTab(name) {
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    el(`tab-${name}`).classList.add('active');
    document.querySelector(`[data-tab="${name}"]`).classList.add('active');
  },

  // ── Schedule metrics ───────────────────────────────────────────────────────
  renderScheduleMetrics(log) {
    const d  = log.final_breakdown || log;
    const ds = log.data_summary || {};
    const hard = d.hard || {};
    const soft = d.soft || {};

    el('s-classes').textContent = ds.n_classes != null ? fmt(ds.n_classes) : '—';
    el('s-classes-sub').textContent = ds.n_rooms != null ? `${ds.n_rooms} rooms` : '';

    const hTotal = d.hard_total ?? hard.total ?? 0;
    el('s-hard').textContent   = fmt(hTotal);
    el('s-hard-sub').textContent = hTotal === 0 ? 'Feasible ✓' : 'violations';
    el('s-hard').className = 'card-value ' + (hTotal === 0 ? 'text-green' : 'text-red');

    el('s-soft').textContent    = fmt(d.soft_total ?? soft.total, 0);
    el('s-soft-sub').textContent = 'weighted penalty';
    el('s-fitness').textContent = fmt(d.fitness, 0);
    el('s-fitness-sub').textContent = `${log.total_seconds != null ? log.total_seconds.toFixed(1) + 's runtime' : ''}`;

    // Hard breakdown
    el('hb-room').textContent   = `Room conflicts: ${fmt(hard.room_conflicts ?? 0)}`;
    el('hb-instr').textContent  = `Instructor conflicts: ${fmt(hard.instructor_conflicts ?? 0)}`;
    el('hb-share').textContent  = `Room sharing: ${fmt(hard.room_sharing ?? 0)}`;
    el('hb-group').textContent  = `Group: ${fmt(hard.group ?? 0)}`;

    // Soft breakdown
    el('sb-pref').textContent  = `Preferences: ${fmt(soft.preferences, 1)}`;
    el('sb-cap').textContent   = `Capacity: ${fmt(soft.capacity, 0)}`;
    el('sb-work').textContent  = `Workload: ${fmt(soft.instructor_workload, 1)}`;
    el('sb-group').textContent = `Group: ${fmt(soft.group, 0)}`;
  },

  // ── Schedule grid ─────────────────────────────────────────────────────────
  renderScheduleGrid(sched) {
    App.renderConflictGraph(sched);
    App.renderComplexityStats(sched);
    el('schedule-placeholder').style.display = 'none';
    const grid = el('schedule-grid');

    // Find which days have classes
    const activeDays = new Set();
    sched.classes.forEach(c => {
      for (let d = 0; d < 7; d++) {
        if (c.tp_days & (1 << d)) activeDays.add(d);
      }
    });
    const sortedDays = [...activeDays].sort();

    // Build day tabs
    const dayTabsEl = el('day-tabs');
    dayTabsEl.innerHTML = '';
    sortedDays.forEach((dayIdx, i) => {
      const btn = document.createElement('button');
      btn.className = 'day-tab-btn' + (i === 0 ? ' active' : '');
      btn.textContent = DAY_SHORT[dayIdx];
      btn.onclick = () => App.showDay(dayIdx, sortedDays);
      dayTabsEl.appendChild(btn);
    });

    // Remove existing day panels
    grid.querySelectorAll('.schedule-day-panel').forEach(p => p.remove());

    sortedDays.forEach((dayIdx, i) => {
      const panel = document.createElement('div');
      panel.className = 'schedule-day-panel' + (i === 0 ? ' active' : '');
      panel.id = `day-panel-${dayIdx}`;
      panel.innerHTML = App.buildDayTable(sched, dayIdx);
      grid.appendChild(panel);
    });

    State.activeDay = sortedDays[0];
  },

  showDay(dayIdx, sortedDays) {
    sortedDays.forEach(d => {
      const p = el(`day-panel-${d}`);
      if (p) p.classList.toggle('active', d === dayIdx);
    });
    document.querySelectorAll('.day-tab-btn').forEach((btn, i) => {
      btn.classList.toggle('active', sortedDays[i] === dayIdx);
    });
    State.activeDay = dayIdx;
  },

  buildDayTable(sched, dayIdx) {
    // Classes on this day, grouped by room
    const dayClasses = sched.classes.filter(c => c.tp_days & (1 << dayIdx));
    if (dayClasses.length === 0) return '<div style="padding:20px;color:var(--text-secondary);">No classes on this day.</div>';

    const roomIds = [...new Set(dayClasses.map(c => c.room_id))].sort((a,b) => a - b);
    const roomInfo = sched.rooms || {};

    // Time slots from DISPLAY_START to DISPLAY_END in 6-slot (30-min) steps
    const timeSlots = [];
    for (let s = DISPLAY_START; s < DISPLAY_END; s += 6) timeSlots.push(s);

    let html = `<div style="overflow-x:auto;max-height:600px;overflow-y:auto;">
      <table class="sched-table">
        <thead><tr>
          <th class="time-cell">Time</th>`;
    roomIds.forEach(rid => {
      const ri = roomInfo[String(rid)] || {};
      html += `<th class="room-header-cell">
        Room ${rid}${ri.has_sharing ? ' <span style="font-size:9px;opacity:.7;">[shared]</span>' : ''}
        <div style="font-size:9px;font-weight:400;opacity:.7;">${ri.capacity ? ri.capacity + ' seats' : ''}</div>
      </th>`;
    });
    html += '</tr></thead><tbody>';

    // Build a lookup: roomId → list of classes sorted by start
    const byRoom = {};
    roomIds.forEach(rid => { byRoom[rid] = []; });
    dayClasses.forEach(c => {
      if (byRoom[c.room_id]) byRoom[c.room_id].push(c);
    });

    // Render each 30-min row
    timeSlots.forEach(slot => {
      const timeLabel = slotToTime(slot) + '–' + slotToTime(slot + 6);
      html += `<tr><td class="time-cell">${timeLabel}</td>`;
      roomIds.forEach(rid => {
        // Find classes in this room that START in this 30-min block
        const chips = (byRoom[rid] || []).filter(c =>
          c.tp_start >= slot && c.tp_start < slot + 6
        );
        html += '<td>';
        chips.forEach(c => {
          const bg    = c.color || '#64748B';
          const conf  = c.has_conflict ? ' conflict' : '';
          const tip   = `Class ${c.class_id} | Dept ${c.department} | Limit ${c.class_limit} | ${c.start_time}–${c.end_time}${c.has_conflict ? ' | ⚠ ROOM CONFLICT' : ''}`;
          html += `<div class="class-chip${conf}"
            style="background:${bg}22;border-left-color:${bg};color:${bg};"
            title="${tip}">
            <div class="chip-name">C${c.class_id}</div>
            <div class="chip-time">${c.start_time}</div>
            <div class="chip-enroll">✦${c.class_limit}</div>
          </div>`;
        });
        html += '</td>';
      });
      html += '</tr>';
    });

    html += '</tbody></table></div>';
    return html;
  },

  // ── Data summary ──────────────────────────────────────────────────────────
  renderDataSummary(log) {
    const ds = log.data_summary || {};
    el('d-classes').textContent  = fmt(ds.n_classes);
    el('d-rooms').textContent    = fmt(ds.n_rooms);
    el('d-students').textContent = fmt(ds.n_students);
    el('d-gcs').textContent      = fmt(ds.n_group_constraints);
  },

  // ── Phase 1 chart ─────────────────────────────────────────────────────────
  renderP1Chart(log) {
    const history = log.history || [];
    if (!history.length) return;

    const dark = window.matchMedia('(prefers-color-scheme:dark)').matches;
    const tc = dark ? '#94A3B8' : '#64748B';
    const gc = dark ? 'rgba(255,255,255,.07)' : 'rgba(0,0,0,.04)';

    const labels = history.map(h => h.generation);
    const best   = history.map(h => h.best_fitness);
    const avg    = history.map(h => h.avg_fitness);

    const sub = `Phase 1 · ${history.length} generations · ` +
                `best fitness = ${fmt(log.final_fitness, 0)} · ` +
                `runtime = ${log.total_seconds != null ? log.total_seconds.toFixed(1) + 's' : '?'}`;
    el('p1-chart-sub').textContent = sub;

    if (State.charts.p1) State.charts.p1.destroy();
    State.charts.p1 = new Chart(el('chart-p1'), {
      type: 'line',
      data: {
        labels,
        datasets: [
          { label: 'Best fitness', data: best, borderColor: '#3B82F6',
            backgroundColor: 'transparent', borderWidth: 2, pointRadius: 0, tension: .3 },
          { label: 'Avg fitness',  data: avg,  borderColor: '#94A3B8',
            backgroundColor: 'transparent', borderWidth: 1, pointRadius: 0, tension: .3,
            borderDash: [4, 2] },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: true, labels: { color: tc, font: { size: 10 } } } },
        scales: {
          x: { ticks: { color: tc, font: { size: 10 }, maxTicksLimit: 12 },
               grid: { color: gc }, title: { display: true, text: 'Generation', color: tc, font: { size: 11 } } },
          y: { ticks: { color: tc, font: { size: 10 } },
               grid: { color: gc }, title: { display: true, text: 'Fitness', color: tc, font: { size: 11 } } },
        },
      },
    });
  },

  // ── Phase 2 chart ─────────────────────────────────────────────────────────
  renderP2Chart(log) {
    const history = (log.history || []);
    if (!history.length) return;

    const dark = window.matchMedia('(prefers-color-scheme:dark)').matches;
    const tc = dark ? '#94A3B8' : '#64748B';
    const gc = dark ? 'rgba(255,255,255,.07)' : 'rgba(0,0,0,.04)';

    const labels = history.map(h => h.generation);
    const best   = history.map(h => h.best_fitness);

    const fb = log.final_breakdown || {};
    const sub = `Phase 2 · ${history.length} generations · ` +
                `coverage = ${fb.coverage_pct != null ? fb.coverage_pct.toFixed(1) + '%' : '?'} · ` +
                `${fmt(fb.n_students)} students`;
    el('p2-chart-sub').textContent = sub;

    if (State.charts.p2) State.charts.p2.destroy();
    State.charts.p2 = new Chart(el('chart-p2'), {
      type: 'line',
      data: {
        labels,
        datasets: [
          { label: 'Best fitness', data: best, borderColor: '#10B981',
            backgroundColor: 'rgba(16,185,129,.08)', borderWidth: 2, pointRadius: 0,
            tension: .3, fill: true },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: tc, font: { size: 10 }, maxTicksLimit: 12 },
               grid: { color: gc }, title: { display: true, text: 'Generation', color: tc, font: { size: 11 } } },
          y: { ticks: { color: tc, font: { size: 10 } },
               grid: { color: gc }, title: { display: true, text: 'Fitness', color: tc, font: { size: 11 } } },
        },
      },
    });
  },

  // ── Phase 2 analytics cards ───────────────────────────────────────────────
  renderP2Analytics(log) {
    const fb = log.final_breakdown || {};
    el('a-students').textContent     = fmt(fb.n_students);
    el('a-coverage').textContent     = fb.coverage_pct != null ? fb.coverage_pct.toFixed(1) + '%' : '—';
    el('a-coverage-sub').textContent = `${fmt(fb.enrollments_placed)} of ${fmt(fb.enrollments_total)} placed`;
    el('a-skipped').textContent      = fmt(fb.enrollments_skipped);
    el('a-skipped-sub').textContent  = 'missed enrollments';
    el('a-p2fit').textContent        = fmt(log.final_fitness, 0);
  },

  // ── Feasibility report ────────────────────────────────────────────────────
  renderFeasibilityReport(log) {
    const hard = (log.final_breakdown || {}).hard || {};
    function rowClass(val) {
      return val === 0 ? 'feas-pass' : 'feas-fail';
    }
    function passOrFail(val) {
      return val === 0 ? '✓ PASS (0)' : `✗ FAIL (${fmt(val)})`;
    }
    const rc = hard.room_conflicts ?? '?';
    const ic = hard.instructor_conflicts ?? '?';
    const rs = hard.room_sharing ?? '?';
    const gc = hard.group ?? '?';
    const ht = hard.total ?? '?';

    el('fr-overlap').querySelector('.feas-val').className = `feas-val ${rowClass(rc)}`;
    el('fr-overlap').querySelector('.feas-val').textContent = passOrFail(rc);
    el('fr-instr').querySelector('.feas-val').className = `feas-val ${rowClass(ic)}`;
    el('fr-instr').querySelector('.feas-val').textContent  = passOrFail(ic);
    el('fr-share').querySelector('.feas-val').className = `feas-val ${rowClass(rs)}`;
    el('fr-share').querySelector('.feas-val').textContent  = passOrFail(rs);
    el('fr-group').querySelector('.feas-val').className = `feas-val ${rowClass(gc)}`;
    el('fr-group').querySelector('.feas-val').textContent  = passOrFail(gc);

    const isFeasible = ht === 0;
    el('fr-total-val').textContent = isFeasible ? '✓ FEASIBLE' : `✗ NOT FEASIBLE (${fmt(ht)} violations)`;
    el('fr-total-val').className   = `feas-val ${isFeasible ? 'feas-pass' : 'feas-fail'}`;
  },

  // ── Export functions ──────────────────────────────────────────────────────
  exportScheduleCSV() {
    const sched = State.currentSchedule;
    if (!sched) return;
    const header = 'class_id,offering,department,room_id,days,start_time,end_time,class_limit,has_conflict';
    const rows = sched.classes.map(c => {
      const days = (c.active_days || []).map(d => DAY_SHORT[d]).join('/');
      return `${c.class_id},${c.offering},${c.department},${c.room_id},"${days}",${c.start_time},${c.end_time},${c.class_limit},${c.has_conflict}`;
    });
    downloadFile('schedule.csv', [header, ...rows].join('\n'), 'text/csv');
  },

  exportMetricsJSON() {
    const log = State.currentP1Log;
    if (!log) return;
    const fb   = log.final_breakdown || log;
    const hard = fb.hard || {};
    const soft = fb.soft || {};
    const p2fb = State.currentP2Log?.final_breakdown || {};
    const metrics = {
      run_id:              log.run_id || '',
      fitness:             log.final_fitness,
      hard_violations:     fb.hard_total ?? hard.total ?? 0,
      soft_penalty:        fb.soft_total ?? soft.total,
      is_feasible:         (fb.hard_total ?? hard.total ?? 1) === 0,
      runtime_s:           log.total_seconds,
      n_generations:       log.history?.length,
      n_classes:           log.data_summary?.n_classes,
      phase2_coverage_pct: p2fb.coverage_pct,
      phase2_students:     p2fb.n_students,
      hard_breakdown:      hard,
      soft_breakdown:      soft,
    };
    downloadFile('metrics.json', JSON.stringify(metrics, null, 2), 'application/json');
  },

  exportFeasibilityReport() {
    const log = State.currentP1Log;
    if (!log) return;
    const fb   = log.final_breakdown || log;
    const hard = fb.hard || {};
    const soft = fb.soft || {};
    const ht   = fb.hard_total ?? hard.total ?? 0;
    const feasible = ht === 0;
    const p2fb = State.currentP2Log?.final_breakdown || {};

    const md = `# Feasibility Report
**Run:** ${log.run_id || 'unknown'}
**Status:** ${feasible ? '✅ FEASIBLE' : '❌ NOT FEASIBLE'}
**Fitness:** ${log.final_fitness != null ? Number(log.final_fitness).toFixed(0) : '—'}
**Runtime:** ${log.total_seconds != null ? log.total_seconds.toFixed(1) + 's' : '—'}

## Hard Constraints (must be 0)
| Constraint | Violations |
|---|---|
| Room conflicts | ${hard.room_conflicts ?? '—'} |
| Instructor conflicts | ${hard.instructor_conflicts ?? '—'} |
| Room sharing | ${hard.room_sharing ?? '—'} |
| Group constraints | ${hard.group ?? '—'} |
| **Total** | **${ht}** |

## Soft Penalties (lower = better)
| Constraint | Penalty |
|---|---|
| Preferences | ${soft.preferences != null ? Number(soft.preferences).toFixed(1) : '—'} |
| Capacity | ${soft.capacity != null ? Number(soft.capacity).toFixed(0) : '—'} |
| Instructor workload | ${soft.instructor_workload != null ? Number(soft.instructor_workload).toFixed(1) : '—'} |
| Group | ${soft.group != null ? Number(soft.group).toFixed(0) : '—'} |
| **Total** | **${(fb.soft_total ?? soft.total) != null ? Number(fb.soft_total ?? soft.total).toFixed(1) : '—'}** |

## Phase 2 — Student Sectioning
| Metric | Value |
|---|---|
| Students processed | ${p2fb.n_students ?? '—'} |
| Enrollments placed | ${p2fb.enrollments_placed ?? '—'} |
| Enrollments skipped | ${p2fb.enrollments_skipped ?? '—'} |
| Coverage | ${p2fb.coverage_pct != null ? p2fb.coverage_pct.toFixed(1) + '%' : '—'} |

---
*Generated by UCTP Solver — CS 4306, KSU Spring 2026*
`;
    downloadFile('feasibility_report.md', md, 'text/markdown');
  },

  // ── Conflict graph ────────────────────────────────────────────────────────
  renderConflictGraph(schedule) {
    const classes = schedule.classes || [];
    if (!classes.length) return;

    // Build instructor → class-index map
    const instrMap = {};
    classes.forEach((c, i) => {
      (c.instructor_ids || []).forEach(id => {
        (instrMap[id] = instrMap[id] || []).push(i);
      });
    });

    // Build adjacency sets (edge = shared instructor)
    const adj = classes.map(() => new Set());
    Object.values(instrMap).forEach(idxs => {
      for (let a = 0; a < idxs.length; a++) {
        for (let b = a + 1; b < idxs.length; b++) {
          adj[idxs[a]].add(idxs[b]);
          adj[idxs[b]].add(idxs[a]);
        }
      }
    });

    const degrees   = classes.map((_, i) => adj[i].size);
    const n_edges   = degrees.reduce((s, d) => s + d, 0) / 2;
    const avg_deg   = (degrees.reduce((s, d) => s + d, 0) / classes.length).toFixed(1);
    const max_deg   = Math.max(...degrees);

    // Connected components (BFS)
    const vis = new Uint8Array(classes.length);
    let n_comp = 0;
    for (let i = 0; i < classes.length; i++) {
      if (vis[i]) continue;
      n_comp++;
      const q = [i]; vis[i] = 1;
      while (q.length) {
        const u = q.shift();
        adj[u].forEach(v => { if (!vis[v]) { vis[v] = 1; q.push(v); } });
      }
    }

    // Chromatic number estimate via greedy coloring (degree-descending)
    const gcols = new Int32Array(classes.length).fill(-1);
    [...classes.keys()].sort((a, b) => degrees[b] - degrees[a]).forEach(i => {
      const used = new Set();
      adj[i].forEach(nb => { if (gcols[nb] !== -1) used.add(gcols[nb]); });
      let c = 0; while (used.has(c)) c++;
      gcols[i] = c;
    });
    const chromatic = Math.max(...gcols) + 1;

    el('cg-nodes').textContent     = fmt(classes.length);
    el('cg-edges').textContent     = fmt(Math.round(n_edges));
    el('cg-avgdeg').textContent    = avg_deg;
    el('cg-maxdeg').textContent    = max_deg;
    el('cg-components').textContent = n_comp;
    el('cg-chromatic').textContent  = chromatic;

    // Degree distribution (binned)
    const binEdges  = [0, 1, 5, 10, 20, 30, 50, Infinity];
    const binLabels = ['0', '1', '2–5', '6–10', '11–20', '21–30', '31–50', '>50'];
    const binCounts = new Array(binLabels.length).fill(0);
    degrees.forEach(d => {
      for (let k = 0; k < binEdges.length - 1; k++) {
        if (d >= binEdges[k] && d < binEdges[k + 1]) { binCounts[k]++; break; }
      }
    });

    el('cg-chart-sub').textContent =
      `${classes.length} nodes · ${Math.round(n_edges)} edges · avg degree ${avg_deg}`;

    const dark = window.matchMedia('(prefers-color-scheme:dark)').matches;
    const tc = dark ? '#94A3B8' : '#64748B';
    const gc = dark ? 'rgba(255,255,255,.07)' : 'rgba(0,0,0,.04)';

    if (State.charts.conflictDeg) State.charts.conflictDeg.destroy();
    State.charts.conflictDeg = new Chart(el('chart-conflict-degree'), {
      type: 'bar',
      data: {
        labels: binLabels,
        datasets: [{ label: 'Sections', data: binCounts,
          backgroundColor: 'rgba(139,92,246,.7)', borderWidth: 0, borderRadius: 4 }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: tc }, grid: { color: gc },
               title: { display: true, text: 'Conflicts (degree)', color: tc, font: { size: 11 } } },
          y: { ticks: { color: tc }, grid: { color: gc },
               title: { display: true, text: 'Sections', color: tc, font: { size: 11 } } },
        },
      },
    });

    // DSATUR table
    const order = computeDSATUR(adj, degrees, classes, 10);
    let html = `<div class="dsatur-row dsatur-header">
      <span>#</span><span>Class</span><span>Dept</span><span>Degree</span><span>Sat.</span><span>Group</span>
    </div>`;
    order.forEach(r => {
      const hue = (r.color_group * 47) % 360;
      html += `<div class="dsatur-row">
        <span>${r.step}</span>
        <span>C${r.class_id}</span>
        <span>${r.department}</span>
        <span>${r.degree}</span>
        <span>${r.saturation}</span>
        <span><span class="color-chip" style="background:hsl(${hue},65%,50%)">${r.color_group}</span></span>
      </div>`;
    });
    el('dsatur-table').innerHTML = html;
  },

  // ── Asymptotic complexity live stats ──────────────────────────────────────
  renderComplexityStats(schedule) {
    const classes = schedule.classes || [];
    if (!classes.length) return;

    const n        = classes.length;
    const avgRoom  = (classes.reduce((s, c) => s + (c.n_room_opts || 1), 0) / n).toFixed(1);
    const avgTime  = (classes.reduce((s, c) => s + (c.n_time_opts || 1), 0) / n).toFixed(1);
    const avgOpts  = Math.max(1, Math.round(parseFloat(avgRoom) * parseFloat(avgTime)));
    const naivePer = 63 * 288;
    const naiveExp = Math.round(Math.log10(naivePer) * n);
    const filtExp  = Math.round(Math.log10(avgOpts) * n);
    const nGens    = State.currentP1Log?.history?.length || 0;
    const gaEvals  = nGens * n;

    el('complexity-chart-sub').textContent = `${n} classes loaded from current run`;
    el('complexity-live-stats').innerHTML = `
      <div class="complexity-stat-grid">
        <div class="cstat-card">
          <div class="cstat-label">Classes (n)</div>
          <div class="cstat-val">${fmt(n)}</div>
        </div>
        <div class="cstat-card">
          <div class="cstat-label">Avg candidate rooms</div>
          <div class="cstat-val">${avgRoom}</div>
          <div class="cstat-sub">after capacity/lab filter</div>
        </div>
        <div class="cstat-card">
          <div class="cstat-label">Avg candidate times</div>
          <div class="cstat-val">${avgTime}</div>
          <div class="cstat-sub">after instructor filter</div>
        </div>
        <div class="cstat-card">
          <div class="cstat-label">Naive options/class</div>
          <div class="cstat-val">${fmt(naivePer)}</div>
          <div class="cstat-sub">63 rooms × 288 slots</div>
        </div>
        <div class="cstat-card cstat-red">
          <div class="cstat-label">Naive search space</div>
          <div class="cstat-val">≈ 10<sup style="font-size:11px">${fmt(naiveExp)}</sup></div>
          <div class="cstat-sub">${naivePer}^${n}</div>
        </div>
        <div class="cstat-card cstat-amber">
          <div class="cstat-label">Filtered space</div>
          <div class="cstat-val">≈ 10<sup style="font-size:11px">${fmt(filtExp)}</sup></div>
          <div class="cstat-sub">~${avgOpts} options/class</div>
        </div>
        <div class="cstat-card cstat-green">
          <div class="cstat-label">GA evaluations</div>
          <div class="cstat-val">${gaEvals > 0 ? fmt(gaEvals) : '—'}</div>
          <div class="cstat-sub">${nGens} gen × ${fmt(n)} classes</div>
        </div>
      </div>`;
  },

  // ── Scaling chart ─────────────────────────────────────────────────────────
  renderScalingChart(scaling) {
    const runs = scaling.runs || [];
    if (!runs.length) return;

    const dark = window.matchMedia('(prefers-color-scheme:dark)').matches;
    const tc = dark ? '#94A3B8' : '#64748B';
    const gc = dark ? 'rgba(255,255,255,.07)' : 'rgba(0,0,0,.04)';
    const ga = scaling.ga_settings || {};

    el('scaling-chart-sub').textContent =
      `${runs.length} data points · pop=${ga.population_size ?? '?'}, gen=${ga.n_generations ?? '?'}, seed=${ga.random_seed ?? '?'}`;

    if (State.charts.scaling) State.charts.scaling.destroy();
    State.charts.scaling = new Chart(el('chart-scaling'), {
      type: 'line',
      data: {
        labels: runs.map(r => r.n_classes),
        datasets: [
          { label: 'Runtime (s)', data: runs.map(r => r.runtime_s),
            borderColor: '#3B82F6', backgroundColor: 'rgba(59,130,246,.1)',
            borderWidth: 2, pointRadius: 5, tension: .3, fill: true, yAxisID: 'y' },
          { label: 'Hard violations', data: runs.map(r => r.hard_violations),
            borderColor: '#EF4444', backgroundColor: 'transparent',
            borderWidth: 2, pointRadius: 5, tension: .3, borderDash: [5, 3], yAxisID: 'y2' },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: true, labels: { color: tc, font: { size: 10 } } } },
        scales: {
          x:  { ticks: { color: tc }, grid: { color: gc },
                title: { display: true, text: 'Number of classes', color: tc, font: { size: 11 } } },
          y:  { ticks: { color: tc }, grid: { color: gc },
                title: { display: true, text: 'Runtime (s)', color: tc, font: { size: 11 } },
                position: 'left' },
          y2: { ticks: { color: '#EF4444' }, grid: { display: false },
                title: { display: true, text: 'Hard violations', color: '#EF4444', font: { size: 11 } },
                position: 'right' },
        },
      },
    });

    // Summary table
    let tbl = `<div class="chart-card" style="margin-top:12px;">
      <div class="chart-title">Scaling results table</div>
      <div class="slt-header" style="grid-template-columns:80px 90px 100px 110px 80px;">
        <span>Classes</span><span>Runtime</span><span>Fitness</span><span>Hard violations</span><span>Feasible</span>
      </div>`;
    runs.forEach(r => {
      tbl += `<div class="slt-row" style="grid-template-columns:80px 90px 100px 110px 80px;">
        <span>${fmt(r.n_classes)}</span>
        <span>${r.runtime_s}s</span>
        <span>${fmt(r.fitness, 0)}</span>
        <span class="${r.hard_violations > 0 ? 'text-red' : 'text-green'}">${r.hard_violations}</span>
        <span class="${r.is_feasible ? 'text-green' : 'text-amber'}">${r.is_feasible ? '✓ Yes' : '✗ No'}</span>
      </div>`;
    });
    tbl += '</div>';
    el('scaling-table-wrap').innerHTML = tbl;
  },

  // ── Room utilisation chart ────────────────────────────────────────────────
  renderRoomUsageChart(analysis) {
    const rooms = (analysis.room_usage || []).slice(0, 20);
    if (!rooms.length) {
      el('room-chart-sub').textContent = 'No room data available';
      return;
    }
    const dark = window.matchMedia('(prefers-color-scheme:dark)').matches;
    const tc = dark ? '#94A3B8' : '#64748B';
    const gc = dark ? 'rgba(255,255,255,.07)' : 'rgba(0,0,0,.04)';

    const labels = rooms.map(r => `Room ${r.room_id}`);
    const data   = rooms.map(r => r.avg_fill_pct);
    const colors = data.map(v =>
      v >= 100 ? 'rgba(239,68,68,.75)' : v >= 75 ? 'rgba(16,185,129,.75)' : 'rgba(59,130,246,.75)'
    );

    el('room-chart-sub').textContent =
      `Top ${rooms.length} rooms · avg fill % = (mean enrollment / capacity) × 100`;

    if (State.charts.rooms) State.charts.rooms.destroy();
    State.charts.rooms = new Chart(el('chart-rooms'), {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          label: 'Avg fill %',
          data,
          backgroundColor: colors,
          borderWidth: 0,
          borderRadius: 3,
        }],
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const r = rooms[ctx.dataIndex];
                return [
                  `Avg fill: ${ctx.raw.toFixed(1)}%`,
                  `Classes: ${r.n_classes}  ·  Capacity: ${r.room_cap}`,
                  `Total enrolled: ${fmt(r.total_enrolled)}`,
                ];
              },
            },
          },
        },
        scales: {
          x: {
            beginAtZero: true,
            ticks: { color: tc, font: { size: 10 }, callback: v => v + '%' },
            grid: { color: gc },
            title: { display: true, text: 'Avg fill % per class', color: tc, font: { size: 11 } },
          },
          y: { ticks: { color: tc, font: { size: 10 } }, grid: { color: gc } },
        },
      },
    });
  },

  // ── Over-capacity table ───────────────────────────────────────────────────
  renderOverCapacity(analysis) {
    const items = analysis.over_capacity || [];
    const container = el('overcap-content');
    if (!items.length) {
      container.innerHTML = '<div class="overcap-none">✓ No over-capacity classes</div>';
      return;
    }
    let html = `<div class="overcap-table">
      <div class="overcap-header">
        <span>Class</span><span>Dept</span><span>Limit</span><span>Cap</span><span>Over by</span>
      </div>`;
    items.forEach(c => {
      html += `<div class="overcap-row">
        <span>C${c.class_id}</span>
        <span>${c.department}</span>
        <span>${fmt(c.limit)}</span>
        <span>${fmt(c.room_cap)}</span>
        <span class="text-red">+${c.over_cap}</span>
      </div>`;
    });
    html += '</div>';
    container.innerHTML = html;
  },

  // ── Section load + fill distribution ─────────────────────────────────────
  renderSectionLoad(analysis) {
    const p2 = analysis.phase2;
    if (!p2) {
      el('section-load-sub').textContent = 'No Phase 2 data available';
      el('fill-dist-sub').textContent    = 'No Phase 2 data';
      return;
    }

    el('section-load-sub').textContent =
      `${p2.coverage_pct != null ? p2.coverage_pct.toFixed(1) + '% coverage' : ''} · ` +
      `${fmt(p2.enrollments_placed)} placed · ${fmt(p2.enrollments_skipped)} skipped`;

    // Section load table
    const sl = p2.section_load || [];
    let html = `<div class="slt-header">
      <span>Class</span><span>Offering</span><span>Enrolled / Limit</span><span>Fill</span>
    </div>`;
    sl.forEach(s => {
      const pct = s.fill_pct;
      const barColor = pct >= 100 ? 'var(--red)' : pct >= 75 ? 'var(--green)' : 'var(--blue)';
      html += `<div class="slt-row">
        <span>C${s.class_id}</span>
        <span>${s.offering}</span>
        <span>${fmt(s.enrolled)} / ${fmt(s.limit)}</span>
        <div class="fill-bar-wrap">
          <div class="fill-bar-bg">
            <div class="fill-bar-fill" style="width:${Math.min(pct, 100)}%;background:${barColor}"></div>
          </div>
          <span class="fill-pct-label">${pct.toFixed(0)}%</span>
        </div>
      </div>`;
    });
    el('section-load-table').innerHTML = '<div class="section-load-table">' + html + '</div>';

    // Fill distribution donut
    const fd = p2.fill_distribution || {};
    const distData   = [fd.empty || 0, fd.under_50 || 0, fd.f50_75 || 0, fd.f75_99 || 0, fd.full || 0];
    const distColors = ['#94A3B8', '#3B82F6', '#10B981', '#F59E0B', '#EF4444'];
    const distLabels = ['Empty', '< 50%', '50–75%', '75–99%', '100% full'];
    const total      = distData.reduce((a, b) => a + b, 0);

    el('fill-dist-sub').textContent = `${fmt(total)} sections total`;
    el('fill-dist-content').style.display = 'flex';

    if (State.charts.fillDist) State.charts.fillDist.destroy();
    State.charts.fillDist = new Chart(el('chart-fill-dist'), {
      type: 'doughnut',
      data: {
        labels: distLabels,
        datasets: [{ data: distData, backgroundColor: distColors, borderWidth: 1 }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: ctx => `${ctx.label}: ${ctx.raw} (${total ? (ctx.raw / total * 100).toFixed(1) : 0}%)`,
            },
          },
        },
      },
    });

    el('fill-dist-legend').innerHTML = distLabels.map((label, i) =>
      `<div class="fill-dist-item">
        <div class="fill-dist-dot" style="background:${distColors[i]}"></div>
        <span>${label}: <strong>${distData[i]}</strong></span>
      </div>`
    ).join('');
  },

  // ── Results browser ───────────────────────────────────────────────────────
  buildResultsBrowser() {
    const { phase1 = [], phase2_logs = [] } = State.manifest;

    const p1El = el('p1-runs-list');
    if (!phase1.length) {
      p1El.innerHTML = '<div style="color:var(--text-secondary);font-size:12px;">No Phase 1 runs found.</div>';
    } else {
      p1El.innerHTML = '';
      phase1.forEach(name => {
        const card = document.createElement('div');
        card.className = 'run-card';
        card.innerHTML = `
          <div class="run-id">${name}</div>
          <div class="run-meta">
            <button class="btn btn-sm btn-secondary" onclick="App.loadRun('${name}')">View →</button>
          </div>`;
        p1El.appendChild(card);
      });
    }

    const p2El = el('p2-runs-list');
    if (!phase2_logs.length) {
      p2El.innerHTML = '<div style="color:var(--text-secondary);font-size:12px;">No Phase 2 runs found.</div>';
    } else {
      p2El.innerHTML = '';
      phase2_logs.forEach(async name => {
        const card = document.createElement('div');
        card.className = 'run-card';
        card.innerHTML = `<div class="run-id">${name}</div><div class="run-meta">Loading…</div>`;
        p2El.appendChild(card);
        try {
          const log = await API.getResult(name);
          const fb  = log.final_breakdown || {};
          card.querySelector('.run-meta').innerHTML = `
            <span>${fb.coverage_pct != null ? fb.coverage_pct.toFixed(1) + '% coverage' : ''}</span>
            <span>${fmt(fb.n_students)} students</span>
            <span>${fmt(log.total_seconds, 1)}s</span>`;
        } catch (_) {}
      });
    }
  },

  // ── Config preview ────────────────────────────────────────────────────────
  updateConfigPreview() {
    const pop  = el('sl-p1-pop')?.value || 100;
    const gen  = el('sl-p1-gen')?.value || 500;
    const cx   = (el('sl-p1-cx')?.value || 70) / 100;
    const mt   = (el('sl-p1-mt')?.value || 2) / 1000;
    const ts   = el('sl-p1-ts')?.value || 3;
    const el_  = el('sl-p1-el')?.value || 2;
    const hw   = el('sl-p1-hw')?.value || 1000;
    const sub  = el('sl-p1-sub')?.value || 100;
    const p2g  = el('sl-p2-gen')?.value || 50;
    const p2p  = el('sl-p2-pop')?.value || 15;
    const seed = el('inp-seed')?.value  || 42;

    el('config-preview').textContent = `data:
  input_path: data/data.xml
  subset: ${sub}                # max classes (null = all 896)

student_sectioning:
  sample_size: ${el('sl-p2-ss')?.value || 500}          # max students (null = all ~30k)

ga:
  population_size: ${pop}
  n_generations:   ${gen}
  crossover_rate:  ${cx.toFixed(2)}
  mutation_rate:   ${mt.toFixed(3)}
  tournament_size: ${ts}
  elitism_count:   ${el_}
  random_seed:     ${seed}

phase2:
  ga:
    population_size: ${p2p}
    n_generations:   ${p2g}
    crossover_rate:  ${(el('sl-p2-cx')?.value || 70) / 100}
    mutation_rate:   ${(el('sl-p2-mt')?.value || 1) / 1000}

fitness:
  hard_weight: ${hw}`;
  },

  // ── CSV upload ────────────────────────────────────────────────────────────
  csvFileSelected(key, input) {
    if (input.files.length === 0) return;
    State.csvFiles[key] = input.files[0];
    const statusEl = el(`status-${key}`);
    statusEl.textContent = '✓ ' + input.files[0].name;
    statusEl.className   = 'csv-status loaded';
    const allLoaded = ['rooms','timeslots','sections','instructors']
      .every(k => State.csvFiles[k]);
    el('btn-upload-csv').disabled = !allLoaded || State.mode !== 'live';
  },

  async uploadCSVs() {
    if (State.mode !== 'live') {
      el('csv-upload-msg').textContent = 'CSV upload requires the Flask backend.';
      return;
    }
    const fd = new FormData();
    Object.entries(State.csvFiles).forEach(([k, f]) => fd.append(k, f));
    el('csv-upload-msg').textContent = 'Converting…';
    try {
      const r = await fetch('/api/upload/csv', { method: 'POST', body: fd });
      const d = await r.json();
      if (d.error) {
        el('csv-upload-msg').textContent = '✗ ' + d.error;
      } else {
        el('csv-upload-msg').textContent = '✓ ' + d.message;
      }
    } catch (e) {
      el('csv-upload-msg').textContent = '✗ Upload failed: ' + e.message;
    }
  },

  // ── Run solver ────────────────────────────────────────────────────────────
  startRun(phase) {
    if (State.mode !== 'live') {
      alert('Live mode required. Start the Flask backend:\npython server/app.py');
      return;
    }

    const config = {
      ga: {
        population_size: parseInt(el('sl-p1-pop').value),
        n_generations:   parseInt(el('sl-p1-gen').value),
        crossover_rate:  parseFloat(el('sl-p1-cx').value) / 100,
        mutation_rate:   parseFloat(el('sl-p1-mt').value) / 1000,
        tournament_size: parseInt(el('sl-p1-ts').value),
        elitism_count:   parseInt(el('sl-p1-el').value),
        random_seed:     parseInt(el('inp-seed').value),
      },
      phase2: {
        ga: {
          population_size: parseInt(el('sl-p2-pop').value),
          n_generations:   parseInt(el('sl-p2-gen').value),
        },
      },
      subset:      parseInt(el('sl-p1-sub').value),
      sample_size: parseInt(el('sl-p2-ss').value),
    };

    // Show log box and switch to algorithm tab
    App.switchTab('algorithm');
    const logBox = el('run-log');
    logBox.style.display = 'block';
    logBox.innerHTML = '';

    function appendLog(text, cls = '') {
      const span = document.createElement('span');
      span.className = 'run-log-line' + (cls ? ' ' + cls : '');
      span.textContent = text;
      logBox.appendChild(span);
      logBox.scrollTop = logBox.scrollHeight;
    }

    appendLog(`▶ Starting ${phase} run…`, 'phase');

    // Close any existing SSE
    if (State.eventSource) { State.eventSource.close(); State.eventSource = null; }

    // Start run
    fetch('/api/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phase, config }),
    }).then(r => r.json()).then(d => {
      if (d.error) { appendLog('✗ ' + d.error, 'error'); return; }

      // Open SSE stream
      State.eventSource = new EventSource('/api/run/stream');
      State.eventSource.onmessage = async (evt) => {
        const msg = JSON.parse(evt.data);
        if (msg.type === 'ping') return;
        if (msg.type === 'log') {
          appendLog(msg.message);
        } else if (msg.type === 'phase') {
          appendLog(`── Phase ${msg.phase} starting ──`, 'phase');
        } else if (msg.type === 'phase1_complete') {
          appendLog('✓ Phase 1 complete', 'done');
          State.currentP1Log = msg.result;
          App.renderScheduleMetrics(msg.result);
          App.renderP1Chart(msg.result);
          App.renderFeasibilityReport(msg.result);
        } else if (msg.type === 'schedule_ready') {
          try {
            const sched = await API.getSchedule(msg.run_id);
            State.currentSchedule = sched;
            App.renderScheduleGrid(sched);
          } catch (_) {}
        } else if (msg.type === 'analysis_ready') {
          try {
            const analysis = await API.getAnalysis(msg.run_id);
            State.currentAnalysis = analysis;
            App.renderRoomUsageChart(analysis);
            App.renderOverCapacity(analysis);
            App.renderSectionLoad(analysis);
          } catch (_) {}
        } else if (msg.type === 'phase2_complete') {
          appendLog('✓ Phase 2 complete', 'done');
          State.currentP2Log = msg.result;
          App.renderP2Chart(msg.result);
          App.renderP2Analytics(msg.result);
        } else if (msg.type === 'error') {
          appendLog('✗ Error: ' + msg.message, 'error');
        } else if (msg.type === 'done') {
          appendLog('── Run complete ──', 'done');
          State.eventSource.close();
          State.eventSource = null;
          // Refresh dropdown
          const newList = await API.listResults();
          State.manifest = newList;
          App.buildRunDropdown();
          App.buildResultsBrowser();
        }
      };
      State.eventSource.onerror = () => {
        appendLog('Connection to backend lost.', 'error');
        if (State.eventSource) { State.eventSource.close(); State.eventSource = null; }
      };
    }).catch(e => appendLog('✗ ' + e.message, 'error'));
  },
};

// ── Wire up config preview updates ───────────────────────────────────────────
document.querySelectorAll('input[type=range], input[type=number]')
  .forEach(inp => inp.addEventListener('input', App.updateConfigPreview));

// ── Boot ──────────────────────────────────────────────────────────────────────
App.init().catch(console.error);
