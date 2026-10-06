"""Canteen DBMS - Flask + SQLite. Same 5 tables and seed data as schema.sql."""
import os, sqlite3
from functools import wraps
from flask import Flask, g, jsonify, request, session, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "canteen.db")
app = Flask(__name__, static_folder="static")
app.secret_key = os.environ.get("SECRET_KEY", "dev-canteen-key")

SCHEMA = """
CREATE TABLE users (user_id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
  password TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('admin','moderator','customer')),
  created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE admin (admin_id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER UNIQUE NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  department TEXT DEFAULT 'General', access_level TEXT DEFAULT 'full');
CREATE TABLE moderators (moderator_id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER UNIQUE NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  assigned_section TEXT DEFAULT 'Main Counter',
  approved_by INTEGER REFERENCES admin(admin_id) ON DELETE SET NULL);
CREATE TABLE customers (customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER UNIQUE NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  phone TEXT, wallet_balance REAL DEFAULT 0 CHECK (wallet_balance >= 0));
CREATE TABLE menu_items (item_id INTEGER PRIMARY KEY AUTOINCREMENT, item_name TEXT NOT NULL,
  description TEXT, price REAL NOT NULL CHECK (price >= 0), category TEXT DEFAULT 'General',
  is_available INTEGER DEFAULT 1,
  added_by INTEGER REFERENCES moderators(moderator_id) ON DELETE SET NULL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP);
"""

USERS = [("rahul_admin", "admin123", "rahul.admin@canteen.com", "admin"),
         ("priya_mod", "mod123", "priya.mod@canteen.com", "moderator"),
         ("aman_mod", "mod456", "aman.mod@canteen.com", "moderator"),
         ("sara_cust", "cust123", "sara@student.edu", "customer"),
         ("vikram_cust", "cust456", "vikram@student.edu", "customer"),
         ("neha_cust", "cust789", "neha@student.edu", "customer")]
MENU = [("Veg Sandwich", "Grilled sandwich with mixed vegetables", 40, "Snacks", 1, 1),
        ("Samosa", "Crispy fried pastry with spiced potato filling", 15, "Snacks", 1, 1),
        ("Masala Chai", "Spiced Indian tea", 12, "Beverages", 2, 1),
        ("Cold Coffee", "Chilled coffee with milk and ice", 35, "Beverages", 2, 1),
        ("Veg Biryani", "Aromatic rice with mixed vegetables", 70, "Meals", 1, 0)]


def init_db():
    c = sqlite3.connect(DB)
    c.executescript(SCHEMA)
    for u, p, e, r in USERS:
        c.execute("INSERT INTO users(username,password,email,role) VALUES(?,?,?,?)",
                  (u, generate_password_hash(p), e, r))
    c.execute("INSERT INTO admin(user_id,department) VALUES(1,'Canteen Operations')")
    c.execute("INSERT INTO moderators(user_id,assigned_section,approved_by) VALUES(2,'Snacks Counter',1)")
    c.execute("INSERT INTO moderators(user_id,assigned_section,approved_by) VALUES(3,'Beverages Counter',1)")
    for uid, ph, bal in [(4, "9876500001", 250), (5, "9876500002", 100), (6, "9876500003", 500)]:
        c.execute("INSERT INTO customers(user_id,phone,wallet_balance) VALUES(?,?,?)", (uid, ph, bal))
    c.executemany("INSERT INTO menu_items(item_name,description,price,category,added_by,is_available) VALUES(?,?,?,?,?,?)", MENU)
    c.commit(); c.close()


if not os.path.exists(DB):
    init_db()


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB, isolation_level=None)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


@app.teardown_appcontext
def close(_):
    d = g.pop("db", None)
    if d: d.close()


def rows(sql, *a): return [dict(r) for r in db().execute(sql, a).fetchall()]
def one(sql, *a):
    r = db().execute(sql, a).fetchone()
    return dict(r) if r else None


def need(*roles):
    def deco(f):
        @wraps(f)
        def w(*a, **k):
            if session.get("role") not in roles:
                return jsonify(error="Not allowed"), 403
            return f(*a, **k)
        return w
    return deco


def me():
    uid, role = session["user_id"], session["role"]
    tbl = {"admin": "admin", "moderator": "moderators", "customer": "customers"}[role]
    return {"user_id": uid, "username": session["username"], "role": role,
            "profile": one(f"SELECT * FROM {tbl} WHERE user_id=?", uid)}


@app.get("/")
def index(): return send_from_directory("static", "index.html")


