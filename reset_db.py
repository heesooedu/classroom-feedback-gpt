# reset_db.py
# 완전 삭제. 문제도 날아감!!

from app import create_app
from models import db, ensure_default_admin

app = create_app()

with app.app_context():
    print("모든 테이블을 드롭(drop)합니다...")
    db.drop_all()

    print("테이블을 다시 생성합니다...")
    db.create_all()

    print("기본 관리자 계정을 생성합니다...")
    ensure_default_admin()

    print("✅ DB 초기화 완료")
