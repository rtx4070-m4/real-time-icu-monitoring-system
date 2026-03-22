/**
 * app.js — ICU Command Center Frontend
 *
 * Architecture:
 *   WebSocket  ← vitals_update events (every 2 s from backend broadcaster)
 *   REST API   ← fallback polling if WS unavailable
 *
 * State: patientMap (id → snapshot), alertLog (ring buffer)
 */

"use strict";

// ─── Config ───────────────────────────────────────────────────────────────
const API_BASE = `${location.protocol}//${location.hostname}:8000`;
const WS_URL   = `ws://${location.hostname}:8000/ws/vitals`;
const MAX_CHART_POINTS = 30;
const MAX_ALERT_LOG    = 80;

// ─── State ────────────────────────────────────────────────────────────────
let patientMap    = {};   // id → latest snapshot
let alertLog      = [];   // [alertObj, ...]
let selectedId    = null; // patient card focused for chart
let sortMode      = "priority";
let ws            = null;
let vitalsChart   = null;
let chartHistory  = {};   // patient_id → { labels[], hr[], spo2[], bp[] }

// ─── DOM refs ─────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const grid        = $("patientGrid");
const triageList  = $("triageList");
const alertFeed   = $("alertFeed");
const wsDot       = $("wsDot");
const wsLabel     = $("wsLabel");
const statTotal   = $("statTotal");
const statCrit    = $("statCrit");
const statAlert   = $("statAlert");
const queueBadge  = $("queueBadge");
const chartName   = $("chartPatientName");
const chartHint   = $("chartHint");
const clockEl     = $("clock");

// ─── Clock ────────────────────────────────────────────────────────────────
function updateClock() {
  const now = new Date();
  clockEl.textContent = now.toLocaleTimeString("en-GB", { hour12: false });
}
updateClock();
setInterval(updateClock, 1000);

// ─── WebSocket ────────────────────────────────────────────────────────────
function connectWS() {
  ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    wsDot.className   = "ws-dot connected";
    wsLabel.textContent = "LIVE";
  };

  ws.onclose = () => {
    wsDot.className   = "ws-dot disconnected";
    wsLabel.textContent = "Reconnecting…";
    setTimeout(connectWS, 3000);
  };

  ws.onerror = () => {
    ws.close();
  };

  ws.onmessage = evt => {
    try {
      const msg = JSON.parse(evt.data);
      if (msg.type === "vitals_update") {
        processVitalsUpdate(msg.data);
      }
    } catch (e) {
      console.error("WS parse error:", e);
    }
  };
}

// ─── Data processing ──────────────────────────────────────────────────────
function processVitalsUpdate(snapshots) {
  snapshots.forEach(snap => {
    const id = snap.patient.id;
    patientMap[id] = snap;

    // Update chart history
    if (!chartHistory[id]) {
      chartHistory[id] = { labels: [], hr: [], spo2: [], sbp: [] };
    }
    const h   = chartHistory[id];
    const ts  = new Date(snap.vitals.timestamp);
    const lbl = ts.toLocaleTimeString("en-GB", { hour12: false, second: "2-digit" });
    h.labels.push(lbl);
    h.hr.push(snap.vitals.heart_rate);
    h.spo2.push(snap.vitals.spo2);
    h.sbp.push(snap.vitals.systolic_bp);
    if (h.labels.length > MAX_CHART_POINTS) {
      h.labels.shift(); h.hr.shift(); h.spo2.shift(); h.sbp.shift();
    }

    // Collect alerts
    snap.alerts.forEach(a => {
      if (!alertLog.find(x => x.id === a.id)) {
        alertLog.unshift(a);
      }
    });
  });

  if (alertLog.length > MAX_ALERT_LOG) alertLog.length = MAX_ALERT_LOG;

  render(snapshots);
}

// ─── Main render ──────────────────────────────────────────────────────────
function render(snapshots) {
  const all    = Object.values(patientMap);
  const crits  = all.filter(s => s.patient.status === "CRITICAL").length;
  const alerts = alertLog.length;

  statTotal.textContent = all.length;
  statCrit.textContent  = crits;
  statAlert.textContent = alerts;

  renderPatientGrid(all);
  renderTriageQueue(all);
  renderAlertFeed();
  if (selectedId && chartHistory[selectedId]) {
    renderChart(selectedId);
  }
}

// ─── Patient grid ─────────────────────────────────────────────────────────
function sortedPatients(all) {
  return [...all].sort((a, b) => {
    if (sortMode === "priority") return b.priority - a.priority;
    if (sortMode === "name")     return a.patient.name.localeCompare(b.patient.name);
    if (sortMode === "bed")      return a.patient.bed_number.localeCompare(b.patient.bed_number);
    return 0;
  });
}

