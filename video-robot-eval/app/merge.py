"""Merge batch evaluations: importance-weighted per-frame risk + batch-level mins."""

from __future__ import annotations

from collections.abc import Callable

from app.schemas import FrameNote, RobotBatchEvaluation, RobotFinalEvaluation


def _merge_predicted_task_prompts(
    batches: list[tuple[RobotBatchEvaluation, int, int, int]],
    *,
    max_chars: int = 300,
) -> str:
    """Dedupe non-empty batch prompts, join with middle dot, truncate for RobotFinalEvaluation."""
    seen: list[str] = []
    for ev, _, _, _ in batches:
        t = (ev.predicted_task_prompt or "").strip()
        if not t or t in seen:
            continue
        seen.append(t)
    if not seen:
        return ""
    joined = " · ".join(seen)
    if len(joined) <= max_chars:
        return joined
    return joined[: max_chars - 1].rstrip("-,.; ·") + "…"


def _compact_batch_explain(text: str, max_chars: int = 120) -> str:
    t = " ".join(text.split())
    if not t:
        return "(no batch explain)"
    low = t.lower()
    if "all 1.0" in low and ("no visible" in low or "on plan" in low or "defect" in low):
        return "All 1.0; no visible defect."
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1].rstrip("-,.; ") + "…"


def _frame_risk_merge(
    details: list[FrameNote],
    getter: Callable[[FrameNote], float],
) -> float:
    """
    Per frame: adjusted = 1 - importance * (1 - metric).
    Episode value = min over frames. importance=1 and metric=0 -> 0; importance=0 does not pull down.
    """
    if not details:
        return 1.0
    adjusted: list[float] = []
    for d in details:
        imp = max(0.0, min(1.0, d.importance))
        v = max(0.0, min(1.0, getter(d)))
        adjusted.append(1.0 - imp * (1.0 - v))
    return max(0.0, min(1.0, min(adjusted)))


def merge_batch_evaluations(
    batches: list[tuple[RobotBatchEvaluation, int, int, int]],
) -> RobotFinalEvaluation:
    """
    batches: (evaluation, num_frames, frame_index_first, frame_index_last).

    Final metrics = min(importance-weighted frame aggregate, min of batch-level metrics)
    so one bad important frame or one bad segment can dominate the score.
    """
    if not batches:
        raise ValueError("empty batches")

    details: list[FrameNote] = []
    for ev, _, _, _ in batches:
        details.extend(ev.details)

    details.sort(key=lambda d: (d.frame_index, d.second))

    fr_overall = _frame_risk_merge(details, lambda d: d.score)
    fr_safety = _frame_risk_merge(details, lambda d: d.safety)
    fr_eff = _frame_risk_merge(details, lambda d: d.efficiency)
    fr_task = _frame_risk_merge(details, lambda d: d.score)

    br_overall = min(ev.overall_score for ev, _, _, _ in batches)
    br_safety = min(ev.safety for ev, _, _, _ in batches)
    br_eff = min(ev.efficiency for ev, _, _, _ in batches)
    br_task = min(ev.task_match_score for ev, _, _, _ in batches)

    overall = max(0.0, min(1.0, min(fr_overall, br_overall)))
    safety = max(0.0, min(1.0, min(fr_safety, br_safety)))
    efficiency = max(0.0, min(1.0, min(fr_eff, br_eff)))
    task_match = max(0.0, min(1.0, min(fr_task, br_task)))

    lines: list[str] = [
        "Episode metrics = min(frame-level risk merge with `importance`, batch-level mins). "
        "Per-frame rows in `details`.",
    ]
    for _i, (ev, _w, lo, hi) in enumerate(batches, start=1):
        lines.append(f"[{lo}–{hi}] {_compact_batch_explain(ev.explain)}")

    merged_explain = "\n".join(lines)
    merged_ptp = _merge_predicted_task_prompts(batches)

    return RobotFinalEvaluation(
        overall_score=overall,
        safety=safety,
        efficiency=efficiency,
        task_match_score=task_match,
        predicted_task_prompt=merged_ptp,
        explain=merged_explain,
        details=details,
        batch_count=len(batches),
        merge_method=(
            "min( importance_weighted_per_frame_min , min(batch metrics) ); "
            "per_frame: min_i(1 - importance_i*(1-metric_i)); explain = compact per batch; "
            "predicted_task_prompt = deduped join of batch predicted_task_prompt"
        ),
    )
