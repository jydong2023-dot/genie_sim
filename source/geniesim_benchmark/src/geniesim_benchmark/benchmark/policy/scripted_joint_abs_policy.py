# Copyright (c) 2023-2026, AgiBot Inc. All Rights Reserved.
# Author: Genie Sim Team
# License: Mozilla Public License Version 2.0

import os
from pathlib import Path

import numpy as np

from .base import BasePolicy
from geniesim_benchmark.benchmark.config.robot_init_states import TASK_INFO_DICT
from geniesim_benchmark.plugins.logger import Logger
from geniesim_benchmark.utils.name_utils import ROBOT_CONFIGS


logger = Logger()


class ScriptedJointAbsPolicy(BasePolicy):
    """Small JOINT_ABS script for dual_agx_nero observation and actuation smoke tests."""

    _KEYFRAMES = (
        (0, "home", [0.0, -0.61, 0.0, -1.0, 0.0, -0.7, -0.61], "open"),
        (100, "settle", [0.0, -0.61, 0.0, -1.0, 0.0, -0.7, -0.61], "open"),
        (200, "approach", [0.0, -0.81, 0.0, -1.0, 0.0, -0.7, -0.61], "open"),
        (300, "close", [0.0, -0.81, 0.0, -1.0, 0.0, -0.7, -0.61], "closed"),
        (400, "lift", [0.0, -0.61, 0.0, -1.0, 0.5, -0.7, -0.61], "closed"),
        (500, "return_home", [0.0, -0.61, 0.0, -1.0, 0.0, -0.7, -0.61], "open"),
    )

    def __init__(
        self,
        task_name="",
        sub_task_name="pick_block_color",
        robot_cfg="dual_agx_nero",
        save_observation_images=True,
    ) -> None:
        super().__init__(task_name=task_name, sub_task_name=sub_task_name)
        self.robot_cfg = robot_cfg
        self.save_observation_images = bool(save_observation_images)
        self.step_idx = 0
        self._episode_idx = 0
        self._saved_observation_images = False

        self._robot_config = ROBOT_CONFIGS.get(robot_cfg)
        if self._robot_config is None:
            raise ValueError(f"Unsupported robot_cfg for ScriptedJointAbsPolicy: {robot_cfg}")
        self._arm_dim = len(self._robot_config["arm_joints"])
        self._gripper_dim = len(self._robot_config["gripper_joints"])

        task_info = TASK_INFO_DICT.get(sub_task_name, {}).get(robot_cfg)
        if task_info is None:
            raise ValueError(f"No scripted home pose for sub_task={sub_task_name}, robot_cfg={robot_cfg}")
        self.home_arm = [float(v) for v in task_info["init_arm"]]
        if len(self.home_arm) != self._arm_dim:
            raise ValueError(f"Expected {self._arm_dim} home arm joints, got {len(self.home_arm)}")

        self._single_arm_dim = self._arm_dim // 2
        self.left_home = self.home_arm[: self._single_arm_dim]
        self.right_home = self.home_arm[self._single_arm_dim :]
        self._logged_reset_observation = False

        self.open_gripper = [float(v) for v in self._robot_config.get("init_gripper_open", [0.0] * self._gripper_dim)]
        self.closed_gripper = [0.0] * self._gripper_dim
        self.total_steps = self._KEYFRAMES[-1][0]

    def reset(self):
        self.step_idx = 0
        self._saved_observation_images = False
        self._logged_reset_observation = False
        self.action_buffer.clear()

    def set_episode_idx(self, idx):
        self._episode_idx = idx

    def need_infer(self):
        return False

    def _interpolated_stage(self):
        if self.step_idx >= self.total_steps:
            return self._KEYFRAMES[-1][1], self._KEYFRAMES[-1][2], self._KEYFRAMES[-1][3]

        prev = self._KEYFRAMES[0]
        for nxt in self._KEYFRAMES[1:]:
            if self.step_idx <= nxt[0]:
                span = max(1, nxt[0] - prev[0])
                ratio = (self.step_idx - prev[0]) / span
                prev_offset = np.asarray(prev[2], dtype=np.float64)
                next_offset = np.asarray(nxt[2], dtype=np.float64)
                offset = ((1.0 - ratio) * prev_offset + ratio * next_offset).tolist()
                return nxt[1], offset, nxt[3]
            prev = nxt
        return prev[1], prev[2], prev[3]

    def _arm_target(self, single_arm_offset):
        left = [base + delta for base, delta in zip(self.left_home, single_arm_offset)]
        right = [base + delta for base, delta in zip(self.right_home, single_arm_offset)]
        return [float(v) for v in left + right]

    def _gripper_target(self, gripper_state):
        if gripper_state == "closed":
            return list(self.closed_gripper)
        return list(self.open_gripper)

    def _save_observation_images(self, observations):
        if self._saved_observation_images or not self.save_observation_images:
            return
        images = (observations or {}).get("images", {})
        if not images:
            logger.warning("[ScriptedJointAbsPolicy] no observation images to save")
            self._saved_observation_images = True
            return

        try:
            import cv2
        except Exception as exc:
            logger.warning(f"[ScriptedJointAbsPolicy] cv2 unavailable; skip saving images: {exc}")
            self._saved_observation_images = True
            return

        root = Path(os.environ.get("SIM_REPO_ROOT") or os.environ.get("GENIESIM_REPO_ROOT") or os.getcwd())
        out_dir = root / "debug_preview" / "dual_agx_nero_scripted_smoke"
        out_dir.mkdir(parents=True, exist_ok=True)

        for name, image in images.items():
            if image is None or getattr(image, "size", 0) == 0:
                logger.warning(f"[ScriptedJointAbsPolicy] empty observation image: {name}")
                continue
            image_arr = np.asarray(image)
            if image_arr.ndim == 3 and image_arr.shape[-1] == 3:
                image_arr = cv2.cvtColor(image_arr, cv2.COLOR_RGB2BGR)
            path = out_dir / f"episode_{self._episode_idx:04d}_{name}.png"
            cv2.imwrite(str(path), image_arr)
            logger.info(f"[ScriptedJointAbsPolicy] saved observation image {name}: {path}")

        self._saved_observation_images = True

    def _log_reset_observation_once(self, observations):
        if self._logged_reset_observation:
            return
        states = (observations or {}).get("states", {})
        if not isinstance(states, dict):
            logger.warning("[ScriptedJointAbsPolicy] reset observation has no keyed states")
            self._logged_reset_observation = True
            return

        left = [float(v) for v in states.get("left_arm", [])]
        right = [float(v) for v in states.get("right_arm", [])]
        if len(left) == self._single_arm_dim and len(right) == self._single_arm_dim:
            diff = [round(l - r, 4) for l, r in zip(left, right)]
            logger.info(
                f"[ScriptedJointAbsPolicy] reset_obs_left={[round(v, 4) for v in left]} "
                f"reset_obs_right={[round(v, 4) for v in right]} left_minus_right={diff}"
            )
        else:
            logger.warning(
                f"[ScriptedJointAbsPolicy] reset observation arm dims unexpected: "
                f"left={len(left)} right={len(right)} expected={self._single_arm_dim}"
            )
        self._logged_reset_observation = True

    def act(self, observations, **kwargs):
        self._save_observation_images(observations)
        self._log_reset_observation_once(observations)

        if self.step_idx >= self.total_steps:
            logger.info(
                f"[ScriptedJointAbsPolicy] episode_idx={self._episode_idx} finished after {self.step_idx} steps"
            )
            return None

        stage_name, single_arm_offset, gripper_state = self._interpolated_stage()
        arm = self._arm_target(single_arm_offset)
        gripper = self._gripper_target(gripper_state)

        self.step_idx += 1
        if self.step_idx == 1 or self.step_idx % 30 == 0:
            preview = [round(v, 4) for v in arm[:4] + arm[7:11]]
            logger.info(
                f"[ScriptedJointAbsPolicy] episode_idx={self._episode_idx} step={self.step_idx} "
                f"stage={stage_name} kind=JOINT_ABS arm_preview={preview} gripper={gripper}"
            )

        return {"arm": arm, "gripper": gripper, "kind": "JOINT_ABS"}
