"""Database helpers: connection handling, schema creation and sample data."""
import os
import sqlite3

import click
from flask import current_app, g
from werkzeug.security import generate_password_hash

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db():
    """Create all tables (safe to run repeatedly)."""
    conn = get_db()
    with open(SCHEMA_PATH, encoding="utf-8") as fh:
        conn.executescript(fh.read())
    conn.commit()


def _add_form(conn, admin_id, title, description, questions, active=1):
    cur = conn.execute(
        "INSERT INTO forms (title, description, is_active, created_by, created_at) "
        "VALUES (?, ?, ?, ?, '2026-10-01 10:00:00')",
        (title, description, active, admin_id),
    )
    form_id = cur.lastrowid
    qids = []
    for pos, (text, qtype, options, required) in enumerate(questions, start=1):
        import json

        qcur = conn.execute(
            "INSERT INTO questions (form_id, text, qtype, options, is_required, position) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (form_id, text, qtype, json.dumps(options), required, pos),
        )
        qids.append(qcur.lastrowid)
    return form_id, qids


def _add_response(conn, form_id, user_id, qids, values, when):
    cur = conn.execute(
        "INSERT INTO responses (form_id, user_id, submitted_at) VALUES (?, ?, ?)",
        (form_id, user_id, when),
    )
    for qid, value in zip(qids, values):
        if value != "":
            conn.execute(
                "INSERT INTO answers (response_id, question_id, value) VALUES (?, ?, ?)",
                (cur.lastrowid, qid, value),
            )


def seed():
    """Insert sample data. Does nothing if users already exist."""
    conn = get_db()
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
        return False

    admin_hash = generate_password_hash("admin123")
    user_hash = generate_password_hash("user123")

    admin_id = conn.execute(
        "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'admin')",
        ("Admin", "admin@example.com", admin_hash),
    ).lastrowid

    students = [
        ("Aarav Mehta", "aarav@example.com"),
        ("Diya Nair", "diya@example.com"),
        ("Kabir Rao", "kabir@example.com"),
        ("Meera Iyer", "meera@example.com"),
        ("Rohan Desai", "rohan@example.com"),
    ]
    user_ids = [
        conn.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'user')",
            (name, email, user_hash),
        ).lastrowid
        for name, email in students
    ]

    pace = ["Too slow", "Just right", "Too fast"]
    resources = ["Lectures", "Labs", "Online material", "Peer discussion"]
    course_id, course_q = _add_form(
        conn, admin_id,
        "Course Feedback - Semester 5",
        "Tell us how this semester's courses went. Your answers help us improve teaching and materials.",
        [
            ("How would you rate the overall quality of teaching?", "rating", [], 1),
            ("How clear were the course materials and assignments?", "rating", [], 1),
            ("How was the pace of the course?", "choice", pace, 1),
            ("Which resource helped you the most?", "choice", resources, 0),
            ("What is one thing we should improve?", "text", [], 0),
        ],
    )
    sample = [
        ("5", "4", "Just right", "Labs", "More practical sessions, please."),
        ("4", "4", "Just right", "Lectures", ""),
        ("3", "2", "Too fast", "Peer discussion", "Slow down during the database unit."),
        ("5", "5", "Just right", "Online material", "Share slides before class."),
    ]
    for i, values in enumerate(sample):
        _add_response(conn, course_id, user_ids[i], course_q, values, f"2026-10-0{i + 2} 09:{15 + i}:00")

    _add_form(
        conn, admin_id,
        "Campus Facilities Survey",
        "Library, canteen and lab facilities: what is working and what is not?",
        [
            ("How satisfied are you with the library?", "rating", [], 1),
            ("How often do you use the canteen?", "choice", ["Daily", "Weekly", "Rarely", "Never"], 1),
            ("Any suggestions for the campus?", "text", [], 0),
        ],
    )
    _add_form(
        conn, admin_id,
        "Orientation Week Feedback (closed)",
        "This form is closed and no longer accepts responses.",
        [("How useful was the orientation week?", "rating", [], 1)],
        active=0,
    )
    conn.commit()
    return True


def init_app(app):
    app.teardown_appcontext(close_db)

    @app.cli.command("init-db")
    def init_db_command():
        """Create the database tables."""
        init_db()
        click.echo("Database initialised.")

    @app.cli.command("seed")
    def seed_command():
        """Load sample data (admin@example.com / admin123, students / user123)."""
        click.echo("Sample data loaded." if seed() else "Database already has users; nothing changed.")
