# OrthoCare 백엔드 통합 가이드

> 버전: V3.1 (Gateway Architecture)
> 최종 업데이트: 2025-12-24

---

## 목차

1. [개요](#1-개요)
2. [시스템 아키텍처](#2-시스템-아키텍처)
3. [통합 Gateway API](#3-통합-gateway-api)
4. [데이터 저장 전략](#4-데이터-저장-전략)
5. [개별 서비스 API](#5-개별-서비스-api)
6. [에러 처리](#6-에러-처리)
7. [통합 시나리오](#7-통합-시나리오)
8. [성능 최적화](#8-성능-최적화)

---

## 1. 개요

### 대상 독자
- 백엔드 개발자
- 모바일 앱 개발자
- 시스템 아키텍트

### 핵심 포인트

| 항목 | 설명 |
|------|------|
| **통합 방식** | Gateway API 한 번 호출로 진단 + 운동 추천 완료 |
| **데이터 보존** | 응답에 원본 설문 데이터 포함 → 백엔드 저장 용이 |
| **부분 실패 처리** | Red Flag / 운동 추천 실패 시에도 진단 결과 반환 |
| **호출 빈도** | 버킷 추론: 2주 1회, 운동 추천: 매일 |

---

## 2. 시스템 아키텍처

### 서비스 구성

```
┌─────────────────────────────────────────────────────────────────────┐
│                        클라이언트 (앱/웹)                              │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Gateway Service (port 8000)                      │
│                 POST /api/v1/diagnose-and-recommend                  │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
        ┌───────────────────┐   ┌───────────────────────┐
        │ Bucket Inference  │   │ Exercise Recommendation│
        │   (port 8001)     │   │     (port 8002)        │
        │  2주 1회 호출       │   │   매일 호출             │
        └───────────────────┘   └───────────────────────┘
                    │                       │
                    ▼                       ▼
        ┌───────────────────┐   ┌───────────────────────┐
        │  Pinecone         │   │  Pinecone              │
        │ (diagnosis index) │   │ (exercise index)       │
        └───────────────────┘   └───────────────────────┘
```

### 포트 및 용도

| 서비스 | 포트 | 용도 | 호출 빈도 |
|--------|------|------|----------|
| Gateway | 8000 | 통합 API (권장) | 상황별 |
| Bucket Inference | 8001 | 버킷 추론 전용 | 2주 1회 |
| Exercise Recommendation | 8002 | 운동 추천 전용 | 매일 |

---

## 3. 통합 Gateway API

### 3.1 진단 + 운동 추천 (메인 API)

```http
POST /api/v1/diagnose-and-recommend
Content-Type: application/json
```

#### Request

```json
{
  "request_id": "req_20251224_001",
  "user_id": "user_12345",
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
      "symptoms": [
        "pain_stairs",
        "stiffness_morning",
        "crepitus",
        "pain_bilateral"
      ],
      "nrs": 6,
      "red_flags_checked": []
    }
  ],
  "physical_score": {
    "total_score": 10
  },
  "natural_language": {
    "chief_complaint": "양쪽 무릎이 아프고 계단 내려갈 때 특히 힘들어요",
    "pain_description": "아침에 30분 정도 뻣뻣하다가 나아져요. 오래 앉았다 일어날 때도 아파요.",
    "history": "5년 전부터 조금씩 아팠는데 최근 6개월간 많이 심해졌어요"
  },
  "raw_survey_responses": {
    "Q1": "5년 이상",
    "Q2": "양쪽 무릎",
    "Q3": "계단 내려갈 때, 오래 앉았다 일어날 때",
    "Q4": "아침에 뻣뻣함 (30분 이내)",
    "Q5": "무릎에서 소리남"
  },
  "options": {
    "include_exercises": true,
    "skip_exercise_on_red_flag": true,
    "max_exercises": 5
  }
}
```

#### Request 필드 상세

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `request_id` | string | O | 요청 추적용 ID (백엔드 생성) |
| `user_id` | string | O | 사용자 ID |
| `demographics` | object | O | 인구통계 정보 |
| `body_parts` | array | O | 부위별 증상 (최소 1개) |
| `physical_score` | object | O | 사전 신체 평가 점수 |
| `natural_language` | object | X | 자연어 입력 (선택) |
| `raw_survey_responses` | object | X | 원본 설문 응답 (백엔드 저장용) |
| `options` | object | X | 옵션 설정 |

#### Response

```json
{
  "request_id": "req_20251224_001",
  "user_id": "user_12345",
  "survey_data": {
    "demographics": {
      "age": 55,
      "sex": "female",
      "height_cm": 160,
      "weight_kg": 65,
      "bmi": 25.4
    },
    "body_parts": [
      {
        "code": "knee",
        "primary": true,
        "side": "both",
        "symptoms": ["pain_stairs", "stiffness_morning", "crepitus", "pain_bilateral"],
        "nrs": 6,
        "red_flags_checked": []
      }
    ],
    "natural_language": {
      "chief_complaint": "양쪽 무릎이 아프고 계단 내려갈 때 특히 힘들어요",
      "pain_description": "아침에 30분 정도 뻣뻣하다가 나아져요...",
      "history": "5년 전부터 조금씩 아팠는데 최근 6개월간 많이 심해졌어요"
    },
    "physical_score": {
      "total_score": 10,
      "level": "C"
    },
    "raw_responses": {
      "Q1": "5년 이상",
      "Q2": "양쪽 무릎"
    }
  },
  "diagnosis": {
    "body_part": "knee",
    "bucket": "OA",
    "bucket_name_kr": "퇴행성 관절염",
    "confidence": 0.85,
    "bucket_scores": {
      "OA": 15.0,
      "OVR": 4.0,
      "TRM": 0.0,
      "INF": 2.0
    },
    "evidence_summary": "55세 여성, 양측 무릎 통증, 아침 뻣뻣함(<30분), 계단 통증, 염발음은 OARSI 가이드라인에 따른 전형적인 무릎 골관절염(OA) 소견입니다.",
    "llm_reasoning": "### 버킷 판단 근거\n- **가중치 분석**: OA 15점 > OVR 4점 > INF 2점\n- **검색 분석**: OA 관련 논문 5개 매칭\n- **결론**: 두 경로 일치, OA로 최종 판단",
    "has_red_flag": false,
    "red_flag_details": null
  },
  "exercise_plan": {
    "exercises": [
      {
        "exercise_id": "E01",
        "name_kr": "힐 슬라이드",
        "name_en": "Heel Slide",
        "difficulty": "low",
        "function_tags": ["Mobility"],
        "target_muscles": ["햄스트링", "대퇴사두근"],
        "sets": 2,
        "reps": "15회",
        "rest": "30초",
        "reason": "OA 환자의 무릎 가동범위 개선에 효과적인 저강도 운동",
        "priority": 1,
        "match_score": 0.95,
        "youtube": "https://youtu.be/Er-Fl_poWDk",
        "description": "누워서 발꿈치를 엉덩이 쪽으로 미끄러뜨려 무릎 가동범위 회복"
      }
    ],
    "excluded": [
      {
        "exercise_id": "E25",
        "name_kr": "점프 스쿼트",
        "reason": "NRS 6점으로 고강도 운동 제외",
        "exclusion_type": "nrs"
      }
    ],
    "routine_order": ["E01", "E06", "E09", "E11", "E15"],
    "total_duration_min": 15,
    "difficulty_level": "low",
    "personalization_note": "퇴행성 관절염 패턴으로 진단되어 맞춤 운동을 구성했습니다 (신뢰도: 85%). 주요 증상(pain_stairs, stiffness_morning, crepitus)을 고려하여 선별했습니다. 중간 강도로 시작하며 점진적으로 증가할 수 있습니다.",
    "llm_reasoning": "### 운동 조합 근거\n- 가동성 → 근력 순서로 워밍업 효과 극대화\n- OA 관절 보호를 위한 저충격 운동 위주"
  },
  "status": "success",
  "message": null,
  "processed_at": "2025-12-24T10:30:00.000Z",
  "processing_time_ms": 15234
}
```

#### Response 필드 상세

| 필드 | 타입 | 설명 |
|------|------|------|
| `request_id` | string | 요청 ID (추적용) |
| `user_id` | string | 사용자 ID |
| `survey_data` | object | **원본 설문 데이터 (백엔드 저장용)** |
| `diagnosis` | object | 진단 결과 |
| `exercise_plan` | object | 운동 추천 결과 (null 가능) |
| `status` | string | 처리 상태 |
| `message` | string | 상태 메시지 (부분 실패 시) |
| `processing_time_ms` | int | 처리 시간 (밀리초) |

### 3.2 Status 값

| 상태 | 설명 | exercise_plan |
|------|------|---------------|
| `success` | 정상 처리 | 운동 목록 포함 |
| `partial` | 부분 성공 (Red Flag 또는 운동 추천 실패) | null |
| `error` | 전체 실패 | null |

### 3.3 진단만 수행 (운동 추천 제외)

```http
POST /api/v1/diagnose
Content-Type: application/json
```

동일한 Request 형식, `options.include_exercises`가 자동으로 false로 설정됨.

---

## 4. 데이터 저장 전략

### 4.1 저장해야 할 데이터

Gateway 응답의 `survey_data`를 그대로 저장하면 됩니다:

```sql
-- 예시 테이블 구조
CREATE TABLE user_diagnoses (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    request_id VARCHAR(100) UNIQUE NOT NULL,

    -- survey_data 전체를 JSONB로 저장
    survey_data JSONB NOT NULL,

    -- diagnosis 결과
    diagnosis_bucket VARCHAR(10) NOT NULL,
    diagnosis_confidence FLOAT NOT NULL,
    diagnosis_data JSONB NOT NULL,

    -- exercise_plan (nullable)
    exercise_plan JSONB,

    -- 메타데이터
    status VARCHAR(20) NOT NULL,
    processing_time_ms INT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 4.2 조회 시 활용

```sql
-- 특정 사용자의 최근 진단 조회
SELECT
    diagnosis_bucket,
    diagnosis_confidence,
    survey_data->'demographics'->>'age' as age,
    survey_data->'body_parts'->0->>'nrs' as pain_score,
    created_at
FROM user_diagnoses
WHERE user_id = 'user_12345'
ORDER BY created_at DESC
LIMIT 1;

-- 버킷별 통계
SELECT
    diagnosis_bucket,
    COUNT(*) as count,
    AVG((survey_data->'body_parts'->0->>'nrs')::int) as avg_nrs
FROM user_diagnoses
GROUP BY diagnosis_bucket;
```

### 4.3 운동 기록 저장

매일 운동 수행 후 사후 평가 저장:

```sql
CREATE TABLE exercise_sessions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    body_part VARCHAR(20) NOT NULL,
    bucket VARCHAR(10) NOT NULL,

    -- 수행한 운동
    exercises JSONB NOT NULL,

    -- 사후 평가 (RPE)
    difficulty_felt INT CHECK (difficulty_felt BETWEEN 1 AND 5),
    muscle_stimulus INT CHECK (muscle_stimulus BETWEEN 1 AND 5),
    sweat_level INT CHECK (sweat_level BETWEEN 1 AND 5),
    pain_during_exercise INT CHECK (pain_during_exercise BETWEEN 0 AND 10),

    -- 완료 정보
    completed_sets INT,
    total_sets INT,
    skipped_exercises TEXT[],

    session_date TIMESTAMP DEFAULT NOW()
);
```

---

## 5. 개별 서비스 API

Gateway를 사용하지 않고 개별 서비스를 직접 호출할 수도 있습니다.

### 5.1 버킷 추론 (Port 8001)

```http
POST http://localhost:8001/api/v1/infer-bucket
```

**용도**: 2주마다 새로운 버킷 추론이 필요할 때

```json
{
  "demographics": { ... },
  "body_parts": [ ... ],
  "natural_language": { ... }
}
```

### 5.2 운동 추천 (Port 8002)

```http
POST http://localhost:8002/api/v1/recommend-exercises
```

**용도**: 이미 버킷이 정해진 상태에서 매일 운동 추천

```json
{
  "user_id": "user_12345",
  "body_part": "knee",
  "bucket": "OA",
  "physical_score": { "total_score": 10 },
  "demographics": { ... },
  "nrs": 5,
  "previous_assessments": [
    {
      "session_date": "2025-12-23T10:00:00",
      "difficulty_felt": 3,
      "muscle_stimulus": 3,
      "sweat_level": 2,
      "pain_during_exercise": 4,
      "skipped_exercises": [],
      "completed_sets": 10,
      "total_sets": 12
    }
  ]
}
```

---

## 6. 에러 처리

### 6.1 HTTP 상태 코드

| 코드 | 의미 | 대응 |
|------|------|------|
| 200 | 성공 (status로 부분 실패 구분) | - |
| 400 | 잘못된 요청 (필수 필드 누락) | 요청 데이터 확인 |
| 422 | 유효성 검증 실패 | 필드 형식 확인 |
| 500 | 서버 오류 | 재시도 또는 문의 |

### 6.2 에러 응답 형식

```json
{
  "detail": "body_parts는 최소 1개 이상이어야 합니다",
  "error_code": "VALIDATION_ERROR",
  "field": "body_parts"
}
```

### 6.3 부분 실패 처리

```json
{
  "status": "partial",
  "message": "Red Flag 감지: 급성 외상 후 관절 잠김. 운동 추천이 생략되었습니다. 전문의 상담을 권장합니다.",
  "diagnosis": { ... },
  "exercise_plan": null
}
```

**백엔드 처리**:
```python
if response["status"] == "partial":
    if response["diagnosis"]["has_red_flag"]:
        # Red Flag 알림 발송
        send_red_flag_notification(user_id, response["message"])
    # 진단 결과만 저장
    save_diagnosis_only(response["diagnosis"])
else:
    # 전체 저장
    save_full_result(response)
```

---

## 7. 통합 시나리오

### 7.1 신규 사용자 첫 진단

```
1. 앱: 설문 수집 (demographics, symptoms, NRS)
2. 앱: POST /api/v1/diagnose-and-recommend
3. AI: 버킷 추론 → 운동 추천 → 통합 응답
4. 백엔드: survey_data + diagnosis + exercise_plan 저장
5. 앱: 진단 결과 및 운동 프로그램 표시
```

### 7.2 기존 사용자 매일 운동

```
1. 백엔드: 저장된 버킷 + 최근 3세션 사후평가 조회
2. 앱: POST /api/v1/recommend-exercises (직접 호출)
3. AI: 사후평가 기반 난이도 조정 → 운동 추천
4. 앱: 운동 프로그램 표시
5. 운동 완료 후: 사후평가 저장
```

### 7.3 2주 후 재진단

```
1. 백엔드: 마지막 진단일 확인 (14일 초과?)
2. 앱: POST /api/v1/diagnose-and-recommend (재진단)
3. AI: 새로운 버킷 추론 (증상 변화 반영)
4. 백엔드: 새 진단 결과 저장, 이전 기록 보존
```

---

## 8. 성능 최적화

### 8.1 응답 시간

| API | 평균 응답 시간 | 최대 |
|-----|--------------|------|
| 통합 (diagnose-and-recommend) | 15-20초 | 30초 |
| 버킷 추론만 | 8-12초 | 20초 |
| 운동 추천만 | 5-8초 | 15초 |

### 8.2 권장 타임아웃

```python
# 통합 API
timeout = 60  # 초

# 개별 API
bucket_timeout = 30
exercise_timeout = 20
```

### 8.3 캐싱 전략

```python
# 버킷 추론 결과 캐싱 (2주)
cache_key = f"bucket:{user_id}:{body_part}"
cached_bucket = redis.get(cache_key)

if cached_bucket and not force_refresh:
    # 캐시된 버킷으로 운동 추천만 수행
    return recommend_exercises(bucket=cached_bucket)
else:
    # 새로운 버킷 추론 + 운동 추천
    result = diagnose_and_recommend(...)
    redis.setex(cache_key, 14*24*60*60, result["diagnosis"]["bucket"])
```

### 8.4 병렬 처리

다중 부위 진단 시 병렬 처리 가능:

```python
import asyncio

async def diagnose_multiple_body_parts(body_parts):
    tasks = [
        diagnose_body_part(bp)
        for bp in body_parts
    ]
    results = await asyncio.gather(*tasks)
    return results
```

---

## 부록: 증상 코드 참조

### 무릎 (knee)

| 코드 | 설명 | 관련 버킷 |
|------|------|----------|
| `pain_stairs` | 계단 통증 | OA |
| `stiffness_morning` | 아침 뻣뻣함 | OA |
| `crepitus` | 염발음 (소리) | OA |
| `pain_running` | 달리기 통증 | OVR |
| `swelling_acute` | 급성 부종 | TRM, INF |
| `instability` | 불안정감 | TRM |
| `warmth_redness` | 열감/발적 | INF |
| `locking` | 잠김 현상 | TRM |

### 어깨 (shoulder)

| 코드 | 설명 | 관련 버킷 |
|------|------|----------|
| `pain_overhead` | 머리 위 동작 통증 | OVR |
| `painful_arc` | Painful arc (60-120도) | OVR |
| `night_pain` | 야간통 | STF |
| `rom_limitation` | 가동범위 제한 | STF, OA |
| `weakness` | 근력 약화 | TRM |
| `trauma_acute` | 급성 외상 | TRM |
| `crepitus` | 염발음 | OA |

---

## 문의

기술적 문의사항은 AI 개발팀으로 연락해주세요.
