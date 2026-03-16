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
    "Connect": False,
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
@app.route("/")
def index():
    with open(os.path.join(os.path.dirname(__file__), "index.html"), "r", encoding="utf-8") as f:
        return f.read()

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
        "Connect",
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

@app.route("/api/connect", methods=["POST"])
def set_connect():
    if not verify_token(request):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(force=True)
    value = bool(data.get("Connect", False))

    config_state["Connect"] = value
    config_state["last_updated"] = datetime.utcnow().isoformat()

    return jsonify({"ok": True, "Connect": value})
    

# ── Health check ──────────────────────────────────────────────────────────────
@app.route("/health")
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)