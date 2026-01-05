# 게이트웨이 API 분석 리포트

## 요약

1. **증상 코드 변환**: ✅ 맞습니다. 설문 응답(Q1, Q2 등)이 `survey_mapping.json`에 따라 증상 코드로 변환됩니다.
2. **추가 필드 설명**: `physical_score`, `raw_survey_responses`, `options`는 게이트웨이 통합 API의 선택 필드입니다.
3. **게이트웨이 배포**: ✅ 게이트웨이 하나로 통합 API 사용 가능 (버킷 추론 + 운동 추천)
4. **버킷 추론 사용 시점**: 서비스 이용 초기 + 부위 변경/증상 재설명 시

---

## 0. 버킷 추론 사용 시점

### 서비스 이용 패턴

1. **초기 설문 (버킷 추론 실행)**
   - 사용자가 서비스를 처음 이용할 때
   - 증상 설문을 기반으로 버킷 추론 실행
   - 결과에 맞춰 초기 운동 커리큘럼 추천

2. **운동 커리큘럼 반복 추천**
   - 버킷 추론 결과를 기반으로
   - 매일 또는 정기적으로 운동 커리큘럼 추천
   - 이 단계에서는 버킷 추론 없이 운동 추천만 실행

3. **버킷 추론 재실행**
   - 사용자가 부위를 변경할 때 (예: 무릎 → 어깨)
   - 증상에 대해 다시 설명할 때
   - 새로운 증상이 발생했을 때

### API 호출 패턴

```
초기 설문 → POST /api/v1/diagnose-and-recommend (버킷 추론 + 운동 추천)
    ↓
운동 커리큘럼 반복 추천 → POST /api/v1/recommend-exercises (운동 추천만, 버킷 추론 없음)
    ↓
부위 변경/증상 재설명 → POST /api/v1/diagnose-and-recommend (버킷 추론 + 운동 추천)
```

---

## 1. 증상 코드 변환 방식

### 설문 응답 → 증상 코드 변환

앱에서 사용자가 설문에 답하면:

```
사용자 선택 (텍스트/선택지)
    ↓
survey_mapping.json (매핑 규칙)
    ↓
증상 코드 (symptom_codes) 배열
    ↓
API 요청의 body_parts[].symptoms 필드
```

**예시:**
- 사용자가 "무릎 안쪽" 선택 → `pain_medial` 코드
- "서서히 시작" 선택 → `chronic` 코드
- "계단 내려갈 때" 선택 → `stairs_down` 코드

**참고 파일:**
- `data/medical/knee/survey_mapping.json`
- `data/medical/shoulder/survey_mapping.json`

**결론**: ✅ 맞습니다. 텍스트/선택지를 증상 코드로 변환해서 `symptoms` 배열에 넣습니다.

---

## 2. README vs Swagger 스키마 비교

### 2.1 버킷 추론 API (README 기준)

**엔드포인트**: `POST /api/v1/infer-bucket` (port 8001)

**요청 필드 (최소)**:
```json
{
  "demographics": {...},
  "body_parts": [{
    "code": "knee",
    "symptoms": ["pain_medial", "stiffness_morning"],
    "nrs": 6
  }],
  "natural_language": {...}  // 선택
}
```

**필수 필드**:
- `demographics`
- `body_parts`
- `natural_language` (선택)

**없는 필드**:
- ❌ `physical_score`
- ❌ `raw_survey_responses`
- ❌ `options`
- ❌ `request_id`
- ❌ `user_id`

### 2.2 게이트웨이 통합 API (Swagger 기준)

**엔드포인트**: `POST /api/v1/diagnose-and-recommend` (port 8000)

**요청 필드 (전체)**:
```json
{
  "request_id": "uuid-xxx",  // 자동 생성 (Optional)
  "user_id": "user_123",     // 필수
  "demographics": {...},     // 필수
  "body_parts": [{...}],     // 필수
  "physical_score": {...},   // Optional (운동 추천 시 필요)
  "natural_language": {...}, // Optional
  "raw_survey_responses": {...}, // Optional (백엔드 저장용)
  "options": {...}           // Optional (기본값 있음)
}
```

**필수 필드**:
- `user_id`
- `demographics`
- `body_parts`

