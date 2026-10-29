"""Deterministic validation and caption helpers for the demo pipeline."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SAMPLES_ROOT = (REPOSITORY_ROOT / "samples" / "input").resolve()
OUTPUT_ROOT = (REPOSITORY_ROOT / "demo" / "output").resolve()
SCENE_IDS = (
    "introduction",
    "purpose",
    "text",
    "document",
    "image",
    "ecosystem",
    "closing",
)
ALLOWED_FIXTURES = frozenset(
    {
        "synthetic-contact.txt",
        "synthetic-secrets.txt",
        "synthetic-pii-form.pdf",
        "synthetic-pii-record.docx",
        "synthetic-pii-image.png",
    }
)
SUPPORTED_FIXTURE_EXTENSIONS = frozenset({".txt", ".pdf", ".docx", ".png"})
REVIEW_WARNING = (
    "Automated detection can miss sensitive information. Always review the redacted copy"
)
FINAL_MESSAGE = "Protect sensitive information before it enters your enterprise AI workflow."


def narration_scenes(script_path: Path) -> list[str]:
    """Read the seven customer-facing narration paragraphs without altering their wording."""
    try:
        text = script_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ValueError("The narration script could not be read.") from exc
    scenes = [part.strip() for part in text.split("\n\n") if part.strip()]
    if len(scenes) != len(SCENE_IDS):
        raise ValueError("The narration script must contain exactly seven scene paragraphs.")
    if REVIEW_WARNING.casefold() not in scenes[-1].casefold():
        raise ValueError("The closing narration must include the responsible-use warning.")
    if FINAL_MESSAGE.casefold() not in scenes[-1].casefold():
        raise ValueError("The closing narration must include the approved final message.")
    return scenes


def validate_fixture_path(path: str | Path) -> Path:
    """Resolve only approved repository-owned synthetic fixtures."""
    candidate = Path(path)
    try:
        resolved = candidate.resolve(strict=True)
        relative = resolved.relative_to(SAMPLES_ROOT)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError(
            "A required synthetic fixture is unavailable or outside samples/input."
        ) from exc
    if (
        len(relative.parts) != 1
        or resolved.name not in ALLOWED_FIXTURES
        or resolved.suffix.casefold() not in SUPPORTED_FIXTURE_EXTENSIONS
        or not resolved.is_file()
    ):
        raise ValueError("The demo fixture is not on the synthetic input allow-list.")
    return resolved


def validate_app_url(value: str) -> str:
    """Validate a base application URL without retaining it in generated artifacts."""
    try:
        parsed = urlsplit(value.strip())
        hostname = parsed.hostname
        if (
            parsed.scheme not in {"https", "http"}
            or not hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError
        if parsed.scheme == "http" and hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError
    except (AttributeError, ValueError) as exc:
        raise ValueError("The application URL must be an HTTPS base URL.") from exc
    return value.strip().rstrip("/")


def validate_speech_endpoint(value: str) -> str:
    """Accept Azure Speech HTTPS endpoints only."""
    try:
        parsed = urlsplit(value.strip())
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or not parsed.hostname.endswith(
                (
                    ".cognitiveservices.azure.com",
                    ".api.cognitive.microsoft.com",
                    ".tts.speech.microsoft.com",
                    ".speech.microsoft.com",
                )
            )
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError
    except ValueError as exc:
        raise ValueError(
            "AZURE_SPEECH_ENDPOINT must be an HTTPS Azure AI Speech endpoint."
        ) from exc
    return value.strip().rstrip("/")


def transcript_text(scenes: list[str]) -> str:
    """Render narration paragraphs with no wording changes."""
    if len(scenes) != len(SCENE_IDS):
        raise ValueError("The narration transcript requires all seven scenes.")
    return "\n\n".join(scenes) + "\n"


def validate_output_path(path: str | Path, output_root: Path = OUTPUT_ROOT) -> Path:
    """Ensure generated assets remain inside the demo output directory."""
    root = output_root.resolve()
    candidate = Path(path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("A generated asset path must remain inside demo/output.") from exc
    return candidate


def timestamp_vtt(milliseconds: int) -> str:
    """Format a non-negative millisecond offset as a WebVTT timestamp."""
    if milliseconds < 0:
        raise ValueError("Caption timing cannot be negative.")
    total_ms = milliseconds
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def build_vtt(scenes: list[str], events: list[dict[str, int | str]]) -> str:
    """Create ordered, non-overlapping WebVTT cues using recorded speech offsets."""
    if len(scenes) != len(SCENE_IDS) or len(events) != len(SCENE_IDS):
        raise ValueError("Caption timing requires all seven narration scenes.")
    cues = ["WEBVTT", ""]
    previous_end = 0
    for index, (scene_id, text, event) in enumerate(
        zip(SCENE_IDS, scenes, events, strict=True),
        start=1,
    ):
        if event.get("scene_id") != scene_id:
            raise ValueError("Recorded scene order does not match the narration.")
        start_ms = event.get("start_ms")
        duration_ms = event.get("duration_ms")
        if (
            not isinstance(start_ms, int)
            or isinstance(start_ms, bool)
            or not isinstance(duration_ms, int)
            or isinstance(duration_ms, bool)
            or start_ms < previous_end
            or duration_ms <= 0
        ):
            raise ValueError("Recorded caption timings are invalid.")
        end_ms = start_ms + duration_ms
        cues.extend(
            (
                str(index),
                f"{timestamp_vtt(start_ms)} --> {timestamp_vtt(end_ms)}",
                text,
                "",
            )
        )
        previous_end = end_ms
    return "\n".join(cues)


def public_failure(stage: str) -> str:
    """Return a fixed safe error string; never include exception or source text."""
    messages = {
        "speech": (
            "Azure AI Speech narration failed; no diagnostic response or "
            "source content was recorded."
        ),
        "recording": (
            "The browser demo did not complete its privacy checks; no recording was saved."
        ),
        "composition": "The demo media could not be composed or validated.",
    }
    try:
        return messages[stage]
    except KeyError as exc:
        raise ValueError("Unknown demo pipeline stage.") from exc
