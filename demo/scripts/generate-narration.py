"""Generate Australian-English narration with Azure AI Speech and Entra ID."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import wave
from pathlib import Path
from xml.sax.saxutils import escape

import httpx
from azure.core.exceptions import ClientAuthenticationError
from azure.identity import CredentialUnavailableError, DefaultAzureCredential

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))

from demo.scripts.demo_pipeline import (  # noqa: E402
    OUTPUT_ROOT,
    SCENE_IDS,
    build_vtt,
    narration_scenes,
    public_failure,
    transcript_text,
    validate_output_path,
    validate_speech_endpoint,
)

SCRIPT_PATH = REPOSITORY_ROOT / "demo" / "narration" / "script.txt"
MANIFEST_PATH = OUTPUT_ROOT / "speech-manifest.json"
TRANSCRIPT_PATH = OUTPUT_ROOT / "transcript.txt"
NARRATION_PATH = OUTPUT_ROOT / "narration.wav"
CAPTIONS_PATH = OUTPUT_ROOT / "sensitive-data-protection-demo.vtt"
VOICE = "en-AU-NatashaNeural"
SAMPLE_RATE = 24_000
MIN_DURATION_MS = 195_000
MAX_DURATION_MS = 240_000


def speech_request_url(endpoint: str) -> str:
    """Validate an Azure Speech endpoint and construct its text-to-speech route."""
    base = validate_speech_endpoint(endpoint)
    if base.endswith("/cognitiveservices/v1"):
        return base
    return f"{base}/cognitiveservices/v1"


def endpoint_from_environment() -> str:
    """Require the non-secret endpoint exported by the selected azd environment."""
    value = os.environ.get("AZURE_SPEECH_ENDPOINT", "").strip()
    if not value:
        raise ValueError(
            "Missing non-secret configuration AZURE_SPEECH_ENDPOINT in the "
            "rai-private azd environment or process environment."
        )
    return speech_request_url(value)


def synthesize_scene(text: str, endpoint: str, credential: DefaultAzureCredential) -> bytes:
    """Request WAV speech without logging request text, endpoint, or response bodies."""
    try:
        token = credential.get_token("https://cognitiveservices.azure.com/.default").token
    except (CredentialUnavailableError, ClientAuthenticationError):
        raise RuntimeError(
            "Entra authentication for Azure AI Speech failed; check Azure CLI sign-in and RBAC."
        ) from None

    ssml = (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
        'xml:lang="en-AU">'
        f'<voice name="{VOICE}"><prosody rate="-5%">{escape(text)}</prosody></voice>'
        "</speak>"
    )
    try:
        response = httpx.post(
            endpoint,
            content=ssml.encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": "riff-24khz-16bit-mono-pcm",
                "User-Agent": "SensitiveDataProtectionDemo",
            },
            timeout=90,
        )
    except httpx.HTTPError:
        raise RuntimeError(
            "Azure AI Speech could not be reached; verify endpoint connectivity."
        ) from None
    if response.status_code >= 400:
        raise RuntimeError(
            f"Azure AI Speech returned HTTP {response.status_code}; "
            "verify endpoint access and Entra RBAC."
        )
    return response.content


def wav_duration_ms(path: Path) -> int:
    """Return duration for a valid mono 24 kHz 16-bit PCM WAV file."""
    with wave.open(str(path), "rb") as source:
        if (
            source.getnchannels() != 1
            or source.getsampwidth() != 2
            or source.getframerate() != SAMPLE_RATE
            or source.getnframes() <= 0
        ):
            raise ValueError("Speech service returned audio in an unexpected WAV format.")
        return round(source.getnframes() * 1000 / source.getframerate())


def write_transcript(scenes: list[str]) -> None:
    validate_output_path(TRANSCRIPT_PATH).write_text(
        transcript_text(scenes),
        encoding="utf-8",
    )


def load_manifest(scenes: list[str]) -> dict[str, object]:
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            "A valid local narration set is not available; generate narration first."
        ) from exc
    if not isinstance(manifest, dict) or manifest.get("script_sha256") != hashlib.sha256(
        SCRIPT_PATH.read_bytes()
    ).hexdigest():
        raise ValueError("Local narration does not match the current narration script.")
    manifest_scenes = manifest.get("scenes")
    if not isinstance(manifest_scenes, list) or len(manifest_scenes) != len(scenes):
        raise ValueError("The local narration set is incomplete.")
    for index, scene in enumerate(manifest_scenes):
        if (
            not isinstance(scene, dict)
            or scene.get("scene_id") != SCENE_IDS[index]
            or scene.get("audio_file") != f"speech-{index + 1:02d}.wav"
        ):
            raise ValueError("The local narration set is invalid.")
        audio_path = validate_output_path(OUTPUT_ROOT / str(scene["audio_file"]))
        if wav_duration_ms(audio_path) != scene.get("duration_ms"):
            raise ValueError("A local narration audio segment is invalid.")
    return manifest


def synthesize(*, skip_existing: bool) -> dict[str, object]:
    scenes = narration_scenes(SCRIPT_PATH)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    if skip_existing:
        manifest = load_manifest(scenes)
        write_transcript(scenes)
        return manifest

    endpoint = endpoint_from_environment()
    credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
    metadata: list[dict[str, int | str]] = []
    try:
        for index, (scene_id, text) in enumerate(zip(SCENE_IDS, scenes, strict=True), start=1):
            audio = synthesize_scene(text, endpoint, credential)
            audio_path = validate_output_path(OUTPUT_ROOT / f"speech-{index:02d}.wav")
            audio_path.write_bytes(audio)
            metadata.append(
                {
                    "scene_id": scene_id,
                    "audio_file": audio_path.name,
                    "duration_ms": wav_duration_ms(audio_path),
                }
            )
    except RuntimeError:
        raise
    except (OSError, ValueError):
        raise RuntimeError(public_failure("speech")) from None
    finally:
        credential.close()

    manifest: dict[str, object] = {
        "version": 1,
        "voice": VOICE,
        "locale": "en-AU",
        "sample_rate": SAMPLE_RATE,
        "script_sha256": hashlib.sha256(SCRIPT_PATH.read_bytes()).hexdigest(),
        "scenes": metadata,
    }
    validate_output_path(MANIFEST_PATH).write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    write_transcript(scenes)
    return manifest


def assemble_audio(
    manifest: dict[str, object],
    events: list[dict[str, int | str]],
    total_duration_ms: int,
) -> None:
    """Place speech clips at recorded scene offsets and regenerate the matching VTT."""
    scenes = narration_scenes(SCRIPT_PATH)
    vtt = build_vtt(scenes, events)
    duration_ms = max(total_duration_ms, MIN_DURATION_MS)
    if (
        isinstance(total_duration_ms, bool)
        or total_duration_ms < 0
        or duration_ms > MAX_DURATION_MS
    ):
        raise ValueError("The browser sequence exceeded the four-minute demo limit.")
    target_frames = round(duration_ms * SAMPLE_RATE / 1000)
    output = bytearray(target_frames * 2)
    manifest_scenes = manifest["scenes"]
    if not isinstance(manifest_scenes, list) or len(manifest_scenes) != len(events):
        raise ValueError("The local narration set is incomplete.")

    for item, event in zip(manifest_scenes, events, strict=True):
        if not isinstance(item, dict):
            raise ValueError("The local narration set is invalid.")
        if (
            event.get("scene_id") != item.get("scene_id")
            or event.get("duration_ms") != item.get("duration_ms")
        ):
            raise ValueError("Recorded speech timing does not match the narration manifest.")
        audio_path = validate_output_path(OUTPUT_ROOT / str(item["audio_file"]))
        start_frame = round(int(event["start_ms"]) * SAMPLE_RATE / 1000)
        with wave.open(str(audio_path), "rb") as source:
            frames = source.readframes(source.getnframes())
        end_frame = start_frame + len(frames) // 2
        if end_frame > target_frames:
            raise ValueError("Narration extends beyond the recorded browser sequence.")
        start_byte = start_frame * 2
        output[start_byte : start_byte + len(frames)] = frames

    with wave.open(str(validate_output_path(NARRATION_PATH)), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(SAMPLE_RATE)
        target.writeframes(output)
    validate_output_path(CAPTIONS_PATH).write_text(vtt, encoding="utf-8")
    write_transcript(scenes)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-narration", action="store_true")
    parser.add_argument("--assemble", action="store_true")
    parser.add_argument("--sequence")
    args = parser.parse_args()

    try:
        manifest = synthesize(skip_existing=args.skip_narration)
        if args.assemble:
            if not args.sequence:
                raise ValueError("A browser sequence is required to assemble the demo.")
            sequence_path = validate_output_path(Path(args.sequence))
            sequence = json.loads(sequence_path.read_text(encoding="utf-8"))
            if not isinstance(sequence, dict):
                raise ValueError("The browser sequence is invalid.")
            events = sequence.get("scenes")
            total_ms = sequence.get("total_duration_ms")
            if not isinstance(events, list) or not isinstance(total_ms, int):
                raise ValueError("The browser sequence is incomplete.")
            assemble_audio(manifest, events, total_ms)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print("Narration and captions are ready; no source content or endpoint values were logged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
