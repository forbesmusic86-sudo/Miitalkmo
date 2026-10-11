# tts.py
"""
Miitalkmo TTS Module
Handles Nuance Vocalizer synthesis for text-to-speech conversion.
Replaces Citra emulator approach with direct SDK integration.
"""

import os
import io
import json
import logging
import struct
from typing import Optional, Dict, Tuple, Any
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to import Nuance SDK (adjust based on your actual SDK)
try:
    from nuance.tts import VocalizerEngine, VocalizerVoice, VocalizerAudioSettings
except ImportError:
    logger.warning("Nuance SDK not found. Using mock TTS for testing.")
    VocalizerEngine = None

# Try to import audio libraries
try:
    import wave
except ImportError:
    wave = None

try:
    from pydub import AudioSegment
except ImportError:
    AudioSegment = None

# =====================================================
# Configuration
# =====================================================
NUANCE_VOICE = os.getenv("NUANCE_VOICE", "default")
NUANCE_SAMPLE_RATE = int(os.getenv("NUANCE_SAMPLE_RATE", "16000"))
NUANCE_CHANNELS = int(os.getenv("NUANCE_CHANNELS", "1"))
TTS_OUTPUT_FORMAT = os.getenv("TTS_OUTPUT_FORMAT", "wav").lower()
TTS_CACHE_DIR = Path(os.getenv("TTS_CACHE_DIR", "/tmp/tts_cache"))
TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# =====================================================
# Voice Profile
# =====================================================
@dataclass
class VoiceParams:
    """Voice parameters matching Miitomo's 5-point system."""
    pitch: int = 50
    depth: int = 50
    energy: int = 50
    accent: int = 50
    speed: int = 50

    @staticmethod
    def _clamp(value: int, min_val: int = 0, max_val: int = 100) -> int:
        try:
            value = int(value)
        except (TypeError, ValueError):
            value = 50
        return max(min_val, min(max_val, value))

    def __post_init__(self):
        self.pitch = self._clamp(self.pitch)
        self.depth = self._clamp(self.depth)
        self.energy = self._clamp(self.energy)
        self.accent = self._clamp(self.accent)
        self.speed = self._clamp(self.speed)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]] = None):
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

    def to_nuance_params(self) -> Dict[str, int]:
        """Map Miitomo 5-dot params to Nuance engine settings."""
        return {
            "pitch": int(self.pitch * 1.5),  # Scale 0-100 to typical pitch range
            "rate": int(self.speed * 1.5),   # Speech rate
            "volume": int(self.energy * 0.8),  # Volume/loudness
        }

