import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def top_level_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_command_controller_does_not_import_rclpy_at_module_load_time():
    imports = top_level_imports(ROOT / "server" / "command_controller.py")

    assert "rclpy" not in imports
    assert "common.base_utils.ros_nodes.server_node" not in imports


def test_ros_publisher_helpers_defer_python_ros_node_imports():
    base_imports = top_level_imports(ROOT / "server" / "ros_publisher" / "base.py")
    camera_imports = top_level_imports(ROOT / "server" / "ros_publisher" / "camera.py")

    assert "common.base_utils.ros_nodes.sim_ros_node" not in base_imports
    assert "common.base_utils.ros_nodes.sim_ros_node" not in camera_imports
