from helpers import count, login, post, register


def test_register_creates_student_account(app, anon):
    resp = register(anon, "New Student", "New@Example.com")
    assert resp.status_code == 302 and "/login" in resp.headers["Location"]
    assert count(app, "SELECT role FROM users WHERE email = 'new@example.com'") == "user"


def test_register_never_creates_admin(app, anon):
    post(anon, "/register", {"name": "Sneaky", "email": "s@example.com", "password": "secret1",
                             "confirm": "secret1", "role": "admin"})
    assert count(app, "SELECT role FROM users WHERE email = 's@example.com'") == "user"


def test_register_duplicate_email_rejected(anon):
    resp = register(anon, "Dup", "aarav@example.com")
    assert resp.status_code == 400
    assert "already registered" in resp.get_data(as_text=True)


def test_register_short_password_rejected(app, anon):
    resp = register(anon, "Short", "short@example.com", password="123")
    assert resp.status_code == 400
    assert count(app, "SELECT COUNT(*) FROM users WHERE email = 'short@example.com'") == 0


def test_register_password_mismatch_rejected(anon):
    resp = register(anon, "Mismatch", "mm@example.com", password="secret1", confirm="secret2")
    assert resp.status_code == 400
    assert "do not match" in resp.get_data(as_text=True)


def test_register_invalid_email_rejected(anon):
    assert register(anon, "Bad", "not-an-email").status_code == 400


def test_admin_login_redirects_to_dashboard(anon):
    resp = login(anon, "admin@example.com", "admin123")
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/")
    assert anon.get("/", follow_redirects=False).headers["Location"].endswith("/admin")


def test_student_login_redirects_to_forms(anon):
    login(anon, "aarav@example.com", "user123")
    assert anon.get("/", follow_redirects=False).headers["Location"].endswith("/forms")


def test_login_wrong_password(anon):
    resp = login(anon, "admin@example.com", "wrong")
    assert resp.status_code == 401
    assert "Incorrect email or password" in resp.get_data(as_text=True)


def test_login_unknown_user_gives_same_message(anon):
    resp = login(anon, "nobody@example.com", "whatever")
    assert resp.status_code == 401
    assert "Incorrect email or password" in resp.get_data(as_text=True)


def test_logout_ends_session(admin):
    assert admin.get("/admin").status_code == 200
    post(admin, "/logout")
    assert admin.get("/admin").status_code == 302


def test_logout_requires_post(admin):
    assert admin.get("/logout").status_code == 405


def test_passwords_are_hashed(app):
    assert count(app, "SELECT password_hash FROM users WHERE email = 'admin@example.com'") != "admin123"