# =====================================================
# Nuance TTS Engine Wrapper
# =====================================================
class TTSEngine:
    """Wrapper around Nuance Vocalizer for text-to-speech synthesis."""

    def __init__(self):
        self.engine = None
        self.current_voice = None
        self.sample_rate = NUANCE_SAMPLE_RATE
        self.channels = NUANCE_CHANNELS
        self._init_engine()

    def _init_engine(self):
        """Initialize Nuance Vocalizer engine."""
        if VocalizerEngine is None:
            logger.warning("Nuance SDK not available. Using mock synthesis.")
            return

        try:
            self.engine = VocalizerEngine()
            logger.info("Nuance Vocalizer engine initialized.")
        except Exception as exc:
            logger.error(f"Failed to initialize Nuance engine: {exc}")
            self.engine = None

    def load_voice(self, voice_name: str = "default"):
        """Load a specific voice."""
        if self.engine is None:
            logger.warning("Engine not initialized. Skipping voice load.")
            return False

        try:
            voice = VocalizerVoice(voice_name)
            self.engine.load_voice(voice)
            self.current_voice = voice_name
            logger.info(f"Loaded voice: {voice_name}")
            return True
        except Exception as exc:
            logger.error(f"Failed to load voice {voice_name}: {exc}")
            return False

    def synthesize(
        self,
        text: str,
        params: VoiceParams,
        output_format: str = "wav",
    ) -> bytes:
        """
        Synthesize text to audio.
        
        Args:
            text: Text to speak
            params: VoiceParams object with pitch, speed, etc.
            output_format: Output format (wav, mp3, ogg)
            
        Returns:
            Audio data as bytes
        """
        if not text:
            raise ValueError("Text is required for synthesis.")

        if self.engine is None:
            logger.warning("Engine not initialized. Returning mock audio.")
            return self._generate_mock_audio(text, params)

        try:
            # Apply voice parameters
            nuance_params = params.to_nuance_params()
            self.engine.set_pitch(nuance_params["pitch"])
            self.engine.set_rate(nuance_params["rate"])
            self.engine.set_volume(nuance_params["volume"])

            # Synthesize
            audio_data = self.engine.synthesize(text)

            if output_format == "wav":
                return self._wrap_as_wav(audio_data)
            elif output_format == "mp3":
                return self._convert_to_mp3(audio_data)
            elif output_format == "ogg":
                return self._convert_to_ogg(audio_data)
            else:
                logger.warning(f"Unknown format {output_format}. Returning WAV.")
                return self._wrap_as_wav(audio_data)

        except Exception as exc:
            logger.error(f"Synthesis failed: {exc}")
            raise

    def _wrap_as_wav(self, audio_data: bytes) -> bytes:
        """Wrap raw audio data in WAV container."""
        if wave is None:
            logger.warning("wave module not available. Returning raw audio.")
            return audio_data

        try:
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as wav_file:
                wav_file.setnchannels(self.channels)
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(self.sample_rate)
                wav_file.writeframes(audio_data)
            return buffer.getvalue()
        except Exception as exc:
            logger.error(f"Failed to wrap WAV: {exc}")
            return audio_data

    def _convert_to_mp3(self, audio_data: bytes) -> bytes:
        """Convert audio to MP3."""
        if AudioSegment is None:
            logger.warning("pydub not available. Returning WAV instead.")
            return self._wrap_as_wav(audio_data)

        try:
            # Create AudioSegment from raw data
            sound = AudioSegment(
                audio_data,
                frame_rate=self.sample_rate,
                sample_width=2,  # 16-bit
                channels=self.channels,
            )
            buffer = io.BytesIO()
            sound.export(buffer, format="mp3", bitrate="128k")
            return buffer.getvalue()
        except Exception as exc:
            logger.error(f"Failed to convert to MP3: {exc}")
            return self._wrap_as_wav(audio_data)

    def _convert_to_ogg(self, audio_data: bytes) -> bytes:
        """Convert audio to OGG."""
        if AudioSegment is None:
            logger.warning("pydub not available. Returning WAV instead.")
            return self._wrap_as_wav(audio_data)

        try:
            sound = AudioSegment(
                audio_data,
                frame_rate=self.sample_rate,
                sample_width=2,
                channels=self.channels,
            )
            buffer = io.BytesIO()
            sound.export(buffer, format="ogg", codec="libvorbis", bitrate="128k")
            return buffer.getvalue()
        except Exception as exc:
            logger.error(f"Failed to convert to OGG: {exc}")
            return self._wrap_as_wav(audio_data)

    def _generate_mock_audio(self, text: str, params: VoiceParams) -> bytes:
        """Generate mock audio for testing (no Nuance SDK)."""
        logger.info(f"Generating mock audio for: {text}")
        logger.info(f"  Params: pitch={params.pitch}, speed={params.speed}, energy={params.energy}")

        # Create silence with appropriate duration
        duration_seconds = len(text) * 0.05  # ~50ms per character
        sample_count = int(self.sample_rate * duration_seconds)

        # Generate very quiet sine wave (simulating speech)
        freq = 440  # A4 note
        t = np.linspace(0, duration_seconds, sample_count, False)
        wave_data = np.sin(2 * np.pi * freq * t) * 0.05

        # Convert to 16-bit PCM
        audio_data = (wave_data * 32767).astype(np.int16).tobytes()

        return self._wrap_as_wav(audio_data)

    def release(self):
        """Clean up resources."""
        if self.engine is not None:
            try:
                self.engine.release()
                logger.info("Nuance engine released.")
            except Exception as exc:
                logger.error(f"Error releasing engine: {exc}")

