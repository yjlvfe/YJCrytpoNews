#!/usr/bin/env python3
"""🌐 YJCryptoNews - Web Dashboard (API Only Mode)"""
import sys
import os
import json
import threading
import time
import uuid
import sqlite3
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, Future

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, request, jsonify, send_from_directory
from yjcryptonews import config, database
from yjcryptonews.log import setup_logging, get_logger
import subprocess

app = Flask(__name__, static_folder="dashboard-ui", static_url_path="")
logger = get_logger("dashboard")

# ─── Async Job Manager ──────────────────────────────────
# Phase 6: replaces blocking subprocess.run with a thread pool so the
# dashboard HTTP request returns immediately and the bot command runs in
# the background. Each job gets a unique id, stores its output in memory,
# and a /api/job/<id> endpoint lets the UI poll for completion.

_JOB_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="bot-cmd")
_JOBS: dict = {}  # job_id -> {"future", "status", "output", "error", "submitted_at"}
_JOBS_LOCK = threading.Lock()
_JOB_TTL_SECONDS = 600  # purge completed jobs after 10 min
_JOBS_MAX = 50  # hard cap so memory doesn't grow unbounded


def _purge_old_jobs() -> None:
    """Remove completed jobs older than _JOB_TTL_SECONDS, keep at most _JOBS_MAX."""
    now = time.monotonic()
    with _JOBS_LOCK:
        # Drop old finished ones first
        stale = [
            jid for jid, j in _JOBS.items()
            if j["status"] in ("success", "failed", "timeout")
            and (now - j["submitted_at"]) > _JOB_TTL_SECONDS
        ]
        for jid in stale:
            _JOBS.pop(jid, None)
        # If still over cap, drop oldest finished
        if len(_JOBS) > _JOBS_MAX:
            finished = sorted(
                ((j["submitted_at"], jid) for jid, j in _JOBS.items()
                 if j["status"] in ("success", "failed", "timeout"))
            )
            for _, jid in finished[:len(_JOBS) - _JOBS_MAX]:
                _JOBS.pop(jid, None)


def _run_bot_command_async(command: str, timeout: int = 120) -> str:
    """Submit a bot command to the thread pool. Returns job_id immediately.

    The actual subprocess runs in the background; poll /api/job/<id> for
    the result. This prevents the dashboard HTTP worker from being blocked
    for up to `timeout` seconds on long-running bot cycles.
    """
    job_id = uuid.uuid4().hex[:12]
    bot_path = os.path.join(app.root_path, "bot.py")

    def _runner() -> None:
        entry = {
            "future": None,  # set below to avoid circular ref
            "status": "running",
            "output": "",
            "error": "",
            "command": command,
            "submitted_at": time.monotonic(),
        }
        with _JOBS_LOCK:
            _JOBS[job_id] = entry
        try:
            result = subprocess.run(
                [sys.executable, bot_path, command],
                capture_output=True, text=True, timeout=timeout,
            )
            entry["output"] = (result.stdout or "")[-2000:]
            entry["error"] = (result.stderr or "")[-2000:]
            entry["status"] = "success" if result.returncode == 0 else "failed"
        except subprocess.TimeoutExpired:
            entry["status"] = "timeout"
            entry["error"] = f"Bot command '{command}' exceeded {timeout}s"
            logger.error("Job %s timed out after %ds", job_id, timeout)
        except Exception as e:
            entry["status"] = "failed"
            entry["error"] = str(e)
            logger.error("Job %s failed: %s", job_id, e)
        finally:
            logger.info("Job %s (%s) finished with status=%s",
                        job_id, command, entry["status"])

    future: Future = _JOB_EXECUTOR.submit(_runner)
    with _JOBS_LOCK:
        if job_id in _JOBS:
            _JOBS[job_id]["future"] = future
    _purge_old_jobs()
    return job_id

# ─── API Routes ────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")

