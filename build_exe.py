"""构建两个单文件产物，并做端到端验收。

    dist/PluginShellExe.exe            窗口版（主交付，带图标与版本信息）
    dist/PluginShellExe-console.exe    控制台版（同一程序，用于 --check / CLI / CI）

    python build_exe.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from pluginshell import APP_NAME, APP_VERSION

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
NAME = APP_NAME
CONSOLE_NAME = f"{NAME}-console"
ICON = ROOT / "assets" / "app.ico"
CONFIG_DIR = ROOT / "config"
PY_SHELL = ROOT.parent / "PluginShell" / "sample_plugins"
SAMPLES = ("com.example.content_a", "com.example.content_b", "com.example.lab_coordinate")

HIDDEN_IMPORTS = (
    "pluginshell",
    "pluginshell.bootstrap",
    "pluginshell.bootstrap.application",
    "pluginshell.application.plugin_service",
    "pluginshell.application.self_check",
    "pluginshell.presentation.main_window",
    "pluginshell.presentation.plugin_manager_dialog",
    "pluginshell.presentation.about_dialog",
    "pluginshell.presentation.theme",
    "kernel",
    "sdk",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtSvg",
)

VERSION_TEMPLATE = """VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(1, 0, 0, 0),
    prodvers=(1, 0, 0, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('CompanyName', 'ml-308'),
        StringStruct('FileDescription', 'PluginShellExe - native plugin host'),
        StringStruct('FileVersion', '1.0.0.0'),
        StringStruct('InternalName', '{name}'),
        StringStruct('LegalCopyright', 'MIT License, Copyright (c) 2026 ml-308'),
        StringStruct('OriginalFilename', '{name}.exe'),
        StringStruct('ProductName', 'PluginShellExe'),
        StringStruct('ProductVersion', '1.0.0.0')
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def clean_pycache() -> None:
    for path in ROOT.rglob("__pycache__"):
        shutil.rmtree(path, ignore_errors=True)


def write_version_file(target_name: str) -> Path:
    path = BUILD / f"version-{target_name}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(VERSION_TEMPLATE.format(name=target_name), encoding="utf-8")
    return path


def build(target_name: str, windowed: bool, clean: bool = False) -> Path:
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--name",
        target_name,
        "--distpath",
        str(DIST),
        "--workpath",
        str(BUILD),
        "--specpath",
        str(BUILD),
        "--icon",
        str(ICON),
        "--version-file",
        str(write_version_file(target_name)),
        "--add-data",
        f"{CONFIG_DIR};config",
        "--windowed" if windowed else "--console",
    ]
    if clean:
        command.insert(3, "--clean")
    for module in HIDDEN_IMPORTS:
        command += ["--hidden-import", module]
    command.append(str(ROOT / "app.py"))

    print(f"\n=== 构建 {target_name}（windowed={windowed}）===")
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        print((result.stdout + result.stderr).strip()[-2500:])
        raise SystemExit(f"BUILD_FAILED {target_name} rc={result.returncode}")
    exe = DIST / f"{target_name}.exe"
    if not exe.is_file():
        raise SystemExit(f"BUILD_FAILED {target_name}: exe 未生成")
    print(f"✓ {exe.name}  {exe.stat().st_size:,} bytes / {exe.stat().st_size / 1048576:.1f} MB")
    return exe


def _child_env() -> dict[str, str]:
    """给被测 exe 一个可控的工作环境。

    * TEMP/TMP：PyInstaller onefile 需要解包目录，受限环境默认 TEMP 不可创建子目录；
    * PLUGINSHELL_DATA_DIR：把日志/启用记录/自检报告隔离到工作区，既不依赖也不污染
      用户真实的 %LOCALAPPDATA%\\PluginShellExe。
    """
    runtime_temp = ROOT / ".tmp" / "pyi-runtime"
    data_dir = ROOT / ".tmp" / "verify-data"
    runtime_temp.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["TEMP"] = str(runtime_temp)
    env["TMP"] = str(runtime_temp)
    env["PLUGINSHELL_DATA_DIR"] = str(data_dir)
    return env