@app.post("/api/login")
def login():
    d = request.get_json(force=True)
    u = one("SELECT * FROM users WHERE username=?", (d.get("username") or "").strip())
    if not u: return jsonify(error="User not found"), 401
    if not check_password_hash(u["password"], d.get("password") or ""):
        return jsonify(error="Incorrect password"), 401
    session.update(user_id=u["user_id"], username=u["username"], role=u["role"])
    return jsonify(me())


@app.post("/api/logout")
def logout(): session.clear(); return jsonify(ok=True)


@app.get("/api/me")
def whoami():
    return jsonify(me()) if "user_id" in session else (jsonify(error="No session"), 401)


@app.get("/api/menu")
def menu():
    if request.args.get("all") and session.get("role") in ("admin", "moderator"):
        return jsonify(rows("""SELECT mi.*, u.username AS added_by_username FROM menu_items mi
            LEFT JOIN moderators m ON mi.added_by=m.moderator_id LEFT JOIN users u ON m.user_id=u.user_id
            ORDER BY mi.item_id"""))
    return jsonify(rows("SELECT item_id,item_name,description,price,category FROM menu_items "
                        "WHERE is_available=1 ORDER BY category,item_name"))


@app.post("/api/menu")
@need("moderator")
def add_item():
    d = request.get_json(force=True)
    cur = db().execute("INSERT INTO menu_items(item_name,description,price,category,added_by) VALUES(?,?,?,?,?)",
                       (d["item_name"], d.get("description", ""), float(d["price"]),
                        d.get("category", "General"), me()["profile"]["moderator_id"]))
    return jsonify(one("SELECT * FROM menu_items WHERE item_id=?", cur.lastrowid)), 201


@app.put("/api/menu/<int:i>")
@need("moderator", "admin")
def edit_item(i):
    d = request.get_json(force=True)
    av = None if d.get("is_available") is None else int(bool(d["is_available"]))
    db().execute("UPDATE menu_items SET price=COALESCE(?,price), is_available=COALESCE(?,is_available) WHERE item_id=?",
                 (d.get("price"), av, i))
    return jsonify(one("SELECT * FROM menu_items WHERE item_id=?", i))


@app.delete("/api/menu/<int:i>")
@need("admin")
def del_item(i):
    db().execute("DELETE FROM menu_items WHERE item_id=?", (i,)); return jsonify(ok=True)


@app.get("/api/users")
@need("admin")
def users():
    return jsonify(rows("""SELECT u.user_id,u.username,u.email,u.role,a.department,m.assigned_section,c.wallet_balance
        FROM users u LEFT JOIN admin a ON u.user_id=a.user_id LEFT JOIN moderators m ON u.user_id=m.user_id
        LEFT JOIN customers c ON u.user_id=c.user_id ORDER BY u.role,u.user_id"""))


@app.get("/api/summary")
@need("admin")
def summary():
    return jsonify(one("""SELECT (SELECT COUNT(*) FROM admin) total_admins,
        (SELECT COUNT(*) FROM moderators) total_moderators, (SELECT COUNT(*) FROM customers) total_customers,
        (SELECT COUNT(*) FROM menu_items) total_menu_items,
        (SELECT COUNT(*) FROM menu_items WHERE is_available=1) available_items"""))


@app.post("/api/order")
@need("customer")
def order():
    """Transaction: validate every line, deduct once, ROLLBACK on any failure."""
    lines = (request.get_json(force=True).get("items") or [])
    c = db(); cid = me()["profile"]["customer_id"]
    c.execute("BEGIN IMMEDIATE")
    try:
        total = 0
        for l in lines:
            it = one("SELECT item_name,price,is_available FROM menu_items WHERE item_id=?", l["item_id"])
            if not it: raise ValueError("Item not found")
            if not it["is_available"]: raise ValueError(f"{it['item_name']} is currently unavailable")
            total += it["price"] * max(1, int(l["qty"]))
        if not lines: raise ValueError("Your ticket is empty")
        bal = one("SELECT wallet_balance FROM customers WHERE customer_id=?", cid)["wallet_balance"]
        if bal < total: raise ValueError("Insufficient wallet balance")
        c.execute("UPDATE customers SET wallet_balance=wallet_balance-? WHERE customer_id=?", (total, cid))
        c.execute("COMMIT")
        return jsonify(success=True, total=total, new_balance=bal - total)
    except Exception as e:
        c.execute("ROLLBACK"); return jsonify(error=str(e)), 400


if __name__ == "__main__":
    app.run(debug=True, port=5000)
