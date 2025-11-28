"""문서 청킹 모듈"""

import re
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import tiktoken


@dataclass
class Chunk:
    """청크 데이터"""
    text: str
    chunk_index: int
    total_chunks: int
    metadata: Dict[str, Any]


class DocumentChunker:
    """
    문서를 벡터 DB 인덱싱용 청크로 분할

    전략:
    - 최대 512 토큰 (text-embedding-3-large 최적화)
    - 100 토큰 오버랩 (문맥 유지)
    - 문단/문장 경계 우선
    """

    def __init__(
        self,
        max_tokens: int = 512,
        overlap_tokens: int = 100,
        model: str = "cl100k_base",  # GPT-4/text-embedding-3 tokenizer
    ):
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens
        self.tokenizer = tiktoken.get_encoding(model)

    def chunk_document(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Chunk]:
        """
        문서를 청크로 분할

        Args:
            text: 원본 텍스트
            metadata: 청크에 포함할 메타데이터

        Returns:
            Chunk 리스트
        """
        if not text or not text.strip():
            return []

        metadata = metadata or {}

        # 1. 문단으로 먼저 분할
        paragraphs = self._split_paragraphs(text)

        # 2. 토큰 제한에 맞게 청크 생성
        chunks = []
        current_chunk = []
        current_tokens = 0

        for para in paragraphs:
            para_tokens = len(self.tokenizer.encode(para))

            # 단일 문단이 max_tokens 초과 시 문장 단위로 분할
            if para_tokens > self.max_tokens:
                # 현재 청크 저장
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                    current_chunk = []
                    current_tokens = 0

                # 긴 문단을 문장 단위로 분할
                sentence_chunks = self._chunk_by_sentences(para)
                chunks.extend(sentence_chunks)

            # 현재 청크에 추가 가능한 경우
            elif current_tokens + para_tokens <= self.max_tokens:
                current_chunk.append(para)
                current_tokens += para_tokens

            # 새 청크 시작
            else:
                if current_chunk:
                    chunks.append(" ".join(current_chunk))

                # 오버랩: 이전 청크의 마지막 부분 포함
                overlap_text = self._get_overlap(current_chunk)
                current_chunk = [overlap_text, para] if overlap_text else [para]
                current_tokens = len(self.tokenizer.encode(" ".join(current_chunk)))

        # 마지막 청크 저장
        if current_chunk:
            chunks.append(" ".join(current_chunk))

        # Chunk 객체로 변환
        total = len(chunks)
        return [
            Chunk(
                text=chunk_text.strip(),
                chunk_index=i,
                total_chunks=total,
                metadata={**metadata},
            )
            for i, chunk_text in enumerate(chunks)
            if chunk_text.strip()
        ]

    def _split_paragraphs(self, text: str) -> List[str]:
        """문단 분할"""
        # 연속 줄바꿈으로 분할
        paragraphs = re.split(r'\n\s*\n', text)
        return [p.strip() for p in paragraphs if p.strip()]

    def _chunk_by_sentences(self, text: str) -> List[str]:
        """문장 단위 청킹 (긴 문단용)"""
        # 문장 분할 (마침표, 물음표, 느낌표)
        sentences = re.split(r'(?<=[.!?])\s+', text)

        chunks = []
        current_chunk = []
        current_tokens = 0

        for sentence in sentences:
            sent_tokens = len(self.tokenizer.encode(sentence))

            if current_tokens + sent_tokens <= self.max_tokens:
                current_chunk.append(sentence)
                current_tokens += sent_tokens
            else:
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                current_chunk = [sentence]
                current_tokens = sent_tokens

        if current_chunk:
            chunks.append(" ".join(current_chunk))

        return chunks

    def _get_overlap(self, chunks: List[str]) -> str:
        """오버랩 텍스트 추출"""
        if not chunks:
            return ""

        # 마지막 청크에서 overlap_tokens만큼 추출
        full_text = " ".join(chunks)
        tokens = self.tokenizer.encode(full_text)

        if len(tokens) <= self.overlap_tokens:
            return full_text

        overlap_tokens = tokens[-self.overlap_tokens:]
        return self.tokenizer.decode(overlap_tokens)

    def count_tokens(self, text: str) -> int:
        """토큰 수 계산"""
        return len(self.tokenizer.encode(text))
