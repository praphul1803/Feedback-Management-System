# Feedback Management System: Project Documentation

## 1. Introduction

The Feedback Management System lets a college collect structured feedback online. An **admin** builds feedback forms and questions. **Users** (students) log in and submit feedback. The admin then reads the individual responses and a computed summary.

**Technology:** Python 3, Flask (web framework), SQLite (database), Jinja2 templates, plain CSS and a little JavaScript, pytest for testing, Git/GitHub for version control.

## 2. Roles and requirements

| Role  | Can do |
|-------|--------|
| Admin | Create, edit, close and delete forms; add, edit, reorder and delete questions; view all responses; view the summary; export CSV |
| User  | Register, log in, see open forms, submit feedback once per form, see which forms are completed |

Rules enforced by the system:
- Only admins can reach `/admin/...` pages (anonymous visitors are sent to log in, students receive 403).
- Registration always creates a *user*; admins are created only through the seed script or directly in the database.
- A user can submit each form once (database `UNIQUE (form_id, user_id)` plus an application check).
- Closed forms, and forms without questions, cannot be answered.
- Required questions must be answered; ratings must be 1-5; a choice must be one of the listed options.

## 3. System design

```
 Browser ──► Flask routes (app.py) ──► queries.py / db.py ──► SQLite (schema.sql)
                │
                └──► Jinja templates (templates/) + static/ (CSS, JS)
```

### 3.1 Front end (pages, forms, layout)

| Page | URL | Who |
|------|-----|-----|
| Log in / Register | `/login`, `/register` | everyone |
| Admin dashboard (forms list, stats) | `/admin` | admin |
| New form | `/admin/forms/new` | admin |
| Edit form + manage questions | `/admin/forms/<id>/edit` | admin |
| Edit question | `/admin/questions/<id>/edit` | admin |
| Responses | `/admin/forms/<id>/responses` | admin |
| Summary | `/admin/forms/<id>/summary` | admin |
| Open forms list | `/forms` | user |
| Fill a form | `/forms/<id>` | user |

Layout: one shared `base.html` (top bar, flash messages, footer); admin pages use cards and tables; the user form uses large tap-friendly rating buttons and option cards. The CSS is responsive, so tables and bars collapse on phones. `app.js` hides the "options" box unless the type is *Multiple choice* and asks for confirmation before deleting.

### 3.2 Back end (server-side logic and CRUD)

| Entity | Create | Read | Update | Delete |
|--------|--------|------|--------|--------|
| Form | `POST /admin/forms/new` | dashboard, edit page | `POST /admin/forms/<id>/edit` | `POST /admin/forms/<id>/delete` |
| Question | `POST /admin/forms/<id>/questions` | edit page | `POST /admin/questions/<id>/edit` (+ `/move`) | `POST /admin/questions/<id>/delete` |
| Response | `POST /forms/<id>` | responses page, summary, CSV | not allowed | removed with its form |
| User | `POST /register` | n/a | n/a | n/a |

Security measures:
- Passwords stored with Werkzeug's salted hash (never plain text).
- Every SQL statement is parameterised (no string-built SQL), which prevents SQL injection.
- CSRF token required on every POST.
- Jinja auto-escaping prevents stored XSS from question text or answers.
- State-changing actions are POST-only (including log out).
- The session is cleared at login; cookies use `SameSite=Lax`.
- CSV export prefixes cells starting with `= + - @` so spreadsheets do not run them as formulas.
- Login errors are identical for unknown email and wrong password.

### 3.3 Database

**Entity relationships**

```
users 1 ──< responses >── 1 forms 1 ──< questions
                 │                          │
                 └──< answers >─────────────┘
```

- A form has many questions.
- A user submits at most one response per form.
- A response has one answer per answered question.

**Tables**

| Table | Columns | Notes |
|-------|---------|-------|
| `users` | id, name, email (unique), password_hash, role (`admin`/`user`), created_at | role restricted by CHECK |
| `forms` | id, title, description, is_active (0/1), created_by → users, created_at | |
| `questions` | id, form_id → forms, text, qtype (`text`/`rating`/`choice`), options (JSON list), is_required, position | deleted with the form |
| `responses` | id, form_id → forms, user_id → users, submitted_at | `UNIQUE (form_id, user_id)` |
| `answers` | id, response_id → responses, question_id → questions, value | `UNIQUE (response_id, question_id)` |

