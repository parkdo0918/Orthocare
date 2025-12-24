# CLAUDE.md - OrthoCare 프로젝트 개요

이 문서는 OrthoCare 프로젝트의 핵심 개념과 구조를 빠르게 이해하기 위한 가이드입니다.

## 프로젝트 목적

**근거 기반 근골격계 진단 및 운동 추천 AI 시스템**

- 자연어 증상 입력 분석
- 의학 논문 기반 진단
- 맞춤형 운동 프로그램 추천
- 현재 지원: **무릎(knee)**, **어깨(shoulder)**

---

## 핵심 아키텍처

### 마이크로서비스 분리 (V3)

| 서비스 | 포트 | 역할 | 호출 빈도 |
|--------|------|------|----------|
| `bucket_inference` | 8001 | 버킷 추론 (진단) | 2주 1회 |
| `exercise_recommendation` | 8002 | 운동 추천 | 매일 |

### Config-Driven Architecture

**핵심 개념**: 부위별(knee/shoulder) 모든 차이는 `data/medical/{body_part}/` 데이터 파일로 관리

```
body_part.code 입력 → BodyPartConfigLoader.load() → 모든 설정 자동 로드
```

**트리거**: `body_part.code` (예: "knee", "shoulder")

**로드되는 파일들**:
- `config.json` - 부위 기본 설정
- `buckets.json` - 버킷 정의 및 순서
- `weights.json` - 증상별 가중치 벡터
- `survey_mapping.json` - 설문→증상코드 매핑
- `red_flags.json` - 위험 신호 정의
- `prompts/arbitrator.txt` - LLM 프롬프트 템플릿

---

## 버킷 시스템

### 무릎 (Knee)

| 버킷 | 의미 |
|------|------|
| OA | 퇴행성 (Osteoarthritis) |
| OVR | 과사용 (Overuse) |
| TRM | 외상 (Trauma) |
| **INF** | 염증 (Inflammatory) |

### 어깨 (Shoulder)

| 버킷 | 의미 |
|------|------|
| OA | 퇴행성 (Osteoarthritis) |
| OVR | 과사용 (Overuse) |
| TRM | 외상 (Trauma) |
| **STF** | 동결견 (Stiff/Frozen Shoulder) |

**중요**: 무릎은 INF, 어깨는 STF - 4번째 버킷이 다름!

---

## 주요 파일 위치

### 공유 모듈
```
shared/
├── config/
│   └── body_part_config.py    # BodyPartConfig, BodyPartConfigLoader
├── models/
│   ├── demographics.py        # Demographics 모델
│   └── body_part.py           # BodyPartInput 모델
└── utils/
    └── pinecone_client.py     # Pinecone 클라이언트
```

### 버킷 추론 서비스
```
bucket_inference/
├── main.py                    # FastAPI (:8001)
├── services/
│   ├── weight_service.py      # 가중치 계산
│   ├── evidence_search.py     # 벡터 검색
│   └── bucket_arbitrator.py   # LLM 중재 (버킷 결정)
└── pipeline/
    └── inference_pipeline.py  # 메인 파이프라인
```

### 부위별 데이터
```
data/medical/
├── knee/
│   ├── config.json
│   ├── buckets.json
│   ├── weights.json
│   ├── survey_mapping.json
│   ├── red_flags.json
│   └── prompts/arbitrator.txt
└── shoulder/
    ├── config.json
    ├── buckets.json
    ├── weights.json
    ├── survey_mapping.json
    ├── red_flags.json
    └── prompts/arbitrator.txt
```

---

## 진단 파이프라인 흐름

```
1. 입력 검증
   └─ body_part.code로 BodyPartConfig 로드

2. 레드플래그 체크
   └─ config.red_flags 기반

3. 병렬 진단
   ├─ 경로 A: 가중치 기반 (config.weights)
   └─ 경로 B: 벡터 검색 (Pinecone)

4. LLM 중재
   ├─ config.bucket_order로 유효 버킷 결정
   └─ config.prompt_template으로 프롬프트 생성

5. 최종 버킷 결정
   └─ final_bucket: "OA" | "OVR" | "TRM" | "INF/STF"
```

---

## 핵심 원칙

1. **Fail-fast**: 오류 즉시 드러내기, 조용한 폴백 금지
2. **Anti-Hallucination**: 벡터 DB 검색 결과만 인용
3. **Config-Driven**: 코드 수정 없이 데이터 파일로 부위 추가

---

## 새 부위 추가 방법

1. `data/medical/{new_body_part}/` 디렉토리 생성
2. 필수 파일 생성:
   - `config.json`
   - `buckets.json` (bucket_order 포함)
   - `weights.json` (증상 가중치)
   - `survey_mapping.json`
   - `red_flags.json`
   - `prompts/arbitrator.txt`
3. 코드 수정 불필요 - 자동으로 새 부위 지원

---

## 자주 수정되는 파일

| 작업 | 파일 |
|------|------|
| 증상 가중치 수정 | `data/medical/{body_part}/weights.json` |
| 버킷 정의 수정 | `data/medical/{body_part}/buckets.json` |
| LLM 프롬프트 수정 | `data/medical/{body_part}/prompts/arbitrator.txt` |
| 설문 매핑 수정 | `data/medical/{body_part}/survey_mapping.json` |
| 파이프라인 로직 | `bucket_inference/pipeline/inference_pipeline.py` |
| 운동 추천 로직 | `exercise_recommendation/pipeline/recommendation_pipeline.py` |

---

## 테스트 명령어

```bash
# 버킷 추론 서비스 실행
cd bucket_inference && uvicorn main:app --reload --port 8001

# 운동 추천 서비스 실행
cd exercise_recommendation && uvicorn main:app --reload --port 8002

# Config 로딩 테스트
PYTHONPATH=. python -c "
from shared.config import BodyPartConfigLoader
config = BodyPartConfigLoader.load('shoulder')
print(f'Bucket Order: {config.bucket_order}')
"
```

---

## 문서 위치

- `README.md` - 전체 프로젝트 설명
- `docs/knee/` - 무릎 관련 문서
- `docs/shoulder/diagnosis.md` - 어깨 진단 시스템 설명
