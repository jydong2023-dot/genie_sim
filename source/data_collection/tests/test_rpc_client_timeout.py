import ast
import importlib.util
import sys
import types
from pathlib import Path

import pytest


DATA_COLLECTION_ROOT = Path(__file__).parents[1]
CLIENT_PATH = DATA_COLLECTION_ROOT / "client" / "robot" / "client.py"
OMNI_ROBOT_PATH = DATA_COLLECTION_ROOT / "client" / "robot" / "omni_robot.py"


def load_rpc_client(monkeypatch, fake_grpc):
    logger = types.SimpleNamespace(error=lambda *args, **kwargs: None)
    package_names = [
        "common",
        "common.aimdk",
        "common.aimdk.protocol",
        "common.aimdk.protocol.hal",
        "common.aimdk.protocol.hal.arm",
        "common.aimdk.protocol.hal.joint",
        "common.aimdk.protocol.sim",
        "common.base_utils",
    ]
    for name in package_names:
        package = types.ModuleType(name)
        package.__path__ = []
        monkeypatch.setitem(sys.modules, name, package)

    for package_name, attributes in {
        "common.aimdk.protocol.hal.arm": ("arm_pb2", "arm_pb2_grpc"),
        "common.aimdk.protocol.hal.joint": (
            "joint_channel_pb2",
            "joint_channel_pb2_grpc",
        ),
        "common.aimdk.protocol.sim": (
            "sim_gripper_service_pb2",
            "sim_gripper_service_pb2_grpc",
            "sim_object_service_pb2",
            "sim_object_service_pb2_grpc",
            "sim_observation_service_pb2",
            "sim_observation_service_pb2_grpc",
        ),
    }.items():
        package = sys.modules[package_name]
        for attribute in attributes:
            setattr(package, attribute, types.ModuleType(attribute))

    logger_module = types.ModuleType("common.base_utils.logger")
    logger_module.logger = logger
    monkeypatch.setitem(sys.modules, "common.base_utils.logger", logger_module)
    monkeypatch.setitem(sys.modules, "grpc", fake_grpc)
    monkeypatch.setitem(sys.modules, "pinocchio", types.ModuleType("pinocchio"))

    module_name = "rpc_client_timeout_under_test"
    spec = importlib.util.spec_from_file_location(module_name, CLIENT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "find_urdf_in_robot_cfg", lambda name, root: f"/{name}")
    return module


def make_fake_grpc(outcomes):
    class FutureTimeoutError(Exception):
        pass

    class RpcError(Exception):
        pass

    channels = []
    ready_timeouts = []

    class FakeChannel:
        def __init__(self):
            self.close_calls = 0

        def close(self):
            self.close_calls += 1

    class FakeFuture:
        def result(self, timeout):
            ready_timeouts.append(timeout)
            outcome = outcomes.pop(0)
            if outcome is not None:
                raise outcome

    def insecure_channel(endpoint, options):
        channel = FakeChannel()
        channels.append((endpoint, options, channel))
        return channel

    grpc = types.SimpleNamespace(
        FutureTimeoutError=FutureTimeoutError,
        RpcError=RpcError,
        insecure_channel=insecure_channel,
        channel_ready_future=lambda channel: FakeFuture(),
        channels=channels,
        ready_timeouts=ready_timeouts,
    )
    return grpc


def test_connect_timeout_attempts_once_closes_channel_and_does_not_sleep(monkeypatch):
    fake_grpc = make_fake_grpc([])
    timeout_error = fake_grpc.FutureTimeoutError("not ready")
    fake_grpc_outcomes = [timeout_error]

    class FakeFuture:
        def result(self, timeout):
            fake_grpc.ready_timeouts.append(timeout)
            raise fake_grpc_outcomes.pop(0)

    fake_grpc.channel_ready_future = lambda channel: FakeFuture()
    module = load_rpc_client(monkeypatch, fake_grpc)
    monkeypatch.setattr(
        module.time,
        "sleep",
        lambda seconds: pytest.fail("bounded connection must not sleep"),
    )

    with pytest.raises(module.RpcConnectionError) as exc_info:
        module.RpcClient("localhost:50051", "robot.urdf", connect_timeout=0.25)

    assert exc_info.value.__cause__ is timeout_error
    assert len(fake_grpc.channels) == 1
    assert fake_grpc.ready_timeouts == [0.25]
    assert fake_grpc.channels[0][2].close_calls == 1


def test_default_connect_timeout_preserves_retry_behavior(monkeypatch):
    fake_grpc = make_fake_grpc([])
    outcomes = [fake_grpc.FutureTimeoutError("first"), None]

    class FakeFuture:
        def result(self, timeout):
            fake_grpc.ready_timeouts.append(timeout)
            outcome = outcomes.pop(0)
            if outcome is not None:
                raise outcome

    fake_grpc.channel_ready_future = lambda channel: FakeFuture()
    module = load_rpc_client(monkeypatch, fake_grpc)
    sleep_calls = []
    monkeypatch.setattr(module.time, "sleep", sleep_calls.append)

    client = module.RpcClient("localhost:50051", "robot.urdf")

    assert len(fake_grpc.channels) == 2
    assert fake_grpc.ready_timeouts == [5, 5]
    assert sleep_calls == [3]
    assert fake_grpc.channels[0][2].close_calls == 1
    assert fake_grpc.channels[1][2].close_calls == 0
    assert client.channel is fake_grpc.channels[1][2]
    assert client.robot_urdf == "robot.urdf"
    assert client.urdf_path == "/robot.urdf"


