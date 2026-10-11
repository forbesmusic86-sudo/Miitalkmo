import io
import os
import json
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional

import requests
from flask import Flask, request, jsonify, send_file

app = Flask(__name__)

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
# VoiceProfile
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
def normalize_text(value):
    if value is None:
        value = ""
    text = str(value).strip()
    if not text:
        raise ValueError("Text is required.")
    return text

def build_cache_key(text: str, profile: VoiceProfile, output_format: str) -> str:
    payload = {
        "text": text,
        "profile": profile.to_dict(),
        "format": output_format,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return f"{digest}.{output_format}"

def get_cached_audio(cache_key: str):
    path = CACHE_DIR / cache_key
    if path.exists():
        return path.read_bytes()
    return None

def save_cached_audio(cache_key: str, data: bytes):
    path = CACHE_DIR / cache_key
    path.write_bytes(data)

# -----------------------------
# Nuance client
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

        # Raw audio response
        if "audio" in content_type or output_format in content_type or response.content.startswith(b"RIFF"):
            return response.content

        # JSON response
        try:
            json_data = response.json()
        except ValueError as exc:
            raise RuntimeError("Nuance response was not valid audio or JSON.") from exc

        if "audio_base64" in json_data:
            import base64
            return base64.b64decode(json_data["audio_base64"])

        if "audio_url" in json_data:
            audio_resp = requests.get(json_data["audio_url"], timeout=30)
            audio_resp.raise_for_status()
            return audio_resp.content

        raise RuntimeError("Nuance response did not include audio data.")

nuance_client = NuanceTTSClient()

# -----------------------------
# Routes
# -----------------------------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "service": "miitalkmo",
    })

@app.route("/api/voices", methods=["GET"])
def list_voices():
    return jsonify({
        "voices": [
            {"id": "default", "name": "Default"},
            {"id": "gentle", "name": "Gentle"},
            {"id": "warm", "name": "Warm"},
            {"id": "bright", "name": "Bright"},
        ]
    })

@app.route("/api/tts", methods=["POST"])
def synthesize_tts():
    try:
        data = request.get_json(force=True, silent=False)
    except Exception:
        raise ValueError("Request body must be valid JSON.")

    text = normalize_text(data.get("text", ""))

    output_format = (data.get("format") or data.get("output_format") or DEFAULT_OUTPUT_FORMAT).lower()
    if output_format not in ("wav", "mp3", "ogg"):
        output_format = DEFAULT_OUTPUT_FORMAT

    voice = data.get("voice") or NUANCE_VOICE

    profile = VoiceProfile.from_dict(data.get("voice_profile") or data.get("profile"))
    if "pitch" in data:
        profile.pitch = profile._clamp(data["pitch"])
    if "depth" in data:
        profile.depth = profile._clamp(data["depth"])
    if "energy" in data:
        profile.energy = profile._clamp(data["energy"])
    if "accent" in data:
        profile.accent = profile._clamp(data["accent"])
    if "speed" in data:
        profile.speed = profile._clamp(data["speed"])

    cache_key = build_cache_key(text, profile, output_format)
    cached_audio = get_cached_audio(cache_key)
    if cached_audio is not None:
        return send_file(
            io.BytesIO(cached_audio),
            mimetype=f"audio/{output_format}",
            as_attachment=True,
            download_name=f"tts_output.{output_format}",
        )

    try:
        audio_bytes = nuance_client.synthesize(text, profile, output_format)
    except Exception as exc:
        raise RuntimeError(f"TTS synthesis failed: {exc}")

    if not audio_bytes:
        raise RuntimeError("No audio data returned by Nuance.")

    save_cached_audio(cache_key, audio_bytes)

    return send_file(
        io.BytesIO(audio_bytes),
        mimetype=f"audio/{output_format}",
        as_attachment=True,
        download_name=f"tts_output.{output_format}",
    )

@app.route("/api/tts-json", methods=["POST"])
def synthesize_tts_json():
    try:
        data = request.get_json(force=True, silent=False)
    except Exception:
        raise ValueError("Request body must be valid JSON.")

    text = normalize_text(data.get("text", ""))
    profile = VoiceProfile.from_dict(data.get("voice_profile") or data.get("profile"))
    output_format = (data.get("format") or data.get("output_format") or DEFAULT_OUTPUT_FORMAT).lower()

    try:
        audio_bytes = nuance_client.synthesize(text, profile, output_format)
    except Exception as exc:
        raise RuntimeError(f"TTS synthesis failed: {exc}")

    return jsonify({
        "status": "success",
        "voice": data.get("voice") or NUANCE_VOICE,
        "format": output_format,
        "profile": profile.to_dict(),
        "audio_size_bytes": len(audio_bytes),
    })

@app.errorhandler(400)
def bad_request(error):
    return jsonify({"error": "Bad request"}), 400

@app.errorhandler(500)
def server_error(error):
    return jsonify({"error": "Internal server error"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
