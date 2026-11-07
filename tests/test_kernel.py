"""内核行为测试：不依赖 Qt，也不依赖同级 PluginShell 项目。

覆盖：空壳、安装出内容、事件/服务协作、依赖缺失、声明强制、故障隔离、
禁用/卸载回滚、依赖解析。
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kernel import Kernel  # noqa: E402
from kernel.errors import DependencyError  # noqa: E402
from kernel.manifest import parse_manifest  # noqa: E402
from kernel.resolver import resolve_load_order  # noqa: E402

ALPHA = "com.test.alpha"
BETA = "com.test.beta"

ALPHA_CODE = """
from sdk import Plugin, content_panel


class AlphaPlugin(Plugin):
    def activate(self, context):
        self.context = context
        self.hits = 0
        context.services.register("com.test.alpha.api", self)
        context.events.subscribe("alpha.ping", self._on_ping)
        context.extensions.contribute(
            "main.content",
            content_panel("com.test.alpha.panel", "Alpha", self._build, category="alpha", order=10),
        )

    def _on_ping(self, event, payload):
        self.hits += 1
        self.context.events.publish("alpha.pong", {"hits": self.hits})

    def topic(self):
        return "alpha-service"

    def _build(self, parent):
        from PySide6.QtWidgets import QLabel, QWidget

        widget = QWidget(parent)
        QLabel("alpha", widget)
        return widget
"""

BETA_CODE = """
from sdk import Plugin, content_panel


class BetaPlugin(Plugin):
    def activate(self, context):
        self.context = context
        self.received = 0
        self.api = context.services.require("com.test.alpha.api")
        context.events.subscribe("alpha.pong", self._on_pong)
        context.extensions.contribute(
            "main.content",
            content_panel("com.test.beta.panel", "Beta", self._build, category="beta", order=20),
        )

    def _on_pong(self, event, payload):
        self.received += 1

    def _build(self, parent):
        from PySide6.QtWidgets import QWidget

        return QWidget(parent)
