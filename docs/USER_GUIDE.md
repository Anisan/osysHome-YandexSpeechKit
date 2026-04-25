# YandexSpeechKit - User Guide

![YandexSpeechKit Icon](../static/YandexSpeechKit.png "YandexSpeechKit plugin")

## Purpose

`YandexSpeechKit` is a text-to-speech module for osysHome that uses Yandex Cloud SpeechKit.

The module is designed to:

- synthesize spoken audio from text via Yandex TTS API;
- support API `v1` and `v3` modes;
- select voice and intonation (emotion/role);
- optionally set default volume (`0..100`) for API `v3`;
- cache generated MP3 files and reuse them;
- manage phrase cache from the admin UI.

> [!IMPORTANT]
> The module does both synthesis and local cache management. Repeated phrases are usually played from cache without a new API call.

---

## What the User Gets

| Capability | What it does |
| --- | --- |
| Voice synthesis | Converts text into MP3 speech |
| Voice profiles | Supports multiple speakers and intonations |
| API mode switch | Lets you choose `v1` or `v3` |
| Preview | Plays test audio in settings before saving |
| Level intervals | Overrides emotion/volume or skips speech by `level` range |
| Phrase cache UI | Lists, filters, plays, downloads, deletes, and pre-caches phrases |

---

## Interface Overview

Admin page path:

```text
/admin/YandexSpeechKit
```

The page has two tabs:

1. `Settings`
2. `Phrase cache`

### Settings tab sections

- `Connection`: API key input.
- `Voice and intonation`: API version, speaker, intonation, default volume, preview button.
- `Level intervals`: rules by `say(level=...)` range.
- `Cache`: summary and full cache clear button.

### Phrase cache tab actions

- refresh cache list;
- clear all cached files;
- add new text phrase to cache;
- filter and sort by phrase text;
- per-row actions: play, download, delete.

---

## Quick Start Checklist

- [ ] Open `/admin/YandexSpeechKit`.
- [ ] Paste your Yandex Cloud API key.
- [ ] Choose `API version` (`v1` or `v3`).
- [ ] Select `Voice` and `Intonation`.
- [ ] (Optional) set `Default volume` (`0..100`, meaningful for `v3`).
- [ ] Click `Listen` to preview.
- [ ] Save settings.
- [ ] Trigger speech with `say("...")` from your scenario/script.

---

## Configuration Details

| Field | Required | Description |
| --- | --- | --- |
| `access_key` | Yes | Yandex Cloud API key |
| `api_version` | Yes | `v1` or `v3` |
| `speaker` | Yes | Selected voice profile |
| `emotion` | Yes | Selected intonation/role |
| `default_volume` | No | `0..100`; converted to LUFS hint for `v3` |

### API version behavior

- `v1` uses endpoint `/speech/v1/tts:synthesize`.
- `v3` uses endpoint `/tts/v3/utteranceSynthesis` and supports volume hint.

> [!NOTE]
> If `v1` is selected, voices are filtered to those supported by v1 in the UI.

---

## Supported Usage Patterns

### Basic speech output

```python
from app.core.lib.common import say

say("System is armed")
```

### Per-call voice override

```python
say("Attention please", args={
    "voice": "jane",
    "emotion": "good"
})
```

### Per-call volume override

```python
say("Night mode enabled", args={
    "volume": 35
})
```

### Full call through plugin function

```python
app.callPluginFunction("YandexSpeechKit", "say", {
    "message": "Garage is open",
    "level": 2,
    "args": {
        "speaker": "marina",
        "emotion": "friendly",
        "volume": 70
    }
})
```

---

## Level Intervals (Priority Rules)

You can define multiple level ranges with overrides:

- `min`, `max` range;
- `skip` (do not speak);
- forced `emotion`;
- forced `volume`.

Example:

| Min | Max | Skip | Emotion | Volume |
| --- | --- | --- | --- | --- |
| 0 | 2 | No | friendly | 80 |
| 3 | 5 | No | neutral | 60 |
| 6 | 10 | Yes | neutral | - |

If multiple ranges match, the module applies the narrower (more specific) interval first.

---

## Phrase Cache Management

The module stores MP3 files in module cache and keeps metadata (text, speaker, emotion, volume).

From UI you can:

- add phrase to cache without playback;
- inspect phrase text and hash ID;
- play cached audio;
- download cached MP3;
- delete one file;
- clear full cache.

> [!TIP]
> After changing main voice profile, clear cache to regenerate old phrases with the new voice.

---

## Troubleshooting

### Preview does not play

Check:

- API key is filled;
- internet access to Yandex TTS endpoints;
- selected voice/emotion is valid for the selected API version.

### Phrases are voiced with old settings

Cause: existing cache entry.

Fix: clear cache and synthesize again.

### No sound in runtime `say(...)`

Check:

- message text is not empty;
- the host playback subsystem works (`playSound` path);
- logs for API errors and empty response warnings.

---

## See Also

- [Technical Reference](TECHNICAL_REFERENCE.md)
- [Module index](index.md)
