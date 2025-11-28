# OrthoCare

> 근거 기반 무릎 진단 및 운동 추천 AI 파이프라인

## 개요

OrthoCare는 자연어 증상 입력을 분석하여 무릎 통증의 원인을 진단하고, 의학 논문 근거에 기반한 맞춤형 운동 프로그램을 추천하는 AI 시스템입니다.

### 주요 기능

- **3-Layer 근거 검색**: 검증된 논문 → OrthoBullets → PubMed 순으로 신뢰도 높은 근거 우선 제공
- **버킷 기반 진단**: 4가지 카테고리(OA/OVR/TRM/INF)로 무릎 통증 분류
- **Anti-Hallucination**: LLM이 실제 검색된 문서만 인용 (가짜 논문 인용 방지)
- **맞춤형 운동 추천**: 진단 결과와 신체 상태에 따른 운동 프로그램 생성

## 아키텍처

```
[자연어 입력] → [증상 추출] → [벡터 검색] → [LLM 추론] → [버킷 결정] → [운동 추천]
                                  ↓
                        ┌─────────────────┐
                        │ Pinecone 벡터DB │
                        │ - 논문 (Layer 1) │
                        │ - OrthoBullets  │
                        │ - 운동 데이터    │
                        └─────────────────┘
```

## 버킷 분류

| 버킷 | 의미 | 예시 |
|------|------|------|
| **OA** | Osteoarthritis (퇴행성) | 골관절염, 연골 마모 |
| **OVR** | Overuse (과사용) | 러너스니, 슬개대퇴 증후군 |
| **TRM** | Trauma (외상) | ACL 손상, 반월판 파열 |
| **INF** | Inflammatory (염증) | 화농성 관절염, 통풍 |

## 설치

```bash
# 저장소 클론
git clone https://github.com/3mlnssaco/Orthocare.git
cd Orthocare

# 가상환경 생성
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt

# 환경변수 설정
cp .env.example .env
# .env 파일에 API 키 입력
```

### 필수 환경변수

```bash
OPENAI_API_KEY=sk-...
PINECONE_API_KEY=...
PINECONE_INDEX=orthocare
PINECONE_HOST=...  # 선택사항
```

## 사용법

### 1. 데이터 인덱싱

```bash
# 전체 인덱싱 (논문 + 운동 + OrthoBullets)
PYTHONPATH=. python scripts/run_indexing.py

# 논문만 재인덱싱
PYTHONPATH=. python scripts/run_indexing.py --papers-only
```

### 2. E2E 테스트

```bash
# 기본 테스트 (첫 번째 페르소나)
PYTHONPATH=. python scripts/test_e2e.py

# 모든 페르소나 테스트
PYTHONPATH=. python scripts/test_e2e.py --all

# 특정 페르소나 테스트
PYTHONPATH=. python scripts/test_e2e.py --persona GS-OA-001
```

테스트 결과는 `data/evaluation/test_results/YYYY-MM-DD/`에 저장됩니다:
- `run_001_GS-OA-001.json` - 건별 상세 결과
- `REPORT.md` - 종합 리포트

### 3. 파이프라인 실행

```python
from orthocare.pipelines import GranularPipeline
from openai import OpenAI
from pinecone import Pinecone

# 클라이언트 초기화
openai_client = OpenAI()
pc = Pinecone()
index = pc.Index("orthocare")

# 파이프라인 실행
pipeline = GranularPipeline(
    llm_client=openai_client,
    vector_store=index,
)

result = pipeline.run({
    "body_parts": [{
        "code": "knee",
        "symptoms": ["무릎 통증", "아침 뻣뻣함", "계단 오르기 어려움"]
    }],
    "natural_language": {
        "chief_complaint": "55세 여성, 3개월 전부터 무릎이 아파요"
    }
})

print(result.diagnoses["knee"].final_bucket)  # OA
print(result.diagnoses["knee"].llm_reasoning)  # 추론 근거
```

### 4. 앱용 출력 (Phase 3-4)

앱에서는 질환 버킷(OA, TRM 등)을 사용자에게 직접 노출하지 않고, 친근한 메시지와 운동 테이블만 제공합니다.