**선택 필드**:
- `request_id` (자동 생성)
- `physical_score` (운동 추천 시 필요)
- `natural_language` (선택)
- `raw_survey_responses` (백엔드 저장용)
- `options` (기본값: `{"include_exercises": true, ...}`)

---

## 3. 추가 필드 설명

### 3.1 `physical_score`

**용도**: 운동 추천 시 신체 능력 평가 (사전 평가 4문항 총점)

**필요 시점**: 
- ✅ 운동 추천 포함 시 (`options.include_exercises = true`)
- ❌ 버킷 추론만 할 때는 불필요

**코드 확인**:
```python
# gateway/services/orchestrator.py:188-199
physical_score = request.physical_score
if physical_score is None:
    # NRS 기반 기본 레벨 추정 (폴백)
    nrs = request.primary_nrs
    if nrs >= 7:
        physical_score = PhysicalScore(total_score=6)  # Level D
    # ...
```

**결론**: Optional이지만, 운동 추천 시 제공하면 더 정확합니다. 없으면 NRS 기반으로 추정합니다.

### 3.2 `raw_survey_responses`

**용도**: 백엔드 저장용 원본 설문 응답

**필요 시점**:
- ✅ 백엔드에서 사용자 프로필에 저장할 때
- ❌ 버킷 추론/운동 추천 로직에는 불필요

**코드 확인**:
```python
# gateway/models/unified.py:108-122
class SurveyData(BaseModel):
    """원본 설문 데이터 (백엔드 저장용)"""
    raw_responses: Optional[Dict[str, Any]] = Field(
        default=None,
        description="앱 설문 원본 응답 (key-value)"
    )
```

**결론**: Optional, 백엔드 저장용입니다. 버킷 추론에는 사용되지 않습니다.

### 3.3 `options`

**용도**: 요청 옵션 설정

**필요 시점**: 
- ✅ 운동 추천 포함 여부 등 제어
- ✅ 기본값 있음 (`include_exercises: true`)

**코드 확인**:
```python
# gateway/models/unified.py:27-42
class RequestOptions(BaseModel):
    include_exercises: bool = Field(default=True, ...)
    exercise_days: int = Field(default=3, ...)
    skip_exercise_on_red_flag: bool = Field(default=True, ...)
```

**결론**: Optional, 기본값이 있어서 생략 가능합니다.

### 3.4 `natural_language`

**용도**: 자연어 입력 (주호소, 통증 설명, 병력)

**필요 시점**:
- ✅ 버킷 추론의 보조 정보 (선택)
- ✅ LLM 추론 시 참고

**결론**: Optional, 있으면 더 정확한 추론이 가능합니다.

---

## 4. 게이트웨이 배포로 해결되는가?

### ✅ 네, 게이트웨이 하나로 해결 가능합니다.

**이유**:
1. 게이트웨이 API가 버킷 추론 + 운동 추천을 통합 처리
2. 개별 서비스(8001, 8002)는 내부적으로 호출됨
3. 앱은 게이트웨이(8000)만 호출하면 됨

**아키텍처**:
```
앱 → Gateway (8000) → Bucket Inference (8001) + Exercise Recommendation (8002)
```

**사용 방법**:
- **초기 설문 (버킷 추론 + 운동 추천)**: `POST /api/v1/diagnose-and-recommend`
  - `options.include_exercises = true`
  - `physical_score` 제공 (선택)
- **버킷 추론만**: `POST /api/v1/diagnose` 또는 `include_exercises = false`
  - `physical_score` 불필요

---

## 5. 권장 사항

### 5.1 최소 요청 (버킷 추론만)

```json
{
  "user_id": "user_123",
  "demographics": {"age": 55, "sex": "female", "height_cm": 160, "weight_kg": 65},
  "body_parts": [{
    "code": "knee",
    "symptoms": ["pain_medial", "stiffness_morning"],
    "nrs": 6
  }],
  "options": {
    "include_exercises": false
  }
}
```

### 5.2 전체 요청 (버킷 추론 + 운동 추천)

```json
{
  "user_id": "user_123",
  "demographics": {"age": 55, "sex": "female", "height_cm": 160, "weight_kg": 65},
  "body_parts": [{
    "code": "knee",
    "symptoms": ["pain_medial", "stiffness_morning"],
    "nrs": 6
  }],
  "physical_score": {"total_score": 12},
  "natural_language": {
    "chief_complaint": "무릎이 아파요"
  },
  "options": {
    "include_exercises": true,
    "exercise_days": 3
  }
}
```

