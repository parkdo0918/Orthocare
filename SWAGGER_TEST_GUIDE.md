# Swagger 테스트 가이드

## 배포 정보

### Railway 배포 URL

- **Swagger UI**: https://orthocare-production-7b4d.up.railway.app/docs
- **API Base URL**: https://orthocare-production-7b4d.up.railway.app
- **Health Check**: https://orthocare-production-7b4d.up.railway.app/health
- **통합 API**: https://orthocare-production-7b4d.up.railway.app/api/v1/diagnose-and-recommend

---

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

## 실제 배포된 API 테스트 방법

### 1. 최소 요청 테스트 (버킷 추론만)

Swagger UI에서 다음 요청으로 테스트하세요:

```json
{
  "user_id": "test_user_001",
  "demographics": {
    "age": 55,
    "sex": "female",
    "height_cm": 160,
    "weight_kg": 65
  },
  "body_parts": [
    {
      "code": "knee",
      "primary": true,
      "side": "both",
      "symptoms": ["pain_medial", "stiffness_morning"],
      "nrs": 6,
      "red_flags_checked": []
    }
  ],
  "options": {
    "include_exercises": false
  }
}
```

**예상 결과**: 
- ✅ 성공 시: `status: "success"`, `exercise_plan: null`
- ❌ 실패 시: 422 Validation Error 또는 500 Internal Server Error

---

### 2. 전체 필드 요청 (운동 추천 포함)

```json
{
  "user_id": "test_user_002",
  "demographics": {
    "age": 55,
    "sex": "male",
    "height_cm": 175,
    "weight_kg": 80
  },
  "body_parts": [
    {
      "code": "knee",
      "primary": true,
      "side": "left",
      "symptoms": ["pain_medial", "stiffness_morning"],
      "nrs": 6,
      "red_flags_checked": []
    }
  ],
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

**예상 결과**:
- ✅ 성공 시: `status: "success"`, `exercise_plan` 포함
- ⚠️ Red Flag 시: `status: "partial"`, `exercise_plan: null`, `message`에 경고

---

### 3. Swagger Example Value 수정해서 테스트

⚠️ **중요**: Swagger의 "Example Value"는 placeholder이므로 실제 값으로 변경해야 합니다!

#### 잘못된 예시 (에러 발생)

```json
{
  "code": "string",  // ❌ "string"은 실제 값이 아닙니다!
  "symptoms": ["string"]  // ❌ 실제 증상 코드를 입력해야 합니다!
}
```

**에러 메시지:**
```json
{
  "detail": [{
    "type": "value_error",
    "loc": ["body", "body_parts", 0, "code"],
    "msg": "Value error, 지원하지 않는 부위: string. 가능한 값: ['knee', 'shoulder', 'back', 'neck', 'ankle']"
  }]
}
```

#### 올바른 예시

Swagger Example Value를 다음처럼 수정해서 사용:

```json
{
  "user_id": "test_user_003",
  "demographics": {
    "age": 55,
    "sex": "male",
    "height_cm": 175,
    "weight_kg": 80
  },
  "body_parts": [
    {
      "code": "knee",  // ✅ 실제 부위 코드
      "primary": true,
      "side": "left",
      "symptoms": ["pain_medial", "stiffness_morning"],  // ✅ 실제 증상 코드
      "nrs": 6,
      "red_flags_checked": []
    }
  ],
  "physical_score": {
    "total_score": 12
  },
  "natural_language": {
    "chief_complaint": "무릎이 아파요",
    "pain_description": "아침에 뻣뻣하고 30분 정도 지나면 나아져요",
    "history": "5년 전부터 서서히 심해짐"
  },
  "options": {
    "include_exercises": true,
    "exercise_days": 3,
    "skip_exercise_on_red_flag": true
  }
}
```

**변경 사항:**
- `"code": "string"` → `"code": "knee"` (또는 "shoulder", "back", "neck", "ankle")
- `"symptoms": ["string"]` → `"symptoms": ["pain_medial", "stiffness_morning"]`
- `"user_id": "string"` → `"user_id": "test_user_003"`
- `"chief_complaint": "string"` → 실제 문장으로 변경

---

## 필드별 필수/선택 여부

| 필드 | 필수 | 기본값 | 설명 |
|------|------|--------|------|
| `user_id` | ✅ 필수 | - | 사용자 ID |
| `demographics` | ✅ 필수 | - | 인구통계 정보 |
| `body_parts` | ✅ 필수 | - | 부위별 증상 (최소 1개) |
| `request_id` | ❌ 선택 | 자동 생성 | 요청 ID (생략 가능) |
| `physical_score` | ❌ 선택 | `null` | 신체 점수 (운동 추천 시 권장) |
| `natural_language` | ❌ 선택 | `null` | 자연어 입력 (선택) |
| `raw_survey_responses` | ❌ 선택 | `null` | 원본 설문 (백엔드 저장용) |
| `options` | ❌ 선택 | 기본값 있음 | 옵션 설정 |

---

## 오류 발생 시 확인 사항

### 422 Validation Error

**원인**: 필수 필드 누락 또는 타입 오류

**확인**:
1. `user_id`가 문자열인가?
2. `demographics.age`가 10-100 범위인가?
3. `demographics.height_cm`가 100-250 범위인가?
4. `demographics.weight_kg`가 30-200 범위인가?
5. `body_parts[].nrs`가 0-10 범위인가?
6. `body_parts[].code`가 유효한 값인가? (`knee`, `shoulder`, `back`, `neck`, `ankle`)

### 500 Internal Server Error

**원인**: 서버 내부 오류

**확인**:
1. 로그 확인 (Railway 대시보드)
2. 환경 변수 설정 확인 (OPENAI_API_KEY, PINECONE_API_KEY 등)
3. 의존 서비스 상태 확인

---

## 코드 레벨 검증 결과

로컬 코드 검증 결과:

```python
# ✅ 최소 요청 (physical_score 없음): 성공
UnifiedRequest(
    user_id='test',
    demographics={...},
    body_parts=[...],
    options=RequestOptions(include_exercises=False)
)

# ✅ options 없이 요청: 성공 (기본값 사용)
UnifiedRequest(
    user_id='test',
    demographics={...},
    body_parts=[...]
)
```

**결론**: 코드 레벨에서는 모든 Optional 필드가 정상적으로 처리됩니다.

---

## 실제 테스트 권장 사항

1. **최소 요청부터 시작**: 가장 간단한 요청으로 기본 동작 확인
2. **단계별 추가**: 필드를 하나씩 추가하며 테스트
3. **에러 메시지 확인**: 422 에러 시 `detail` 필드의 구체적인 에러 메시지 확인
4. **로그 확인**: Railway 대시보드에서 서버 로그 확인

---

## 참고 문서

- `API_ANALYSIS_REPORT.md` - 상세 분석 리포트
- `API_FAQ.md` - 질문과 답변
- `test_railway_api.py` - 자동 테스트 스크립트

