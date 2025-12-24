# OrthoCare 변경 이력

> 모든 주요 변경사항을 기록합니다.

---

## [V3.1] - 2025-12-24

### 추가
- **LangGraph 버킷 추론 파이프라인**
  - `bucket_inference/pipeline/langgraph_pipeline.py` 신규
  - 기존 대비 32% 성능 향상 (10.4초 → 7.1초)
  - 그래프 시각화 지원 (Mermaid)
  - 체크포인트/재시도 지원

- **통합 Gateway 아키텍처**
  - `gateway/` 서비스 신규
  - POST `/api/v1/diagnose-and-recommend` 단일 엔드포인트
  - Red Flag 감지 시 운동 추천 자동 스킵
  - 버킷 추론 컨텍스트 → 운동 추천 개인화 전달

- **문서화**
  - `docs/backend-integration.md` - 백엔드 통합 가이드
  - `docs/medical-review.md` - 임상 검토 문서
  - `docs/architecture/langgraph.md` - LangGraph 아키텍처
  - `docs/INDEX.md` - 문서 인덱스
  - `docs/CHANGELOG.md` - 변경 이력

### 변경
- **OrchestrationService** - LangGraph 버킷 추론 기본값
  - `USE_LANGGRAPH_BUCKET=false` 환경변수로 폴백 가능
- **README.md** - Gateway 아키텍처, 다중 부위 지원 추가

### 수정
- `min_search_score` 0.35 → 0.15 (벡터 검색 결과 필터링 완화)
- `difficulty` 필드 타입 Literal → str (데이터 호환성)
- 무릎 weights.json 증상 코드 별칭 추가

---

## [V3.0] - 2025-12-04

### 추가
- **마이크로서비스 분리**
  - `bucket_inference/` (port 8001)
  - `exercise_recommendation/` (port 8002)
  - 벡터 DB 분리 (diagnosis / exercise)

- **다중 부위 지원 (Config-Driven)**
  - 무릎 (knee) - 버킷: OA, OVR, TRM, INF
  - 어깨 (shoulder) - 버킷: OA, OVR, TRM, STF
  - `data/medical/{body_part}/` 설정 파일

- **어깨 진단 시스템**
  - 동결견(STF) 버킷 추가
  - 어깨 전용 가중치, 설문 매핑

### 변경
- 단일 파이프라인 → 마이크로서비스 분리
- 부위별 설정 파일 분리

---

## [V2.0] - 2025-11-29

### 추가
- **사후 평가 시스템 (RPE 기반)**
  - 3세션 RPE 합계 기반 난이도 자동 조정
  - AssessmentHandler 케이스 처리

- **개인화 강화**
  - 연령/BMI/NRS 기반 운동 조정
  - 기능 태그별 우선순위 부스트

### 변경
- 운동 추천 알고리즘 고도화

---

## [V1.0] - 2025-11-15

### 추가
- 초기 버전
- 무릎 버킷 추론 (OA/OVR/TRM/INF)
- 운동 추천 기본 기능
- 3-Layer 근거 검색

---

## 버전 관리 규칙

| 버전 | 설명 |
|------|------|
| X.0 | 주요 아키텍처 변경 |
| X.Y | 기능 추가/개선 |
| X.Y.Z | 버그 수정 |