---

## 6. 확인 필요 사항

1. **배포 URL**: 실제 배포된 게이트웨이 URL 확인 필요
2. **테스트**: Swagger에서 최소 요청으로 테스트해보기
3. **에러 메시지**: 구체적인 에러 메시지 확인 필요

---

## 7. 버킷 추론 로직에서 실제 사용되는 필드 (코드 레벨 검증)

### 코드 검증 결과

```python
# gateway/services/orchestrator.py:166-173
def _build_bucket_input(self, request: UnifiedRequest) -> BucketInferenceInput:
    """버킷 추론 입력 생성"""
    return BucketInferenceInput(
        demographics=request.demographics,        # ✅ 사용됨
        body_parts=request.body_parts,            # ✅ 사용됨
        natural_language=request.natural_language, # ✅ 사용됨 (선택)
        survey_responses=request.raw_survey_responses, # ⚠️ 전달되지만 실제 사용 안 함
    )
    # ❌ physical_score는 전달되지 않음 (버킷 추론 입력에 없음)
```

### 실제 사용되는 필드

| 필드 | 버킷 추론 로직 사용 여부 | 용도 |
|------|----------------------|------|
| `demographics` | ✅ 사용 | 가중치 계산, 검색 쿼리 구성 |
| `body_parts` | ✅ 사용 | 가중치 계산, 검색 쿼리 구성 |
| `natural_language` | ✅ 사용 | 검색 쿼리 보강 (선택) |
| `physical_score` | ❌ **미사용** | 운동 추천에서만 사용 |
| `raw_survey_responses` | ❌ **미사용** | 디버깅용 (실제 로직 미사용) |
| `options` | ❌ **미사용** | 게이트웨이 레벨 제어용 |

**결론**: 초반 설문 기반 버킷 추론에서 `physical_score`, `raw_survey_responses`, `options`는 실제로 버킷 추론 로직에 사용되지 않습니다. 모두 Optional 필드이므로 생략 가능합니다.

---

## 8. 배포 정보

### Railway 배포 URL

- **Swagger UI**: https://orthocare-production-7b4d.up.railway.app/docs
- **API Base URL**: https://orthocare-production-7b4d.up.railway.app
- **Health Check**: https://orthocare-production-7b4d.up.railway.app/health
- **통합 API**: https://orthocare-production-7b4d.up.railway.app/api/v1/diagnose-and-recommend

### API 테스트 결과 (2026-01-05)

#### 테스트 실행
```bash
python test_railway_api.py https://orthocare-production-7b4d.up.railway.app
```

#### 결과
- ✅ **헬스 체크**: 성공 (200)
- ❌ **최소 요청**: 실패 (500 - Connection error)
- ❌ **Swagger 예시**: 실패 (500 - Connection error)
- ❌ **진단만 실행**: 실패 (500 - Connection error)

#### 테스트 결과 업데이트 (2026-01-05)

**422 Validation Error 발견:**
- Swagger Example Value를 그대로 사용하면 422 에러 발생
- `"code": "string"` → 실제 부위 코드(`"knee"`, `"shoulder"` 등)로 변경 필요
- `"symptoms": ["string"]` → 실제 증상 코드 배열로 변경 필요

**해결 방법:**
- Swagger UI에서 Example Value를 실제 값으로 수정해서 사용
- 또는 `SWAGGER_QUICK_START.md`의 예시 사용

**참고:**
- 실제 422 에러는 정상적인 검증 에러 (잘못된 입력값)
- 500 Connection Error는 환경 변수(Pinecone, OpenAI) 문제일 가능성 높음
- 상세 가이드: `SWAGGER_QUICK_START.md`, `RAILWAY_DEPLOYMENT_CHECKLIST.md`

---

## 9. 다음 단계

1. ✅ 배포된 게이트웨이 URL 확인 (Railway)
2. 최소 요청으로 테스트
3. 에러 발생 시 에러 메시지 확인
4. 필요시 코드 수정 (현재는 Optional 필드들이므로 문제 없어야 함)

