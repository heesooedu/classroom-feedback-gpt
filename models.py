# models.py
import os
import datetime as dt

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash

db = SQLAlchemy()


class Student(db.Model):
    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True)
    grade = db.Column(db.Integer, nullable=False)
    class_no = db.Column(db.Integer, nullable=False)
    student_no = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(100), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("grade", "class_no", "student_no", name="uq_student"),
    )

    @property
    def student_code(self) -> str:
        """10101 같은 형식의 학번 문자열."""
        return f"{self.grade}{self.class_no:02d}{self.student_no:02d}"


class Problem(db.Model):
    __tablename__ = "problems"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    sample_input = db.Column(db.Text)
    sample_output = db.Column(db.Text)
    answer_code = db.Column(db.Text, nullable=False)
    rubric = db.Column(db.Text, nullable=False)
    max_score = db.Column(db.Integer, nullable=False, default=10)
    is_open = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=dt.datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=dt.datetime.utcnow,
        onupdate=dt.datetime.utcnow,
    )


class Submission(db.Model):
    __tablename__ = "submissions"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    problem_id = db.Column(db.Integer, db.ForeignKey("problems.id"), nullable=False)
    code = db.Column(db.Text, nullable=False)
    score = db.Column(db.Float)
    max_score = db.Column(db.Float)
    feedback = db.Column(db.Text)
    summary = db.Column(db.Text)
    attempt_no = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=dt.datetime.utcnow)
    gpt_model = db.Column(db.String(50))

    student = db.relationship("Student", backref="submissions")
    problem = db.relationship("Problem", backref="submissions")


class AdminUser(db.Model):
    __tablename__ = "admin_users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=dt.datetime.utcnow)


def ensure_default_admin():
    """
    환경변수 ADMIN_USERNAME / ADMIN_PASSWORD 기반으로
    기본 관리자 계정이 없으면 하나 만든다.
    """
    from sqlalchemy import select

    username = os.getenv("ADMIN_USERNAME", "admin")
    password = os.getenv("ADMIN_PASSWORD", "admin1234")

    # 이미 있으면 아무것도 안 함
    stmt = select(AdminUser).where(AdminUser.username == username)
    existing = db.session.execute(stmt).scalar_one_or_none()
    if existing:
        return

    admin = AdminUser(
        username=username,
        password_hash=generate_password_hash(password),
    )
    db.session.add(admin)
    db.session.commit()
    print(f"[INFO] 기본 관리자 계정 생성: {username} / {password}")
