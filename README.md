# Python 자동 채점 웹 시스템 (교실용)

> 고등학교 컴퓨터실에서 파이썬 기초 문법 문제를 자동으로 채점해 주는 웹 시스템입니다.  
> 선생님 PC 1대를 서버로 사용하고, 학생들은 같은 로컬망의 브라우저로 접속합니다.

---

## 주요 기능 요약

- **학생**
  - 학번(5자리) + 이름으로 간단 로그인
  - 공개된 문제 목록 조회
  - 브라우저에서 파이썬 코드 작성 & 제출
  - GPT 기반 자동 채점 결과 및 피드백 확인
  - 문제별 제출 이력 확인

- **교사(관리자)**
  - 관리자 로그인
  - **수업/분반 개설**: CSV 업로드로 과목/분반/학생 등록
  - 문제 생성/수정/공개 여부 관리
  - 반/문제별 대시보드에서 제출 현황 확인
  - 개별 학생의 제출 코드 & GPT 피드백 열람

---

## 기술 스택

- **Backend**: Python, Flask, Flask-SQLAlchemy
- **DB**: SQLite (`autograder_v2.db` 한 파일)
- **Frontend**: HTML + CSS + Jinja2 템플릿
- **LLM**: OpenAI API (모델 이름은 `get_grader.py`에서 설정)
- **서버 실행**: Waitress WSGI 서버

---

## 0. 준비물 (선행 조건)

1. **Python 3.10 이상**  
   - Windows에서 `python --version` 또는 `py --version`으로 버전 확인

2. **Git**  
   - Git이 설치되어 있고, 이 프로젝트가 GitHub에 올라가 있다고 가정합니다.

3. **OpenAI API 키**
   - OpenAI 계정에서 발급받은 API 키 (예: `sk-...`)

---

## 1. 코드 내려받기 (GitHub에서 clone)

터미널(또는 PowerShell)을 열고, 코드를 저장할 폴더로 이동한 뒤:

```bash
git clone https://github.com/본인계정/본인레포.git
cd 본인레포폴더명
