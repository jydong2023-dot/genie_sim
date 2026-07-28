from geniesim_benchmark.benchmark.render_profile import (
    format_frame_profile,
    format_render_profile,
    is_head_camera_name,
)


def test_is_head_camera_name_matches_g1_and_g2_head_cameras():
    assert is_head_camera_name("head_camera")
    assert is_head_camera_name("head_front_camera")
    assert not is_head_camera_name("left_camera")


def test_format_render_profile_includes_total_and_shape():
    line = format_render_profile(
        camera_name="head_front_camera",
        env_idx=0,
        render_wait_ms=12.34,
        get_data_ms=1.2,
        shape=(400, 640, 4),
        subframes=8,
    )

    assert line == (
        "[render_profile] env=0 camera=head_front_camera "
        "render_wait_ms=12.34 get_data_ms=1.20 total_ms=13.54 "
        "shape=(400, 640, 4) subframes=8"
    )


def test_format_frame_profile_includes_world_step_and_render_step_times():
    line = format_frame_profile(
        frame_idx=42,
        render_enabled=True,
        world_step_ms=16.789,
        render_step_ms=1.234,
    )

    assert line == (
        "[frame_profile] frame=42 render_enabled=True "
        "world_step_ms=16.79 render_step_ms=1.23 total_ms=18.02"
    )
