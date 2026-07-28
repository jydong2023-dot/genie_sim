from geniesim_teleop.devices.keyboard_device import KeyboardDevice


def test_idle_keyboard_returns_no_command():
    device = KeyboardDevice()

    assert device.update() == {}


def test_keyboard_outputs_pico_compatible_command_fields():
    device = KeyboardDevice(pos_step=0.05)

    for key in ("w", "d", "1", "up", "right", "r", "q", "2", "i", "l", "u", "e", "c"):
        device.press_key(key)

    output = device.update()

    assert output["l_axisY"] == 1.0
    assert output["l_axisX"] == 1.0
    assert output["l_on"] is True
    assert output["left"] == [0.05, 0.05, 0.05, 0.0, 0.0, 0.0, 1.0]
    assert output["l_eef"] == 1.0

    assert output["r_on"] is True
    assert output["right"] == [0.05, 0.05, 0.05, 0.0, 0.0, 0.0, 1.0]
    assert output["r_eef"] == 1.0
    assert output["r_b"] is True
    assert device.extra_r() is True


def test_released_keys_stop_output():
    device = KeyboardDevice()
    device.press_key("w")
    assert device.update()

    device.release_key("w")

    assert device.update() == {}
