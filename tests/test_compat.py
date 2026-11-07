"""跨项目兼容测试（走完整分层：PluginService → kernel → py 版插件）。

直接加载 PluginShell（py 版）的示例插件，源码一字不改。
若同级目录没有 PluginShell 项目，整组测试跳过并说明原因。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pluginshell.application.plugin_service import PluginService  # noqa: E402
from pluginshell.domain.models import PluginState  # noqa: E402
from pluginshell.infrastructure.paths import AppPaths  # noqa: E402
from pluginshell.infrastructure.runtime_factory import create_kernel  # noqa: E402

PY_SHELL = ROOT.parent / "PluginShell" / "sample_plugins"
A = "com.example.content_a"
B = "com.example.content_b"
C = "com.example.lab_coordinate"


@unittest.skipUnless(
    (PY_SHELL / A).is_dir(),
    f"未找到同级 PluginShell 示例插件（{PY_SHELL}），跳过跨项目兼容测试",
)
class PyPluginCompatibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.paths = AppPaths(
            resource_root=ROOT, exe_dir=self.base, data_dir=self.base / "data"
        )
        self.kernel = create_kernel(self.paths, self.base / "plugins")
        self.service = PluginService(self.kernel, auto_adopt=True)
        self.service.boot()

    def tearDown(self) -> None:
        self.service.shutdown()
        self.tmp.cleanup()

    def test_all_three_py_plugins_load_through_application_layer(self) -> None:
        for plugin_id in (A, B, C):
            result = self.service.install(PY_SHELL / plugin_id)
            self.assertTrue(result.ok, f"{plugin_id}: {result.message}")

        counts = self.service.counts()
        self.assertEqual(counts["installed"], 3)
        self.assertEqual(counts["enabled"], 3)
        self.assertEqual(counts["contributions"], 3)

        self.assertEqual([c.id for c in self.service.categories()], ["lesson", "tool", "lab"])
        self.assertEqual(
            [c.id for c in self.service.contributions()],
            [
                "com.example.content_a.panel",
                "com.example.content_b.panel",
                "com.example.lab_coordinate.panel",
            ],
        )
        self.assertIn("com.example.content_a.api", self.service.snapshot()["services"])
        self.assertTrue(all(item.state is PluginState.ENABLED for item in self.service.list_plugins()))

    def test_category_filter_uses_plugin_declared_metadata(self) -> None:
        for plugin_id in (A, B, C):
            self.service.install(PY_SHELL / plugin_id)
        self.assertEqual([c.title for c in self.service.contributions("lab")],
                         ["实验室 · 平面直角坐标系"])
        self.assertEqual([c.owner for c in self.service.contributions("tool")], [B])

    def test_py_plugins_collaborate(self) -> None:
        self.service.install(PY_SHELL / A)
        self.service.install(PY_SHELL / B)
        service_object = self.kernel.services.require("com.example.content_a.api")
        self.assertIs(self.kernel.records[B].instance.api, service_object)

        acks: list = []
        self.kernel.bus.subscribe("tool.sync_ack", lambda _e, payload: acks.append(payload))
        self.kernel.records[A].instance.publish_update()
        self.assertEqual(self.kernel.records[B].instance.received, 1)
        self.assertEqual(len(acks), 1)

        self.kernel.records[B].instance.request_refresh()
        self.assertEqual(service_object.last_refresh, {"requester": "B"})

    def test_missing_dependency_is_reported_as_failed_state(self) -> None:
        result = self.service.install(PY_SHELL / B)
        self.assertFalse(result.ok)
        self.assertIn("缺少依赖插件", result.message)
        failed = [item for item in self.service.list_plugins() if item.id == B][0]
        self.assertIs(failed.state, PluginState.FAILED)
        self.assertIn(A, failed.message)
        self.assertEqual(self.service.counts()["contributions"], 0)

    def test_uninstall_rolls_back_everything(self) -> None:
        for plugin_id in (A, B, C):
            self.service.install(PY_SHELL / plugin_id)
        for plugin_id in (B, C, A):
            result = self.service.uninstall(plugin_id)
            self.assertTrue(result.ok, result.message)

        self.assertEqual(self.service.list_plugins(), [])
        self.assertEqual(self.service.contributions(), [])
        self.assertEqual(self.service.categories(), [])
        self.assertEqual(self.service.snapshot()["services"], [])
        self.assertFalse(any(key.startswith("_pluginshell_") for key in sys.modules))

    def test_disable_blocked_by_dependent_returns_result_not_exception(self) -> None:
        self.service.install(PY_SHELL / A)
        self.service.install(PY_SHELL / B)
        result = self.service.disable(A)
        self.assertFalse(result.ok)
        self.assertIn(B, result.message)


class AutoAdoptTests(unittest.TestCase):
    """把插件目录直接拷进去（不调用 install）时，首次启动应自动采用。"""

    @unittest.skipUnless(PY_SHELL.is_dir(), "缺少 py 版示例插件")
    def test_first_boot_adopts_existing_plugins(self) -> None:
        import shutil

        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            plugins = base / "plugins"
            plugins.mkdir()
            for plugin_id in (A, B, C):
                shutil.copytree(PY_SHELL / plugin_id, plugins / plugin_id)

            paths = AppPaths(resource_root=ROOT, exe_dir=base, data_dir=base / "data")
            kernel = create_kernel(paths, plugins)
            service = PluginService(kernel, auto_adopt=True)
            service.boot()
            try:
                counts = service.counts()
                self.assertEqual(counts["installed"], 3)
                self.assertEqual(counts["enabled"], 3)
                self.assertEqual(counts["contributions"], 3)
            finally:
                service.shutdown()

            # 第二次启动必须尊重已有启用记录
            kernel2 = create_kernel(paths, plugins)
            service2 = PluginService(kernel2, auto_adopt=True)
            service2.boot()
            try:
                self.assertEqual(len(service2.snapshot()["enabled"]), 3)
            finally:
                service2.shutdown()


if __name__ == "__main__":
    unittest.main(verbosity=2)
