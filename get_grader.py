# get_grader.py
import os
import json
from typing import Dict

from dotenv import load_dotenv
from openai import OpenAI

from models import Problem  # 타입 힌트용

# .env 에서 OPENAI_API_KEY 로드
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def build_prompt(problem: Problem, code: str, student_label: str) -> str:
    """
    프롬프트 텍스트만 별도 함수로 분리.
    백틱(``` 같은 것) 없이 그냥 텍스트만 사용해서 복붙 문제 없게 구성.
    """
    return f"""다음은 파이썬 기초 문법 문제와 학생의 제출 코드입니다.

[문제 정보]
제목: {problem.title}
설명: {problem.description}

[예시 입력]
{problem.sample_input or "없음"}

[예시 출력]
{problem.sample_output or "없음"}

[정답 예시 코드]
{problem.answer_code}

[채점 기준 (루브릭)]
{problem.rubric}

[학생 정보]
{student_label}

[학생 제출 코드]
{code}

위 정보를 바탕으로 아래 JSON 스키마에 맞추어 채점 결과를 반환하세요.

- score: 정수 또는 실수, 학생의 점수 (0 ~ max_score)
- max_score: 정수 또는 실수, 만점 기준 (기본 10점)
- feedback: 학생이 이해하기 쉬운 한국어 피드백 (구체적인 수정 방향)
- summary: 짧은 요약 (예: "출력은 맞지만 변수 이름 규칙 위반으로 감점")

반드시 다음과 같이 하나의 JSON 객체만 반환하세요.

예시:
{{"score": 8, "max_score": 10, "feedback": "설명...", "summary": "요약..."}}
"""


def grade_with_gpt(problem: Problem, code: str, student_label: str) -> Dict:
    """
    GPT에게 JSON만 받는 채점 함수.
    실패하면 예외를 던지지 않고 "채점 실패" 정보 포함한 dict 반환.
    """
    system_msg = (
        "당신은 한국의 고등학교 파이썬 교사이자 자동 채점 시스템입니다. "
        "반드시 JSON 형식으로만 응답하세요."
    )

    user_prompt = build_prompt(problem, code, student_label)

    try:
        completion = client.chat.completions.create(
            model="gpt-5.1-mini",  # 필요하면 환경변수로 빼도 됨
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_prompt},
            ],
            # JSON 모드 강제
            response_format={"type": "json_object"},
            temperature=0.0,
        )

        content = completion.choices[0].message.content
        data = json.loads(content)

        score = float(data.get("score", 0))
        max_score = float(data.get("max_score", problem.max_score))
        feedback = data.get("feedback", "피드백 없음.")
        summary = data.get("summary", "요약 없음.")

        return {
            "score": score,
            "max_score": max_score,
            "feedback": feedback,
            "summary": summary,
            "model": completion.model,
        }
    except Exception as e:
        # 서버 콘솔에만 로그
        print("GPT 채점 중 오류:", e)
        return {
            "score": 0,
            "max_score": problem.max_score,
            "feedback": "자동 채점에 실패했습니다. 선생님께 문의하세요.",
            "summary": "자동 채점 오류.",
            "model": None,
        }
