import os
import base64
import requests
import hashlib
import shutil
import json
from flask import jsonify
from app.core.main.BasePlugin import BasePlugin
from plugins.YandexSpeechKit.forms.SettingForms import SettingsForm, V1_VOICES, VOICE_EMOTIONS
from app.core.lib.common import playSound
from app.core.lib.cache import getFullFilename, findInCache, getCacheDir

class YandexSpeechKit(BasePlugin):

    def __init__(self,app):
        super().__init__(app,__name__)
        self.title = "Yandex SpeechKit"
        self.description = """This is a plugin get voice by text"""
        self.category = "App"
        self.version = "0.1"
        self.actions = ["say"]

    def initialization(self):
        pass

    def admin(self, request):
        # Handle preview request
        if request.method == 'POST' and request.is_json:
            data = request.get_json()
            
            # Preview voice
            if data.get('action') == 'preview':
                try:
                    access_key = data.get('access_key')
                    api_version = data.get('api_version', 'v1')
                    speaker = data.get('speaker', 'marina')
                    emotion = data.get('emotion', 'neutral')
                    volume = data.get('default_volume')
                    if volume is not None:
                        try:
                            volume = int(volume)
                        except (TypeError, ValueError):
                            volume = None
                    
                    if not access_key:
                        return jsonify({'success': False, 'error': 'Access key is required'}), 400
                    
                    # Generate preview audio
                    preview_text = "Привет! Это пример голоса."
                    audio_data = self.synthesize_preview(preview_text, access_key, speaker, emotion, api_version, volume)
                    
                    return jsonify({
                        'success': True,
                        'audio': audio_data
                    })
                except Exception as e:
                    self.logger.exception(f"Preview error: {e}")
                    return jsonify({'success': False, 'error': str(e)}), 500
            
            # Clear cache
            elif data.get('action') == 'clear_cache':
                try:
                    deleted_count = self.clear_voice_cache()
                    return jsonify({
                        'success': True,
                        'count': deleted_count
                    })
                except Exception as e:
                    self.logger.exception(f"Clear cache error: {e}")
                    return jsonify({'success': False, 'error': str(e)}), 500
        
        # Regular form handling
        settings = SettingsForm()
        if request.method == 'GET':
            settings.access_key.data = self.config.get('access_key','')
            settings.api_version.data = self.config.get('api_version','v1')
            settings.speaker.data = self.config.get("speaker",'marina')
            settings.emotion.data = self.config.get("emotion",'neutral')
            settings.default_volume.data = self.config.get("default_volume")
        else:
            if settings.validate_on_submit():
                self.config["access_key"] = settings.access_key.data
                self.config["api_version"] = settings.api_version.data
                self.config["speaker"] = settings.speaker.data
                self.config["emotion"] = settings.emotion.data
                self.config["default_volume"] = settings.default_volume.data
                raw = request.form.get("level_intervals_json", "[]")
                try:
                    intervals = json.loads(raw) if raw else []
                    self.config["level_intervals"] = [x for x in intervals if isinstance(x, dict) and "min" in x and "max" in x]
                except (json.JSONDecodeError, TypeError):
                    pass
                self.saveConfig()
        content = {
            "form": settings,
            "v1_voices": V1_VOICES,
            "voice_emotions": VOICE_EMOTIONS,
            "level_intervals": self.config.get("level_intervals") or [],
        }
        return self.render('main_ysk.html', content)

    def _volume_to_lufs(self, pct):
        """Convert user volume 0-100% to LUFS. API: range [-145,0), default -19. Use [-60,0] for practical range."""
        if pct is None or pct < 0 or pct > 100:
            return None
        return -60 + (pct / 100.0) * 60  # 0% -> -60, 100% -> 0

    def synthesize(self, text, speaker=None, emotion=None, volume=None):
        """Synthesize text to speech. volume: 0-100%, applied in API request (v3 only)."""
        api_version = self.config.get("api_version", "v1")
        speaker = speaker or self.config.get("speaker", "marina")
        emotion = emotion or self.config.get("emotion", "neutral")

        if api_version == "v3":
            return self.synthesize_v3(text, speaker, emotion, volume)
        else:
            return self.synthesize_v1(text, speaker, emotion, volume)
    
    def synthesize_v1(self, text, speaker=None, emotion=None, volume=None):
        """Synthesize using API v1. Volume not supported in v1, ignored."""
        speaker = speaker or self.config.get("speaker", "marina")
        emotion = emotion or self.config.get("emotion", "neutral")
        url = 'https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize'
        headers = {
            'Authorization': 'Api-Key ' + self.config["access_key"],
        }

        data = {
            'text': text,
            'lang': 'ru-RU',
            'emotion': emotion,
            'voice': speaker,
            'format': 'mp3',
        }

        with requests.post(url, headers=headers, data=data, stream=True) as resp:
            if resp.status_code != 200:
                raise RuntimeError("Invalid response received: code: %d, message: %s" % (resp.status_code, resp.text))

            for chunk in resp.iter_content(chunk_size=None):
                yield chunk
    
    def synthesize_v3(self, text, speaker=None, emotion=None, volume=None):
        """Synthesize using API v3. volume: 0-100% -> LUFS hint."""
        speaker = speaker or self.config.get("speaker", "marina")
        emotion = emotion or self.config.get("emotion", "neutral")
        url = 'https://tts.api.cloud.yandex.net/tts/v3/utteranceSynthesis'
        headers = {
            'Authorization': 'Api-Key ' + self.config["access_key"],
            'Content-Type': 'application/json',
        }

        hints = [{"voice": speaker}, {"role": emotion}]
        lufs = self._volume_to_lufs(volume)
        if lufs is not None:
            hints.append({"volume": lufs})

        payload = {
            "text": text,
            "outputAudioSpec": {
                "containerAudio": {
                    "containerAudioType": "MP3"
                }
            },
            "hints": hints,
            "loudnessNormalizationType": "LUFS"
        }

        resp = requests.post(url, headers=headers, json=payload)
        if resp.status_code != 200:
            raise RuntimeError("Invalid response received: code: %d, message: %s" % (resp.status_code, resp.text))

        data = resp.json()
        # API может возвращать data.audioChunk или data.result.audioChunk
        chunk = data.get("audioChunk") or data.get("result", {}).get("audioChunk")
        audio_b64 = (chunk or {}).get("data", "")
        if not audio_b64:
            raise RuntimeError("No audio data in V3 API response: %s" % data)

        yield base64.b64decode(audio_b64)
    
    def synthesize_preview(self, text, access_key, speaker, emotion, api_version='v1', volume=None):
        """Generate audio preview and return base64 encoded data. volume: 0-100% (v3 only)."""
        if api_version == 'v3':
            url = 'https://tts.api.cloud.yandex.net/tts/v3/utteranceSynthesis'
            headers = {
                'Authorization': 'Api-Key ' + access_key,
                'Content-Type': 'application/json',
            }

            hints = [{"voice": speaker}, {"role": emotion}]
            lufs = self._volume_to_lufs(volume)
            if lufs is not None:
                hints.append({"volume": lufs})

            payload = {
                "text": text,
                "outputAudioSpec": {
                    "containerAudio": {
                        "containerAudioType": "MP3"
                    }
                },
                "hints": hints,
                "loudnessNormalizationType": "LUFS"
            }

            resp = requests.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                raise RuntimeError("Invalid response received: code: %d, message: %s" % (resp.status_code, resp.text))

            data = resp.json()
            # API может возвращать data.audioChunk или data.result.audioChunk
            chunk = data.get("audioChunk") or data.get("result", {}).get("audioChunk")
            audio_base64 = (chunk or {}).get("data", "")
            if not audio_base64:
                raise RuntimeError("No audio data in V3 API response: %s" % data)
            return audio_base64
        else:
            # V1 API
            url = 'https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize'
            headers = {
                'Authorization': 'Api-Key ' + access_key,
            }

            data = {
                'text': text,
                'lang': 'ru-RU',
                'emotion': emotion,
                'voice': speaker,
                'format': 'mp3',
            }

            resp = requests.post(url, headers=headers, data=data)
        
        if resp.status_code != 200:
            raise RuntimeError("Invalid response received: code: %d, message: %s" % (resp.status_code, resp.text))
        
        # Return base64 encoded audio
        audio_base64 = base64.b64encode(resp.content).decode('utf-8')
        return audio_base64
    
    def clear_voice_cache(self):
        """Clear all cached voice files for this plugin"""
        cache_dir = os.path.join(getCacheDir(), self.name)
        deleted_count = 0
        
        if os.path.exists(cache_dir):
            # Count and delete all mp3 files
            for root, dirs, files in os.walk(cache_dir):
                for file in files:
                    if file.endswith('.mp3'):
                        try:
                            file_path = os.path.join(root, file)
                            os.remove(file_path)
                            deleted_count += 1
                        except Exception as e:
                            self.logger.error(f"Error deleting {file}: {e}")
            
            self.logger.info(f"Cleared {deleted_count} cached voice files")
        
        return deleted_count

    def _get_level_interval(self, level):
        """
        Find matching level interval from config. Returns dict with skip, emotion, volume
        or None if no interval matches.
        """
        intervals = self.config.get("level_intervals") or []
        if not isinstance(intervals, list):
            return None
        # Narrower intervals first (more specific override)
        for iv in sorted(intervals, key=lambda x: (x.get("max", 10) - x.get("min", 0))):
            if not isinstance(iv, dict):
                continue
            lo, hi = iv.get("min", 0), iv.get("max", 10)
            if lo <= level <= hi:
                return iv
        return None

    def say(self, message, level=0, args=None):
        """
        Synthesize text to speech and play audio.
        args (dict) may contain 'voice' or 'speaker' and 'emotion' to override configured settings.
        level_intervals in config: for each [min,max] set skip, emotion, volume per level range.
        """
        iv = self._get_level_interval(level)
        if iv and iv.get("skip"):
            return

        args = args if isinstance(args, dict) else {}
        if iv:
            if iv.get("emotion"):
                args = dict(args, emotion=iv["emotion"])
            vol = iv.get("volume")
            if vol is not None and "volume" not in args:
                try:
                    args = dict(args, volume=int(vol))
                except (TypeError, ValueError):
                    pass
        speaker = args.get("voice") or args.get("speaker") or self.config.get("speaker", "marina")
        emotion = args.get("emotion") or self.config.get("emotion", "neutral")
        volume = args.get("volume")
        if volume is None:
            volume = self.config.get("default_volume")
        voice_overridden = "voice" in args or "speaker" in args
        emotion_overridden = "emotion" in args
        volume_overridden = volume is not None

        # Ключ кэша: голос, интонация, громкость — при переопределении
        parts = [message, speaker, emotion]
        if volume_overridden:
            parts.append(str(volume))
        if voice_overridden or emotion_overridden or volume_overridden:
            cache_key = hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()
        else:
            cache_key = hashlib.md5(message.encode("utf-8")).hexdigest()
        file_name = cache_key + ".mp3"

        cached_file_name = findInCache(file_name, self.name, True)
        if cached_file_name and os.path.getsize(cached_file_name) == 0:
            try:
                os.remove(cached_file_name)
            except OSError:
                pass
            cached_file_name = None
        if not cached_file_name:
            try:
                audio_content = b"".join(self.synthesize(message, speaker, emotion, volume))
                if not audio_content:
                    self.logger.warning("API returned empty audio for: %s", message[:50])
                else:
                    file_path = getFullFilename(file_name, self.name, True)
                    os.makedirs(os.path.dirname(file_path), exist_ok=True)
                    with open(file_path, "wb") as f:
                        f.write(audio_content)
                    self.logger.debug("Файл успешно сохранен {}.".format(file_path))
            except Exception as e:
                self.logger.exception(f"{type(e).__name__}, {e}")

        cached_file_name = findInCache(file_name, self.name, True)
        if cached_file_name and os.path.getsize(cached_file_name):
            playSound(cached_file_name, level)
