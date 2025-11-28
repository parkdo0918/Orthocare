# OrthoCare 기술 설계서 (통합본)

> 최종 수정: 2025-11-29
> 이 문서가 단일 참조 지점입니다.

---

## 1. 프로젝트 개요

**목표**: 자연어/설문 입력 → 근거 기반 진단 → 운동 추천 파이프라인

**핵심 원칙**:
- **Fail-fast**: 오류 발생 시 즉시 드러내고 해결 (조용한 폴백/예외처리 금지)
- Body-part 네임스페이스 분리 (무릎 → 어깨 → 전신 확장)
- 전문가(의사/트레이너) 협업 기반 품질 향상
- 모든 의존성(LLM, 벡터DB, API) 필수 — 없으면 실행 안 함
- **실제 근거 인용**: LLM 응답에서 벡터 DB 검색 결과만 인용 (hallucination 금지)

---

## 2. 버전 정보

| 항목 | 버전 | 위치 |
|------|------|------|
| 무릎 설문 | v1.1 | `docs/knee/form_v1.1.md` |
| 무릎 가중치 | v1.1 | `docs/knee/weights_v1.1.md` |
| 무릎 임상 룰 | v2 | `docs/knee/clinical_rules_v2.json` |
| 운동 라이브러리 | v1.0 | `data/exercise/knee/exercises.json` |
| 논문 메타데이터 | v1.0 | `data/medical/knee/papers/paper_metadata.json` |
| OrthoBullets 캐시 | v1.0 | `data/crawled/orthobullets_cache.json` |

---

## 3. 파이프라인 아키텍처

### 3.1 전체 흐름

```
┌─────────────────────────────────────────────────────────────────┐
│ Phase 1: 입력 처리                                              │
├─────────────────────────────────────────────────────────────────┤
│ 1-1. 입력 검증                                                  │
│ 1-2. 레드플래그 체크 (부위별 룰)                                 │
│ 1-3. 설문 → 증상 코드 매핑 (테이블 기반, LLM 없음)               │
│ 1-4. [복합] 다중 부위 시 우선순위 결정                           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Phase 2: 진단 (병렬 처리)                                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────┐              ┌─────────────────┐           │
│  │ 경로 A: 가중치   │              │ 경로 B: 벡터검색 │           │
│  │ weights.json    │              │ 의미 기반 검색   │           │
│  │ → 버킷 점수     │              │ → 관련 문서     │           │
│  └────────┬────────┘              └────────┬────────┘           │
│           │                                │                    │
│           └───────────────┬────────────────┘                    │
│                           ↓                                     │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ 2-3. LLM Pass #1 — 버킷 검증/정당화                      │    │
│  │      • 두 경로 결과 비교                                 │    │
│  │      • 불일치 감지 시 재검토                             │    │
│  │      • Output: 최종 버킷 + 신뢰도 + 근거 설명            │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Phase 3: 운동 처방                                              │
├─────────────────────────────────────────────────────────────────┤
│ 3-1. [복합] 부위 간 금기 교차 체크                               │
│ 3-2. LLM Pass #2 — 운동 추천                                    │
│      Input: 버킷 + 근거 + 신체점수 + NRS + 금기조건              │
│      Output: 운동 5~7개 + 추천 이유                             │
│ 3-3. 영상 매칭                                                  │
│ 3-4. 루틴 구성 (순서, 세트/렙/휴식)                              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Phase 4: 출력 + 전문가 리뷰 요청                                │
├─────────────────────────────────────────────────────────────────┤
│ 4-1. 환자용 요약                                                │
│ 4-2. 근거 인용 정리                                             │
│ 4-3. 전문가 리뷰 섹션 생성 (→ 협업 앱으로 전달)                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 병렬 검색 전략 (가중치 + 벡터)

**문제**: 가중치만 믿으면 오류 시 전체가 틀어짐

**해결**: 두 경로 병렬 실행 → LLM이 비교 판단

```python
# 경로 A: 규칙 기반
weight_scores = {"OA": 15, "OVR": 8, "TRM": 3, "INF": 2}

# 경로 B: 의미 기반 검색
search_results = [
    {"bucket": "OA", "count": 5},
    {"bucket": "TRM", "count": 3},  # 가중치와 불일치!
    {"bucket": "OVR", "count": 2}
]

