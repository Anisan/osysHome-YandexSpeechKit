import os
import base64
import requests
import hashlib
import shutil
import json
from flask import jsonify, request as flask_request
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
                    
                    if not access_key:
                        return jsonify({'success': False, 'error': 'Access key is required'}), 400
                    
                    # Generate preview audio
                    preview_text = "Привет! Это пример голоса."
                    audio_data = self.synthesize_preview(preview_text, access_key, speaker, emotion, api_version)
                    
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
        else:
            if settings.validate_on_submit():
                self.config["access_key"] = settings.access_key.data
                self.config["api_version"] = settings.api_version.data
                self.config["speaker"] = settings.speaker.data
                self.config["emotion"] = settings.emotion.data
                self.saveConfig()
        content = {
            "form": settings,
            "v1_voices": V1_VOICES,
            "voice_emotions": VOICE_EMOTIONS,
        }
        return self.render('main_ysk.html', content)

    def synthesize(self, text, speaker=None, emotion=None):
        """Synthesize text to speech using configured API version and optional voice override"""
        api_version = self.config.get("api_version", "v1")
        speaker = speaker or self.config.get("speaker", "marina")
        emotion = emotion or self.config.get("emotion", "neutral")

        if api_version == "v3":
            return self.synthesize_v3(text, speaker, emotion)
        else:
            return self.synthesize_v1(text, speaker, emotion)
    
    def synthesize_v1(self, text, speaker=None, emotion=None):
        """Synthesize using API v1"""
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
    
    def synthesize_v3(self, text, speaker=None, emotion=None):
        """Synthesize using API v3 (https://yandex.cloud/ru/docs/speechkit/tts-v3/api-ref/Synthesizer/utteranceSynthesis)"""
        speaker = speaker or self.config.get("speaker", "marina")
        emotion = emotion or self.config.get("emotion", "neutral")
        url = 'https://tts.api.cloud.yandex.net/tts/v3/utteranceSynthesis'
        headers = {
            'Authorization': 'Api-Key ' + self.config["access_key"],
            'Content-Type': 'application/json',
        }

        # Каждый hint содержит только одно поле: voice, role, speed и т.д.
        hints = [{"voice": speaker}, {"role": emotion}]

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
    
    def synthesize_preview(self, text, access_key, speaker, emotion, api_version='v1'):
        """Generate audio preview and return base64 encoded data"""
        if api_version == 'v3':
            url = 'https://tts.api.cloud.yandex.net/tts/v3/utteranceSynthesis'
            headers = {
                'Authorization': 'Api-Key ' + access_key,
                'Content-Type': 'application/json',
            }

            # Каждый hint содержит только одно поле
            hints = [{"voice": speaker}, {"role": emotion}]

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

    def say(self, message, level=0, args=None):
        """
        Synthesize text to speech and play audio.
        args (dict) may contain 'voice' or 'speaker' and 'emotion' to override configured settings.
        """
        args = args if isinstance(args, dict) else {}
        speaker = args.get("voice") or args.get("speaker") or self.config.get("speaker", "marina")
        emotion = args.get("emotion") or self.config.get("emotion", "neutral")
        voice_overridden = "voice" in args or "speaker" in args
        emotion_overridden = "emotion" in args

        # Ключ кэша с голосом/интонацией только при переопределении
        if voice_overridden or emotion_overridden:
            cache_key = hashlib.md5(
                (message + "|" + speaker + "|" + emotion).encode("utf-8")
            ).hexdigest()
        else:
            cache_key = hashlib.md5(message.encode("utf-8")).hexdigest()
        file_name = cache_key + ".mp3"

        cached_file_name = findInCache(file_name, self.name, True)
        if not cached_file_name or os.path.getsize(cached_file_name) == 0:
            try:
                file_path = getFullFilename(file_name, self.name, True)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, "wb") as f:
                    for audio_content in self.synthesize(message, speaker, emotion):
                        f.write(audio_content)
                self.logger.debug("Файл успешно сохранен {}.".format(file_path))
            except Exception as e:
                self.logger.exception(f"{type(e).__name__}, {e}")

        cached_file_name = findInCache(file_name, self.name, True)
        if cached_file_name and os.path.getsize(cached_file_name):
            playSound(cached_file_name, level, args)
