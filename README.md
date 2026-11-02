# Feedback Management System

A web application where an **admin** creates feedback forms and questions, **users** (students) submit feedback, and the admin reviews every response together with an automatic summary.

## Features

**Admin**

- Create, edit, close/reopen and delete feedback forms
- Add, edit, reorder and delete questions (short text, 1-5 rating, multiple choice; required or optional)
- View every response, one card per student
- Summary page: average rating, answer bars, written comments, participation percentage
- Download responses as CSV

**User**

- Register and log in
- See open forms and which ones are already completed
- Submit feedback once per form, with validation
- Dark and light theme toggle with system preference detection and persistent preference

## Tech stack

| Layer     | Technology                                |
| --------- | ----------------------------------------- |
| Front end | HTML5, CSS3, JavaScript, Jinja2 templates |
| Back end  | Python 3, Flask                           |
| Database  | SQLite                                    |
| Testing   | pytest (59 test cases)                    |

## Getting started

```bash
git clone https://github.com/[your-username]/feedback-management-system.git
cd feedback-management-system

python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

flask --app app init-db           # create tables
flask --app app seed              # load sample data
flask --app app run               # open http://127.0.0.1:5000
```

### Sample logins (created by `seed`)

| Role  | Email             | Password |
| ----- | ----------------- | -------- |
| Admin | admin@example.com | admin123 |
| User  | aarav@example.com | user123  |

## Database

Five tables: `users`, `forms`, `questions`, `responses`, `answers`. Deleting a form removes its questions, responses and answers (cascading delete). One user can submit one response per form.

## Security

Salted password hashing, parameterised SQL (no SQL injection), CSRF token on every POST, auto-escaped output (no stored XSS), role-based access control, and CSV export that neutralises spreadsheet formulas.

## Run the tests

```bash
python -m pytest -v
```

## Project structure

```
app.py          routes, validation, access control
queries.py      read queries and summary calculation
db.py           database connection, schema, sample data
schema.sql      table definitions
templates/      Jinja pages (admin/ and user/)
static/         CSS and JavaScript
tests/          pytest test suite
docs/           full project documentation
```
