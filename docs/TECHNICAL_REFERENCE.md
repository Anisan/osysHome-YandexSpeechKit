# YandexSpeechKit - Technical Reference

## Module Structure

Core files:

| File | Responsibility |
| --- | --- |
| `plugins/YandexSpeechKit/__init__.py` | Main plugin class, synthesis, cache, admin JSON actions |
| `plugins/YandexSpeechKit/forms/SettingForms.py` | Form fields, voice lists, emotion map |
| `plugins/YandexSpeechKit/templates/main_ysk.html` | Admin UI (settings + phrase cache tabs) |
| `plugins/YandexSpeechKit/translations/en.json` | English UI translations |
| `plugins/YandexSpeechKit/translations/ru.json` | Russian UI translations |

---

## Runtime Architecture

```mermaid
flowchart LR
    A[User calls say(message, level, args)] --> B[Resolve level interval]
    B --> C{skip?}
    C -->|Yes| D[Return without playback]
    C -->|No| E[Build cache key]
    E --> F{File exists in cache?}
    F -->|Yes| G[playSound(file, level)]
    F -->|No| H[Synthesize via Yandex API]
    H --> I[Save MP3 + index.json metadata]
    I --> G
```

### Plugin identity

- class: `YandexSpeechKit(BasePlugin)`
- `title`: `Yandex SpeechKit`
- `category`: `App`
- `version`: `0.1`
- `actions`: `say`

---

## Configuration Model

Saved keys in plugin config:

| Key | Type | Meaning |
| --- | --- | --- |
| `access_key` | string | Yandex API key |
| `api_version` | string | `v1` or `v3` |
| `speaker` | string | Default voice |
| `emotion` | string | Default role/intonation |
| `default_volume` | int/null | `0..100`; used as default volume input |
| `level_intervals` | list[dict] | Per-level behavior overrides |

### Level interval record shape

```json
{
  "min": 0,
  "max": 3,
  "skip": false,
  "emotion": "friendly",
  "volume": 75
}
```

Resolution rule:

- all matching intervals are sorted by width (`max - min`);
- the narrowest interval wins.

---

## Synthesis Pipeline

Entry methods:

- `synthesize(text, speaker=None, emotion=None, volume=None)`
- `synthesize_v1(...)`
- `synthesize_v3(...)`
- `synthesize_preview(...)`

### API v1 request

- endpoint: `https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize`
- auth: `Authorization: Api-Key <access_key>`
- payload fields: `text`, `lang=ru-RU`, `emotion`, `voice`, `format=mp3`
- response: streamed binary chunks

### API v3 request

- endpoint: `https://tts.api.cloud.yandex.net/tts/v3/utteranceSynthesis`
- auth: `Authorization: Api-Key <access_key>`
- JSON payload includes:
  - `text`
  - `outputAudioSpec.containerAudio.containerAudioType=MP3`
  - `hints` with `voice`, `role`, optional `volume`
  - `loudnessNormalizationType=LUFS`
- response audio is extracted from `audioChunk.data` or `result.audioChunk.data` and base64-decoded

### Volume conversion

User volume (`0..100`) is converted to LUFS hint by:

```text
lufs = -60 + (pct / 100) * 60
```

So `0% -> -60`, `100% -> 0`.

> [!NOTE]
> Volume hint is used only in v3 requests.

---

## `say(...)` Action Semantics

Signature:

```python
say(message, level=0, args=None)
```

Supported `args`:

- `voice` or `speaker`
- `emotion`
- `volume`

Behavior order:

1. Resolve level interval for `level`.
2. If interval has `skip=True`, return immediately.
3. Merge interval overrides (`emotion`, `volume`) with runtime `args` and config defaults.
4. Build cache key.
5. If cache miss, synthesize and store MP3.
6. Play cached MP3 via `playSound(file, level)`.

---

## Cache Key and Metadata Model

### Cache key algorithm

Two modes are used:

- default mode: `md5(message)`
- override mode (voice/emotion/volume overridden): `md5("message|speaker|emotion|volume?")`

Final file name:

```text
<md5>.mp3
```

### Cache storage helpers

- `findInCache(...)`, `getFullFilename(...)`, `getCacheDir()` from core cache library
- module cache directory is `getCacheDir()/YandexSpeechKit`

### Metadata index

Metadata is stored in a shared `index.json` in module cache root.

Index key:

- relative path to audio file inside module cache
- normalized to forward slashes

Metadata value includes:

```json
{
  "text": "...",
  "speaker": "marina",
  "emotion": "neutral",
  "volume": 70
}
```

---

## Admin JSON Actions

`admin(request)` handles both HTML form and JSON actions on POST.

### Supported JSON actions

| Action | Input | Output |
| --- | --- | --- |
| `preview` | `access_key`, `api_version`, `speaker`, `emotion`, optional `default_volume` | base64 MP3 |
| `cache_stats` | none | file count + human size |
| `cache_list` | none | cache items + stats |
| `cache_get` | `filename` | base64 MP3 + stored text |
| `cache_add` | `text` | synthesize and store phrase |
| `cache_delete` | `filename` | delete one cached file |
| `clear_cache` | none | remove full module cache |

### Cache list item shape

```json
{
  "filename": "a1b2c3.mp3",
  "size": 12345,
  "mtime": 1700000000,
  "text": "Cached phrase"
}
```

---

## Cache Operations API (Internal)

Main methods:

- `get_voice_cache_stats()`
- `list_voice_cache()`
- `get_cached_audio_base64(filename)`
- `get_cached_audio_meta(filename)`
- `delete_voice_cache_file(filename)`
- `clear_voice_cache()`
- `add_phrase_to_cache(message, args=None)`

Path safety:

- `_get_cache_file_path(...)` normalizes paths;
- strips leading separators;
- rejects traversal outside module cache root.

---

## Frontend Behavior (`main_ysk.html`)

UI logic includes:

- dynamic voice filtering by API version;
- dynamic emotion filtering by selected speaker;
- preview button with loading state;
- level-interval table editor serialized into hidden JSON field (`level_intervals_json`);
- phrase cache table with client-side filter and sort;
- per-item play/download/delete actions using JSON requests.

---

## Error Handling

- non-200 Yandex API responses raise `RuntimeError` with response code and text;
- admin JSON handlers return `{success: false, error: ...}` with HTTP 4xx/5xx as needed;
- synthesis and cache write paths are wrapped with exception logging;
- empty cache files are detected and removed before playback.

---

## Known Caveats

> [!WARNING]
> `v1` requests hardcode `lang=ru-RU`, so multilingual output is not configurable in current implementation.

Other caveats:

- plugin `version` is still `0.1`;
- `initialization()` is empty;
- cache stats are recursive and include any file in module cache folder, not only MP3;
- if a cached MP3 exists without metadata, index entry is recreated lazily on next access.

---

## See Also

- [User Guide](USER_GUIDE.md)
- [Module index](index.md)
