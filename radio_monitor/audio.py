"""Audio capture from RTL-SDR via rtl_fm, with voice activity detection."""
import subprocess
import struct
import math
import threading
import queue
import time
import logging

log = logging.getLogger(__name__)


class AudioCapture:
    """Captures audio from RTL-SDR using rtl_fm and detects voice activity."""

    def __init__(self, config: dict):
        self.freq = config["radio"]["frequency"]
        self.mod = config["radio"]["modulation"]
        self.squelch = config["radio"]["squelch"]
        self.gain = config["radio"]["gain"]
        self.sample_rate = config["radio"]["sample_rate"]
        self.output_rate = config["radio"]["output_rate"]
        self.device_index = config["radio"].get("device_index", 0)

        self.vad_threshold = config["audio"]["vad_threshold"]
        self.silence_timeout = config["audio"]["silence_timeout"]
        self.chunk_duration = config["audio"]["chunk_duration"]
        self.max_buffer = config["audio"]["max_buffer"]

        self._process = None
        self._running = False
        self.audio_queue = queue.Queue()

    def start(self):
        """Start rtl_fm subprocess and audio processing thread."""
        cmd = [
            "rtl_fm",
            "-d", str(self.device_index),
            "-f", str(self.freq),
            "-M", self.mod,
            "-s", str(self.sample_rate),
            "-r", str(self.output_rate),
            "-l", str(self.squelch),
            "-g", str(self.gain),
            "-",
        ]
        log.info(f"Starting rtl_fm: {' '.join(cmd)}")

        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        self._running = True

        thread = threading.Thread(target=self._read_audio, daemon=True)
        thread.start()
        log.info("Audio capture started.")

    def _read_audio(self):
        """Read raw PCM from rtl_fm, detect voice, and queue audio segments."""
        frame_size = 2  # 16-bit signed PCM = 2 bytes per sample
        frames_per_chunk = int(self.output_rate * 0.1)  # 100ms chunks
        bytes_per_chunk = frames_per_chunk * frame_size

        voice_buffer = bytearray()
        silence_start = None
        buffer_start = None

        while self._running and self._process.poll() is None:
            data = self._process.stdout.read(bytes_per_chunk)
            if not data:
                break

            rms = self._calculate_rms(data)
            is_voice = rms > self.vad_threshold

            if is_voice:
                if buffer_start is None:
                    buffer_start = time.time()
                    log.debug("Voice detected, buffering...")
                voice_buffer.extend(data)
                silence_start = None

                # Force-process if buffer exceeds max
                buffer_duration = len(voice_buffer) / (self.output_rate * frame_size)
                if buffer_duration >= self.max_buffer:
                    log.debug(f"Max buffer reached ({buffer_duration:.1f}s), processing...")
                    self._emit_segment(voice_buffer)
                    voice_buffer = bytearray()
                    buffer_start = None

            elif voice_buffer:
                # Voice stopped — wait for silence timeout
                voice_buffer.extend(data)
                if silence_start is None:
                    silence_start = time.time()
                elif time.time() - silence_start >= self.silence_timeout:
                    buffer_duration = len(voice_buffer) / (self.output_rate * frame_size)
                    if buffer_duration >= 0.5:  # Ignore very short blips
                        log.debug(f"Voice segment complete ({buffer_duration:.1f}s)")
                        self._emit_segment(voice_buffer)
                    voice_buffer = bytearray()
                    buffer_start = None
                    silence_start = None

    def _emit_segment(self, buffer: bytearray):
        """Convert raw PCM buffer to numpy array and queue it."""
        import numpy as np
        samples = np.frombuffer(bytes(buffer), dtype=np.int16).astype(np.float32) / 32768.0
        self.audio_queue.put(samples)

    @staticmethod
    def _calculate_rms(data: bytes) -> float:
        """Calculate RMS energy of 16-bit PCM audio data."""
        if len(data) < 2:
            return 0.0
        count = len(data) // 2
        samples = struct.unpack(f"<{count}h", data[:count * 2])
        if not samples:
            return 0.0
        sum_sq = sum(s * s for s in samples)
        rms = math.sqrt(sum_sq / count) / 32768.0
        return rms

    def stop(self):
        self._running = False
        if self._process:
            self._process.terminate()
            self._process.wait()
            log.info("Audio capture stopped.")