def verify(exe: Path) -> bool:
    with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temp:
        plugins = Path(temp) / "plugins"
        report = Path(temp) / "report.json"
        command = [str(exe), "--plugins", str(plugins), "--check", "--report", str(report)]
        expected = 0
        if PY_SHELL.is_dir():
            for plugin_id in SAMPLES:
                if (PY_SHELL / plugin_id).is_dir():
                    command += ["--install", str(PY_SHELL / plugin_id)]
                    expected += 1

        print(f"\n=== 验收 {exe.name}（预期加载 py 版插件 {expected} 个）===")
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
            env=_child_env(),
        )
        output = (result.stdout or "").strip()
        if output and "\ufffd" not in output:
            print(output)
        elif output:
            print("(子进程控制台输出按本地代码页编码，已省略；以下以 JSON 报告为准)")
        print("CHECK_RC", result.returncode)
        if not report.is_file():
            print("REPORT_MISSING —— exe 未能启动或自检中断")
            return False

        data = json.loads(report.read_text(encoding="utf-8"))
        print("frozen:", data["frozen"], "| python:", data["python"])
        print("qt:", data["qt"], "| gui:", {k: data["gui"].get(k) for k in ("ok", "groupboxes")})
        print(
            "installed:", data["installed"],
            "| contributions:", len(data["contributions"]),
            "| categories:", [item["id"] for item in data["categories"]],
        )
        ok = bool(data["frozen"]) and bool(data["qt"]["ok"]) and data["gui"]["ok"] is True
        ok = ok and data["installed"] == expected
        ok = ok and len(data["contributions"]) == expected
        if expected:
            ok = ok and data["gui"]["groupboxes"] == expected
            ok = ok and not data["failed"]
        else:
            ok = ok and data["gui"]["empty_state_visible"] is True
        print("VERIFY", "OK" if ok else "FAILED")
        return ok


def verify_adoption(exe: Path) -> bool:
    if not PY_SHELL.is_dir():
        print("\n=== 跳过采用策略验证（缺少 py 版示例插件）===")
        return True
    with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temp:
        plugins = Path(temp) / "plugins"
        plugins.mkdir()
        copied = 0
        for plugin_id in SAMPLES:
            source = PY_SHELL / plugin_id
            if source.is_dir():
                shutil.copytree(source, plugins / plugin_id)
                copied += 1
        report = Path(temp) / "adopt.json"
        command = [str(exe), "--plugins", str(plugins), "--check", "--report", str(report)]
        print(f"\n=== 采用策略验证：拷入 {copied} 个插件目录后首次运行（无启用记录）===")
        subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
            env=_child_env(),
        )
        if not report.is_file():
            print("REPORT_MISSING")
            return False
        data = json.loads(report.read_text(encoding="utf-8"))
        print(
            "installed:", data["installed"],
            "| enabled:", len(data["enabled"]),
            "| contributions:", len(data["contributions"]),
        )
        ok = (
            data["installed"] == copied
            and len(data["enabled"]) == copied
            and len(data["contributions"]) == copied
            and not data["failed"]
        )
        print("VERIFY_ADOPTION", "OK" if ok else "FAILED")
        return ok


def main() -> int:
    clean_pycache()
    (ROOT / ".tmp").mkdir(exist_ok=True)

    console_exe = build(CONSOLE_NAME, windowed=False, clean=True)
    console_ok = verify(console_exe)

    gui_exe = build(NAME, windowed=True, clean=False)
    gui_ok = verify(gui_exe)
    adopt_ok = verify_adoption(gui_exe)

    print("\n=== 产物 ===")
    for exe in (gui_exe, console_exe):
        size = exe.stat().st_size
        flag = "  ⚠ >100MB：作为 Release 资产分发" if size > 100 * 1048576 else ""
        print(f"  {exe}  {size / 1048576:.1f} MB{flag}")

    print(
        f"\nVERIFY  {NAME}.exe={'OK' if gui_ok else 'FAILED'}  "
        f"{CONSOLE_NAME}.exe={'OK' if console_ok else 'FAILED'}  "
        f"adoption={'OK' if adopt_ok else 'FAILED'}"
    )
    return 0 if (gui_ok and console_ok and adopt_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
