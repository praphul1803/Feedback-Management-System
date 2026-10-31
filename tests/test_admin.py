from helpers import add_question, count, create_form, post, question_ids


# ---------- access control ----------
def test_anonymous_redirected_from_admin(anon):
    assert anon.get("/admin").status_code == 302
    assert "/login" in anon.get("/admin").headers["Location"]


def test_student_gets_403_on_admin_pages(student):
    for url in ("/admin", "/admin/forms/new", "/admin/forms/1/edit",
                "/admin/forms/1/responses", "/admin/forms/1/summary", "/admin/forms/1/export.csv"):
        assert student.get(url).status_code == 403, url


def test_student_cannot_post_admin_actions(app, student):
    before = count(app, "SELECT COUNT(*) FROM forms")
    assert post(student, "/admin/forms/new", {"title": "Hack"}).status_code == 403
    assert post(student, "/admin/forms/1/delete").status_code == 403
    assert count(app, "SELECT COUNT(*) FROM forms") == before


# ---------- form CRUD ----------
def test_admin_creates_form(app, admin):
    form_id = create_form(admin, "Lab Feedback", "About the labs")
    assert count(app, "SELECT title FROM forms WHERE id = ?", (form_id,)) == "Lab Feedback"
    assert count(app, "SELECT is_active FROM forms WHERE id = ?", (form_id,)) == 1


def test_create_form_requires_title(app, admin):
    before = count(app, "SELECT COUNT(*) FROM forms")
    resp = post(admin, "/admin/forms/new", {"title": "   ", "description": "x"})
    assert resp.status_code == 400
    assert count(app, "SELECT COUNT(*) FROM forms") == before


def test_create_form_title_too_long(admin):
    assert post(admin, "/admin/forms/new", {"title": "x" * 121}).status_code == 400


def test_admin_edits_form_and_closes_it(app, admin):
    form_id = create_form(admin)
    resp = post(admin, f"/admin/forms/{form_id}/edit", {"title": "Renamed", "description": "new"})
    assert resp.status_code == 302
    assert count(app, "SELECT title FROM forms WHERE id = ?", (form_id,)) == "Renamed"
    assert count(app, "SELECT is_active FROM forms WHERE id = ?", (form_id,)) == 0  # box unticked


def test_edit_form_blank_title_keeps_old(app, admin):
    form_id = create_form(admin, "Keep me")
    assert post(admin, f"/admin/forms/{form_id}/edit", {"title": ""}).status_code == 400
    assert count(app, "SELECT title FROM forms WHERE id = ?", (form_id,)) == "Keep me"


def test_missing_form_is_404(admin):
    assert admin.get("/admin/forms/9999/edit").status_code == 404
    assert admin.get("/admin/forms/9999/summary").status_code == 404


def test_delete_form_cascades(app, admin, student):
    # Form 1 is seeded with questions and responses.
    assert count(app, "SELECT COUNT(*) FROM responses WHERE form_id = 1") > 0
    post(admin, "/admin/forms/1/delete")
    assert count(app, "SELECT COUNT(*) FROM forms WHERE id = 1") == 0
    assert count(app, "SELECT COUNT(*) FROM questions WHERE form_id = 1") == 0
    assert count(app, "SELECT COUNT(*) FROM responses WHERE form_id = 1") == 0
    assert count(app, "SELECT COUNT(*) FROM answers") == 0  # only form 1 had answers


def test_delete_form_requires_post(admin):
    assert admin.get("/admin/forms/1/delete").status_code == 405


# ---------- question CRUD ----------
def test_add_questions_of_each_type(app, admin):
    form_id = create_form(admin)
    assert add_question(admin, form_id, "Rate it", "rating").status_code == 302
    assert add_question(admin, form_id, "Pick one", "choice", options="A\nB\nC").status_code == 302
    assert add_question(admin, form_id, "Comments", "text", required=False).status_code == 302
    assert count(app, "SELECT COUNT(*) FROM questions WHERE form_id = ?", (form_id,)) == 3
    assert count(app, "SELECT options FROM questions WHERE form_id = ? AND qtype = 'choice'",
                 (form_id,)) == '["A", "B", "C"]'


def test_choice_needs_two_options(app, admin):
    form_id = create_form(admin)
    resp = add_question(admin, form_id, "Pick", "choice", options="Only one")
    assert resp.status_code == 400
    assert "at least two" in resp.get_data(as_text=True)
    assert question_ids(app, form_id) == []


def test_duplicate_options_collapsed(app, admin):
    form_id = create_form(admin)
    add_question(admin, form_id, "Pick", "choice", options="A\nA\nB\n\n  B  ")
    assert count(app, "SELECT options FROM questions WHERE form_id = ?", (form_id,)) == '["A", "B"]'


def test_question_text_required_and_type_valid(app, admin):
    form_id = create_form(admin)
    assert add_question(admin, form_id, "", "rating").status_code == 400
    assert add_question(admin, form_id, "Q", "essay").status_code == 400
    assert question_ids(app, form_id) == []


def test_edit_question(app, admin):
    form_id = create_form(admin)
    add_question(admin, form_id, "Old text", "rating")
    qid = question_ids(app, form_id)[0]
    assert admin.get(f"/admin/questions/{qid}/edit").status_code == 200
    resp = post(admin, f"/admin/questions/{qid}/edit", {"text": "New text", "qtype": "rating"})
    assert resp.status_code == 302
    assert count(app, "SELECT text FROM questions WHERE id = ?", (qid,)) == "New text"
    assert count(app, "SELECT is_required FROM questions WHERE id = ?", (qid,)) == 0


def test_edit_question_invalid_keeps_old(app, admin):
    form_id = create_form(admin)
    add_question(admin, form_id, "Stay", "rating")
    qid = question_ids(app, form_id)[0]
    assert post(admin, f"/admin/questions/{qid}/edit", {"text": "", "qtype": "rating"}).status_code == 400
    assert count(app, "SELECT text FROM questions WHERE id = ?", (qid,)) == "Stay"


def test_delete_question(app, admin):
    form_id = create_form(admin)
    add_question(admin, form_id, "Q1")
    add_question(admin, form_id, "Q2")
    first = question_ids(app, form_id)[0]
    post(admin, f"/admin/questions/{first}/delete")
    assert len(question_ids(app, form_id)) == 1


def test_move_question_reorders(app, admin):
    form_id = create_form(admin)
    for t in ("A", "B", "C"):
        add_question(admin, form_id, t)
    a, b, c = question_ids(app, form_id)
    post(admin, f"/admin/questions/{c}/move", {"direction": "up"})
    assert question_ids(app, form_id) == [a, c, b]
    post(admin, f"/admin/questions/{a}/move", {"direction": "up"})  # already first: no change
    assert question_ids(app, form_id) == [a, c, b]
    assert post(admin, f"/admin/questions/{a}/move", {"direction": "sideways"}).status_code == 400


def test_question_html_is_escaped(admin):
    form_id = create_form(admin)
    add_question(admin, form_id, "<script>alert(1)</script>")
    page = admin.get(f"/admin/forms/{form_id}/edit").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page
