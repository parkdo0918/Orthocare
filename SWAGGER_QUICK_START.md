# Swagger 빠른 시작 가이드

## ⚠️ 중요: Swagger Example Value는 실제 값으로 변경해야 합니다!

Swagger UI의 "Example Value"는 **placeholder**입니다. 그대로 사용하면 422 Validation Error가 발생합니다.

---

## 빠른 테스트 (Copy & Paste)

### 1. 최소 요청 (버킷 추론만)

Swagger UI에서 다음 JSON을 복사해서 사용:

```json
{
  "user_id": "test_001",
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

### 2. 전체 필드 요청 (운동 추천 포함)

```json
{
  "user_id": "test_002",
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

---

## 주요 필드 설명

### body_parts[].code

**지원하는 값:**
- `"knee"` - 무릎
- `"shoulder"` - 어깨
- `"back"` - 등
- `"neck"` - 목
- `"ankle"` - 발목

❌ `"string"` - 사용 불가 (422 에러)

### body_parts[].symptoms

**무릎 증상 코드 예시:**
- `"pain_medial"` - 무릎 안쪽 통증
- `"pain_lateral"` - 무릎 바깥쪽 통증
- `"stiffness_morning"` - 아침 뻣뻣함
- `"chronic"` - 만성
- `"stairs_down"` - 계단 내려갈 때
- `"pain_bilateral"` - 양쪽 무릎 통증

❌ `["string"]` - 사용 불가 (실제 증상 코드를 입력해야 함)

**전체 증상 코드 목록:**
- `data/medical/knee/weights.json` 참고
- `data/medical/shoulder/weights.json` 참고

### demographics

**범위 제한:**
- `age`: 10-100
- `height_cm`: 100-250
- `weight_kg`: 30-200
- `sex`: `"male"` 또는 `"female"`

### physical_score.total_score

**범위:** 4-16

---

## 일반적인 에러

### 422 Validation Error

**원인:** 필드 값이 유효하지 않음

**예시:**
```json
{
  "detail": [{
    "type": "value_error",
    "loc": ["body", "body_parts", 0, "code"],
    "msg": "Value error, 지원하지 않는 부위: string. 가능한 값: ['knee', 'shoulder', 'back', 'neck', 'ankle']"
  }]
}
```

**해결:** `"code": "string"` → `"code": "knee"` 등 실제 값으로 변경

### 500 Internal Server Error

**원인:** 서버 내부 오류 (환경 변수 미설정, 외부 서비스 연결 실패 등)

**해결:** Railway 대시보드에서 로그 확인

---

## 참고

- 배포 URL: https://orthocare-production-7b4d.up.railway.app
- Swagger UI: https://orthocare-production-7b4d.up.railway.app/docs
- 상세 가이드: `SWAGGER_TEST_GUIDE.md`

