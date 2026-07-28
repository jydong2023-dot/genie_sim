# -*- coding: utf-8 -*-

from pathlib import Path

import pytest

from scripts.first_run_demo_tasks import (
    FIRST_RUN_DEMOS,
    find_new_recording_dir,
    parse_index_selection,
    snapshot_recording_dirs,
)
from scripts.run_first_run_demos import apply_template_overrides, configure_seed, parse_template_overrides


def test_first_run_demos_has_nine_entries():
    assert len(FIRST_RUN_DEMOS) == 9
    indices = [int(d["index"]) for d in FIRST_RUN_DEMOS]
    assert indices == list(range(1, 10))


def test_parse_index_selection():
    assert parse_index_selection(None, 10) == set(range(1, 11))
    assert parse_index_selection("1,3,8", 10) == {1, 3, 8}
    assert parse_index_selection("2-4", 10) == {2, 3, 4}


def test_parse_index_selection_rejects_out_of_range():
    with pytest.raises(ValueError):
        parse_index_selection("11", 10)


def test_parse_template_overrides():
    assert parse_template_overrides(["3=tmp/task.json"]) == {"3": "tmp/task.json"}
    with pytest.raises(ValueError):
        parse_template_overrides(["bad"])


def test_apply_template_overrides():
    demos = [{"index": "1", "template": "a.json"}, {"index": "3", "template": "b.json"}]
    updated = apply_template_overrides(demos, {"3": "override.json"})

    assert updated[0]["template"] == "a.json"
    assert updated[1]["template"] == "override.json"
    assert demos[1]["template"] == "b.json"


def test_configure_seed_sets_python_and_numpy_rng():
    configure_seed(10)

    import random

    import numpy as np

    assert random.randint(0, 1000) == 585
    assert np.random.randint(0, 1000) == 265


def test_find_new_recording_dir(tmp_path):
    rec = tmp_path / "recording_data"
    (rec / "old_task").mkdir(parents=True)
    (rec / "new_task").mkdir(parents=True)

    before = snapshot_recording_dirs(tmp_path)
    assert before == {"old_task", "new_task"}

    found = find_new_recording_dir(tmp_path, {"old_task"})
    assert found is not None
    assert found.name == "new_task"


def test_manifest_template_paths_exist():
    root = Path(__file__).resolve().parents[1]
    missing = [demo["template"] for demo in FIRST_RUN_DEMOS if not (root / demo["template"]).is_file()]
    assert not missing, f"Missing templates: {missing}"
