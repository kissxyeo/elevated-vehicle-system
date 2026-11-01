# -*- coding: utf-8 -*-
"""数据库模块（SQLite）

表：users 登录用户 / owners 车主 / vehicles 车辆 / records 识别记录 / notifications 短信通知
首次启动自动建库，并写入演示账号与示例车主数据。
"""
import hashlib
import os
import secrets
import sqlite3
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(os.environ.get("EVS_DATA_DIR") or BASE_DIR, "data.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  username      TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  display_name  TEXT DEFAULT '',
  role          TEXT DEFAULT 'admin',
  phone         TEXT DEFAULT '',
  email         TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS owners(
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  name     TEXT NOT NULL,
  phone    TEXT NOT NULL,
  address  TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS vehicles(
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  plate_no     TEXT UNIQUE NOT NULL,
  owner_id     INTEGER NOT NULL,
  vehicle_type TEXT NOT NULL,
  color        TEXT DEFAULT '',
  FOREIGN KEY(owner_id) REFERENCES owners(id)
);
CREATE TABLE IF NOT EXISTS records(
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  image            TEXT DEFAULT '',
  plate_no         TEXT DEFAULT '',
  vehicle_type     TEXT DEFAULT '',
  confidence       REAL DEFAULT 0,
  plate_confidence REAL DEFAULT 0,
  allowed          INTEGER DEFAULT 1,
  violation        TEXT DEFAULT '',
  notified         INTEGER DEFAULT 0,
  source           TEXT DEFAULT 'image',
  session_id       INTEGER DEFAULT 0,
  created_at       TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS notifications(
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  record_id  INTEGER DEFAULT 0,
  plate_no   TEXT DEFAULT '',
  phone      TEXT DEFAULT '',
  owner_name TEXT DEFAULT '',
  content    TEXT DEFAULT '',
  status     TEXT DEFAULT '',
  created_at TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS app_state(
  key   TEXT PRIMARY KEY,
  value TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS user_plates(
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id  INTEGER NOT NULL,
  plate_no TEXT UNIQUE NOT NULL,
  created_at TEXT DEFAULT ''
);
"""

# 演示账号（首次建库写入，登录页也会显示）
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "gaojia123"
# 普通用户演示账号
USER_USERNAME = "user"
USER_PASSWORD = "user123"

# 示例车主与车辆（均为演示用虚拟数据）
_SEED_OWNERS = [
    ("张伟", "13800001234", "上海市浦东新区张江路100号", [("沪A12345", "小型汽车", "白色")]),
    ("李娜", "13900002345", "上海市徐汇区漕溪北路58号",   [("沪B23456", "小型汽车", "黑色")]),
    ("王强", "13700003456", "江苏省苏州市姑苏区人民路20号", [("苏C34567", "货车", "蓝色")]),
    ("赵敏", "13600004567", "上海市闵行区莘庄镇258号",     [("京D45678", "大型客车", "黄色")]),
    ("刘洋", "13500005678", "上海市杨浦区四平路1200号",    [("沪C56789", "小型汽车", "灰色")]),
    ("陈静", "13400006789", "浙江省杭州市西湖区文一路66号", [("苏E67890", "摩托车", "红色")]),
    ("杨帆", "13300007890", "上海市静安区南京西路1000号",  [("沪F78901", "小型汽车", "蓝色")]),
    ("周婷", "13200008901", "上海市黄浦区中山东一路18号",  [("浙G89012", "小型汽车", "银色")]),
]


# ---------- 密码 ----------

def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000)
    return "%s$%s" % (salt, digest.hex())


def verify_password(password, stored):
    try:
        salt, expected = stored.split("$", 1)
    except ValueError:
        return False
    return secrets.compare_digest(hash_password(password, salt).split("$", 1)[1], expected)


# ---------- 连接与初始化 ----------

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_column(cursor, table, column, ddl):
    cols = [r[1] for r in cursor.execute("PRAGMA table_info(%s)" % table).fetchall()]
    if column not in cols:
        cursor.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, column, ddl))


def init_db():
    """建表、补齐字段并写入演示数据（仅首次）"""
    conn = get_conn()
    conn.executescript(SCHEMA)
    c = conn.cursor()
    # 兼容旧版数据库
    _ensure_column(c, "records", "plate_confidence", "REAL DEFAULT 0")
    _ensure_column(c, "records", "source", "TEXT DEFAULT 'image'")
    _ensure_column(c, "records", "session_id", "INTEGER DEFAULT 0")
    _ensure_column(c, "users", "phone", "TEXT DEFAULT ''")
    _ensure_column(c, "users", "email", "TEXT DEFAULT ''")
    conn.commit()

    if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        c.execute("INSERT INTO users(username, password_hash, display_name, role) VALUES(?,?,?,?)",
                  (DEFAULT_USERNAME, hash_password(DEFAULT_PASSWORD), "系统管理员", "admin"))

    # 普通用户演示账号（缺失时自动补齐）
    if not c.execute("SELECT 1 FROM users WHERE username=?", (USER_USERNAME,)).fetchone():
        c.execute("INSERT INTO users(username, password_hash, display_name, role) VALUES(?,?,?,?)",
                  (USER_USERNAME, hash_password(USER_PASSWORD), "普通用户", "user"))

    if c.execute("SELECT COUNT(*) FROM owners").fetchone()[0] == 0:
        for name, phone, addr, vehicles in _SEED_OWNERS:
            c.execute("INSERT INTO owners(name, phone, address) VALUES(?,?,?)", (name, phone, addr))
            oid = c.lastrowid
            for plate, vtype, color in vehicles:
                c.execute("INSERT INTO vehicles(plate_no, owner_id, vehicle_type, color) VALUES(?,?,?,?)",
                          (plate, oid, vtype, color))
    conn.commit()
    conn.close()
    print("[db] database ready")


# ---------- 用户 ----------

def get_user(username):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_login(identifier):
    """按用户名、手机号或邮箱查找用户"""
    ident = (identifier or "").strip()
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM users WHERE username=? OR phone=? OR email=?",
        (ident, ident, ident.lower())).fetchone()
    conn.close()
    return dict(row) if row else None


def create_user(username, password, display_name="", role="user", phone="", email=""):
    """创建用户（注册用），username 为手机号或邮箱"""
    conn = get_conn()
    conn.execute(
        "INSERT INTO users(username, password_hash, display_name, role, phone, email) VALUES(?,?,?,?,?,?)",
        (username, hash_password(password), display_name, role, phone, email))
    conn.commit()
    conn.close()


def get_user_by_username(username):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_user_contact(user_id, phone="", email=""):
    conn = get_conn()
    conn.execute("UPDATE users SET phone=?, email=? WHERE id=?", (phone, email.lower(), user_id))
    conn.commit()
    conn.close()


def get_user_plates(user_id):
    conn = get_conn()
    rows = [r["plate_no"] for r in conn.execute(
        "SELECT plate_no FROM user_plates WHERE user_id=? ORDER BY id", (user_id,)).fetchall()]
    conn.close()
    return rows


def add_user_plate(user_id, plate_no):
    """绑定车牌，返回 (ok, message)"""
    conn = get_conn()
    owner = conn.execute("SELECT user_id FROM user_plates WHERE plate_no=?", (plate_no,)).fetchone()
    if owner:
        conn.close()
        return False, "该车牌已被其他账号绑定" if owner["user_id"] != user_id else "该车牌已绑定"
    conn.execute("INSERT INTO user_plates(user_id, plate_no, created_at) VALUES(?,?,?)",
                 (user_id, plate_no, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    return True, "绑定成功"


def remove_user_plate(user_id, plate_no):
    conn = get_conn()
    cur = conn.execute("DELETE FROM user_plates WHERE user_id=? AND plate_no=?", (user_id, plate_no))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def list_users():
    """全部普通用户及其绑定车牌"""
    conn = get_conn()
    rows = [dict(r) for r in conn.execute(
        "SELECT id, username, display_name, phone, email FROM users WHERE role='user' ORDER BY id").fetchall()]
    for r in rows:
        r["plates"] = [x["plate_no"] for x in conn.execute(
            "SELECT plate_no FROM user_plates WHERE user_id=? ORDER BY id", (r["id"],)).fetchall()]
    conn.close()
    return rows


def get_user_by_id(user_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def admin_update_user(user_id, phone="", email="", password=""):
    """管理员重置用户的手机号、邮箱，可选重置密码"""
    conn = get_conn()
    conn.execute("UPDATE users SET phone=?, email=? WHERE id=?", (phone, email.lower(), user_id))
    if password:
        conn.execute("UPDATE users SET password_hash=? WHERE id=?",
                     (hash_password(password), user_id))
    conn.commit()
    conn.close()


def delete_user(user_id):
    """删除用户及其绑定的车牌，返回是否删除成功"""
    conn = get_conn()
    conn.execute("DELETE FROM user_plates WHERE user_id=?", (user_id,))
    cur = conn.execute("DELETE FROM users WHERE id=? AND role='user'", (user_id,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def get_violations_by_plates(plates):
    """查询指定车牌列表的全部违规记录（按时间正序，便于计算罚款冷却）"""
    if not plates:
        return []
    marks = ",".join("?" * len(plates))
    conn = get_conn()
    rows = [dict(r) for r in conn.execute(
        "SELECT id, image, plate_no, vehicle_type, violation, source, created_at "
        "FROM records WHERE violation != '' AND plate_no IN (%s) ORDER BY id" % marks,
        plates).fetchall()]
    conn.close()
    return rows


# ---------- 查询 ----------

def get_all_vehicles():
    conn = get_conn()
    rows = [dict(r) for r in conn.execute(
        "SELECT v.*, o.name AS owner_name, o.phone AS owner_phone "
        "FROM vehicles v JOIN owners o ON v.owner_id=o.id").fetchall()]
    conn.close()
    return rows


def get_vehicle_by_plate(plate):
    if not plate:
        return None
    conn = get_conn()
    row = conn.execute("SELECT * FROM vehicles WHERE plate_no=?", (plate,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_owner(owner_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM owners WHERE id=?", (owner_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_owners_with_vehicles():
    conn = get_conn()
    rows = [dict(r) for r in conn.execute(
        """SELECT v.id AS vehicle_id, v.plate_no, v.vehicle_type, v.color,
                  o.id AS owner_id, o.name, o.phone, o.address
           FROM vehicles v JOIN owners o ON v.owner_id=o.id
           ORDER BY o.id, v.id""").fetchall()]
    conn.close()
    return rows


def new_session():
    """登录时开启新一轮识别记录会话，返回会话编号"""
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO app_state(key, value) VALUES('record_session', '0')")
    c.execute("UPDATE app_state SET value = CAST(value AS INTEGER) + 1 WHERE key='record_session'")
    c.execute("SELECT value FROM app_state WHERE key='record_session'")
    sid = int(c.fetchone()[0])
    conn.commit()
    conn.close()
    return sid


def current_session():
    conn = get_conn()
    row = conn.execute("SELECT value FROM app_state WHERE key='record_session'").fetchone()
    conn.close()
    return int(row[0]) if row else 0


def get_hour_stats(day, hour):
    """某天某个小时的识别统计"""
    like = "%s %02d%%" % (day, hour)
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(allowed),0), COALESCE(SUM(CASE WHEN violation != '' THEN 1 ELSE 0 END),0) "
        "FROM records WHERE created_at LIKE ?", (like,)).fetchone()
    total, allowed, violations = int(row[0]), int(row[1]), int(row[2])
    types = [dict(r) for r in conn.execute(
        "SELECT vehicle_type AS type, COUNT(*) AS count, COALESCE(SUM(allowed),0) AS allowed_count "
        "FROM records WHERE created_at LIKE ? GROUP BY vehicle_type ORDER BY count DESC",
        (like,)).fetchall()]
    conn.close()
    return {"date": day, "hour": hour, "total": total, "allowed": allowed,
            "violations": violations, "types": types}


def delete_record(rid):
    conn = get_conn()
    conn.execute("DELETE FROM records WHERE id=?", (rid,))
    conn.commit()
    conn.close()


def get_records(limit=100, only_violation=False, source=None, session_id=None, date=None, order="desc"):
    conn = get_conn()
    sql = ("""SELECT r.*, o.name AS owner_name, o.phone AS owner_phone
              FROM records r
              LEFT JOIN vehicles v ON r.plate_no = v.plate_no
              LEFT JOIN owners o ON v.owner_id = o.id""")
    where = []
    args = []
    if only_violation:
        where.append("r.violation != ''")
    if source:
        where.append("r.source = ?")
        args.append(source)
    if date:
        where.append("r.created_at LIKE ?")
        args.append(date + "%")
    if session_id is not None:
        where.append("r.session_id = ?")
        args.append(session_id)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY r.id %s LIMIT ?" % ("ASC" if order == "asc" else "DESC")
    args.append(limit)
    rows = [dict(r) for r in conn.execute(sql, args).fetchall()]
    conn.close()
    return rows


def get_record(rid):
    conn = get_conn()
    row = conn.execute(
        """SELECT r.*, o.name AS owner_name, o.phone AS owner_phone
           FROM records r
           LEFT JOIN vehicles v ON r.plate_no = v.plate_no
           LEFT JOIN owners o ON v.owner_id = o.id
           WHERE r.id=?""", (rid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_notifications(limit=100):
    conn = get_conn()
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM notifications ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]
    conn.close()
    return rows


def get_stats():
    conn = get_conn()
    c = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")

    def one(sql, args=()):
        c.execute(sql, args)
        return c.fetchone()[0]

    stats = {
        "total_records": one("SELECT COUNT(*) FROM records"),
        "total_violations": one("SELECT COUNT(*) FROM records WHERE violation != ''"),
        "today_detections": one("SELECT COUNT(*) FROM records WHERE created_at LIKE ?", (today + "%",)),
        "today_violations": one("SELECT COUNT(*) FROM records WHERE violation != '' AND created_at LIKE ?", (today + "%",)),
        "owners_count": one("SELECT COUNT(*) FROM owners"),
        "vehicles_count": one("SELECT COUNT(*) FROM vehicles"),
        "notifications_count": one("SELECT COUNT(*) FROM notifications"),
        "type_distribution": [dict(r) for r in c.execute(
            "SELECT vehicle_type AS type, COUNT(*) AS count FROM records GROUP BY vehicle_type").fetchall()],
        "recent": [dict(r) for r in c.execute(
            """SELECT id, plate_no, vehicle_type, violation, allowed, source, created_at
               FROM records ORDER BY id DESC LIMIT 8""").fetchall()],
    }
    conn.close()
    return stats


def get_day_stats(day):
    """按天统计：各车型出现次数、允许/禁行数、24 小时分布与违规高峰时段"""
    conn = get_conn()
    c = conn.cursor()
    like = day + "%"

    def one(sql, args=()):
        c.execute(sql, args)
        return c.fetchone()[0]

    total = one("SELECT COUNT(*) FROM records WHERE created_at LIKE ?", (like,))
    allowed = one("SELECT COUNT(*) FROM records WHERE allowed=1 AND created_at LIKE ?", (like,))
    violations = one("SELECT COUNT(*) FROM records WHERE violation != '' AND created_at LIKE ?", (like,))

    types = [dict(r) for r in c.execute(
        """SELECT vehicle_type AS type, COUNT(*) AS count,
                  SUM(CASE WHEN allowed=1 THEN 1 ELSE 0 END) AS allowed_count,
                  SUM(CASE WHEN violation != '' THEN 1 ELSE 0 END) AS violation_count
           FROM records WHERE created_at LIKE ? AND vehicle_type != ''
           GROUP BY vehicle_type ORDER BY count DESC""", (like,)).fetchall()]

    hourly = [0] * 24
    for r in c.execute(
            """SELECT substr(created_at, 12, 2) AS hour, COUNT(*) AS count
               FROM records WHERE created_at LIKE ? GROUP BY hour""", (like,)).fetchall():
        try:
            h = int(r["hour"])
        except (TypeError, ValueError):
            continue
        if 0 <= h < 24:
            hourly[h] = r["count"]

    violation_hourly = [0] * 24
    for r in c.execute(
            """SELECT substr(created_at, 12, 2) AS hour, COUNT(*) AS count
               FROM records WHERE created_at LIKE ? AND violation != ''
               GROUP BY hour""", (like,)).fetchall():
        try:
            h = int(r["hour"])
        except (TypeError, ValueError):
            continue
        if 0 <= h < 24:
            violation_hourly[h] = r["count"]

    # 违规高峰时段：按违规记录数从多到少取前 3 个有违规的小时
    ranked = sorted(({"hour": h, "count": n} for h, n in enumerate(violation_hourly)),
                    key=lambda x: (-x["count"], x["hour"]))
    peak_hours = [p for p in ranked if p["count"] > 0][:3]

    conn.close()
    return {
        "date": day,
        "total": total,
        "allowed": allowed,
        "violations": violations,
        "types": types,
        "hourly": hourly,
        "peak_hours": peak_hours,
    }


# ---------- 写入 ----------

def add_owner_with_vehicle(name, phone, address, plate, vehicle_type, color):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO owners(name, phone, address) VALUES(?,?,?)", (name, phone, address))
    oid = c.lastrowid
    c.execute("INSERT INTO vehicles(plate_no, owner_id, vehicle_type, color) VALUES(?,?,?,?)",
              (plate, oid, vehicle_type, color))
    conn.commit()
    conn.close()


def add_record(rec):
    sid = rec.get("session_id")
    if sid is None:
        sid = current_session()
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """INSERT INTO records(image, plate_no, vehicle_type, confidence, plate_confidence,
           allowed, violation, notified, source, session_id, created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (rec.get("image", ""), rec.get("plate_no", ""), rec.get("vehicle_type", ""),
         rec.get("confidence", 0), rec.get("plate_confidence", 0),
         rec.get("allowed", 1), rec.get("violation", ""), rec.get("notified", 0),
         rec.get("source", "image"), sid, rec.get("created_at", "")))
    rid = c.lastrowid
    conn.commit()
    conn.close()
    return rid


def update_record_image(rid, image):
    conn = get_conn()
    conn.execute("UPDATE records SET image=? WHERE id=?", (image, rid))
    conn.commit()
    conn.close()


def update_record_notified(rid, notified):
    conn = get_conn()
    conn.execute("UPDATE records SET notified=? WHERE id=?", (notified, rid))
    conn.commit()
    conn.close()


def add_notification(n):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """INSERT INTO notifications(record_id, plate_no, phone, owner_name,
           content, status, created_at) VALUES(?,?,?,?,?,?,?)""",
        (n["record_id"], n["plate_no"], n["phone"], n["owner_name"],
         n["content"], n["status"], n["created_at"]))
    conn.commit()
    conn.close()