Foreign keys use `ON DELETE CASCADE` (deleting a form removes its questions, responses and answers). Indexes exist on `questions(form_id, position)`, `responses(form_id)` and `answers(question_id)`.

**Example queries used by the application**

```sql
-- Dashboard: forms with counts
SELECT f.*, (SELECT COUNT(*) FROM questions q WHERE q.form_id = f.id) AS question_count,
            (SELECT COUNT(*) FROM responses r WHERE r.form_id = f.id) AS response_count
FROM forms f ORDER BY f.created_at DESC;

-- Average rating for one question
SELECT AVG(CAST(value AS REAL)) FROM answers WHERE question_id = ?;

-- Which choice was picked how often
SELECT value, COUNT(*) FROM answers WHERE question_id = ? GROUP BY value;
```

**Sample data** (`flask --app app seed`): 1 admin, 5 students, 3 forms (two open, one closed), and 4 responses on the first form so the summary page has something to show.

## 4. Testing

Run with `python -m pytest -v`. The suite has **59 automated test cases** across three files. Each test starts from a fresh temporary database.

| Area | What is verified |
|------|------------------|
| Registration | success; role is always `user`; duplicate email, short password, mismatched passwords, invalid email rejected |
| Login / logout | admin and student redirects; wrong password and unknown user give the same error; log out ends session and needs POST; passwords are hashed |
| Access control | anonymous redirected; students get 403 on every admin URL and cannot POST admin actions; admins are redirected away from student pages |
| Form CRUD | create; blank/overlong title rejected; edit; close; unknown id gives 404; delete cascades; delete needs POST |
| Question CRUD | add each type; choice needs 2+ options; duplicate options collapsed; blank text/invalid type rejected; edit; invalid edit keeps old data; delete; reorder |
| Submitting feedback | success; optional answers may be blank; required answers enforced; entered values kept after an error; rating 0/6/abc/-1/5.5 rejected; choice outside options rejected; overlong text rejected; second submission blocked; closed form and empty form blocked |
| Admin views | responses visible; HTML in answers escaped |
| Summary | average and distribution exact (e.g. ratings 5,4,3 → 4.0); percentages; empty states; seeded data average 4.25 |
| CSV | headers and row counts; formula injection neutralised |
| Security | missing and wrong CSRF token rejected; SQL-injection text in login harmless; deleting a form never deletes users |

### Bugs found and fixed during testing

| # | Bug | Cause | Fix |
|---|-----|-------|-----|
| 1 | Summary page showed "No responses yet" for a form with *no questions* instead of "no questions yet" | The template read `summary.items`; Jinja resolved it to the dictionary's built-in `.items()` method (always true) instead of the data key | Renamed the key to `results` in `queries.py`, the template and the tests |
| 2 | A weak test (`... == 0 or True`) could never fail | Placeholder assertion left in the cascade-delete test | Replaced with a real check that no answers remain |

## 5. Version control and team workflow (GitHub)

The repository history follows the four workstreams:

1. **Database**: schema, seed data, DB helper
2. **Back end**: routes, validation, summary queries
3. **Front end**: templates, CSS, JavaScript
4. **Testing and documentation**: tests, README, this document

Suggested branching for the team: `main` (always working), plus one branch per workstream such as `feature/database`, `feature/backend`, `feature/frontend`, `feature/tests-docs`. Merge through pull requests, run `python -m pytest` before merging, and keep commit messages short and specific (for example `Add CSV export for responses`).

Publishing the repository:

```bash
git remote add origin https://github.com/<your-username>/feedback-management-system.git
git branch -M main
git push -u origin main
```

## 6. Limitations and future work

- Passwords cannot be reset by email, and there is no admin screen for creating more admins (use the database or the seed script).
- Editing a question's type after responses exist can leave older answers that no longer match (the edit page warns about this).
- Charts are simple CSS bars; a chart library could be added for richer analytics.
- Forms are open to all registered users; per-class or per-department targeting would be a natural extension.
- SQLite suits a single college server; moving to MySQL/PostgreSQL would need only small changes in `db.py` and the SQL.
