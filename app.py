# -*- coding: utf-8 -*-
"""基于 YOLO 的高架车辆智能识别系统 - 后端服务

运行：python app.py    访问：http://127.0.0.1:5000
演示账号：admin / gaojia123
"""
import os
import re
import sys
import uuid
from datetime import datetime

from flask import Flask, jsonify, render_template, request, session
from PIL import Image

import auth
import database as db
from analyzer import Analyzer, draw_annotations, now_str
from plate_recognizer import PlateRecognizer
from rules import FINE_COOLDOWN_HOURS, SPEED_LIMIT, VEHICLE_RULES, VIOLATION_FINES
from sms_service import SMSService
from video_processor import VideoJobManager
from yolo_detector import get_detector

# 保证 Windows 控制台中文输出不报编码错误
try:
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    else:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    else:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
# 云端部署时可用 EVS_DATA_DIR 指向持久化磁盘，图片与数据库一同保留
DATA_DIR = os.environ.get("EVS_DATA_DIR")
if DATA_DIR:
    UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    link_path = os.path.join(BASE_DIR, "static", "uploads")
    try:
        if not os.path.islink(link_path) and not os.path.exists(link_path):
            os.symlink(UPLOAD_DIR, link_path)
        elif os.path.isdir(link_path) and not os.path.islink(link_path) and not os.listdir(link_path):
            os.rmdir(link_path)
            os.symlink(UPLOAD_DIR, link_path)
    except OSError:
        pass
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "elevated-vehicle-ai-2026-secret")
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 视频最大 200MB
app.config["TEMPLATES_AUTO_RELOAD"] = True

PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

db.init_db()
detector = get_detector()
plate_recognizer = PlateRecognizer()
sms_service = SMSService()
analyzer = Analyzer(detector, plate_recognizer, sms_service)
video_jobs = VideoJobManager(analyzer, UPLOAD_DIR)


# ---------- 页面与登录 ----------

@app.route("/login", methods=["GET"])
def login_page():
    # 每次进入页面都要求重新登录，因此这里不再自动跳转到首页
    return render_template("login.html",
                           default_user=db.DEFAULT_USERNAME,
                           default_pass=db.DEFAULT_PASSWORD,
                           user_user=db.USER_USERNAME,
                           user_pass=db.USER_PASSWORD)


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or request.form
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    role = (data.get("role") or "").strip()
    user = auth.check_login(username, password)
    if not user:
        return jsonify({"success": False, "error": "账号或密码错误"}), 401
    if role and user.get("role") != role:
        role_name = "管理员" if role == "admin" else "普通用户"
        return jsonify({"success": False, "error": "该账号不是%s账号，请选择正确的登录方式" % role_name}), 403
    session.clear()
    session["user"] = {"username": user["username"], "name": user["display_name"] or user["username"],
                       "role": user.get("role") or "admin",
                       "phone": user.get("phone") or "", "email": user.get("email") or ""}
    return jsonify({"success": True, "user": session["user"]})


@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json(silent=True) or request.form
    name = (data.get("name") or "").strip()
    account = (data.get("account") or "").strip()
    password = data.get("password") or ""
    if not name:
        return jsonify({"success": False, "error": "请填写昵称"}), 400
    if PHONE_RE.match(account):
        phone, email = account, ""
    elif EMAIL_RE.match(account):
        phone, email = "", account.lower()
    else:
        return jsonify({"success": False, "error": "请输入正确的手机号或邮箱"}), 400
    if len(password) < 6:
        return jsonify({"success": False, "error": "密码至少需要 6 位"}), 400
    if db.get_user_by_login(account):
        return jsonify({"success": False, "error": "该手机号或邮箱已注册"}), 400
    username = phone or email
    db.create_user(username, password, name, "user", phone, email)
    return jsonify({"success": True, "message": "注册成功，请登录"})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"success": True})


@app.route("/")
@auth.login_required
def index():
    return render_template("index.html", user=session.get("user"))


# ---------- 基础信息 ----------

def _forbid_non_admin():
    user = session.get("user") or {}
    if user.get("role") != "admin":
        return jsonify({"success": False, "error": "仅管理员可以使用数据统计功能"}), 403
    return None


@app.route("/api/info")
@auth.login_required
def api_info():
    return jsonify({
        "detector_mode": detector.mode,
        "plate_mode": plate_recognizer.mode,
        "sms_mode": sms_service.mode,
        "speed_limit": SPEED_LIMIT,
        "user": session.get("user"),
    })


