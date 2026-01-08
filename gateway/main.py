"""Gateway Service - 통합 API 서버

사용법:
    PYTHONPATH=. python -m gateway.main

포트: 8000 (기본)
"""

from contextlib import asynccontextmanager
from datetime import datetime
import os

from dotenv import load_dotenv
load_dotenv(override=True)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from gateway.models import UnifiedRequest, UnifiedResponse
from gateway.services import OrchestrationService
from exercise_recommendation.models.input import ExerciseRecommendationInput
from exercise_recommendation.models.output import ExerciseRecommendationOutput


# 오케스트레이션 서비스 (싱글톤)
orchestration_service: OrchestrationService = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 라이프사이클 관리"""
    global orchestration_service
    print("Gateway Service 시작 중...")
    orchestration_service = OrchestrationService()
    print("Gateway Service 준비 완료")
    yield
    print("Gateway Service 종료")


app = FastAPI(
    title="Orthocare Gateway API",
    description="버킷 추론 + 운동 추천 통합 API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """헬스 체크"""
    return {
        "status": "healthy",
        "service": "gateway",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post("/api/v1/diagnose-and-recommend", response_model=UnifiedResponse)
async def diagnose_and_recommend(request: UnifiedRequest):
    """통합 API: 버킷 추론 + 운동 추천

    한 번의 요청으로:
    1. 증상 기반 버킷 추론
    2. 버킷 기반 운동 추천 (옵션)
    3. 백엔드 저장용 데이터 반환

    Red Flag 감지 시 운동 추천 자동 스킵

    Request:
    ```json
    {
        "user_id": "user_123",
        "demographics": {"age": 55, "sex": "male", "height_cm": 175, "weight_kg": 80},
        "body_parts": [{"code": "knee", "symptoms": ["pain_medial", "stiffness_morning"], "nrs": 6}],
        "physical_score": {"total_score": 12},
        "options": {"include_exercises": true, "exercise_days": 3}
    }
    ```

    Response:
    - survey_data: 원본 설문 (백엔드 저장용)
    - diagnosis: 버킷 추론 결과
    - exercise_plan: 운동 추천 (red_flag 시 null)
    """
    try:
        result = orchestration_service.process(request)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import traceback
        error_detail = f"{type(e).__name__}: {str(e)}"
        # 디버깅을 위해 더 자세한 에러 정보 포함 (프로덕션에서는 제거 가능)
        raise HTTPException(
            status_code=500,
            detail=f"처리 실패: {error_detail}"
        )


@app.post("/api/v1/recommend-exercises", response_model=ExerciseRecommendationOutput)
async def recommend_exercises(request: ExerciseRecommendationInput):
    """운동 추천만 실행 (버킷 추론 생략)

    앱/백엔드에서 이미 버킷과 사전평가가 있을 때 사용
    """
    try:
        exercise_output = orchestration_service.exercise_pipeline.run(request)
        return exercise_output
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        error_detail = f"{type(e).__name__}: {str(e)}"
        raise HTTPException(
            status_code=500,
            detail=f"처리 실패: {error_detail}"
        )


@app.post("/api/v1/diagnose", response_model=UnifiedResponse)
async def diagnose_only(request: UnifiedRequest):
    """버킷 추론만 실행 (운동 추천 제외)

    운동 추천 없이 버킷 추론 결과만 반환
    """
    try:
        result = orchestration_service.process_diagnosis_only(request)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import traceback
        error_detail = f"{type(e).__name__}: {str(e)}"
        # 디버깅을 위해 더 자세한 에러 정보 포함 (프로덕션에서는 제거 가능)
        raise HTTPException(
            status_code=500,
            detail=f"처리 실패: {error_detail}"
        )


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("GATEWAY_HOST", "0.0.0.0")
    port = int(os.getenv("GATEWAY_PORT", "8000"))

    print(f"Gateway Service 시작: http://{host}:{port}")
    uvicorn.run(
        "gateway.main:app",
        host=host,
        port=port,
        reload=True,
    )