# LLM에 둘 다 전달
if weight_ranking != search_ranking:
    # 불일치 감지 → LLM이 증상 재검토 후 최종 결정
```

### 3.3 근거 검색 계층 (Evidence Layers)

| Layer | 소스 타입 | 신뢰도 | 벡터 DB 메타데이터 |
|-------|----------|--------|-------------------|
| **1** | verified_paper | 최상 | `source: "verified_paper"` |
| **2** | orthobullets | 상 | `source: "orthobullets"` |
| **3** | pubmed | 중 (미검증) | `source: "pubmed"` |

**현재 벡터 DB 현황** (2025-11-29):
```
총 벡터 수: 875개
├── verified_paper: 47개 (검증된 논문 청크)
├── pubmed: 40개 (PubMed 논문 청크)
├── orthobullets: 5개 (OrthoBullets 교육 자료)
└── exercise: 50개 (운동 데이터)
```

**벡터 검색 구현** (`EvidenceSearchService`):
```python
# 1. 임베딩 생성 (text-embedding-3-large, 3072차원)
embed_result = embedder.embed(query)

# 2. Pinecone 검색 (body_part 필터만, 모든 소스 포함)
filters = {"body_part": body_part}
results = vector_store.query(
    vector=embed_result.embedding,
    top_k=10,
    filter=filters,
    namespace=""  # 기본 네임스페이스
)

# 3. 소스 타입에 따른 레이어 결정
for match in results.matches:
    source = match.metadata.get("source")
    if source == "verified_paper":
        source_layer = 1
    elif source == "orthobullets":
        source_layer = 2
    elif source == "pubmed":
        source_layer = 3
```

**중요: min_score 임계값 = 0.35** (유사도 0.4~0.5 수준에서 결과 반환)

### 3.4 LLM 인용 규칙 (Anti-Hallucination)

**핵심 원칙**: LLM은 벡터 DB에서 검색된 문서만 인용해야 함. 존재하지 않는 논문 인용 금지.

**BucketArbitrator 프롬프트 규칙**:
```
## 인용 규칙 (매우 중요)
- 아래 "실제 검색된 근거 자료" 섹션에 있는 문서만 인용하세요
- 존재하지 않는 논문이나 가이드라인을 만들어내지 마세요
- 검색된 문서의 title, source, text를 그대로 인용하세요
- 인용 형식: "제목" [source] - "관련 내용 직접 인용"
```

**구현 위치**: `orthocare/services/diagnosis/bucket_arbitrator.py:77-82`

**검증된 출력 예시**:
```
## 근거 문서
1. **Knee Osteoarthritis - OrthoBullets** [orthobullets]
   > "Most common form of knee arthritis. Risk factors: age, obesity, prior injury."
2. **Clinical Knee Assessment** [verified_paper]
   > "Pain is the most common symptom in knee OA..."
```

---

## 4. 모듈 구조

```
orthocare/
├── config/
│   ├── settings.py           # Pydantic Settings (.env 통합)
│   └── constants.py          # 버킷명, 증상코드 상수
│
├── models/                   # 데이터 계약
│   ├── user_input.py         # UserInput, Demographics
│   ├── diagnosis.py          # DiagnosisResult, BucketScore
│   ├── exercise.py           # Exercise, ExerciseRecommendation
│   └── evidence.py           # Paper, Guideline, EvidenceResult
│
├── services/
│   ├── input/
│   │   ├── validator.py      # 입력 검증
│   │   ├── red_flag_checker.py
│   │   └── symptom_mapper.py # 설문 → 코드 (테이블 기반)
│   │
│   ├── scoring/
│   │   ├── weight_service.py # 가중치 로딩/계산
│   │   └── modifiers.py      # 나이/성별/BMI 보정
│   │
│   ├── evidence/
│   │   ├── search_service.py # 벡터 검색 (3-Layer)
│   │   └── relevance.py      # relevance 점수
│   │
│   ├── diagnosis/
│   │   ├── clinical_engine.py
│   │   ├── bucket_arbitrator.py  # LLM Pass #1
│   │   └── override_rules.py
│   │
│   ├── exercise/
│   │   ├── recommender.py        # LLM Pass #2
│   │   ├── contraindication.py   # 금기 체크
│   │   └── video_matcher.py
│   │
│   └── output/
│       ├── summary_generator.py
│       └── review_request_builder.py
│
├── pipelines/
│   ├── base.py
│   └── main_pipeline.py      # 전체 오케스트레이션
│
├── data_ops/
│   ├── loaders/              # body_part별 데이터 로딩
│   ├── embeddings.py
│   └── vector_store.py
│
└── utils/
    ├── tracing.py            # LangSmith
    └── logging.py
