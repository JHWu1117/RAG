"""Offline fallback contract tests for ImageCaptioner (C7)."""

from types import SimpleNamespace

from src.core.types import Chunk
from src.ingestion.transform.image_captioner import ImageCaptioner


def _settings(enabled: bool):
    return SimpleNamespace(
        vision_llm=SimpleNamespace(enabled=enabled),
    )


def _chunk(image_path: str = "missing.png") -> Chunk:
    return Chunk(
        id="chunk-1",
        text="Diagram: [IMAGE: img-1]",
        metadata={
            "source_path": "sample.pdf",
            "image_refs": ["img-1"],
            "images": [{"id": "img-1", "path": image_path}],
        },
    )


def test_disabled_vision_keeps_references_and_marks_unprocessed() -> None:
    chunk = _chunk()
    result = ImageCaptioner(_settings(enabled=False)).transform([chunk])

    assert result[0].metadata["image_refs"] == ["img-1"]
    assert result[0].metadata["has_unprocessed_images"] is True
    assert "image_captions" not in result[0].metadata


def test_missing_image_falls_back_without_blocking() -> None:
    class FakeVision:
        def chat_with_image(self, **kwargs):
            raise AssertionError("missing image must not call provider")

    chunk = _chunk()
    result = ImageCaptioner(
        _settings(enabled=True),
        llm=FakeVision(),
    ).transform([chunk])

    assert result == [chunk]
    assert chunk.metadata["image_refs"] == ["img-1"]
    assert chunk.metadata["has_unprocessed_images"] is True


def test_enabled_vision_adds_mock_caption_without_external_call(tmp_path) -> None:
    image_path = tmp_path / "diagram.png"
    image_path.write_bytes(b"offline-test-image")

    class FakeVision:
        def chat_with_image(self, **kwargs):
            return SimpleNamespace(content="A deterministic architecture diagram.")

    chunk = _chunk(str(image_path))
    result = ImageCaptioner(
        _settings(enabled=True),
        llm=FakeVision(),
    ).transform([chunk])

    assert "A deterministic architecture diagram." in result[0].text
    assert result[0].metadata["image_captions"] == [
        {"id": "img-1", "caption": "A deterministic architecture diagram."}
    ]
    assert "has_unprocessed_images" not in result[0].metadata
