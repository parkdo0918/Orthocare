# 배포 가이드

## 로컬 테스트

### 1. 게이트웨이 로컬 실행

```bash
# 환경 변수 설정 (.env 파일 또는 export)
export OPENAI_API_KEY="your-key"
export PINECONE_API_KEY="your-key"

# 게이트웨이 실행 (포트 8000)
PYTHONPATH=. python -m gateway.main
```

다른 포트 사용:
```bash
GATEWAY_PORT=8001 PYTHONPATH=. python -m gateway.main
```

### 2. Docker Compose로 전체 서비스 실행

```bash
# 모든 서비스 실행 (gateway, bucket-inference, exercise-recommendation)
docker-compose up

# 게이트웨이만 실행
docker-compose up gateway
```

---

## Railway 배포

### 게이트웨이 서비스 배포

Railway에 게이트웨이를 배포하려면:

1. **Railway 프로젝트 생성**
   - Railway 대시보드에서 새 프로젝트 생성
   - GitHub 저장소 연결 (또는 직접 배포)

2. **서비스 추가**
   - 새 서비스 추가
   - Dockerfile 경로: `gateway/Dockerfile`

3. **환경 변수 설정**
   Railway 대시보드 → Variables 탭에서 다음 변수 설정:
   ```
   OPENAI_API_KEY=sk-...
   PINECONE_API_KEY=...
   USE_LANGGRAPH_BUCKET=true
   ```

4. **배포**
   - GitHub 연결 시 자동 배포
   - 또는 Railway CLI 사용:
   ```bash
   railway up
   ```

### Railway CLI 사용 (선택)

```bash
# Railway CLI 설치
npm i -g @railway/cli

# 로그인
railway login

# 프로젝트 선택
railway link

# 환경 변수 설정
railway variables set OPENAI_API_KEY=sk-...
railway variables set PINECONE_API_KEY=...

# 배포
railway up
```

---

## 배포 확인

### 1. 헬스 체크

```bash
curl https://your-app.railway.app/health
```

### 2. API 테스트

```bash
# 테스트 스크립트 사용
python test_railway_api.py https://your-app.railway.app
```

---

## 문제 해결

### Connection Error 발생 시

1. **환경 변수 확인**
   - Railway 대시보드 → Variables 탭
   - `OPENAI_API_KEY`, `PINECONE_API_KEY` 설정 확인

2. **로그 확인**
   - Railway 대시보드 → Deployments → Logs
   - 에러 메시지 확인

3. **자세한 가이드**
   - `RAILWAY_DEPLOYMENT_CHECKLIST.md` 참고

---

## 파일 구조

```
.
├── gateway/
│   ├── Dockerfile          # 게이트웨이 Dockerfile
│   ├── main.py             # FastAPI 앱
│   ├── models/
│   └── services/
├── bucket_inference/       # 버킷 추론 모듈 (게이트웨이에서 import)
├── exercise_recommendation/ # 운동 추천 모듈 (게이트웨이에서 import)
├── shared/                 # 공유 모듈
├── data/                   # 데이터 파일
├── docker-compose.yml      # 로컬 테스트용
└── requirements.txt        # 공통 의존성
```

---

## 참고

- 게이트웨이는 HTTP로 다른 서비스를 호출하지 않고 Python 모듈을 직접 import
- 따라서 단일 컨테이너로 배포 가능 (게이트웨이만 배포하면 됨)
- 환경 변수만 설정하면 동작

