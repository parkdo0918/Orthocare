"""벡터 DB 인덱싱 파이프라인

운동 데이터, 논문, 크롤링 자료 등을 Pinecone에 인덱싱
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from langsmith import traceable

from orthocare.config import settings
from .indexer import PineconeIndexer, IndexDocument, IndexResult, generate_document_id
from .chunker import DocumentChunker
from .embedder import TextEmbedder


@dataclass
class IndexingConfig:
    """인덱싱 설정"""
    namespace: str = ""
    chunk_max_tokens: int = 512
    chunk_overlap_tokens: int = 100
    batch_size: int = 50
    show_progress: bool = True


class ExerciseIndexer:
    """운동 데이터 인덱서"""

    def __init__(self, indexer: PineconeIndexer, config: IndexingConfig = None):
        self.indexer = indexer
        self.config = config or IndexingConfig()

    @traceable(name="index_exercises")
    def index_exercises(
        self,
        body_part: str,
        exercises_data: Dict[str, Any],
    ) -> List[IndexResult]:
        """
        운동 데이터 인덱싱

        Args:
            body_part: 부위 코드
            exercises_data: exercises.json의 exercises 딕셔너리

        Returns:
            IndexResult 리스트
        """
        docs = []

        for exercise_id, exercise in exercises_data.items():
            # 운동 설명 텍스트 구성
            text_parts = [
                f"운동명: {exercise.get('name_kr', exercise.get('name_en', ''))}",
                f"영문명: {exercise.get('name_en', '')}",
                f"설명: {exercise.get('description', '')}",
                f"대상 근육: {', '.join(exercise.get('target_muscles', []))}",
                f"난이도: {exercise.get('difficulty', '')}",
                f"세트: {exercise.get('sets', '')}회",
                f"반복: {exercise.get('reps', '')}",
                f"휴식: {exercise.get('rest', '')}",
            ]

            # 기능 태그, 진단 태그 추가
            if exercise.get('function_tags'):
                text_parts.append(f"기능: {', '.join(exercise.get('function_tags', []))}")
            if exercise.get('diagnosis_tags'):
                text_parts.append(f"적용 진단: {', '.join(exercise.get('diagnosis_tags', []))}")

            text = "\n".join(text_parts)

            doc = IndexDocument(
                id=generate_document_id("exercise", f"{body_part}_{exercise_id}"),
                text=text,
                source="exercise",
                source_id=exercise_id,
                title=exercise.get('name_kr', exercise.get('name_en', '')),
                body_part=body_part,
                bucket=",".join(exercise.get('diagnosis_tags', [])),
                url=exercise.get('youtube', ''),
                extra={
                    "difficulty": exercise.get('difficulty'),
                    "sets": exercise.get('sets'),
                    "reps": exercise.get('reps'),
                    "function_tags": exercise.get('function_tags', []),
                    "target_muscles": exercise.get('target_muscles', []),
                }
            )
            docs.append(doc)

        if self.config.show_progress:
            print(f"[Exercise] {body_part}: {len(docs)}개 운동 인덱싱...")

        return self.indexer.index_documents(docs, show_progress=self.config.show_progress)


class PaperIndexer:
    """논문 데이터 인덱서"""

    def __init__(self, indexer: PineconeIndexer, config: IndexingConfig = None):
        self.indexer = indexer
        self.config = config or IndexingConfig()
        self._paper_metadata_cache: Optional[Dict] = None

    def _load_paper_metadata(self, body_part: str) -> Dict:
        """논문 메타데이터 파일 로드"""
        if self._paper_metadata_cache is not None:
            return self._paper_metadata_cache

        metadata_path = settings.data_dir / "medical" / body_part / "papers" / "paper_metadata.json"
        if metadata_path.exists():
            with open(metadata_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self._paper_metadata_cache = data.get("papers", {})
        else:
            self._paper_metadata_cache = {}

        return self._paper_metadata_cache

    @traceable(name="index_paper_chunks")
    def index_paper_chunks(
        self,
        paper_id: str,
        chunks: List[Dict[str, Any]],
        body_part: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[IndexResult]:
        """
        논문 청크 인덱싱

        Args:
            paper_id: 논문 ID (파일명 등)
            chunks: 청크 데이터 리스트
            body_part: 부위 코드
            metadata: 추가 메타데이터

        Returns:
            IndexResult 리스트
        """
        metadata = metadata or {}

        # 논문 메타데이터에서 버킷/소스 정보 가져오기
        paper_metadata = self._load_paper_metadata(body_part)
        paper_info = paper_metadata.get(paper_id, {})

        # 버킷 태그: 메타데이터에서 가져오거나 기본값 사용
        bucket_tags = paper_info.get("buckets", [])
        bucket = ",".join(bucket_tags) if bucket_tags else "general"

        # 소스 타입: verified_paper, pubmed, orthobullets
        source_type = paper_info.get("source_type", "paper")

        # 제목: 메타데이터 > 전달된 metadata > paper_id
        title = paper_info.get("title") or metadata.get('title') or paper_id

        # 연도 및 근거 수준
        year = paper_info.get("year") or metadata.get('year')
        evidence_level = paper_info.get("evidence_level") or metadata.get('evidence_level')

        docs = []

        for chunk in chunks:
            # text가 없는 청크는 스킵
            chunk_text = chunk.get('text', '').strip()
            if not chunk_text:
                continue

            doc = IndexDocument(
                id=generate_document_id("paper", f"{paper_id}_{chunk.get('id', 0)}"),
                text=chunk_text,
                source=source_type,  # verified_paper, pubmed, orthobullets
                source_id=paper_id,
                title=title,
                body_part=body_part,
                bucket=bucket,  # "OA,OVR" 형태
                evidence_level=evidence_level,
                year=year,
                extra={
                    "chunk_type": chunk.get('type', 'content'),
                    "chunk_index": chunk.get('id', 0),
                    "bucket_tags": bucket_tags,  # 리스트 형태도 보존
                }
            )
            docs.append(doc)

        return self.indexer.index_documents(docs, show_progress=self.config.show_progress)

    @traceable(name="index_papers_from_directory")
    def index_papers_from_directory(
        self,
        papers_dir: Path,
        body_part: str,
    ) -> Dict[str, Any]:
        """
        디렉토리의 모든 논문 청크 인덱싱

        Args:
            papers_dir: 논문 청크 JSON 파일들이 있는 디렉토리
            body_part: 부위 코드

        Returns:
            인덱싱 통계
        """
        stats = {"total_papers": 0, "total_chunks": 0, "success": 0, "failed": 0}

        if not papers_dir.exists():
            print(f"  ⚠ 디렉토리 없음: {papers_dir}")
            return stats

        chunk_files = list(papers_dir.glob("*_chunks.json"))

        if self.config.show_progress:
            print(f"[Papers] {body_part}: {len(chunk_files)}개 논문 발견...")

        for chunk_file in chunk_files:
            try:
                with open(chunk_file, 'r', encoding='utf-8') as f:
                    chunks = json.load(f)

                paper_id = chunk_file.stem.replace("_chunks", "")
                results = self.index_paper_chunks(paper_id, chunks, body_part)

                stats["total_papers"] += 1
                stats["total_chunks"] += len(chunks)

                for r in results:
                    if r.success:
                        stats["success"] += 1
                    else:
                        stats["failed"] += 1

            except Exception as e:
                print(f"  ⚠ 파일 처리 실패 ({chunk_file.name}): {e}")
                stats["failed"] += 1

        return stats


class CrawledDataIndexer:
    """크롤링 데이터 인덱서"""

    def __init__(self, indexer: PineconeIndexer, config: IndexingConfig = None):
        self.indexer = indexer
        self.config = config or IndexingConfig()

    @traceable(name="index_pubmed_articles")
    def index_pubmed_articles(
        self,
        articles: List[Any],  # PubMedArticle
        body_part: str = "general",
    ) -> List[IndexResult]:
        """
        PubMed 논문 인덱싱

        Args:
            articles: PubMedArticle 리스트
            body_part: 부위 코드

        Returns:
            IndexResult 리스트
        """
        docs = []

        for article in articles:
            # 제목 + 초록 조합
            text = f"제목: {article.title}\n\n초록: {article.abstract}"

            doc = IndexDocument(
                id=generate_document_id("pubmed", article.pmid),
                text=text,
                source="pubmed",
                source_id=article.pmid,
                title=article.title,
                body_part=body_part,
                bucket="research",
                year=article.year,
                url=article.url,
                extra={
                    "authors": article.authors[:5],  # 상위 5명만
                    "journal": article.journal,
                    "doi": article.doi,
                    "mesh_terms": article.mesh_terms[:10],
                    "keywords": article.keywords[:10],
                }
            )
            docs.append(doc)

        if self.config.show_progress:
            print(f"[PubMed] {len(docs)}개 논문 인덱싱...")

        return self.indexer.index_documents(docs, show_progress=self.config.show_progress)

    @traceable(name="index_orthobullets_articles")
    def index_orthobullets_articles(
        self,
        articles: List[Any],  # OrthoBulletsArticle
    ) -> List[IndexResult]:
        """
        OrthoBullets 문서 인덱싱

        Args:
            articles: OrthoBulletsArticle 리스트

        Returns:
            IndexResult 리스트
        """
        docs = []

        for article in articles:
            # 주요 섹션 조합
            text_parts = [f"제목: {article.title}"]

            if article.key_points:
                text_parts.append("핵심 포인트:\n" + "\n".join(f"- {p}" for p in article.key_points))

            for section_name, section_field in [
                ("역학", "epidemiology"),
                ("병태해부학", "pathoanatomy"),
                ("분류", "classification"),
                ("진단", "diagnosis"),
                ("치료", "treatment"),
                ("합병증", "complications"),
            ]:
                content = getattr(article, section_field, None)
                if content:
                    text_parts.append(f"\n{section_name}:\n{content}")

            # 본문 추가 (너무 길면 자름)
            if article.content:
                text_parts.append(f"\n본문:\n{article.content[:2000]}")

            text = "\n".join(text_parts)

            doc = IndexDocument(
                id=generate_document_id("orthobullets", article.source_id),
                text=text,
                source="orthobullets",
                source_id=article.source_id,
                title=article.title,
                body_part=article.body_part,
                bucket=article.category,
                url=article.url,
                extra={
                    "subcategory": article.subcategory,
                    "key_points": article.key_points[:5],
                }
            )
            docs.append(doc)

        if self.config.show_progress:
            print(f"[OrthoBullets] {len(docs)}개 문서 인덱싱...")

        return self.indexer.index_documents(docs, show_progress=self.config.show_progress)


class IndexingPipeline:
    """
    통합 인덱싱 파이프라인

    모든 데이터 소스를 Pinecone에 인덱싱
    """

    def __init__(
        self,
        pinecone_index,
        openai_client=None,
        namespace: str = "",
        config: Optional[IndexingConfig] = None,
    ):
        self.config = config or IndexingConfig(namespace=namespace)

        # 기본 컴포넌트 초기화
        chunker = DocumentChunker(
            max_tokens=self.config.chunk_max_tokens,
            overlap_tokens=self.config.chunk_overlap_tokens,
        )
        embedder = TextEmbedder(openai_client)
        base_indexer = PineconeIndexer(
            pinecone_index,
            openai_client,
            namespace=namespace,
            chunker=chunker,
            embedder=embedder,
        )

        # 특화 인덱서들
        self.exercise_indexer = ExerciseIndexer(base_indexer, self.config)
        self.paper_indexer = PaperIndexer(base_indexer, self.config)
        self.crawled_indexer = CrawledDataIndexer(base_indexer, self.config)
        self.base_indexer = base_indexer

    @traceable(name="index_all_exercises")
    def index_all_exercises(self) -> Dict[str, Any]:
        """모든 부위의 운동 데이터 인덱싱"""
        stats = {"body_parts": {}, "total": 0, "success": 0, "failed": 0}

        exercise_dir = settings.data_dir / "exercise"
        if not exercise_dir.exists():
            print(f"⚠ 운동 데이터 디렉토리 없음: {exercise_dir}")
            return stats

        for body_part_dir in exercise_dir.iterdir():
            if not body_part_dir.is_dir():
                continue

            body_part = body_part_dir.name
            exercises_file = body_part_dir / "exercises.json"

            if not exercises_file.exists():
                continue

            try:
                with open(exercises_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                exercises = data.get("exercises", {})
                results = self.exercise_indexer.index_exercises(body_part, exercises)

                body_part_stats = {"total": len(results), "success": 0, "failed": 0}
                for r in results:
                    if r.success:
                        body_part_stats["success"] += 1
                        stats["success"] += 1
                    else:
                        body_part_stats["failed"] += 1
                        stats["failed"] += 1
                    stats["total"] += 1

                stats["body_parts"][body_part] = body_part_stats

            except Exception as e:
                print(f"⚠ {body_part} 운동 인덱싱 실패: {e}")
                stats["body_parts"][body_part] = {"error": str(e)}

        return stats

    @traceable(name="index_all_papers")
    def index_all_papers(self) -> Dict[str, Any]:
        """모든 부위의 논문 데이터 인덱싱"""
        stats = {"body_parts": {}, "total_papers": 0, "total_chunks": 0}

        medical_dir = settings.data_dir / "medical"
        if not medical_dir.exists():
            print(f"⚠ 의료 데이터 디렉토리 없음: {medical_dir}")
            return stats

        for body_part_dir in medical_dir.iterdir():
            if not body_part_dir.is_dir():
                continue

            body_part = body_part_dir.name
            papers_dir = body_part_dir / "papers" / "processed"

            if papers_dir.exists():
                body_part_stats = self.paper_indexer.index_papers_from_directory(
                    papers_dir, body_part
                )
                stats["body_parts"][body_part] = body_part_stats
                stats["total_papers"] += body_part_stats.get("total_papers", 0)
                stats["total_chunks"] += body_part_stats.get("total_chunks", 0)

        return stats

    @traceable(name="index_crawled_data")
    def index_crawled_data(self) -> Dict[str, Any]:
        """크롤링 데이터 인덱싱 (PubMed, OrthoBullets 캐시)"""
        stats = {"pubmed": 0, "orthobullets": 0, "success": 0, "failed": 0}

        crawled_dir = settings.data_dir / "crawled"
        if not crawled_dir.exists():
            print(f"⚠ 크롤링 데이터 디렉토리 없음: {crawled_dir}")
            return stats

        # PubMed 캐시 인덱싱
        pubmed_cache = crawled_dir / "pubmed_cache.json"
        if pubmed_cache.exists():
            try:
                with open(pubmed_cache, 'r', encoding='utf-8') as f:
                    pubmed_data = json.load(f)

                from orthocare.data_ops.crawlers import PubMedArticle

                articles = []
                for pmid, data in pubmed_data.items():
                    try:
                        articles.append(PubMedArticle(**data))
                    except Exception:
                        continue

                if articles:
                    results = self.crawled_indexer.index_pubmed_articles(articles)
                    stats["pubmed"] = len(articles)
                    for r in results:
                        if r.success:
                            stats["success"] += 1
                        else:
                            stats["failed"] += 1

            except Exception as e:
                print(f"⚠ PubMed 캐시 인덱싱 실패: {e}")

        # OrthoBullets 캐시 인덱싱
        orthobullets_cache = crawled_dir / "orthobullets_cache.json"
        if orthobullets_cache.exists():
            try:
                with open(orthobullets_cache, 'r', encoding='utf-8') as f:
                    ortho_data = json.load(f)

                from orthocare.data_ops.crawlers import OrthoBulletsArticle

                articles = []
                for source_id, data in ortho_data.items():
                    try:
                        articles.append(OrthoBulletsArticle(**data))
                    except Exception:
                        continue

                if articles:
                    results = self.crawled_indexer.index_orthobullets_articles(articles)
                    stats["orthobullets"] = len(articles)
                    for r in results:
                        if r.success:
                            stats["success"] += 1
                        else:
                            stats["failed"] += 1

            except Exception as e:
                print(f"⚠ OrthoBullets 캐시 인덱싱 실패: {e}")

        return stats

    @traceable(name="run_full_indexing")
    def run_full_indexing(self) -> Dict[str, Any]:
        """
        전체 인덱싱 실행

        모든 데이터 소스를 동일한 벡터 공간(3072차원)에 인덱싱:
        - 운동 데이터
        - 논문 데이터
        - 크롤링 데이터 (PubMed, OrthoBullets)
        """
        print("=" * 50)
        print("OrthoCare 전체 인덱싱 시작")
        print("=" * 50)

        results = {}

        # 1. 운동 데이터
        print("\n[1/3] 운동 데이터 인덱싱...")
        results["exercises"] = self.index_all_exercises()

        # 2. 논문 데이터
        print("\n[2/3] 논문 데이터 인덱싱...")
        results["papers"] = self.index_all_papers()

        # 3. 크롤링 데이터
        print("\n[3/3] 크롤링 데이터 인덱싱...")
        results["crawled"] = self.index_crawled_data()

        # 결과 요약
        print("\n" + "=" * 50)
        print("인덱싱 완료")
        print("=" * 50)
        print(f"운동: {results['exercises'].get('total', 0)}개 "
              f"(성공: {results['exercises'].get('success', 0)}, "
              f"실패: {results['exercises'].get('failed', 0)})")
        print(f"논문: {results['papers'].get('total_papers', 0)}개, "
              f"청크: {results['papers'].get('total_chunks', 0)}개")
        print(f"크롤링: PubMed {results['crawled'].get('pubmed', 0)}개, "
              f"OrthoBullets {results['crawled'].get('orthobullets', 0)}개")

        return results

    def get_stats(self) -> Dict[str, Any]:
        """인덱스 통계 조회"""
        return self.base_indexer.get_stats()
