# Copyright (c) 2023-2026, AgiBot Inc. All Rights Reserved.
# Author: Genie Sim Team
# License: Mozilla Public License Version 2.0

import argparse
import os
import subprocess
import sys

root_directory = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_directory)


def _prepare_isaac_sim_ros_environment():
    """Keep system ROS Python 3.12 paths out of Isaac Sim Python 3.11."""

    ready_variable = "GENIESIM_ISAAC_ROS_ENV_READY"

    def filter_paths(value):
        return os.pathsep.join(
            path for path in (value or "").split(os.pathsep) if path and not path.startswith("/opt/ros/")
        )

    updated_env = os.environ.copy()
    updated_env["ROS_DISTRO"] = updated_env.get("ROS_DISTRO", "jazzy")
    updated_env["PYTHONPATH"] = filter_paths(updated_env.get("PYTHONPATH"))
    updated_env["LD_LIBRARY_PATH"] = filter_paths(updated_env.get("LD_LIBRARY_PATH"))
    for variable in ("AMENT_PREFIX_PATH", "COLCON_PREFIX_PATH", "CMAKE_PREFIX_PATH"):
        updated_env.pop(variable, None)

    isaacsim_home = updated_env.get("ISAACSIM_HOME", "/isaac-sim")
    distro = updated_env["ROS_DISTRO"]
    bridge_root = os.path.join(isaacsim_home, "exts", "isaacsim.ros2.bridge", distro)
    bridge_rclpy = os.path.join(bridge_root, "rclpy")
    bridge_lib = os.path.join(bridge_root, "lib")
    if os.path.isdir(bridge_rclpy):
        updated_env["PYTHONPATH"] = os.pathsep.join(
            path for path in (bridge_rclpy, updated_env.get("PYTHONPATH", "")) if path
        )

    library_paths = [bridge_lib]
    internal_ros_lib = os.path.join(os.path.sep, distro, "lib")
    if os.path.isdir(internal_ros_lib):
        library_paths.append(internal_ros_lib)
    library_paths.append(updated_env.get("LD_LIBRARY_PATH", ""))
    updated_env["LD_LIBRARY_PATH"] = os.pathsep.join(path for path in library_paths if path)

    if updated_env.get(ready_variable) != "1" and any(
        updated_env.get(key) != os.environ.get(key)
        for key in ("PYTHONPATH", "LD_LIBRARY_PATH", "ROS_DISTRO")
    ):
        updated_env[ready_variable] = "1"
        os.execvpe(sys.executable, [sys.executable, *sys.argv], updated_env)

    os.environ.clear()
    os.environ.update(updated_env)
    if os.path.isdir(bridge_rclpy) and bridge_rclpy not in sys.path:
        sys.path.insert(0, bridge_rclpy)


_prepare_isaac_sim_ros_environment()

from common.base_utils.isaac_numpy_runtime import reexec_with_isaacsim_numpy_libs

reexec_with_isaacsim_numpy_libs()

from common.base_utils.logger import logger

if os.path.exists(os.path.join(root_directory, "git_commit_info.txt")):
    with open(os.path.join(root_directory, "git_commit_info.txt"), "r") as f:
        logger.info("############GIT COMMIT INFO##########")
        logger.info(f.read())
        logger.info("############GIT COMMIT INFO##########")
else:
    logger.warning(f"git_commit_info.txt not found in {root_directory}")

parser = argparse.ArgumentParser()
parser.add_argument(
    "--headless",
    action="store_true",
    default=False,
)
parser.add_argument(
    "--debug",
    action="store_true",
    default=False,
)
parser.add_argument("--enable_physics", action="store_true", default=False)
parser.add_argument(
    "--enable_curobo",
    action="store_true",
    default=False,
)
parser.add_argument("--publish_ros", action="store_true", default=False)
parser.add_argument(
    "--physics_step",
    type=int,
    default=60,
)

args = parser.parse_args()


def _require_runtime_dependency(package_name, import_statement):
    result = subprocess.run(
        [sys.executable, "-c", import_statement],
        capture_output=True,
        env=os.environ,
        text=True,
    )
    if result.returncode == 0:
        return

    details = result.stderr.strip().splitlines()
    reason = details[-1] if details else "import failed"
    parser.error(
        f"Isaac Sim Python cannot import {package_name}: {reason}. "
        "Run data collection with registry.agibot.com/genie-sim/"
        "geniesim3-data-collection:latest."
    )


_require_runtime_dependency("ruckig", "import ruckig")
_require_runtime_dependency(
    "curobo",
    "from curobo.cuda_robot_model.cuda_robot_model import CudaRobotModel",
)

from isaacsim import SimulationApp

simulation_app = SimulationApp(
    {
        "headless": args.headless,
        "renderer": "RealTimePathTracing",
        "extra_args": [
            "--/persistent/rtx/modes/rt2/enabled=true",
        ],
    }
)
simulation_app._carb_settings.set("/physics/cooking/ujitsoCollisionCooking", False)
simulation_app._carb_settings.set("/omni/replicator/asyncRendering", False)
simulation_app._carb_settings.set("/app/asyncRendering", False)
from isaacsim.core.api import World
from isaacsim.core.utils import extensions

if args.publish_ros:
    extensions.enable_extension("isaacsim.ros2.bridge")
import omni

from server.command_controller import CommandController
from server.grpc_server import GrpcServer
from server.ui_builder import UIBuilder

physics_dt = (float)(1 / args.physics_step)
rendering_dt = (float)(1 / 30)
world = World(
    stage_units_in_meters=1,
    physics_dt=physics_dt,
    rendering_dt=rendering_dt,
    device="cpu",
)
physx_interface = omni.physx.get_physx_interface()
# Override CPU setting to use GPU
# physx_interface.overwrite_gpu_setting(1)

# world._physics_context.enable_gpu_dynamics(flag=True)
ui_builder = UIBuilder(world=world, debug=args.debug)
server_function = CommandController(
    ui_builder=ui_builder,
    enable_physics=args.enable_physics,
    enable_curobo=args.enable_curobo,
    publish_ros=args.publish_ros,
    rendering_step=int(1 / rendering_dt),
    debug=args.debug,
)
rpc_server = GrpcServer(server_function=server_function)
rpc_server.start()

step = 0
last_physics_time = 0
last_render_time = 0
while simulation_app.is_running():
    with rpc_server.server_function._timing_context("ui_builder.my_world.step"):
        ui_builder.my_world.step(render=False)
        current_time = ui_builder.my_world.current_time
        need_render = False
        if last_render_time == 0 or current_time - last_render_time >= rendering_dt:
            need_render = True
            last_render_time = current_time
        if need_render:
            ui_builder.my_world.render()
    if rpc_server:
        rpc_server.server_function.on_physics_step()
        if rpc_server.server_function.exit:
            break
    if not ui_builder.my_world.is_playing():
        if step % 100 == 0:
            logger.info("**** simulation paused ****")
        step += 1
        continue
rpc_server.server_function.print_timing_stats()
simulation_app.close()
