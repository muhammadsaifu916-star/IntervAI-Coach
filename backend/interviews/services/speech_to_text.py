"""Backend speech-to-text for interview answers.

Accepts recorded audio from the client, converts when needed, and returns
transcript text for the AI interview module.
"""

from __future__ import annotations

import io
import logging
import os
import tempfile
import wave
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import speech_recognition as sr
except ImportError:  # pragma: no cover
    sr = None

try:
    from pydub import AudioSegment
except ImportError:  # pragma: no cover
    AudioSegment = None


def _write_wav_from_pcm(pcm_bytes: bytes, sample_rate: int = 16000) -> str:
    """Write raw PCM16 mono audio to a temporary WAV file."""
    tmp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    with wave.open(tmp.name, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return tmp.name


def _convert_to_wav(source_path: str) -> str:
    """Convert webm/ogg/mp4 audio to wav for SpeechRecognition."""
    if AudioSegment is None:
        raise RuntimeError(
            'Audio conversion requires pydub. Install pydub and ensure ffmpeg is available.'
        )
    ext = Path(source_path).suffix.lower().lstrip('.') or 'webm'
    segment = AudioSegment.from_file(source_path, format=ext)
    segment = segment.set_channels(1).set_frame_rate(16000)
    out = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    segment.export(out.name, format='wav')
    return out.name


def transcribe_audio_file(uploaded_file) -> str:
    """Transcribe an uploaded audio file. Returns stripped transcript or empty string."""
    if sr is None:
        logger.error('speech_recognition is not installed')
        return ''

    raw = uploaded_file.read()
    if not raw:
        return ''

    suffix = Path(getattr(uploaded_file, 'name', '') or 'answer.webm').suffix or '.webm'
    tmp_in = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp_in.write(raw)
    tmp_in.flush()
    tmp_in.close()

    wav_path = None
    paths_to_cleanup = [tmp_in.name]

    try:
        if suffix.lower() == '.wav':
            wav_path = tmp_in.name
        else:
            wav_path = _convert_to_wav(tmp_in.name)
            paths_to_cleanup.append(wav_path)

        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio = recognizer.record(source)

        try:
            text = recognizer.recognize_google(audio, language='en-US')
            return str(text or '').strip()
        except sr.UnknownValueError:
            return ''
        except sr.RequestError as exc:
            logger.warning('Google STT request failed: %s', exc)
            return ''
    except Exception as exc:
        logger.warning('STT failed for %s: %s', suffix, exc)
        return ''
    finally:
        for path in paths_to_cleanup:
            try:
                os.unlink(path)
            except OSError:
                pass


def transcribe_uploads(audio_by_question: dict) -> dict[str, str]:
    """Transcribe a mapping of question_id -> uploaded file."""
    transcripts: dict[str, str] = {}
    for question_id, uploaded in audio_by_question.items():
        transcripts[str(question_id)] = transcribe_audio_file(uploaded)
    return transcripts