@app.route("/api/stats")
@auth.login_required
def api_stats():
    deny = _forbid_non_admin()
    if deny:
        return deny
    s = db.get_stats()
    s["detector_mode"] = detector.mode
    s["plate_mode"] = plate_recognizer.mode
    s["sms_mode"] = sms_service.mode
    return jsonify(s)


@app.route("/api/stats/day")
@auth.login_required
def api_stats_day():
    deny = _forbid_non_admin()
    if deny:
        return deny
    day = (request.args.get("date") or "").strip()
    try:
        day = datetime.strptime(day, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        day = datetime.now().strftime("%Y-%m-%d")
    return jsonify(db.get_day_stats(day))


@app.route("/api/stats/hour")
@auth.login_required
def api_stats_hour():
    deny = _forbid_non_admin()
    if deny:
        return deny
    date = request.args.get("date") or datetime.now().strftime("%Y-%m-%d")
    if not DATE_RE.match(date):
        date = datetime.now().strftime("%Y-%m-%d")
    try:
        hour = int(request.args.get("hour", ""))
    except ValueError:
        return jsonify({"success": False, "error": "hour 必须是 0-23 的整数"}), 400
    if not 0 <= hour <= 23:
        return jsonify({"success": False, "error": "hour 必须是 0-23 的整数"}), 400
    return jsonify(db.get_hour_stats(date, hour))


# ---------- 图片识别 ----------

@app.route("/api/detect", methods=["POST"])
@auth.login_required
def api_detect():
    f = request.files.get("image")
    if not f or not f.filename:
        return jsonify({"success": False, "error": "未接收到图片文件"}), 400
    try:
        img = Image.open(f.stream).convert("RGB")
    except Exception:
        return jsonify({"success": False, "error": "图片格式无法解析，请上传 JPG/PNG 图片"}), 400

    if max(img.size) > 3000:
        img.thumbnail((3000, 3000))

    created_at = now_str()
    detections = analyzer.analyze(img)
    ann_name = "ann_%s.jpg" % uuid.uuid4().hex[:12]
    if detections:
        draw_annotations(img, detections).save(os.path.join(UPLOAD_DIR, ann_name), quality=90)
    else:
        ann_name = ""

    results = []
    for d in detections:
        analyzer.persist(d, "image", ann_name, created_at)
        results.append({
            "record_id": d["record_id"],
            "class_key": d["class_key"],
            "vehicle_type": d["vehicle_type"],
            "confidence": d["confidence"],
            "plate_no": d.get("plate_no", ""),
            "plate_confidence": d.get("plate_confidence", 0),
            "owner_name": d["owner_name"],
            "owner_phone": d["owner_phone"],
            "allowed": d["allowed"],
            "violation": d["violation"],
            "notified": d["notified"],
        })

    return jsonify({
        "success": True,
        "detections": results,
        "annotated_image": ("/static/uploads/" + ann_name) if ann_name else None,
        "summary": {
            "total": len(results),
            "allowed": sum(1 for r in results if r["allowed"]),
            "violations": sum(1 for r in results if r["violation"]),
        },
        "detector_mode": detector.mode,
        "plate_mode": plate_recognizer.mode,
    })


# ---------- 视频识别 ----------

VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}


