-- Feedback Management System: database schema (SQLite)
-- Foreign keys are switched on per connection in db.py (PRAGMA foreign_keys = ON).

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    email         TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
    created_at    TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS forms (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,
    description TEXT    NOT NULL DEFAULT '',
    is_active   INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_by  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- qtype: 'text' (free text), 'rating' (1-5), 'choice' (pick one of `options`)
-- options: JSON array of strings, only used when qtype = 'choice'
CREATE TABLE IF NOT EXISTS questions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    form_id     INTEGER NOT NULL REFERENCES forms(id) ON DELETE CASCADE,
    text        TEXT    NOT NULL,
    qtype       TEXT    NOT NULL CHECK (qtype IN ('text', 'rating', 'choice')),
    options     TEXT    NOT NULL DEFAULT '[]',
    is_required INTEGER NOT NULL DEFAULT 1 CHECK (is_required IN (0, 1)),
    position    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_questions_form ON questions(form_id, position);

-- One submission per user per form.
CREATE TABLE IF NOT EXISTS responses (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    form_id      INTEGER NOT NULL REFERENCES forms(id) ON DELETE CASCADE,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    submitted_at TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (form_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_responses_form ON responses(form_id);

CREATE TABLE IF NOT EXISTS answers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    response_id INTEGER NOT NULL REFERENCES responses(id) ON DELETE CASCADE,
    question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    value       TEXT    NOT NULL DEFAULT '',
    UNIQUE (response_id, question_id)
);
CREATE INDEX IF NOT EXISTS idx_answers_question ON answers(question_id);
