# 어깨 진단 시스템 (Shoulder Diagnosis System)

> 어깨 통증 분류 및 진단 파이프라인 설명서

---

## 목차

1. [버킷 분류 체계](#1-버킷-분류-체계)
2. [증상 가중치 시스템](#2-증상-가중치-시스템)
3. [설문 매핑](#3-설문-매핑)
4. [임상 테스트](#4-임상-테스트)
5. [레드플래그](#5-레드플래그)
6. [진단 파이프라인 흐름](#6-진단-파이프라인-흐름)

---

## 1. 버킷 분류 체계

어깨 통증은 4가지 버킷으로 분류됩니다:

| 버킷 | 영문명 | 한글명 | 설명 | 전형적 프로필 |
|------|--------|--------|------|---------------|
| **TRM** | Trauma | 외상성 | 급성 외상으로 인한 회전근개 파열, AC joint 손상, 탈구 등 | 외상 직후 급성 통증, 팔 들어올리기 어려움, 힘이 빠지는 느낌 |
| **OVR** | Overuse | 과사용성 | 반복적인 과부하로 인한 건염, 충돌증후군, 견갑운동장애 | 서서히 시작, Painful Arc (60-120도), 반복 overhead 활동 후 악화 |
| **OA** | Osteoarthritis | 퇴행성 | 만성 구조 변화로 인한 견관절/AC joint 골관절염 | 50세 이상, 서서히 진행, ROM 감소, crepitus |
| **STF** | Stiff (Frozen Shoulder) | 동결견 | 관절낭 구축으로 인한 동결견 (Adhesive Capsulitis) | 40-60대, 외회전 제한 현저, 야간통, Freezing→Frozen→Thawing 단계 |

### 버킷별 주요 특징

#### TRM (외상성)
- **주요 증상**: `trauma_recent`, `sudden_onset`, `weakness`, `drop_arm`, `popeye_sign`
- **핵심 테스트**: Drop Arm Test, Empty Can Test, External Rotation Lag Sign
- **흔한 질환**: 급성 회전근개 파열, AC joint sprain, 이두근 장건 파열, 탈구/Bankart lesion
- **재활 전략**: 보호 → 단계적 강화

#### OVR (과사용성)
- **주요 증상**: `painful_arc`, `overhead_pain`, `gradual_onset`, `activity_related`, `rest_improvement`
- **핵심 테스트**: Hawkins-Kennedy Test, Neer Test, Empty Can Test
- **흔한 질환**: 회전근개 건염, 충돌증후군, 견갑운동조절 장애, 이두건염
- **재활 전략**: 견갑 안정화 + cuff 강화

#### OA (퇴행성)
- **주요 증상**: `chronic`, `crepitus`, `stiffness_morning`, `rom_limited`, `adl_limited`
- **핵심 테스트**: Apley Scratch Test, Passive ROM 제한, Crepitus 촉진
- **흔한 질환**: 견관절 골관절염, 회전근개 관절병증, AC joint OA
- **재활 전략**: ROM 유지 + 중강도 강화

#### STF (동결견)
- **주요 증상**: `er_limitation`, `capsular_pattern`, `night_pain`, `progressive_rom_loss`, `axillary_pain`
- **핵심 테스트**: Passive ROM (특히 ER 제한), Capsular End-feel, Apley Scratch Test
- **흔한 질환**: 동결견 (Adhesive Capsulitis), 초기 capsulitis
- **재활 전략**: Phase-based ROM/stretch

### 감별 포인트

| 감별 기준 | 우선 고려 버킷 |
|-----------|---------------|
| 명확한 외상 유무 | TRM 우선 고려 |
| ROM 패턴: ER 제한 현저 + Capsular pattern | STF |
| Painful Arc: 60-120도 통증 | OVR (충돌증후군) |
| Crepitus + 50세+ | OA |

---

## 2. 증상 가중치 시스템

가중치는 `[OA, OVR, TRM, STF]` 순서로 정의됩니다.

### 인구통계 가중치

| 증상 코드 | OA | OVR | TRM | STF | 설명 |
|----------|-----|-----|-----|-----|------|
| `sex_female` | 1.0 | 1.0 | 0.0 | 1.0 | 여성 |
| `sex_male` | 0.0 | 1.0 | 1.0 | 0.0 | 남성 |
| `age_gte_50` | 3.0 | 0.0 | 0.0 | 2.0 | 50세 이상 |
| `age_gte_60` | 3.0 | 0.0 | 0.0 | 2.0 | 60세 이상 |
| `age_40s` | 1.0 | 1.0 | 0.5 | 1.5 | 40대 |
| `age_30s` | 0.0 | 2.0 | 1.0 | 0.5 | 30대 |
| `age_20s` | 0.0 | 2.0 | 1.5 | 0.0 | 20대 |
| `bmi_gte_25` | 1.0 | 0.0 | 0.0 | 0.0 | BMI 25 이상 |
| `bmi_gte_30` | 2.0 | 0.0 | 0.0 | 0.0 | BMI 30 이상 |

### 통증 위치 가중치

| 증상 코드 | OA | OVR | TRM | STF | 설명 |
|----------|-----|-----|-----|-----|------|
| `pain_anterior` | 1.0 | 2.0 | 2.0 | 1.0 | 어깨 앞쪽 (이두근 쪽) |
| `pain_lateral` | 1.0 | 3.0 | 2.0 | 0.0 | 어깨 바깥쪽 (옆면) |
| `pain_superior` | 3.0 | 1.0 | 1.0 | 0.0 | 어깨 위쪽 (견봉/쇄골 부위) |
| `pain_axillary` | 1.0 | 0.0 | 0.0 | 3.0 | 겨드랑이 안쪽 (관절 깊은 부위) |
| `pain_bilateral` | 1.0 | 0.0 | 0.0 | 1.0 | 양측 통증 |

### 발병 시점 가중치

| 증상 코드 | OA | OVR | TRM | STF | 설명 |
|----------|-----|-----|-----|-----|------|
| `gradual_onset` | 1.0 | 1.0 | 0.0 | 1.0 | 서서히 시작 |
| `activity_increase` | 0.0 | 3.0 | 1.0 | 0.0 | 활동 후 악화 |
| `trauma_recent` | 0.0 | 1.0 | 3.0 | 0.0 | 최근 외상 |
| `progressive_rom_loss` | 2.0 | 0.0 | 0.0 | 4.0 | 점진적 ROM 감소 |
| `sudden_onset` | 0.0 | 1.0 | 3.0 | 0.0 | 갑작스런 발병 |

### 악화 요인 가중치

| 증상 코드 | OA | OVR | TRM | STF | 설명 |
|----------|-----|-----|-----|-----|------|
| `abduction_overhead` | 1.0 | 3.0 | 2.0 | 1.0 | 팔 벌리기/머리 위 동작 |
| `internal_rotation_behind` | 2.0 | 0.0 | 0.0 | 4.0 | 등 뒤로 손 넣기 |
| `heavy_lifting` | 1.0 | 2.0 | 3.0 | 0.0 | 무거운 물건 들기 |
| `lying_on_side` | 0.0 | 3.0 | 2.0 | 0.0 | 아픈 쪽으로 눕기 |
| `at_rest` | 0.0 | 1.0 | 1.0 | 2.0 | 가만히 있을 때 |

### 통증 성격 가중치

| 증상 코드 | OA | OVR | TRM | STF | 설명 |
|----------|-----|-----|-----|-----|------|
| `catching_feeling` | 2.0 | 2.0 | 1.0 | 0.0 | 걸리는 느낌 |
| `sharp_pain` | 0.0 | 1.0 | 3.0 | 0.0 | 날카로운 통증 |
| `dull_heavy` | 3.0 | 1.0 | 0.0 | 1.0 | 뻐근하고 묵직한 통증 |
| `stiff_restricted` | 2.0 | 0.0 | 0.0 | 4.0 | 뻣뻣하고 움직임 제한 |
| `night_pain` | 1.0 | 2.0 | 1.0 | 4.0 | 야간통 |

### 임상 특징 가중치 (높은 가중치)

| 증상 코드 | OA | OVR | TRM | STF | 설명 |
|----------|-----|-----|-----|-----|------|
| `painful_arc` | 1.0 | **4.0** | 1.0 | 0.0 | Painful Arc (60-120도) |
| `drop_arm` | 0.0 | 0.0 | **5.0** | 0.0 | Drop Arm 양성 |
| `crepitus` | **4.0** | 0.0 | 0.0 | 0.0 | 거친 소리/느낌 |
| `er_limitation` | 1.0 | 0.0 | 0.0 | **5.0** | 외회전 제한 |
| `capsular_pattern` | 1.0 | 0.0 | 0.0 | **5.0** | Capsular pattern |
| `popeye_sign` | 0.0 | 0.0 | **5.0** | 0.0 | Popeye Sign |
| `overhead_activity` | 0.0 | **4.0** | 1.0 | 0.0 | Overhead 활동 관련 |

---

## 3. 설문 매핑

### Q1: 통증 위치

> "어느 쪽 어깨가 아프신가요?" (다중 선택)

| 선택지 | 증상 코드 |
|--------|----------|
| 왼쪽 | - |
| 오른쪽 | - |
| 모두 | `pain_bilateral` |
| 어깨 앞쪽 (이두근 쪽) | `pain_anterior` |
| 어깨 바깥쪽 (옆면) | `pain_lateral` |
| 어깨 위쪽 (견봉/쇄골 부위) | `pain_superior` |
| 겨드랑이 안쪽 (관절 깊은 부위) | `pain_axillary` |
| 경추 승모근 (목과 어깨 사이) | `pain_cervical_trapezius` |

**특별 규칙:**
- 경추/승모근 + 다른 어깨 부위 선택 → "어깨 관절 문제와 목/승모근 문제가 함께 있을 가능성" 안내
- 경추/승모근만 선택 → "목/경추 문제 가능성" 안내 후 목 운동 추천으로 리다이렉트

### Q2: 발병 시점

> "언제부터 아팠나요?" (다중 선택)

| 선택지 | 증상 코드 |
|--------|----------|
| 특별한 계기 없이 서서히 | `gradual_onset` |
| 팔을 많이 쓰는 활동 후 | `activity_increase`, `overhead_activity` |
| 넘어지거나 부딪히거나 '뚝' 소리와 함께 | `trauma_recent`, `sudden_onset` |
| 몇 주~몇 달 사이 팔이 점점 덜 올라감 | `progressive_rom_loss`, `stiff_restricted` |

### Q3: 통증 정도 (NRS)

> "현재 어깨 통증의 정도" (0-10 슬라이더)

- NRS는 운동 강도 결정에 사용
- 직접적인 버킷 가중치에는 미반영

### Q4: 악화 요인

> "언제 통증이 더 심해지나요?" (다중 선택)

| 선택지 | 증상 코드 |
|--------|----------|
| 팔을 옆으로 벌리거나 머리 위로 올릴 때 | `abduction_overhead`, `painful_arc` |
| 팔을 앞으로 들거나 멀리 뻗을 때 | `forward_flexion` |
| 팔을 뒤로 돌리거나 등 뒤로 손을 넣을 때 | `internal_rotation_behind`, `er_limitation` |
| 무거운 물건을 들거나 들어올릴 때 | `heavy_lifting` |
| 아픈 쪽으로 옆으로 누워 잘 때 | `lying_on_side`, `night_pain` |
| 팔을 든 채로 오래 유지할 때 | `arm_sustained`, `overhead_activity` |
| 가만히 있을 때도 아프다 | `at_rest`, `night_pain` |

### Q5: 통증 성격

> "어떤 느낌으로 아프신가요?" (다중 선택)

| 선택지 | 증상 코드 |
|--------|----------|
| 움직일 때 어깨 안에서 걸리는 느낌 | `catching_feeling`, `crepitus` |
| 찌릿찌릿하거나 찌르는 날카로운 통증 | `sharp_pain` |
| 뻐근하고 묵직한 통증 | `dull_heavy`, `chronic` |
| 당기고 뻣뻣해서 잘 안 움직이는 느낌 | `stiff_restricted`, `rom_limited`, `capsular_pattern` |
| 가만히 있을 때도 아프고 밤에 더 심해짐 | `night_pain`, `at_rest` |

---

## 4. 임상 테스트

### 버킷별 핵심 테스트

| 버킷 | 테스트 | 양성 의미 |
|------|--------|----------|
| **TRM** | Drop Arm Test | 회전근개 파열 |
| **TRM** | Empty Can Test | 극상근 손상 |
| **TRM** | External Rotation Lag Sign | 외회전근 손상 |
| **OVR** | Hawkins-Kennedy Test | 충돌증후군 |
| **OVR** | Neer Test | 충돌증후군 |
| **OA** | Apley Scratch Test | ROM 제한 |
| **OA** | Passive ROM 제한 | 관절 문제 |
| **STF** | Passive ROM (특히 ER 제한) | 관절낭 구축 |
| **STF** | Capsular End-feel | 동결견 |

### Painful Arc 해석

```
0°─────60°─────120°─────180°
          ▲      ▲
       통증 시작  통증 종료

60-120도 사이 통증 = 충돌증후군 (OVR) 의심
```

---

## 5. 레드플래그

즉시 병원 방문이 필요한 위험 신호:

| 코드 | 증상 | 심각도 | 조치 |
|------|------|--------|------|
| `severe_pain_no_movement` | 팔을 거의 들기 어려울 정도로 심한 통증 | high | 즉시 진료 |
| `acute_swelling_heat` | 어깨가 갑자기 붓고 뜨거움 | high | 즉시 진료 |
| `weakness_numbness` | 팔에 힘이 안 들어가거나 감각 둔화 | high | 즉시 진료 |
| `radiating_pain_cervical` | 목에서 팔로 전기 뻗치는 통증 | high | 즉시 진료 |
| `fever_chills` | 발열, 오한, 전신 몸살 | critical | 즉시 진료 |
| `post_injection_pain` | 주사 후 통증 급격히 심해짐 | high | 즉시 진료 |

**경고 메시지:**
> "체크하신 항목은 **즉시 전문적인 진단이 필요한 위험 신호**일 수 있습니다. 무리한 운동은 오히려 상태를 악화시킬 수 있으니, **지금 바로 정형외과나 병원에 방문하여 정확한 진료를 받아보시기를 강력하게 권유**합니다."

---

## 6. 진단 파이프라인 흐름

### Config-Driven Architecture

어깨와 무릎은 동일한 파이프라인을 사용하며, `body_part.code`가 트리거가 됩니다:

```
                    ┌─────────────────┐
 body_part.code ──▶ │ BodyPartConfig  │
    "shoulder"      │    Loader       │
                    └────────┬────────┘
                             │
           ┌─────────────────┼─────────────────┐
           ▼                 ▼                 ▼
    ┌──────────┐      ┌──────────┐      ┌──────────┐
    │ buckets  │      │ weights  │      │ prompts  │
    │  .json   │      │  .json   │      │  .txt    │
    └──────────┘      └──────────┘      └──────────┘
```

### 추론 흐름

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. 입력 검증                                                      │
├─────────────────────────────────────────────────────────────────┤
│ • body_part = "shoulder" → BodyPartConfigLoader.load("shoulder") │
│ • 레드플래그 체크                                                  │
│ • 설문 → 증상 코드 매핑                                            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. 병렬 진단                                                      │
├─────────────────────────────────────────────────────────────────┤
│  ┌───────────────────┐        ┌───────────────────┐             │
│  │ 경로 A: 가중치      │        │ 경로 B: 벡터 검색   │             │
│  │ config.weights    │        │ Pinecone 검색      │             │
│  │ [OA,OVR,TRM,STF] │        │ body_part=shoulder │             │
│  └─────────┬─────────┘        └─────────┬─────────┘             │
│            └────────────┬───────────────┘                       │
│                         ▼                                        │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ LLM Arbitrator                                           │    │
│  │ • config.bucket_order = [OA, OVR, TRM, STF]              │    │
│  │ • config.prompt_template (어깨 전용 프롬프트)              │    │
│  │ • 가중치 vs 검색 불일치 시 재검토                          │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. 출력                                                          │
├─────────────────────────────────────────────────────────────────┤
│ • final_bucket: "STF" (예시)                                     │
│ • confidence: 0.85                                               │
│ • evidence_summary: 근거 요약                                    │
│ • bucket_scores: {OA: 8.0, OVR: 5.0, TRM: 3.0, STF: 19.0}       │
└─────────────────────────────────────────────────────────────────┘
```

### 파일 구조

```
data/medical/shoulder/
├── config.json          # 부위 설정 (display_name, version)
├── buckets.json         # 버킷 정의 (TRM, OVR, OA, STF)
├── weights.json         # 증상 가중치 [OA, OVR, TRM, STF]
├── survey_mapping.json  # 설문 → 증상 코드 매핑
├── red_flags.json       # 위험 신호 정의
└── prompts/
    └── arbitrator.txt   # LLM 중재자 프롬프트
```

### 무릎 vs 어깨 차이점

| 항목 | 무릎 (knee) | 어깨 (shoulder) |
|------|------------|-----------------|
| 버킷 | OA, OVR, TRM, **INF** | OA, OVR, TRM, **STF** |
| 가중치 배열 | [OA, OVR, TRM, INF] | [OA, OVR, TRM, STF] |
| 프롬프트 | 무릎 전문의 | 어깨 전문의 |
| 설문 | 무릎 전용 Q1-Q5 | 어깨 전용 Q1-Q5 |

---

## 참고

- 이 문서는 `data/medical/shoulder/` 디렉토리의 데이터 파일을 기반으로 작성되었습니다.
- 가중치 값은 임상 전문가와의 협의를 통해 조정될 수 있습니다.
- 버킷 분류 체계는 OrthoBullets 및 검증된 논문을 참고하여 설계되었습니다.
