#!/usr/bin/env python3
"""PetDeals Tracker -- lightweight visit/click counter (Flask + SQLite)."""

import sqlite3
import os
from datetime import datetime, timezone
from flask import Flask, request, jsonify

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "tracker.db")

app = Flask(__name__)


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            page TEXT NOT NULL,
            action TEXT NOT NULL,
            product TEXT,
            ip TEXT,
            ua TEXT
        )
    """)
    conn.commit()
    return conn


# Init DB on import
_get_db().close()


@app.after_request
def _cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    return resp


@app.route("/api/track", methods=["POST", "OPTIONS"])
def track():
    if request.method == "OPTIONS":
        return "", 204
    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        data = {}
    page = (data.get("page") or "unknown")[:100]
    action = (data.get("action") or "view")[:20]
    product = (data.get("product") or "")[:200] or None
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "")
    ua = (request.headers.get("User-Agent") or "")[:300]
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    conn = _get_db()
    conn.execute(
        "INSERT INTO events (ts, page, action, product, ip, ua) VALUES (?,?,?,?,?,?)",
        (ts, page, action, product, ip, ua),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True}), 201


@app.route("/api/stats", methods=["GET"])
def stats():
    conn = _get_db()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM events WHERE action='view'")
    total_views = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM events WHERE action='click'")
    total_clicks = cur.fetchone()[0]

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cur.execute("SELECT COUNT(*) FROM events WHERE action='view' AND ts LIKE ?", (f"{today}%",))
    today_views = cur.fetchone()[0]

    cur.execute("""
        SELECT page, COUNT(*) FROM events WHERE action='view'
        GROUP BY page ORDER BY COUNT(*) DESC
    """)
    pages = [{"page": r[0], "views": r[1]} for r in cur.fetchall()]

    cur.execute("""
        SELECT product, COUNT(*) FROM events WHERE action='click' AND product IS NOT NULL
        GROUP BY product ORDER BY COUNT(*) DESC LIMIT 10
    """)
    top_products = [{"product": r[0], "clicks": r[1]} for r in cur.fetchall()]

    cur.execute("""
        SELECT DATE(ts), COUNT(*) FROM events WHERE action='view'
        GROUP BY DATE(ts) ORDER BY DATE(ts) DESC LIMIT 7
    """)
    daily = [{"date": r[0], "views": r[1]} for r in cur.fetchall()]

    conn.close()
    return jsonify({
        "total_views": total_views,
        "total_clicks": total_clicks,
        "today_views": today_views,
        "pages": pages,
        "top_products": top_products,
        "daily": daily,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    try:
        from waitress import serve
        print(f"[Tracker] Production server on port {port}")
        serve(app, host="0.0.0.0", port=port, threads=4)
    except ImportError:
        print("[Tracker] Waitress not installed, using Flask dev server")
        app.run(host="0.0.0.0", port=port)
