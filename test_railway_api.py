"""Railway 배포 API 테스트 스크립트

사용법:
    python test_railway_api.py <RAILWAY_URL>

예시:
    python test_railway_api.py https://your-app.railway.app
"""

import requests
import json
import sys
from typing import Dict, Any, Optional

def test_health_check(base_url: str) -> Dict[str, Any]:
    """헬스 체크"""
    url = f"{base_url}/health"
    
    try:
        response = requests.get(url, timeout=5)
        return {
            "status_code": response.status_code,
            "success": response.status_code == 200,
            "response": response.json() if response.status_code == 200 else response.text,
            "error": None
        }
    except Exception as e:
        return {
            "status_code": None,
            "success": False,
            "response": None,
            "error": str(e)
        }


def test_minimal_request(base_url: str) -> Dict[str, Any]:
    """최소 요청 테스트 (README 버킷 추론 API 기준 - physical_score 없음)"""
    url = f"{base_url}/api/v1/diagnose-and-recommend"
    
    # README의 버킷 추론 API 예시 (최소 필드만)
    payload = {
        "user_id": "test_user_001",
        "demographics": {
            "age": 55,
            "sex": "female",
            "height_cm": 160,
            "weight_kg": 65
        },
        "body_parts": [{
            "code": "knee",
            "primary": True,
            "side": "both",
            "symptoms": ["pain_bilateral", "chronic", "stairs_down", "stiffness_morning"],
            "nrs": 6,
            "red_flags_checked": []
        }],
        "natural_language": {
            "chief_complaint": "양쪽 무릎이 아프고 계단 내려갈 때 힘들어요",
            "pain_description": "아침에 뻣뻣하고 30분 정도 지나면 나아져요",
            "history": "5년 전부터 서서히 심해짐"
        },
        "options": {
            "include_exercises": False  # 버킷 추론만
        }
    }
    
    try:
        response = requests.post(url, json=payload, timeout=60)
        return {
            "status_code": response.status_code,
            "success": response.status_code == 200,
            "response": response.json() if response.status_code == 200 else response.text,
            "error": None,
            "payload": payload
        }
    except Exception as e:
        return {
            "status_code": None,
            "success": False,
            "response": None,
            "error": str(e),
            "payload": payload
        }


def test_swagger_example(base_url: str) -> Dict[str, Any]:
    """Swagger 예시 요청 테스트 (전체 필드)"""
    url = f"{base_url}/api/v1/diagnose-and-recommend"
    
    # Swagger의 전체 필드 예시
    payload = {
        "user_id": "user_123",
        "demographics": {
            "age": 55,
            "sex": "male",
            "height_cm": 175,
            "weight_kg": 80
        },
        "body_parts": [{
            "code": "knee",
            "primary": True,
            "side": "left",
            "symptoms": ["pain_medial", "stiffness_morning"],
            "nrs": 6,
            "red_flags_checked": []
        }],
        "physical_score": {
            "total_score": 12
        },
        "options": {
            "include_exercises": True,
            "exercise_days": 3,
            "skip_exercise_on_red_flag": True
        }
    }
    
    try:
        response = requests.post(url, json=payload, timeout=60)
        return {
            "status_code": response.status_code,
            "success": response.status_code == 200,
            "response": response.json() if response.status_code == 200 else response.text,
            "error": None,
            "payload": payload
        }
    except Exception as e:
        return {
            "status_code": None,
            "success": False,
            "response": None,
            "error": str(e),
            "payload": payload
        }


def test_diagnose_only(base_url: str) -> Dict[str, Any]:
    """진단만 실행 (운동 추천 제외)"""
    url = f"{base_url}/api/v1/diagnose"
    
    payload = {
        "user_id": "test_user_002",
        "demographics": {
            "age": 55,
            "sex": "female",
            "height_cm": 160,
            "weight_kg": 65
        },
        "body_parts": [{
            "code": "knee",
            "symptoms": ["pain_medial", "stiffness_morning"],
            "nrs": 6
        }]
    }
    
    try:
        response = requests.post(url, json=payload, timeout=60)
        return {
            "status_code": response.status_code,
            "success": response.status_code == 200,
            "response": response.json() if response.status_code == 200 else response.text,
            "error": None,
            "payload": payload
        }
    except Exception as e:
        return {
            "status_code": None,
            "success": False,
            "response": None,
            "error": str(e),
            "payload": payload
        }


