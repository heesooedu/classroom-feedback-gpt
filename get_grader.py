import os
import json
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI

# .env 로드 (OPENAI_API_KEY, GPT_MODEL 등)
load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 기본 사용할 채점용 모델 이름 (없으면 gpt-4.1-mini 사용)
DEFAULT_GPT_MODEL = os.getenv("GPT_MODEL", "gpt-4.1-mini")


def build_grading_messages(problem, code: str, student_label: str):
    """
    GPT에게 전달할 system / user 메시지를 구성한다.
    여기 system_prompt 안에 '정답 코드 직접 제공 금지' 등 정책을 넣는다.
    """
    system_prompt = """
당신은 고등학교 파이썬 기초 문법 과제를 채점하는 조교입니다.
학생의 코드를 실행하지 않고, 정적 분석과 문제 요구사항을 기준으로 채점합니다.

[역할 / 원칙]
- 점수는 0에서 max_score 사이의 정수로 평가합니다.
- 출력이 요구사항과 거의 맞지만 사소한 오류(띄어쓰기, 따옴표 등)가 있으면 약간 감점합니다.
- 문법 오류나 실행 불가능한 코드는 크게 감점합니다.
- 피드백은 한국어로, 친절하고 구체적으로 작성합니다.
- 학생이 스스로 생각해 볼 수 있도록, "정답 코드 전체"를 그대로 제공하지 않습니다.
- 필요한 경우, 짧은 코드 조각(한두 줄)이나 의사코드는 허용되지만,
  "정답은 아래와 같습니다:"와 같이 완전한 정답 코드를 제시하지 않습니다.
- 학생의 현재 코드를 바탕으로 무엇이 잘못되었는지, 어떻게 수정하면 좋을지 설명하는 데 집중합니다.

[출력 형식]
- 반드시 JSON 형식으로만 응답해야 합니다.
- JSON 바깥에 다른 설명 텍스트를 절대 쓰지 않습니다.
"""

    user_prompt = f"""
[문제 정보]
- 제목: {problem.title}
- 설명: {problem.description}

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

위 정보를 바탕으로 아래 JSON 스키마에 맞게 채점 결과를 반환하세요.

- score: 점수 (0 ~ max_score 정수)
- max_score: 만점 (정수)
- feedback: 학생에게 보여줄 구체적인 피드백 (한국어, 여러 줄 가능)
- summary: 교사용 짧은 요약 (한두 문장)

JSON 예시:
{{
  "score": 8,
  "max_score": 10,
  "feedback": "print 문 끝에 괄호를 닫지 않았습니다. 문제에서 요구한 문장을 그대로 출력하세요.",
  "summary": "출력 문법은 이해했으나, 세부 문법 오류로 감점."
}}
"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def grade_with_gpt(
    problem,
    code: str,
    student_label: str,
    model_name: Optional[str] = None,
):
    """
    문제 + 학생 코드 + 학생 라벨을 받아 GPT로 채점하고
    점수/피드백/요약을 dict로 반환한다.
    """
    model = model_name or DEFAULT_GPT_MODEL
    messages = build_grading_messages(problem, code, student_label)

    try:
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.0,
        )

        raw_content = completion.choices[0].message.content or "{}"

        try:
            data = json.loads(raw_content)
        except json.JSONDecodeError:
            # 혹시 JSON 형식이 살짝 틀어졌을 때 대비
            print("GPT 응답 JSON 파싱 실패, 원본:", raw_content)
            raise

        score = int(data.get("score", 0))
        # Problem 모델에 max_score 필드가 있다고 가정, 없으면 기본 10점
        max_score = int(data.get("max_score", getattr(problem, "max_score", 10) or 10))
        feedback = data.get("feedback", "").strip()
        summary = data.get("summary", "").strip()

        return {
            "score": score,
            "max_score": max_score,
            "feedback": feedback,
            "summary": summary,
            "model": model,
        }

    except Exception as e:
        # 서버 콘솔에는 에러 내용을 찍어두고,
        # 학생 화면에는 공손한 실패 메시지를 돌려준다.
        print("GPT 채점 중 오류:", e)

        fallback_max = getattr(problem, "max_score", 10) or 10

        return {
            "score": 0,
            "max_score": fallback_max,
            "feedback": "자동 채점에 실패했습니다. 선생님께 문의하세요.",
            "summary": f"자동 채점 실패: {e}",
            "model": model,
        }
