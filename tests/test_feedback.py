import csv
import io

from helpers import (add_question, count, create_form, login, new_client, post,
                     question_ids, register)
import db
from queries import build_summary


def make_survey(admin, app):
    """A form with one required rating, one optional choice and one optional text question."""
    form_id = create_form(admin, "Survey", "Tell us")
    add_question(admin, form_id, "Rating?", "rating", required=True)
    add_question(admin, form_id, "Pace?", "choice", required=False, options="Slow\nFine\nFast")
    add_question(admin, form_id, "Comments?", "text", required=False)
    return form_id, question_ids(app, form_id)


def answers(qids, rating="5", pace="Fine", comment="Good"):
    data = {}
    for qid, value in zip(qids, (rating, pace, comment)):
        data[f"q{qid}"] = value
    return data


# ---------- listing ----------
def test_student_sees_only_open_forms_with_questions(app, admin, student):
    empty_id = create_form(admin, "Empty form")  # no questions yet
    page = student.get("/forms").get_data(as_text=True)
    assert "Course Feedback" in page and "Campus Facilities" in page
    assert "Orientation Week Feedback" not in page   # closed
    assert "Empty form" not in page                  # no questions


def test_admin_visiting_student_pages_is_redirected(admin):
    assert "/admin" in admin.get("/forms").headers["Location"]
    assert admin.get("/forms/1").status_code == 302


# ---------- submitting ----------
def test_submit_feedback_success(app, admin, student):
    form_id, qids = make_survey(admin, app)
    resp = post(student, f"/forms/{form_id}", answers(qids))
    assert resp.status_code == 302
    assert count(app, "SELECT COUNT(*) FROM responses WHERE form_id = ?", (form_id,)) == 1
    assert count(app, "SELECT COUNT(*) FROM answers") >= 3
    assert "Submitted" in student.get("/forms").get_data(as_text=True)


def test_optional_blank_answers_are_allowed(app, admin, student):
    form_id, qids = make_survey(admin, app)
    assert post(student, f"/forms/{form_id}", answers(qids, pace="", comment="")).status_code == 302
    assert count(app, "SELECT COUNT(*) FROM answers a JOIN responses r ON r.id = a.response_id "
                      "WHERE r.form_id = ?", (form_id,)) == 1


def test_required_question_blocks_submission(app, admin, student):
    form_id, qids = make_survey(admin, app)
    resp = post(student, f"/forms/{form_id}", answers(qids, rating=""))
    assert resp.status_code == 400
    assert "This question is required" in resp.get_data(as_text=True)
    assert count(app, "SELECT COUNT(*) FROM responses WHERE form_id = ?", (form_id,)) == 0


def test_failed_submission_keeps_entered_values(app, admin, student):
    form_id, qids = make_survey(admin, app)
    page = post(student, f"/forms/{form_id}", answers(qids, rating="", comment="Keep this text")).get_data(as_text=True)
    assert "Keep this text" in page


def test_invalid_rating_rejected(app, admin, student):
    form_id, qids = make_survey(admin, app)
    for bad in ("0", "6", "abc", "-1", "5.5"):
        assert post(student, f"/forms/{form_id}", answers(qids, rating=bad)).status_code == 400, bad
    assert count(app, "SELECT COUNT(*) FROM responses WHERE form_id = ?", (form_id,)) == 0


def test_choice_outside_options_rejected(app, admin, student):
    form_id, qids = make_survey(admin, app)
    assert post(student, f"/forms/{form_id}", answers(qids, pace="Teleport")).status_code == 400


def test_overlong_text_rejected(app, admin, student):
    form_id, qids = make_survey(admin, app)
    assert post(student, f"/forms/{form_id}", answers(qids, comment="x" * 2001)).status_code == 400


def test_cannot_submit_twice(app, admin, student):
    form_id, qids = make_survey(admin, app)
    post(student, f"/forms/{form_id}", answers(qids))
    again = post(student, f"/forms/{form_id}", answers(qids, rating="1"))
    assert again.status_code == 302
    assert count(app, "SELECT COUNT(*) FROM responses WHERE form_id = ?", (form_id,)) == 1
    assert count(app, "SELECT value FROM answers WHERE question_id = ?", (qids[0],)) == "5"


def test_closed_form_not_submittable(app, student):
    # Seeded form 3 is closed.
    resp = post(student, "/forms/3", {"q1": "5"})
    assert resp.status_code == 302
    assert count(app, "SELECT COUNT(*) FROM responses WHERE form_id = 3") == 0


def test_closing_form_stops_new_responses(app, admin, student):
    form_id, qids = make_survey(admin, app)
    post(admin, f"/admin/forms/{form_id}/edit", {"title": "Survey"})  # is_active unticked
    post(student, f"/forms/{form_id}", answers(qids))
    assert count(app, "SELECT COUNT(*) FROM responses WHERE form_id = ?", (form_id,)) == 0