"""


class KernelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.plugins_dir = self.root / "plugins"
        self.kernel = Kernel(plugins_dir=self.plugins_dir, project_root=ROOT, state_path=None)
        self.kernel.bootstrap()
        self._write(
            ALPHA,
            {"contributes": {"main.content": [{"id": "com.test.alpha.panel"}]}},
            ALPHA_CODE,
            class_name="AlphaPlugin",
            category={"id": "alpha", "label": "Alpha", "order": 10},
            provides=["com.test.alpha.api"],
            subscribes=["alpha.ping"],
            publishes=["alpha.pong"],
        )
        self._write(
            BETA,
            {"contributes": {"main.content": [{"id": "com.test.beta.panel"}]}},
            BETA_CODE,
            class_name="BetaPlugin",
            category={"id": "beta", "label": "Beta", "order": 20},
            depends={ALPHA: ">=1.0.0"},
            requires=["com.test.alpha.api"],
            subscribes=["alpha.pong"],
        )

    def tearDown(self) -> None:
        self.kernel.shutdown()
        self.tmp.cleanup()

    # ------------------------------------------------------------------
    def _write(self, plugin_id: str, extra: dict, code: str, class_name: str = "AlphaPlugin",
               category: dict | None = None, depends=None, requires=None,
               provides=None, subscribes=None, publishes=None) -> Path:
        directory = self.root / "src" / plugin_id
        directory.mkdir(parents=True, exist_ok=True)
        manifest = {
            "id": plugin_id,
            "name": plugin_id,
            "version": "1.0.0",
            "api": "1.0",
            "entry": "plugin.py",
            "class": class_name,
            "dependencies": depends or {},
            "requires_services": requires or [],
            "provides_services": provides or [],
            "subscribes": subscribes or [],
            "publishes": publishes or [],
        }
        if category:
            manifest["category"] = category
        manifest.update(extra)
        (directory / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (directory / "plugin.py").write_text(code, encoding="utf-8")
        return directory

    def _source(self, plugin_id: str) -> Path:
        return self.root / "src" / plugin_id

    # ------------------------------------------------------------------
    def test_empty_shell(self) -> None:
        self.assertEqual(self.kernel.records, {})
        self.assertEqual(self.kernel.extensions.contributions("main.content"), ())
        self.assertEqual(self.kernel.services.names(), ())
        self.assertEqual(self.kernel.bus.handler_count(), 0)
        self.assertEqual(self.kernel.extensions.points(), ("main.content",))

    def test_install_shows_content_and_service(self) -> None:
        result = self.kernel.install(self._source(ALPHA))
        self.assertTrue(result.ok, result.message)
        contributions = self.kernel.extensions.contributions("main.content")
        self.assertEqual([c.payload["id"] for c in contributions], ["com.test.alpha.panel"])
        self.assertIn("com.test.alpha.api", self.kernel.services.names())
        self.assertEqual(self.kernel.bus.handler_count("alpha.ping"), 1)
        self.assertEqual({c.id for c in self.kernel.categories()}, {"alpha"})

    def test_event_bus_roundtrip(self) -> None:
        self.kernel.install(self._source(ALPHA))
        pong = []
        self.kernel.bus.subscribe("alpha.pong", lambda _e, payload: pong.append(payload))
        self.kernel.bus.publish("alpha.ping", {"n": 1})
        self.assertEqual(pong, [{"hits": 1}])
        self.assertEqual(self.kernel.records[ALPHA].instance.hits, 1)

    def test_beta_depends_on_alpha(self) -> None:
        self.assertTrue(self.kernel.install(self._source(ALPHA)).ok)
        self.assertTrue(self.kernel.install(self._source(BETA)).ok)
        self.assertEqual(len(self.kernel.extensions.contributions("main.content")), 2)
        self.assertEqual({c.id for c in self.kernel.categories()}, {"alpha", "beta"})
        beta = self.kernel.records[BETA].instance
        self.assertIs(beta.api, self.kernel.records[ALPHA].instance)
        self.kernel.records[ALPHA].instance.context.events.publish("alpha.pong", {})
        self.assertTrue(beta.received >= 1)

    def test_beta_without_alpha_is_refused(self) -> None:
        result = self.kernel.install(self._source(BETA))
        self.assertFalse(result.ok)
        self.assertIn("缺少依赖插件", result.message)
        self.assertEqual(self.kernel.records[BETA].state, "failed")
        self.assertEqual(self.kernel.extensions.contributions("main.content"), ())

    def test_disable_blocked_by_dependent_then_rolls_back(self) -> None:
        self.kernel.install(self._source(ALPHA))
        self.kernel.install(self._source(BETA))
        with self.assertRaises(DependencyError) as ctx:
            self.kernel.disable(ALPHA)
        self.assertIn(BETA, str(ctx.exception))

        self.kernel.disable(BETA)
        self.kernel.disable(ALPHA)
        self.assertEqual(self.kernel.extensions.contributions("main.content"), ())
        self.assertEqual(self.kernel.services.names(), ())
        self.assertEqual(self.kernel.bus.handler_count(), 0)
        self.assertFalse(any(key.startswith("_pluginshell_") for key in sys.modules))

    def test_uninstall_restores_empty(self) -> None:
        self.kernel.install(self._source(ALPHA))
        self.kernel.uninstall(ALPHA)
        self.assertEqual(self.kernel.records, {})
        self.assertEqual(list(self.plugins_dir.iterdir()), [])

    def test_uninstall_blocked_by_installed_dependent(self) -> None:
        self.kernel.install(self._source(ALPHA))
        self.kernel.install(self._source(BETA))
        with self.assertRaises(DependencyError) as ctx:
            self.kernel.uninstall(ALPHA)
        self.assertIn(BETA, str(ctx.exception))
        self.kernel.uninstall(BETA)
        self.kernel.uninstall(ALPHA)
        self.assertEqual(self.kernel.records, {})

    def test_declaration_enforced(self) -> None:
        bad = self._write(
            "com.test.undeclared",
            {},
            "from sdk import Plugin\n"
            "class AlphaPlugin(Plugin):\n"
            "    def activate(self, context):\n"
            "        context.events.subscribe('secret.event', lambda e, p: None)\n",
        )
        result = self.kernel.install(bad)
        self.assertFalse(result.ok)
        self.assertIn("未在 manifest.subscribes 声明", result.message)
        self.assertEqual(self.kernel.bus.handler_count("secret.event"), 0)

    def test_load_failure_isolated(self) -> None:
        bad = self._write(
            "com.test.boom",
            {},
            "from sdk import Plugin\n"
            "class AlphaPlugin(Plugin):\n"
            "    def activate(self, context):\n"
            "        raise RuntimeError('boom')\n",
        )
        self.assertFalse(self.kernel.install(bad).ok)
        self.assertEqual(self.kernel.records["com.test.boom"].state, "failed")
        self.assertTrue(self.kernel.install(self._source(ALPHA)).ok)

    def test_describe_snapshot(self) -> None:
        self.kernel.install(self._source(ALPHA))
        snapshot = self.kernel.describe()
        self.assertEqual(snapshot["installed"], 1)
        self.assertEqual(snapshot["enabled"], [ALPHA])
        self.assertEqual(snapshot["contributions"][0]["id"], "com.test.alpha.panel")
        self.assertEqual(snapshot["event_handlers"], {"alpha.ping": 1})
        json.dumps(snapshot)  # 必须可序列化

    def test_resolver(self) -> None:
        def manifest(pid: str, deps: dict):
            return parse_manifest(
                {
                    "id": pid,
                    "name": pid,
                    "version": "1.0.0",
                    "api": "1.0",
                    "entry": "plugin.py",
                    "class": "X",
                    "dependencies": deps,
                }
            )

        with self.assertRaises(DependencyError):
            resolve_load_order({"a"}, {"a": manifest("a", {"b": "*"})})
        with self.assertRaises(DependencyError) as ctx:
            resolve_load_order(
                {"a"}, {"a": manifest("a", {"b": "*"}), "b": manifest("b", {"a": "*"})}
            )
        self.assertIn("循环依赖", str(ctx.exception))
        order = resolve_load_order(
            {"c"},
            {"a": manifest("a", {}), "b": manifest("b", {"a": "*"}), "c": manifest("c", {"b": "*"})},
        )
        self.assertEqual(order, ["a", "b", "c"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
