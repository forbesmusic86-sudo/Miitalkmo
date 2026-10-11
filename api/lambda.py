import io
import json
import os
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional

import requests

# -----------------------------
# Config
# -----------------------------
NUANCE_API_URL = os.getenv("NUANCE_API_URL", "https://example.nuance.com/tts")
NUANCE_API_KEY = os.getenv("NUANCE_API_KEY", "")
NUANCE_APP_ID = os.getenv("NUANCE_APP_ID", "")
NUANCE_VOICE = os.getenv("NUANCE_VOICE", "default")
CACHE_DIR = Path(os.getenv("CACHE_DIR", "/tmp/tts_cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_OUTPUT_FORMAT = os.getenv("DEFAULT_OUTPUT_FORMAT", "wav")

# -----------------------------
# Voice profile
# -----------------------------
class VoiceProfile:
    def __init__(self, pitch=50, depth=50, energy=50, accent=50, speed=50):
        self.pitch = self._clamp(pitch)
        self.depth = self._clamp(depth)
        self.energy = self._clamp(energy)
        self.accent = self._clamp(accent)
        self.speed = self._clamp(speed)

    @staticmethod
    def _clamp(value):
        try:
            value = int(value)
        except (TypeError, ValueError):
            value = 50
        return max(0, min(100, value))

    @classmethod
    def from_dict(cls, payload: Optional[Dict[str, Any]] = None):
        data = payload or {}
        return cls(
            pitch=data.get("pitch", 50),
            depth=data.get("depth", 50),
            energy=data.get("energy", 50),
            accent=data.get("accent", 50),
            speed=data.get("speed", 50),
        )

    def to_dict(self):
        return {
            "pitch": self.pitch,
            "depth": self.depth,
            "energy": self.energy,
            "accent": self.accent,
            "speed": self.speed,
        }

# -----------------------------
# Helpers
# -----------------------------
def json_response(body, status=200):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        },
        "body": json.dumps(body),
    }

def audio_response(audio_bytes: bytes, output_format: str = "wav", filename: str = "tts_output.wav"):
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": f"audio/{output_format}",
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        },
        "body": audio_bytes.decode("latin1") if False else __binary_body(audio_bytes),
        "isBase64Encoded": True,
    }

def __binary_body(data: bytes) -> str:
    import base64
    return base64.b64encode(data).decode("utf-8")

def normalize_text(value):
    if value is None:
        text = ""
    else:
        text = str(value).strip()
    if not text:
        raise ValueError("Text is required.")
    return text

def build_cache_key(text: str, profile: VoiceProfile, output_format: str) -> str:
    data = json.dumps({
        "text": text,
        "profile": profile.to_dict(),
        "format": output_format,
    }, sort_keys=True)
    digest = hashlib.sha256(data.encode("utf-8")).hexdigest()
    return f"{digest}.{output_format}"

def get_cached_audio(cache_key: str):
    file_path = CACHE_DIR / cache_key
    if file_path.exists():
        return file_path.read_bytes()
    return None

def save_cached_audio(cache_key: str, data: bytes):
    file_path = CACHE_DIR / cache_key
    file_path.write_bytes(data)

# -----------------------------
# Nuance adapter
# -----------------------------
class NuanceTTSClient:
    def __init__(self):
        self.api_url = NUANCE_API_URL
        self.api_key = NUANCE_API_KEY
        self.app_id = NUANCE_APP_ID
        self.voice = NUANCE_VOICE

    def synthesize(self, text: str, profile: VoiceProfile, output_format: str = "wav") -> bytes:
        headers = {
            "Content-Type": "application/json",
            "Accept": output_format,
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "text": text,
            "voice": self.voice,
            "output_format": output_format,
            "profile": profile.to_dict(),
            "app_id": self.app_id,
        }

        try:
            response = requests.post(self.api_url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"Nuance TTS request failed: {exc}") from exc

        content_type = response.headers.get("Content-Type", "").lower()

        if "audio" in content_type or output_format in content_type or response.content.startswith(b"RIFF"):
            return response.content

        try:
            payload_json = response.json()
        except ValueError as exc:
            raise RuntimeError("Nuance response was not valid audio or JSON.") from exc

        if "audio_base64" in payload_json:
            import base64
            return base64.b64decode(payload_json["audio_base64"])

        if "audio_url" in payload_json:
            audio_resp = requests.get(payload_json["audio_url"], timeout=30)
            audio_resp.raise_for_status()
            return audio_resp.content

        raise RuntimeError("Nuance response did not include audio data.")

nuance_client = NuanceTTSClient()

# -----------------------------
# Lambda handler
# -----------------------------
def handler(event, context):
    try:
        method = (event.get("httpMethod") or "GET").upper()
        path = (event.get("path") or "").lower()

        # CORS preflight
        if method == "OPTIONS":
            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                },
                "body": "",
            }

        if path in ("/health", "/api/health"):
            return json_response({"status": "ok", "service": "miitalkmo-lambda"})

        if path in ("/api/tts", "/tts"):
            body = event.get("body") or "{}"
            if isinstance(body, str):
                body = json.loads(body)
            if not isinstance(body, dict):
                return json_response({"error": "Request body must be a JSON object."}, 400)

            text = normalize_text(body.get("text", ""))
            output_format = (body.get("format") or body.get("output_format") or DEFAULT_OUTPUT_FORMAT).lower()
            voice = body.get("voice") or NUANCE_VOICE

            profile = VoiceProfile.from_dict(body.get("voice_profile") or body.get("profile"))
            if "pitch" in body:
                profile.pitch = profile._clamp(body["pitch"])
            if "depth" in body:
                profile.depth = profile._clamp(body["depth"])
            if "energy" in body:
                profile.energy = profile._clamp(body["energy"])
            if "accent" in body:
                profile.accent = profile._clamp(body["accent"])
            if "speed" in body:
                profile.speed = profile._clamp(body["speed"])

            if output_format not in ("wav", "mp3", "ogg"):
                output_format = DEFAULT_OUTPUT_FORMAT

            cache_key = build_cache_key(text, profile, output_format)
            cached_audio = get_cached_audio(cache_key)
            if cached_audio is not None:
                return audio_response(cached_audio, output_format, f"tts_{cache_key}.{output_format}")

            try:
                audio_bytes = nuance_client.synthesize(text, profile, output_format)
            except Exception as exc:
                return json_response({"error": f"TTS synthesis failed: {exc}"}, 500)

            if not audio_bytes:
                return json_response({"error": "No audio returned by Nuance."}, 500)

            save_cached_audio(cache_key, audio_bytes)
            return audio_response(audio_bytes, output_format, f"tts_output.{output_format}")

        if path in ("/api/voices", "/voices"):
            return json_response({
                "voices": [
                    {"id": "default", "name": "Default"},
                    {"id": "warm", "name": "Warm"},
                    {"id": "bright", "name": "Bright"},
                    {"id": "gentle", "name": "Gentle"},
                ]
            })

        return json_response({"error": "Not found"}, 404)

    except ValueError as exc:
        return json_response({"error": str(exc)}, 400)
    except Exception as exc:
        return json_response({"error": str(exc)}, 500)

# For local testing
if __name__ == "__main__":
    import sys
    print("Miitalkmo Lambda handler loaded.")
    print("Run this with a local event or use SAM/localstack.")
