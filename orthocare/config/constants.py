"""상수 정의 - 버킷명, 증상 코드 등"""

from typing import Dict, List

# 무릎 버킷
KNEE_BUCKETS: List[str] = ["OA", "OVR", "TRM", "INF"]

# 버킷 한글명
BUCKET_NAMES: Dict[str, str] = {
    "OA": "퇴행성관절염",
    "OVR": "과사용증후군",
    "TRM": "외상",
    "INF": "염증성",
}

# 현재 지원 부위
SUPPORTED_BODY_PARTS: List[str] = ["knee"]

# 부위별 버킷 매핑
BUCKETS: Dict[str, List[str]] = {
    "knee": KNEE_BUCKETS,
    # 추후 추가
    # "shoulder": ["RC", "IMP", "FRZ", "INST"],
}

# 무릎 증상 코드 (weights.json 키와 일치)
SYMPTOM_CODES: List[str] = [
    # 연령
    "age_gte_60",
    "age_gte_50",
    "age_40s",
    "age_30s",
    "age_20s",
    "age_teens",
    # BMI
    "bmi_gte_30",
    "bmi_gte_27",
    "bmi_gte_25",
    "bmi_normal",
    # 통증 위치
    "pain_medial",
    "pain_lateral",
    "pain_anterior",
    "pain_bilateral",
    "pain_whole_knee",
    # 악화 요인
    "stairs_down",
    "stairs_up",
    "stairs_difficulty",
    "squatting",
    "sitting_to_standing",
    "weather_sensitive",
    "after_walking",
    "activity_running",
    "activity_sports",
    "activity_jumping",
    "after_exercise",
    "rest_improvement",
    "overuse_pattern",
    # 증상
    "swelling",
    "heat",
    "swelling_heat",
    "redness",
    "night_pain",
    "systemic_symptoms",
    "fever",
    "stiffness_morning",
    "stiffness_30min_plus",
    "stiffness_improves",
    # 외상/기계적
    "trauma",
    "trauma_recent",
    "twisting",
    "acute_pain",
    "sudden_onset",
    "instability",
    "giving_way",
    "locking",
    "catching",
    "clicking",
    # 기능
    "mobility_limited",
    "weight_bearing_pain",
    "adl_limited",
    # 경과
    "acute",
    "subacute",
    "chronic",
    "progressive",
    # 염증성 지표
    "bilateral_symmetric",
    "multiple_joints",
    "family_history_ra",
    "autoimmune_signs",
]

# 운동 난이도
EXERCISE_DIFFICULTY: List[str] = ["low", "medium", "high"]

# 신체 점수 레벨
PHYSICAL_SCORE_LEVELS: List[str] = ["A", "B", "C", "D"]
