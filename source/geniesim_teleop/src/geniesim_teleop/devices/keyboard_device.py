#!/usr/bin/env python3
# Copyright (c) 2023-2026, AgiBot Inc. All Rights Reserved.
# Author: Genie Sim Team
# License: Mozilla Public License Version 2.0

from geniesim_teleop.devices.teleop_device import TeleopDevice


class KeyboardDevice(TeleopDevice):
    """Keyboard teleop device that emits the same command shape as PicoDevice."""

    VALID_KEYS = {
        "w",
        "s",
        "a",
        "d",
        "i",
        "k",
        "j",
        "l",
        "u",
        "o",
        "r",
        "f",
        "q",
        "e",
        "z",
        "x",
        "c",
        "1",
        "2",
        "up",
        "down",
        "left",
        "right",
    }

    def __init__(self, robot_cfg="G2_omnipicker", pos_step=0.02):
        self.robot_cfg = robot_cfg
        self.pos_step = pos_step
        self.pressed_keys = set()
        self.listener = None
        self.output = {"left": None, "right": None}

    def initialize(self):
        try:
            from pynput import keyboard
        except Exception as exc:
            raise RuntimeError(
                "KeyboardDevice requires pynput and an available GUI keyboard backend. "
                "Install pynput in the container, or run autoteleop.sh which installs it."
            ) from exc

        self.listener = keyboard.Listener(on_press=self.press_key, on_release=self.release_key)
        self.listener.start()

    def update(self, debug=False):
        l_axis_x = self._axis("d", "a")
        l_axis_y = self._axis("w", "s")
        left_pos = [
            self._axis("up", "down") * self.pos_step,
            self._axis("right", "left") * self.pos_step,
            self._axis("r", "f") * self.pos_step,
        ]
        right_pos = [
            self._axis("i", "k") * self.pos_step,
            self._axis("l", "j") * self.pos_step,
            self._axis("u", "o") * self.pos_step,
        ]

        l_on = self._is_pressed("1")
        r_on = self._is_pressed("2")
        l_eef = 1.0 if self._is_pressed("q") else 0.0
        r_eef = 1.0 if self._is_pressed("e") else 0.0
        l_x = self._is_pressed("z")
        r_a = self._is_pressed("x")
        r_b = self._is_pressed("c")

        if not any(
            [
                l_axis_x,
                l_axis_y,
                any(left_pos),
                any(right_pos),
                l_on,
                r_on,
                l_eef,
                r_eef,
                l_x,
                r_a,
                r_b,
            ]
        ):
            return {}

        identity_quat = [0.0, 0.0, 0.0, 1.0]
        self.output = {
            "left": self._round_pose(left_pos + identity_quat),
            "right": self._round_pose(right_pos + identity_quat),
            "l_eef": l_eef,
            "r_eef": r_eef,
            "l_on": l_on,
            "r_on": r_on,
            "r_b": r_b,
            "r_a": r_a,
            "l_x": l_x,
            "r_axisX": 0.0,
            "r_axisY": 0.0,
            "l_axisX": l_axis_x,
            "l_axisY": l_axis_y,
        }
        return self.output

    def reset(self):
        self.output = {"left": None, "right": None}
        self.pressed_keys.clear()

    def press_key(self, key):
        key_id = self._key_id(key)
        if key_id in self.VALID_KEYS:
            self.pressed_keys.add(key_id)

    def release_key(self, key):
        self.pressed_keys.discard(self._key_id(key))

    def extra_l(self):
        return False

    def extra_r(self):
        return self._is_pressed("c")

    def _axis(self, positive_key, negative_key):
        return float(self._is_pressed(positive_key)) - float(self._is_pressed(negative_key))

    def _is_pressed(self, key):
        return key in self.pressed_keys

    def _key_id(self, key):
        if isinstance(key, str):
            raw = key
        else:
            raw = getattr(key, "char", None) or str(key)
        raw = raw.lower()
        if raw.startswith("key."):
            raw = raw.split(".", 1)[1]
        return raw

    def _round_pose(self, pose):
        return [round(value, 3) for value in pose]
