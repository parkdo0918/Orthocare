"""로깅 유틸리티"""

import logging
import sys
from typing import Optional


def get_logger(
    name: str,
    level: int = logging.INFO,
    format_string: Optional[str] = None,
) -> logging.Logger:
    """
    로거 인스턴스 생성

    Args:
        name: 로거 이름 (보통 __name__)
        level: 로그 레벨
        format_string: 포맷 문자열

    Returns:
        logging.Logger 인스턴스
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        # 이미 핸들러가 있으면 반환
        return logger

    logger.setLevel(level)

    # 포맷 설정
    if format_string is None:
        format_string = (
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        )
    formatter = logging.Formatter(format_string)

    # 콘솔 핸들러
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
