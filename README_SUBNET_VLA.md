# Subnet VLA (ветка `master-vla`)

Демо-сабнет: **текстовая задача для «робота»** → майнеры отвечают **одной и той же заглушкой видео** (пока нет настоящей VLA).

## Протокол

- **`VLASynapse`**: поле `task` (строка), ответ `video_url`.
- Допустимые задачи (как в UI симулятора):
  - `Clean-up the guestroom`
  - `Clean-up the kitchen`
  - `Prepare groceries`
  - `Setup the table`
- Заглушка URL: `https://konnex-ai.xyz/videos/results_tidy/40.mp4` (константа в `template/protocol.py`).

## Валидатор

- Случайная задача из списка, опрос `sample_size` майнеров.
- **Веса**: почти равные + небольшой случайный jitter, нормализация к сумме 1 (`template/validator/reward.py`).
- Лог: строка `VLA_SCOREBOARD` + JSON.

## HTTP probe

`scripts/vla_probe_http.py` — `POST /v1/vla-probe`, тело JSON с полем `task`.

Интеграция с репозиторием **xsubtensor**: см. `REQUEST_TO_SUBNET_VLA.md` и `docker-compose.subnet-vla.yml`.