function renderPatientGrid(all) {
  const sorted = sortedPatients(all);
  const existing = new Set([...grid.children].map(el => el.dataset.pid));
  const incoming  = new Set(sorted.map(s => String(s.patient.id)));

  // Remove cards no longer present
  existing.forEach(pid => {
    if (!incoming.has(pid)) {
      const el = grid.querySelector(`[data-pid="${pid}"]`);
      if (el) el.remove();
    }
  });

  sorted.forEach(snap => {
    const pid    = snap.patient.id;
    const status = snap.patient.status;
    const v      = snap.vitals;

    let card = grid.querySelector(`[data-pid="${pid}"]`);
    if (!card) {
      card = document.createElement("div");
      card.className   = "patient-card";
      card.dataset.pid = pid;
      card.addEventListener("click", () => selectPatient(pid));
      grid.appendChild(card);
    }

    card.className = `patient-card status-${status.toLowerCase()}${selectedId === pid ? " selected" : ""}`;

    const maxPriority = Math.max(...Object.values(patientMap).map(s => s.priority), 1);
    const pct         = Math.round((snap.priority / maxPriority) * 100);
    const barColor    = status === "CRITICAL" ? "var(--red)" : status === "WATCH" ? "var(--amber)" : "var(--green)";

    card.innerHTML = `
      <div class="card-header">
        <div>
          <div class="card-name">${snap.patient.name}</div>
          <div class="card-diag">${snap.patient.diagnosis || "—"}</div>
        </div>
        <div style="text-align:right">
          <div class="card-bed">${snap.patient.bed_number}</div>
          <div class="status-badge ${status}">${status}</div>
        </div>
      </div>
      <div class="vital-grid">
        ${vitalCell("♥", v.heart_rate, "bpm", "HR", v.severity)}
        ${vitalCell("〇", v.spo2, "%", "SpO₂", spo2Sev(v.spo2))}
        ${vitalCell("⬆", v.systolic_bp+"/"+v.diastolic_bp, "", "BP mmHg", bpSev(v.systolic_bp))}
        ${vitalCell("🌡", v.temperature.toFixed(1), "°C", "Temp", tempSev(v.temperature))}
        ${vitalCell("≈", v.respiratory_rate, "/min", "RR", rrSev(v.respiratory_rate))}
        ${vitalCell("⬡", snap.priority, "pts", "Priority", status === "CRITICAL" ? "CRITICAL" : "NORMAL")}
      </div>
      <div class="card-footer">
        <span>${fmtTime(v.timestamp)}</span>
        <div class="priority-bar-wrap">
          <div class="priority-bar" style="width:${pct}%;background:${barColor}"></div>
        </div>
        <span>P:${snap.priority}</span>
      </div>
    `;
  });
}

function vitalCell(icon, val, unit, label, sev) {
  return `
    <div class="vital-cell">
      <div class="vital-icon">${icon}</div>
      <div class="vital-val ${sev}">${val}${unit ? '<span style="font-size:9px">'+unit+'</span>' : ''}</div>
      <div class="vital-label">${label}</div>
    </div>`;
}

// Quick severity helpers (mirrors Python thresholds)
function spo2Sev(v)  { return v >= 95 ? "NORMAL" : v >= 92 ? "LOW" : v >= 88 ? "MEDIUM" : "CRITICAL"; }
function bpSev(v)    { return (v>=90&&v<=140) ? "NORMAL" : (v>=85&&v<=155) ? "LOW" : (v>=75&&v<=170) ? "MEDIUM" : "CRITICAL"; }
function tempSev(v)  { return (v>=36.1&&v<=37.5) ? "NORMAL" : (v>=35.5&&v<=38) ? "LOW" : (v>=34.5&&v<=39) ? "MEDIUM" : "CRITICAL"; }
function rrSev(v)    { return (v>=12&&v<=20) ? "NORMAL" : (v>=10&&v<=24) ? "LOW" : (v>=8&&v<=28) ? "MEDIUM" : "CRITICAL"; }

function fmtTime(iso) {
  return new Date(iso).toLocaleTimeString("en-GB", { hour12: false });
}

// ─── Patient selection → chart ─────────────────────────────────────────────
function selectPatient(pid) {
  selectedId = pid;
  document.querySelectorAll(".patient-card").forEach(c => {
    c.classList.toggle("selected", Number(c.dataset.pid) === pid);
  });
  const snap = patientMap[pid];
  if (snap) chartName.textContent = snap.patient.name;
  chartHint.style.display = "none";
  renderChart(pid);
}

