# import_class_from_csv.py
import csv
from pathlib import Path

from app import create_app
from models import db, Student, ClassGroup, Enrollment


def import_class_from_csv(subject: str, csv_path: str, year: int | None = None, term: str | None = None):
    """
    CSV 예시:
    분반,학번,이름
    A,10101,김일번
    A,10302,김이번
    B,10503,김삼번
    """
    app = create_app()

    with app.app_context():
        path = Path(csv_path)
        if not path.exists():
            print("CSV 파일을 찾을 수 없습니다:", path)
            return

        with path.open(encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                section = row["분반"].strip()
                code_str = row["학번"].strip()
                name = row["이름"].strip()

                if len(code_str) != 5 or not code_str.isdigit():
                    print("학번 형식이 잘못됨:", code_str)
                    continue

                grade = int(code_str[0])
                class_no = int(code_str[1:3])
                student_no = int(code_str[3:5])

                # Student 찾거나 생성
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
                    db.session.flush()  # id 확보

                # ClassGroup 찾거나 생성
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

                # Enrollment (중복 체크)
                exists = Enrollment.query.filter_by(
                    class_group_id=cg.id, student_id=student.id
                ).first()
                if not exists:
                    enroll = Enrollment(class_group_id=cg.id, student_id=student.id)
                    db.session.add(enroll)

                print(f"등록: {label} - {student.student_code} {student.name}")

        db.session.commit()
        print("CSV import 완료.")


if __name__ == "__main__":
    # 예: python import_class_from_csv.py
    #     → import_class_from_csv("정보", "정보.csv", 2025, "1학기") 같은 식으로 직접 호출
    import_class_from_csv("정보", "정보.csv", 2025, "1학기")
