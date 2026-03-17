"""
Glory VN Panel Server — v2.0
Hệ thống Auth + HWID binding + Per-user Config
Sử dụng Supabase để lưu keys, users, configs
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import jwt
import bcrypt
import secrets
import string
from datetime import datetime, timedelta
from supabase import create_client, Client

app = Flask(__name__)
CORS(app)

# ── Environment Variables ────────────────────────────────────────────────────
#  Trên Render: Settings → Environment Variables
#  SUPABASE_URL   = https://xxxx.supabase.co
#  SUPABASE_KEY   = service_role key (Settings → API → service_role)
#  JWT_SECRET     = chuỗi bí mật bất kỳ (>= 32 ký tự)
#  ADMIN_SECRET   = mật khẩu admin để tạo key
JWT_SECRET    = "GloryVN2026"
ADMIN_SECRET  = "AdminGloryVN"

SUPABASE_URL  = "https://utpnnnmekrvqxkkgemqw.supabase.co"
SUPABASE_KEY  = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InV0cG5ubm1la3J2cXhra2dlbXF3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM2NjAyNTksImV4cCI6MjA4OTIzNjI1OX0.dhQB4xD_L0a0fwo4gf0hl1pjNvVyeyyZYVZpnXwNep8"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ════════════════════════════════════════════════════════════════════════════

def make_jwt(user_id: str, username: str) -> str:
    payload = {
        "user_id":  user_id,
        "username": username,
        "exp": datetime.utcnow() + timedelta(days=7)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def decode_jwt(req) -> dict | None:
    """Lấy JWT từ Authorization header hoặc query param ?token="""
    auth = req.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else (
        req.headers.get("X-API-Secret") or req.args.get("token")
    )
    if not token:
        return None
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        return None


def is_admin(req) -> bool:
    secret = req.headers.get("X-Admin-Secret") or req.args.get("admin_secret")
    return secret == ADMIN_SECRET


def row_to_config(d: dict) -> dict:
    """Chuyển DB row sang dict trả về client"""
    return {
        "Connect":          d.get("connect",          False),
        "AimbotNewEnabled": d.get("aimbot_enabled",   False),
        "AimbotDelay":      round(float(d.get("aimbot_delay", 0.1)), 2),
        "ESPLine":          d.get("esp_line",         False),
        "ESPBox2":          d.get("esp_box2",         False),
        "ESPWukong":        d.get("esp_wukong",       False),
        "ESPInfo":          d.get("esp_info",         False),
        "ESPSkeleton":      d.get("esp_skeleton",     False),
        "ESPREFRESH":       d.get("esp_refresh",      False),
        "FixEsp":           d.get("fix_esp",          True),
        "linePosition":     d.get("line_position",    "Top"),
        "last_updated":     d.get("last_updated",     ""),
    }


KEY_MAP = {
    "Connect":          "connect",
    "AimbotNewEnabled": "aimbot_enabled",
    "AimbotDelay":      "aimbot_delay",
    "ESPLine":          "esp_line",
    "ESPBox2":          "esp_box2",
    "ESPWukong":        "esp_wukong",
    "ESPInfo":          "esp_info",
    "ESPSkeleton":      "esp_skeleton",
    "ESPREFRESH":       "esp_refresh",
    "FixEsp":           "fix_esp",
    "linePosition":     "line_position",
}


def get_or_create_config(user_id: str) -> dict:
    res = supabase.table("configs").select("*").eq("user_id", user_id).execute()
    if res.data:
        return row_to_config(res.data[0])
    # Tạo config mặc định
    supabase.table("configs").insert({
        "user_id":       user_id,
        "connect":       False,
        "aimbot_enabled":False,
        "aimbot_delay":  0.1,
        "esp_line":      False,
        "esp_box2":      False,
        "esp_wukong":    False,
        "esp_info":      False,
        "esp_skeleton":  False,
        "esp_refresh":   False,
        "fix_esp":       True,
        "line_position": "Top",
    }).execute()
    return get_or_create_config(user_id)


def patch_config(user_id: str, data: dict) -> dict:
    update = {"last_updated": datetime.utcnow().isoformat()}
    for k, v in data.items():
        if k in KEY_MAP:
            update[KEY_MAP[k]] = v
    supabase.table("configs").update(update).eq("user_id", user_id).execute()
    return get_or_create_config(user_id)


def touch_user(user_id: str):
    supabase.table("users").update({
        "last_seen": datetime.utcnow().isoformat()
    }).eq("id", user_id).execute()


# ════════════════════════════════════════════════════════════════════════════
#  SERVE HTML
# ════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()


# ════════════════════════════════════════════════════════════════════════════
#  ADMIN — Tạo & xem keys
# ════════════════════════════════════════════════════════════════════════════

@app.route("/api/admin/generate-keys", methods=["POST"])
def admin_generate_keys():
    if not is_admin(request):
        return jsonify({"error": "Unauthorized"}), 401

    data   = request.get_json(force=True) or {}
    count  = max(1, min(int(data.get("count", 1)), 50))
    note   = data.get("note", "")
    keys   = []
    chars  = string.ascii_uppercase + string.digits

    for _ in range(count):
        key = "GLORY-" + "-".join(
            "".join(secrets.choice(chars) for _ in range(5))
            for _ in range(4)
        )
        supabase.table("keys").insert({"key": key, "is_used": False, "note": note}).execute()
        keys.append(key)

    return jsonify({"ok": True, "keys": keys, "count": len(keys)})


@app.route("/api/admin/keys", methods=["GET"])
def admin_list_keys():
    if not is_admin(request):
        return jsonify({"error": "Unauthorized"}), 401
    res = supabase.table("keys").select("*").order("created_at", desc=True).execute()
    return jsonify(res.data)


@app.route("/api/admin/users", methods=["GET"])
def admin_list_users():
    if not is_admin(request):
        return jsonify({"error": "Unauthorized"}), 401
    res = supabase.table("users").select(
        "id, username, hwid, is_active, created_at, last_seen"
    ).order("created_at", desc=True).execute()
    return jsonify(res.data)


@app.route("/api/admin/users/<user_id>/toggle", methods=["POST"])
def admin_toggle_user(user_id):
    if not is_admin(request):
        return jsonify({"error": "Unauthorized"}), 401
    res = supabase.table("users").select("is_active").eq("id", user_id).single().execute()
    if not res.data:
        return jsonify({"error": "User not found"}), 404
    new_state = not res.data["is_active"]
    supabase.table("users").update({"is_active": new_state}).eq("id", user_id).execute()
    return jsonify({"ok": True, "is_active": new_state})


@app.route("/api/admin/users/<user_id>/reset-hwid", methods=["POST"])
def admin_reset_hwid(user_id):
    """Admin reset HWID để user có thể bind thiết bị mới"""
    if not is_admin(request):
        return jsonify({"error": "Unauthorized"}), 401
    supabase.table("users").update({"hwid": None}).eq("id", user_id).execute()
    return jsonify({"ok": True, "message": "HWID đã được reset"})


# ════════════════════════════════════════════════════════════════════════════
#  AUTH — Register / Login (Web)
# ════════════════════════════════════════════════════════════════════════════

@app.route("/api/auth/register", methods=["POST"])
def register():
    data     = request.get_json(force=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    key      = data.get("key", "").strip().upper()

    # Validate input
    if not username or not password or not key:
        return jsonify({"error": "Thiếu username, password hoặc key"}), 400
    if len(username) < 3 or len(username) > 20:
        return jsonify({"error": "Username phải từ 3–20 ký tự"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password phải có ít nhất 6 ký tự"}), 400
    if not username.replace("_", "").isalnum():
        return jsonify({"error": "Username chỉ gồm chữ, số và dấu _"}), 400

    # Kiểm tra key hợp lệ
    key_res = supabase.table("keys").select("*").eq("key", key).eq("is_used", False).execute()
    if not key_res.data:
        return jsonify({"error": "Key không hợp lệ hoặc đã được sử dụng"}), 400
    key_id = key_res.data[0]["id"]

    # Kiểm tra username đã tồn tại
    dup = supabase.table("users").select("id").eq("username", username).execute()
    if dup.data:
        return jsonify({"error": "Username đã tồn tại, hãy chọn tên khác"}), 400

    # Hash password + tạo user
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user_res = supabase.table("users").insert({
        "username":      username,
        "password_hash": pw_hash,
        "key_id":        key_id,
        "hwid":          None,
        "is_active":     True,
    }).execute()
    user_id = user_res.data[0]["id"]

    # Đánh dấu key đã dùng
    supabase.table("keys").update({
        "is_used":  True,
        "used_by":  user_id,
        "used_at":  datetime.utcnow().isoformat(),
    }).eq("id", key_id).execute()

    # Tạo config mặc định
    get_or_create_config(user_id)

    token = make_jwt(user_id, username)
    return jsonify({
        "ok":         True,
        "token":      token,
        "username":   username,
        "user_id":    user_id,
        "hwid_bound": False,
    })


@app.route("/api/auth/login", methods=["POST"])
def login():
    data     = request.get_json(force=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"error": "Thiếu username hoặc password"}), 400

    user_res = supabase.table("users").select("*").eq("username", username).execute()
    if not user_res.data:
        return jsonify({"error": "Tài khoản không tồn tại"}), 401
    user = user_res.data[0]

    if not user.get("is_active", True):
        return jsonify({"error": "Tài khoản đã bị khoá"}), 403

    if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return jsonify({"error": "Sai mật khẩu"}), 401

    touch_user(user["id"])
    token = make_jwt(user["id"], username)
    return jsonify({
        "ok":         True,
        "token":      token,
        "username":   username,
        "user_id":    user["id"],
        "hwid_bound": bool(user.get("hwid")),
    })


@app.route("/api/auth/me", methods=["GET"])
def auth_me():
    payload = decode_jwt(request)
    if not payload:
        return jsonify({"error": "Unauthorized"}), 401
    res = supabase.table("users").select(
        "id, username, hwid, is_active, created_at, last_seen"
    ).eq("id", payload["user_id"]).single().execute()
    if not res.data:
        return jsonify({"error": "User not found"}), 404
    u = res.data
    hwid_raw = u.get("hwid") or ""
    # Trả về HWID masked để hiển thị trên UI (không lộ full)
    if hwid_raw:
        hwid_display = hwid_raw[:4] + "****" + hwid_raw[-4:] if len(hwid_raw) > 8 else "****"
    else:
        hwid_display = None
    return jsonify({
        "user_id":    u["id"],
        "username":   u["username"],
        "hwid_bound": bool(hwid_raw),
        "hwid_value": hwid_display,
        "is_active":  u.get("is_active", True),
        "last_seen":  u.get("last_seen"),
    })


# ════════════════════════════════════════════════════════════════════════════
#  AUTH — Login từ PC + Bind HWID
# ════════════════════════════════════════════════════════════════════════════

@app.route("/api/device/login", methods=["POST"])
def device_login():
    """
    PC Client gọi endpoint này khi khởi động.
    Xác thực username/password + HWID.
    Lần đầu: tự động bind HWID vào tài khoản.
    Các lần sau: kiểm tra HWID khớp.
    """
    data     = request.get_json(force=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    hwid     = data.get("hwid", "").strip()

    if not username or not password or not hwid:
        return jsonify({"error": "Missing credentials or HWID"}), 400

    user_res = supabase.table("users").select("*").eq("username", username).execute()
    if not user_res.data:
        return jsonify({"error": "Invalid credentials"}), 401
    user = user_res.data[0]

    if not user.get("is_active", True):
        return jsonify({"error": "Account suspended"}), 403

    if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return jsonify({"error": "Invalid credentials"}), 401

    existing_hwid = user.get("hwid")

    if existing_hwid:
        # HWID đã bind → phải khớp
        if existing_hwid != hwid:
            return jsonify({
                "error": "HWID không khớp — thiết bị này không được phép. Liên hệ admin để reset."
            }), 403
    else:
        # Chưa bind → kiểm tra HWID chưa được dùng bởi tài khoản khác
        hwid_check = supabase.table("users").select("id, username").eq("hwid", hwid).execute()
        if hwid_check.data:
            return jsonify({
                "error": "HWID này đã được đăng ký với tài khoản khác"
            }), 403
        # Bind HWID
        supabase.table("users").update({"hwid": hwid}).eq("id", user["id"]).execute()

    touch_user(user["id"])
    token = make_jwt(user["id"], username)
    return jsonify({
        "ok":       True,
        "token":    token,
        "username": username,
        "user_id":  user["id"],
    })


# ════════════════════════════════════════════════════════════════════════════
#  CONFIG — Web Panel (dùng JWT)
# ════════════════════════════════════════════════════════════════════════════

@app.route("/api/config", methods=["GET"])
def get_config():
    payload = decode_jwt(request)
    if not payload:
        return jsonify({"error": "Unauthorized"}), 401
    cfg = get_or_create_config(payload["user_id"])
    return jsonify(cfg)


@app.route("/api/config", methods=["POST"])
def update_config():
    payload = decode_jwt(request)
    if not payload:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(force=True) or {}
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    cfg = patch_config(payload["user_id"], data)
    return jsonify({"ok": True, "config": cfg})


# ════════════════════════════════════════════════════════════════════════════
#  CONFIG — PC Client (dùng HWID, poll mỗi 2s)
# ════════════════════════════════════════════════════════════════════════════

@app.route("/api/device/config", methods=["GET"])
def get_config_by_hwid():
    """
    ESP.cs gọi endpoint này mỗi 2 giây.
    Header: X-HWID: <hwid>
    Trả về config của user sở hữu HWID đó.
    """
    hwid = (request.headers.get("X-HWID") or request.args.get("hwid", "")).strip()
    if not hwid:
        return jsonify({"error": "Missing HWID"}), 400

    user_res = supabase.table("users").select("id, is_active").eq("hwid", hwid).execute()
    if not user_res.data:
        return jsonify({"error": "Device not registered. Please login first."}), 403

    user = user_res.data[0]
    if not user.get("is_active", True):
        return jsonify({"error": "Account suspended"}), 403

    touch_user(user["id"])
    cfg = get_or_create_config(user["id"])
    return jsonify(cfg)


# ════════════════════════════════════════════════════════════════════════════
#  TOGGLE (shortcut — web panel dùng)
# ════════════════════════════════════════════════════════════════════════════

@app.route("/api/toggle/<feature>", methods=["POST"])
def toggle_feature(feature):
    payload = decode_jwt(request)
    if not payload:
        return jsonify({"error": "Unauthorized"}), 401

    bool_features = {
        "AimbotNewEnabled", "ESPLine", "ESPBox2", "ESPWukong",
        "ESPInfo", "ESPSkeleton", "ESPREFRESH", "FixEsp", "Connect"
    }
    if feature not in bool_features:
        return jsonify({"error": f"Unknown feature: {feature}"}), 400

    cfg     = get_or_create_config(payload["user_id"])
    new_val = not cfg.get(feature, False)
    cfg     = patch_config(payload["user_id"], {feature: new_val})
    return jsonify({"ok": True, "feature": feature, "value": new_val})


# ════════════════════════════════════════════════════════════════════════════
#  CONFIG — Set float value (e.g. AimbotDelay)
# ════════════════════════════════════════════════════════════════════════════

@app.route("/api/config/set", methods=["POST"])
def set_config_value():
    """
    Web panel dùng để set giá trị float/string.
    Body: { "key": "AimbotDelay", "value": 0.35 }
    """
    payload = decode_jwt(request)
    if not payload:
        return jsonify({"error": "Unauthorized"}), 401

    data  = request.get_json(force=True) or {}
    key   = data.get("key", "")
    value = data.get("value")

    if key not in KEY_MAP or value is None:
        return jsonify({"error": "Invalid key or missing value"}), 400

    cfg = patch_config(payload["user_id"], {key: value})
    return jsonify({"ok": True, "config": cfg})


# ════════════════════════════════════════════════════════════════════════════
#  HEALTH
# ════════════════════════════════════════════════════════════════════════════

@app.route("/health")
def health():
    return jsonify({"status": "ok", "ts": datetime.utcnow().isoformat()})


# Thêm endpoint này vào Server.py
# Đặt trước dòng  if __name__ == "__main__":

@app.route("/api/device/check-hwid", methods=["GET"])
def check_hwid():
    """
    App gọi khi khởi động để kiểm tra HWID đã liên kết account chưa.
    Header: X-HWID: <hwid>
    Trả về: {"linked": true/false}
    """
    hwid = (request.headers.get("X-HWID") or request.args.get("hwid", "")).strip()
    if not hwid:
        return jsonify({"error": "Missing HWID"}), 400

    res = supabase.table("users").select("id").eq("hwid", hwid).execute()
    linked = bool(res.data)

    return jsonify({"linked": linked})

@app.route("/test-db")
def test_db():
    try:
        res = supabase.table("keys").select("*").execute()
        return {
            "count": len(res.data),
            "data": res.data
        }
    except Exception as e:
        return {"error": str(e)}
 

# ════════════════════════════════════════════════════════════════════════════
#  ACCOUNT SETTINGS — Bind HWID / Đổi username / Đổi mật khẩu
# ════════════════════════════════════════════════════════════════════════════

@app.route("/api/account/bind-hwid", methods=["POST"])
def bind_hwid():
    """
    Gán HWID vào tài khoản (chỉ khi chưa có HWID).
    Body: { "hwid": "<hwid_string>" }
    """
    payload = decode_jwt(request)
    if not payload:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(force=True) or {}
    hwid = data.get("hwid", "").strip()
    if not hwid:
        return jsonify({"error": "Thiếu HWID"}), 400

    user_res = supabase.table("users").select("id, hwid").eq("id", payload["user_id"]).single().execute()
    if not user_res.data:
        return jsonify({"error": "User not found"}), 404

    user = user_res.data
    if user.get("hwid"):
        return jsonify({"error": "Tài khoản đã có HWID. Liên hệ admin để reset nếu cần."}), 400

    # Kiểm tra HWID chưa được dùng bởi tài khoản khác
    hwid_check = supabase.table("users").select("id").eq("hwid", hwid).execute()
    if hwid_check.data:
        return jsonify({"error": "HWID này đã được gán vào tài khoản khác"}), 409

    supabase.table("users").update({"hwid": hwid}).eq("id", payload["user_id"]).execute()
    return jsonify({"ok": True, "message": "Đã gán HWID thành công"})


@app.route("/api/account/change-username", methods=["POST"])
def change_username():
    """
    Đổi tên đăng nhập.
    Body: { "new_username": "...", "password": "..." }
    Yêu cầu xác nhận mật khẩu hiện tại.
    """
    payload = decode_jwt(request)
    if not payload:
        return jsonify({"error": "Unauthorized"}), 401

    data         = request.get_json(force=True) or {}
    new_username = data.get("new_username", "").strip()
    password     = data.get("password", "")

    if not new_username or not password:
        return jsonify({"error": "Thiếu tên đăng nhập mới hoặc mật khẩu"}), 400
    if len(new_username) < 3 or len(new_username) > 20:
        return jsonify({"error": "Username phải từ 3–20 ký tự"}), 400
    if not new_username.replace("_", "").isalnum():
        return jsonify({"error": "Username chỉ gồm chữ, số và dấu _"}), 400

    user_res = supabase.table("users").select("id, username, password_hash").eq("id", payload["user_id"]).single().execute()
    if not user_res.data:
        return jsonify({"error": "User not found"}), 404
    user = user_res.data

    if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return jsonify({"error": "Mật khẩu không đúng"}), 401

    if new_username.lower() == user["username"].lower():
        return jsonify({"error": "Tên mới trùng với tên hiện tại"}), 400

    # Kiểm tra trùng username
    dup = supabase.table("users").select("id").eq("username", new_username).execute()
    if dup.data:
        return jsonify({"error": "Username đã tồn tại, hãy chọn tên khác"}), 400

    supabase.table("users").update({"username": new_username}).eq("id", payload["user_id"]).execute()
    new_token = make_jwt(payload["user_id"], new_username)
    return jsonify({"ok": True, "new_username": new_username, "token": new_token})


@app.route("/api/account/change-password", methods=["POST"])
def change_password():
    """
    Đổi mật khẩu.
    Body: { "old_password": "...", "new_password": "..." }
    """
    payload = decode_jwt(request)
    if not payload:
        return jsonify({"error": "Unauthorized"}), 401

    data         = request.get_json(force=True) or {}
    old_password = data.get("old_password", "")
    new_password = data.get("new_password", "")

    if not old_password or not new_password:
        return jsonify({"error": "Thiếu mật khẩu cũ hoặc mật khẩu mới"}), 400
    if len(new_password) < 6:
        return jsonify({"error": "Mật khẩu mới phải có ít nhất 6 ký tự"}), 400

    user_res = supabase.table("users").select("id, password_hash").eq("id", payload["user_id"]).single().execute()
    if not user_res.data:
        return jsonify({"error": "User not found"}), 404
    user = user_res.data

    if not bcrypt.checkpw(old_password.encode(), user["password_hash"].encode()):
        return jsonify({"error": "Mật khẩu cũ không đúng"}), 401

    new_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    supabase.table("users").update({"password_hash": new_hash}).eq("id", payload["user_id"]).execute()
    return jsonify({"ok": True, "message": "Đổi mật khẩu thành công"})


# ════════════════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)