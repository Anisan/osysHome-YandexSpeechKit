# YandexSpeechKit - Техническая документация

## Структура модуля

Основные файлы:

| Файл | Назначение |
| --- | --- |
| `plugins/YandexSpeechKit/__init__.py` | Основной класс плагина, синтез, кэш, JSON-действия admin |
| `plugins/YandexSpeechKit/forms/SettingForms.py` | Поля формы, списки голосов, карта эмоций |
| `plugins/YandexSpeechKit/templates/main_ysk.html` | UI админки (вкладки настроек и кэша фраз) |
| `plugins/YandexSpeechKit/translations/en.json` | Английские переводы UI |
| `plugins/YandexSpeechKit/translations/ru.json` | Русские переводы UI |

---

## Архитектура выполнения

```mermaid
flowchart LR
    A[Пользователь вызывает say(message, level, args)] --> B[Определение интервала level]
    B --> C{skip?}
    C -->|Да| D[Возврат без воспроизведения]
    C -->|Нет| E[Формирование cache key]
    E --> F{Файл есть в кэше?}
    F -->|Да| G[playSound(file, level)]
    F -->|Нет| H[Синтез через Yandex API]
    H --> I[Сохранение MP3 + метаданные в index.json]
    I --> G
```

### Идентификация плагина

- class: `YandexSpeechKit(BasePlugin)`
- `title`: `Yandex SpeechKit`
- `category`: `App`
- `version`: `0.1`
- `actions`: `say`

---

## Модель конфигурации

Сохраняемые ключи в конфиге плагина:

| Ключ | Тип | Смысл |
| --- | --- | --- |
| `access_key` | string | API-ключ Yandex |
| `api_version` | string | `v1` или `v3` |
| `speaker` | string | Голос по умолчанию |
| `emotion` | string | Роль/интонация по умолчанию |
| `default_volume` | int/null | `0..100`; громкость по умолчанию |
| `level_intervals` | list[dict] | Переопределения поведения по уровням |

### Формат записи интервала уровней

```json
{
  "min": 0,
  "max": 3,
  "skip": false,
  "emotion": "friendly",
  "volume": 75
}
```

Правило выбора:

- среди подходящих интервалов сортировка идет по ширине (`max - min`);
- применяется самый узкий (наиболее специфичный) интервал.

---

## Пайплайн синтеза

Точки входа:

- `synthesize(text, speaker=None, emotion=None, volume=None)`
- `synthesize_v1(...)`
- `synthesize_v3(...)`
- `synthesize_preview(...)`

### Запрос API v1

- endpoint: `https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize`
- auth: `Authorization: Api-Key <access_key>`
- поля payload: `text`, `lang=ru-RU`, `emotion`, `voice`, `format=mp3`
- ответ: stream бинарных чанков

### Запрос API v3

- endpoint: `https://tts.api.cloud.yandex.net/tts/v3/utteranceSynthesis`
- auth: `Authorization: Api-Key <access_key>`
- JSON payload включает:
  - `text`
  - `outputAudioSpec.containerAudio.containerAudioType=MP3`
  - `hints` с `voice`, `role`, опционально `volume`
  - `loudnessNormalizationType=LUFS`
- аудио извлекается из `audioChunk.data` или `result.audioChunk.data` и декодируется из base64

### Конвертация громкости

Громкость пользователя (`0..100`) переводится в LUFS-подсказку формулой:

```text
lufs = -60 + (pct / 100) * 60
```

То есть `0% -> -60`, `100% -> 0`.

> [!NOTE]
> Подсказка громкости используется только в запросах v3.

---

## Семантика действия `say(...)`

Сигнатура:

```python
say(message, level=0, args=None)
```

Поддерживаемые `args`:

- `voice` или `speaker`
- `emotion`
- `volume`

Порядок работы:

1. Определяется интервал для входного `level`.
2. Если в интервале `skip=True`, метод завершает работу.
3. Переопределения из интервала (`emotion`, `volume`) объединяются с `args` и дефолтами конфига.
4. Строится cache key.
5. При cache miss выполняется синтез и сохранение MP3.
6. Кэшированный MP3 воспроизводится через `playSound(file, level)`.

