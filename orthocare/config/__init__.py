# .env 파일을 가장 먼저 로드하여 LangSmith 등 외부 라이브러리가 환경변수를 읽을 수 있게 함
from dotenv import load_dotenv
load_dotenv(override=True)  # 기존 환경변수도 덮어씀

from .settings import settings
from .constants import BUCKETS, SYMPTOM_CODES

__all__ = ["settings", "BUCKETS", "SYMPTOM_CODES"]
