class EchoflowError(Exception):
    """Base class for user-facing Echoflow failures."""


class ConfigError(EchoflowError):
    """Configuration or local environment is missing or invalid."""


class DownloadError(EchoflowError):
    """Video metadata, subtitle, or audio download failed."""


class SubtitleError(DownloadError):
    """Subtitle extraction failed."""


class TranscriptionError(EchoflowError):
    """Audio transcription failed."""


class SummaryError(EchoflowError):
    """AI summary generation failed."""


class WriteError(EchoflowError):
    """Saving output files failed."""