@pytest.mark.parametrize(
    "connect_timeout",
    [True, False, 0, -1, float("nan"), float("inf"), "1"],
)
def test_invalid_connect_timeout_fails_before_creating_channel(
    monkeypatch, connect_timeout
):
    fake_grpc = make_fake_grpc([])
    module = load_rpc_client(monkeypatch, fake_grpc)

    with pytest.raises(ValueError, match="finite positive real"):
        module.RpcClient(
            "localhost:50051", "robot.urdf", connect_timeout=connect_timeout
        )

    assert fake_grpc.channels == []


def test_default_connect_timeout_closes_every_channel_on_final_failure(monkeypatch):
    fake_grpc = make_fake_grpc([])
    final_error = fake_grpc.FutureTimeoutError("still unavailable")
    outcomes = [fake_grpc.FutureTimeoutError(str(i)) for i in range(599)] + [
        final_error
    ]

    class FakeFuture:
        def result(self, timeout):
            fake_grpc.ready_timeouts.append(timeout)
            raise outcomes.pop(0)

    fake_grpc.channel_ready_future = lambda channel: FakeFuture()
    module = load_rpc_client(monkeypatch, fake_grpc)
    sleep_calls = []
    monkeypatch.setattr(module.time, "sleep", sleep_calls.append)

    with pytest.raises(fake_grpc.FutureTimeoutError) as exc_info:
        module.RpcClient("localhost:50051", "robot.urdf")

    assert exc_info.value is final_error
    assert len(fake_grpc.channels) == 600
    assert all(channel.close_calls == 1 for _, _, channel in fake_grpc.channels)
    assert sleep_calls == [3] * 599


def load_omni_robot(monkeypatch, rpc_client_class):
    client_package = types.ModuleType("client")
    client_package.__path__ = []
    robot_package = types.ModuleType("client.robot")
    robot_package.__path__ = []
    robot_package.Robot = object
    rpc_module = types.ModuleType("client.robot.client")
    rpc_module.RpcClient = rpc_client_class

    common = types.ModuleType("common")
    common.__path__ = []
    base_utils = types.ModuleType("common.base_utils")
    base_utils.__path__ = []
    logger_module = types.ModuleType("common.base_utils.logger")
    logger_module.logger = types.SimpleNamespace()
    noise_module = types.ModuleType("common.base_utils.noise_utils")
    noise_module.add_noise_with_regex = lambda value, noise: value
    transform_module = types.ModuleType("common.base_utils.transform_utils")
    for name in (
        "euler2quat",
        "mat2euler",
        "mat2quat_wxyz",
        "quat2mat_wxyz",
        "quat_xyzw_to_wxyz",
    ):
        setattr(transform_module, name, lambda *args: None)

    scipy = types.ModuleType("scipy")
    scipy.__path__ = []
    spatial = types.ModuleType("scipy.spatial")
    spatial.__path__ = []
    scipy_transform = types.ModuleType("scipy.spatial.transform")
    scipy_transform.Rotation = object
    for name, module in {
        "client": client_package,
        "client.robot": robot_package,
        "client.robot.client": rpc_module,
        "common": common,
        "common.base_utils": base_utils,
        "common.base_utils.logger": logger_module,
        "common.base_utils.noise_utils": noise_module,
        "common.base_utils.transform_utils": transform_module,
        "scipy": scipy,
        "scipy.spatial": spatial,
        "scipy.spatial.transform": scipy_transform,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    spec = importlib.util.spec_from_file_location(
        "omni_robot_cleanup_under_test", OMNI_ROBOT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "init_error",
    [
        RuntimeError("rpc failed"),
        FileNotFoundError("missing scene"),
        KeyboardInterrupt(),
        SystemExit(2),
    ],
)
def test_omni_robot_closes_channel_when_init_robot_fails(monkeypatch, init_error):
    clients = []

    class FakeChannel:
        def __init__(self):
            self.close_calls = 0

        def close(self):
            self.close_calls += 1

    class FakeRpcClient:
        def __init__(self, *args, **kwargs):
            self.channel = FakeChannel()
            clients.append(self)

        def init_robot(self, **kwargs):
            raise init_error

    module = load_omni_robot(monkeypatch, FakeRpcClient)

    with pytest.raises(BaseException) as exc_info:
        module.IsaacSimRpcRobot()

    assert exc_info.value is init_error
    assert clients[0].channel.close_calls == 1


def test_omni_robot_passes_connect_timeout_to_rpc_client():
    tree = ast.parse(OMNI_ROBOT_PATH.read_text(encoding="utf-8"))
    constructor = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "__init__"
        and any(
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == "RpcClient"
            for child in ast.walk(node)
        )
    )
    rpc_call = next(
        child
        for child in ast.walk(constructor)
        if isinstance(child, ast.Call)
        and isinstance(child.func, ast.Name)
        and child.func.id == "RpcClient"
    )

    assert any(arg.arg == "connect_timeout" for arg in constructor.args.args)
    assert any(
        keyword.arg == "connect_timeout"
        and isinstance(keyword.value, ast.Name)
        and keyword.value.id == "connect_timeout"
        for keyword in rpc_call.keywords
    )
