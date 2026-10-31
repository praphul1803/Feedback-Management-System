"""Small helpers shared by the test modules."""
import re


def csrf(client):
    client.get("/login")
    with client.session_transaction() as sess:
        return sess["csrf"]


def post(client, url, data=None, **kwargs):
    payload = dict(data or {})
    payload.setdefault("csrf", csrf(client))
    return client.post(url, data=payload, **kwargs)


def login(client, email, password):
    return post(client, "/login", {"email": email, "password": password})


def register(client, name, email, password="secret1", confirm=None):
    return post(client, "/register", {
        "name": name, "email": email, "password": password,
        "confirm": password if confirm is None else confirm,
    })


def new_client(app, email=None, password="user123"):
    client = app.test_client()
    if email:
        login(client, email, password)
    return client


def create_form(admin, title="Test form", description="desc"):
    resp = post(admin, "/admin/forms/new", {"title": title, "description": description})
    assert resp.status_code == 302, resp.get_data(as_text=True)
    return int(re.search(r"/admin/forms/(\d+)/edit", resp.headers["Location"]).group(1))


def add_question(admin, form_id, text, qtype="rating", required=True, options=""):
    data = {"text": text, "qtype": qtype, "options": options}
    if required:
        data["is_required"] = "1"
    return post(admin, f"/admin/forms/{form_id}/questions", data)


def question_ids(app, form_id):
    import db
    with app.app_context():
        rows = db.get_db().execute(
            "SELECT id FROM questions WHERE form_id = ? ORDER BY position, id", (form_id,)
        ).fetchall()
        return [r["id"] for r in rows]


def count(app, sql, params=()):
    import db
    with app.app_context():
        return db.get_db().execute(sql, params).fetchone()[0]
