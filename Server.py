from flask import Flask, jsonify, request, render_template_string
from flask_cors import CORS
import os
import json
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Secret token để bảo vệ API (set qua environment variable trên Render)
API_SECRET = os.environ.get("API_SECRET", "gloryvn_secret_2024")

# Trạng thái config mặc định
config_state = {
    "AimbotNewEnabled": False,
    "ESPLine": False,
    "ESPBox2": False,
    "ESPWukong": False,
    "ESPInfo": False,
    "ESPSkeleton": False,
    "ESPREFRESH": False,
    "FixEsp": True,
    "linePosition": "Top",
    "last_updated": datetime.utcnow().isoformat()
}

def verify_token(req):
    token = req.headers.get("X-API-Secret") or req.args.get("secret")
    return token == API_SECRET

# ── Trang web chính ──────────────────────────────────────────────────────────
HTML_PAGE = """<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Glory VN — ESP Control Panel</title>
  <style>
    :root {
      --bg: #0d0d14;
      --card: #13131f;
      --border: #2a2040;
      --purple: #9d7ae5;
      --purple-light: #b196f7;
      --purple-dark: #6b4faa;
      --green: #4ade80;
      --red: #f87171;
      --text: #e2d9f3;
      --muted: #7a6f96;
      --radius: 12px;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      background: var(--bg);
      color: var(--text);
      font-family: 'Segoe UI', system-ui, sans-serif;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 24px 16px 48px;
    }

    header {
      width: 100%;
      max-width: 560px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 28px;
    }

    header h1 {
      font-size: 1.5rem;
      font-weight: 700;
      background: linear-gradient(135deg, var(--purple-light), var(--purple));
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      letter-spacing: 0.5px;
    }

    #status-dot {
      width: 10px; height: 10px;
      border-radius: 50%;
      background: var(--muted);
      transition: background 0.3s;
      box-shadow: 0 0 0 0 transparent;
    }
    #status-dot.online {
      background: var(--green);
      box-shadow: 0 0 8px var(--green);
    }

    /* Auth card */
    #auth-card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 24px;
      width: 100%;
      max-width: 560px;
      margin-bottom: 20px;
    }
    #auth-card label {
      display: block;
      font-size: 0.8rem;
      color: var(--muted);
      margin-bottom: 6px;
      text-transform: uppercase;
      letter-spacing: 0.6px;
    }
    #auth-card .row {
      display: flex;
      gap: 10px;
    }
    #auth-card input {
      flex: 1;
      background: #1a1a2e;
      border: 1px solid var(--border);
      border-radius: 8px;
      color: var(--text);
      padding: 9px 13px;
      font-size: 0.92rem;
      outline: none;
      transition: border-color 0.2s;
    }
    #auth-card input:focus { border-color: var(--purple); }
    #auth-card button {
      background: var(--purple);
      color: #fff;
      border: none;
      border-radius: 8px;
      padding: 9px 20px;
      font-size: 0.9rem;
      cursor: pointer;
      font-weight: 600;
      transition: background 0.2s;
    }
    #auth-card button:hover { background: var(--purple-light); }

    /* Main panel */
    #panel {
      width: 100%;
      max-width: 560px;
      display: flex;
      flex-direction: column;
      gap: 14px;
    }

    .section-label {
      font-size: 0.7rem;
      text-transform: uppercase;
      letter-spacing: 1px;
      color: var(--muted);
      padding: 0 4px;
      margin-top: 6px;
    }

    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      overflow: hidden;
    }

    .toggle-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 14px 18px;
      border-bottom: 1px solid var(--border);
      transition: background 0.15s;
      cursor: pointer;
      user-select: none;
    }
    .toggle-row:last-child { border-bottom: none; }
    .toggle-row:hover { background: rgba(157,122,229,0.06); }

    .toggle-info { display: flex; flex-direction: column; gap: 2px; }
    .toggle-name {
      font-size: 0.95rem;
      font-weight: 500;
      color: var(--text);
    }
    .toggle-desc {
      font-size: 0.75rem;
      color: var(--muted);
    }

    /* Toggle switch */
    .switch {
      position: relative;
      width: 46px; height: 26px;
      flex-shrink: 0;
    }
    .switch input { opacity: 0; width: 0; height: 0; }
    .slider {
      position: absolute;
      inset: 0;
      background: #2a2040;
      border-radius: 26px;
      transition: background 0.3s;
    }
    .slider:before {
      content: "";
      position: absolute;
      width: 20px; height: 20px;
      left: 3px; bottom: 3px;
      background: white;
      border-radius: 50%;
      transition: transform 0.3s;
    }
    input:checked + .slider { background: var(--purple); }
    input:checked + .slider:before { transform: translateX(20px); }

    /* linePosition select */
    .select-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 14px 18px;
    }
    .select-row select {
      background: #1a1a2e;
      border: 1px solid var(--border);
      border-radius: 8px;
      color: var(--text);
      padding: 6px 12px;
      font-size: 0.88rem;
      outline: none;
      cursor: pointer;
    }
    .select-row select:focus { border-color: var(--purple); }

    /* Last updated */
    #last-update {
      font-size: 0.75rem;
      color: var(--muted);
      text-align: center;
      margin-top: 6px;
    }

    /* Toast */
    #toast {
      position: fixed;
      bottom: 28px; right: 20px;
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 10px 18px;
      font-size: 0.85rem;
      color: var(--text);
      opacity: 0;
      transform: translateY(12px);
      transition: opacity 0.3s, transform 0.3s;
      pointer-events: none;
      z-index: 999;
    }
    #toast.show { opacity: 1; transform: translateY(0); }
    #toast.success { border-color: var(--green); color: var(--green); }
    #toast.error   { border-color: var(--red);   color: var(--red);   }

    /* Loading spinner */
    .spinner {
      width: 18px; height: 18px;
      border: 2px solid var(--border);
      border-top-color: var(--purple);
      border-radius: 50%;
      animation: spin 0.7s linear infinite;
      display: inline-block;
    }
    @keyframes spin { to { transform: rotate(360deg); } }

    #loading {
      text-align: center;
      padding: 40px 0;
      color: var(--muted);
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 12px;
    }

    .badge {
      font-size: 0.7rem;
      padding: 2px 8px;
      border-radius: 99px;
      font-weight: 600;
    }
    .badge.on  { background: rgba(74,222,128,0.15); color: var(--green); }
    .badge.off { background: rgba(248,113,113,0.12); color: var(--red); }
  </style>
</head>
<body>

<header>
  <h1>⚡ Glory VN Panel</h1>
  <div id="status-dot" title="Server status"></div>
</header>

<!-- Auth -->
<div id="auth-card">
  <label>API Secret Token</label>
  <div class="row">
    <input type="password" id="token-input" placeholder="Nhập secret token..." />
    <button onclick="saveToken()">Lưu</button>
  </div>
</div>

<!-- Panel -->
<div id="panel">
  <div id="loading">
    <div class="spinner"></div>
    <span>Đang tải config...</span>
  </div>
</div>

<div id="last-update"></div>
<div id="toast"></div>

<script>
  const FEATURES = [
    {
      section: "🎯 Aim",
      items: [
        { key: "AimbotNewEnabled", name: "AimBot Enable", desc: "Bật / tắt chức năng Aimbot" },
      ]
    },
    {
      section: "👁️ ESP Visual",
      items: [
        { key: "ESPLine",      name: "ESP Line",     desc: "Vẽ đường thẳng tới kẻ địch" },
        { key: "ESPBox2",      name: "ESP Box",      desc: "Vẽ hộp 3D quanh kẻ địch" },
        { key: "ESPWukong",    name: "ESP Wukong",   desc: "Hiện ESP cho dạng Wukong" },
        { key: "ESPInfo",      name: "ESP INFO",     desc: "Hiển thị thông tin (tên, máu...)" },
        { key: "ESPSkeleton",  name: "ESP Skeleton", desc: "Vẽ skeleton / xương kẻ địch" },
      ]
    },
    {
      section: "⚙️ Misc ESP",
      items: [
        { key: "ESPREFRESH",   name: "ESP Refresh",  desc: "Tự động refresh entity cache" },
        { key: "FixEsp",       name: "ESP FIX",      desc: "Bật fix lỗi ESP" },
      ]
    }
  ];

  let token = localStorage.getItem("gloryvn_token") || "";
  let config = {};
  let pollTimer = null;

  // ── Init ──────────────────────────────────────────────────────────────────
  document.getElementById("token-input").value = token;

  function saveToken() {
    token = document.getElementById("token-input").value.trim();
    localStorage.setItem("gloryvn_token", token);
    showToast("Token đã lưu ✓", "success");
  }

  // ── Fetch config ──────────────────────────────────────────────────────────
  async function fetchConfig() {
    try {
      const res = await fetch("/api/config");
      if (!res.ok) throw new Error("HTTP " + res.status);
      config = await res.json();
      document.getElementById("status-dot").classList.add("online");
      renderPanel();
      updateLastUpdated();
    } catch (e) {
      document.getElementById("status-dot").classList.remove("online");
      console.error("fetchConfig error:", e);
    }
  }

  // ── Toggle feature ────────────────────────────────────────────────────────
  async function sendToggle(key, value) {
    try {
      const body = {};
      body[key] = value;
      const res = await fetch("/api/config", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-Secret": token
        },
        body: JSON.stringify(body)
      });
      const data = await res.json();
      if (!res.ok) {
        showToast("Lỗi: " + (data.error || res.status), "error");
        // Revert
        config[key] = !value;
        renderPanel();
        return;
      }
      config = data.config;
      renderPanel();
      updateLastUpdated();
      showToast(`${key}: ${value ? "ON ✓" : "OFF ✓"}`, "success");
    } catch (e) {
      showToast("Kết nối thất bại!", "error");
    }
  }

  async function sendLinePosition(val) {
    try {
      const res = await fetch("/api/config", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-Secret": token
        },
        body: JSON.stringify({ linePosition: val })
      });
      const data = await res.json();
      if (res.ok) {
        config = data.config;
        showToast("linePosition: " + val, "success");
        updateLastUpdated();
      } else {
        showToast("Lỗi: " + (data.error || res.status), "error");
      }
    } catch (e) {
      showToast("Kết nối thất bại!", "error");
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────
  function renderPanel() {
    const panel = document.getElementById("panel");
    panel.innerHTML = "";

    FEATURES.forEach(section => {
      const sectionEl = document.createElement("div");
      sectionEl.className = "section-label";
      sectionEl.textContent = section.section;
      panel.appendChild(sectionEl);

      const card = document.createElement("div");
      card.className = "card";

      section.items.forEach(item => {
        const isOn = !!config[item.key];
        const row = document.createElement("div");
        row.className = "toggle-row";
        row.innerHTML = `
          <div class="toggle-info">
            <span class="toggle-name">${item.name}</span>
            <span class="toggle-desc">${item.desc}</span>
          </div>
          <label class="switch" onclick="event.stopPropagation()">
            <input type="checkbox" ${isOn ? "checked" : ""} onchange="handleToggle('${item.key}', this.checked)" />
            <span class="slider"></span>
          </label>
        `;
        card.appendChild(row);
      });

      panel.appendChild(card);
    });

    // linePosition select (chỉ hiện khi ESPLine bật)
    const lpSection = document.createElement("div");
    lpSection.className = "section-label";
    lpSection.textContent = "📐 ESP Line Position";
    panel.appendChild(lpSection);

    const lpCard = document.createElement("div");
    lpCard.className = "card";
    const lineDisabled = !config.ESPLine;
    lpCard.innerHTML = `
      <div class="select-row">
        <div class="toggle-info">
          <span class="toggle-name">Line Position</span>
          <span class="toggle-desc">Vị trí điểm xuất phát đường ESP Line</span>
        </div>
        <select id="line-position-select" onchange="handleLinePosition(this.value)" ${lineDisabled ? "disabled" : ""}>
          <option value="Top"    ${config.linePosition === "Top"    ? "selected" : ""}>Top</option>
          <option value="Bottom" ${config.linePosition === "Bottom" ? "selected" : ""}>Bottom</option>
          <option value="Center" ${config.linePosition === "Center" ? "selected" : ""}>Center</option>
        </select>
      </div>
    `;
    panel.appendChild(lpCard);
  }

  function handleToggle(key, value) {
    config[key] = value;
    sendToggle(key, value);
    // Re-render để cập nhật linePosition disabled state
    renderPanel();
  }

  function handleLinePosition(val) {
    sendLinePosition(val);
  }

  function updateLastUpdated() {
    const el = document.getElementById("last-update");
    if (config.last_updated) {
      const d = new Date(config.last_updated + "Z");
      el.textContent = "Cập nhật lúc: " + d.toLocaleTimeString("vi-VN");
    }
  }

  // ── Toast ─────────────────────────────────────────────────────────────────
  let toastTimer;
  function showToast(msg, type) {
    const el = document.getElementById("toast");
    el.textContent = msg;
    el.className = "show " + (type || "");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.className = ""; }, 2500);
  }

  // ── Poll every 3s ─────────────────────────────────────────────────────────
  fetchConfig();
  pollTimer = setInterval(fetchConfig, 3000);
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return HTML_PAGE

# ── API: lấy toàn bộ config (ESP.cs poll endpoint này) ───────────────────────
@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify(config_state)

# ── API: cập nhật một hoặc nhiều key config ───────────────────────────────────
@app.route("/api/config", methods=["POST"])
def update_config():
    if not verify_token(request):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    allowed_keys = {
        "AimbotNewEnabled", "ESPLine", "ESPBox2", "ESPWukong",
        "ESPInfo", "ESPSkeleton", "ESPREFRESH", "FixEsp", "linePosition"
    }

    updated = {}
    for key, value in data.items():
        if key in allowed_keys:
            config_state[key] = value
            updated[key] = value

    config_state["last_updated"] = datetime.utcnow().isoformat()

    return jsonify({"ok": True, "updated": updated, "config": config_state})

# ── API: toggle một feature ───────────────────────────────────────────────────
@app.route("/api/toggle/<feature>", methods=["POST"])
def toggle_feature(feature):
    if not verify_token(request):
        return jsonify({"error": "Unauthorized"}), 401

    bool_keys = {
        "AimbotNewEnabled", "ESPLine", "ESPBox2", "ESPWukong",
        "ESPInfo", "ESPSkeleton", "ESPREFRESH", "FixEsp"
    }

    if feature not in bool_keys:
        return jsonify({"error": f"Unknown feature: {feature}"}), 400

    config_state[feature] = not config_state[feature]
    config_state["last_updated"] = datetime.utcnow().isoformat()

    return jsonify({"ok": True, "feature": feature, "value": config_state[feature]})

# ── Health check ──────────────────────────────────────────────────────────────
@app.route("/health")
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
