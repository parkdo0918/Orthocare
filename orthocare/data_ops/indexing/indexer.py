"""Pinecone 인덱싱 모듈"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
import hashlib
import json

from langsmith import traceable

from .chunker import Chunk, DocumentChunker
from .embedder import TextEmbedder, EmbeddingResult


@dataclass
class IndexDocument:
    """인덱싱할 문서"""
    id: str
    text: str
    source: str  # pubmed, orthobullets, guideline, exercise
    source_id: str  # PMID, URL 등
    title: str
    body_part: Optional[str] = None
    bucket: Optional[str] = None
    evidence_level: Optional[str] = None
    year: Optional[int] = None
    url: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None


@dataclass
class IndexResult:
    """인덱싱 결과"""
    document_id: str
    chunks_count: int
    vectors_upserted: int
    success: bool
    error: Optional[str] = None


class PineconeIndexer:
    """
    Pinecone 벡터 DB 인덱서

    문서를 청킹하고 임베딩한 후 Pinecone에 업서트
    """

    def __init__(
        self,
        pinecone_index,
        openai_client=None,
        namespace: str = "",
        chunker: Optional[DocumentChunker] = None,
        embedder: Optional[TextEmbedder] = None,
    ):
        """
        Args:
            pinecone_index: Pinecone Index 객체
            openai_client: OpenAI 클라이언트
            namespace: Pinecone 네임스페이스
            chunker: DocumentChunker 인스턴스
            embedder: TextEmbedder 인스턴스
        """
        self.index = pinecone_index
        self.namespace = namespace
        self.chunker = chunker or DocumentChunker()
        self.embedder = embedder or TextEmbedder(openai_client)

    @traceable(name="index_document")
    def index_document(self, doc: IndexDocument) -> IndexResult:
        """
        단일 문서 인덱싱

        Args:
            doc: 인덱싱할 문서

        Returns:
            IndexResult 객체
        """
        try:
            # 1. 청킹
            chunks = self.chunker.chunk_document(
                text=doc.text,
                metadata={
                    "source": doc.source,
                    "source_id": doc.source_id,
                    "title": doc.title,
                    "body_part": doc.body_part,
                    "bucket": doc.bucket,
                    "evidence_level": doc.evidence_level,
                    "year": doc.year,
                    "url": doc.url,
                }
            )

            if not chunks:
                return IndexResult(
                    document_id=doc.id,
                    chunks_count=0,
                    vectors_upserted=0,
                    success=True,
                )

            # 2. 임베딩
            texts = [c.text for c in chunks]
            embeddings = self.embedder.embed_batch(texts, show_progress=False)

            # 3. 벡터 준비
            vectors = []
            for chunk, emb in zip(chunks, embeddings):
                vector_id = f"{doc.id}_chunk_{chunk.chunk_index}"

                # 메타데이터에서 None 값 필터링 (Pinecone은 null 허용 안함)
                metadata = {
                    **chunk.metadata,
                    "text": chunk.text[:1000],  # 메타데이터 크기 제한
                    "chunk_index": chunk.chunk_index,
                    "total_chunks": chunk.total_chunks,
                    "document_id": doc.id,
                }
                # None 값 제거
                metadata = {k: v for k, v in metadata.items() if v is not None}

                vectors.append({
                    "id": vector_id,
                    "values": emb.embedding,
                    "metadata": metadata,
                })

            # 4. Pinecone 업서트
            self.index.upsert(vectors=vectors, namespace=self.namespace)

            return IndexResult(
                document_id=doc.id,
                chunks_count=len(chunks),
                vectors_upserted=len(vectors),
                success=True,
            )

        except Exception as e:
            return IndexResult(
                document_id=doc.id,
                chunks_count=0,
                vectors_upserted=0,
                success=False,
                error=str(e),
            )

    @traceable(name="index_documents_batch")
    def index_documents(
        self,
        docs: List[IndexDocument],
        show_progress: bool = True,
    ) -> List[IndexResult]:
        """
        다중 문서 인덱싱

        Args:
            docs: 문서 리스트
            show_progress: 진행률 표시 여부

        Returns:
            IndexResult 리스트
        """
        results = []
        total = len(docs)

        for i, doc in enumerate(docs):
            if show_progress:
                print(f"[{i+1}/{total}] {doc.title[:50]}...")

            result = self.index_document(doc)
            results.append(result)

            if not result.success:
                print(f"  ⚠ 실패: {result.error}")

        return results

    def delete_document(self, document_id: str) -> bool:
        """
        문서 삭제 (모든 청크)

        Args:
            document_id: 삭제할 문서 ID

        Returns:
            성공 여부
        """
        try:
            # 문서의 모든 청크 ID 조회 후 삭제
            # Pinecone은 prefix 삭제를 지원하지 않으므로 메타데이터 필터 사용
            self.index.delete(
                filter={"document_id": {"$eq": document_id}},
                namespace=self.namespace,
            )
            return True
        except Exception:
            return False

    def get_stats(self) -> Dict[str, Any]:
        """인덱스 통계 조회"""
        return self.index.describe_index_stats()


def generate_document_id(source: str, source_id: str) -> str:
    """
    문서 ID 생성

    Args:
        source: 소스 타입 (pubmed, orthobullets 등)
        source_id: 소스별 고유 ID

    Returns:
        해시 기반 문서 ID
    """
    raw = f"{source}:{source_id}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]
