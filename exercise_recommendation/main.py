"""Exercise Recommendation FastAPI 서버

Docker Container 2: 운동 추천 모델
포트: 8002 (외부) → 8000 (내부)
"""

import os
from dotenv import load_dotenv
load_dotenv(override=True)

# LangSmith 프로젝트 분리
os.environ["LANGSMITH_PROJECT"] = "orthocare-exercise-recommendation"

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from exercise_recommendation.models import (
    ExerciseRecommendationInput,
    ExerciseRecommendationOutput,
)
from exercise_recommendation.pipeline import ExerciseRecommendationPipeline
from exercise_recommendation.config import settings

app = FastAPI(
    title="OrthoCare Exercise Recommendation",
    description="운동 추천 모델 API (매일 사용)",
    version="1.0.0",
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 파이프라인 인스턴스
pipeline = ExerciseRecommendationPipeline()


@app.get("/health")
async def health_check():
    """헬스 체크"""
    return {"status": "healthy", "service": "exercise-recommendation"}


@app.post("/api/v1/recommend-exercises", response_model=ExerciseRecommendationOutput)
async def recommend_exercises(input_data: ExerciseRecommendationInput):
    """
    운동 추천 API

    사용 빈도: 매일

    입력:
    - user_id: 사용자 ID
    - body_part: 부위 코드
    - bucket: 진단 버킷 (버킷 추론 결과)
    - physical_score: 신체 점수
    - demographics: 인구통계 정보
    - nrs: 통증 점수
    - previous_assessments: 사후 설문 기록 (선택)
    - last_assessment_date: 마지막 설문 날짜 (선택)

    출력:
    - exercises: 추천 운동 목록
    - adjustments_applied: 적용된 조정
    - assessment_status: 사후 설문 처리 상태
    """
    try:
        result = pipeline.run(input_data)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "exercise_recommendation.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
