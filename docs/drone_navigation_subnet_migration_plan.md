# Drone Navigation -> Bittensor Subnet Migration Plan

Goal: produce a standalone subnet repository (this `xsubnet-template` fork) that can run drone navigation miners and validators without depending on the old monolithic runtime layout.

## Target architecture

- **Protocol layer** (`template/protocol.py`)
  - Replace math payload with navigation task payload:
    - task/instruction text
    - optional start pose / episode id
    - optional validation mode flags
  - Miner response:
    - action trace (or world-delta trace),
    - final pose/status,
    - optional artifact references (video/frame bundle),
    - execution metadata (latency, model id, run id).

- **Miner neuron** (`neurons/miner.py`)
  - Wrap OpenFly runtime invocation (attach mode or embedded mode by config).
  - Execute one evaluation episode per request against UE + policy.
  - Return compact deterministic outputs for validator scoring.
  - Persist rich artifacts to local/object storage (not on-chain).

- **Validator neuron** (`neurons/validator.py`, `template/validator/*`)
  - Sample miners and send same task/seed.
  - Score by navigation objective:
    - success / goal proximity / safety constraints / path quality.
  - Optionally run secondary verifier (video/text judge, similar to `video-robot-eval` pattern).
  - Update weights with anti-cheat sanity checks and timeout penalties.

- **Ops surfaces**
  - Probe API (similar to `vla_probe_http.py`) for external integrations.
  - Deterministic logs for rollout replay and dispute/debug workflows.
  - Docker profiles for miner and validator roles with GPU-aware runtime.

## Migration phases

### Phase 0: Repo scaffolding and assets

- Keep this repo as canonical subnet codebase.
- Pin nested submodule `OpenFly-Platform` for runtime logic reuse.
- Define machine bootstrap doc for:
  - model weights location,
  - UE environment installation,
  - required env vars.

### Phase 1: Protocol definition

- Introduce `DroneNavSynapse` in `template/protocol.py`.
- Freeze a minimal response schema that is robust across miner implementations.
- Add schema validation + backward-compatible version field.

### Phase 2: Miner integration

- Replace stub/math miner forward with real OpenFly episode execution.
- Start with single-step deterministic task set (known teleports + instructions).
- Add strict timeouts and structured error codes (`timeout`, `ue_unavailable`, `policy_unloaded`).

### Phase 3: Validator scoring loop

- Build reward function around objective metrics (success, NE, SPL, collision penalties).
- Add fallback rewards for partial outputs to avoid all-zero rounds.
- Add deterministic sampling by seed so validator reruns are reproducible.

### Phase 4: Validation service split

- Extract optional heavy verification (video/frame judging) to a sidecar service.
- Keep on-chain critical logic lightweight in validator process.
- Store heavy artifacts externally and reference by hash/URI.

### Phase 5: Deployment hardening

- Add compose/systemd templates for:
  - miner node with UE + model,
  - validator node with scoring dependencies.
- Add health checks and startup sequencing (UE readiness gate, UnrealCV socket checks).
- Add CI checks for protocol compatibility and mock forward tests.

## Mapping from current services to subnet components

- Current dashboard/backend service -> mostly **miner runtime adapter** + optional operator UI.
- Current UE process management -> **miner-side execution backend**.
- Current competition/judge utilities -> part of **validator scoring/verification pipeline**.
- Current telemetry/log files -> **miner and validator observability layer**.

## Risks and mitigations

- **UE startup instability** (Xvfb/locks/sockets): enforce startup gate and lock cleanup in miner container.
- **Non-deterministic scoring**: freeze task sets/seeds for validator rounds, normalize timeout behavior.
- **Heavy artifact transfer**: do not move videos through synapse payload; return compact references + hashes.
- **GPU contention**: isolate miner runtime and optional verification workers into separate containers/profiles.

## Immediate next implementation tasks

1. Add `DroneNavSynapse` with versioned fields.
2. Port miner forward from stub to OpenFly call wrapper with mocked fallback.
3. Port validator reward from stub/random to objective metrics.
4. Add probe endpoint and one end-to-end localnet smoke scenario.
