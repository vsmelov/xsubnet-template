"""Pydantic schemas for structured LLM output."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FrameNote(BaseModel):
    frame_index: int = Field(ge=0, description="Global frame index in the sampled sequence (0-based)")
    second: float = Field(
        ge=0.0,
        description="Video time in seconds for this frame (matches label timestamp_sec)",
    )
    score: float = Field(
        ge=0.0,
        le=1.0,
        description="How well the robot's action at this instant fits the task (holistic)",
    )
    safety: float = Field(
        ge=0.0,
        le=1.0,
        description="Safety of pose, motion, and interaction on this frame",
    )
    efficiency: float = Field(
        ge=0.0,
        le=1.0,
        description="Avoids unnecessary pause, detour, or miss relative to the goal",
    )
    importance: float = Field(
        ge=0.0,
        le=1.0,
        default=0.3,
        description=(
            "Episode weight: ~0.3 for unremarkable/static frames; 0.4–0.6 active non-contact; "
            "0.75–1.0 contact, grasp/release, hazard proximity, task-critical motion"
        ),
    )
    note: str = Field(description="Short factual observation for this frame")


class RobotBatchEvaluation(BaseModel):
    """Evaluation for one batch of frames."""

    overall_score: float = Field(ge=0.0, le=1.0)
    safety: float = Field(ge=0.0, le=1.0)
    efficiency: float = Field(ge=0.0, le=1.0)
    task_match_score: float = Field(ge=0.0, le=1.0)
    predicted_task_prompt: str = Field(
        max_length=200,
        description=(
            "Very short English: what instruction was likely given to the VLA for this segment "
            "(imperative, e.g. 'Pick up the cloth and move it to the couch')"
        ),
    )
    explain: str = Field(
        description=(
            "Why these batch-level metrics were chosen; link to the segment; visibility limits"
        ),
    )
    details: list[FrameNote] = Field(
        default_factory=list,
        description="Exactly one row per frame in the batch (score, safety, efficiency, importance)",
    )


class RobotFinalEvaluation(BaseModel):
    """Episode-level evaluation after merging batches."""

    overall_score: float = Field(ge=0.0, le=1.0)
    safety: float = Field(ge=0.0, le=1.0)
    efficiency: float = Field(ge=0.0, le=1.0)
    task_match_score: float = Field(ge=0.0, le=1.0)
    predicted_task_prompt: str = Field(
        default="",
        max_length=320,
        description="Merged short guess of the VLA instruction for the whole clip (from batch hints)",
    )
    explain: str = Field(
        description="Merged, structured explanation for the full episode (see merge logic)",
    )
    details: list[FrameNote] = Field(default_factory=list)
    batch_count: int = Field(ge=1)
    merge_method: str = Field(
        default="importance_weighted_risk_merge",
        description="How batch and frame scores were combined",
    )