@app.route("/api/detect_video", methods=["POST"])
@auth.login_required
def api_detect_video():
    f = request.files.get("video")
    if not f or not f.filename:
        return jsonify({"success": False, "error": "未接收到视频文件"}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in VIDEO_EXTS:
        return jsonify({"success": False, "error": "请上传 MP4/AVI/MOV/MKV/WEBM 格式的视频"}), 400

    src_name = "src_%s%s" % (uuid.uuid4().hex[:12], ext)
    src_path = os.path.join(UPLOAD_DIR, src_name)
    f.save(src_path)
    job_id = video_jobs.start(src_path)
    return jsonify({"success": True, "job_id": job_id})


@app.route("/api/video_status/<job_id>")
@auth.login_required
def api_video_status(job_id):
    job = video_jobs.get(job_id)
    if not job:
        return jsonify({"success": False, "error": "任务不存在或已过期"}), 404
    return jsonify(job)


# ---------- 记录 / 车主 / 短信 ----------

@app.route("/api/records")
@auth.login_required
def api_records():
    only = request.args.get("violation") == "1"
    source = request.args.get("source") or None
    date = request.args.get("date") or None
    if date and not DATE_RE.match(date):
        date = None
    order = "asc" if request.args.get("order") == "asc" else "desc"
    return jsonify(db.get_records(limit=200, only_violation=only, source=source, date=date, order=order))


@app.route("/api/records/<int:rid>", methods=["DELETE"])
@auth.login_required
def api_delete_record(rid):
    user = session.get("user") or {}
    if user.get("role") != "admin":
        return jsonify({"success": False, "error": "仅管理员可以删除识别记录"}), 403
    db.delete_record(rid)
    return jsonify({"success": True, "message": "记录已删除"})


# ---------- 我的记录（普通用户） ----------

def _current_db_user():
    u = session.get("user") or {}
    return db.get_user_by_username(u.get("username", ""))


@app.route("/api/my/profile")
@auth.login_required
def api_my_profile():
    user = _current_db_user()
    if not user:
        return jsonify({"success": False, "error": "用户不存在"}), 404
    return jsonify({
        "username": user["username"], "name": user["display_name"],
        "phone": user["phone"], "email": user["email"],
        "plates": db.get_user_plates(user["id"]),
    })


@app.route("/api/my/contact", methods=["POST"])
@auth.login_required
def api_my_contact():
    user = _current_db_user()
    if not user:
        return jsonify({"success": False, "error": "用户不存在"}), 404
    data = request.get_json(silent=True) or {}
    phone = (data.get("phone") or "").strip()
    email = (data.get("email") or "").strip().lower()
    if phone and not PHONE_RE.match(phone):
        return jsonify({"success": False, "error": "手机号格式不正确"}), 400
    if email and not EMAIL_RE.match(email):
        return jsonify({"success": False, "error": "邮箱格式不正确"}), 400
    for v, label in ((phone, "手机号"), (email, "邮箱")):
        if v:
            other = db.get_user_by_login(v)
            if other and other["id"] != user["id"]:
                return jsonify({"success": False, "error": "该%s已被其他账号使用" % label}), 400
    db.update_user_contact(user["id"], phone, email)
    return jsonify({"success": True, "message": "联系方式已保存"})


@app.route("/api/my/plates", methods=["POST"])
@auth.login_required
def api_my_plate_add():
    user = _current_db_user()
    if not user:
        return jsonify({"success": False, "error": "用户不存在"}), 404
    data = request.get_json(silent=True) or {}
    plate = (data.get("plate_no") or "").strip().upper().replace("·", "").replace("-", "").replace(" ", "")
    if not 5 <= len(plate) <= 8:
        return jsonify({"success": False, "error": "车牌号格式不正确"}), 400
    ok, msg = db.add_user_plate(user["id"], plate)
    return jsonify({"success": ok, "message": msg if ok else "", "error": "" if ok else msg}), (200 if ok else 400)


@app.route("/api/my/plates/<plate>", methods=["DELETE"])
@auth.login_required
def api_my_plate_remove(plate):
    user = _current_db_user()
    if not user:
        return jsonify({"success": False, "error": "用户不存在"}), 404
    ok = db.remove_user_plate(user["id"], plate)
    return jsonify({"success": ok, "message": "已解绑" if ok else "", "error": "" if ok else "未绑定该车牌"}), (200 if ok else 404)


@app.route("/api/my/violations")
@auth.login_required
def api_my_violations():
    user = _current_db_user()
    if not user:
        return jsonify({"success": False, "error": "用户不存在"}), 404
    plates = db.get_user_plates(user["id"])
    rows = db.get_violations_by_plates(plates)

    cooldown = FINE_COOLDOWN_HOURS * 3600
    last_fined = {}
    items, total_fine = [], 0
    for r in rows:
        std_fine = VIOLATION_FINES.get(r["violation"], 0)
        try:
            t = datetime.strptime(r["created_at"], "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            t = None
        key = (r["plate_no"], r["violation"])
        cooling = False
        prev = last_fined.get(key)
        if prev is not None and t is not None and 0 <= (t - prev).total_seconds() < cooldown:
            fine, cooling = 0, True
        else:
            fine = std_fine
            if t is not None:
                last_fined[key] = t
        total_fine += fine
        items.append({
            "id": r["id"], "plate_no": r["plate_no"], "vehicle_type": r["vehicle_type"],
            "violation": r["violation"], "source": r["source"], "created_at": r["created_at"],
            "image": ("/static/uploads/" + r["image"]) if r["image"] else "",
            "fine": fine, "standard_fine": std_fine, "cooling": cooling,
        })
    items.reverse()  # 最新在前
    return jsonify({
        "violations": items,
        "total_fine": total_fine,
        "cooling_count": sum(1 for i in items if i["cooling"]),
        "plates": plates,
    })


# ---------- 管理员：用户管理 ----------

@app.route("/api/admin/users")
@auth.login_required
def api_admin_users():
    deny = _forbid_non_admin()
    if deny:
        return deny
    return jsonify({"users": db.list_users()})


@app.route("/api/admin/users/<int:uid>/reset", methods=["POST"])
@auth.login_required
def api_admin_user_reset(uid):
    deny = _forbid_non_admin()
    if deny:
        return deny
    target = db.get_user_by_id(uid)
    if not target or target.get("role") != "user":
        return jsonify({"success": False, "error": "用户不存在"}), 404
    data = request.get_json(silent=True) or {}
    phone = (data.get("phone") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = (data.get("password") or "").strip()
    if phone and not PHONE_RE.match(phone):
        return jsonify({"success": False, "error": "手机号格式不正确"}), 400
    if email and not EMAIL_RE.match(email):
        return jsonify({"success": False, "error": "邮箱格式不正确"}), 400
    if password and len(password) < 6:
        return jsonify({"success": False, "error": "密码至少 6 位"}), 400
    for v, label in ((phone, "手机号"), (email, "邮箱")):
        if v:
            other = db.get_user_by_login(v)
            if other and other["id"] != uid:
                return jsonify({"success": False, "error": "该%s已被其他账号使用" % label}), 400
    db.admin_update_user(uid, phone, email, password)
    return jsonify({"success": True, "message": "已重置该用户的手机号、邮箱" + ("与密码" if password else "")})


@app.route("/api/admin/users/<int:uid>", methods=["DELETE"])
@auth.login_required
def api_admin_user_delete(uid):
    deny = _forbid_non_admin()
    if deny:
        return deny
    target = db.get_user_by_id(uid)
    if not target or target.get("role") != "user":
        return jsonify({"success": False, "error": "用户不存在"}), 404
    ok = db.delete_user(uid)
    if not ok:
        return jsonify({"success": False, "error": "删除失败"}), 400
    return jsonify({"success": True, "message": "已删除用户 %s" % target["username"]})


@app.route("/api/records/<int:rid>/notify", methods=["POST"])
@auth.login_required
def api_notify(rid):
    rec = db.get_record(rid)
    if not rec:
        return jsonify({"success": False, "error": "记录不存在"}), 404
    if not rec["violation"]:
        return jsonify({"success": False, "error": "该记录无违规行为，无需通知"}), 400
    vehicle = db.get_vehicle_by_plate(rec["plate_no"])
    owner = db.get_owner(vehicle["owner_id"]) if vehicle else None
    if not owner:
        return jsonify({"success": False, "error": "该车牌未登记车主，无法发送短信"}), 400

    created_at = now_str()
    ok, status, content = sms_service.send_violation_sms(
        owner["phone"], owner["name"], rec["plate_no"], rec["violation"], created_at)
    if ok:
        db.update_record_notified(rid, 1)
        db.add_notification({
            "record_id": rid, "plate_no": rec["plate_no"],
            "phone": owner["phone"], "owner_name": owner["name"],
            "content": content, "status": status, "created_at": created_at,
        })
    return jsonify({"success": ok, "message": status, "error": "" if ok else status})


@app.route("/api/owners", methods=["GET", "POST"])
@auth.login_required
def api_owners():
    if request.method == "GET":
        return jsonify(db.get_owners_with_vehicles())
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip()
    plate = (data.get("plate_no") or "").strip().upper().replace("·", "").replace("-", "").replace(" ", "")
    if not name or not phone or not plate:
        return jsonify({"success": False, "error": "姓名、手机号、车牌号不能为空"}), 400
    if db.get_vehicle_by_plate(plate):
        return jsonify({"success": False, "error": "该车牌号已登记"}), 400
    db.add_owner_with_vehicle(
        name, phone, (data.get("address") or "").strip(),
        plate, data.get("vehicle_type") or "小型汽车", (data.get("color") or "").strip())
    return jsonify({"success": True, "message": "登记成功"})


@app.route("/api/notifications")
@auth.login_required
def api_notifications():
    return jsonify(db.get_notifications(limit=200))


@app.errorhandler(413)
def too_large(_e):
    return jsonify({"success": False, "error": "文件过大，视频请控制在 200MB 以内"}), 413


if __name__ == "__main__":
    print("[server] http://127.0.0.1:5000  账号: %s / %s" % (db.DEFAULT_USERNAME, db.DEFAULT_PASSWORD))
    app.run(host="0.0.0.0", port=5000, threaded=True)
