const vehiclesTbody = document.getElementById("vehicles-tbody");
const auditTbody = document.getElementById("audit-tbody");
const auditTable = document.getElementById("audit-table");
const auditHint = document.getElementById("audit-hint");
const auditTitle = document.getElementById("audit-title");
const refreshBtn = document.getElementById("refresh-btn");
const replayBtn = document.getElementById("replay-btn");
const replayResult = document.getElementById("replay-result");
const timelineContainer = document.getElementById("timeline-container");
const timelineSvg = document.getElementById("timeline-svg");
const trajectoriesSvg = document.getElementById("trajectories-svg");
const trajectoriesLegend = document.getElementById("trajectories-legend");
const proximityTbody = document.getElementById("proximity-tbody");

// Status colors: same three used by the .badge CSS classes, reused here so
// a safety_state always means the same color everywhere on the page. Per
// the dataviz skill's rule, a status color never carries meaning alone -
// every colored mark below is paired with a visible text label/tooltip.
const STATE_COLORS = { safe: "#1a7f37", alert: "#b08900", danger: "#cf222e" };

// Categorical palette (fixed hue order, never cycled per-render) for
// identity encoding - used only for the trajectory plot, where color
// distinguishes WHICH vehicle, not a status.
const CATEGORICAL_PALETTE = [
  "#2a78d6", // blue
  "#eb6834", // orange
  "#1baf7a", // aqua
  "#eda100", // yellow
  "#e87ba4", // magenta
  "#008300", // green
  "#4a3aa7", // violet
  "#e34948", // red
];

function badge(state) {
  return `<span class="badge ${state}">${state}</span>`;
}

function svgEl(tag, attrs) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  return el;
}

function svgTitle(text) {
  const t = svgEl("title", {});
  t.textContent = text;
  return t;
}

