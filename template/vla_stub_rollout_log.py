"""
Plain English stub logs for one VLA rollout (one scenario, one video, sub-tasks).
Uses bittensor default logger; short random sleep after each line.
"""

from __future__ import annotations

import random
import time

import bittensor as bt


def _subtasks_for_task(task: str) -> list[str]:
    t = task.lower()
    if "guestroom" in t or "guest" in t:
        return [
            "navigate_to_clutter",
            "pick_loose_items",
            "navigate_to_couch",
            "place_on_surface",
            "tidy_surfaces",
            "verify_room_state",
        ]
    if "kitchen" in t:
        return [
            "navigate_to_counter",
            "pick_utensils_and_trash",
            "navigate_to_sink",
            "rinse_or_sort",
            "place_in_dish_area",
            "wipe_counter",
        ]
    if "grocer" in t:
        return [
            "navigate_to_pantry",
            "pick_bags_and_boxes",
            "navigate_to_fridge",
            "stock_shelves",
            "align_labels_outward",
            "verify_inventory",
        ]
    if "table" in t:
        return [
            "navigate_to_storage",
            "pick_dishes",
            "navigate_to_table",
            "place_settings",
            "align_utensils",
            "final_arrangement_check",
        ]
    return [
        "observe_scene",
        "plan_motion",
        "execute_skill_chain",
        "refine_trajectory",
        "render_episode",
    ]


def run_verbose_stub_rollout(
    task: str,
    req_id: str,
    *,
    min_delay_s: float = 0.18,
    max_delay_s: float = 0.45,
) -> None:
    subtasks = _subtasks_for_task(task)
    seed = random.randint(1000, 9999)
    scene_id = random.choice(
        [
            "v3_sc1_staging_04.scene_instance.json",
            "knx_vla_guestroom_v1.scene.json",
            "tidy_house_single_room_v2.json",
        ]
    )

    def log_line(msg: str) -> None:
        bt.logging.info(msg)
        time.sleep(random.uniform(min_delay_s, max_delay_s))

    log_line("=" * 80)
    log_line("VLA ROLLOUT: single episode (one scenario, one output video)")
    log_line("=" * 80)
    log_line("Device: cuda:0 (stub worker, weights in VRAM)")
    log_line("ManiSkill ASSET_DIR: /lambda/nfs/knx-west/.maniskill_nfs/data")
    log_line(f"Request id: {req_id}")
    log_line(f"Task instruction: {task!r}")
    log_line("Mode: 1 scenario x 1 seed; one MP4 per request")
    log_line(f"Execution seed: {seed}")
    log_line(f"Scene build_config: {scene_id}")
    log_line(f"Sub-steps for this episode ({len(subtasks)}): {subtasks}")
    log_line("Stochastic policy: True")
    log_line("save_trajectory: True, record_env_state: True, save_video: True")
    log_line("Creating environment SingleTaskEpisode-v0...")
    log_line("Resolution 1280x720, sim_backend=gpu, render_backend=gpu")
    log_line(
        "mani_skill WARNING: shader_dir will be deprecated; use sensor_configs instead."
    )
    log_line("Environment ready; info-dict transition patch applied.")
    log_line("Loading experts: mshab_checkpoints=/lambda/nfs/knx-west/mshab_checkpoints")
    log_line("Loaded navigate/all")
    log_line("Loaded pick/all")
    log_line("Loaded place/all")
    log_line("NNPACK WARNING: Unsupported hardware (stub)")
    log_line("Generating trajectory for this episode...")
    for i, st in enumerate(subtasks, start=1):
        log_line(f"Transition to sub-task {i}/{len(subtasks)}: {st}")
        if i == max(1, len(subtasks) // 2) and random.random() < 0.3:
            log_line(
                f"WARNING: sub-task {i} ({st}) hit step limit 200; "
                "closing segment and continuing episode."
            )
    log_line("Episode finished (stub success).")
    log_line("Encoding H.264 and muxing timestamps...")
    log_line("Uploading result object to bucket...")
    log_line(f"Rollout complete [{req_id}].")
