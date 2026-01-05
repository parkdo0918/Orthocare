# 최신 테스트 결과 (2026-01-05)

## 테스트 환경

- **URL**: https://orthocare-production-7b4d.up.railway.app
- **테스트 시간**: 2026-01-05 02:26 EST
- **테스트 방법**: `python test_railway_api.py` 스크립트

---

## 테스트 1: 헬스 체크

```bash
curl -X GET https://orthocare-production-7b4d.up.railway.app/health
```

**결과:** ✅ 성공 (200)

**응답:**
```json
{
  "status": "healthy",
  "service": "gateway",
  "timestamp": "2026-01-05T07:26:03.526535"
}
```

**결론:** 게이트웨이 서비스 자체는 정상 작동 중

---

## 테스트 2: 최소 요청 (올바른 값)

```bash
curl -X POST https://orthocare-production-7b4d.up.railway.app/api/v1/diagnose-and-recommend \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test_manual_001",
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
      "symptoms": ["pain_medial", "stiffness_morning"],
      "nrs": 6,
      "red_flags_checked": []
    }],
    "options": {
      "include_exercises": false
    }
  }'
```

**결과:** ❌ 실패 (500)

**응답:**
```json
{
  "detail": "처리 실패: Connection error."
}
```

**분석:**
- 입력값은 올바름 (422 에러 아님)
- API 검증 통과
- 서버 내부에서 Connection error 발생
- Pinecone 또는 OpenAI API 연결 문제로 추정

---

## 테스트 3: Swagger 예시 요청 (전체 필드)

```bash
curl -X POST https://orthocare-production-7b4d.up.railway.app/api/v1/diagnose-and-recommend \
  -H "Content-Type: application/json" \
  -d '{
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
  }'
```

**결과:** ❌ 실패 (500)

**응답:**
```json
{
  "detail": "처리 실패: Connection error."
}
```

**분석:**
- 입력값은 올바름 (422 에러 아님)
- API 검증 통과
- 서버 내부에서 Connection error 발생

---

## 테스트 4: 진단만 실행 (/api/v1/diagnose)

```bash
curl -X POST https://orthocare-production-7b4d.up.railway.app/api/v1/diagnose \
  -H "Content-Type: application/json" \
  -d '{
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
  }'
```

**결과:** ❌ 실패 (500)

**응답:**
```json
{
  "detail": "처리 실패: Connection error."
}
```

---

## 결론

### 정상 작동하는 부분

1. ✅ **게이트웨이 서비스**: 헬스 체크 정상
2. ✅ **API 검증**: 입력값 검증 정상 작동 (422 에러 정확히 반환)
3. ✅ **에러 처리**: 명확한 에러 메시지 제공

### 문제가 있는 부분

1. ❌ **외부 서비스 연결**: Pinecone 또는 OpenAI API 연결 실패
   - 모든 API 요청에서 "Connection error" 발생
   - 환경 변수 미설정 또는 네트워크/키 문제 가능성 높음

### 해결 방법

Railway 대시보드에서 다음 환경 변수 확인:

1. `OPENAI_API_KEY` - OpenAI API 키
2. `PINECONE_API_KEY` - Pinecone API 키

환경 변수가 설정되어 있으면:
- Railway 로그 확인 (더 자세한 에러 메시지)
- API 키 유효성 확인
- 네트워크 연결 상태 확인

---

## 참고 문서

- `RAILWAY_DEPLOYMENT_CHECKLIST.md` - 환경 변수 설정 가이드
- `SWAGGER_QUICK_START.md` - 올바른 요청 예시
- `TEST_RESULTS.md` - 이전 테스트 결과
