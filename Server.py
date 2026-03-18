"""
Glory VN Panel Server — v4.0
Hệ thống Auth + HWID binding + Per-user Config + Dynamic Key Expiry

Thời hạn tài khoản được tính ĐỘNG mỗi lần check:
  expires_at = keys.used_at + keys.duration_hours
  Nếu admin thay đổi duration_hours trên key → hiệu lực ngay với tất cả
  tài khoản đã dùng key đó, không cần sửa bảng users.
  duration_hours = NULL → key vĩnh viễn.
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import jwt
import bcrypt
import secrets
import string
from datetime import datetime, timedelta, timezone
from supabase import create_client, Client

app = Flask(__name__)
CORS(app)

# ── Environment Variables ────────────────────────────────────────────────────
JWT_SECRET    = "GloryVN2026"
ADMIN_SECRET  = "AdminGloryVN"

SUPABASE_URL  = "https://utpnnnmekrvqxkkgemqw.supabase.co"
SUPABASE_KEY  = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InV0cG5ubm1la3J2cXhra2dlbXF3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM2NjAyNTksImV4cCI6MjA4OTIzNjI1OX0.dhQB4xD_L0a0fwo4gf0hl1pjNvVyeyyZYVZpnXwNep8"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ════════════════════════════════════════════════════════════════════════════
#  HELPERS — JWT
# ════════════════════════════════════════════════════════════════════════════

def make_jwt(user_id: str, username: str) -> str:
    payload = {
        "user_id":  user_id,
        "username": username,
        "exp": datetime.utcnow() + timedelta(days=7)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def decode_jwt(req) -> dict | None:
    auth  = req.headers.get("Authorization", "")
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


# ════════════════════════════════════════════════════════════════════════════
#  HELPERS — KEY EXPIRY (tính động từ keys table)
# ════════════════════════════════════════════════════════════════════════════

def _parse_utc(iso_str) -> datetime | None:
    """Parse ISO string -> UTC-aware datetime. Tra None neu loi."""
    if not iso_str:
        return None
    try:
        s = iso_str.replace("Z", "+00:00") if iso_str.endswith("Z") else iso_str
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _calc_expiry_from_key(key_row) -> dict:
    """
    Tinh expiry tu key_row dict.
    key_row can co: duration_hours, used_at
    """
    if not key_row:
        return {"is_expired": False, "is_lifetime": True,
                "expires_at": None, "remaining_hours": None, "duration_hours": None}

    dh = key_row.get("duration_hours")
    if dh is None:
        return {"is_expired": False, "is_lifetime": True,
                "expires_at": None, "remaining_hours": None, "duration_hours": None}

    used_at_dt = _parse_utc(key_row.get("used_at"))
    if not used_at_dt:
        # Key co duration nhung chua co used_at -> chua bat dau tinh
        return {"is_expired": False, "is_lifetime": True,
                "expires_at": None, "remaining_hours": None, "duration_hours": float(dh)}

    expires_dt    = used_at_dt + timedelta(hours=float(dh))
    now           = datetime.now(timezone.utc)
    remaining_sec = (expires_dt - now).total_seconds()

    return {
        "is_expired":      remaining_sec <= 0,
        "is_lifetime":     False,
        "expires_at":      expires_dt.isoformat(),
        "remaining_hours": max(0.0, round(remaining_sec / 3600, 2)),
        "duration_hours":  float(dh),
    }


def get_key_expiry_for_user(user: dict) -> dict:
    """
    Tinh thoi han key cua user bang cach doc truc tiep tu bang keys.

    Logic:
      expires_at = keys.used_at + keys.duration_hours  (real-time moi lan check)
      duration_hours = NULL -> vinh vien
      Admin sua duration_hours -> hieu luc ngay voi tat ca tai khoan dung key do
    """
    key_id = user.get("key_id")
    if not key_id:
        return {"is_expired": False, "is_lifetime": True,
                "expires_at": None, "remaining_hours": None, "duration_hours": None,
                "used_at": None}

    key_res = supabase.table("keys").select(
        "duration_hours, used_at"
    ).eq("id", key_id).execute()

    if not key_res.data:
        return {"is_expired": False, "is_lifetime": True,
                "expires_at": None, "remaining_hours": None, "duration_hours": None,
                "used_at": None}

    key_row = key_res.data[0]
    expiry  = _calc_expiry_from_key(key_row)
    expiry["used_at"] = key_row.get("used_at")
    return expiry


def check_user_access(user_id: str):
    """
    Kiem tra user ton tai, khong bi khoa, key con han.
    Returns: (user_dict, expiry_dict) neu OK
             (None, (response, status_code)) neu loi
    """
    res = supabase.table("users").select(
        "id, username, hwid, is_active, key_id, created_at, last_seen"
    ).eq("id", user_id).execute()

    if not res.data:
        return None, (jsonify({"error": "User not found"}), 404)

    user = res.data[0]

    if not user.get("is_active", True):
        return None, (jsonify({"error": "Tai khoan da bi khoa"}), 403)

    expiry = get_key_expiry_for_user(user)
    if expiry["is_expired"]:
        return None, (jsonify({
            "error":      "Key da het han. Vui long lien he admin de gia han.",
            "expired":    True,
            "expires_at": expiry["expires_at"],
        }), 403)

    return user, expiry


# ════════════════════════════════════════════════════════════════════════════
#  HELPERS — CONFIG
# ════════════════════════════════════════════════════════════════════════════

def row_to_config(d: dict) -> dict:
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
        "StreamMode":       d.get("stream_mode", True),
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
    "StreamMode": "stream_mode",
}

EXPIRED_CONFIG = {
    "Connect": False, "AimbotNewEnabled": False, "AimbotDelay": 0.1,
    "ESPLine": False, "ESPBox2": False, "ESPWukong": False,
    "ESPInfo": False, "ESPSkeleton": False, "ESPREFRESH": False,
    "FixEsp": False, "linePosition": "Top", "last_updated": "",
}


def get_or_create_config(user_id: str) -> dict:
    res = supabase.table("configs").select("*").eq("user_id", user_id).execute()
    if res.data:
        return row_to_config(res.data[0])
    supabase.table("configs").insert({
        "user_id": user_id, "connect": True, "aimbot_enabled": False,
        "aimbot_delay": 0.1, "esp_line": False, "esp_box2": False,
        "esp_wukong": False, "esp_info": False, "esp_skeleton": False,
        "esp_refresh": False, "fix_esp": True, "line_position": "Top",
        "stream_mode": False,
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


def attach_expiry(cfg: dict, expiry: dict) -> dict:
    """Gan metadata han key vao config response."""
    cfg["_expired"]         = expiry["is_expired"]
    cfg["_is_lifetime"]     = expiry["is_lifetime"]
    cfg["_expires_at"]      = expiry["expires_at"]
    cfg["_remaining_hours"] = expiry["remaining_hours"]
    cfg["_duration_hours"]  = expiry.get("duration_hours")
    return cfg


# ════════════════════════════════════════════════════════════════════════════
#  SERVE HTML
# ════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()


# ════════════════════════════════════════════════════════════════════════════
#  ADMIN — Quan ly keys
# ════════════════════════════════════════════════════════════════════════════

@app.route("/api/admin/generate-keys", methods=["POST"])
def admin_generate_keys():
    if not is_admin(request):
        return jsonify({"error": "Unauthorized"}), 401

    data   = request.get_json(force=True) or {}
    count  = max(1, min(int(data.get("count", 1)), 50))
    note   = data.get("note", "")

    duration_hours = data.get("duration_hours", None)
    if duration_hours is not None:
        try:
            duration_hours = float(duration_hours)
            if duration_hours <= 0:
                duration_hours = None
        except (TypeError, ValueError):
            duration_hours = None

    keys  = []
    chars = string.ascii_uppercase + string.digits

    for _ in range(count):
        key = "GLORY-" + "-".join(
            "".join(secrets.choice(chars) for _ in range(5))
            for _ in range(4)
        )
        supabase.table("keys").insert({
            "key":            key,
            "is_used":        False,
            "note":           note,
            "duration_hours": duration_hours,
        }).execute()
        keys.append(key)

    return jsonify({
        "ok":             True,
        "keys":           keys,
        "count":          len(keys),
        "duration_hours": duration_hours,
    })


@app.route("/api/admin/keys", methods=["GET"])
def admin_list_keys():
    if not is_admin(request):
        return jsonify({"error": "Unauthorized"}), 401
    res = supabase.table("keys").select("*").order("created_at", desc=True).execute()
    return jsonify(res.data)


@app.route("/api/admin/keys/<key_id>", methods=["PATCH"])
def admin_patch_key(key_id):
    """
    Sua duration_hours cua mot key.
    Hieu luc NGAY LAP TUC voi tat ca tai khoan da dung key do.
    Body: { "duration_hours": 720 }  hoac  { "duration_hours": null }  (vinh vien)
    """
    if not is_admin(request):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(force=True) or {}
    if "duration_hours" not in data:
        return jsonify({"error": "Thieu truong duration_hours"}), 400

    dh = data["duration_hours"]
    if dh is not None:
        try:
            dh = float(dh)
            if dh <= 0:
                dh = None
        except (TypeError, ValueError):
            return jsonify({"error": "duration_hours phai la so duong hoac null"}), 400

    supabase.table("keys").update({"duration_hours": dh}).eq("id", key_id).execute()
    return jsonify({"ok": True, "key_id": key_id, "duration_hours": dh,
                    "message": "Cap nhat hieu luc ngay voi tat ca tai khoan dung key nay"})


@app.route("/api/admin/users", methods=["GET"])
def admin_list_users():
    if not is_admin(request):
        return jsonify({"error": "Unauthorized"}), 401

    users_res = supabase.table("users").select(
        "id, username, hwid, is_active, key_id, created_at, last_seen"
    ).order("created_at", desc=True).execute()

    # Batch-fetch tat ca keys can tra cuu
    key_ids = list({u["key_id"] for u in users_res.data if u.get("key_id")})
    keys_map = {}
    if key_ids:
        keys_res = supabase.table("keys").select(
            "id, key, duration_hours, used_at, note"
        ).in_("id", key_ids).execute()
        for k in keys_res.data:
            keys_map[k["id"]] = k

    result = []
    for u in users_res.data:
        key_row = keys_map.get(u.get("key_id"))
        expiry  = _calc_expiry_from_key(key_row)
        result.append({
            **u,
            "key_value":      key_row["key"]            if key_row else None,
            "duration_hours": key_row["duration_hours"] if key_row else None,
            "used_at":        key_row["used_at"]        if key_row else None,
            "key_note":       key_row["note"]            if key_row else None,
            **expiry,
        })
    return jsonify(result)


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
    if not is_admin(request):
        return jsonify({"error": "Unauthorized"}), 401
    supabase.table("users").update({"hwid": None}).eq("id", user_id).execute()
    return jsonify({"ok": True, "message": "HWID da duoc reset"})


@app.route("/api/admin/users/<user_id>/key-info", methods=["GET"])
def admin_user_key_info(user_id):
    """Tra ve thong tin han key hien tai cua user (real-time)."""
    if not is_admin(request):
        return jsonify({"error": "Unauthorized"}), 401

    user_res = supabase.table("users").select(
        "id, username, key_id"
    ).eq("id", user_id).single().execute()
    if not user_res.data:
        return jsonify({"error": "User not found"}), 404

    expiry = get_key_expiry_for_user(user_res.data)
    return jsonify({"user_id": user_id, **expiry})


# ════════════════════════════════════════════════════════════════════════════
#  AUTH — Register / Login
# ════════════════════════════════════════════════════════════════════════════

@app.route("/api/auth/register", methods=["POST"])
def register():
    data     = request.get_json(force=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    key      = data.get("key", "").strip().upper()

    if not username or not password or not key:
        return jsonify({"error": "Thieu username, password hoac key"}), 400
    if len(username) < 3 or len(username) > 20:
        return jsonify({"error": "Username phai tu 3-20 ky tu"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password phai co it nhat 6 ky tu"}), 400
    if not username.replace("_", "").isalnum():
        return jsonify({"error": "Username chi gom chu, so va dau _"}), 400

    # Kiem tra key hop le va chua dung
    key_res = supabase.table("keys").select("*").eq("key", key).eq("is_used", False).execute()
    if not key_res.data:
        return jsonify({"error": "Key khong hop le hoac da duoc su dung"}), 400
    key_row = key_res.data[0]
    key_id  = key_row["id"]

    dup = supabase.table("users").select("id").eq("username", username).execute()
    if dup.data:
        return jsonify({"error": "Username da ton tai, hay chon ten khac"}), 400

    # Tao user — KHONG luu expires_at, thoi han tinh dong tu keys table
    pw_hash  = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    now_iso  = datetime.utcnow().isoformat()

    user_res = supabase.table("users").insert({
        "username":      username,
        "password_hash": pw_hash,
        "key_id":        key_id,
        "hwid":          None,
        "is_active":     True,
    }).execute()
    user_id = user_res.data[0]["id"]

    # Danh dau key da dung + luu used_at = thoi diem bat dau tinh gio
    supabase.table("keys").update({
        "is_used": True,
        "used_by": user_id,
        "used_at": now_iso,
    }).eq("id", key_id).execute()

    get_or_create_config(user_id)
    token = make_jwt(user_id, username)

    # Tinh expiry ngay sau dang ky
    key_row["used_at"] = now_iso
    expiry = _calc_expiry_from_key(key_row)

    return jsonify({
        "ok":         True,
        "token":      token,
        "username":   username,
        "user_id":    user_id,
        "hwid_bound": False,
        **expiry,
    })


@app.route("/api/auth/login", methods=["POST"])
def login():
    data     = request.get_json(force=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"error": "Thieu username hoac password"}), 400

    user_res = supabase.table("users").select("*").eq("username", username).execute()
    if not user_res.data:
        return jsonify({"error": "Tai khoan khong ton tai"}), 401
    user = user_res.data[0]

    if not user.get("is_active", True):
        return jsonify({"error": "Tai khoan da bi khoa"}), 403

    if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return jsonify({"error": "Sai mat khau"}), 401

    touch_user(user["id"])
    token  = make_jwt(user["id"], username)
    expiry = get_key_expiry_for_user(user)

    return jsonify({
        "ok":         True,
        "token":      token,
        "username":   username,
        "user_id":    user["id"],
        "hwid_bound": bool(user.get("hwid")),
        **expiry,
    })


@app.route("/api/auth/me", methods=["GET"])
def auth_me():
    payload = decode_jwt(request)
    if not payload:
        return jsonify({"error": "Unauthorized"}), 401

    res = supabase.table("users").select(
        "id, username, hwid, is_active, key_id, created_at, last_seen"
    ).eq("id", payload["user_id"]).single().execute()
    if not res.data:
        return jsonify({"error": "User not found"}), 404
    u = res.data

    hwid_raw = u.get("hwid") or ""
    if hwid_raw:
        hwid_display = hwid_raw[:4] + "****" + hwid_raw[-4:] if len(hwid_raw) > 8 else "****"
    else:
        hwid_display = None

    expiry = get_key_expiry_for_user(u)

    return jsonify({
        "user_id":    u["id"],
        "username":   u["username"],
        "hwid_bound": bool(hwid_raw),
        "hwid_value": hwid_display,
        "is_active":  u.get("is_active", True),
        "last_seen":  u.get("last_seen"),
        **expiry,
    })


# ════════════════════════════════════════════════════════════════════════════
#  AUTH — PC Device Login
# ════════════════════════════════════════════════════════════════════════════

@app.route("/api/device/login", methods=["POST"])
def device_login():
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

    # Kiem tra han key real-time
    expiry = get_key_expiry_for_user(user)
    if expiry["is_expired"]:
        return jsonify({
            "error":      "Key da het han. Vui long lien he admin de gia han.",
            "expired":    True,
            "expires_at": expiry["expires_at"],
        }), 403

    existing_hwid = user.get("hwid")
    if existing_hwid:
        if existing_hwid != hwid:
            return jsonify({"error": "HWID khong khop. Lien he admin de reset."}), 403
    else:
        hwid_check = supabase.table("users").select("id").eq("hwid", hwid).execute()
        if hwid_check.data:
            return jsonify({"error": "HWID nay da duoc dang ky voi tai khoan khac"}), 403
        supabase.table("users").update({"hwid": hwid}).eq("id", user["id"]).execute()

    touch_user(user["id"])
    token = make_jwt(user["id"], username)

    return jsonify({
        "ok":       True,
        "token":    token,
        "username": username,
        "user_id":  user["id"],
        **expiry,
    })


# ════════════════════════════════════════════════════════════════════════════
#  CONFIG — Web Panel
# ════════════════════════════════════════════════════════════════════════════

@app.route("/api/config", methods=["GET"])
def get_config():
    payload = decode_jwt(request)
    if not payload:
        return jsonify({"error": "Unauthorized"}), 401

    user, expiry_or_err = check_user_access(payload["user_id"])
    if user is None:
        resp, code = expiry_or_err
        if code == 403:
            body = resp.get_json()
            if body.get("expired"):
                # Tra config tat het (200) thay vi 403 de frontend render duoc
                cfg = dict(EXPIRED_CONFIG)
                cfg["_expired"]         = True
                cfg["_is_lifetime"]     = False
                cfg["_expires_at"]      = body.get("expires_at")
                cfg["_remaining_hours"] = 0
                cfg["_duration_hours"]  = None
                return jsonify(cfg), 200
        return expiry_or_err

    touch_user(user["id"])
    cfg = get_or_create_config(payload["user_id"])
    return jsonify(attach_expiry(cfg, expiry_or_err))


@app.route("/api/config", methods=["POST"])
def update_config():
    payload = decode_jwt(request)
    if not payload:
        return jsonify({"error": "Unauthorized"}), 401

    user, expiry_or_err = check_user_access(payload["user_id"])
    if user is None:
        return expiry_or_err

    data = request.get_json(force=True) or {}
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    cfg = patch_config(payload["user_id"], data)
    return jsonify({"ok": True, "config": attach_expiry(cfg, expiry_or_err)})


# ════════════════════════════════════════════════════════════════════════════
#  CONFIG — PC Client (poll bang HWID)
# ════════════════════════════════════════════════════════════════════════════

@app.route("/api/device/config", methods=["GET"])
def get_config_by_hwid():
    hwid = (request.headers.get("X-HWID") or request.args.get("hwid", "")).strip()
    if not hwid:
        return jsonify({"error": "Missing HWID"}), 400

    user_res = supabase.table("users").select(
        "id, is_active, key_id"
    ).eq("hwid", hwid).execute()
    if not user_res.data:
        return jsonify({"error": "Device not registered. Please login first."}), 403

    user = user_res.data[0]
    if not user.get("is_active", True):
        return jsonify({"error": "Account suspended"}), 403

    # Kiem tra han key real-time tu DB
    expiry = get_key_expiry_for_user(user)
    if expiry["is_expired"]:
        cfg = dict(EXPIRED_CONFIG)
        cfg["_expired"]         = True
        cfg["_is_lifetime"]     = False
        cfg["_expires_at"]      = expiry["expires_at"]
        cfg["_remaining_hours"] = 0
        cfg["_duration_hours"]  = expiry.get("duration_hours")
        return jsonify(cfg)

    touch_user(user["id"])
    cfg = get_or_create_config(user["id"])
    return jsonify(attach_expiry(cfg, expiry))


# ════════════════════════════════════════════════════════════════════════════
#  TOGGLE / CONFIG SET
# ════════════════════════════════════════════════════════════════════════════

@app.route("/api/toggle/<feature>", methods=["POST"])
def toggle_feature(feature):
    payload = decode_jwt(request)
    if not payload:
        return jsonify({"error": "Unauthorized"}), 401

    user, expiry_or_err = check_user_access(payload["user_id"])
    if user is None:
        return expiry_or_err

    bool_features = {
        "AimbotNewEnabled", "ESPLine", "ESPBox2", "ESPWukong",
        "ESPInfo", "ESPSkeleton", "ESPREFRESH", "FixEsp", "Connect"
    }
    if feature not in bool_features:
        return jsonify({"error": f"Unknown feature: {feature}"}), 400

    cfg     = get_or_create_config(payload["user_id"])
    new_val = not cfg.get(feature, False)
    patch_config(payload["user_id"], {feature: new_val})
    return jsonify({"ok": True, "feature": feature, "value": new_val})


@app.route("/api/config/set", methods=["POST"])
def set_config_value():
    payload = decode_jwt(request)
    if not payload:
        return jsonify({"error": "Unauthorized"}), 401

    user, expiry_or_err = check_user_access(payload["user_id"])
    if user is None:
        return expiry_or_err

    data  = request.get_json(force=True) or {}
    key   = data.get("key", "")
    value = data.get("value")

    if key not in KEY_MAP or value is None:
        return jsonify({"error": "Invalid key or missing value"}), 400

    cfg = patch_config(payload["user_id"], {key: value})
    return jsonify({"ok": True, "config": cfg})


# ════════════════════════════════════════════════════════════════════════════
#  ACCOUNT SETTINGS
# ════════════════════════════════════════════════════════════════════════════

@app.route("/api/account/bind-hwid", methods=["POST"])
def bind_hwid():
    payload = decode_jwt(request)
    if not payload:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(force=True) or {}
    hwid = data.get("hwid", "").strip()
    if not hwid:
        return jsonify({"error": "Thieu HWID"}), 400

    user_res = supabase.table("users").select("id, hwid").eq("id", payload["user_id"]).single().execute()
    if not user_res.data:
        return jsonify({"error": "User not found"}), 404
    user = user_res.data
    if user.get("hwid"):
        return jsonify({"error": "Tai khoan da co HWID. Lien he admin de reset neu can."}), 400

    hwid_check = supabase.table("users").select("id").eq("hwid", hwid).execute()
    if hwid_check.data:
        return jsonify({"error": "HWID nay da duoc gan vao tai khoan khac"}), 409

    supabase.table("users").update({"hwid": hwid}).eq("id", payload["user_id"]).execute()
    return jsonify({"ok": True, "message": "Da gan HWID thanh cong"})


@app.route("/api/account/change-username", methods=["POST"])
def change_username():
    payload = decode_jwt(request)
    if not payload:
        return jsonify({"error": "Unauthorized"}), 401

    data         = request.get_json(force=True) or {}
    new_username = data.get("new_username", "").strip()
    password     = data.get("password", "")

    if not new_username or not password:
        return jsonify({"error": "Thieu ten dang nhap moi hoac mat khau"}), 400
    if len(new_username) < 3 or len(new_username) > 20:
        return jsonify({"error": "Username phai tu 3-20 ky tu"}), 400
    if not new_username.replace("_", "").isalnum():
        return jsonify({"error": "Username chi gom chu, so va dau _"}), 400

    user_res = supabase.table("users").select(
        "id, username, password_hash"
    ).eq("id", payload["user_id"]).single().execute()
    if not user_res.data:
        return jsonify({"error": "User not found"}), 404
    user = user_res.data

    if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return jsonify({"error": "Mat khau khong dung"}), 401
    if new_username.lower() == user["username"].lower():
        return jsonify({"error": "Ten moi trung voi ten hien tai"}), 400

    dup = supabase.table("users").select("id").eq("username", new_username).execute()
    if dup.data:
        return jsonify({"error": "Username da ton tai, hay chon ten khac"}), 400

    supabase.table("users").update({"username": new_username}).eq("id", payload["user_id"]).execute()
    new_token = make_jwt(payload["user_id"], new_username)
    return jsonify({"ok": True, "new_username": new_username, "token": new_token})


@app.route("/api/account/change-password", methods=["POST"])
def change_password():
    payload = decode_jwt(request)
    if not payload:
        return jsonify({"error": "Unauthorized"}), 401

    data         = request.get_json(force=True) or {}
    old_password = data.get("old_password", "")
    new_password = data.get("new_password", "")

    if not old_password or not new_password:
        return jsonify({"error": "Thieu mat khau cu hoac mat khau moi"}), 400
    if len(new_password) < 6:
        return jsonify({"error": "Mat khau moi phai co it nhat 6 ky tu"}), 400

    user_res = supabase.table("users").select(
        "id, password_hash"
    ).eq("id", payload["user_id"]).single().execute()
    if not user_res.data:
        return jsonify({"error": "User not found"}), 404
    user = user_res.data

    if not bcrypt.checkpw(old_password.encode(), user["password_hash"].encode()):
        return jsonify({"error": "Mat khau cu khong dung"}), 401

    new_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    supabase.table("users").update({"password_hash": new_hash}).eq("id", payload["user_id"]).execute()
    return jsonify({"ok": True, "message": "Doi mat khau thanh cong"})


# ════════════════════════════════════════════════════════════════════════════
#  DEVICE / HEALTH
# ════════════════════════════════════════════════════════════════════════════

@app.route("/api/device/check-hwid", methods=["GET"])
def check_hwid():
    hwid = (request.headers.get("X-HWID") or request.args.get("hwid", "")).strip()
    if not hwid:
        return jsonify({"error": "Missing HWID"}), 400
    res = supabase.table("users").select("id").eq("hwid", hwid).execute()
    return jsonify({"linked": bool(res.data)})


@app.route("/health")
def health():
    return jsonify({"status": "ok", "ts": datetime.utcnow().isoformat()})


@app.route("/test-db")
def test_db():
    try:
        res = supabase.table("keys").select("*").execute()
        return {"count": len(res.data), "data": res.data}
    except Exception as e:
        return {"error": str(e)}


# ════════════════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)