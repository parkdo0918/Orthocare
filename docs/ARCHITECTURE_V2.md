# OrthoCare V2 아키텍처

## 개요

기존 Phase 1/2/3 파이프라인을 세분화하고, 근거 기반 검색 및 크롤링 시스템을 추가합니다.

---

## 1. 벡터 DB 인덱싱 시스템

### 1.1 인덱싱 대상

| 소스 | 설명 | 우선순위 |
|------|------|----------|
| 운동 DB | exercises.json | P0 |
| 임상 가이드라인 | OARSI, ACR, AAFP 등 | P0 |
| PubMed | 무릎 관련 논문 | P1 |
| OrthoBullets | 정형외과 교육 자료 | P1 |

### 1.2 인덱싱 스키마

```json
{
  "id": "paper_001_chunk_1",
  "values": [0.123, ...],  // 3072-dim embedding
  "metadata": {
    "source": "pubmed|orthobullets|guideline|exercise",
    "source_id": "PMID:12345678",
    "title": "논문/가이드라인 제목",
    "body_part": "knee|shoulder|back|neck|ankle",
    "bucket": "OA|OVR|TRM|INF|null",
    "evidence_level": "1a|1b|2a|2b|3|4|5",
    "year": 2023,
    "chunk_index": 1,
    "total_chunks": 5,
    "text": "청크 텍스트 (검색 결과 표시용)"
  }
}
```

### 1.3 청킹 전략

- **Chunk 크기**: 512 tokens (text-embedding-3-large 최적)
- **Overlap**: 100 tokens (20%)
- **분할 기준**: 문단 > 문장 > 토큰

---

## 2. 크롤링 시스템

### 2.1 PubMed 크롤러

```
검색 쿼리 예시:
- "knee osteoarthritis"[MeSH] AND "exercise therapy"[MeSH]
- "anterior cruciate ligament"[MeSH] AND "rehabilitation"[MeSH]

필터:
- 최근 5년
- Clinical Trial, Systematic Review, Meta-Analysis
- English
```

### 2.2 OrthoBullets 크롤러

```
대상 페이지:
- /knee/pathology/
- /knee/anatomy/
- /techniques/rehabilitation/
```

### 2.3 크롤링 → 검토 → 인덱싱 워크플로우

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   크롤링     │ --> │  Sheets     │ --> │   검토      │ --> │  인덱싱     │
│   (자동)    │     │  업로드     │     │  (수동)     │     │  (자동)     │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
```

---

## 3. Google Sheets 검토 시스템

### 3.1 시트 구조

| Column | 설명 |
|--------|------|
| id | 문서 ID |
| source | pubmed/orthobullets/guideline |
| title | 제목 |
| url | 원본 URL |
| body_part | 신체 부위 |
| bucket | 진단 버킷 |
| evidence_level | 근거 수준 |
| status | pending/approved/rejected |
| reviewer | 검토자 |
| notes | 검토 메모 |
| indexed_at | 인덱싱 시간 |

### 3.2 워크플로우

1. 크롤러가 데이터 수집 → Sheets에 `pending` 상태로 추가
2. 검토자가 내용 확인 후 `approved`/`rejected` 표시
3. 스케줄러가 `approved` 항목을 벡터 DB에 인덱싱
4. 인덱싱 완료 시 `indexed_at` 업데이트

---

## 4. 근거 기반 에이전트

### 4.1 에이전트 구조

```
EvidenceAgent
├── Tools
│   ├── PubMedSearchTool      # PubMed API 검색
│   ├── OrthoBulletsSearchTool # OrthoBullets 검색
│   ├── VectorSearchTool       # 내부 벡터 DB 검색
│   └── WebFetchTool           # 웹 페이지 크롤링
│
├── Reasoning
│   ├── EvidenceSynthesizer    # 근거 종합
│   └── ConfidenceEstimator    # 신뢰도 추정
│
└── Output
    ├── EvidenceSummary        # 근거 요약
    └── RecommendationWithCitations # 인용 포함 추천
```

### 4.2 에이전트 실행 예시

```python
# 사용자 쿼리
"60세 여성, 무릎 내측 통증, 계단 내려갈 때 악화 - 어떤 운동이 좋을까요?"

# 에이전트 추론 과정
1. 증상 분석 → OA 가능성 높음
2. PubMed 검색: "knee osteoarthritis exercise elderly women"
3. VectorDB 검색: 유사 케이스 + 관련 가이드라인
4. 근거 종합: OARSI 가이드라인 + 메타분석 3편
5. 운동 추천 with citations
```

---

## 5. 세분화된 파이프라인

### 5.1 기존 vs 개선

```
[기존]
Phase 1 → Phase 2 → Phase 3

