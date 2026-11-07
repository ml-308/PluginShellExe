"""应用层 / 基础设施层测试：不依赖 Qt，也不依赖外部项目。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pluginshell.application.plugin_service import PluginService  # noqa: E402
from pluginshell.domain.errors import ConfigError  # noqa: E402
from pluginshell.domain.models import PluginState  # noqa: E402
from pluginshell.infrastructure.config import AppConfig  # noqa: E402
from pluginshell.infrastructure.paths import AppPaths  # noqa: E402
from pluginshell.infrastructure.runtime_factory import create_kernel  # noqa: E402

PLUGIN_ID = "com.test.alpha"
PLUGIN_CODE = """
from sdk import Plugin, content_panel


class AlphaPlugin(Plugin):
    def activate(self, context):
        self.context = context
        context.services.register("com.test.alpha.api", self)
        context.extensions.contribute(
            "main.content",
            content_panel("com.test.alpha.panel", "Alpha", self._build, category="alpha"),
        )

    def _build(self, parent):
        from PySide6.QtWidgets import QWidget

        return QWidget(parent)
"""


class ConfigTests(unittest.TestCase):
    def test_defaults_and_overrides(self) -> None:
        config = AppConfig.from_mapping({"log_level": "debug", "window_width": 1200})
        self.assertEqual(config.log_level, "DEBUG")
        self.assertEqual(config.window_width, 1200)
        self.assertTrue(config.auto_adopt)

    def test_unknown_keys_are_ignored(self) -> None:
        config = AppConfig.from_mapping({"future_key": 1})
        self.assertEqual(config.window_width, 1000)

    def test_invalid_values_raise(self) -> None:
        with self.assertRaises(ConfigError):
            AppConfig.from_mapping({"log_level": "TRACE"})
        with self.assertRaises(ConfigError):
            AppConfig.from_mapping({"window_width": "wide"})
        with self.assertRaises(ConfigError):
            AppConfig.from_mapping({"auto_adopt": "yes"})

    def test_user_config_overrides_bundled(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            bundled = base / "config" / "default.json"
            bundled.parent.mkdir(parents=True)
            bundled.write_text(json.dumps({"window_width": 1100}), encoding="utf-8")
            data_dir = base / "data"
            data_dir.mkdir()
            (data_dir / "config.json").write_text(
                json.dumps({"window_width": 1300}), encoding="utf-8"
            )
            paths = AppPaths(resource_root=base, exe_dir=base, data_dir=data_dir)
            self.assertEqual(AppConfig.load(paths).window_width, 1300)


class PathsTests(unittest.TestCase):
    def test_explicit_override_wins(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            target = base / "custom"
            paths = AppPaths(resource_root=base, exe_dir=base / "exe", data_dir=base / "data")
            directory, source = paths.resolve_plugins_dir(str(target))
            self.assertEqual(directory, target.resolve())
            self.assertIn("--plugins", source)

    def test_side_by_side_plugins_preferred(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            exe_dir = base / "exe"
            plugins = exe_dir / "plugins"
            (plugins / "com.demo.x").mkdir(parents=True)
            (plugins / "com.demo.x" / "manifest.json").write_text("{}", encoding="utf-8")
            paths = AppPaths(resource_root=base, exe_dir=exe_dir, data_dir=base / "data")
            directory, source = paths.resolve_plugins_dir(None)
            self.assertEqual(directory, plugins)
            self.assertIn("exe 同级", source)


class PluginServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.paths = AppPaths(resource_root=ROOT, exe_dir=self.base, data_dir=self.base / "data")
        self.kernel = create_kernel(self.paths, self.base / "plugins")
        self.service = PluginService(self.kernel, auto_adopt=True)
        self.service.boot()
        self.source = self._write_plugin()

    def tearDown(self) -> None:
        self.service.shutdown()
        self.tmp.cleanup()

    def _write_plugin(self) -> Path:
        directory = self.base / "src" / PLUGIN_ID
        directory.mkdir(parents=True)
        (directory / "manifest.json").write_text(
            json.dumps(
                {
                    "id": PLUGIN_ID,
                    "name": "Alpha",
                    "version": "1.0.0",
                    "api": "1.0",
                    "entry": "plugin.py",
                    "class": "AlphaPlugin",
                    "category": {"id": "alpha", "label": "Alpha 分类", "order": 5},
                    "provides_services": ["com.test.alpha.api"],
                    "contributes": {"main.content": [{"id": "com.test.alpha.panel"}]},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (directory / "plugin.py").write_text(PLUGIN_CODE, encoding="utf-8")
        return directory

    def test_empty_shell_returns_empty_views(self) -> None:
        self.assertEqual(self.service.list_plugins(), [])
        self.assertEqual(self.service.contributions(), [])
        self.assertEqual(self.service.categories(), [])
        self.assertEqual(self.service.counts()["installed"], 0)

    def test_install_returns_dto_views(self) -> None:
        result = self.service.install(self.source)
        self.assertTrue(result.ok, result.message)

        plugins = self.service.list_plugins()
        self.assertEqual(len(plugins), 1)
        self.assertEqual(plugins[0].state, PluginState.ENABLED)
        self.assertEqual(plugins[0].category_label, "Alpha 分类")

        categories = self.service.categories()
        self.assertEqual([(c.id, c.count) for c in categories], [("alpha", 1)])

        contributions = self.service.contributions()
        self.assertEqual([c.id for c in contributions], ["com.test.alpha.panel"])
        self.assertTrue(callable(contributions[0].factory))

    def test_disable_and_uninstall_return_results(self) -> None:
        self.service.install(self.source)
        self.assertTrue(self.service.disable(PLUGIN_ID).ok)
        self.assertEqual(self.service.contributions(), [])
        self.assertEqual(
            self.service.list_plugins()[0].state, PluginState.DISABLED
        )
        self.assertTrue(self.service.uninstall(PLUGIN_ID).ok)
        self.assertEqual(self.service.list_plugins(), [])

    def test_invalid_operations_are_reported_not_raised(self) -> None:
        result = self.service.enable("com.test.missing")
        self.assertFalse(result.ok)
        self.assertIn("未安装", result.message)
        result = self.service.install(self.base / "src" / "nope")
        self.assertFalse(result.ok)


if __name__ == "__main__":
    unittest.main(verbosity=2)
