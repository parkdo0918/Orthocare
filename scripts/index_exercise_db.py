"""운동용 벡터 DB 인덱싱 스크립트

벡터 DB: orthocare-exercise
소스: exercise

사용법:
    PYTHONPATH=. python scripts/index_exercise_db.py
    PYTHONPATH=. python scripts/index_exercise_db.py --clear-first
    PYTHONPATH=. python scripts/index_exercise_db.py --body-part shoulder
"""

import argparse
import json
import os
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

from dotenv import load_dotenv
load_dotenv(override=True)  # .env 파일 우선

from pinecone import Pinecone, ServerlessSpec
from openai import OpenAI

# 설정 (환경변수 무시, 하드코딩)
PINECONE_INDEX = "orthocare-exercise"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536
DATA_DIR = Path(__file__).parent.parent / "data"


def get_clients():
    """Pinecone, OpenAI 클라이언트 반환"""
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    openai = OpenAI()
    return pc, openai


def ensure_index_exists(pc: Pinecone):
    """인덱스 존재 확인 및 생성"""
    if PINECONE_INDEX not in pc.list_indexes().names():
        print(f"인덱스 '{PINECONE_INDEX}' 생성 중...")
        pc.create_index(
            name=PINECONE_INDEX,
            dimension=EMBEDDING_DIM,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
        print(f"인덱스 '{PINECONE_INDEX}' 생성 완료")
    else:
        print(f"인덱스 '{PINECONE_INDEX}' 이미 존재")


def embed_text(openai: OpenAI, text: str) -> List[float]:
    """텍스트 임베딩"""
    response = openai.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
    )
    return response.data[0].embedding


def build_exercise_text(exercise: Dict) -> str:
    """운동 임베딩용 텍스트 생성 (v2.0 스키마)"""
    # 근육 정보 통합 (주동근, 길항근, 협동근)
    all_muscles = []
    all_muscles.extend(exercise.get('primary_muscles', []))
    all_muscles.extend(exercise.get('antagonist_muscles', []))
    all_muscles.extend(exercise.get('synergist_muscles', []))

    # 기존 target_muscles 호환성 유지
    if not all_muscles:
        all_muscles = exercise.get('target_muscles', [])

    parts = [
        f"운동: {exercise.get('name_kr', '')} ({exercise.get('name_en', '')})",
        f"난이도: {exercise.get('difficulty', '')}",
        f"기능: {', '.join(exercise.get('function_tags', []))}",
        f"주동근: {', '.join(exercise.get('primary_muscles', []))}",
        f"타겟 근육: {', '.join(all_muscles)}",
        f"관절부하: {exercise.get('joint_load', '')}",
        f"움직임패턴: {exercise.get('movement_pattern', '')}",
        f"운동사슬: {exercise.get('kinetic_chain', '')}",
        f"설명: {exercise.get('description', '')}",
    ]
    return " ".join(parts)


def index_exercises(pc: Pinecone, openai: OpenAI, body_part: str = "knee"):
    """운동 인덱싱"""
    print(f"\n=== 운동 인덱싱 ({body_part}) ===")

    index = pc.Index(PINECONE_INDEX)
    exercises_path = DATA_DIR / "exercise" / body_part / "exercises.json"

    if not exercises_path.exists():
        print(f"운동 파일 없음: {exercises_path}")
        return 0

    with open(exercises_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # v2.0 스키마: exercises 키 안에 운동 데이터
    exercises = data.get("exercises", data)
    if isinstance(exercises, dict) and "_metadata" in data:
        exercises = data["exercises"]

    vectors = []
    for ex_id, ex_data in exercises.items():
        # 임베딩용 텍스트 생성
        text = build_exercise_text(ex_data)
        embedding = embed_text(openai, text)

        # 버킷 태그
        diagnosis_tags = ex_data.get("diagnosis_tags", [])

        # 근육 정보 통합
        all_muscles = []
        all_muscles.extend(ex_data.get('primary_muscles', []))
        all_muscles.extend(ex_data.get('antagonist_muscles', []))
        all_muscles.extend(ex_data.get('synergist_muscles', []))
        if not all_muscles:
            all_muscles = ex_data.get('target_muscles', [])

        # 메타데이터 (v2.0 스키마)
        metadata = {
            "id": ex_id,
            "body_part": body_part,
            "source": "exercise",
            "bucket": ",".join(diagnosis_tags),
            "name_kr": ex_data.get("name_kr", ""),
            "name_en": ex_data.get("name_en", ""),
            "difficulty": ex_data.get("difficulty", "standard"),
            "function_tags": ",".join(ex_data.get("function_tags", [])),
            "target_muscles": ",".join(all_muscles),
            "primary_muscles": ",".join(ex_data.get("primary_muscles", [])),
            "antagonist_muscles": ",".join(ex_data.get("antagonist_muscles", [])),
            "synergist_muscles": ",".join(ex_data.get("synergist_muscles", [])),
            "sets": ex_data.get("sets", 2),
            "reps": ex_data.get("reps", "10회"),
            "rest": ex_data.get("rest", "30초"),
            "text": text[:1000],
        }

        # v2.0 확장 속성 (있으면 추가)
        if "joint_load" in ex_data:
            metadata["joint_load"] = ex_data["joint_load"]
        if "movement_pattern" in ex_data:
            metadata["movement_pattern"] = ex_data["movement_pattern"]
        if "required_rom" in ex_data:
            metadata["required_rom"] = ex_data["required_rom"]
        if "kinetic_chain" in ex_data:
            metadata["kinetic_chain"] = ex_data["kinetic_chain"]

        vectors.append({
            "id": f"exercise_{body_part}_{ex_id}",
            "values": embedding,
            "metadata": metadata,
        })

    # 배치 업서트
    if vectors:
        batch_size = 100
        for i in range(0, len(vectors), batch_size):
            batch = vectors[i:i + batch_size]
            index.upsert(vectors=batch)
            print(f"  업서트: {i + len(batch)}/{len(vectors)}")

    print(f"운동 인덱싱 완료: {len(vectors)}개")
    return len(vectors)


def main():
    parser = argparse.ArgumentParser(description="운동용 벡터 DB 인덱싱")
    parser.add_argument("--clear-first", action="store_true", help="기존 데이터 삭제 후 인덱싱")
    parser.add_argument("--body-part", default="knee", help="부위 코드")
    args = parser.parse_args()

    print(f"=== 운동용 벡터 DB 인덱싱 시작 ({datetime.now()}) ===")
    print(f"인덱스: {PINECONE_INDEX}")

    pc, openai = get_clients()
    ensure_index_exists(pc)

    if args.clear_first:
        print("\n기존 데이터 삭제 중...")
        index = pc.Index(PINECONE_INDEX)
        index.delete(delete_all=True)
        print("삭제 완료")

    total = index_exercises(pc, openai, args.body_part)

    print(f"\n=== 인덱싱 완료: 총 {total}개 벡터 ===")


if __name__ == "__main__":
    main()