```

---

## 5. 데이터 구조

### 5.1 실제 폴더 구조 (2025-11-29 기준)

```
data/
├── medical/
│   └── knee/
│       ├── papers/
│       │   ├── original/           # 원본 PDF
│       │   ├── processed/          # 청크 처리된 JSON
│       │   └── paper_metadata.json # 논문별 버킷/소스 메타데이터 ⭐
│       └── guidelines/
│
├── exercise/
│   └── knee/
│       └── exercises.json          # 운동 라이브러리 (50개)
│
├── crawled/
│   └── orthobullets_cache.json     # OrthoBullets 교육 자료 (5개) ⭐
│
└── clinical/
    └── knee/
        ├── weights.json
        ├── buckets.json
        ├── red_flags.json
        └── symptom_mapping.json
```

### 5.2 논문 메타데이터 (`paper_metadata.json`)

논문별 버킷 태그와 소스 타입을 관리:
```json
{
  "_description": "논문별 버킷 태그 및 소스 타입 메타데이터",
  "_updated": "2025-11-29",
  "papers": {
    "duncan2008": {
      "title": "Pain and Function in Knee Osteoarthritis (Duncan 2008)",
      "buckets": ["OA"],
      "source_type": "verified_paper",
      "evidence_level": "Level II",
      "year": 2008
    },
    "prodromos2007": {
      "title": "ACL Tears Meta-analysis (Prodromos 2007)",
      "buckets": ["TRM"],
      "source_type": "verified_paper",
      "evidence_level": "Level I"
    }
  }
}
```

**버킷 태그 정의**:
- `OA`: Osteoarthritis (퇴행성)
- `OVR`: Overuse (과사용)
- `TRM`: Trauma (외상)
- `INF`: Inflammatory/Infection (염증/감염)

### 5.3 OrthoBullets 캐시 (`orthobullets_cache.json`)

수동 큐레이션된 OrthoBullets 교육 자료:
```json
{
  "knee_oa_overview": {
    "url": "https://www.orthobullets.com/recon/9061/knee-osteoarthritis",
    "title": "Knee Osteoarthritis - OrthoBullets",
    "content": "Knee osteoarthritis (OA) is a degenerative joint disease...",
    "body_part": "knee",
    "category": "OA",
    "key_points": ["Most common form of knee arthritis", ...]
  }
}
```

**현재 포함된 토픽** (5개):
| 토픽 | 버킷 | 내용 |
|------|------|------|
| knee_oa_overview | OA | 무릎 골관절염 |
| acl_injury | TRM | 전방십자인대 손상 |
| meniscus_tear | TRM | 반월판 파열 |
| patellofemoral_syndrome | OVR | 슬개대퇴 증후군 |
| septic_arthritis | INF | 화농성 관절염 |

### 5.4 벡터 DB 메타데이터 스키마 (Pinecone)

```python
# 각 벡터의 메타데이터 구조
metadata = {
    "body_part": "knee",           # 필수: 부위 코드
    "source": "verified_paper",    # 소스 타입: verified_paper, orthobullets, pubmed, exercise
    "bucket": "OA,TRM",            # 버킷 태그 (쉼표 구분)
    "title": "논문 제목",
    "text": "청크 텍스트 내용...",
    "year": 2008,                  # 선택: 발행연도
    "url": "https://..."           # 선택: 원문 URL
}
```

### 5.5 핵심 인터페이스

```python
@dataclass
class UserInput:
    body_parts: List[BodyPartInput]  # 복합 부위 지원
    demographics: Demographics
    physical_score: PhysicalScore    # Lv A/B/C/D