def main():
    if len(sys.argv) < 2:
        print("사용법: python test_railway_api.py <RAILWAY_URL>")
        print("예시: python test_railway_api.py https://your-app.railway.app")
        sys.exit(1)
    
    base_url = sys.argv[1].rstrip('/')
    
    print("=" * 70)
    print("Railway 배포 API 테스트")
    print("=" * 70)
    print(f"\n대상 URL: {base_url}\n")
    
    # 헬스 체크
    print("1. 헬스 체크")
    print("-" * 70)
    health_result = test_health_check(base_url)
    print(json.dumps(health_result, indent=2, ensure_ascii=False))
    
    if not health_result["success"]:
        print("\n⚠️  헬스 체크 실패. URL을 확인하세요.")
        sys.exit(1)
    
    # 최소 요청 테스트
    print("\n\n2. 최소 요청 테스트 (README 버킷 추론 API 기준)")
    print("-" * 70)
    print("📝 요청 페이로드:")
    minimal_result = test_minimal_request(base_url)
    print(json.dumps(minimal_result.get("payload", {}), indent=2, ensure_ascii=False))
    print("\n📥 응답:")
    print(json.dumps({k: v for k, v in minimal_result.items() if k != "payload"}, indent=2, ensure_ascii=False))
    
    # Swagger 예시 테스트
    print("\n\n3. Swagger 예시 요청 테스트 (전체 필드)")
    print("-" * 70)
    print("📝 요청 페이로드:")
    swagger_result = test_swagger_example(base_url)
    print(json.dumps(swagger_result.get("payload", {}), indent=2, ensure_ascii=False))
    print("\n📥 응답:")
    print(json.dumps({k: v for k, v in swagger_result.items() if k != "payload"}, indent=2, ensure_ascii=False))
    
    # 진단만 테스트
    print("\n\n4. 진단만 실행 (/api/v1/diagnose)")
    print("-" * 70)
    print("📝 요청 페이로드:")
    diagnose_result = test_diagnose_only(base_url)
    print(json.dumps(diagnose_result.get("payload", {}), indent=2, ensure_ascii=False))
    print("\n📥 응답:")
    print(json.dumps({k: v for k, v in diagnose_result.items() if k != "payload"}, indent=2, ensure_ascii=False))
    
    # 요약
    print("\n\n" + "=" * 70)
    print("테스트 요약")
    print("=" * 70)
    print(f"헬스 체크:        {'✅ 성공' if health_result['success'] else '❌ 실패'}")
    print(f"최소 요청:        {'✅ 성공' if minimal_result['success'] else '❌ 실패'}")
    print(f"Swagger 예시:     {'✅ 성공' if swagger_result['success'] else '❌ 실패'}")
    print(f"진단만 실행:      {'✅ 성공' if diagnose_result['success'] else '❌ 실패'}")
    
    # 실패한 테스트 상세 정보
    failures = []
    if not minimal_result['success']:
        failures.append(("최소 요청", minimal_result))
    if not swagger_result['success']:
        failures.append(("Swagger 예시", swagger_result))
    if not diagnose_result['success']:
        failures.append(("진단만 실행", diagnose_result))
    
    if failures:
        print("\n\n❌ 실패한 테스트 상세:")
        print("-" * 70)
        for name, result in failures:
            print(f"\n{name}:")
            if result.get('error'):
                print(f"  에러: {result['error']}")
            if result.get('status_code'):
                print(f"  상태 코드: {result['status_code']}")
            if result.get('response'):
                print(f"  응답: {json.dumps(result['response'], indent=2, ensure_ascii=False)}")


if __name__ == "__main__":
    main()

