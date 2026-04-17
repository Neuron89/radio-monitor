"""Speech-to-text transcription using faster-whisper."""
import logging
import numpy as np

log = logging.getLogger(__name__)


class Transcriber:
    """Wraps faster-whisper for real-time transcription of audio segments."""

    def __init__(self, config: dict):
        self.model_size = config["whisper"]["model"]
        self.language = config["whisper"]["language"]
        self.compute_type = config["whisper"]["compute_type"]
        self._model = None

    def load(self):
        """Load the Whisper model. Called once at startup."""
        from faster_whisper import WhisperModel
        log.info(f"Loading Whisper model '{self.model_size}' (compute: {self.compute_type})...")
        self._model = WhisperModel(
            self.model_size,
            device="cpu",
            compute_type=self.compute_type,
        )
        log.info("Whisper model loaded.")

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe a numpy audio array (float32, 16kHz mono) to text."""
        if self._model is None:
            self.load()

        segments, info = self._model.transcribe(
            audio,
            language=self.language,
            beam_size=3,
            best_of=3,
            vad_filter=True,
            vad_parameters=dict(
                min_silence_duration_ms=300,
                speech_pad_ms=200,
            ),
        )

        text = " ".join(seg.text.strip() for seg in segments).strip()

        if text:
            log.debug(f"Transcribed ({info.duration:.1f}s): {text}")

        return text
