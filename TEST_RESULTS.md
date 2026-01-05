# API 테스트 결과

## 배포 정보

- **URL**: https://orthocare-production-7b4d.up.railway.app
- **Swagger UI**: https://orthocare-production-7b4d.up.railway.app/docs
- **테스트 일시**: 2026-01-05

## 테스트 결과

### 1. 헬스 체크

**요청:**
```http
GET /health
```

**결과:** ✅ 성공 (200)

**응답:**
```json
{
  "status": "healthy",
  "service": "gateway",
  "timestamp": "2026-01-05T07:16:26.309280"
}
```

---

### 2. 최소 요청 테스트 (버킷 추론만)

**요청:**
```http
POST /api/v1/diagnose-and-recommend
```

**페이로드:**
```json
{
  "user_id": "test_user_001",
  "demographics": {
    "age": 55,
    "sex": "female",
    "height_cm": 160,
    "weight_kg": 65
  },
  "body_parts": [{
    "code": "knee",
    "primary": true,
    "side": "both",
    "symptoms": ["pain_bilateral", "chronic", "stairs_down", "stiffness_morning"],
    "nrs": 6,
    "red_flags_checked": []
  }],
  "natural_language": {
    "chief_complaint": "양쪽 무릎이 아프고 계단 내려갈 때 힘들어요",
    "pain_description": "아침에 뻣뻣하고 30분 정도 지나면 나아져요",
    "history": "5년 전부터 서서히 심해짐"
  },
  "options": {
    "include_exercises": false
  }
}
```

**결과:** ❌ 실패 (500)

**에러:**
```json
{
  "detail": "처리 실패: Connection error."
}
```

---

### 3. Swagger 예시 요청 (전체 필드)

**요청:**
```http
POST /api/v1/diagnose-and-recommend
```

**페이로드:**
```json
{
  "user_id": "user_123",
  "demographics": {
    "age": 55,
    "sex": "male",
    "height_cm": 175,
    "weight_kg": 80
  },
  "body_parts": [{
    "code": "knee",
    "primary": true,
    "side": "left",
    "symptoms": ["pain_medial", "stiffness_morning"],
    "nrs": 6,
    "red_flags_checked": []
  }],
  "physical_score": {
    "total_score": 12
  },
  "options": {
    "include_exercises": true,
    "exercise_days": 3,
    "skip_exercise_on_red_flag": true
  }
}
```

**결과:** ❌ 실패 (500)

**에러:**
```json
{
  "detail": "처리 실패: Connection error."
}
```

---

### 4. 진단만 실행

**요청:**
```http
POST /api/v1/diagnose
```

**페이로드:**
```json
{
  "user_id": "test_user_002",
  "demographics": {
    "age": 55,
    "sex": "female",
    "height_cm": 160,
    "weight_kg": 65
  },
  "body_parts": [{
    "code": "knee",
    "symptoms": ["pain_medial", "stiffness_morning"],
    "nrs": 6
  }]
}
```

**결과:** ❌ 실패 (500)

**에러:**
```json
{
  "detail": "처리 실패: Connection error."
}
```

---

## 요약

| 테스트 항목 | 결과 | 상태 코드 | 메모 |
|------------|------|----------|------|
| 헬스 체크 | ✅ 성공 | 200 | 게이트웨이 서비스 정상 |
| 최소 요청 (올바른 값) | ❌ 실패 | 500 | Connection error |
| Swagger 예시 (string 값) | ❌ 실패 | 422 | Validation Error (정상 - 잘못된 입력값) |
| 진단만 실행 (올바른 값) | ❌ 실패 | 500 | Connection error |

**최신 테스트 (2026-01-05):**
- ✅ 헬스 체크: 정상
- ❌ API 요청: 여전히 Connection error 발생 (환경 변수 문제로 추정)
- ✅ 422 Validation Error: API 검증 정상 작동 확인 (Swagger Example Value 문제)

## 문제 분석

### 발생한 문제
모든 API 요청에서 "Connection error" 발생

### 코드 구조 분석

게이트웨이는 **HTTP로 내부 서비스를 호출하지 않습니다**. 대신 Python 파이프라인 클래스를 직접 import해서 사용합니다:

```python
# gateway/services/orchestrator.py
from bucket_inference.pipeline import BucketInferencePipeline
from exercise_recommendation.pipeline import ExerciseRecommendationPipeline

self.bucket_pipeline = LangGraphBucketInferencePipeline()
self.exercise_pipeline = ExerciseRecommendationPipeline()
```

### 가능한 원인

"Connection error"는 외부 서비스 연결 문제일 가능성이 높습니다:

1. **Pinecone 연결 실패** ⚠️ 가장 가능성 높음
   - `PINECONE_API_KEY` 환경 변수 미설정
   - Pinecone 인덱스 접근 권한 문제
   - 네트워크 연결 문제

2. **OpenAI API 연결 실패**
   - `OPENAI_API_KEY` 환경 변수 미설정
   - API 키 유효하지 않음
   - 네트워크 연결 문제

3. **환경 변수 미설정**
   - Railway 배포 환경에서 필요한 환경 변수가 설정되지 않음
   - `.env` 파일이 Railway에 업로드되지 않음

### 권장 조치

1. **Railway 대시보드 확인**
   - 모든 서비스 상태 확인 (gateway, bucket_inference, exercise_recommendation)
   - 서비스 로그 확인

2. **환경 변수 확인**
   - 게이트웨이의 내부 서비스 URL 설정 확인
   - Railway Service URL 또는 Private Network 설정 확인

3. **로그 분석**
   - Railway 대시보드에서 게이트웨이 로그 확인
   - "Connection error"의 구체적인 원인 파악

## 참고

- 테스트 스크립트: `test_railway_api.py`
- 관련 문서: `API_ANALYSIS_REPORT.md`, `API_FAQ.md`, `SWAGGER_TEST_GUIDE.md`

