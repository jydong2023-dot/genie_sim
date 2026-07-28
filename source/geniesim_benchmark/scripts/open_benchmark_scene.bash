#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../../.." && pwd)"
CONTAINER_NAME="${GENIESIM_CONTAINER:-geniesim3}"
CONTAINER_SCRIPT="/workspace/source/geniesim_benchmark/scripts/open_benchmark_scene.bash"
CONTAINER_PYTHON="/isaac-sim/python.sh"

has_arg() {
    local needle="$1"
    shift
    local arg
    for arg in "$@"; do
        [[ "${arg}" == "${needle}" ]] && return 0
    done
    return 1
}

add_isaacsim_numpy_libs() {
    local dir existing
    local -a new_paths=()
    for dir in /isaac-sim/extscache/omni.kit.pip_archive-*/pip_prebundle/numpy.libs \
        /isaac-sim/kit/python/lib/python*/site-packages/numpy.libs; do
        [[ -d "${dir}" ]] || continue
        [[ ":${LD_LIBRARY_PATH:-}:" == *":${dir}:"* ]] && continue
        for existing in "${new_paths[@]}"; do
            [[ "${existing}" == "${dir}" ]] && continue 2
        done
        new_paths+=("${dir}")
    done

    if ((${#new_paths[@]})); then
        local IFS=:
        if [[ -n "${LD_LIBRARY_PATH:-}" ]]; then
            export LD_LIBRARY_PATH="${new_paths[*]}:${LD_LIBRARY_PATH}"
        else
            export LD_LIBRARY_PATH="${new_paths[*]}"
        fi
        export GENIESIM_NUMPY_LIBS_READY=1
    fi
}

export GENIESIM_REPO_ROOT="${GENIESIM_REPO_ROOT:-${REPO_ROOT}}"
export SIM_REPO_ROOT="${SIM_REPO_ROOT:-${REPO_ROOT}}"
export GENIESIM_ASSETS_PATH="${GENIESIM_ASSETS_PATH:-${REPO_ROOT}/../geniesim_assets}"

LOCAL_PYTHONPATH="${REPO_ROOT}/source/geniesim_benchmark/src:${REPO_ROOT}/source/geniesim_cli/src:${REPO_ROOT}/source/scene_augmentation/src:${REPO_ROOT}/.."
if [[ -n "${PYTHONPATH:-}" ]]; then
    export PYTHONPATH="${LOCAL_PYTHONPATH}:${PYTHONPATH}"
else
    export PYTHONPATH="${LOCAL_PYTHONPATH}"
fi

if [[ "${GENIESIM_IN_CONTAINER:-0}" == "1" || -x "${CONTAINER_PYTHON}" ]]; then
    export GENIESIM_REPO_ROOT="${GENIESIM_REPO_ROOT:-/workspace}"
    export SIM_REPO_ROOT="${SIM_REPO_ROOT:-/workspace}"
    export GENIESIM_ASSETS_PATH="${GENIESIM_ASSETS_PATH:-/geniesim_assets}"
    add_isaacsim_numpy_libs
    exec "${CONTAINER_PYTHON}" "${SCRIPT_DIR}/open_benchmark_scene.py" "$@"
fi

if has_arg "--dry-run" "$@" || has_arg "--help" "$@" || has_arg "-h" "$@"; then
    exec python3 "${SCRIPT_DIR}/open_benchmark_scene.py" "$@"
fi

if command -v docker >/dev/null 2>&1; then
    state="$(docker inspect -f '{{.State.Status}}' "${CONTAINER_NAME}" 2>/dev/null || true)"
    if [[ "${state}" == "running" ]]; then
        exec docker exec -it \
            -u "$(id -u):$(id -g)" \
            -e "HOME=/home/isaac-sim" \
            -e "GENIESIM_REPO_ROOT=/workspace" \
            -e "SIM_REPO_ROOT=/workspace" \
            -e "GENIESIM_ASSETS_PATH=/geniesim_assets" \
            -w "/workspace" \
            "${CONTAINER_NAME}" \
            "${CONTAINER_SCRIPT}" "$@"
    fi
fi

cat >&2 <<EOF
GenieSim Isaac Sim container '${CONTAINER_NAME}' is not running.

Start and enter the container, then run:

  cd /home/user/djy/genie_sim
  geniesim docker up
  geniesim docker into
  /workspace/source/geniesim_benchmark/scripts/open_benchmark_scene.bash "$@"

This viewer intentionally does not use the host Isaac Sim 4.5 install.
EOF
exit 1