@app.route("/api/dashboard")
def api_dashboard():
    """بيانات اللوحة الرئيسية"""
    try:
        cfg = config.load()
        channels = database.get_channels()
        recent = database.get_recent_publishes(30)
        stats = database.get_stats() if hasattr(database, 'get_stats') else {}
        return jsonify({
            "ok": True,
            "config": {
                "interval": cfg.get("scheduler", {}).get("interval_minutes", 60),
                "max_posts": cfg.get("publisher", {}).get("max_posts_per_cycle", 5),
                "delay": cfg.get("publisher", {}).get("delay_between_posts", 720),
                "window_hours": cfg.get("scheduler", {}).get("news_window_hours", 12),
            },
            "channels": [{
                "chat_id": ch["chat_id"],
                "title": ch.get("title") or ch.get("username") or ch["chat_id"],
                "is_active": ch["is_active"],
            } for ch in channels],
            "recent": [{
                "title": r.get("item_title", "")[:80],
                "time": str(r.get("created_at", ""))[:19],
                "status": r.get("status", "unknown"),
                "channel": r.get("channel_name", ""),
            } for r in recent[:20]],
            "stats": {
                "total_posts": len(recent),
                "total_channels": len(channels),
                "active_channels": sum(1 for ch in channels if ch["is_active"]),
                "last_publish": str(recent[0]["created_at"])[:19] if recent else "—",
                "bot_status": "active" if True else "inactive",
            },
            "now": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
    except Exception as e:
        logger.error("Dashboard API error: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/channels/toggle", methods=["POST"])
def api_toggle_channel():
    data = request.json or {}
    chat_id = data.get("chat_id", "").strip()
    if not chat_id:
        return jsonify({"ok": False, "error": "chat_id required"}), 400
    try:
        database.toggle_channel(chat_id)
        ch = database.get_channel(chat_id)
        return jsonify({"ok": True, "active": ch["is_active"] if ch else False})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/channels/add", methods=["POST"])
def api_add_channel():
    data = request.json or {}
    chat_id = data.get("chat_id", "").strip()
    title = data.get("title", "").strip()
    if not chat_id:
        return jsonify({"ok": False, "error": "chat_id required"}), 400
    try:
        database.add_channel(chat_id, title=title)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/channels/remove", methods=["POST"])
def api_remove_channel():
    data = request.json or {}
    chat_id = data.get("chat_id", "").strip()
    if not chat_id:
        return jsonify({"ok": False, "error": "chat_id required"}), 400
    try:
        database.remove_channel(chat_id)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/config/update", methods=["POST"])
def api_update_config():
    data = request.json or {}
    try:
        cfg = config.load()
        updates = 0
        if "interval" in data:
            val = int(data["interval"])
            if 1 <= val <= 1440:
                cfg.setdefault("scheduler", {})["interval_minutes"] = val; updates += 1
        if "max_posts" in data:
            val = int(data["max_posts"])
            if 1 <= val <= 20:
                cfg.setdefault("publisher", {})["max_posts_per_cycle"] = val; updates += 1
        if "window_hours" in data:
            val = int(data["window_hours"])
            if 1 <= val <= 168:
                cfg.setdefault("scheduler", {})["news_window_hours"] = val; updates += 1
        if "delay" in data:
            val = int(data["delay"])
            if 0 <= val <= 300:
                cfg.setdefault("publisher", {})["delay_between_posts"] = val; updates += 1
        if updates:
            config.save(cfg)
        return jsonify({"ok": True, "updates": updates})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/run-cycle", methods=["POST"])
def api_run_cycle():
    """Submit a cycle to the thread pool. Returns job_id immediately.

    The bot command (which can take 30-120s) runs in the background.
    Poll /api/job/<job_id> for status and output. This prevents the
    dashboard HTTP worker from being blocked while a full cycle runs.
    """
    job_id = _run_bot_command_async("run", timeout=180)
    return jsonify({
        "ok": True,
        "started": True,
        "job_id": job_id,
        "poll_url": f"/api/job/{job_id}",
    })


@app.route("/api/job/<job_id>")
def api_job_status(job_id):
    """Return current status of a background job."""
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
    if not job:
        return jsonify({"ok": False, "error": "job not found or expired"}), 404
    return jsonify({
        "ok": True,
        "job_id": job_id,
        "status": job["status"],  # running | success | failed | timeout
        "command": job.get("command", ""),
        "output": job.get("output", ""),
        "error": job.get("error", ""),
        "elapsed_sec": round(time.monotonic() - job["submitted_at"], 1),
    })

@app.route("/api/status")
def api_status():
    try:
        db_ok = bool(database.get_channels())
        cfg = config.load()
        return jsonify({"ok": True, "status": "running", "database": "connected" if db_ok else "empty"})
    except sqlite3.Error as e:
        # Phase 6: DB errors return 503 (transient — caller may retry) instead
        # of 500 (logic bug). Lets the UI show "reconnecting..." gracefully.
        logger.warning("DB unavailable for /api/status: %s", e)
        return jsonify({"ok": False, "error": "database unavailable", "detail": str(e)}), 503
    except Exception as e:
        logger.error("Unexpected /api/status error: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500

# ─── Main ────────────────────────────────────────────────

if __name__ == "__main__":
    setup_logging()
    database.init_db()
    port = int(os.environ.get("DASHBOARD_PORT", 5050))
    host = os.environ.get("DASHBOARD_HOST", "127.0.0.1")
    logger.info("🌐 Dashboard API starting at http://%s:%d", host, port)
    try:
        from waitress import serve
        serve(app, host=host, port=port, threads=4)
    except ImportError:
        # threaded=True so concurrent requests don't block each other
        # (e.g. /api/run-cycle submit + /api/job/<id> poll from the same browser)
        app.run(host=host, port=port, debug=False, threaded=True)
