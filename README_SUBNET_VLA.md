# Subnet VLA (ветка `master-vla`)

Chain-facing shim для `robokitchen-vla`: валидатор и майнеры живут в `xsubtensor/subnet-vla`, а канонический beta-contract и verifier/miner runtime остаются в `sources/kitchen-roboarm/services/task-api`.

## Протокол

- **`VLASynapse`** теперь несёт kitchen-beta envelope:
  - вход: `job_id`, `task_type`, `scene_id`, `layout_id`, `style_id`, `deadline_ms`, `validator_nonce`
  - выход: `artifact_manifest`, `episode_video_ref`, `video_url`, `score`, `score_components`
- Допустимые `task_type` берутся из RoboCasa `task-api` (`CloseDrawer`, `PnPCounterToCab`, ...).
- Старое поле `task` оставлено как compatibility alias для probe/debug сценариев.
- Fallback preview URL при отсутствии runtime ответа: `https://konnex-ai.xyz/videos/results_tidy/40.mp4`.

## Runtime shim

- Miner shim вызывает `POST /internal/mine` на kitchen runtime (`KONNEX_VLA_RUNTIME_BASE_URL`).
- Validator shim вызывает `POST /internal/verify` и переводит verifier verdict в on-chain reward signals.
- Если runtime недоступен, miner и validator откатываются к локальному stub/fallback path без падения процесса.

## Валидатор

- Каждый round — это `single-step episode` для одного kitchen job.
- Канонический scoring authority остаётся у verifier/runtime; chain shim только транслирует его в `score` / `set_weights`.
- Лог: строка `VLA_SCOREBOARD` + JSON с `runtime_verdict`.

## HTTP probe

`scripts/vla_probe_http.py` — `POST /v1/vla-probe`. Для kitchen path используйте `task_type` из `template/protocol.py`; старый `task` поддерживается только как debug/compat слой.

Интеграция с репозиторием **xsubtensor**: см. `REQUEST_TO_SUBNET_VLA.md` и `docker-compose.subnet-vla.yml`.

Оценка видео (пайплайн для `vla-video-analyzer`): каталог **`video-robot-eval/`** внутри этого же дерева `subnet-vla/`.
