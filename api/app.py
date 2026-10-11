# app.py
import io
import os
import json
import hashlib
import tempfile
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any
from pathlib import Path

import requests
from flask import Flask, request, jsonify, send_file, Response
from werkzeug.exceptions import BadRequest, InternalServerError

app = Flask(__name__)

# -----------------------------
# Config
# -----------------------------
APP_ENV = os.getenv("APP_ENV", "development")
DEBUG = os.getenv("FLASK_DEBUG", "0") == "1"

NUANCE_API_URL = os.getenv("NUANCE_API_URL", "https://example.nuance.com/tts")
NUANCE_API_KEY = os.getenv("NUANCE_API_KEY", "")
NUANCE_APP_ID = os.getenv("NUANCE_APP_ID", "")
NUANCE_VOICE = os.getenv("NUANCE_VOICE", "default")

CACHE_DIR = Path(os.getenv("CACHE_DIR", "/tmp/tts_cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_OUTPUT_FORMAT = os.getenv("DEFAULT_OUTPUT_FORMAT", "wav")

# -----------------------------
# Voice profile model
# -----------------------------
@dataclass
class VoiceProfile:
    pitch: int = 50
    depth: int = 50
    energy: int = 50
    accent: int = 50
    speed: int = 50

    @classmethod
    def from_dict(cls, payload: Optional[Dict[str, Any]] = None):
        data = payload or {}
        return cls(
            pitch=int(data.get("pitch", 50)),
            depth=int(data.get("depth", 50)),
            energy=int(data.get("energy", 50)),
            accent=int(data.get("accent", 50)),
            speed=int(data.get("speed", 50)),
        )

    def clamp(self):
        for key in ("pitch", "depth", "energy", "accent", "speed"):
            value = getattr(self, key)
            setattr(self, key, max(0, min(100, int(value))))

    def to_payload(self) -> Dict[str, int]:
        self.clamp()
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
def normalize_text(text: str) -> str:
    if text is None:
        return ""
    text = text.strip()
    if len(text) == 0:
        raise BadRequest("Text is required.")
    return text

def build_cache_key(text: str, profile: VoiceProfile, output_format: str) -> str:
    data = json.dumps({
        "text": text,
        "profile": profile.to_payload(),
        "format": output_format,
    }, sort_keys=True)
    digest = hashlib.sha256(data.encode("utf-8")).hexdigest()
    return f"{digest}.{output_format}"

def get_cache_file(cache_key: str) -> Optional[Path]:
    file_path = CACHE_DIR / cache_key
    if file_path.exists():
        return file_path
    return None

def save_cache_file(cache_key: str, payload: bytes):
    file_path = CACHE_DIR / cache_key
    with open(file_path, "wb") as f:
        f.write(payload)

# -----------------------------
# Nuance TTS adapter
# -----------------------------
class NuanceTTSClient:
    def __init__(self):
        self.api_url = NUANCE_API_URL
        self.api_key = NUANCE_API_KEY
        self.app_id = NUANCE_APP_ID
        self.voice = NUANCE_VOICE

    def synthesize(self, text: str, profile: VoiceProfile, output_format: str = "wav") -> bytes:
        """
        Replace this with the exact Nuance request format for your environment.

        This example sends a generic JSON request to a Nuance-style TTS endpoint.
        If your Nuance SDK/API differs, only this method should need adjustment.
        """
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
            "profile": profile.to_payload(),
            "app_id": self.app_id,
        }

        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise InternalServerError(f"Nuance TTS request failed: {exc}") from exc

        content_type = response.headers.get("Content-Type", "").lower()

        # If endpoint returns raw audio bytes:
        if "audio" in content_type or output_format in content_type or response.content.startswith(b"RIFF"):
            return response.content

        # If endpoint returns JSON with audio_url or base64:
        try:
            json_data = response.json()
        except ValueError:
            raise InternalServerError("Nuance response was not valid audio or JSON.")

        if "audio_base64" in json_data:
            import base64
            return base64.b64decode(json_data["audio_base64"])

        if "audio_url" in json_data:
            audio_resp = requests.get(json_data["audio_url"], timeout=30)
            audio_resp.raise_for_status()
            return audio_resp.content

        raise InternalServerError("Nuance response did not include audio data.")

nuance_client = NuanceTTSClient()

# -----------------------------
# Routes
# -----------------------------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "app": "miitalkmo-api",
        "version": "1.0.0",
        "env": APP_ENV,
    }), 200

@app.route("/api/voices", methods=["GET"])
def list_voices():
    # Replace with actual supported voices from Nuance or your local config
    return jsonify({
        "voices": [
            {"id": "default", "name": "Default"},
            {"id": "gentle", "name": "Gentle"},
            {"id": "warm", "name": "Warm"},
            {"id": "bright", "name": "Bright"},
        ]
    }), 200

@app.route("/api/tts", methods=["POST"])
def synthesize_tts():
    try:
        data = request.get_json(force=True, silent=False)
    except Exception:
        raise BadRequest("Request body must be valid JSON.")

    text = normalize_text(data.get("text", ""))
    output_format = (data.get("format") or data.get("output_format") or DEFAULT_OUTPUT_FORMAT).lower()
    voice = data.get("voice") or NUANCE_VOICE

    # Profile fields matching your Miitomo-style 5-dot controls:
    profile = VoiceProfile.from_dict(data.get("voice_profile") or data.get("profile"))
    profile.clamp()

    # Optionally allow direct profile override from root-level object
    if "pitch" in data:
        profile.pitch = int(data["pitch"])
    if "depth" in data:
        profile.depth = int(data["depth"])
    if "energy" in data:
        profile.energy = int(data["energy"])
    if "accent" in data:
        profile.accent = int(data["accent"])
    if "speed" in data:
        profile.speed = int(data["speed"])

    # Force valid output format
    if output_format not in ("wav", "mp3", "ogg"):
        output_format = DEFAULT_OUTPUT_FORMAT

    # Use cache
    cache_key = build_cache_key(text, profile, output_format)
    cached_file = get_cache_file(cache_key)
    if cached_file is not None:
        return send_file(
            str(cached_file),
            mimetype=f"audio/{output_format}",
            as_attachment=True,
            download_name=f"tts_{cache_key}.{output_format}",
        )

    # Synthesize
    try:
        audio_bytes = nuance_client.synthesize(text=text, profile=profile, output_format=output_format)
    except Exception as exc:
        raise InternalServerError(f"TTS synthesis failed: {exc}") from exc

    if not audio_bytes:
        raise InternalServerError("No audio data returned by TTS engine.")

    save_cache_file(cache_key, audio_bytes)

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
        raise BadRequest("Request body must be valid JSON.")

    text = normalize_text(data.get("text", ""))
    profile = VoiceProfile.from_dict(data.get("voice_profile") or data.get("profile"))

    voice = data.get("voice") or NUANCE_VOICE
    output_format = (data.get("format") or data.get("output_format") or DEFAULT_OUTPUT_FORMAT).lower()

    try:
        audio_bytes = nuance_client.synthesize(text=text, profile=profile, output_format=output_format)
    except Exception as exc:
        raise InternalServerError(f"TTS synthesis failed: {exc}") from exc

    return jsonify({
        "status": "success",
        "voice": voice,
        "format": output_format,
        "profile": profile.to_payload(),
        "audio_size_bytes": len(audio_bytes),
    }), 200

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def server_error(error):
    return jsonify({"error": "Internal server error"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=DEBUG)
