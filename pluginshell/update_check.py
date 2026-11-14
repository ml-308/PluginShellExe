"""update_check.py — 「发现新版本」检查与提示（本模块随程序分发）。

行为：
  * 启动后后台线程查 GitHub Releases 最新版，最多每 24 小时一次；
  * 只有比当前版本新才提示；用户可「跳过此版本」不再打扰；
  * 断网 / 代理 / 限流都只是「检查失败」，绝不阻塞主程序；
  * 命令行开关（诊断与自动化用）：
      --check-update         启动时立即检查（忽略 24h 与跳过记录）
      --no-update-check      本次启动不检查
      --update-feed <url>    覆盖检查地址（本地联调 / 镜像）
      --update-probe <path>  无人值守检查，把结果写成 JSON 后退出
"""

from __future__ import annotations

import json
import os
import sys
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

APP_NAME = "PluginShellExe"
APP_SLUG = "PluginShellExe"
APP_OWNER = "ml-308"
APP_REPO = "PluginShellExe"
CURRENT_VERSION = "1.2.0"

APP_URL = "https://github.com/" + APP_OWNER + "/" + APP_REPO
RELEASES_URL = APP_URL + "/releases"
LATEST_API = "https://api.github.com/repos/" + APP_OWNER + "/" + APP_REPO + "/releases/latest"

AUTO_ENABLED = True
FORCE_NOW = False
FEED_OVERRIDE = ""
CHECK_INTERVAL_HOURS = 24
DIALOG_DELAY_MS = 2200


# ---------------------------------------------------------------- 状态文件
def _state_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / APP_SLUG


def _state_file() -> Path:
    return _state_dir() / "update-state.txt"


def _read_state(key: str) -> str:
    try:
        path = _state_file()
        if not path.is_file():
            return ""
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith(key + "="):
                return line[len(key) + 1:].strip()
    except OSError:
        pass
    return ""


def _write_state(key: str, value: str) -> None:
    try:
        values = {
            "last_check_utc": _read_state("last_check_utc"),
            "skipped_version": _read_state("skipped_version"),
        }
        values[key] = value
        _state_dir().mkdir(parents=True, exist_ok=True)
        body = "".join(k + "=" + v + "\n" for k, v in values.items())
        _state_file().write_text(body, encoding="utf-8", newline="\n")
    except OSError:
        pass


def should_auto_check() -> bool:
    last = _read_state("last_check_utc")
    if not last:
        return True
    try:
        stamp = datetime.fromisoformat(last.replace("Z", "+00:00"))
    except ValueError:
        return True
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - stamp >= timedelta(hours=CHECK_INTERVAL_HOURS)


def skipped_version() -> str:
    return _read_state("skipped_version")


def skip_version(version: str) -> None:
    if version:
        _write_state("skipped_version", version)