def test_unknown_form_is_404(student):
    assert student.get("/forms/9999").status_code == 404


def test_anonymous_cannot_open_form(anon):
    assert anon.get("/forms/1").status_code == 302


# ---------- admin views responses ----------
def test_admin_sees_responses(app, admin, student):
    form_id, qids = make_survey(admin, app)
    post(student, f"/forms/{form_id}", answers(qids, comment="Great lectures"))
    page = admin.get(f"/admin/forms/{form_id}/responses").get_data(as_text=True)
    assert "Aarav Mehta" in page and "Great lectures" in page


def test_responses_page_escapes_html(app, admin, student):
    form_id, qids = make_survey(admin, app)
    post(student, f"/forms/{form_id}", answers(qids, comment="<b>bold</b><script>x</script>"))
    page = admin.get(f"/admin/forms/{form_id}/responses").get_data(as_text=True)
    assert "<script>x</script>" not in page and "&lt;script&gt;" in page


# ---------- summary ----------
def test_summary_calculations(app, admin):
    form_id, qids = make_survey(admin, app)
    for email, rating, pace in (("aarav@example.com", "5", "Fine"),
                                ("diya@example.com", "4", "Fine"),
                                ("kabir@example.com", "3", "Fast")):
        post(new_client(app, email), f"/forms/{form_id}", answers(qids, rating=rating, pace=pace, comment=""))
    with app.app_context():
        summary = build_summary(db.get_db(), form_id)
    assert summary["total"] == 3
    rating, pace, comments = summary["results"]
    assert rating["average"] == 4.0
    assert {b["label"]: b["count"] for b in rating["bars"]} == {"5": 1, "4": 1, "3": 1, "2": 0, "1": 0}
    assert {b["label"]: b["count"] for b in pace["bars"]} == {"Slow": 0, "Fine": 2, "Fast": 1}
    assert pace["bars"][1]["pct"] == 67
    assert comments["texts"] == []
    page = admin.get(f"/admin/forms/{form_id}/summary").get_data(as_text=True)
    assert "4.0" in page and "3 responses" in page


def test_summary_with_no_responses(app, admin):
    form_id, _ = make_survey(admin, app)
    page = admin.get(f"/admin/forms/{form_id}/summary")
    assert page.status_code == 200 and "No responses yet" in page.get_data(as_text=True)


def test_summary_of_seeded_form(app):
    with app.app_context():
        summary = build_summary(db.get_db(), 1)
    assert summary["total"] == 4
    assert summary["results"][0]["average"] == 4.25   # (5+4+3+5)/4
    assert len(summary["results"][4]["texts"]) == 3


def test_summary_with_no_questions(app, admin):
    form_id = create_form(admin)
    assert "no questions yet" in admin.get(f"/admin/forms/{form_id}/summary").get_data(as_text=True)


# ---------- CSV export ----------
def test_csv_export(app, admin):
    resp = admin.get("/admin/forms/1/export.csv")
    assert resp.status_code == 200 and resp.mimetype == "text/csv"
    rows = list(csv.reader(io.StringIO(resp.get_data(as_text=True))))
    assert rows[0][:4] == ["Response ID", "Name", "Email", "Submitted (UTC)"]
    assert len(rows) == 1 + 4 and len(rows[0]) == 4 + 5


def test_csv_export_neutralises_formulas(app, admin, student):
    form_id, qids = make_survey(admin, app)
    post(student, f"/forms/{form_id}", answers(qids, comment="=HYPERLINK(\"http://evil\")"))
    text = admin.get(f"/admin/forms/{form_id}/export.csv").get_data(as_text=True)
    assert "'=HYPERLINK" in text


# ---------- security ----------
def test_post_without_csrf_token_rejected(app, anon):
    anon.get("/login")
    assert anon.post("/login", data={"email": "admin@example.com", "password": "admin123"}).status_code == 400


def test_post_with_wrong_csrf_token_rejected(app, admin):
    before = count(app, "SELECT COUNT(*) FROM forms")
    assert admin.post("/admin/forms/new", data={"title": "X", "csrf": "wrong"}).status_code == 400
    assert count(app, "SELECT COUNT(*) FROM forms") == before


def test_sql_injection_attempt_in_login_is_harmless(app, anon):
    resp = login(anon, "' OR 1=1 --", "x")
    assert resp.status_code == 401
    assert count(app, "SELECT COUNT(*) FROM users") == 6


def test_deleting_form_after_responses_keeps_users(app, admin, student):
    form_id, qids = make_survey(admin, app)
    post(student, f"/forms/{form_id}", answers(qids))
    post(admin, f"/admin/forms/{form_id}/delete")
    assert count(app, "SELECT COUNT(*) FROM users") == 6
    assert count(app, "SELECT COUNT(*) FROM responses WHERE form_id = ?", (form_id,)) == 0
