# Drone Navigation: Branch Notes (`main` vs `master-vla`)

This document captures what was reviewed in `xsubnet-template` before designing the migration.

## `main` branch (current default)

- Protocol is math-only: `template/protocol.py` defines `MathSynapse`.
- `neurons/miner.py` answers arithmetic with noise.
- `template/validator/forward.py` generates math tasks, queries miners, computes rewards, updates weights.
- This branch is clean for subnet scaffolding, but not aligned with robot/video navigation payloads.

## `master-vla` branch

- Replaces math protocol with `VLASynapse(task, video_url)`.
- Includes VLA stub miner flow and validator flow for task -> video URL scoring.
- Adds helper services/scripts:
  - `scripts/vla_probe_http.py` and probe library (HTTP endpoint over subnet query flow).
  - `video-robot-eval/` for MP4 evaluation pipeline.
  - static video artifacts and POC scripts for local testing.
- Good reference for shape of task-based subnet I/O, but still a stub (no real UE rollout execution in miner).

## Implication for drone-navigation subnet

- We should keep the robust subnet skeleton from `main` (base neuron lifecycle, config, logging, weights loop).
- We should reuse `master-vla` ideas for:
  - task-centric synapse contract,
  - probe API patterns,
  - optional video evaluator sidecar.
- Real value path must replace stub video URLs with actual OpenFly/UE-backed rollout outputs.
