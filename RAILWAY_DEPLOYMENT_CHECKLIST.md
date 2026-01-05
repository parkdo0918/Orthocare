# Railway 배포 체크리스트

## Connection Error 해결 가이드

### 문제
모든 API 요청에서 "Connection error" 발생 (500 에러)

### 원인 분석

게이트웨이는 HTTP로 내부 서비스를 호출하지 않고, Python 파이프라인을 직접 import해서 사용합니다.
따라서 "Connection error"는 **외부 서비스(Pinecone, OpenAI) 연결 문제**일 가능성이 높습니다.

---

## 필수 환경 변수 확인

Railway 대시보드에서 다음 환경 변수가 설정되어 있는지 확인:

### 필수 환경 변수

1. **OpenAI API Key**
   - 변수명: `OPENAI_API_KEY`
   - 용도: LLM 추론 및 임베딩 생성

2. **Pinecone API Key**
   - 변수명: `PINECONE_API_KEY`
   - 용도: 벡터 DB 검색

3. **Pinecone 인덱스 (선택)**
   - 변수명: `PINECONE_INDEX_DIAGNOSIS` (기본값: `orthocare-diagnosis`)
   - 변수명: `PINECONE_INDEX_EXERCISE` (기본값: `orthocare-exercise`)

### 확인 방법

1. Railway 대시보드 접속
2. 게이트웨이 서비스 선택
3. "Variables" 탭 확인
4. 위 환경 변수들이 모두 설정되어 있는지 확인

---

## 디버깅 단계

### 1단계: 환경 변수 확인

```bash
# Railway CLI로 확인 (또는 대시보드에서)
railway variables
```

확인 사항:
- ✅ `OPENAI_API_KEY` 설정됨
- ✅ `PINECONE_API_KEY` 설정됨

### 2단계: 로그 확인

Railway 대시보드에서 게이트웨이 서비스의 로그를 확인:

1. 게이트웨이 서비스 선택
2. "Deployments" 탭
3. 최근 배포 클릭
4. "Logs" 탭 확인

찾아야 할 내용:
- Pinecone 연결 에러
- OpenAI API 에러
- 환경 변수 미설정 에러

### 3단계: 테스트 재실행

환경 변수를 설정한 후:

```bash
python test_railway_api.py https://orthocare-production-7b4d.up.railway.app
```

---

## 예상되는 에러 유형

### 1. Pinecone 연결 실패

**에러 메시지 예시:**
- `PINECONE_API_KEY가 설정되지 않았습니다.`
- `Connection error`
- `Pinecone API error`

**해결:**
- Railway 환경 변수에 `PINECONE_API_KEY` 추가
- Pinecone 대시보드에서 API 키 확인

### 2. OpenAI API 연결 실패

**에러 메시지 예시:**
- `OPENAI_API_KEY가 설정되지 않았습니다.`
- `API key not found`
- `Invalid API key`

**해결:**
- Railway 환경 변수에 `OPENAI_API_KEY` 추가
- OpenAI 대시보드에서 API 키 확인

---

## 빠른 해결 방법

### Railway 대시보드에서 환경 변수 추가

1. Railway 대시보드 접속
2. 게이트웨이 서비스 선택
3. "Variables" 탭 클릭
4. "New Variable" 클릭
5. 다음 변수 추가:

```
OPENAI_API_KEY=sk-...
PINECONE_API_KEY=...
```

6. "Deploy" 버튼 클릭 (자동 재배포)

---

## 추가 확인 사항

### 데이터 디렉토리

게이트웨이는 `data/` 디렉토리의 설정 파일을 사용합니다:
- `data/medical/knee/`
- `data/medical/shoulder/`
- `data/exercise/`

Railway 배포 시 이 파일들이 포함되어 있는지 확인:

1. `.dockerignore` 확인
2. Dockerfile에서 `data/` 디렉토리 복사 확인

---

## 에러 메시지 개선

코드 수정으로 더 자세한 에러 메시지 제공 (gateway/main.py):

```python
except Exception as e:
    error_detail = f"{type(e).__name__}: {str(e)}"
    raise HTTPException(
        status_code=500,
        detail=f"처리 실패: {error_detail}"
    )
```

이제 실제 예외 타입과 메시지가 표시됩니다.

---

## 참고

- 테스트 스크립트: `test_railway_api.py`
- 배포 URL: https://orthocare-production-7b4d.up.railway.app
- Swagger UI: https://orthocare-production-7b4d.up.railway.app/docs