---

## Cache key и модель метаданных

### Алгоритм cache key

Используются два режима:

- базовый режим: `md5(message)`
- режим override (переопределены voice/emotion/volume): `md5("message|speaker|emotion|volume?")`

Итоговое имя файла:

```text
<md5>.mp3
```

### Хелперы хранилища кэша

- `findInCache(...)`, `getFullFilename(...)`, `getCacheDir()` из core cache library
- каталог кэша модуля: `getCacheDir()/YandexSpeechKit`

### Индекс метаданных

Метаданные хранятся в общем `index.json` в корне кэша модуля.

Ключ индекса:

- относительный путь к аудиофайлу внутри кэша модуля
- нормализуется через `/`

Значение метаданных содержит:

```json
{
  "text": "...",
  "speaker": "marina",
  "emotion": "neutral",
  "volume": 70
}
```

---

## Admin JSON actions

`admin(request)` обрабатывает и HTML-форму, и JSON-действия при POST.

### Поддерживаемые JSON-действия

| Action | Вход | Выход |
| --- | --- | --- |
| `preview` | `access_key`, `api_version`, `speaker`, `emotion`, опционально `default_volume` | base64 MP3 |
| `cache_stats` | нет | число файлов + размер в читаемом формате |
| `cache_list` | нет | список кэша + статистика |
| `cache_get` | `filename` | base64 MP3 + сохраненный текст |
| `cache_add` | `text` | синтез и сохранение фразы |
| `cache_delete` | `filename` | удаление одного кэш-файла |
| `clear_cache` | нет | очистка всего кэша модуля |

### Формат элемента списка кэша

```json
{
  "filename": "a1b2c3.mp3",
  "size": 12345,
  "mtime": 1700000000,
  "text": "Cached phrase"
}
```

---

## API операций с кэшем (внутреннее)

Основные методы:

- `get_voice_cache_stats()`
- `list_voice_cache()`
- `get_cached_audio_base64(filename)`
- `get_cached_audio_meta(filename)`
- `delete_voice_cache_file(filename)`
- `clear_voice_cache()`
- `add_phrase_to_cache(message, args=None)`

Безопасность пути:

- `_get_cache_file_path(...)` нормализует путь;
- убирает ведущие разделители;
- отклоняет path traversal за пределы каталога кэша модуля.

---

## Поведение фронтенда (`main_ysk.html`)

UI-логика включает:

- динамическую фильтрацию голосов по версии API;
- динамическую фильтрацию эмоций по выбранному голосу;
- кнопку предпрослушивания с состоянием загрузки;
- редактор таблицы интервалов уровней с сериализацией в hidden JSON (`level_intervals_json`);
- таблицу кэша фраз с клиентским фильтром и сортировкой;
- действия по элементам (play/download/delete) через JSON-запросы.

---

## Обработка ошибок

- при ответе Yandex API с кодом не `200` выбрасывается `RuntimeError` с кодом и текстом;
- обработчики admin JSON возвращают `{success: false, error: ...}` и HTTP 4xx/5xx при необходимости;
- пути синтеза и записи в кэш обернуты логированием исключений;
- пустые кэш-файлы обнаруживаются и удаляются до воспроизведения.

---

## Известные нюансы

> [!WARNING]
> Для `v1` язык зафиксирован как `lang=ru-RU`, поэтому многоязычный синтез в текущей реализации не настраивается.

Другие нюансы:

- `version` плагина пока `0.1`;
- `initialization()` пустой;
- статистика кэша рекурсивная и учитывает любые файлы в каталоге кэша модуля, не только MP3;
- если MP3 уже есть, но в `index.json` нет записи, метаданные дозапишутся лениво при следующем обращении.

---

## См. также

- [Руководство пользователя](USER_GUIDE.ru.md)
- [Индекс модуля](index.ru.md)