```python
# 파이프라인 실행 후 앱용 출력 생성
result = pipeline.run(input_data)

# JSON 형식 (API 응답용)
app_output = pipeline.generate_app_output(result)

# 마크다운 형식 (화면 표시용)
app_markdown = pipeline.generate_app_markdown(result)
```

**앱용 JSON 출력 예시:**

```json
{
  "user_summary": {
    "age": 55,
    "physical_level": "C"
  },
  "body_parts": [
    {
      "code": "knee",
      "name": "무릎",
      "intro_message": "무릎 상태를 분석한 결과, 맞춤 운동을 추천해드려요.",
      "exercise_intro": "현재 상태에 도움이 되는 운동들이에요",
      "total_duration_min": 15,
      "exercises": [
        {
          "name": "힐 슬라이드",
          "difficulty": "쉬움",
          "sets": 2,
          "reps": "10회",
          "rest": "30초",
          "reason": "ROM 개선에 효과적",
          "youtube": "https://youtube.com/..."
        },
        {
          "name": "대퇴사두근 수축",
          "difficulty": "쉬움",
          "sets": 3,
          "reps": "10회",
          "rest": "30초",
          "reason": "근력 유지에 도움",
          "youtube": null
        }
      ],
      "red_flag": null
    }
  ]
}
```

**앱용 마크다운 출력 예시:**

```markdown
### 무릎

무릎 상태를 분석한 결과, 맞춤 운동을 추천해드려요.

**현재 상태에 도움이 되는 운동들이에요** (총 15분)

| 운동 | 난이도 | 세트 | 반복 | 휴식 |
|------|--------|------|------|------|
| [힐 슬라이드](https://youtube.com/...) | 쉬움 | 2 | 10회 | 30초 |
| 대퇴사두근 수축 | 쉬움 | 3 | 10회 | 30초 |
| 클램쉘 | 보통 | 2 | 15회 | 30초 |
```

**레드플래그 시 출력:**

```markdown
⚠️ **주의가 필요해요**
> 발열과 함께 심한 부종이 있습니다. 전문의 상담을 권장합니다.
```

## 프로젝트 구조

```
orthocare/
├── config/           # 설정 (API 키, 상수)
├── models/           # 데이터 모델
├── services/
│   ├── diagnosis/    # 버킷 판정 (LLM)
│   ├── evidence/     # 3-Layer 검색
│   ├── exercise/     # 운동 추천
│   └── input/        # 입력 검증
├── pipelines/        # 전체 오케스트레이션
└── data_ops/
    ├── indexing/     # 벡터 인덱싱
    └── crawlers/     # 데이터 수집

data/
├── medical/knee/papers/     # 논문 (PDF + 청크)
├── crawled/                 # OrthoBullets 캐시
├── exercise/knee/           # 운동 라이브러리
└── evaluation/              # 테스트 결과

scripts/
├── run_indexing.py          # 인덱싱 스크립트
├── test_e2e.py              # E2E 테스트
└── crawl_orthobullets.py    # 크롤링 (현재 비활성)
```

## 기술 스택

- **LLM**: OpenAI GPT-4
- **벡터 DB**: Pinecone (3072차원, text-embedding-3-large)
- **트레이싱**: LangSmith
- **언어**: Python 3.11+

## LLM 인용 규칙

이 시스템은 LLM이 **실제 검색된 문서만 인용**하도록 설계되었습니다:

```
## 인용 규칙 (Anti-Hallucination)
- 벡터 DB 검색 결과에 있는 문서만 인용
- 존재하지 않는 논문/가이드라인 생성 금지
- 인용 형식: "제목" [source] - "관련 내용"
```

출력 예시:
```
## 근거 문서
1. **Knee Osteoarthritis - OrthoBullets** [orthobullets]
   > "Risk factors: age, obesity, prior injury. Morning stiffness <30 minutes."
2. **Duncan 2008** [verified_paper]
   > "Pain is the most common symptom in knee OA..."
```

## 라이선스

MIT License

## 기여

이슈 및 PR 환영합니다.
