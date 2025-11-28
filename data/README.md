# Data 폴더 구조

```
data/
├── medical/                    # 의료 데이터 (진단 관련)
│   └── knee/
│       ├── weights.json        # 증상 → 버킷 가중치
│       ├── buckets.json        # 버킷 정의 (OA/OVR/TRM/INF)
│       ├── clinical_rules.json # 임상 규칙
│       ├── red_flags.json      # 레드플래그
│       ├── survey_mapping.json # 설문 → 증상코드 매핑
│       └── papers/
│           ├── original/       # 원본 PDF
│           ├── processed/      # 청크화된 텍스트/JSON
│           └── orthobullet/    # Orthobullet 크롤링 데이터
│
├── exercise/                   # 운동 데이터
│   └── knee/
│       └── exercises.json      # 운동 라이브러리 (50개)
│
├── evaluation/                 # 평가/테스트
│   ├── golden_set/            # 골든셋 페르소나
│   │   ├── knee_personas.json # 무릎 테스트 케이스
│   │   └── expected_results.json
│   └── test_results/          # 테스트 결과 저장
│       └── {timestamp}_results.json
│
├── crawling/                   # 크롤링
│   ├── scripts/               # 크롤링 스크립트
│   └── raw/                   # 크롤링 원본 데이터
│
├── check/                      # 전문가 리뷰 앱 관련
│   └── README.md              # 전문가 리뷰 시스템 스펙
│
├── shared/                     # 공통 데이터
│   └── physical_score.json    # 신체점수 레벨 정의
│
└── body_parts.json            # 지원 부위 목록
```

## 폴더별 역할

| 폴더 | 담당자 | 용도 |
|------|--------|------|
| `medical/` | 의사 | 진단 로직, 가중치, 임상 규칙 |
| `exercise/` | 트레이너 | 운동 라이브러리, 금기 조건 |
| `evaluation/` | 개발자 | 파이프라인 정확도 테스트 |
| `crawling/` | 개발자 | Orthobullet/PubMed 크롤링 |
| `check/` | 개발자 | 전문가 리뷰 앱 스펙 |
