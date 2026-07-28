import builtins
import importlib.util
from pathlib import Path


def test_logger_imports_without_colorama(monkeypatch):
    logger_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "geniesim_benchmark"
        / "plugins"
        / "logger"
        / "logger.py"
    )
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "colorama":
            raise ModuleNotFoundError("No module named 'colorama'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    spec = importlib.util.spec_from_file_location("logger_without_colorama", logger_path)
    module = importlib.util.module_from_spec(spec)

    spec.loader.exec_module(module)

    module.logger.info("plain logger fallback works")
    assert module.Fore.RED == ""
    assert module.Style.RESET_ALL == ""
