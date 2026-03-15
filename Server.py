from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)
CORS(app)

API_SECRET = os.environ.get("API_SECRET", "gloryvn_secret_2024")

# ── State ─────────────────────────────────────────────────────────────────────
config_state = {
    "connect":    False,
    "disconnect": False,
    "AimbotNewEnabled": False,
    "ESPLine":          False,
    "ESPBox2":          False,
    "ESPWukong":        False,
    "ESPInfo":          False,
    "ESPSkeleton":      False,
    "ESPREFRESH":       False,
    "FixEsp":           True,
    "linePosition":     "Top",
    "client_status":    "waiting",
    "client_message":   "",
    "client_last_seen": None,
    "last_updated": datetime.utcnow().isoformat()
}

def verify_token(req):
    token = req.headers.get("X-API-Secret") or req.args.get("secret")
    return token == API_SECRET

# ── Trang web (route / và /index.html đều hoạt động) ─────────────────────────
@app.route("/")
@app.route("/index.html")
def index():
    return send_from_directory(BASE_DIR, "index.html")

# ── GET /api/config ───────────────────────────────────────────────────────────
@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify(config_state)

# ── POST /api/config ──────────────────────────────────────────────────────────
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

# ── POST /api/status ──────────────────────────────────────────────────────────
@app.route("/api/status", methods=["POST"])
def update_status():
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "No JSON body"}), 400
    if "status"  in data: config_state["client_status"]  = data["status"]
    if "message" in data: config_state["client_message"] = data["message"]
    config_state["client_last_seen"] = datetime.utcnow().isoformat()
    if data.get("status") == "connected": config_state["connect"]    = False
    if data.get("status") == "waiting":   config_state["disconnect"] = False
    return jsonify({"ok": True})

# ── POST /api/toggle/<feature> ────────────────────────────────────────────────
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
