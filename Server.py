from flask import Flask, jsonify, request
from flask_cors import CORS
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)

API_SECRET = os.environ.get("API_SECRET", "gloryvn_secret_2024")

# ── State ─────────────────────────────────────────────────────────────────────
config_state = {
    # === LỆNH KẾT NỐI (Panel → Client) ===
    "connect":    False,   # Panel bật → Client tự kết nối ADB + start ESP
    "disconnect": False,   # Panel bật → Client ngắt kết nối + dừng ESP

    # === ESP FEATURES ===
    "AimbotNewEnabled": False,
    "ESPLine":          False,
    "ESPBox2":          False,
    "ESPWukong":        False,
    "ESPInfo":          False,
    "ESPSkeleton":      False,
    "ESPREFRESH":       False,
    "FixEsp":           True,
    "linePosition":     "Top",

    # === TRẠNG THÁI CLIENT (Client → Server báo cáo) ===
    "client_status":    "waiting",   # waiting | connecting | connected | error
    "client_message":   "",          # Thông báo chi tiết từ client
    "client_last_seen": None,        # Lần cuối client ping

    "last_updated": datetime.utcnow().isoformat()
}

def verify_token(req):
    token = req.headers.get("X-API-Secret") or req.args.get("secret")
    return token == API_SECRET

# ── Trang web ─────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    path = os.path.join(os.path.dirname(__file__), "index.html")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

# ── GET /api/config  (ESP.cs poll mỗi 2s) ────────────────────────────────────
@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify(config_state)

# ── POST /api/config  (Panel cập nhật config/lệnh) ───────────────────────────
@app.route("/api/config", methods=["POST"])
def update_config():
    if not verify_token(request):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    allowed_keys = {
        "connect", "disconnect",
        "AimbotNewEnabled", "ESPLine", "ESPBox2", "ESPWukong",
        "ESPInfo", "ESPSkeleton", "ESPREFRESH", "FixEsp", "linePosition"
    }
    for key, value in data.items():
        if key in allowed_keys:
            config_state[key] = value

    config_state["last_updated"] = datetime.utcnow().isoformat()
    return jsonify({"ok": True, "config": config_state})

# ── POST /api/status  (ESP.cs / Program.cs báo trạng thái về) ────────────────
@app.route("/api/status", methods=["POST"])
def update_status():
    # Không cần token — client nội bộ tự báo
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    if "status" in data:
        config_state["client_status"] = data["status"]
    if "message" in data:
        config_state["client_message"] = data.get("message", "")

    config_state["client_last_seen"] = datetime.utcnow().isoformat()

    # Auto-reset flag sau khi client xác nhận
    if data.get("status") == "connected":
        config_state["connect"] = False       # lệnh đã thực thi xong
    if data.get("status") == "waiting":
        config_state["disconnect"] = False    # disconnect xong → reset

    return jsonify({"ok": True})

# ── POST /api/toggle/<feature>  (toggle nhanh từ panel) ──────────────────────
@app.route("/api/toggle/<feature>", methods=["POST"])
def toggle_feature(feature):
    if not verify_token(request):
        return jsonify({"error": "Unauthorized"}), 401

    bool_keys = {
        "connect", "disconnect",
        "AimbotNewEnabled", "ESPLine", "ESPBox2", "ESPWukong",
        "ESPInfo", "ESPSkeleton", "ESPREFRESH", "FixEsp"
    }
    if feature not in bool_keys:
        return jsonify({"error": f"Unknown feature: {feature}"}), 400

    config_state[feature] = not config_state[feature]
    config_state["last_updated"] = datetime.utcnow().isoformat()
    return jsonify({"ok": True, "feature": feature, "value": config_state[feature]})

# ── Health ────────────────────────────────────────────────────────────────────
@app.route("/health")
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)