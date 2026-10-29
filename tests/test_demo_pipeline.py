from __future__ import annotations

from pathlib import Path

import pytest

from demo.scripts.demo_pipeline import (
    ALLOWED_FIXTURES,
    SCENE_IDS,
    build_vtt,
    narration_scenes,
    public_failure,
    timestamp_vtt,
    transcript_text,
    validate_app_url,
    validate_fixture_path,
    validate_output_path,
    validate_speech_endpoint,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPOSITORY_ROOT / "demo" / "narration" / "script.txt"


def test_narration_and_transcript_have_seven_exact_scene_paragraphs() -> None:
    scenes = narration_scenes(SCRIPT_PATH)

    assert len(scenes) == 7
    assert transcript_text(scenes) == SCRIPT_PATH.read_text(encoding="utf-8")
    assert scenes[-1].endswith(
        "Protect sensitive information before it enters your enterprise AI workflow."
    )


def test_caption_timing_generation_is_ordered_and_syntactically_valid() -> None:
    scenes = narration_scenes(SCRIPT_PATH)
    events = [
        {"scene_id": scene, "start_ms": index * 10_000, "duration_ms": 5_000}
        for index, scene in enumerate(SCENE_IDS)
    ]

    vtt = build_vtt(scenes, events)

    assert vtt.startswith("WEBVTT\n\n1\n00:00:00.000 --> 00:00:05.000\n")
    assert vtt.count(" --> ") == 7
    assert scenes[-1] in vtt


def test_caption_generation_rejects_scene_reordering() -> None:
    scenes = narration_scenes(SCRIPT_PATH)
    events = [
        {"scene_id": scene, "start_ms": index * 10_000, "duration_ms": 5_000}
        for index, scene in enumerate(reversed(SCENE_IDS))
    ]

    with pytest.raises(ValueError, match="scene order"):
        build_vtt(scenes, events)


def test_webvtt_timestamp_rounding_and_hour_format() -> None:
    assert timestamp_vtt(1_234) == "00:00:01.234"
    assert timestamp_vtt(3_600_000) == "01:00:00.000"


def test_only_allowlisted_synthetic_fixtures_can_be_used() -> None:
    for filename in ALLOWED_FIXTURES:
        assert validate_fixture_path(REPOSITORY_ROOT / "samples" / "input" / filename).is_file()


def test_fixture_outside_samples_input_is_rejected() -> None:
    with pytest.raises(ValueError, match="outside samples/input"):
        validate_fixture_path(REPOSITORY_ROOT / "README.md")


def test_unsupported_fixture_type_is_rejected() -> None:
    with pytest.raises(ValueError, match="allow-list"):
        validate_fixture_path(REPOSITORY_ROOT / "samples" / "input" / "synthetic-contacts.csv")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://demo.example.test", "https://demo.example.test"),
        ("http://localhost:8000/", "http://localhost:8000"),
    ],
)
def test_app_url_validation_accepts_secure_deployment_or_local_test(
    value: str,
    expected: str,
) -> None:
    assert validate_app_url(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "http://demo.example.test",
        "https://user:password@demo.example.test",
        "https://demo.example.test/path",
        "https://demo.example.test/?mode=demo",
    ],
)
def test_app_url_validation_rejects_unsafe_or_non_base_urls(value: str) -> None:
    with pytest.raises(ValueError):
        validate_app_url(value)


@pytest.mark.parametrize(
    "value",
    [
        "https://speech.cognitiveservices.azure.com",
        "https://australiaeast.tts.speech.microsoft.com",
    ],
)
def test_speech_endpoint_validation_accepts_azure_speech_hosts(value: str) -> None:
    assert validate_speech_endpoint(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "https://speech.example.test",
        "http://australiaeast.tts.speech.microsoft.com",
        "https://user:synthetic-only@speech.cognitiveservices.azure.com",
    ],
)
def test_speech_endpoint_validation_rejects_non_azure_or_unsafe_values(value: str) -> None:
    with pytest.raises(ValueError, match="Azure AI Speech"):
        validate_speech_endpoint(value)


def test_generated_output_paths_must_remain_inside_output_directory(tmp_path: Path) -> None:
    output = tmp_path / "output"
    assert validate_output_path(output / "demo.mp4", output) == output / "demo.mp4"

    with pytest.raises(ValueError, match="inside demo/output"):
        validate_output_path(tmp_path / "outside.mp4", output)


@pytest.mark.parametrize("stage", ["speech", "recording", "composition"])
def test_public_failure_messages_are_value_blind(stage: str) -> None:
    message = public_failure(stage)

    assert "http://" not in message.casefold()
    assert "https://" not in message.casefold()


def test_required_responsible_use_disclaimer_is_part_of_narration() -> None:
    closing = narration_scenes(SCRIPT_PATH)[-1]

    assert "Automated detection can miss sensitive information." in closing
    assert "Always review the redacted copy" in closing
