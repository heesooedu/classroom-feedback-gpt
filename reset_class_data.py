# reset_class_data.py
# 문제은행은 그대로 두고 나머지 날리기 

from app import create_app
from models import db, Student, ClassGroup, Enrollment, Submission

app = create_app()

with app.app_context():
    print("제출(Submission) 삭제 중...")
    Submission.query.delete()

    print("수강 정보(Enrollment) 삭제 중...")
    Enrollment.query.delete()

    print("수업/분반(ClassGroup) 삭제 중...")
    ClassGroup.query.delete()

    print("학생(Student) 삭제 중...")
    Student.query.delete()

    db.session.commit()
    print("✅ 학생/수업/제출 데이터 초기화 완료 (문제는 그대로 남겨둠)")
