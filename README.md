# YandexSpeechKit - Yandex Text-to-Speech

Text-to-speech synthesis using Yandex SpeechKit API for converting text to speech.

## Description

The `YandexSpeechKit` plugin provides text-to-speech capabilities for the osysHome platform using Yandex SpeechKit API. It converts text messages to speech audio files with intelligent caching support to optimize API usage and improve performance.

## Main Features

- ✅ **Text-to-Speech Synthesis**: Convert text to high-quality speech audio using Yandex SpeechKit API
- ✅ **Multiple Voice Options**: Choose from many voice personalities (API v1 and v3)
- ✅ **Emotion Control**: Adjust speech emotion (neutral, whisper, friendly, good, strict, etc.)
- ✅ **Per-call Override**: Override voice and emotion via `args` for individual `say` calls
- ✅ **Smart Audio Caching**: Automatically cache generated audio files using MD5 hash to avoid redundant API calls
- ✅ **MP3 Format**: Generate audio in widely compatible MP3 format
- ✅ **Web Admin Interface**: Easy configuration through web-based admin panel

## Admin Panel

The plugin provides a user-friendly admin interface accessible from the osysHome dashboard:

- **Access Key Configuration**: Enter your Yandex SpeechKit API key
- **Voice Selection**: Choose from available voices
- **Emotion Settings**: Select the desired emotion for speech synthesis

## Configuration

Configure the following parameters through the admin panel:

- **Access Key**: Your Yandex SpeechKit API access key (required)
  - Get your API key from [Yandex Cloud Console](https://console.cloud.yandex.com/)
- **Speaker**: Voice selection (default: `marina`)
- **Emotion**: Speech emotion (default: `neutral`)

## Available Voices

**API v1 and v3:**
- marina (F, default), alena (F), filipp (M), ermil (M), jane (F), omazh (F), zahar (M), madi_ru (M)

**API v3 only:**
- dasha (F), julia (F), lera (F), masha (F), saule_ru (F), zamira_ru (F), zhanar_ru (F), yulduz_ru (F)
- alexander (M), anton (M), kirill (M)

## Available Emotions (intonations)

Supported emotions depend on the selected voice:
- **neutral** — neutral (default)
- **good** — joyful
- **evil** — irritated
- **friendly** — friendly, warm
- **strict** — strict
- **whisper** — whispered speech

For more details about voices and emotions per voice, see [Yandex SpeechKit documentation](https://yandex.cloud/ru/docs/speechkit/tts/voices).

## Usage

### Programmatic Usage

Use the `say` action to synthesize and play speech:

```python
from app.core.lib.common import say

# Simple call (uses configured voice and emotion)
say("Hello, this is a test")

# Call with custom voice and emotion via args
say("Привет! Это радостное сообщение", level=0, args={
    "voice": "marina",
    "emotion": "good"
})

# Alternative: use callPluginFunction
app.callPluginFunction("YandexSpeechKit", "say", {
    "message": "Hello, this is a test",
    "level": 0,
    "args": {
        "voice": "jane",
        "emotion": "friendly"
    }
})
```

**args** (dict) supports:
- `voice` or `speaker` — override configured voice (e.g. `marina`, `jane`, `alexander`)
- `emotion` — override configured intonation (e.g. `neutral`, `good`, `whisper`, `friendly`)

### How It Works

1. The plugin receives text to synthesize
2. Creates MD5 hash of the text for caching
3. Checks if cached audio file exists
4. If not cached, calls Yandex SpeechKit API to synthesize speech
5. Saves audio file to cache
6. Plays the audio file

## Technical Details

- **API Endpoint**: `https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize`
- **Audio Format**: MP3
- **Language**: Russian (ru-RU)
- **Caching**: MD5 hash-based file caching system
- **Error Handling**: Comprehensive exception handling with logging
- **Directory Management**: Automatic creation of cache directories

## Version

Current version: **0.1**

## Category

App

## Actions

The plugin provides the following actions:

- **say**: Synthesize text to speech and play audio
  - Parameters:
    - `message` (string): Text to synthesize
    - `level` (int): Audio level (default: 0)
    - `args` (dict): Additional arguments
      - `voice` or `speaker` (str): Override voice for this call
      - `emotion` (str): Override intonation (e.g. `neutral`, `good`, `whisper`, `friendly`)

## Requirements

- Python 3.x
- requests library
- osysHome core system
- Yandex Cloud account with SpeechKit API access

## Installation

1. Place the plugin in the `plugins/YandexSpeechKit/` directory
2. Restart osysHome
3. Configure the plugin through the admin panel
4. Enter your Yandex SpeechKit API key
5. Select preferred voice and emotion settings

## Troubleshooting

### Common Issues

- **API Key Error**: Ensure your API key is valid and has SpeechKit permissions
- **Network Issues**: Check internet connectivity and Yandex Cloud service status
- **Cache Problems**: Plugin automatically creates cache directories with proper permissions
- **Empty Audio Files**: Check API response and available disk space

### Logs

Check plugin logs for detailed error messages and debugging information.

## Author

osysHome Team

## License

See the main osysHome project license

