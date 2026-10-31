"""Read-side helpers: loading questions/responses and building the summary."""
import json


def load_questions(conn, form_id):
    rows = conn.execute(
        "SELECT * FROM questions WHERE form_id = ? ORDER BY position, id", (form_id,)
    ).fetchall()
    questions = []
    for row in rows:
        q = dict(row)
        q["options"] = json.loads(q["options"] or "[]")
        questions.append(q)
    return questions


def load_responses(conn, form_id):
    """Return (questions, responses). Each response has an `answer_map` {question_id: value}."""
    questions = load_questions(conn, form_id)
    responses = [
        dict(r)
        for r in conn.execute(
            "SELECT r.id, r.submitted_at, u.name, u.email "
            "FROM responses r JOIN users u ON u.id = r.user_id "
            "WHERE r.form_id = ? ORDER BY r.submitted_at DESC, r.id DESC",
            (form_id,),
        )
    ]
    by_id = {r["id"]: r for r in responses}
    for r in responses:
        r["answer_map"] = {}
    for a in conn.execute(
        "SELECT a.response_id, a.question_id, a.value FROM answers a "
        "JOIN responses r ON r.id = a.response_id WHERE r.form_id = ?",
        (form_id,),
    ):
        by_id[a["response_id"]]["answer_map"][a["question_id"]] = a["value"]
    return questions, responses


def _bars(pairs, total):
    return [
        {"label": label, "count": count, "pct": round(100 * count / total) if total else 0}
        for label, count in pairs
    ]


def build_summary(conn, form_id):
    """Aggregate answers per question: averages and distributions, or the list of comments."""
    questions = load_questions(conn, form_id)
    total = conn.execute("SELECT COUNT(*) FROM responses WHERE form_id = ?", (form_id,)).fetchone()[0]
    eligible = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'user'").fetchone()[0]

    items = []
    for q in questions:
        vals = [
            r["value"]
            for r in conn.execute(
                "SELECT value FROM answers WHERE question_id = ? AND value != '' ORDER BY id",
                (q["id"],),
            )
        ]
        item = {"question": q, "answered": len(vals), "total": total}
        if q["qtype"] == "rating":
            nums = [int(v) for v in vals if v.isdigit()]
            item["average"] = round(sum(nums) / len(nums), 2) if nums else None
            item["bars"] = _bars([(str(n), nums.count(n)) for n in range(5, 0, -1)], len(nums))
        elif q["qtype"] == "choice":
            item["bars"] = _bars([(opt, vals.count(opt)) for opt in q["options"]], len(vals))
        else:
            item["texts"] = vals
        items.append(item)
    return {"total": total, "eligible": eligible, "results": items}
