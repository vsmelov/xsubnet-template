# video-robot-eval

Оценка робота по MP4: **ffmpeg** (1 FPS) + **LangChain** structured output + **OpenCV** в `requirements.txt` как fallback.

## Docker

```bash
cd subnet-vla/video-robot-eval
cp .env.example .env
# в .env: OPENAI_API_KEY=...

docker compose build
docker compose run --rm eval
```

**Результат:** весь отчёт (метрики, токены, оценка USD) печатается в **stdout** как JSON. Логи прогресса — в stderr. Чтобы сохранить в файл:

```bash
docker compose run --rm eval python -m app.main --work-dir /app/work --output /app/work/report.json
```

Свои URL / задача:

```bash
docker compose run --rm eval python -m app.main \
  --url "https://example.com/clip.mp4" \
  --task "Pick the red cube and place it in the box." \
  --work-dir /app/work
```

**Промпт** (текст инструкции к модели): файл [`app/prompts.py`](app/prompts.py) — функция `batch_instruction()`; к каждому кадру в [`app/main.py`](app/main.py) добавляются строки вида `frame_index=… timestamp_sec=…`.

Образ уже содержит **ffmpeg**; **opencv** ставится через `pip` из `requirements.txt`.

### Проверка без API (только раскадровка)

```bash
python -m app.main --local-video path/to/clip.mp4 --work-dir work --dry-run-frames --output smoke.json
```

### Проверка «всё работает»

Полный прогон с OpenAI нужен **`OPENAI_API_KEY`** в `.env` или в окружении. Без ключа можно проверить скачивание/нарезку флагом **`--dry-run-frames`**.

## Локально (без Docker)

Нужны Python 3.12+ и по возможности `ffmpeg` в PATH. Иначе используется OpenCV.

```bash
pip install -r requirements.txt
python -m app.main
```