# =====================================================
# Caching
# =====================================================
class TTSCache:
    """Simple file-based cache for TTS output."""

    @staticmethod
    def get_cache_key(text: str, params: VoiceParams, output_format: str) -> str:
        """Generate cache key from text and parameters."""
        import hashlib
        data = json.dumps({
            "text": text,
            "params": params.to_dict(),
            "format": output_format,
        }, sort_keys=True)
        digest = hashlib.sha256(data.encode()).hexdigest()
        return f"{digest}.{output_format}"

    @staticmethod
    def get(cache_key: str) -> Optional[bytes]:
        """Retrieve cached audio."""
        path = TTS_CACHE_DIR / cache_key
        if path.exists():
            logger.info(f"Cache hit: {cache_key}")
            return path.read_bytes()
        return None

    @staticmethod
    def put(cache_key: str, data: bytes):
        """Store audio in cache."""
        path = TTS_CACHE_DIR / cache_key
        path.write_bytes(data)
        logger.info(f"Cached: {cache_key}")

    @staticmethod
    def clear():
        """Clear all cached files."""
        for file in TTS_CACHE_DIR.glob("*"):
            file.unlink()
        logger.info("Cache cleared.")

# =====================================================
# Main TTS Interface
# =====================================================
class Miitalkmo:
    """Main TTS interface for Miitalkmo."""

    def __init__(self):
        self.engine = TTSEngine()
        self.cache = TTSCache()

    def synthesize(
        self,
        text: str,
        voice_params: Optional[Dict[str, int]] = None,
        output_format: str = "wav",
        use_cache: bool = True,
    ) -> bytes:
        """
        Synthesize text to audio.
        
        Args:
            text: Text to speak
            voice_params: Dict with pitch, depth, energy, accent, speed
            output_format: Output format (wav, mp3, ogg)
            use_cache: Use cached result if available
            
        Returns:
            Audio data as bytes
        """
        text = text.strip()
        if not text:
            raise ValueError("Text is required.")

        params = VoiceParams.from_dict(voice_params)
        output_format = output_format.lower()

        # Check cache
        if use_cache:
            cache_key = self.cache.get_cache_key(text, params, output_format)
            cached = self.cache.get(cache_key)
            if cached:
                return cached

        # Synthesize
        audio_bytes = self.engine.synthesize(text, params, output_format)

        # Cache result
        if use_cache:
            self.cache.put(cache_key, audio_bytes)

        return audio_bytes

    def release(self):
        """Clean up resources."""
        self.engine.release()

# =====================================================
# Module instantiation
# =====================================================
_tts_instance = None

def get_tts_engine() -> Miitalkmo:
    """Get or create TTS engine singleton."""
    global _tts_instance
    if _tts_instance is None:
        _tts_instance = Miitalkmo()
    return _tts_instance

if __name__ == "__main__":
    # Test the TTS module
    tts = get_tts_engine()

    test_text = "Hello! This is Miitalkmo speaking with Nuance Vocalizer."
    test_params = VoiceParams(pitch=60, speed=50, energy=70, accent=50, depth=55)

    print(f"Synthesizing: {test_text}")
    print(f"Params: {test_params.to_dict()}")

    audio = tts.synthesize(test_text, test_params.to_dict(), output_format="wav")
    print(f"Generated {len(audio)} bytes of audio.")

    # Save to file
    output_path = Path("/tmp/miitalkmo_test.wav")
    output_path.write_bytes(audio)
    print(f"Saved to: {output_path}")

    tts.release()
