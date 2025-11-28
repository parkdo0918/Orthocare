from .user_input import UserInput, Demographics, BodyPartInput, PhysicalScore, SurveyResponse, NaturalLanguageInput
from .diagnosis import DiagnosisResult, BucketScore
from .exercise import Exercise, ExerciseRecommendation, ExerciseSet
from .evidence import Paper, EvidenceResult
from .feedback import (
    FeedbackType,
    FeedbackRating,
    SearchFeedback,
    ExerciseFeedback,
    PairwisePreference,
    FeedbackBatch,
)

__all__ = [
    # User Input
    "UserInput",
    "Demographics",
    "BodyPartInput",
    "PhysicalScore",
    "SurveyResponse",
    "NaturalLanguageInput",
    # Diagnosis
    "DiagnosisResult",
    "BucketScore",
    # Exercise
    "Exercise",
    "ExerciseRecommendation",
    "ExerciseSet",
    # Evidence
    "Paper",
    "EvidenceResult",
    # Feedback (for RL)
    "FeedbackType",
    "FeedbackRating",
    "SearchFeedback",
    "ExerciseFeedback",
    "PairwisePreference",
    "FeedbackBatch",
]