class MicCapture:
    """Captures audio from system microphone for testing without RTL-SDR."""

    def __init__(self, config: dict):
        self.output_rate = config["radio"]["output_rate"]
        self.vad_threshold = config["audio"]["vad_threshold"]
        self.silence_timeout = config["audio"]["silence_timeout"]
        self.max_buffer = config["audio"]["max_buffer"]
        self._running = False
        self.audio_queue = queue.Queue()

    def start(self):
        import sounddevice as sd
        self._running = True
        self._buffer = bytearray()
        self._silence_start = None
        self._buffer_start = None

        def callback(indata, frames, time_info, status):
            if not self._running:
                return
            import numpy as np
            pcm = (indata[:, 0] * 32768).astype(np.int16).tobytes()
            rms = AudioCapture._calculate_rms(pcm)
            is_voice = rms > self.vad_threshold

            if is_voice:
                if self._buffer_start is None:
                    self._buffer_start = time.time()
                self._buffer.extend(pcm)
                self._silence_start = None

                buf_dur = len(self._buffer) / (self.output_rate * 2)
                if buf_dur >= self.max_buffer:
                    self._emit()
            elif self._buffer:
                self._buffer.extend(pcm)
                if self._silence_start is None:
                    self._silence_start = time.time()
                elif time.time() - self._silence_start >= self.silence_timeout:
                    buf_dur = len(self._buffer) / (self.output_rate * 2)
                    if buf_dur >= 0.5:
                        self._emit()
                    else:
                        self._buffer = bytearray()
                        self._buffer_start = None
                        self._silence_start = None

        self._stream = sd.InputStream(
            samplerate=self.output_rate,
            channels=1,
            dtype="float32",
            blocksize=int(self.output_rate * 0.1),
            callback=callback,
        )
        self._stream.start()
        log.info("Microphone capture started.")

    def _emit(self):
        import numpy as np
        samples = np.frombuffer(bytes(self._buffer), dtype=np.int16).astype(np.float32) / 32768.0
        self.audio_queue.put(samples)
        self._buffer = bytearray()
        self._buffer_start = None
        self._silence_start = None

    def stop(self):
        self._running = False
        if hasattr(self, "_stream"):
            self._stream.stop()
            self._stream.close()


class FileCapture:
    """Processes a WAV file for testing."""

    def __init__(self, config: dict, filepath: str):
        self.filepath = filepath
        self.output_rate = config["radio"]["output_rate"]
        self.chunk_duration = config["audio"]["chunk_duration"]
        self.audio_queue = queue.Queue()

    def start(self):
        import numpy as np
        import wave

        with wave.open(self.filepath, "rb") as wf:
            rate = wf.getframerate()
            frames = wf.readframes(wf.getnframes())
            samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0

            # If stereo, take first channel
            if wf.getnchannels() == 2:
                samples = samples[::2]

        # Resample if needed
        if rate != self.output_rate:
            duration = len(samples) / rate
            target_len = int(duration * self.output_rate)
            indices = np.linspace(0, len(samples) - 1, target_len).astype(int)
            samples = samples[indices]

        # Chunk it
        chunk_samples = int(self.output_rate * self.chunk_duration)
        for i in range(0, len(samples), chunk_samples):
            chunk = samples[i:i + chunk_samples]
            if len(chunk) > self.output_rate * 0.5:  # skip tiny tail
                self.audio_queue.put(chunk)

        log.info(f"File loaded: {self.filepath} ({len(samples) / self.output_rate:.1f}s)")

    def stop(self):
        pass
