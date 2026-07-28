import numpy as np

from geniesim_benchmark.preview_overlay import annotate_instruction


def test_annotate_instruction_draws_visible_label_without_resizing():
    image = np.full((120, 220, 3), 180, dtype=np.uint8)

    annotated = annotate_instruction(image, "Pick up the red block on the table")

    assert annotated.shape == image.shape
    assert annotated.dtype == image.dtype
    assert not np.array_equal(annotated[-40:, :, :], image[-40:, :, :])
    assert np.array_equal(image, np.full((120, 220, 3), 180, dtype=np.uint8))


def test_annotate_instruction_handles_empty_instruction():
    image = np.zeros((80, 160, 3), dtype=np.uint8)

    annotated = annotate_instruction(image, "")

    assert annotated.shape == image.shape


def test_annotate_instruction_uses_large_text_on_full_size_preview():
    image = np.zeros((800, 1280, 3), dtype=np.uint8)

    annotated = annotate_instruction(image, "Pick the red block")

    text_rows = np.flatnonzero(np.any(annotated > 200, axis=(1, 2)))
    assert text_rows[-1] - text_rows[0] + 1 >= 28
