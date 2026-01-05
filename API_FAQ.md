# API FAQ - 질문과 답변

## 버킷 추론 사용 시점

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

---

## Q1: 증상(symptoms) 양식은 텍스트를 증상 코드로 바꿔서 넣는 건가요?

### ✅ 네, 맞습니다.

**프로세스:**
1. 사용자가 앱에서 설문에 답변 (예: "무릎 안쪽", "서서히 시작", "계단 내려갈 때")
2. 앱에서 `survey_mapping.json`을 참고하여 증상 코드로 변환
3. API 요청의 `body_parts[].symptoms` 배열에 증상 코드를 넣어서 전송

**예시:**
```json
// 설문 응답
{
  "Q1_location": ["medial", "both"],
  "Q2_onset": ["gradual"],
  "Q4_aggravating": ["stairs_down"]
}

// ↓ 변환 (survey_mapping.json 참고)

// API 요청
{
  "body_parts": [{
    "code": "knee",
    "symptoms": ["pain_medial", "pain_bilateral", "chronic", "stairs_down"],
    "nrs": 6
  }]
}
```

**참고 파일:**
- `data/medical/knee/survey_mapping.json`
- `data/medical/shoulder/survey_mapping.json`

---

## Q2: README와 다르게 추가된 필드들이 왜 필요한가요?

> "초반 설문 기반 버킷추론에서 필요없거나 알수가 없는 항목인거 같은데?"

**답변: ✅ 맞습니다. 버킷 추론 로직에는 실제로 사용되지 않습니다.**

### 코드 레벨 검증

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

### 필드별 설명

#### `physical_score` (Optional)

**용도**: 운동 추천 시 신체 능력 평가

**필요 시점**:
- ✅ 운동 추천 포함 시 (`options.include_exercises = true`)
- ❌ 버킷 추론만 할 때는 불필요 (버킷 추론 로직에서 미사용)

**코드 검증**:
- 버킷 추론 파이프라인에는 `physical_score` 필드가 없음
- 운동 추천에서만 사용됨

**코드 동작**:
```python
# gateway/services/orchestrator.py:188-199
if physical_score is None:
    # NRS 기반으로 기본 레벨 추정 (폴백)
    nrs = request.primary_nrs
    if nrs >= 7:
        physical_score = PhysicalScore(total_score=6)  # Level D
    # ...
```

**결론**: Optional이므로 버킷 추론만 할 때는 생략 가능합니다.

---

#### `raw_survey_responses` (Optional)

**용도**: 백엔드 저장용 원본 설문 응답

**필요 시점**:
- ✅ 백엔드에서 사용자 프로필에 저장할 때
- ❌ 버킷 추론/운동 추천 로직에는 불필요 (버킷 추론 로직에서 미사용)

**코드 검증**:
- `BucketInferenceInput`에는 `survey_responses` 필드가 있지만 "디버깅용"으로만 정의
- 실제 버킷 추론 파이프라인 로직에서는 사용되지 않음

**결론**: Optional, 백엔드 저장용입니다. 버킷 추론 로직에는 사용되지 않습니다.

---

#### `options` (Optional, 기본값 있음)

**용도**: 요청 옵션 설정

**기본값**:
```python
{
    "include_exercises": true,
    "exercise_days": 3,
    "skip_exercise_on_red_flag": true
}
```

**결론**: Optional이지만 기본값이 있어서 생략 가능합니다.

---

#### `natural_language` (Optional)

**용도**: 자연어 입력 (주호소, 통증 설명, 병력)

**필요 시점**:
- ✅ 버킷 추론의 보조 정보 (선택)
- ✅ LLM 추론 시 참고하여 정확도 향상

**코드 검증**:
- 검색 쿼리 구성 시 사용 (`_build_search_query`)
- 있으면 검색 정확도 향상, 없어도 동작

**결론**: Optional, 있으면 더 정확한 추론이 가능합니다.

---

## Q3: 게이트웨이 배포 하나면 다 해결되는가요?

### ✅ 네, 게이트웨이 하나로 해결됩니다.

**아키텍처:**
```
앱
 ↓
Gateway API (8000)  ← 여기만 호출
 ↓
├─ Bucket Inference (8001) [내부 호출]
└─ Exercise Recommendation (8002) [내부 호출]
```

**장점:**
- 앱에서 한 번의 요청으로 버킷 추론 + 운동 추천 완료
- Red Flag 감지 시 운동 추천 자동 스킵
- 원본 설문 데이터를 응답에 포함하여 백엔드 저장 용이

**엔드포인트:**
- `POST /api/v1/diagnose-and-recommend` - 통합 API (권장)
- `POST /api/v1/diagnose` - 버킷 추론만

---

## Q4: 초반 설문 기반 버킷 추론에서 불필요한 필드는?

### 버킷 추론 로직에서 실제 사용되는 필드

| 필드 | 버킷 추론 로직 사용 여부 | 용도 |
|------|----------------------|------|
| `demographics` | ✅ 사용 | 가중치 계산, 검색 쿼리 구성 |
| `body_parts` | ✅ 사용 | 가중치 계산, 검색 쿼리 구성 |
| `natural_language` | ✅ 사용 | 검색 쿼리 보강 (선택) |
| `physical_score` | ❌ **미사용** | 운동 추천에서만 사용 |
| `raw_survey_responses` | ❌ **미사용** | 디버깅용 (실제 로직 미사용) |
| `options` | ❌ **미사용** | 게이트웨이 레벨 제어용 |

**결론**: 초반 설문 기반 버킷 추론에서 `physical_score`, `raw_survey_responses`, `options`는 실제로 버킷 추론 로직에 사용되지 않습니다. 모두 Optional 필드이므로 생략 가능합니다.

### 최소 요청 (버킷 추론만)

```json
{
  "user_id": "user_123",
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
  }],
  "options": {
    "include_exercises": false  // 버킷 추론만
  }
}
```

**생략 가능한 필드:**
- ❌ `physical_score` (운동 추천 시에만 필요)
- ❌ `raw_survey_responses` (백엔드 저장용, 버킷 추론 로직 불필요)
- ❌ `natural_language` (선택, 있으면 정확도 향상)
- ❌ `request_id` (자동 생성)

---

## Q5: README의 버킷 추론 API와 게이트웨이 API의 차이

| 항목 | 버킷 추론 API (README) | 게이트웨이 API (Swagger) |
|------|----------------------|----------------------|
| 엔드포인트 | `POST /api/v1/infer-bucket` (8001) | `POST /api/v1/diagnose-and-recommend` (8000) |
| 용도 | 버킷 추론만 | 버킷 추론 + 운동 추천 통합 |
| 필수 필드 | `demographics`, `body_parts` | `user_id`, `demographics`, `body_parts` |
| 추가 필드 | 없음 | `physical_score`, `options`, `raw_survey_responses` (모두 Optional) |
| 권장 사용 | 개별 서비스 테스트용 | 앱에서 사용 (권장) |

**결론**: 앱에서는 게이트웨이 API를 사용하세요. 모든 추가 필드는 Optional이므로 최소 요청도 작동합니다.

---

## 테스트 방법

### Railway 배포 API 테스트

**배포 URL**: https://orthocare-production-7b4d.up.railway.app

```bash
python test_railway_api.py https://orthocare-production-7b4d.up.railway.app
```

**Swagger UI**: https://orthocare-production-7b4d.up.railway.app/docs

### 최소 요청 테스트 (버킷 추론만)

```bash
curl -X POST "https://your-app.railway.app/api/v1/diagnose-and-recommend" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test_001",
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
    }],
    "options": {
      "include_exercises": false
    }
  }'
```

