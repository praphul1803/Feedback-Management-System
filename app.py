"""Feedback Management System - Flask application (routes and business rules)."""
import csv
import hmac
import io
import json
import os
import re
import secrets
import sqlite3
from functools import wraps

from flask import (Flask, Response, abort, flash, g, redirect, render_template,
                   request, session, url_for)
from markupsafe import Markup
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

import db
from queries import build_summary, load_questions, load_responses

QTYPES = {"text": "Short text", "rating": "Rating (1-5)", "choice": "Multiple choice"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_TITLE, MAX_DESC, MAX_QUESTION, MAX_OPTION, MAX_ANSWER = 120, 1000, 300, 100, 2000


def create_app(config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-me"),
        DATABASE=os.path.join(app.instance_path, "feedback.db"),
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if config:
        app.config.update(config)
    os.makedirs(os.path.dirname(os.path.abspath(app.config["DATABASE"])), exist_ok=True)

    db.init_app(app)
    with app.app_context():
        db.init_db()

    # ------------------------------------------------------------------ #
    # Request hooks, helpers, decorators
    # ------------------------------------------------------------------ #
    @app.before_request
    def load_user_and_check_csrf():
        if request.endpoint == "static":
            return
        if "csrf" not in session:
            session["csrf"] = secrets.token_hex(16)
        g.user = None
        uid = session.get("user_id")
        if uid is not None:
            row = db.get_db().execute(
                "SELECT id, name, email, role FROM users WHERE id = ?", (uid,)
            ).fetchone()
            if row is None:
                session.pop("user_id", None)
            else:
                g.user = dict(row)
        if request.method == "POST":
            sent = request.form.get("csrf", "").encode()
            if not hmac.compare_digest(sent, session["csrf"].encode()):
                abort(400, "Invalid or missing security token. Reload the page and try again.")

    @app.context_processor
    def template_globals():
        return {
            "csrf_input": lambda: Markup(
                '<input type="hidden" name="csrf" value="%s">' % session.get("csrf", "")
            ),
            "QTYPES": QTYPES,
        }

    def login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.user is None:
                flash("Please log in to continue.", "error")
                return redirect(url_for("login"))
            return view(*args, **kwargs)
        return wrapped

    def admin_required(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if g.user["role"] != "admin":
                abort(403)
            return view(*args, **kwargs)
        return wrapped

    def get_form_or_404(form_id):
        row = db.get_db().execute("SELECT * FROM forms WHERE id = ?", (form_id,)).fetchone()
        if row is None:
            abort(404)
        return dict(row)

    def get_question_or_404(question_id):
        row = db.get_db().execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
        if row is None:
            abort(404)
        q = dict(row)
        q["options"] = json.loads(q["options"] or "[]")
        return q

    def parse_form_fields(data):
        title = data.get("title", "").strip()
        description = data.get("description", "").strip()
        errors = []
        if not title:
            errors.append("Form title is required.")
        elif len(title) > MAX_TITLE:
            errors.append(f"Title must be at most {MAX_TITLE} characters.")
        if len(description) > MAX_DESC:
            errors.append(f"Description must be at most {MAX_DESC} characters.")
        return title, description, errors

    def parse_question_fields(data):
        text = data.get("text", "").strip()
        qtype = data.get("qtype", "")
        required = 1 if data.get("is_required") else 0
        raw_options = data.get("options", "")
        errors = []
        if not text:
            errors.append("Question text is required.")
        elif len(text) > MAX_QUESTION:
            errors.append(f"Question text must be at most {MAX_QUESTION} characters.")
        if qtype not in QTYPES:
            errors.append("Choose a valid question type.")
        options = []
        if qtype == "choice":
            for line in raw_options.splitlines():
                line = line.strip()
                if line and line not in options:
                    options.append(line)
            if len(options) < 2:
                errors.append("A multiple-choice question needs at least two different options.")
            if any(len(o) > MAX_OPTION for o in options):
                errors.append(f"Each option must be at most {MAX_OPTION} characters.")
        question = {"text": text, "qtype": qtype, "is_required": required,
                    "options": options, "options_text": raw_options}
        return question, errors

    def flash_all(errors):
        for message in errors:
            flash(message, "error")

    # ------------------------------------------------------------------ #
    # Authentication
    # ------------------------------------------------------------------ #
    @app.route("/")
    def index():
        if g.user is None:
            return redirect(url_for("login"))
        return redirect(url_for("admin_dashboard" if g.user["role"] == "admin" else "user_forms"))

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if g.user:
            return redirect(url_for("index"))
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            confirm = request.form.get("confirm", "")
            errors = []
            if not name or len(name) > 80:
                errors.append("Name is required (max 80 characters).")
            if not EMAIL_RE.match(email) or len(email) > 120:
                errors.append("Enter a valid email address.")
            if len(password) < 6:
                errors.append("Password must be at least 6 characters.")
            elif password != confirm:
                errors.append("Passwords do not match.")
            if not errors:
                try:
                    conn = db.get_db()
                    conn.execute(
                        "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'user')",
                        (name, email, generate_password_hash(password)),
                    )
                    conn.commit()
                except sqlite3.IntegrityError:
                    errors.append("That email is already registered.")
            if errors:
                flash_all(errors)
                return render_template("register.html", name=name, email=email), 400
            flash("Account created. You can log in now.", "success")
            return redirect(url_for("login"))
        return render_template("register.html", name="", email="")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if g.user:
            return redirect(url_for("index"))
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            row = db.get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if row and check_password_hash(row["password_hash"], password):
                session.clear()
                session["user_id"] = row["id"]
                return redirect(url_for("index"))
            flash("Incorrect email or password.", "error")
            return render_template("login.html", email=email), 401
        return render_template("login.html", email="")

    @app.route("/logout", methods=["POST"])
    def logout():
        session.clear()
        flash("You have been logged out.", "success")
        return redirect(url_for("login"))

    # ------------------------------------------------------------------ #
    # Admin: forms
    # ------------------------------------------------------------------ #
    @app.route("/admin")
    @admin_required
    def admin_dashboard():
        conn = db.get_db()
        forms = conn.execute(
            "SELECT f.*, "
            "(SELECT COUNT(*) FROM questions q WHERE q.form_id = f.id) AS question_count, "
            "(SELECT COUNT(*) FROM responses r WHERE r.form_id = f.id) AS response_count "
            "FROM forms f ORDER BY f.created_at DESC, f.id DESC"
        ).fetchall()
        stats = {
            "forms": len(forms),
            "active": sum(1 for f in forms if f["is_active"]),
            "responses": sum(f["response_count"] for f in forms),
            "users": conn.execute("SELECT COUNT(*) FROM users WHERE role = 'user'").fetchone()[0],
        }
        return render_template("admin/dashboard.html", forms=forms, stats=stats)

    @app.route("/admin/forms/new", methods=["GET", "POST"])
    @admin_required
    def admin_new_form():
        form = {"title": "", "description": "", "is_active": 1}
        if request.method == "POST":
            title, description, errors = parse_form_fields(request.form)
            form.update(title=title, description=description)
            if errors:
                flash_all(errors)
                return render_template("admin/form_new.html", form=form), 400
            conn = db.get_db()
            cur = conn.execute(
                "INSERT INTO forms (title, description, is_active, created_by) VALUES (?, ?, 1, ?)",
                (title, description, g.user["id"]),
            )
            conn.commit()
            flash("Form created. Now add some questions.", "success")
            return redirect(url_for("admin_edit_form", form_id=cur.lastrowid))
        return render_template("admin/form_new.html", form=form)

    def render_edit(form_id, new_q=None, form_override=None, status=200):
        conn = db.get_db()
        form = form_override or get_form_or_404(form_id)
        response_count = conn.execute(
            "SELECT COUNT(*) FROM responses WHERE form_id = ?", (form_id,)
        ).fetchone()[0]
        new_q = new_q or {"text": "", "qtype": "rating", "is_required": 1, "options_text": ""}
        return render_template(
            "admin/form_edit.html", form=form, questions=load_questions(conn, form_id),
            response_count=response_count, q=new_q,
        ), status

    @app.route("/admin/forms/<int:form_id>/edit", methods=["GET", "POST"])
    @admin_required
    def admin_edit_form(form_id):
        if request.method == "POST":
            form = get_form_or_404(form_id)
            title, description, errors = parse_form_fields(request.form)
            is_active = 1 if request.form.get("is_active") else 0
            if errors:
                flash_all(errors)
                form.update(title=title, description=description, is_active=is_active)
                return render_edit(form_id, form_override=form, status=400)
            conn = db.get_db()
            conn.execute(
                "UPDATE forms SET title = ?, description = ?, is_active = ? WHERE id = ?",
                (title, description, is_active, form_id),
            )
            conn.commit()
            flash("Form saved.", "success")
            return redirect(url_for("admin_edit_form", form_id=form_id))
        return render_edit(form_id)

    @app.route("/admin/forms/<int:form_id>/delete", methods=["POST"])
    @admin_required
    def admin_delete_form(form_id):
        get_form_or_404(form_id)
        conn = db.get_db()
        conn.execute("DELETE FROM forms WHERE id = ?", (form_id,))
        conn.commit()
        flash("Form and all its responses were deleted.", "success")
        return redirect(url_for("admin_dashboard"))

    # ------------------------------------------------------------------ #
    # Admin: questions
    # ------------------------------------------------------------------ #
    @app.route("/admin/forms/<int:form_id>/questions", methods=["POST"])
    @admin_required
    def admin_add_question(form_id):
        get_form_or_404(form_id)
        question, errors = parse_question_fields(request.form)
        if errors:
            flash_all(errors)
            return render_edit(form_id, new_q=question, status=400)
        conn = db.get_db()
        pos = conn.execute(
            "SELECT COALESCE(MAX(position), 0) + 1 FROM questions WHERE form_id = ?", (form_id,)
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO questions (form_id, text, qtype, options, is_required, position) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (form_id, question["text"], question["qtype"], json.dumps(question["options"]),
             question["is_required"], pos),
        )
        conn.commit()
        flash("Question added.", "success")
        return redirect(url_for("admin_edit_form", form_id=form_id) + "#questions")

    @app.route("/admin/questions/<int:question_id>/edit", methods=["GET", "POST"])
    @admin_required
    def admin_edit_question(question_id):
        existing = get_question_or_404(question_id)
        conn = db.get_db()
        response_count = conn.execute(
            "SELECT COUNT(*) FROM responses WHERE form_id = ?", (existing["form_id"],)
        ).fetchone()[0]
        status = 200
        q = dict(existing, options_text="\n".join(existing["options"]))
        if request.method == "POST":
            question, errors = parse_question_fields(request.form)
            if errors:
                flash_all(errors)
                q, status = question, 400
            else:
                conn.execute(
                    "UPDATE questions SET text = ?, qtype = ?, options = ?, is_required = ? WHERE id = ?",
                    (question["text"], question["qtype"], json.dumps(question["options"]),
                     question["is_required"], question_id),
                )
                conn.commit()
                flash("Question updated.", "success")
                return redirect(url_for("admin_edit_form", form_id=existing["form_id"]) + "#questions")
        form = get_form_or_404(existing["form_id"])
        return render_template("admin/question_edit.html", q=q, form=form,
                               response_count=response_count), status

    @app.route("/admin/questions/<int:question_id>/delete", methods=["POST"])
    @admin_required
    def admin_delete_question(question_id):
        q = get_question_or_404(question_id)
        conn = db.get_db()
        conn.execute("DELETE FROM questions WHERE id = ?", (question_id,))
        conn.commit()
        flash("Question deleted.", "success")
        return redirect(url_for("admin_edit_form", form_id=q["form_id"]) + "#questions")

    @app.route("/admin/questions/<int:question_id>/move", methods=["POST"])
    @admin_required
    def admin_move_question(question_id):
        q = get_question_or_404(question_id)
        direction = request.form.get("direction")
        if direction not in ("up", "down"):
            abort(400, "Invalid direction.")
        conn = db.get_db()
        ids = [r["id"] for r in conn.execute(
            "SELECT id FROM questions WHERE form_id = ? ORDER BY position, id", (q["form_id"],))]
        i = ids.index(question_id)
        j = i - 1 if direction == "up" else i + 1
        if 0 <= j < len(ids):
            ids[i], ids[j] = ids[j], ids[i]
            for pos, qid in enumerate(ids, start=1):
                conn.execute("UPDATE questions SET position = ? WHERE id = ?", (pos, qid))
            conn.commit()
        return redirect(url_for("admin_edit_form", form_id=q["form_id"]) + "#questions")

    # ------------------------------------------------------------------ #
    # Admin: responses, summary, export
    # ------------------------------------------------------------------ #
    @app.route("/admin/forms/<int:form_id>/responses")
    @admin_required
    def admin_responses(form_id):
        form = get_form_or_404(form_id)
        questions, responses = load_responses(db.get_db(), form_id)
        return render_template("admin/responses.html", form=form, questions=questions,
                               responses=responses)

    @app.route("/admin/forms/<int:form_id>/summary")
    @admin_required
    def admin_summary(form_id):
        form = get_form_or_404(form_id)
        summary = build_summary(db.get_db(), form_id)
        return render_template("admin/summary.html", form=form, summary=summary)

    def csv_safe(value):
        """Stop spreadsheet apps treating a cell as a formula."""
        value = str(value)
        return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value

    @app.route("/admin/forms/<int:form_id>/export.csv")
    @admin_required
    def admin_export(form_id):
        form = get_form_or_404(form_id)
        questions, responses = load_responses(db.get_db(), form_id)
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["Response ID", "Name", "Email", "Submitted (UTC)"] +
                        [csv_safe(q["text"]) for q in questions])
        for r in responses:
            writer.writerow([r["id"], csv_safe(r["name"]), csv_safe(r["email"]), r["submitted_at"]] +
                            [csv_safe(r["answer_map"].get(q["id"], "")) for q in questions])
        filename = f"form-{form['id']}-responses.csv"
        return Response(buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": f"attachment; filename={filename}"})

    # ------------------------------------------------------------------ #
    # Users: list forms, submit feedback
    # ------------------------------------------------------------------ #
    @app.route("/forms")
    @login_required
    def user_forms():
        if g.user["role"] == "admin":
            return redirect(url_for("admin_dashboard"))
        forms = db.get_db().execute(
            "SELECT f.*, "
            "(SELECT COUNT(*) FROM questions q WHERE q.form_id = f.id) AS question_count, "
            "EXISTS (SELECT 1 FROM responses r WHERE r.form_id = f.id AND r.user_id = ?) AS submitted "
            "FROM forms f WHERE f.is_active = 1 "
            "AND EXISTS (SELECT 1 FROM questions q WHERE q.form_id = f.id) "
            "ORDER BY f.id DESC",
            (g.user["id"],),
        ).fetchall()
        return render_template("user/forms.html", forms=forms)

    @app.route("/forms/<int:form_id>", methods=["GET", "POST"])
    @login_required
    def fill_form(form_id):
        if g.user["role"] == "admin":
            flash("Admins manage forms; log in as a student to submit feedback.", "error")
            return redirect(url_for("admin_edit_form", form_id=form_id))
        conn = db.get_db()
        form = get_form_or_404(form_id)
        questions = load_questions(conn, form_id)
        if not form["is_active"] or not questions:
            flash("This form is not accepting responses.", "error")
            return redirect(url_for("user_forms"))
        done = conn.execute("SELECT 1 FROM responses WHERE form_id = ? AND user_id = ?",
                            (form_id, g.user["id"])).fetchone()
        if done:
            flash("You have already submitted feedback for this form.", "error")
            return redirect(url_for("user_forms"))

        values, errors = {}, {}
        if request.method == "POST":
            for q in questions:
                raw = request.form.get(f"q{q['id']}", "").strip()
                values[q["id"]] = raw
                if not raw:
                    if q["is_required"]:
                        errors[q["id"]] = "This question is required."
                elif q["qtype"] == "rating" and raw not in ("1", "2", "3", "4", "5"):
                    errors[q["id"]] = "Choose a rating from 1 to 5."
                elif q["qtype"] == "choice" and raw not in q["options"]:
                    errors[q["id"]] = "Choose one of the listed options."
                elif q["qtype"] == "text" and len(raw) > MAX_ANSWER:
                    errors[q["id"]] = f"Please keep your answer under {MAX_ANSWER} characters."
            if not errors:
                try:
                    cur = conn.execute("INSERT INTO responses (form_id, user_id) VALUES (?, ?)",
                                       (form_id, g.user["id"]))
                    for q in questions:
                        if values[q["id"]]:
                            conn.execute(
                                "INSERT INTO answers (response_id, question_id, value) VALUES (?, ?, ?)",
                                (cur.lastrowid, q["id"], values[q["id"]]))
                    conn.commit()
                except sqlite3.IntegrityError:
                    conn.rollback()
                    flash("You have already submitted feedback for this form.", "error")
                    return redirect(url_for("user_forms"))
                flash("Thank you! Your feedback has been submitted.", "success")
                return redirect(url_for("user_forms"))
            flash("Please fix the highlighted questions.", "error")
            return render_template("user/fill.html", form=form, questions=questions,
                                   values=values, errors=errors), 400
        return render_template("user/fill.html", form=form, questions=questions,
                               values=values, errors=errors)

    # ------------------------------------------------------------------ #
    # Errors
    # ------------------------------------------------------------------ #
    @app.errorhandler(HTTPException)
    def handle_http_error(err):
        messages = {403: "You do not have permission to view this page.",
                    404: "We could not find that page."}
        message = messages.get(err.code) or err.description
        return render_template("error.html", code=err.code, message=message), err.code

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