@dataclass
class BodyPartInput:
    code: str           # "knee", "shoulder"
    primary: bool       # 주부위 여부
    symptoms: List[str] # 증상 코드 리스트

@dataclass
class DiagnosisResult:
    bucket_scores: BucketScores
    weight_ranking: List[str]       # 가중치 기반 순위
    search_ranking: List[str]       # 검색 기반 순위
    discrepancy: Optional[str]      # 불일치 내용
    final_bucket: str
    confidence: float
    evidence_summary: str

@dataclass
class ExerciseSet:
    exercises: List[ExerciseRecommendation]
    common_safe: List[str]          # 복합 부위 시 공통 안전 운동
    excluded: List[str]             # 금기로 제외된 운동
```

---

## 6. 복합 통증 처리 (v2)

```python
# 입력
body_parts = [
    {"code": "knee", "primary": True},
    {"code": "lower_back", "primary": False}
]

# 부위별 독립 진단
diagnoses = {
    "knee": {"bucket": "OA", "confidence": 0.85},
    "lower_back": {"bucket": "DISC", "confidence": 0.72}
}

# 금기 교차 체크
cross_check = check_contraindications("knee.OA", "lower_back.DISC")
# → ["딥 스쿼트", "레그 프레스"] 제외

# 운동 추천
exercises = {
    "common_safe": ["브릿지", "클램쉘", "데드버그"],
    "knee_specific": ["힐 슬라이드", "쿼드 세팅"],
    "back_specific": ["캣카우", "버드독"],
    "excluded": ["딥 스쿼트", "레그 프레스"]
}
```

---

## 7. 구현 우선순위

| 순서 | 작업 | 이유 |
|------|------|------|
| 1 | `config/settings.py` | 하드코딩 키 제거 |
| 2 | `models/` 전체 | 데이터 계약 확정 |
| 3 | `data_ops/loaders/` | body_part 파라미터화 |
| 4 | `services/input/` | 설문 → 코드 매핑 |
| 5 | `services/scoring/` | 가중치 계산 |
| 6 | `services/evidence/` | 3-Layer 검색 |
| 7 | `services/diagnosis/` | LLM Pass #1 |
| 8 | `services/exercise/` | LLM Pass #2 |
| 9 | `pipelines/` | 오케스트레이션 |

---

## 8. 스크립트

### 8.1 인덱싱 스크립트 (`scripts/run_indexing.py`)

벡터 DB에 데이터 인덱싱:
```bash
# 전체 인덱싱 (논문 + 운동 + OrthoBullets)
PYTHONPATH=. python scripts/run_indexing.py

# 논문만 재인덱싱
PYTHONPATH=. python scripts/run_indexing.py --papers-only

# 운동만 재인덱싱
PYTHONPATH=. python scripts/run_indexing.py --exercises-only
```

**인덱싱 파이프라인 흐름**:
1. `PaperIndexer`: PDF 청크 → `paper_metadata.json`에서 버킷 태그 로드 → 벡터 DB 저장
2. `ExerciseIndexer`: exercises.json → 벡터 DB 저장
3. `CrawledIndexer`: orthobullets_cache.json → 벡터 DB 저장

### 8.2 E2E 테스트 (`scripts/test_e2e.py`)

파이프라인 전체 테스트:
```bash
# 기본 테스트 (Persona 1: OA 증상)
PYTHONPATH=. python scripts/test_e2e.py