async function loadVehicles() {
  vehiclesTbody.innerHTML = `<tr><td colspan="5" class="empty">Loading&hellip;</td></tr>`;
  const res = await fetch("/vehicles");
  const vehicles = await res.json();

  if (!vehicles.length) {
    vehiclesTbody.innerHTML = `<tr><td colspan="5" class="empty">No vehicles yet. POST some events to /events.</td></tr>`;
    return;
  }

  vehiclesTbody.innerHTML = "";
  for (const v of vehicles) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${v.vehicle_id}</td>
      <td>${badge(v.safety_state)}</td>
      <td>${v.timestamp}</td>
      <td>${v.source_of_truth}</td>
      <td>${v.decision_reason}</td>
    `;
    tr.addEventListener("click", () => loadAudit(v.vehicle_id));
    vehiclesTbody.appendChild(tr);
  }
}

// --- Per-vehicle state timeline (bonus viz #1) -----------------------------
// A horizontal strip of segments, one per state-history entry, colored by
// safety_state and proportional to how long that state held. Each segment
// carries a native <title> hover tooltip - color is never the only cue.
function renderTimeline(history) {
  // A late-arriving event can produce a NEW version at a timestamp that
  // already had a reconciled state (see reconciler.py) - the history
  // array therefore may contain multiple versions sharing one timestamp.
  // The timeline should show what was ultimately decided at each
  // timepoint, not the superseded interim version, so keep only the
  // highest version per unique timestamp before laying out segments.
  const latestPerTimestamp = new Map();
  for (const entry of history) {
    const existing = latestPerTimestamp.get(entry.timestamp);
    if (!existing || entry.version > existing.version) latestPerTimestamp.set(entry.timestamp, entry);
  }
  const chrono = [...latestPerTimestamp.values()].sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
  timelineSvg.innerHTML = "";
  timelineSvg.setAttribute("viewBox", "0 0 600 40");
  timelineSvg.setAttribute("preserveAspectRatio", "none");

  if (chrono.length === 0) return;
  if (chrono.length === 1) {
    const rect = svgEl("rect", { x: 0, y: 0, width: 600, height: 32, rx: 4, fill: STATE_COLORS[chrono[0].safety_state] || "#999" });
    rect.appendChild(svgTitle(`${chrono[0].safety_state} @ ${chrono[0].timestamp}\n${chrono[0].decision_reason}`));
    timelineSvg.appendChild(rect);
    return;
  }

  const t0 = new Date(chrono[0].timestamp).getTime();
  const t1 = new Date(chrono[chrono.length - 1].timestamp).getTime();
  const rawSpan = Math.max(t1 - t0, 1);
  // The last entry has no "next" state to bound its segment's width, so it
  // gets a fixed slice of trailing padding. Critically, that padding is
  // folded into the denominator used for EVERY segment's x/width, not
  // just the last one - otherwise the second-to-last segment's width
  // still reaches x=600 (using the un-padded span) and the last segment,
  // starting exactly at x=600, renders with a nonzero width value but at
  // the clipped edge of the viewBox: invisible despite the arithmetic
  // being "correct" in isolation.
  const paddedEnd = t1 + rawSpan * 0.08;
  const totalSpan = paddedEnd - t0;

  for (let i = 0; i < chrono.length; i++) {
    const entry = chrono[i];
    const segStart = new Date(entry.timestamp).getTime();
    const segEnd = i + 1 < chrono.length ? new Date(chrono[i + 1].timestamp).getTime() : paddedEnd;
    const x = ((segStart - t0) / totalSpan) * 600;
    const width = Math.max(((segEnd - segStart) / totalSpan) * 600, 3);

    const rect = svgEl("rect", {
      x: x.toFixed(1),
      y: 0,
      width: width.toFixed(1),
      height: 32,
      rx: 4,
      fill: STATE_COLORS[entry.safety_state] || "#999",
    });
    rect.appendChild(
      svgTitle(
        `${entry.safety_state} (v${entry.version}) @ ${entry.timestamp}\n${entry.decision_reason}${entry.superseded ? "\n[superseded]" : ""}`
      )
    );
    if (entry.superseded) rect.setAttribute("opacity", "0.35");
    timelineSvg.appendChild(rect);
  }
}

async function loadAudit(vehicleId) {
  auditTitle.textContent = `Audit Trail — ${vehicleId}`;
  auditHint.hidden = true;
  auditTable.hidden = false;
  timelineContainer.hidden = false;
  auditTbody.innerHTML = `<tr><td colspan="6" class="empty">Loading&hellip;</td></tr>`;

  const [auditRes, historyRes] = await Promise.all([
    fetch(`/audit/${encodeURIComponent(vehicleId)}`),
    fetch(`/vehicles/${encodeURIComponent(vehicleId)}`),
  ]);

  if (historyRes.ok) renderTimeline(await historyRes.json());

  if (!auditRes.ok) {
    auditTbody.innerHTML = `<tr><td colspan="6" class="empty">No audit entries found.</td></tr>`;
    return;
  }
  const entries = await auditRes.json();

  auditTbody.innerHTML = "";
  for (const e of entries) {
    const tr = document.createElement("tr");
    const conflicts = Object.keys(e.conflicts_resolved || {}).length
      ? Object.entries(e.conflicts_resolved).map(([k, v]) => `<code>${k}: ${v}</code>`).join(" ")
      : "&mdash;";
    tr.innerHTML = `
      <td>${e.timestamp}</td>
      <td>${e.version}</td>
      <td>${badge(e.final_state)}</td>
      <td>${conflicts}</td>
      <td>${e.decision_reason}</td>
      <td>${(e.events_considered || []).map((id) => `<code>${id.slice(0, 8)}</code>`).join(" ")}</td>
    `;
    auditTbody.appendChild(tr);
  }
}

// --- 2D trajectory plot (bonus viz #2) --------------------------------------
async function loadTrajectories() {
  const res = await fetch("/vehicles/trajectories");
  const byVehicle = await res.json();
  const vehicleIds = Object.keys(byVehicle).sort();

  trajectoriesSvg.innerHTML = "";
  trajectoriesLegend.innerHTML = "";

  if (vehicleIds.length === 0) {
    trajectoriesSvg.appendChild(svgEl("text", { x: 20, y: 30, fill: "#6e7781" })).textContent = "No position data yet.";
    return;
  }

  const allPoints = vehicleIds.flatMap((id) => byVehicle[id].map((p) => p.position));
  const xs = allPoints.map((p) => p.x ?? 0);
  const ys = allPoints.map((p) => p.y ?? 0);
  const pad = 30;
  const [minX, maxX] = [Math.min(...xs), Math.max(...xs)];
  const [minY, maxY] = [Math.min(...ys), Math.max(...ys)];
  const spanX = Math.max(maxX - minX, 1);
  const spanY = Math.max(maxY - minY, 1);

  const toSvgX = (x) => pad + ((x - minX) / spanX) * (640 - 2 * pad);
  const toSvgY = (y) => 360 - pad - ((y - minY) / spanY) * (360 - 2 * pad); // flip: +y up

  vehicleIds.forEach((vehicleId, i) => {
    const color = CATEGORICAL_PALETTE[i % CATEGORICAL_PALETTE.length];
    const points = byVehicle[vehicleId];
    const pathPoints = points.map((p) => `${toSvgX(p.position.x ?? 0)},${toSvgY(p.position.y ?? 0)}`).join(" ");

    trajectoriesSvg.appendChild(
      svgEl("polyline", { points: pathPoints, fill: "none", stroke: color, "stroke-width": 2, opacity: 0.85 })
    );

    points.forEach((p) => {
      const circle = svgEl("circle", {
        cx: toSvgX(p.position.x ?? 0),
        cy: toSvgY(p.position.y ?? 0),
        r: 5,
        fill: color,
      });
      circle.appendChild(svgTitle(`${vehicleId} @ ${p.timestamp}\n(${p.position.x}, ${p.position.y}) — ${p.safety_state}`));
      trajectoriesSvg.appendChild(circle);
    });

    const legendItem = document.createElement("div");
    legendItem.className = "legend-item";
    legendItem.innerHTML = `<span class="legend-swatch" style="background:${color}"></span>${vehicleId}`;
    trajectoriesLegend.appendChild(legendItem);
  });
}

// --- Proximity alerts panel (bonus viz #3) ----------------------------------
async function loadProximityAlerts() {
  proximityTbody.innerHTML = `<tr><td colspan="6" class="empty">Loading&hellip;</td></tr>`;
  const res = await fetch("/proximity");
  const alerts = await res.json();

  if (!alerts.length) {
    proximityTbody.innerHTML = `<tr><td colspan="6" class="empty">No proximity alerts.</td></tr>`;
    return;
  }

  proximityTbody.innerHTML = "";
  for (const a of alerts) {
    const tr = document.createElement("tr");
    const closing = a.closing_speed === null || a.closing_speed === undefined ? "—" : a.closing_speed.toFixed(2);
    tr.innerHTML = `
      <td>${a.vehicle_a}</td>
      <td>${a.vehicle_b}</td>
      <td>${a.distance.toFixed(2)}</td>
      <td>${closing}</td>
      <td>${badge(a.severity)}</td>
      <td>${a.timestamp}</td>
    `;
    proximityTbody.appendChild(tr);
  }
}

async function runReplay() {
  replayResult.hidden = false;
  replayResult.textContent = "Replaying…";
  const res = await fetch("/replay", { method: "POST" });
  const report = await res.json();
  replayResult.textContent = report.consistent
    ? `✓ Replay consistent — re-checked ${report.checked} timepoint(s), nothing changed.`
    : `✗ Replay found ${report.unexpected_changes.length} inconsistency(ies) out of ${report.checked} checked.`;
}

function loadAll() {
  loadVehicles();
  loadTrajectories();
  loadProximityAlerts();
}

refreshBtn.addEventListener("click", loadAll);
replayBtn.addEventListener("click", runReplay);
loadAll();
