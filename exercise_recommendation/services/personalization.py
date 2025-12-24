"""개인화 조정 서비스 (v2.0)

나이, 통증, 신체 점수 기반 개인화
+ v2.0: joint_load, kinetic_chain, required_rom, movement_pattern 기반 개인화
"""

from typing import List, Dict, Optional
from collections import Counter

from langsmith import traceable

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.models import Demographics
from exercise_recommendation.models.input import JointStatus


class PersonalizationService:
    """개인화 조정 서비스"""

    @traceable(name="exercise_personalization")
    def apply(
        self,
        exercises: List[Dict],
        demographics: Demographics,
        nrs: int,
        skipped_exercises: Optional[List[str]] = None,
        favorite_exercises: Optional[List[str]] = None,
        joint_status: Optional[JointStatus] = None,
    ) -> List[Dict]:
        """
        개인화 조정 적용 (v2.0)

        Args:
            exercises: 운동 목록
            demographics: 인구통계 정보
            nrs: 통증 점수
            skipped_exercises: 자주 건너뛴 운동 ID
            favorite_exercises: 즐겨찾기 운동 ID
            joint_status: 관절 상태 (v2.0)

        Returns:
            조정된 운동 목록
        """
        # joint_status가 없으면 기본값 생성
        if joint_status is None:
            joint_status = JointStatus()

        personalized = []

        for ex in exercises:
            adjusted = ex.copy()

            # 나이 기반 조정
            adjusted = self._adjust_for_age(adjusted, demographics.age)

            # BMI 기반 조정
            adjusted = self._adjust_for_bmi(adjusted, demographics.bmi)

            # 통증 기반 조정
            adjusted = self._adjust_for_pain(adjusted, nrs)

            # === v2.0: 새로운 칼럼 기반 조정 ===
            # 관절 부하 기반 조정
            adjusted = self._adjust_for_joint_load(adjusted, joint_status, demographics)

            # 운동 사슬 기반 조정
            adjusted = self._adjust_for_kinetic_chain(adjusted, joint_status)

            # 가동범위 기반 조정
            adjusted = self._adjust_for_rom(adjusted, joint_status)

            # 자주 건너뛴 운동 우선순위 하락
            if skipped_exercises and ex.get("id") in skipped_exercises:
                adjusted["_priority_penalty"] = adjusted.get("_priority_penalty", 0) + 0.1

            # 즐겨찾기 운동 우선순위 상승
            if favorite_exercises and ex.get("id") in favorite_exercises:
                adjusted["_priority_boost"] = adjusted.get("_priority_boost", 0) + 0.2

            # 환자 프로필에 맞는 운동 우선순위 상승
            adjusted = self._boost_appropriate_exercises(adjusted, demographics, nrs)

            # v2.0: 관절 상태 기반 우선순위 조정
            adjusted = self._boost_for_joint_status(adjusted, joint_status)

            personalized.append(adjusted)

        # 우선순위 정렬
        personalized.sort(
            key=lambda x: (
                x.get("_priority_boost", 0) - x.get("_priority_penalty", 0)
            ),
            reverse=True,
        )

        # v2.0: 움직임 패턴 다양성 확보
        personalized = self._ensure_movement_pattern_diversity(personalized)

        return personalized

    def _adjust_for_bmi(self, exercise: Dict, bmi: float) -> Dict:
        """BMI 기반 조정"""
        adjusted = exercise.copy()
        function_tags = exercise.get("function_tags", [])

        if bmi >= 30:
            # 비만: 체중 부하 운동 강도 감소
            if "Strengthening" in function_tags:
                current_sets = exercise.get("sets", 2)
                adjusted["sets"] = max(1, current_sets - 1)
                adjusted["_bmi_adjustment"] = "reduced_load"

            # 휴식 시간 증가
            rest_str = exercise.get("rest", "30초")
            import re
            match = re.search(r"(\d+)", rest_str)
            if match:
                current_rest = int(match.group(1))
                adjusted["rest"] = f"{current_rest + 15}초"

        elif bmi >= 25:
            # 과체중: 휴식 시간 약간 증가
            rest_str = exercise.get("rest", "30초")
            import re
            match = re.search(r"(\d+)", rest_str)
            if match:
                current_rest = int(match.group(1))
                adjusted["rest"] = f"{current_rest + 5}초"
            adjusted["_bmi_adjustment"] = "moderate"

        return adjusted

    def _boost_appropriate_exercises(
        self,
        exercise: Dict,
        demographics: Demographics,
        nrs: int,
    ) -> Dict:
        """환자 프로필에 맞는 운동 우선순위 상승"""
        adjusted = exercise.copy()
        function_tags = exercise.get("function_tags", [])
        difficulty = exercise.get("difficulty", "medium")
        boost = adjusted.get("_priority_boost", 0)

        age = demographics.age
        bmi = demographics.bmi

        # 고령자: 균형/안정성 운동 우선
        if age >= 65:
            if "Balance" in function_tags or "Stability" in function_tags:
                boost += 0.15
            if difficulty == "low":
                boost += 0.1

        # 비만: 저충격 운동 우선
        if bmi >= 30:
            if "Mobility" in function_tags or "Stretching" in function_tags:
                boost += 0.1
            if difficulty == "low":
                boost += 0.05

        # 고통증: 가동성 운동 우선
        if nrs >= 6:
            if "Mobility" in function_tags:
                boost += 0.15
            if difficulty == "low":
                boost += 0.1

        # 젊은 층 + 저통증: 근력 운동 우선
        if age < 40 and nrs < 4:
            if "Strengthening" in function_tags:
                boost += 0.1

        adjusted["_priority_boost"] = boost
        return adjusted

    def _adjust_for_age(self, exercise: Dict, age: int) -> Dict:
        """나이 기반 조정"""
        adjusted = exercise.copy()

        if age >= 65:
            # 고령자: 세트 수 감소, 휴식 증가
            current_sets = exercise.get("sets", 2)
            adjusted["sets"] = max(1, current_sets - 1)

            rest_str = exercise.get("rest", "30초")
            current_rest = int(rest_str.replace("초", "").strip())
            adjusted["rest"] = f"{current_rest + 15}초"

            adjusted["_age_adjustment"] = "elderly_safe"

        elif age >= 50:
            # 중년: 휴식 약간 증가
            rest_str = exercise.get("rest", "30초")
            current_rest = int(rest_str.replace("초", "").strip())
            adjusted["rest"] = f"{current_rest + 10}초"

            adjusted["_age_adjustment"] = "moderate"

        return adjusted

    def _adjust_for_pain(self, exercise: Dict, nrs: int) -> Dict:
        """통증 기반 조정"""
        adjusted = exercise.copy()

        if nrs >= 7:
            # 심한 통증: 세트 및 반복 감소
            current_sets = exercise.get("sets", 2)
            adjusted["sets"] = max(1, current_sets - 1)

            reps_str = exercise.get("reps", "10회")
            import re
            match = re.search(r"(\d+)", reps_str)
            if match:
                current_reps = int(match.group(1))
                adjusted["reps"] = f"{max(5, current_reps - 3)}회"

            adjusted["_pain_adjustment"] = "reduced_intensity"

        elif nrs >= 4:
            # 중등도 통증: 반복 약간 감소
            reps_str = exercise.get("reps", "10회")
            import re
            match = re.search(r"(\d+)", reps_str)
            if match:
                current_reps = int(match.group(1))
                adjusted["reps"] = f"{max(5, current_reps - 2)}회"

            adjusted["_pain_adjustment"] = "moderate_intensity"

        return adjusted

    @traceable(name="exercise_ordering")
    def get_exercise_order(self, exercises: List[Dict]) -> List[Dict]:
        """
        운동 순서 결정 (준비운동 → 가동성 → 근력 → 안정성 → 정리)

        원칙:
        1. 준비 운동 (Mobility, Stretching) → 먼저
        2. 본 운동 (Strengthening) → 중간
        3. 마무리 (Balance, Stability) → 마지막
        4. 같은 카테고리 내에서는 난이도 오름차순
        """
        # 기능별 우선순위
        category_priority = {
            "Mobility": 0,      # 준비 - 가동성
            "Stretching": 1,    # 준비 - 스트레칭
            "Strengthening": 2, # 본 - 근력
            "Stability": 3,     # 마무리 - 안정성
            "Balance": 4,       # 마무리 - 균형
        }

        # 난이도별 우선순위 (같은 기능 내 정렬용)
        difficulty_priority = {
            "low": 0,
            "medium": 1,
            "high": 2,
        }

        def get_sort_key(ex: Dict) -> tuple:
            # 기능 태그에서 가장 높은 우선순위 찾기
            tags = ex.get("function_tags", [])
            cat_priorities = [category_priority.get(t, 5) for t in tags]
            min_cat_priority = min(cat_priorities) if cat_priorities else 5

            # 난이도 우선순위
            difficulty = ex.get("difficulty", "medium")
            diff_priority = difficulty_priority.get(difficulty, 1)

            # 개인화 우선순위 (높을수록 먼저)
            boost = ex.get("_priority_boost", 0)

            return (min_cat_priority, diff_priority, -boost)

        ordered = sorted(exercises, key=get_sort_key)

        # 순서 인덱스 추가 (디버깅/추적용)
        for i, ex in enumerate(ordered):
            ex["_order_index"] = i + 1

        return ordered

    def ensure_category_balance(
        self,
        exercises: List[Dict],
        min_per_category: int = 1,
    ) -> List[Dict]:
        """
        카테고리 균형 확인 및 조정

        최소한 각 카테고리에서 min_per_category개씩 포함되도록 함
        """
        categories = {
            "warmup": ["Mobility", "Stretching"],
            "main": ["Strengthening"],
            "cooldown": ["Stability", "Balance"],
        }

        category_counts = {"warmup": 0, "main": 0, "cooldown": 0}

        for ex in exercises:
            tags = ex.get("function_tags", [])
            for cat_name, cat_tags in categories.items():
                if any(t in cat_tags for t in tags):
                    category_counts[cat_name] += 1

        # 카테고리별 부족 여부 체크
        missing = {
            cat: max(0, min_per_category - count)
            for cat, count in category_counts.items()
        }

        return exercises  # 현재는 체크만, 추후 자동 추가 로직 구현 가능

    # ============================================================
    # v2.0: 새로운 칼럼 기반 개인화 메서드
    # ============================================================

    def _adjust_for_joint_load(
        self,
        exercise: Dict,
        joint_status: JointStatus,
        demographics: Demographics,
    ) -> Dict:
        """관절 부하 기반 조정 (v2.0)

        joint_load 칼럼 활용:
        - very_low: 매우 낮은 부하 (재활 초기, 고통증)
        - low: 낮은 부하 (가동범위 제한, 과체중)
        - medium: 중간 부하 (일반)
        """
        adjusted = exercise.copy()
        joint_load = exercise.get("joint_load", "medium")
        preferred_loads = joint_status.preferred_joint_load

        # 선호 부하와 일치하면 우선순위 상승
        if joint_load in preferred_loads:
            boost = adjusted.get("_priority_boost", 0)

            # 정확히 맞는 경우 더 높은 부스트
            if joint_load == preferred_loads[0]:
                boost += 0.2
            else:
                boost += 0.1

            adjusted["_priority_boost"] = boost
            adjusted["_joint_load_match"] = True
        else:
            # 선호하지 않는 부하는 페널티
            penalty = adjusted.get("_priority_penalty", 0)
            penalty += 0.15
            adjusted["_priority_penalty"] = penalty
            adjusted["_joint_load_match"] = False

        # 비만(BMI >= 30) + 중간 부하 = 세트 감소
        if demographics.bmi >= 30 and joint_load == "medium":
            current_sets = exercise.get("sets", 2)
            adjusted["sets"] = max(1, current_sets - 1)
            adjusted["_bmi_joint_load_adjustment"] = True

        return adjusted

    def _adjust_for_kinetic_chain(
        self,
        exercise: Dict,
        joint_status: JointStatus,
    ) -> Dict:
        """운동 사슬 기반 조정 (v2.0)

        kinetic_chain 칼럼 활용:
        - OKC (Open Kinetic Chain): 열린 사슬, 말단 자유
          → 재활 초기, 관절 불안정에 적합
        - CKC (Closed Kinetic Chain): 닫힌 사슬, 말단 고정
          → 기능적 운동, 안정성 훈련에 적합
        """
        adjusted = exercise.copy()
        kinetic_chain = exercise.get("kinetic_chain", "OKC")
        preferred_chains = joint_status.preferred_kinetic_chain

        boost = adjusted.get("_priority_boost", 0)

        if kinetic_chain in preferred_chains:
            # 급성기에 OKC 우선
            if joint_status.rehabilitation_phase == "acute" and kinetic_chain == "OKC":
                boost += 0.15
            elif kinetic_chain in preferred_chains:
                boost += 0.05

            adjusted["_kinetic_chain_match"] = True
        else:
            # 급성기에 CKC는 제외 권장
            if joint_status.rehabilitation_phase == "acute" and kinetic_chain == "CKC":
                penalty = adjusted.get("_priority_penalty", 0)
                penalty += 0.2
                adjusted["_priority_penalty"] = penalty
                adjusted["_kinetic_chain_warning"] = "급성기에 CKC 운동 주의"

            adjusted["_kinetic_chain_match"] = False

        adjusted["_priority_boost"] = boost
        return adjusted

    def _adjust_for_rom(
        self,
        exercise: Dict,
        joint_status: JointStatus,
    ) -> Dict:
        """가동범위 기반 조정 (v2.0)

        required_rom 칼럼 활용:
        - small: 작은 가동범위 필요
        - medium: 중간 가동범위 필요
        """
        adjusted = exercise.copy()
        required_rom = exercise.get("required_rom", "medium")
        preferred_rom = joint_status.preferred_rom

        boost = adjusted.get("_priority_boost", 0)

        if required_rom in preferred_rom:
            # 가동범위 제한 환자에게 small ROM 운동 우선
            if joint_status.rom_status == "restricted" and required_rom == "small":
                boost += 0.15
            else:
                boost += 0.05

            adjusted["_rom_match"] = True
        else:
            # 가동범위 제한인데 medium ROM 필요한 운동
            if joint_status.rom_status == "restricted" and required_rom == "medium":
                penalty = adjusted.get("_priority_penalty", 0)
                penalty += 0.1
                adjusted["_priority_penalty"] = penalty
                adjusted["_rom_warning"] = "가동범위 제한 시 주의"

            adjusted["_rom_match"] = False

        adjusted["_priority_boost"] = boost
        return adjusted

    def _boost_for_joint_status(
        self,
        exercise: Dict,
        joint_status: JointStatus,
    ) -> Dict:
        """관절 상태 종합 우선순위 조정 (v2.0)"""
        adjusted = exercise.copy()
        boost = adjusted.get("_priority_boost", 0)

        movement_pattern = exercise.get("movement_pattern", "")
        function_tags = exercise.get("function_tags", [])

        # 재활 단계별 선호 운동
        phase = joint_status.rehabilitation_phase

        if phase == "acute":
            # 급성기: 모빌리티 우선
            if movement_pattern == "모빌리티" or "Mobility" in function_tags:
                boost += 0.15
        elif phase == "subacute":
            # 아급성기: 모빌리티 + 가벼운 근력
            if movement_pattern in ["모빌리티", "브리지"]:
                boost += 0.1
        elif phase == "chronic":
            # 만성기: 근력 + 안정성
            if movement_pattern in ["스쿼트", "런지", "브리지"]:
                boost += 0.1
            if "Strength" in function_tags:
                boost += 0.05
        else:  # maintenance
            # 유지기: 다양한 패턴
            if "Balance" in function_tags or "Stability" in function_tags:
                boost += 0.05

        # 불안정 관절: 안정성 운동 우선
        if joint_status.joint_condition == "unstable":
            if "Stability" in function_tags:
                boost += 0.15

        adjusted["_priority_boost"] = boost
        return adjusted

    def _ensure_movement_pattern_diversity(
        self,
        exercises: List[Dict],
        max_same_pattern: int = 3,
    ) -> List[Dict]:
        """움직임 패턴 다양성 확보 (v2.0)

        같은 movement_pattern이 너무 많이 연속되지 않도록 조정
        """
        if len(exercises) <= max_same_pattern:
            return exercises

        # 패턴별 카운트
        pattern_counts = Counter(
            ex.get("movement_pattern", "기타") for ex in exercises
        )

        # 가장 많은 패턴이 전체의 60% 이상이면 재정렬
        most_common_pattern, most_common_count = pattern_counts.most_common(1)[0]
        if most_common_count > len(exercises) * 0.6:
            # 패턴별로 그룹화 후 교차 배치
            by_pattern: Dict[str, List[Dict]] = {}
            for ex in exercises:
                pattern = ex.get("movement_pattern", "기타")
                if pattern not in by_pattern:
                    by_pattern[pattern] = []
                by_pattern[pattern].append(ex)

            # 라운드 로빈 방식으로 재정렬
            reordered = []
            pattern_lists = list(by_pattern.values())
            max_len = max(len(lst) for lst in pattern_lists)

            for i in range(max_len):
                for lst in pattern_lists:
                    if i < len(lst):
                        reordered.append(lst[i])

            return reordered

        return exercises

    def get_personalization_summary(
        self,
        exercises: List[Dict],
    ) -> Dict:
        """개인화 적용 요약 (v2.0)"""
        summary = {
            "total_exercises": len(exercises),
            "joint_load_matched": sum(1 for ex in exercises if ex.get("_joint_load_match")),
            "kinetic_chain_matched": sum(1 for ex in exercises if ex.get("_kinetic_chain_match")),
            "rom_matched": sum(1 for ex in exercises if ex.get("_rom_match")),
            "movement_patterns": Counter(ex.get("movement_pattern", "기타") for ex in exercises),
            "warnings": [
                ex.get("_rom_warning") or ex.get("_kinetic_chain_warning")
                for ex in exercises
                if ex.get("_rom_warning") or ex.get("_kinetic_chain_warning")
            ],
        }
        return summary