[개선]
Phase 1: 입력 처리
├── 1-1. 입력 검증 (InputValidator)
├── 1-2. 레드플래그 체크 (RedFlagChecker)
├── 1-3. 증상 코드 매핑 (SymptomMapper)
└── 1-4. 다중 부위 우선순위 (BodyPartPrioritizer)

Phase 2: 진단
├── 2-1a. 가중치 계산 (WeightScorer)
├── 2-1b. 벡터 검색 (VectorSearcher)
├── 2-2. 불일치 감지 (DiscrepancyDetector)
├── 2-3. 근거 수집 (EvidenceCollector) ← 에이전트 호출
└── 2-4. LLM 버킷 결정 (BucketDecider)

Phase 3: 운동 처방
├── 3-1. 후보 필터링 (ExerciseFilter)
├── 3-2. 운동 선택 (ExerciseSelector)
├── 3-3. 세트/반복 조정 (DosageAdjuster)
└── 3-4. 루틴 구성 (RoutineBuilder)
```

### 5.2 각 스텝 관찰 포인트

| 스텝 | 관찰 항목 | 튜닝 파라미터 |
|------|----------|---------------|
| 1-2 | 레드플래그 감지율 | 임계값, 룰 추가 |
| 2-1a | 버킷별 점수 분포 | 가중치 조정 |
| 2-1b | 검색 결과 관련성 | top_k, threshold |
| 2-2 | 불일치 발생률 | 순위 차이 기준 |
| 2-3 | 근거 수/품질 | 검색 쿼리, 필터 |
| 3-1 | 후보 수 | 난이도/NRS 매핑 |

### 5.3 LangSmith 추적 계층

```
orthocare_pipeline (run)
├── phase1_input_processing (chain)
│   ├── input_validation (tool)
│   ├── red_flag_check (tool)
│   └── symptom_mapping (tool)
│
├── phase2_diagnosis (chain)
│   ├── weight_scoring (tool)
│   ├── vector_search (retriever)
│   ├── discrepancy_detection (tool)
│   ├── evidence_collection (agent)
│   │   ├── pubmed_search (tool)
│   │   └── vector_search (retriever)
│   └── bucket_decision (llm)
│
└── phase3_exercise (chain)
    ├── exercise_filtering (tool)
    ├── exercise_selection (llm)
    └── routine_building (tool)
```

---

## 6. 디렉토리 구조

```
orthocare/
├── config/
├── models/
├── services/
│   ├── input/
│   ├── scoring/
│   ├── evidence/
│   │   ├── vector_search.py
│   │   └── evidence_collector.py  # NEW
│   ├── diagnosis/
│   └── exercise/
│
├── agents/                        # NEW
│   ├── __init__.py
│   ├── evidence_agent.py
│   └── tools/
│       ├── __init__.py
│       ├── pubmed_tool.py
│       ├── orthobullets_tool.py
│       └── vector_search_tool.py
│
├── data_ops/
│   ├── loaders/
│   ├── crawlers/                  # NEW
│   │   ├── __init__.py
│   │   ├── pubmed_crawler.py
│   │   └── orthobullets_crawler.py
│   ├── indexing/                  # NEW
│   │   ├── __init__.py
│   │   ├── chunker.py
│   │   ├── embedder.py
│   │   └── indexer.py
│   └── sheets/                    # NEW
│       ├── __init__.py
│       └── sheets_client.py
│
├── pipelines/
│   ├── main_pipeline.py
│   └── steps/                     # NEW
│       ├── __init__.py
│       ├── phase1/
│       │   ├── input_validator.py
│       │   ├── red_flag_checker.py
│       │   └── symptom_mapper.py
│       ├── phase2/
│       │   ├── weight_scorer.py
│       │   ├── vector_searcher.py
│       │   ├── discrepancy_detector.py
│       │   └── bucket_decider.py
│       └── phase3/
│           ├── exercise_filter.py
│           ├── exercise_selector.py
│           └── routine_builder.py
│
└── evaluation/
```

---

## 7. 환경변수 추가

```env
# Google Sheets
GOOGLE_SHEETS_CREDENTIALS_PATH=credentials/service_account.json
REVIEW_SHEET_ID=1abc...xyz

# PubMed
NCBI_API_KEY=your_ncbi_api_key
PUBMED_EMAIL=your_email@example.com

# Crawling
CRAWL_RATE_LIMIT=1.0  # 초당 요청 수
CRAWL_CACHE_DIR=.cache/crawl
```

---

## 8. 구현 우선순위

### Phase 1: 기반 구축 (현재)
- [x] 인덱싱 스키마 설계
- [ ] 운동 DB 인덱싱
- [ ] 파이프라인 스텝 분리

### Phase 2: 크롤링 시스템
- [ ] PubMed 크롤러
- [ ] OrthoBullets 크롤러
- [ ] Sheets 연동

### Phase 3: 에이전트
- [ ] 도구 구현
- [ ] 에이전트 구현
- [ ] 파이프라인 통합
