import csv
import io
import os
import random
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

DB_PATH = os.environ.get("DB_PATH", "app.db")
RETRY_PENALTY = 0.10
MAX_SCORE = 100.0

app = FastAPI(title="Economics Learning API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with closing(get_conn()) as conn, conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                canvas_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                sis_login_id TEXT
            );
            CREATE TABLE IF NOT EXISTS activity_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL REFERENCES students(id),
                activity TEXT NOT NULL,
                completed INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                UNIQUE (student_id, activity)
            );
            CREATE TABLE IF NOT EXISTS assignment_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL REFERENCES students(id),
                assignment TEXT NOT NULL,
                question_id TEXT NOT NULL,
                attempt_number INTEGER NOT NULL,
                correct INTEGER NOT NULL,
                score REAL NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )


init_db()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Question parameters derive from a seed embedded in the question id, so the
# server can regenerate and verify the answer without storing questions.
def build_question(seed: int) -> dict:
    rng = random.Random(seed)
    a_name, b_name = rng.sample(
        ["laptops", "phones", "bicycles", "books", "chairs", "lamps"], 2
    )
    a_max = rng.randrange(20, 101, 5)
    b_max = rng.randrange(20, 101, 5)
    give_up = rng.randint(2, max(2, a_max // 2))
    gain = round(give_up * b_max / a_max, 2)
    return {
        "question_id": f"oc-{seed}",
        "text": (
            f"An economy can produce at most {a_max} {a_name} or {b_max} {b_name} "
            f"per week, with a constant trade-off. What is the opportunity cost, "
            f"in {b_name}, of producing {give_up} more {a_name}?"
        ),
        "_answer": gain,
    }


def public_question(q: dict) -> dict:
    return {k: v for k, v in q.items() if not k.startswith("_")}


def seed_from_id(question_id: str) -> int:
    try:
        prefix, seed = question_id.split("-", 1)
        if prefix != "oc":
            raise ValueError
        return int(seed)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid question_id")


def grade(is_correct: bool, attempt_number: int) -> float:
    """Full marks on first try; 10% of max score deducted per retry."""
    if not is_correct:
        return 0.0
    penalty = RETRY_PENALTY * (attempt_number - 1)
    return round(max(0.0, MAX_SCORE * (1 - penalty)), 2)


class StudentIn(BaseModel):
    canvas_id: str
    name: str
    sis_login_id: str | None = None


class AnswerIn(BaseModel):
    student_id: int
    assignment: str = "opportunity-cost"
    question_id: str
    answer: float


class ProgressIn(BaseModel):
    student_id: int
    activity: str
    completed: bool = True


@app.post("/students")
def upsert_student(s: StudentIn):
    with closing(get_conn()) as conn, conn:
        conn.execute(
            "INSERT INTO students (canvas_id, name, sis_login_id) VALUES (?,?,?) "
            "ON CONFLICT(canvas_id) DO UPDATE SET name=excluded.name, "
            "sis_login_id=excluded.sis_login_id",
            (s.canvas_id, s.name, s.sis_login_id),
        )
        row = conn.execute(
            "SELECT id FROM students WHERE canvas_id=?", (s.canvas_id,)
        ).fetchone()
    return {"id": row["id"]}


@app.get("/questions/opportunity-cost")
def new_question():
    return public_question(build_question(random.randint(1, 10**9)))


@app.post("/questions/opportunity-cost/answer")
def submit_answer(a: AnswerIn):
    expected = build_question(seed_from_id(a.question_id))["_answer"]
    correct = abs(a.answer - expected) <= 0.01
    with closing(get_conn()) as conn, conn:
        if not conn.execute(
            "SELECT 1 FROM students WHERE id=?", (a.student_id,)
        ).fetchone():
            raise HTTPException(status_code=404, detail="Student not found")
        prev = conn.execute(
            "SELECT COUNT(*) AS n FROM assignment_attempts "
            "WHERE student_id=? AND assignment=? AND question_id=?",
            (a.student_id, a.assignment, a.question_id),
        ).fetchone()["n"]
        attempt = prev + 1
        score = grade(correct, attempt)
        conn.execute(
            "INSERT INTO assignment_attempts (student_id, assignment, question_id, "
            "attempt_number, correct, score, created_at) VALUES (?,?,?,?,?,?,?)",
            (a.student_id, a.assignment, a.question_id, attempt, int(correct), score, now()),
        )
    return {"correct": correct, "attempt_number": attempt, "score": score}


@app.post("/progress")
def save_progress(p: ProgressIn):
    with closing(get_conn()) as conn, conn:
        conn.execute(
            "INSERT INTO activity_progress (student_id, activity, completed, updated_at) "
            "VALUES (?,?,?,?) ON CONFLICT(student_id, activity) DO UPDATE SET "
            "completed=excluded.completed, updated_at=excluded.updated_at",
            (p.student_id, p.activity, int(p.completed), now()),
        )
    return {"ok": True}


@app.get("/export/canvas-gradebook")
def export_gradebook(assignment: str = "opportunity-cost"):
    """CSV in Canvas gradebook import layout (best score per student)."""
    with closing(get_conn()) as conn:
        rows = conn.execute(
            "SELECT s.name, s.canvas_id, s.sis_login_id, "
            "COALESCE(MAX(a.score), 0) AS score "
            "FROM students s LEFT JOIN assignment_attempts a "
            "ON a.student_id = s.id AND a.assignment = ? "
            "GROUP BY s.id ORDER BY s.name",
            (assignment,),
        ).fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Student", "ID", "SIS Login ID", assignment])
    for r in rows:
        w.writerow([r["name"], r["canvas_id"], r["sis_login_id"] or "", r["score"]])
    return Response(
        buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="canvas_gradebook.csv"'},
    )
