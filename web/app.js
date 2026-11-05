const elements = {
  connectionPill: document.querySelector("#connection-pill"),
  connectionText: document.querySelector("#connection-text"),
  statusCard: document.querySelector("#status-card"),
  situation: document.querySelector("#situation"),
  statusDescription: document.querySelector("#status-description"),
  distance: document.querySelector("#distance"),
  lastReading: document.querySelector("#last-reading"),
  deviceId: document.querySelector("#device-id"),
  source: document.querySelector("#source"),
  databaseState: document.querySelector("#database-state"),
  alertsBody: document.querySelector("#alerts-body"),
  alertCount: document.querySelector("#alert-count"),
  openAlertCount: document.querySelector("#open-alert-count"),
  ackAlertCount: document.querySelector("#ack-alert-count"),
  chart: document.querySelector("#distance-chart"),
  refreshButton: document.querySelector("#refresh-button"),
};

let readings = [];
let socketRetry = 1000;
let statusPoll = null;

function formatDate(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "medium",
  }).format(new Date(value));
}

function formatDuration(start, end) {
  if (!end) return "Em andamento";
  const seconds = Math.max(0, Math.round((new Date(end) - new Date(start)) / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${minutes}min ${remainder}s`;
}

function renderStatus(status) {
  const situation = status.situation || "SEM_SINAL";
  elements.statusCard.dataset.state = situation;
  elements.situation.textContent = situation.replace("_", " ");
  elements.distance.textContent = status.distance_cm == null ? "—" : Number(status.distance_cm).toFixed(1);
  elements.deviceId.textContent = status.device_id || "—";
  elements.source.textContent = status.source || "—";
  elements.databaseState.textContent = status.database_ok ? "Operacional" : "Falha";
  elements.lastReading.textContent = formatDate(status.last_reading);

  const descriptions = {
    NORMAL: "Área monitorada em condição normal",
    ALERTA: "Objeto dentro da distância de segurança",
    SEM_SINAL: "Sem leituras recentes do sensor",
    AGUARDANDO: "Aguardando a primeira leitura",
  };
  elements.statusDescription.textContent = descriptions[situation] || situation;

  const online = Boolean(status.mqtt_connected);
  elements.connectionPill.className = `connection-pill ${online ? "online" : "offline"}`;
  elements.connectionText.textContent = online ? "MQTT conectado" : "MQTT desconectado";
}

function drawChart() {
  const canvas = elements.chart;
  const context = canvas.getContext("2d");
  const ratio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  canvas.width = width * ratio;
  canvas.height = height * ratio;
  context.scale(ratio, ratio);
  context.clearRect(0, 0, width, height);

  const padding = { top: 15, right: 15, bottom: 28, left: 42 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  const values = readings.map((reading) => Number(reading.distance_cm));
  const maxValue = Math.max(100, ...values, 30) * 1.08;

  context.font = "11px system-ui";
  context.lineWidth = 1;
  context.textAlign = "right";
  context.textBaseline = "middle";
  for (let step = 0; step <= 4; step += 1) {
    const y = padding.top + (chartHeight * step) / 4;
    const label = Math.round(maxValue - (maxValue * step) / 4);
    context.strokeStyle = "rgba(148, 177, 211, .1)";
    context.beginPath();
    context.moveTo(padding.left, y);
    context.lineTo(width - padding.right, y);
    context.stroke();
    context.fillStyle = "#788da5";
    context.fillText(String(label), padding.left - 9, y);
  }

  const alertY = padding.top + chartHeight - (30 / maxValue) * chartHeight;
  context.setLineDash([5, 5]);
  context.strokeStyle = "rgba(255, 95, 104, .55)";
  context.beginPath();
  context.moveTo(padding.left, alertY);
  context.lineTo(width - padding.right, alertY);
  context.stroke();
  context.setLineDash([]);

  if (values.length === 0) {
    context.fillStyle = "#8fa3ba";
    context.textAlign = "center";
    context.fillText("As leituras aparecerão aqui", width / 2, height / 2);
    return;
  }

  const pointX = (index) => padding.left + (index / Math.max(1, values.length - 1)) * chartWidth;
  const pointY = (value) => padding.top + chartHeight - (value / maxValue) * chartHeight;
  const gradient = context.createLinearGradient(0, padding.top, 0, padding.top + chartHeight);
  gradient.addColorStop(0, "rgba(66, 215, 209, .32)");
  gradient.addColorStop(1, "rgba(66, 215, 209, 0)");

  context.beginPath();
  values.forEach((value, index) => {
    const x = pointX(index);
    const y = pointY(value);
    if (index === 0) context.moveTo(x, y);
    else context.lineTo(x, y);
  });
  context.lineTo(pointX(values.length - 1), padding.top + chartHeight);
  context.lineTo(pointX(0), padding.top + chartHeight);
  context.closePath();
  context.fillStyle = gradient;
  context.fill();

  context.beginPath();
  values.forEach((value, index) => {
    const x = pointX(index);
    const y = pointY(value);
    if (index === 0) context.moveTo(x, y);
    else context.lineTo(x, y);
  });
  context.strokeStyle = "#42d7d1";
  context.lineWidth = 2;
  context.lineJoin = "round";
  context.stroke();

  context.fillStyle = "#788da5";
  context.textAlign = "left";
  context.textBaseline = "top";
  context.fillText(formatDate(readings[0].measured_at).split(" ").at(-1), padding.left, height - 19);
  context.textAlign = "right";
  context.fillText(formatDate(readings.at(-1).measured_at).split(" ").at(-1), width - padding.right, height - 19);
}

function appendCell(row, value, className = "") {
  const cell = document.createElement("td");
  cell.textContent = value;
  if (className) cell.className = className;
  row.append(cell);
  return cell;
}

function renderAlerts(alerts) {
  elements.alertCount.textContent = String(alerts.length);
  elements.openAlertCount.textContent = String(alerts.filter((alert) => !alert.ended_at).length);
  elements.ackAlertCount.textContent = String(alerts.filter((alert) => alert.acknowledged_at).length);
  elements.alertsBody.replaceChildren();

  if (alerts.length === 0) {
    const row = document.createElement("tr");
    const cell = appendCell(row, "Nenhum alerta registrado.", "empty-state");
    cell.colSpan = 5;
    elements.alertsBody.append(row);
    return;
  }

  alerts.forEach((alert) => {
    const row = document.createElement("tr");
    appendCell(row, formatDate(alert.started_at));
    appendCell(row, formatDuration(alert.started_at, alert.ended_at));
    appendCell(row, `${Number(alert.min_distance_cm).toFixed(1)} cm`);
    const stateCell = document.createElement("td");
    const stateTag = document.createElement("span");
    stateTag.className = `state-tag ${alert.ended_at ? "closed" : "open"}`;
    stateTag.textContent = alert.ended_at ? "Encerrado" : "Em andamento";
    stateCell.append(stateTag);
    row.append(stateCell);

    const actionCell = document.createElement("td");
    if (alert.acknowledged_at) {
      const label = document.createElement("span");
      label.className = "muted";
      label.textContent = `Reconhecido por ${alert.acknowledged_by}`;
      actionCell.append(label);
    } else {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "ack-button";
      button.dataset.alertId = String(alert.id);
      button.textContent = "Reconhecer";
      actionCell.append(button);
    }
    row.append(actionCell);
    elements.alertsBody.append(row);
  });
}

async function refreshData() {
  try {
    const [readingsResponse, alertsResponse] = await Promise.all([
      fetch("/api/readings?limit=120"),
      fetch("/api/alerts?limit=50"),
    ]);
    if (!readingsResponse.ok || !alertsResponse.ok) throw new Error("Falha ao consultar API");
    readings = await readingsResponse.json();
    const alerts = await alertsResponse.json();
    drawChart();
    renderAlerts(alerts);
  } catch (error) {
    console.error(error);
  }
}

async function refreshStatus() {
  try {
    const response = await fetch("/api/status");
    if (!response.ok) throw new Error("Falha ao consultar estado");
    renderStatus(await response.json());
  } catch (error) {
    console.error(error);
  }
}

async function acknowledgeAlert(alertId) {
  const operator = window.prompt("Nome do operador:", "operador");
  if (!operator) return;
  const response = await fetch(`/api/alerts/${alertId}/acknowledge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ operator }),
  });
  if (response.ok) await refreshData();
}

function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocket(`${protocol}//${window.location.host}/ws/status`);
  socket.addEventListener("open", () => {
    socketRetry = 1000;
    if (statusPoll) window.clearInterval(statusPoll);
    statusPoll = null;
  });
  socket.addEventListener("message", (event) => renderStatus(JSON.parse(event.data)));
  socket.addEventListener("close", () => {
    elements.connectionPill.className = "connection-pill offline";
    elements.connectionText.textContent = "API desconectada";
    refreshStatus();
    if (!statusPoll) statusPoll = window.setInterval(refreshStatus, 2000);
    window.setTimeout(connectWebSocket, socketRetry);
    socketRetry = Math.min(socketRetry * 2, 15000);
  });
}

elements.refreshButton.addEventListener("click", refreshData);
elements.alertsBody.addEventListener("click", (event) => {
  const button = event.target.closest("[data-alert-id]");
  if (button) acknowledgeAlert(button.dataset.alertId);
});
window.addEventListener("resize", drawChart);

connectWebSocket();
refreshStatus();
refreshData();
window.setInterval(refreshData, 5000);
