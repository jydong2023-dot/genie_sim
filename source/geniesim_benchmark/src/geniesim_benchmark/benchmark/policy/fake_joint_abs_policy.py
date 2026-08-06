# Copyright (c) 2023-2026, AgiBot Inc. All Rights Reserved.
# Author: Genie Sim Team
# License: Mozilla Public License Version 2.0

import math

from .base import BasePolicy
from geniesim_benchmark.plugins.logger import Logger
from geniesim_benchmark.utils.name_utils import ROBOT_CONFIGS


logger = Logger()


class FakeJointAbsPolicy(BasePolicy):
    """Deterministic JOINT_ABS smoke policy for validating robot actuation.

    It does not call an inference service. The policy emits small absolute
    joint targets around the observed current pose, then returns None to end
    the episode after ``max_steps`` control steps.
    """

    def __init__(
        self,
        task_name="",
        sub_task_name="",
        robot_cfg="dual_agx_nero",
        max_steps=90,
        amplitude=0.08,
    ) -> None:
        super().__init__(task_name=task_name, sub_task_name=sub_task_name)
        self.robot_cfg = robot_cfg
        self.max_steps = int(max_steps)
        self.amplitude = float(amplitude)
        self.step_idx = 0
        self._episode_idx = 0
        self._robot_config = ROBOT_CONFIGS.get(robot_cfg)
        if self._robot_config is None:
            raise ValueError(f"Unsupported robot_cfg for FakeJointAbsPolicy: {robot_cfg}")
        self._arm_dim = len(self._robot_config["arm_joints"])
        self._gripper_dim = len(self._robot_config["gripper_joints"])
        self._init_gripper_open = list(self._robot_config.get("init_gripper_open", [0.0] * self._gripper_dim))

    def reset(self):
        self.step_idx = 0
        self.action_buffer.clear()

    def set_episode_idx(self, idx):
        self._episode_idx = idx

    def need_infer(self):
        return False

    def _split_arm_state(self, observation):
        states = observation.get("states", {}) if observation else {}
        if isinstance(states, dict):
            return list(states["left_arm"]) + list(states["right_arm"])
        return list(states[: self._arm_dim])

    def _gripper_target(self, observation):
        states = observation.get("states", {}) if observation else {}
        if isinstance(states, dict):
            gripper = list(states.get("left_gripper", [])) + list(states.get("right_gripper", []))
            if len(gripper) == self._gripper_dim:
                return [float(v) for v in gripper]
        return [float(v) for v in self._init_gripper_open[: self._gripper_dim]]

    def act(self, observations, **kwargs):
        if self.step_idx >= self.max_steps:
            logger.info(
                f"[FakeJointAbsPolicy] episode_idx={self._episode_idx} finished after {self.step_idx} steps"
            )
            return None

        arm = self._split_arm_state(observations)
        if len(arm) != self._arm_dim:
            raise ValueError(f"Expected {self._arm_dim} arm joints, got {len(arm)}")

        phase = (self.step_idx + 1) * 0.2
        delta = self.amplitude * math.sin(phase)
        target = [float(v) for v in arm]

        # Move shoulder/elbow joints on both arms in opposite directions so the
        # smoke test is visible while staying close to the reset pose.
        for idx, sign in ((1, 1.0), (3, -0.5), (8, -1.0), (10, 0.5)):
            if idx < len(target):
                target[idx] += sign * delta

        self.step_idx += 1
        if self.step_idx == 1 or self.step_idx % 30 == 0:
            current_preview = [round(v, 4) for v in arm[:4] + arm[7:11]]
            target_preview = [round(v, 4) for v in target[:4] + target[7:11]]
            logger.info(
                f"[FakeJointAbsPolicy] episode_idx={self._episode_idx} step={self.step_idx} "
                f"kind=JOINT_ABS cur_preview={current_preview} target_preview={target_preview}"
            )

        return {
            "arm": target,
            "gripper": self._gripper_target(observations),
            "kind": "JOINT_ABS",
        }
