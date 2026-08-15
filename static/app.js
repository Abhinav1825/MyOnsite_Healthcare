const vehiclesTbody = document.getElementById("vehicles-tbody");
const auditTbody = document.getElementById("audit-tbody");
const auditTable = document.getElementById("audit-table");
const auditHint = document.getElementById("audit-hint");
const auditTitle = document.getElementById("audit-title");
const refreshBtn = document.getElementById("refresh-btn");

function badge(state) {
  return `<span class="badge ${state}">${state}</span>`;
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

async function loadAudit(vehicleId) {
  auditTitle.textContent = `Audit Trail — ${vehicleId}`;
  auditHint.hidden = true;
  auditTable.hidden = false;
  auditTbody.innerHTML = `<tr><td colspan="6" class="empty">Loading&hellip;</td></tr>`;

  const res = await fetch(`/audit/${encodeURIComponent(vehicleId)}`);
  if (!res.ok) {
    auditTbody.innerHTML = `<tr><td colspan="6" class="empty">No audit entries found.</td></tr>`;
    return;
  }
  const entries = await res.json();

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

refreshBtn.addEventListener("click", loadVehicles);
loadVehicles();