// ─── Chart.js ─────────────────────────────────────────────────────────────
function renderChart(pid) {
  const h = chartHistory[pid];
  if (!h || !h.labels.length) return;

  const cfg = {
    type: "line",
    data: {
      labels: h.labels,
      datasets: [
        { label: "Heart Rate", data: h.hr,   borderColor: "#ff4081", backgroundColor: "rgba(255,64,129,.08)", tension: .4, pointRadius: 0, borderWidth: 1.5 },
        { label: "SpO₂",      data: h.spo2,  borderColor: "#00d4ff", backgroundColor: "rgba(0,212,255,.06)",  tension: .4, pointRadius: 0, borderWidth: 1.5 },
        { label: "Sys BP",    data: h.sbp,   borderColor: "#ffab00", backgroundColor: "rgba(255,171,0,.06)",  tension: .4, pointRadius: 0, borderWidth: 1.5 },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 200 },
      plugins: {
        legend: {
          labels: { color: "#6e8fa8", font: { family: "'Share Tech Mono'", size: 10 }, boxWidth: 10, padding: 12 },
        },
      },
      scales: {
        x: { ticks: { color: "#3d5468", font: { family: "'Share Tech Mono'", size: 9 }, maxTicksLimit: 8 }, grid: { color: "#151c22" } },
        y: { ticks: { color: "#3d5468", font: { family: "'Share Tech Mono'", size: 9 } }, grid: { color: "#151c22" } },
      },
    },
  };

  const canvas = $("vitalsChart");
  if (vitalsChart) {
    vitalsChart.data.labels             = h.labels;
    vitalsChart.data.datasets[0].data   = h.hr;
    vitalsChart.data.datasets[1].data   = h.spo2;
    vitalsChart.data.datasets[2].data   = h.sbp;
    vitalsChart.update("none");
  } else {
    vitalsChart = new Chart(canvas, cfg);
  }
}

// ─── Triage queue ─────────────────────────────────────────────────────────
function renderTriageQueue(all) {
  const sorted = [...all].sort((a, b) => b.priority - a.priority);
  queueBadge.textContent = sorted.filter(s => s.patient.status === "CRITICAL").length || sorted.length;

  triageList.innerHTML = sorted.slice(0, 8).map((snap, i) => `
    <li class="triage-item" onclick="selectPatient(${snap.patient.id})">
      <span class="triage-rank${i === 0 ? ' rank-1' : ''}">#${i + 1}</span>
      <div style="flex:1">
        <div class="triage-name">${snap.patient.name}</div>
        <div class="triage-bed">${snap.patient.bed_number} · ${snap.patient.diagnosis || "—"}</div>
      </div>
      <span class="triage-sev ${snap.vitals.severity}">${snap.vitals.severity}</span>
      <span class="triage-score">${snap.priority}p</span>
    </li>
  `).join("");
}

// ─── Alert feed ───────────────────────────────────────────────────────────
function renderAlertFeed() {
  alertFeed.innerHTML = alertLog.slice(0, 40).map(a => `
    <div class="alert-item ${a.severity}">
      <div class="alert-dot"></div>
      <div class="alert-body">
        <div class="alert-header">
          <span class="alert-who">${a.patient_name} · ${a.bed_number}</span>
          <span class="alert-time">${fmtTime(a.timestamp)}</span>
        </div>
        <div class="alert-msg">${a.message}</div>
      </div>
    </div>
  `).join("");
}

$("clearAlerts").addEventListener("click", () => {
  alertLog = [];
  renderAlertFeed();
});

// ─── Sort buttons ─────────────────────────────────────────────────────────
document.querySelectorAll(".sort-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".sort-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    sortMode = btn.dataset.sort;
    renderPatientGrid(Object.values(patientMap));
  });
});

// ─── Fallback REST polling (if WS never connects) ─────────────────────────
let wsConnectedOnce = false;
async function pollFallback() {
  if (wsConnectedOnce) return;
  try {
    const [vitRes, alertRes, qRes] = await Promise.all([
      fetch(`${API_BASE}/api/vitals`),
      fetch(`${API_BASE}/api/alerts?limit=50`),
      fetch(`${API_BASE}/api/scheduler/queue`),
    ]);
    const vitals = await vitRes.json();
    const alerts = await alertRes.json();
    const queue  = await qRes.json();
    const pMap   = {};
    queue.forEach(e => pMap[e.patient_id] = e.priority);

    const snapshots = vitals.map(v => ({
      patient: { id: v.patient_id, name: v.patient_name, bed_number: v.bed_number,
                 status: v.status, diagnosis: "", age: 0 },
      vitals:  v.vitals,
      alerts:  alerts.filter(a => a.patient_id === v.patient_id).slice(0, 5),
      priority: pMap[v.patient_id] || 0,
    }));
    processVitalsUpdate(snapshots);
  } catch (e) {
    console.warn("REST poll failed:", e.message);
  }
}

// ─── Boot ─────────────────────────────────────────────────────────────────
(function init() {
  connectWS();
  // Poll REST as warmup (gets data before first WS message)
  setTimeout(pollFallback, 500);
  setInterval(pollFallback, 5000);
})();
