import pytest

from geniesim_benchmark.benchmark.instance_selection import select_scene_instance_ids


def test_selects_exact_scene_instance_ids_in_numeric_order():
    assert select_scene_instance_ids([0, 8, 9, 12], "9,8") == [8, 9]


@pytest.mark.parametrize("requested", ["8,x", "8,8", "99"])
def test_rejects_invalid_exact_scene_instance_ids(requested):
    with pytest.raises(ValueError):
        select_scene_instance_ids([0, 8, 9], requested)

