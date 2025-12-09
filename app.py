# app.py

import os
import csv
import io
from functools import wraps
from sqlalchemy import func

from datetime import datetime, timedelta, timezone

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash
)
from dotenv import load_dotenv
from werkzeug.security import check_password_hash

from models import (
    db,
    Student,
    Problem,
    Submission,
    AdminUser,
    ensure_default_admin,
    ClassGroup,
    Enrollment,
)

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
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///autograder_v2.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # ---------- KST(UTC+9) 시간 필터 등록 ----------
    KST = timezone(timedelta(hours=9))

    def format_kst(dt):
        """DB에는 UTC(naive)로 저장되어 있고, 화면에 보여줄 때만 KST로 변환."""
        if dt is None:
            return ""
        # naive datetime이면 UTC 기준으로 간주
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M")

    app.jinja_env.filters["kst"] = format_kst
    # ------------------------------------------------

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
        """
        학생 로그인:
        - 학번(5자리) + 이름으로 Student를 찾는다.
        - 해당 학생이 수강 중인 ClassGroup(분반)을 조회
        - 0개: 에러 메시지
        - 1개: 해당 수업으로 바로 입장
        - 여러 개: 수업 선택 페이지로 이동
        """
        if request.method == "POST":
            code_str = request.form["student_code"].strip()
            name = request.form["name"].strip()

            # 학번 형식 체크 (예: 10101)
            if len(code_str) != 5 or not code_str.isdigit():
                flash("학번은 5자리 숫자로 입력해 주세요. (예: 10101)")
                return redirect(url_for("student_login"))

            grade = int(code_str[0])
            class_no = int(code_str[1:3])
            student_no = int(code_str[3:5])

            # CSV에서 미리 import된 학생을 찾는다
            student = Student.query.filter_by(
                grade=grade, class_no=class_no, student_no=student_no
            ).first()

            if not student:
                flash("등록된 학생이 아닙니다. 선생님께 확인해 주세요.")
                return redirect(url_for("student_login"))

            # 이름도 한번 검증 (오타 방지용)
            if student.name != name:
                flash("이름이 CSV에 등록된 정보와 다릅니다. 다시 확인해 주세요.")
                return redirect(url_for("student_login"))

            # 이 학생이 수강 중인 분반 목록 조회
            enrolls = Enrollment.query.filter_by(student_id=student.id).all()
            class_groups = [e.class_group for e in enrolls]

            if not class_groups:
                flash("등록된 수업(분반)이 없습니다. 선생님께 문의하세요.")
                return redirect(url_for("student_login"))

            # 공통: 학생 기본 정보 세션에 저장
            session["student_id"] = student.id
            session["student_name"] = student.name

            # 분반이 하나면 바로 그 수업으로 입장
            if len(class_groups) == 1:
                cg = class_groups[0]
                session["class_group_id"] = cg.id
                session["class_group_label"] = cg.label
                flash(f"{student.name} 학생, {cg.label} 수업에 로그인되었습니다.")
                return redirect(url_for("problem_list"))

            # 여러 수업을 듣는 학생이면 수업 선택 화면으로
            return render_template(
                "student/class_select.html",
                student=student,
                class_groups=class_groups,
            )

        # GET 요청이면 로그인 폼만 보여줌
        return render_template("student/login.html")

    @app.route("/login/select_class", methods=["POST"])
    def select_class():
        """
        로그인 이후, 여러 분반 중에서 하나를 선택할 때 호출되는 라우트.
        """
        if "student_id" not in session:
            flash("먼저 학생 로그인을 해 주세요.")
            return redirect(url_for("student_login"))

        class_group_id = int(request.form["class_group_id"])
        cg = ClassGroup.query.get_or_404(class_group_id)

        session["class_group_id"] = cg.id
        session["class_group_label"] = cg.label

        flash(f"{session.get('student_name')} 학생, {cg.label} 수업에 로그인되었습니다.")
        return redirect(url_for("problem_list"))

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
            .order_by(Submission.attempt_no.asc())
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

        # 제출 횟수 제한 (최근 24시간 기준 예: 10회)
        student_id = session["student_id"]
        now = datetime.utcnow()
        window_start = now - timedelta(hours=24)

        existing_count = (
            Submission.query
            .filter_by(student_id=student_id, problem_id=problem.id)
            .filter(Submission.created_at >= window_start)
            .count()
        )

        if existing_count >= 10:
            flash("이 문제에 대한 최근 24시간 제출 횟수를 초과했습니다. 선생님께 문의하세요.")
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

    @app.route("/admin/classes/import", methods=["GET", "POST"])
    @admin_login_required
    def admin_class_import():
        """
        CSV 업로드로 수업(분반) + 학생 수강 정보 등록.

        CSV 형식 (UTF-8 권장):
        분반,학번,이름
        A,10101,김일번
        A,10302,김이번
        B,10503,김삼번
        """
        if request.method == "POST":
            subject = request.form["subject"].strip()
            year_raw = request.form.get("year", "").strip()
            term = request.form.get("term", "").strip() or None
            file = request.files.get("csv_file")

            if not subject:
                flash("과목명을 입력해 주세요. (예: 정보, 인공지능기초)")
                return redirect(url_for("admin_class_import"))

            if not file or file.filename == "":
                flash("CSV 파일을 선택해 주세요.")
                return redirect(url_for("admin_class_import"))

            year = None
            if year_raw:
                try:
                    year = int(year_raw)
                except ValueError:
                    flash("연도는 숫자로 입력해 주세요. (예: 2025)")
                    return redirect(url_for("admin_class_import"))

            # 파일 내용 읽기 (UTF-8 BOM → CP949 순서로 시도)
            data = file.read()
            try:
                text = data.decode("utf-8-sig")
            except UnicodeDecodeError:
                try:
                    text = data.decode("cp949")
                except UnicodeDecodeError:
                    flash("CSV 인코딩을 읽을 수 없습니다. UTF-8 또는 CP949로 저장해 주세요.")
                    return redirect(url_for("admin_class_import"))

            reader = csv.DictReader(io.StringIO(text))
            required_cols = {"분반", "학번", "이름"}
            if not required_cols.issubset(reader.fieldnames or []):
                flash("CSV 헤더는 '분반,학번,이름' 형식이어야 합니다.")
                return redirect(url_for("admin_class_import"))

            # 집계용
            new_students = 0
            new_classes = 0
            new_enrollments = 0
            total_rows = 0

            for row in reader:
                total_rows += 1
                section = (row.get("분반") or "").strip()
                code_str = (row.get("학번") or "").strip()
                name = (row.get("이름") or "").strip()

                if not section or not code_str or not name:
                    continue

                if len(code_str) != 5 or not code_str.isdigit():
                    print("학번 형식이 잘못됨:", code_str)
                    continue

                grade = int(code_str[0])
                class_no = int(code_str[1:3])
                student_no = int(code_str[3:5])

                # Student 찾기 또는 생성
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
                    db.session.flush()
                    new_students += 1
                else:
                    # 이름이 바뀌었으면 업데이트할 수도 있음
                    if student.name != name:
                        student.name = name

                # ClassGroup 찾기 또는 생성
                label = f"{subject} {section}반"
                cg = ClassGroup.query.filter_by(
                    subject=subject, section=section
                ).first()
                if not cg:
                    cg = ClassGroup(
                        subject=subject,
                        section=section,
                        label=label,
                        year=year,
                        term=term,
                    )
                    db.session.add(cg)
                    db.session.flush()
                    new_classes += 1

                # Enrollment (수강 정보) 중복 체크 후 생성
                exists = Enrollment.query.filter_by(
                    class_group_id=cg.id,
                    student_id=student.id
                ).first()
                if not exists:
                    enroll = Enrollment(
                        class_group_id=cg.id,
                        student_id=student.id
                    )
                    db.session.add(enroll)
                    new_enrollments += 1

            db.session.commit()
            flash(
                f"CSV 처리 완료: 총 {total_rows}행, "
                f"새 학생 {new_students}명, 새 분반 {new_classes}개, "
                f"새 수강등록 {new_enrollments}건."
            )
            return redirect(url_for("admin_class_import"))

        # GET 요청이면 업로드 폼
        return render_template("admin/class_import.html")

    @app.route("/admin/dashboard")
    @admin_login_required
    def admin_dashboard():
        """
        관리자 대시보드:
        - 수업 분반(ClassGroup) 기준으로 학생 목록을 보고
        - 특정 문제에 대한 제출/점수 현황을 조회한다.
        """
        problems = Problem.query.order_by(Problem.id).all()
        class_groups = ClassGroup.query.order_by(
            ClassGroup.subject, ClassGroup.section
        ).all()

        if not class_groups:
            # 아직 CSV로 수업을 한 번도 등록하지 않은 경우
            flash("등록된 수업(분반)이 없습니다. 먼저 '수업 CSV 등록'에서 수업을 개설하세요.")
            return render_template(
                "admin/dashboard.html",
                problems=problems,
                class_groups=[],
                selected_class_group=None,
                selected_problem_id=None,
                rows=[],
                selected_problem=None,
            )

        # 선택된 분반 id (없으면 첫 번째 분반으로)
        class_group_id = request.args.get("class_group_id", type=int)
        if class_group_id is None:
            class_group = class_groups[0]
        else:
            class_group = ClassGroup.query.get(class_group_id) or class_groups[0]

        # 선택된 문제 id (없으면 None)
        problem_id = request.args.get("problem_id", type=int)
        selected_problem = Problem.query.get(problem_id) if problem_id else None

        # 이 분반에 속한 학생 목록
        enrolls = Enrollment.query.filter_by(class_group_id=class_group.id).all()
        student_ids = [e.student_id for e in enrolls]

        students = []
        if student_ids:
            students = (
                Student.query.filter(Student.id.in_(student_ids))
                .order_by(Student.grade, Student.class_no, Student.student_no)
                .all()
            )

        rows = []
        if selected_problem and students:
            for s in students:
                q = Submission.query.filter_by(
                    student_id=s.id, problem_id=selected_problem.id
                )

                best_score = q.with_entities(func.max(Submission.score)).scalar()
                last_time = q.with_entities(func.max(Submission.created_at)).scalar()
                attempt_count = q.count()

                rows.append(
                    {
                        "student": s,
                        "best_score": best_score,
                        "max_score": selected_problem.max_score,
                        "last_time": last_time,
                        "attempt_count": attempt_count,
                        "has_submitted": attempt_count > 0,
                    }
                )

        return render_template(
            "admin/dashboard.html",
            problems=problems,
            class_groups=class_groups,
            selected_class_group=class_group,
            selected_problem_id=problem_id,
            rows=rows,
            selected_problem=selected_problem,
        )

    @app.route("/admin/submissions")
    @admin_login_required
    def admin_submissions():
        """
        특정 학생 + 특정 문제에 대한 모든 제출 내역을 보는 관리자 페이지.
        ?student_id=...&problem_id=... 형태로 호출.
        """
        student_id = request.args.get("student_id", type=int)
        problem_id = request.args.get("problem_id", type=int)

        if not student_id or not problem_id:
            flash("student_id와 problem_id가 필요합니다.")
            return redirect(url_for("admin_dashboard"))

        student = Student.query.get_or_404(student_id)
        problem = Problem.query.get_or_404(problem_id)

        subs = (
            Submission.query
            .filter_by(student_id=student.id, problem_id=problem.id)
            .order_by(Submission.attempt_no.asc())
            .all()
        )

        return render_template(
            "admin/submissions.html",
            student=student,
            problem=problem,
            submissions=subs,
        )

    @app.route("/admin/submission/<int:submission_id>")
    @admin_login_required
    def admin_submission_detail(submission_id):
        sub = Submission.query.get_or_404(submission_id)
        return render_template("admin/submission_detail.html", submission=sub)

    return app


if __name__ == "__main__":
    from waitress import serve

    app = create_app()
    # 개발할 때는 127.0.0.1로만 써도 되고,
    # 교실 전체에서 접속하려면 host="0.0.0.0" 유지
    print("✅ Waitress 서버 시작: http://0.0.0.0:8000 에서 대기 중...")
    serve(app, host="0.0.0.0", port=8000)
    # app.run(host="0.0.0.0", port=8000, debug=True)