def mark_checked() -> None:
    _write_state("last_check_utc", datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------- 版本号
def normalize(version: str) -> str:
    text = (version or "").strip()
    if text[:1] in ("v", "V"):
        text = text[1:]
    return text.split(" ")[0]


def _segment(text: str) -> int:
    digits = []
    for ch in text:
        if not ch.isdigit():
            break
        digits.append(ch)
    return int("".join(digits)) if digits else 0


def compare_version(a: str, b: str) -> int:
    parts_a = a.split(".")
    parts_b = b.split(".")
    for index in range(max(len(parts_a), len(parts_b))):
        left = _segment(parts_a[index]) if index < len(parts_a) else 0
        right = _segment(parts_b[index]) if index < len(parts_b) else 0
        if left != right:
            return 1 if left > right else -1
    return 0


# ---------------------------------------------------------------- 检查
def _feed_url() -> str:
    return FEED_OVERRIDE or LATEST_API


def check(timeout: float = 10.0) -> dict:
    info = {
        "ok": False,
        "error": "",
        "current": CURRENT_VERSION,
        "latest": "",
        "name": "",
        "url": "",
        "notes": "",
        "published": "",
        "has_update": False,
    }
    try:
        request = urllib.request.Request(
            _feed_url(),
            headers={
                "User-Agent": APP_SLUG + "/" + CURRENT_VERSION + " update-check",
                "Accept": "application/vnd.github+json",
            },
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8", "replace"))
        info["latest"] = normalize(str(body.get("tag_name") or ""))
        info["name"] = str(body.get("name") or "")
        info["url"] = str(body.get("html_url") or "")
        info["published"] = str(body.get("published_at") or "")
        info["notes"] = str(body.get("body") or "")
        if not info["latest"]:
            info["error"] = "响应中没有版本号"
        else:
            info["ok"] = True
            info["has_update"] = compare_version(info["latest"], normalize(CURRENT_VERSION)) > 0
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            info["error"] = "GitHub 接口限流（403），请稍后再试"
        elif exc.code == 404:
            info["error"] = "仓库没有可用的 Release（404）"
        else:
            info["error"] = "HTTP " + str(exc.code) + " " + str(exc.reason)
    except urllib.error.URLError as exc:
        info["error"] = "网络不可用：" + str(exc.reason)
    except TimeoutError:
        info["error"] = "连接超时，请检查网络"
    except json.JSONDecodeError:
        info["error"] = "响应不是合法 JSON"
    except Exception as exc:  # noqa: BLE001 - 检查更新失败绝不能影响主程序
        info["error"] = str(exc)
    mark_checked()
    return info


def check_async(callback) -> None:
    def worker() -> None:
        info = check()
        if callback is not None:
            try:
                callback(info)
            except Exception:  # noqa: BLE001
                pass

    threading.Thread(target=worker, name="update-check", daemon=True).start()


def open_releases() -> None:
    try:
        import webbrowser

        webbrowser.open(RELEASES_URL)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------- 命令行
def configure(argv=None) -> None:
    global AUTO_ENABLED, FORCE_NOW, FEED_OVERRIDE
    args = list(sys.argv if argv is None else argv)
    index = 0
    while index < len(args):
        raw = args[index] or ""
        low = raw.lower()
        if low == "--no-update-check":
            AUTO_ENABLED = False
        elif low == "--check-update":
            FORCE_NOW = True
        elif low.startswith("--update-feed="):
            FEED_OVERRIDE = raw.split("=", 1)[1]
        elif low == "--update-feed" and index + 1 < len(args):
            FEED_OVERRIDE = args[index + 1]
            index += 1
        index += 1


def try_probe(argv=None) -> int | None:
    args = list(sys.argv if argv is None else argv)
    for index, raw in enumerate(args):
        if (raw or "").lower() == "--update-probe":
            target = args[index + 1] if index + 1 < len(args) and args[index + 1] else ""
            if not target:
                target = str(Path(os.environ.get("TEMP", ".")) / (APP_SLUG + "-update-probe.json"))
            return run_probe(target)
    return None


def run_probe(path: str) -> int:
    info = check(timeout=15.0)
    report = {
        "app": APP_SLUG,
        "feed": _feed_url(),
        "current": CURRENT_VERSION,
        "latest": info["latest"],
        "hasUpdate": info["has_update"],
        "ok": info["ok"],
        "url": info["url"],
        "error": info["error"],
        "checkedAt": datetime.now(timezone.utc).isoformat(),
    }
    try:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass
    return 0 if info["ok"] else 1


# ---------------------------------------------------------------- UI（PySide6）
def _date_text(iso: str) -> str:
    if not iso:
        return ""
    try:
        stamp = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return stamp.astimezone().strftime("%Y-%m-%d")
    except ValueError:
        return ""


def _notes_text(notes: str) -> str:
    text = (notes or "").strip()
    if not text:
        return "（本版本未提供更新说明，详见 Release 页面。）"
    if len(text) > 2400:
        text = text[:2400] + "\n…"
    return text


def schedule_auto_check(parent) -> None:
    """窗口显示后延迟检查；发现新版本时弹窗（GUI 线程内调用）。"""
    if parent is None or not AUTO_ENABLED:
        return
    if not FORCE_NOW and not should_auto_check():
        return
    try:
        from PySide6.QtCore import QTimer
    except ImportError:
        return
    QTimer.singleShot(DIALOG_DELAY_MS, lambda: _run(parent, quiet=not FORCE_NOW))


def check_now(parent) -> None:
    """菜单「检查更新」：立刻检查，已是最新也给反馈。"""
    _run(parent, quiet=False)


def _run(parent, quiet: bool) -> None:
    try:
        from PySide6.QtCore import QObject, Signal
    except ImportError:
        return

    class _Bridge(QObject):
        done = Signal(object)

    bridge = _Bridge()

    def on_done(info) -> None:
        _handle(parent, info, quiet, bridge)

    bridge.done.connect(on_done)
    bridge_ref = bridge  # 保持引用直到回调完成

    def callback(info) -> None:
        try:
            bridge_ref.done.emit(info)
        except RuntimeError:
            pass

    check_async(callback)


def _handle(parent, info: dict, quiet: bool, bridge) -> None:
    try:
        from PySide6.QtWidgets import QMessageBox
    except ImportError:
        return
    try:
        if not info.get("ok"):
            if not quiet:
                QMessageBox.warning(
                    parent,
                    APP_NAME + " - 检查更新",
                    "暂时无法检查更新。\n\n" + (info.get("error") or "未知错误") +
                    "\n\n可以稍后在菜单里重试，或直接访问：\n" + RELEASES_URL,
                )
            return
        if not info.get("has_update"):
            if not quiet:
                QMessageBox.information(
                    parent,
                    APP_NAME + " - 检查更新",
                    "当前已是最新版本 v" + info.get("current", CURRENT_VERSION) + "。",
                )
            return
        if quiet and info.get("latest") == skipped_version():
            return
        dialog = UpdateDialog(parent, info)
        dialog.exec()
    except Exception:  # noqa: BLE001
        pass
    finally:
        if parent is not None:
            try:
                parent._update_bridge = bridge  # noqa: SLF001 - 防止桥对象被回收
            except AttributeError:
                pass


def build_dialog_class():
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QDialog,
        QHBoxLayout,
        QLabel,
        QPlainTextEdit,
        QPushButton,
        QVBoxLayout,
    )

    class UpdateDialog(QDialog):
        """发现新版本时的提示窗：立即下载 / 稍后提醒 / 跳过此版本。"""

        def __init__(self, parent, info: dict) -> None:
            super().__init__(parent)
            self._info = info
            self.setWindowTitle(APP_NAME + " - 发现新版本")
            self.setMinimumWidth(580)
            self.setStyleSheet(
                "QDialog{background:#ffffff;}"
                "QLabel{color:#1a1a1e;}"
                "QLabel#muted{color:#787a82;}"
                "QPlainTextEdit{background:#f7f8fa;border:1px solid #dee0e6;"
                "border-radius:6px;padding:8px;color:#1a1a1e;}"
                "QPushButton{min-height:34px;padding:0 14px;border-radius:6px;"
                "border:1px solid #d6d8de;background:#ffffff;color:#1a1a1e;}"
                "QPushButton:hover{background:#f2f4f7;}"
                "QPushButton#primary{border:none;background:#0a84ff;color:#ffffff;"
                "font-weight:600;}"
                "QPushButton#primary:hover{background:#0a76e6;}"
            )

            layout = QVBoxLayout(self)
            layout.setContentsMargins(26, 22, 26, 18)
            layout.setSpacing(8)

            title = QLabel("发现新版本 v" + info.get("latest", ""))
            title.setStyleSheet("font-size:20px;font-weight:600;")
            layout.addWidget(title)

            name = (info.get("name") or "").strip()
            subtitle = (
                "当前版本 v" + info.get("current", CURRENT_VERSION) +
                "  →  最新版本 v" + info.get("latest", "")
            )
            if name:
                subtitle += "\n" + name[:60]
            sub = QLabel(subtitle)
            sub.setObjectName("muted")
            sub.setWordWrap(True)
            layout.addWidget(sub)

            published = _date_text(info.get("published", ""))
            if published:
                date = QLabel("发布于 " + published + "  ·  " + APP_OWNER + "/" + APP_REPO)
                date.setObjectName("muted")
                date.setStyleSheet("font-size:11px;")
                layout.addWidget(date)

            notes_label = QLabel("更新内容")
            notes_label.setStyleSheet("font-weight:600;margin-top:12px;")
            layout.addWidget(notes_label)

            notes = QPlainTextEdit()
            notes.setPlainText(_notes_text(info.get("notes", "")))
            notes.setReadOnly(True)
            notes.setMinimumHeight(176)
            layout.addWidget(notes)

            buttons = QHBoxLayout()
            buttons.setSpacing(8)
            buttons.addStretch(1)

            skip = QPushButton("跳过此版本")
            skip.clicked.connect(self._on_skip)
            buttons.addWidget(skip)

            later = QPushButton("稍后提醒")
            later.clicked.connect(self.reject)
            buttons.addWidget(later)

            download = QPushButton("立即下载")
            download.setObjectName("primary")
            download.setDefault(True)
            download.clicked.connect(self._on_download)
            buttons.addWidget(download)

            layout.addLayout(buttons)
            self.resize(580, 460)
            self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        def _on_download(self) -> None:
            open_releases()
            self.accept()

        def _on_skip(self) -> None:
            skip_version(self._info.get("latest", ""))
            self.reject()

    return UpdateDialog


try:  # 有 PySide6 时提供 UpdateDialog 名字；纯控制台 / probe 场景不依赖 Qt
    UpdateDialog = build_dialog_class()
except Exception:  # noqa: BLE001
    UpdateDialog = None  # type: ignore[assignment]
