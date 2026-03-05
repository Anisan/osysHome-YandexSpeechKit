import os
import base64
import requests
from app.configuration import Config
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
        # Handle preview and cache JSON requests
        if request.method == 'POST' and request.is_json:
            data = request.get_json() or {}
            action = data.get('action')

            # Preview voice
            if action == 'preview':
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

            # Cache stats
            elif action == 'cache_stats':
                return jsonify({'success': True, **self.get_voice_cache_stats()})

            # List cache items
            elif action == 'cache_list':
                try:
                    items = self.list_voice_cache()
                    return jsonify({'success': True, 'items': items, **self.get_voice_cache_stats()})
                except Exception as e:
                    self.logger.exception(f"Cache list error: {e}")
                    return jsonify({'success': False, 'error': str(e)}), 500

            # Get single cache file audio (base64)
            elif action == 'cache_get':
                try:
                    filename = (data.get('filename') or '').strip()
                    if not filename:
                        return jsonify({'success': False, 'error': 'Filename is required'}), 400
                    audio_b64 = self.get_cached_audio_base64(filename)
                    if audio_b64 is None:
                        return jsonify({'success': False, 'error': 'File not found'}), 404
                    meta = self.get_cached_audio_meta(filename) or {}
                    return jsonify({'success': True, 'audio': audio_b64, 'text': meta.get("text")})
                except Exception as e:
                    self.logger.exception(f"Cache get error: {e}")
                    return jsonify({'success': False, 'error': str(e)}), 500

            # Add phrase to cache manually
            elif action == 'cache_add':
                try:
                    text = (data.get('text') or '').strip()
                    if not text:
                        return jsonify({'success': False, 'error': 'Text is required'}), 400
                    # Optional: allow overriding voice/emotion/volume in the future
                    self.add_phrase_to_cache(text)
                    stats = self.get_voice_cache_stats()
                    return jsonify({'success': True, **stats})
                except Exception as e:
                    self.logger.exception(f"Cache add error: {e}")
                    return jsonify({'success': False, 'error': str(e)}), 500

            # Delete single cache file
            elif action == 'cache_delete':
                try:
                    filename = (data.get('filename') or '').strip()
                    if not filename:
                        return jsonify({'success': False, 'error': 'Filename is required'}), 400
                    deleted = self.delete_voice_cache_file(filename)
                    stats = self.get_voice_cache_stats()
                    return jsonify({
                        'success': True,
                        'deleted': bool(deleted),
                        **stats,
                    })
                except Exception as e:
                    self.logger.exception(f"Cache delete error: {e}")
                    return jsonify({'success': False, 'error': str(e)}), 500

            # Clear cache
            elif action == 'clear_cache':
                try:
                    deleted_count = self.clear_voice_cache()
                    stats = self.get_voice_cache_stats()
                    return jsonify({
                        'success': True,
                        'count': deleted_count,
                        **stats
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
            "cache_stats": self.get_voice_cache_stats(),
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

        with requests.post(url, headers=headers, data=data, stream=True, timeout=Config.HTTP_REQUEST_TIMEOUT) as resp:
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

        resp = requests.post(url, headers=headers, json=payload, timeout=Config.HTTP_REQUEST_TIMEOUT)
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

            resp = requests.post(url, headers=headers, json=payload, timeout=Config.HTTP_REQUEST_TIMEOUT)
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

            resp = requests.post(url, headers=headers, data=data, timeout=Config.HTTP_REQUEST_TIMEOUT)
        
        if resp.status_code != 200:
            raise RuntimeError("Invalid response received: code: %d, message: %s" % (resp.status_code, resp.text))
        
        # Return base64 encoded audio
        audio_base64 = base64.b64encode(resp.content).decode('utf-8')
        return audio_base64
    
    def get_voice_cache_stats(self):
        """Return count and total size of all files in module cache (recursive)."""
        cache_dir = os.path.join(getCacheDir(), self.name)
        count = 0
        total = 0
        if os.path.exists(cache_dir):
            for root, dirs, files in os.walk(cache_dir):
                for f in files:
                    try:
                        path = os.path.join(root, f)
                        total += os.path.getsize(path)
                        count += 1
                    except OSError:
                        pass
        size_human = "0 B"
        if total > 0:
            for unit in ('B', 'KB', 'MB', 'GB'):
                if total < 1024:
                    size_human = f"{total:.1f} {unit}" if unit != 'B' else f"{total} B"
                    break
                total /= 1024
            else:
                size_human = f"{total:.1f} TB"
        return {"count": count, "size_human": size_human}

    def list_voice_cache(self):
        """
        Return detailed list of cached files for this module.
        Items are sorted by modification time (newest first).
        """
        cache_dir = os.path.join(getCacheDir(), self.name)
        items = []
        if not os.path.exists(cache_dir):
            return items

        for root, dirs, files in os.walk(cache_dir):
            for f in files:
                if not f.lower().endswith(".mp3"):
                    continue
                try:
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, cache_dir)
                    stat = os.stat(full_path)
                    meta = self._read_cache_meta_for_audio_file(full_path)
                    items.append({
                        "filename": rel_path.replace("\\", "/"),
                        "size": stat.st_size,
                        "mtime": int(stat.st_mtime),
                        "text": (meta or {}).get("text"),
                    })
                except OSError:
                    continue

        # newest first
        items.sort(key=lambda x: x.get("mtime", 0), reverse=True)
        return items

    def _get_cache_index_path(self, cache_dir: str) -> str:
        return os.path.join(cache_dir, "index.json")

    def _load_cache_index(self, cache_dir: str):
        """
        Load shared index.json with metadata for cached files.
        Returns dict[rel_path] -> meta.
        """
        index_path = self._get_cache_index_path(cache_dir)
        if not os.path.exists(index_path):
            return {}
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return {}
            # Normalize windows separators in keys (backward compatible)
            normalized = {}
            changed = False
            for k, v in data.items():
                nk = k.replace("\\", "/") if isinstance(k, str) else k
                if nk != k:
                    changed = True
                normalized[nk] = v
            if changed:
                # best-effort: persist normalized index
                try:
                    self._save_cache_index(cache_dir, normalized)
                except Exception:
                    pass
            return normalized
        except Exception:
            return {}

    def _save_cache_index(self, cache_dir: str, index: dict):
        """
        Save shared index.json. Best-effort.
        """
        try:
            os.makedirs(cache_dir, exist_ok=True)
            index_path = self._get_cache_index_path(cache_dir)
            with open(index_path, "w", encoding="utf-8") as f:
                json.dump(index, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _get_cache_index_key_for_audio_path(self, audio_path: str):
        cache_root = os.path.join(getCacheDir(), self.name)
        try:
            return os.path.relpath(audio_path, cache_root).replace("\\", "/")
        except Exception:
            return None

    def _has_cache_index_entry_for_file(self, audio_path: str) -> bool:
        cache_root = os.path.join(getCacheDir(), self.name)
        key = self._get_cache_index_key_for_audio_path(audio_path)
        if not key:
            return False
        index = self._load_cache_index(cache_root)
        return isinstance(index.get(key), dict)

    def _update_cache_index_for_file(self, audio_path: str, meta: dict):
        """
        Update index.json entry for given audio file (by relative path under cache dir).
        """
        if not isinstance(meta, dict):
            return
        cache_root = os.path.join(getCacheDir(), self.name)
        key = self._get_cache_index_key_for_audio_path(audio_path)
        if not key:
            return
        index = self._load_cache_index(cache_root)
        index[key] = meta
        self._save_cache_index(cache_root, index)

    def _delete_cache_index_for_file(self, audio_path: str):
        """
        Remove entry from index.json for given audio file.
        """
        cache_root = os.path.join(getCacheDir(), self.name)
        key = self._get_cache_index_key_for_audio_path(audio_path)
        if not key:
            return
        index = self._load_cache_index(cache_root)
        if key in index:
            index.pop(key, None)
            self._save_cache_index(cache_root, index)

    def _read_cache_meta_for_audio_file(self, audio_path: str):
        """
        Read metadata for an audio file.
        Возвращает dict или None (если записи в index.json нет).
        """
        cache_root = os.path.join(getCacheDir(), self.name)
        try:
            rel = os.path.relpath(audio_path, cache_root).replace("\\", "/")
            index = self._load_cache_index(cache_root)
            data = index.get(rel)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return None

    def clear_voice_cache(self):
        """Clear all cached files for this module (recursive)."""
        cache_dir = os.path.join(getCacheDir(), self.name)
        deleted_count = 0
        if os.path.exists(cache_dir):
            for root, dirs, files in os.walk(cache_dir, topdown=False):
                for f in files:
                    try:
                        os.remove(os.path.join(root, f))
                        deleted_count += 1
                    except Exception as e:
                        self.logger.error(f"Error deleting {f}: {e}")
                for d in dirs:
                    try:
                        os.rmdir(os.path.join(root, d))
                    except OSError:
                        pass
            self.logger.info(f"Cleared {deleted_count} cached files")
        return deleted_count

    def _get_cache_file_path(self, filename: str):
        """
        Resolve a cache filename safely inside this module cache directory.
        Returns absolute path or None if path is invalid or outside cache dir.
        """
        if not filename:
            return None
        cache_dir = os.path.join(getCacheDir(), self.name)
        # Normalise and prevent directory traversal
        safe_name = os.path.normpath(filename).lstrip("\\/")  # remove leading separators
        full_path = os.path.normpath(os.path.join(cache_dir, safe_name))
        if not full_path.startswith(os.path.normpath(cache_dir)):
            return None
        if not os.path.exists(full_path) or not os.path.isfile(full_path):
            return None
        return full_path

    def get_cached_audio_meta(self, filename: str):
        """
        Get metadata for cached audio by its relative filename (mp3).
        Returns dict or None.
        """
        audio_path = self._get_cache_file_path(filename)
        if not audio_path:
            return None
        return self._read_cache_meta_for_audio_file(audio_path)

    def get_cached_audio_base64(self, filename: str):
        """
        Read cached audio file and return base64-encoded content.
        Returns None if file does not exist.
        """
        full_path = self._get_cache_file_path(filename)
        if not full_path:
            return None
        with open(full_path, "rb") as f:
            data = f.read()
        if not data:
            return None
        return base64.b64encode(data).decode("utf-8")

    def delete_voice_cache_file(self, filename: str) -> bool:
        """
        Delete single cached file. Returns True if file was deleted.
        """
        full_path = self._get_cache_file_path(filename)
        if not full_path:
            return False
        try:
            os.remove(full_path)
            # удалить запись из общего индекса
            self._delete_cache_index_for_file(full_path)
            return True
        except OSError as e:
            self.logger.error("Failed to delete cache file %s: %s", filename, e)
            return False

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
        # Если файл уже есть в кэше, но записи в index.json нет — добавим её
        if cached_file_name and os.path.getsize(cached_file_name):
            try:
                if not self._has_cache_index_entry_for_file(cached_file_name):
                    meta = {
                        "text": message,
                        "speaker": speaker,
                        "emotion": emotion,
                        "volume": volume,
                    }
                    self._update_cache_index_for_file(cached_file_name, meta)
            except Exception:
                pass
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
                    # Обновляем общий индекс метаданных (best-effort)
                    try:
                        meta = {
                            "text": message,
                            "speaker": speaker,
                            "emotion": emotion,
                            "volume": volume,
                        }
                        self._update_cache_index_for_file(file_path, meta)
                    except Exception:
                        pass
                    self.logger.debug("Файл успешно сохранен {}.".format(file_path))
            except Exception as e:
                self.logger.exception(f"{type(e).__name__}, {e}")

        cached_file_name = findInCache(file_name, self.name, True)
        if cached_file_name and os.path.getsize(cached_file_name):
            playSound(cached_file_name, level)

    def add_phrase_to_cache(self, message: str, args: dict | None = None):
        """
        Synthesize text to speech and save to cache without playback.
        Uses same cache key logic as say().
        """
        args = args if isinstance(args, dict) else {}
        speaker = args.get("voice") or args.get("speaker") or self.config.get("speaker", "marina")
        emotion = args.get("emotion") or self.config.get("emotion", "neutral")
        volume = args.get("volume")
        if volume is None:
            volume = self.config.get("default_volume")

        voice_overridden = "voice" in args or "speaker" in args
        emotion_overridden = "emotion" in args
        volume_overridden = volume is not None

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
        # Если файл уже есть в кэше, но записи в index.json нет — добавим её
        if cached_file_name and os.path.getsize(cached_file_name):
            try:
                if not self._has_cache_index_entry_for_file(cached_file_name):
                    meta = {
                        "text": message,
                        "speaker": speaker,
                        "emotion": emotion,
                        "volume": volume,
                    }
                    self._update_cache_index_for_file(cached_file_name, meta)
            except Exception:
                pass
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
                    try:
                        meta = {
                            "text": message,
                            "speaker": speaker,
                            "emotion": emotion,
                            "volume": volume,
                        }
                        self._update_cache_index_for_file(file_path, meta)
                    except Exception:
                        pass
                    self.logger.debug("Фраза добавлена в кэш {}.".format(file_path))
            except Exception as e:
                self.logger.exception(f"{type(e).__name__}, {e}")
