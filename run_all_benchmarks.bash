#!/usr/bin/env bash

set -uo pipefail

trap 'echo "Benchmark batch interrupted." >&2; exit 130' INT TERM

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
WORKSPACE_ROOT="${WORKSPACE_ROOT:-/workspace}"
POLICY_ENDPOINT="${POLICY_ENDPOINT:-localhost:8999}"
NUM_EPISODES="${NUM_EPISODES:-1}"
NUM_INSTANCES="${NUM_INSTANCES:-1}"

if [[ "${EUID}" -eq 0 ]]; then
    exec /usr/sbin/runuser -u isaac-sim -- /usr/bin/env \
        WORKSPACE_ROOT="${WORKSPACE_ROOT}" \
        POLICY_ENDPOINT="${POLICY_ENDPOINT}" \
        NUM_EPISODES="${NUM_EPISODES}" \
        NUM_INSTANCES="${NUM_INSTANCES}" \
        "${SCRIPT_PATH}"
fi

if [[ "${EUID}" -ne 1000 ]]; then
    echo "Error: run this script as root or as the isaac-sim user (UID 1000)." >&2
    exit 2
fi

cd "${WORKSPACE_ROOT}" || {
    echo "Error: workspace does not exist: ${WORKSPACE_ROOT}" >&2
    exit 2
}

export LD_LIBRARY_PATH="/isaac-sim/kit/python/lib/python3.11/site-packages/numpy.libs${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"

batch_status=0

for robot in g1op g2op; do
    echo "===== Running all ${robot} benchmark tasks ====="

    if ! /isaac-sim/python.sh /isaac-sim/kit/python/bin/geniesim benchmark batch \
        --robot="${robot}" \
        --infer-host="${POLICY_ENDPOINT}" \
        --app.headless=true \
        --benchmark.num_episode="${NUM_EPISODES}" \
        --benchmark.num_instances="${NUM_INSTANCES}" \
        --benchmark.enable_vec=0 \
        --benchmark.record=true; then
        batch_status=1
    fi
done

exit "${batch_status}"
