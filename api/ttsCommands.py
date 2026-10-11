# ttsCommands.py
"""
Miitalkmo TTS Commands
Command-layer wrapper for TTS synthesis and voice profile handling.

This module is designed to be used by:
- Flask API routes
- CLI scripts
- background jobs
- app logic
"""

import os
import json
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Import the main TTS engine
try:
    from tts import get_tts_engine, VoiceParams
except ImportError:
    logger.warning("Could not import tts module. Using fallback stub.")

    class VoiceParams:
        def __init__(self, pitch=50, depth=50, energy=50, accent=50, speed=50):
            self.pitch = int(pitch)
            self.depth = int(depth)
            self.energy = int(energy)
            self.accent = int(accent)
            self.speed = int(speed)

        @classmethod
        def from_dict(cls, data=None):
            data = data or {}
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

    def get_tts_engine():
        return None


# -------------------------------------------------
# Commands
# -------------------------------------------------
class TTSCommandError(Exception):
    """Raised when a TTS command fails."""
    pass


def parse_voice_profile(data: Optional[Dict[str, Any]] = None) -> VoiceParams:
    """Convert incoming profile data to VoiceParams."""
    if data is None:
        data = {}

    if not isinstance(data, dict):
        raise TTSCommandError("Voice profile must be a dictionary.")

    return VoiceParams.from_dict(data)


def synthesize_text(
    text: str,
    pitch: int = 50,
    depth: int = 50,
    energy: int = 50,
    accent: int = 50,
    speed: int = 50,
    output_format: str = "wav",
    use_cache: bool = True,
) -> bytes:
    """
    Synthesize text using the 5 parameter voice system.

    The five values correspond to:
      - pitch
      - depth
      - energy
      - accent
      - speed
    """
    if not text or not str(text).strip():
        raise TTSCommandError("Text cannot be empty.")

    params = VoiceParams(
        pitch=pitch,
        depth=depth,
        energy=energy,
        accent=accent,
        speed=speed
    )

    engine = get_tts_engine()
    if engine is None:
        raise TTSCommandError("TTS engine is not available.")

    return engine.synthesize(
        text=str(text).strip(),
        voice_params=params.to_dict(),
        output_format=output_format,
        use_cache=use_cache,
    )


def synthesize_from_profile(
    text: str,
    profile: Optional[Dict[str, Any]] = None,
    output_format: str = "wav",
    use_cache: bool = True,
) -> bytes:
    """Synthesize text from a full voice profile object."""
    profile_data = parse_voice_profile(profile)
    return synthesize_text(
        text=text,
        pitch=profile_data.pitch,
        depth=profile_data.depth,
        energy=profile_data.energy,
        accent=profile_data.accent,
        speed=profile_data.speed,
        output_format=output_format,
        use_cache=use_cache,
    )


def get_voice_profile_defaults() -> Dict[str, int]:
    """Return default voice settings."""
    return {
        "pitch": 50,
        "depth": 50,
        "energy": 50,
        "accent": 50,
        "speed": 50,
    }


def set_voice_profile(
    pitch: Optional[int] = None,
    depth: Optional[int] = None,
    energy: Optional[int] = None,
    accent: Optional[int] = None,
    speed: Optional[int] = None,
) -> Dict[str, int]:
    """Validate and return a voice profile object."""
    defaults = get_voice_profile_defaults()

    if pitch is not None:
        defaults["pitch"] = int(pitch)
    if depth is not None:
        defaults["depth"] = int(depth)
    if energy is not None:
        defaults["energy"] = int(energy)
    if accent is not None:
        defaults["accent"] = int(accent)
    if speed is not None:
        defaults["speed"] = int(speed)

    # clamp
    for key in defaults:
        if defaults[key] < 0:
            defaults[key] = 0
        if defaults[key] > 100:
            defaults[key] = 100

    return defaults


# -------------------------------------------------
# CLI-style helpers
# -------------------------------------------------
def preview_voice_profile(profile: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
    """Return parsed and normalized profile."""
    return parse_voice_profile(profile).to_dict()


def generate_voice_summary(profile: Optional[Dict[str, Any]] = None) -> str:
    """Return a human-readable summary of the voice profile."""
    data = preview_voice_profile(profile)
    return (
        f"Pitch={data['pitch']}, "
        f"Depth={data['depth']}, "
        f"Energy={data['energy']}, "
        f"Accent={data['accent']}, "
        f"Speed={data['speed']}"
    )


# -------------------------------------------------
# Example usage
# -------------------------------------------------
if __name__ == "__main__":
    try:
        result = synthesize_text(
            "Hello! This is Miitalkmo.",
            pitch=60,
            depth=55,
            energy=70,
            accent=50,
            speed=45,
            output_format="wav",
        )

        print(f"Generated TTS output ({len(result)} bytes).")
    except Exception as exc:
        print(f"TTS command failed: {exc}")
