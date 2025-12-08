# models.py
import os
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash
from sqlalchemy import select

db = SQLAlchemy()


class Student(db.Model):
    """
    실제 학급 기준 학생 정보 (학년/반/번호/이름).
    선택과목 수업 분반과는 Enrollment로 연결된다.
    """
    id = db.Column(db.Integer, primary_key=True)
    grade = db.Column(db.Integer, nullable=False)
    class_no = db.Column(db.Integer, nullable=False)
    student_no = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 관계
    submissions = db.relationship("Submission", backref="student", lazy=True)
    enrollments = db.relationship("Enrollment", backref="student", lazy=True)

    @property
    def student_code(self) -> str:
        """1학년 3반 1번 -> 10301 형태 코드"""
        return f"{self.grade}{self.class_no:02d}{self.student_no:02d}"

    def __repr__(self):
        return f"<Student {self.student_code} {self.name}>"


class ClassGroup(db.Model):
    """
    선택과목 '수업 분반' 엔티티.
    예: subject='정보', section='A', label='정보 A반'
    """
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(100), nullable=False)      # 정보, 인공지능기초 등
    section = db.Column(db.String(20), nullable=False)       # A, B, 1, 2 ...
    label = db.Column(db.String(150), nullable=False)        # 화면에 표시할 이름
    year = db.Column(db.Integer, nullable=True)              # 2025 등
    term = db.Column(db.String(20), nullable=True)           # 1학기, 2학기 등
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    enrollments = db.relationship("Enrollment", backref="class_group", lazy=True)

    def __repr__(self):
        return f"<ClassGroup {self.label}>"


class Enrollment(db.Model):
    """
    학생-수업 분반 매핑 (수강 정보).
    한 학생이 여러 분반을 들을 수 있고,
    한 분반에 여러 학생이 있을 수 있다.
    """
    id = db.Column(db.Integer, primary_key=True)

    class_group_id = db.Column(
        db.Integer, db.ForeignKey("class_group.id"), nullable=False
    )
    student_id = db.Column(
        db.Integer, db.ForeignKey("student.id"), nullable=False
    )

    __table_args__ = (
        db.UniqueConstraint("class_group_id", "student_id", name="uq_enrollment"),
    )

    def __repr__(self):
        return f"<Enrollment student={self.student_id} class_group={self.class_group_id}>"


class Problem(db.Model):
    """
    코딩 문제.
    지금은 분반에 상관없이 공통 문제지만,
    나중에 분반별로 공개 여부를 다르게 해서 사용할 수도 있다.
    """
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    sample_input = db.Column(db.Text, nullable=True)
    sample_output = db.Column(db.Text, nullable=True)
    answer_code = db.Column(db.Text, nullable=False)
    rubric = db.Column(db.Text, nullable=False)
    is_open = db.Column(db.Boolean, default=False)
    max_score = db.Column(db.Integer, default=10)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    submissions = db.relationship("Submission", backref="problem", lazy=True)

    def __repr__(self):
        return f"<Problem {self.id} {self.title}>"


class Submission(db.Model):
    """
    학생 제출.
    Student, Problem에 각각 FK가 걸려 있어야
    Student.submissions / Problem.submissions 관계가 정상 동작한다.
    """
    id = db.Column(db.Integer, primary_key=True)

    student_id = db.Column(
        db.Integer, db.ForeignKey("student.id"), nullable=False
    )
    problem_id = db.Column(
        db.Integer, db.ForeignKey("problem.id"), nullable=False
    )

    code = db.Column(db.Text, nullable=False)
    score = db.Column(db.Integer, nullable=True)
    max_score = db.Column(db.Integer, nullable=True)
    feedback = db.Column(db.Text, nullable=True)
    summary = db.Column(db.Text, nullable=True)
    attempt_no = db.Column(db.Integer, nullable=True)        # 몇 번째 시도인지
    gpt_model = db.Column(db.String(100), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Submission s={self.student_id} p={self.problem_id} score={self.score}>"


class AdminUser(db.Model):
    """
    관리자 계정 (1개 이상 가능).
    username은 유니크, password_hash에는 해시가 들어간다.
    """
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<AdminUser {self.username}>"


def ensure_default_admin():
    """
    앱 시작 시 기본 관리자 계정을 1개 보장하는 함수.
    - 환경변수 ADMIN_USERNAME / ADMIN_PASSWORD 사용
    - 없으면 username='admin', password='admin1234' 기본값.
    """
    username = os.getenv("ADMIN_USERNAME", "admin")
    password = os.getenv("ADMIN_PASSWORD", "admin1234")

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
    print(f"[ensure_default_admin] 기본 관리자 생성됨: {username}")
