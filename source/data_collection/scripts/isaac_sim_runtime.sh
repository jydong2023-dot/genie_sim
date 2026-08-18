#!/bin/bash

# Shared runtime setup for Isaac Sim Python processes.

prepare_isaac_sim_ros_env() {
    export ISAACSIM_HOME="${ISAACSIM_HOME:-/isaac-sim}"
    export ROS_DISTRO="${ROS_DISTRO:-jazzy}"
    export RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_cyclonedds_cpp}"

    # Isaac Sim 5.1 uses Python 3.11. A sourced host ROS Jazzy environment can
    # leave Python 3.12 packages in PYTHONPATH, which breaks rclpy loading.
    _filter_non_isaac_ros_paths() {
        local value="${1:-}"
        local result=""
        local item
        local -a items

        IFS=':' read -r -a items <<< "$value"
        for item in "${items[@]}"; do
            [ -z "$item" ] && continue
            case "$item" in
                /opt/ros/*)
                    continue
                    ;;
            esac
            if [ -z "$result" ]; then
                result="$item"
            else
                result="${result}:$item"
            fi
        done
        printf '%s' "$result"
    }

    # Do not let a system ROS setup override the bridge bundled with Isaac Sim.
    export PYTHONPATH="$(_filter_non_isaac_ros_paths "${PYTHONPATH:-}")"
    export LD_LIBRARY_PATH="$(_filter_non_isaac_ros_paths "${LD_LIBRARY_PATH:-}")"
    unset AMENT_PREFIX_PATH COLCON_PREFIX_PATH CMAKE_PREFIX_PATH

    if [ -f "${ISAACSIM_HOME}/setup_ros_env.sh" ]; then
        # This script sets paths needed by Isaac Sim's bundled ROS bridge.
        # It is intentionally sourced after removing /opt/ros Python paths.
        source "${ISAACSIM_HOME}/setup_ros_env.sh" 2>/dev/null || true
        export PYTHONPATH="$(_filter_non_isaac_ros_paths "${PYTHONPATH:-}")"
        export LD_LIBRARY_PATH="$(_filter_non_isaac_ros_paths "${LD_LIBRARY_PATH:-}")"
    fi

    local bridge_lib="${ISAACSIM_HOME}/exts/isaacsim.ros2.bridge/${ROS_DISTRO}/lib"
    local bridge_rclpy="${ISAACSIM_HOME}/exts/isaacsim.ros2.bridge/${ROS_DISTRO}/rclpy"
    local internal_ros_lib="/${ROS_DISTRO}/lib"

    # Isaac Sim's startup message explicitly recommends /jazzy/lib for its
    # internal ROS libraries. Add it only when it exists in the image.
    if [ -d "$internal_ros_lib" ]; then
        export LD_LIBRARY_PATH="${internal_ros_lib}:${LD_LIBRARY_PATH:-}"
    fi
    if [ -d "$bridge_lib" ]; then
        export LD_LIBRARY_PATH="${bridge_lib}:${LD_LIBRARY_PATH:-}"
    fi
    if [ -d "$bridge_rclpy" ]; then
        export PYTHONPATH="${bridge_rclpy}:${PYTHONPATH:-}"
    fi
}

prepare_isaac_sim_cache() {
    local cache_dir
    for cache_dir in \
        "${ISAACSIM_HOME:-/isaac-sim}/.cache" \
        "${ISAACSIM_HOME:-/isaac-sim}/.nv/ComputeCache" \
        "${ISAACSIM_HOME:-/isaac-sim}/.nvidia-omniverse/logs" \
        "${ISAACSIM_HOME:-/isaac-sim}/.nvidia-omniverse/config" \
        "${ISAACSIM_HOME:-/isaac-sim}/.local/share/ov/data" \
        "${ISAACSIM_HOME:-/isaac-sim}/.local/share/ov/pkg" \
        "${ISAACSIM_HOME:-/isaac-sim}/kit/cache" \
        "${ISAACSIM_HOME:-/isaac-sim}/kit/cache/shadercache"; do
        sudo mkdir -p "$cache_dir" 2>/dev/null || true
        sudo setfacl -m u:"$(id -u)":rwX "$cache_dir" 2>/dev/null || true
        sudo chown "$(id -u):$(id -g)" "$cache_dir" 2>/dev/null || true
        sudo chmod u+rwX "$cache_dir" 2>/dev/null || true
    done
}

ensure_isaac_sim_python_package() {
    local import_name="$1"
    local package_spec="$2"
    local python_bin="${ISAACSIM_HOME:-/isaac-sim}/python.sh"

    if "$python_bin" -c "import ${import_name}" >/dev/null 2>&1; then
        return 0
    fi

    echo "Missing Isaac Sim Python package: ${package_spec}; installing it..."
    "$python_bin" -m pip install --no-cache-dir "$package_spec"
    "$python_bin" -c "import ${import_name}"
}

require_isaac_sim_python_package() {
    local import_name="$1"
    local package_name="$2"
    local import_check="${3:-import ${import_name}}"
    local python_bin="${ISAACSIM_HOME:-/isaac-sim}/python.sh"

    if "$python_bin" -c "$import_check" >/dev/null 2>&1; then
        return 0
    fi

    echo "ERROR: Isaac Sim Python cannot import ${package_name}."
    echo "Use the geniesim3-data-collection image, or build it from source/data_collection/dockerfile."
    echo "The base geniesim3 image does not contain the data-collection dependencies."
    return 1
}
