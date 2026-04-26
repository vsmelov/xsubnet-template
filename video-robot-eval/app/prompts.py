"""Prompt strings for frame-batch evaluation."""


def batch_instruction(
    task_description: str,
    idx_first: int,
    idx_last: int,
    *,
    frame_step_sec: float = 0.5,
) -> str:
    rate = 1.0 / frame_step_sec if frame_step_sec > 0 else 0.0
    return f"""You evaluate a **robot manipulation** clip from a fixed camera (RGB stills).

**Intended task (operator specification):**
{task_description.strip()}

**Sampling:** one frame every **{frame_step_sec:g} s** of video time (~{rate:.4g} Hz); chronological order.
This batch: **global frame indices** {idx_first}–{idx_last}. Labels use `timestamp_sec` (≈ index × {frame_step_sec:g} s when sampling is uniform).

**Collective dynamics (mandatory — read before scoring):**
- Do **not** treat frames as independent photos. You must judge **the whole batch as one short motion clip**: how pose, gripper, and scene state **evolve across time** in this window.
- Reason about **trends**: approach vs retreat, opening/closing gripper, object motion, repeated micro-adjustments, stalls, jerky vs smooth changes, consistency with the task phase.
- Per-frame scores must **agree with that shared story**: if the trajectory shows friction, redundancy, or caution, reflect it (do not flatten everything to perfect scores).
- Mentally relate this segment to the **rest of the episode** (before/after): same task, continuous policy — avoid contradicting obvious long-horizon progress unless this segment itself is weak.

**Scoring — use the scale; 1.0 is rare:**
- **1.0** only when this segment’s dynamics are **excellent**: clear, safe, efficient progression toward the task with **no meaningful visible downside** in this clip (not merely “acceptable”).
- **0.85–0.95** — **common for competent execution** with small visible imperfections (slight sluggishness, extra repositioning, mild conservatism, minor alignment cost). Use this band when motion is basically fine but not flawless.
- **0.70–0.84** — visible issues: noticeable delay, awkward path, unclear intent for a stretch, occlusion limiting confidence, interaction that looks hesitant or inefficient **across the frames**.
- **Below 0.70** — serious problems: safety concern, wrong or risky interaction, clear stall with little progress over multiple frames, obvious task mismatch.
- **Vary** `score` / `safety` / `efficiency` across frames when the **dynamics** change (e.g. approach vs contact); do not assign identical triplets to every frame unless the clip is truly uniform.
- Batch-level `overall_score`, `safety`, `efficiency`, `task_match_score` must **match** the quality of this segment’s **combined** motion (not an average of forced 1.0s).

**`explain` (required, very concise):** English, **at most 3 bullet lines**, each **≤ 90 characters**. No paragraphs. No per-frame recap (only `details`). Name **dynamics** (e.g. “smooth approach→grasp”, “two stalls mid-segment”) and **why** batch metrics sit where they do.

**`predicted_task_prompt` (required):** One **very short** English imperative (target **≤ 100 characters**) — your best guess of what **instruction was given to the VLA** so the robot would produce **this** motion in the video (ignore the stated operator task if it conflicts; infer from **what you see**). Example style: “Grasp the object on the table and carry it to the sofa.” No quotes, no JSON, no bullet list.

**`details` (required):** Exactly **one row per frame** (indices {idx_first}…{idx_last}). Fields:
- `frame_index`, `second` — must match labels (`timestamp_sec`).
- `score`, `safety`, `efficiency` — per instant, consistent with the rubric and with **neighboring frames** in this batch.
- **`importance` (0.0–1.0) — critical calibration:**
  - **~0.3** for **unremarkable** frames: holding pose, slow drift, repetitive “more of the same”, background-only, no new contact or risk. **Most ordinary frames should be ~0.3** (use **0.25–0.35**).
  - **0.4–0.6** — active but non-critical: approach in open space, reorientation without contact, preparatory motion.
  - **0.75–1.0** only for **decisive** moments: contact, grasp/release, near collision / hazard visibility, fast or high-consequence motion, clear task-critical state change.
  - **Do not** use 0.7–0.9 for boring or static frames; over-weighting routine frames makes episode aggregation meaningless.
- `note` — one short factual sentence tied to **what changes** vs previous/next frame when relevant.

If the task text is ambiguous, assume a reasonable reading; still differentiate scores when visuals differ.
"""


def default_task() -> str:
    return (
        "The robot should complete the demonstrated manipulation task successfully "
        "and smoothly: approach the object, interact as required, and achieve a stable "
        "end state consistent with the episode goal."
    )
