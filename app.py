# app.py
import os
from functools import wraps

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash
)
from dotenv import load_dotenv
from werkzeug.security import check_password_hash

from models import db, Student, Problem, Submission, AdminUser, ensure_default_admin
from get_grader import grade_with_gpt

# .env 로드 (SECRET_KEY, OPENAI_API_KEY, ADMIN_* 등)
load_dotenv()


# ----------------- 로그인 데코레이터 -----------------
def student_login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "student_id" not in session:
            flash("학생 로그인이 필요합니다.")
            return redirect(url_for("student_login"))
        return f(*args, **kwargs)
    return wrapper


def admin_login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "admin_id" not in session:
            flash("관리자 로그인이 필요합니다.")
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return wrapper


# ----------------- Flask 앱 팩토리 -----------------
def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key")
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///autograder.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    with app.app_context():
        db.create_all()
        ensure_default_admin()

    # ----------------- 학생용 라우트 -----------------
    @app.route("/")
    def index():
        return render_template("student/index.html")

    @app.route("/login", methods=["GET", "POST"])
    def student_login():
        if request.method == "POST":
            grade = int(request.form["grade"])
            class_no = int(request.form["class_no"])
            student_no = int(request.form["student_no"])
            name = request.form["name"].strip()

            # TODO: 여기서 CSV 검증 로직을 넣어도 됨
            # if not validate_with_csv(grade, class_no, student_no, name): ...

            student = Student.query.filter_by(
                grade=grade, class_no=class_no, student_no=student_no
            ).first()
            if not student:
                student = Student(
                    grade=grade,
                    class_no=class_no,
                    student_no=student_no,
                    name=name,
                )
                db.session.add(student)
                db.session.commit()

            session["student_id"] = student.id
            session["student_name"] = student.name
            flash(f"{student.name} 학생, 로그인되었습니다.")
            return redirect(url_for("problem_list"))

        return render_template("student/login.html")

    @app.route("/logout")
    @student_login_required
    def student_logout():
        session.clear()
        flash("로그아웃되었습니다.")
        return redirect(url_for("index"))

    @app.route("/problems")
    @student_login_required
    def problem_list():
        problems = Problem.query.filter_by(is_open=True).order_by(Problem.id).all()
        return render_template("student/problems.html", problems=problems)

    @app.route("/problems/<int:problem_id>", methods=["GET"])
    @student_login_required
    def problem_detail(problem_id):
        problem = Problem.query.get_or_404(problem_id)
        submissions = (
            Submission.query
            .filter_by(student_id=session["student_id"], problem_id=problem.id)
            .order_by(Submission.created_at.desc())
            .all()
        )
        return render_template(
            "student/problem_detail.html",
            problem=problem,
            submissions=submissions,
        )

    @app.route("/problems/<int:problem_id>/submit", methods=["POST"])
    @student_login_required
    def submit_code(problem_id):
        problem = Problem.query.get_or_404(problem_id)
        code = request.form["code"]

        # 제출 횟수 제한 (예: 10회)
        student_id = session["student_id"]
        existing_count = Submission.query.filter_by(
            student_id=student_id, problem_id=problem.id
        ).count()
        if existing_count >= 10:
            flash("이 문제에 대한 최대 제출 횟수를 초과했습니다. 선생님께 문의하세요.")
            return redirect(url_for("problem_detail", problem_id=problem.id))

        attempt_no = existing_count + 1
        student = Student.query.get(student_id)
        student_label = f"{student.student_code} {student.name}"

        result = grade_with_gpt(problem, code, student_label)

        submission = Submission(
            student_id=student_id,
            problem_id=problem.id,
            code=code,
            score=result["score"],
            max_score=result["max_score"],
            feedback=result["feedback"],
            summary=result["summary"],
            attempt_no=attempt_no,
            gpt_model=result["model"],
        )
        db.session.add(submission)
        db.session.commit()

        flash("코드가 제출되고 자동 채점되었습니다.")
        return redirect(url_for("submission_detail", submission_id=submission.id))

    @app.route("/history")
    @student_login_required
    def history():
        subs = (
            Submission.query
            .filter_by(student_id=session["student_id"])
            .order_by(Submission.created_at.desc())
            .all()
        )
        return render_template("student/history.html", submissions=subs)

    @app.route("/submission/<int:submission_id>")
    @student_login_required
    def submission_detail(submission_id):
        sub = Submission.query.get_or_404(submission_id)
        if sub.student_id != session["student_id"]:
            flash("본인 제출만 열람할 수 있습니다.")
            return redirect(url_for("history"))
        return render_template("student/submission_detail.html", submission=sub)

    # ----------------- 관리자 라우트 -----------------
    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        if request.method == "POST":
            username = request.form["username"]
            password = request.form["password"]
            admin = AdminUser.query.filter_by(username=username).first()

            if admin and check_password_hash(admin.password_hash, password):
                session["admin_id"] = admin.id
                flash("관리자 로그인 성공.")
                return redirect(url_for("admin_problem_list"))
            flash("로그인 실패.")
        return render_template("admin/login.html")

    @app.route("/admin/logout")
    @admin_login_required
    def admin_logout():
        session.pop("admin_id", None)
        flash("관리자 로그아웃.")
        return redirect(url_for("admin_login"))

    @app.route("/admin/problems")
    @admin_login_required
    def admin_problem_list():
        problems = Problem.query.order_by(Problem.id).all()
        return render_template("admin/problems.html", problems=problems)

    @app.route("/admin/problems/new", methods=["GET", "POST"])
    @admin_login_required
    def admin_problem_new():
        if request.method == "POST":
            p = Problem(
                title=request.form["title"],
                description=request.form["description"],
                sample_input=request.form.get("sample_input") or None,
                sample_output=request.form.get("sample_output") or None,
                answer_code=request.form["answer_code"],
                rubric=request.form["rubric"],
                max_score=int(request.form.get("max_score", 10)),
                is_open=("is_open" in request.form),
            )
            db.session.add(p)
            db.session.commit()
            flash("문제가 생성되었습니다.")
            return redirect(url_for("admin_problem_list"))
        return render_template("admin/problem_form.html", problem=None)

    @app.route("/admin/problems/<int:problem_id>/edit", methods=["GET", "POST"])
    @admin_login_required
    def admin_problem_edit(problem_id):
        problem = Problem.query.get_or_404(problem_id)
        if request.method == "POST":
            problem.title = request.form["title"]
            problem.description = request.form["description"]
            problem.sample_input = request.form.get("sample_input") or None
            problem.sample_output = request.form.get("sample_output") or None
            problem.answer_code = request.form["answer_code"]
            problem.rubric = request.form["rubric"]
            problem.max_score = int(request.form.get("max_score", 10))
            problem.is_open = ("is_open" in request.form)
            db.session.commit()
            flash("문제가 수정되었습니다.")
            return redirect(url_for("admin_problem_list"))
        return render_template("admin/problem_form.html", problem=problem)

    @app.route("/admin/problems/<int:problem_id>/toggle_open", methods=["POST"])
    @admin_login_required
    def admin_problem_toggle_open(problem_id):
        problem = Problem.query.get_or_404(problem_id)
        problem.is_open = not problem.is_open
        db.session.commit()
        flash("공개 상태가 변경되었습니다.")
        return redirect(url_for("admin_problem_list"))

    # TODO:
    # /admin/dashboard
    # /admin/submission/<id>
    # /admin/submission/<id>/rescore
    # /admin/export
    # 등은 2단계에서 구현.

    return app


if __name__ == "__main__":
    app = create_app()
    # 컴퓨터실에서 여러 PC가 접속하려면 host="0.0.0.0" 사용
    app.run(host="0.0.0.0", port=8000, debug=True)