# 특정 페르소나 테스트
PYTHONPATH=. python scripts/test_e2e.py --persona 2
```

**페르소나 정의**:
| Persona | 나이 | 증상 | 예상 버킷 |
|---------|------|------|----------|
| 1 | 55 | 무릎 통증, 아침 뻣뻣함, 계단 오르기 어려움 | OA |
| 2 | 28 | ACL 부상 후 불안정감, 운동 중 손상 | TRM |
| 3 | 35 | 달리기 후 무릎 앞쪽 통증, 앉았다 일어날 때 악화 | OVR |

### 8.3 OrthoBullets 크롤링 (`scripts/crawl_orthobullets.py`)

> **주의**: OrthoBullets가 SPA로 변경되어 직접 크롤링 불가 (404 오류)
> 현재는 수동으로 `orthobullets_cache.json`에 데이터 추가

```bash
# 캐시된 데이터만 인덱싱
PYTHONPATH=. python scripts/crawl_orthobullets.py
```

---

## 9. 인덱싱 파이프라인 상세

### 9.1 PaperIndexer (논문 인덱싱)

**위치**: `orthocare/data_ops/indexing/pipeline.py`

```python
class PaperIndexer:
    def __init__(self, pinecone_index, openai_client, namespace=""):
        self._paper_metadata_cache = {}  # 메타데이터 캐시

    def _load_paper_metadata(self, body_part: str) -> Dict:
        """paper_metadata.json에서 버킷/소스 정보 로드"""
        metadata_path = settings.data_dir / "medical" / body_part / "papers" / "paper_metadata.json"
        # ...

    def index_paper_chunks(self, chunks, body_part: str):
        """청크 인덱싱 - 메타데이터 기반 버킷 태그 적용"""
        paper_metadata = self._load_paper_metadata(body_part)

        for chunk in chunks:
            paper_id = chunk.get("paper_id")
            paper_info = paper_metadata.get(paper_id, {})
            bucket_tags = paper_info.get("buckets", [])
            source_type = paper_info.get("source_type", "paper")

            # 벡터 DB에 저장
            metadata = {
                "body_part": body_part,
                "source": source_type,
                "bucket": ",".join(bucket_tags),
                "title": paper_info.get("title", chunk.get("title")),
                "text": chunk["text"]
            }
```

### 9.2 CrawledIndexer (OrthoBullets 인덱싱)

```python
class CrawledIndexer:
    def index_orthobullets_articles(self, articles: List[OrthoBulletsArticle]):
        """OrthoBullets 문서 인덱싱"""
        for article in articles:
            metadata = {
                "body_part": article.body_part,
                "source": "orthobullets",
                "bucket": article.category,  # OA, TRM, OVR, INF
                "title": article.title,
                "text": article.content,
                "url": article.url
            }
```

---

## 10. 결정 사항

| 항목 | 결정 |
|------|------|
| 무릎 버킷 수 | **4개** (OA/OVR/TRM/INF) |
| PubMed 검색 정책 | 유사도 높음 → 자동 임베딩, 애매한 것만 의사 검토 |
| 벡터 DB | **Pinecone** (서버리스, 3072차원) |
| 임베딩 모델 | **text-embedding-3-large** (OpenAI) |
| 최소 유사도 | **0.35** (검색 결과 필터링) |
| OrthoBullets | 크롤링 불가 → **수동 큐레이션** |
| LLM 인용 | **검색된 문서만** (hallucination 금지)

---

## 참고 파일

### 핵심 데이터 파일
- 논문 메타데이터: `data/medical/knee/papers/paper_metadata.json`
- OrthoBullets 캐시: `data/crawled/orthobullets_cache.json`
- 운동 라이브러리: `data/exercise/knee/exercises.json`

### 설정 및 규칙
- 무릎 설문: `docs/knee/form_v1.1.md`
- 무릎 가중치: `docs/knee/weights_v1.1.md`
- 임상 룰: `docs/knee/clinical_rules_v2.json`

### 스크립트
- 인덱싱: `scripts/run_indexing.py`
- E2E 테스트: `scripts/test_e2e.py`
- OrthoBullets 크롤링: `scripts/crawl_orthobullets.py`

### 핵심 서비스 코드
- 근거 검색: `orthocare/services/evidence/search_service.py`
- 버킷 판정: `orthocare/services/diagnosis/bucket_arbitrator.py`
- 인덱싱 파이프라인: `orthocare/data_ops/indexing/pipeline.py`

---

## 변경 이력

| 날짜 | 변경 내용 |
|------|----------|
| 2025-11-29 | LLM 인용 규칙 추가 (Anti-hallucination) |
| 2025-11-29 | paper_metadata.json 생성 (논문별 버킷 태그) |
| 2025-11-29 | orthobullets_cache.json 생성 (5개 교육 자료) |
| 2025-11-29 | EvidenceSearchService 3-Layer 구현 |
| 2025-11-29 | 스크립트 및 인덱싱 파이프라인 문서화 |
