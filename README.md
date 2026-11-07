# PluginShellExe · 单文件 exe 插件宿主

> **公开仓库**：https://github.com/ml-308/PluginShellExe
> **下载 exe**：https://github.com/ml-308/PluginShellExe/releases/latest
> **开源许可**：[MIT](LICENSE) · Copyright (c) 2026 ml-308

[PluginShell](../PluginShell) 的**可执行（exe）版本**：把同一套微内核插件架构打进一个
单文件 Windows 程序 —— 目标机器**不需要安装 Python、不需要 pip、不需要任何运行时**，
双击 `PluginShellExe.exe` 即可运行。

关键点：**插件协议与 py 版完全一致**。同一份「文件夹 + `manifest.json` + `plugin.py`」
插件，不改一行代码，既能在 `python run.py` 里用，也能在 `PluginShellExe.exe` 里用 ——
连插件目录都可以直接共用。

技术栈仍是 **Python 3.10+ / PySide6（Qt 原生 QWidget）**，由 PyInstaller 冻结成单文件 exe。
**全程无 Web 技术**：没有 HTML/CSS/JS、没有 WebView、没有浏览器、没有 Electron。

---

## 1. 与 py 版的兼容性

| 兼容项 | 状态 |
| --- | --- |
| 插件协议版本 `api` | **1.0**，与 PluginShell 完全一致 |
| `manifest.json` 全部字段（id/version/依赖/分类/扩展点/服务/事件） | ✅ 完全一致 |
| `sdk.Plugin` / `sdk.content_panel` | ✅ 同一份实现 |
| `PluginContext`（`events` / `services` / `extensions`） | ✅ 同一套语义与声明校验 |
| `main.content` 贡献契约（`id/title/factory/category/order`） | ✅ 完全一致 |
| 依赖拓扑、反向依赖阻止、副作用逆序回滚 | ✅ 同一套内核实现 |
| 已有插件是否需要改代码 | **不需要** |
| 插件目录能否共用 | ✅ 自动复用 `%LOCALAPPDATA%\PluginShell\plugins` |

> 结论：**插件层面零迁移成本**。exe 只是换了个宿主外壳，插件生态不变。

唯一的现实边界见 [第 6 节](#6-兼容性边界)：插件若用到非常规 Qt 子模块（例如
`QtMultimedia`），需要把该模块加进 `build_exe.py` 的 `HIDDEN_IMPORTS` 重新打包；
示例的三个插件（Widgets/Gui/Core + QPainter）都已完整支持。

---

## 2. 快速开始

### 2.1 直接用 exe

每次构建产出两个**同一份代码**的单文件程序（约 36 MB / 个）：

| 产物 | 子系统 | 用途 |
| --- | --- | --- |
| `dist/PluginShellExe.exe` | 窗口 | **主交付**，双击即用，无控制台窗口 |
| `dist/PluginShellExe-console.exe` | 控制台 | 同一程序的孪生体：便于 `--check` 读输出、脚本/CI 调用、排查问题 |

```text
双击 PluginShellExe.exe        → 空壳窗口（未装插件时只显示「请安装插件」）
PluginShellExe-console.exe --check --report r.json    → 打印自检摘要并写报告
```

自动化用法（两个产物参数完全一致）：

```bat
PluginShellExe.exe --plugins D:\my\plugins            指定插件目录
PluginShellExe.exe --install D:\my\plugins\foo        先安装再启动（可重复）
PluginShellExe.exe --check --report report.json       无界面自检，写 JSON 报告后退出
PluginShellExe.exe --version
```

> 把插件文件夹**直接拷进** `plugins/` 也可以：首次运行发现目录里有插件但没有启用记录时，
> 宿主会自动采用（按依赖拓扑逐个启用）。之后禁用了哪个插件，都会被记住，不会复活。

### 2.2 从源码运行（开发/调试）

```bash
pip install -r requirements.txt
python app.py
python tools/plugin_cli.py list
```

### 2.3 构建 exe

```bash
pip install -r requirements.txt -r requirements-build.txt
python build_exe.py
# → dist/PluginShellExe.exe，并自动做端到端验收
```

`build_exe.py` 不是"编译完就算"：它会启动打包好的 exe，用 `--check` 在**离屏模式**下
真正创建窗口、安装 `PluginShell/sample_plugins` 的三个插件，断言内容面板数量、
分类数量、Qt 版本、冻结标记，然后才判定成功。

---

## 安装（可选）

只想双击 exe 用，跳过本节即可。要装进系统（开始菜单 / 卸载项 / 快捷方式），用安装包：

**PluginShellExe-Setup-1.1.0.exe** —— Inno Setup 6 构建的向导式安装包，页面顺序固定：

> 欢迎 → 许可协议（MIT）→ 安装位置 → 附加任务 → 准备安装 → 安装进度 → 完成

界面为简体中文，系统语言非中文时自动切 English。

* 默认装到 `%LOCALAPPDATA%\Programs\PluginShellExe`，路径可改，**不需要管理员权限**
* 附加任务：创建桌面快捷方式、创建开始菜单快捷方式
* 完成页可勾选「立即运行」；卸载走「设置 → 应用 → 已安装的应用」或安装目录下的 `unins000.exe`
* 插件目录 `plugins\` 会预先建好，首次启动就是可用的空壳

静默安装 / 卸载（脚本分发用）：

```bat
PluginShellExe-Setup-1.1.0.exe /VERYSILENT /SUPPRESSMSGBOXES /TASKS="desktopicon,startmenuicon"
"%LOCALAPPDATA%\Programs\PluginShellExe\unins000.exe" /VERYSILENT
```

---

## 3. 插件目录解析优先级

| 顺序 | 来源 | 说明 |
| --- | --- | --- |
| 1 | `--plugins <dir>` | 显式指定，优先级最高 |
| 2 | `PLUGINSHELL_PLUGINS` 环境变量 | 便于脚本/便携部署 |
| 3 | `exe 同级 plugins/` | 便携模式；**目录里确实有插件**时才采用 |
| 4 | `%LOCALAPPDATA%\PluginShell\plugins` | **复用 py 版已安装的插件** |
| 5 | `exe 同级 plugins/` 或 `%LOCALAPPDATA%\PluginShellExe\plugins` | 默认安装目标（自动创建） |

用 `PluginShellExe.exe --check`、`python tools/plugin_cli.py path` 或界面状态栏
可以随时确认当前实际使用的目录与来源。

**采用策略**：如果目录里有插件、却没有宿主的启用记录（`.exe-state.json`），
首次运行会把它们按依赖拓扑**自动启用** —— 这正是「把 py 版插件目录搬过来即刻可用」的机制；
一旦有了启用记录，就严格按记录恢复，用户手动禁用的插件不会被自动复活。

---

## 4. 架构

```
┌──────────────── 单文件 PluginShellExe.exe（PyInstaller onefile）───────────────┐
│  内置 CPython 运行时 + PySide6-Essentials（QtCore/QtGui/QtWidgets）           │
│                                                                              │
│  ┌────────────────────── 原生 UI（QWidget，无 Web）──────────────────────┐  │
│  │ 分类导航（来自插件清单） │ main.content 主内容区（插件 factory 产出的     │  │
│  │ 全部 / lesson / tool … │ QWidget，装在 QGroupBox 里）                  │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                    │                                        │
│  ┌──────────────── 微内核 kernel/（纯 Python，零 Qt）──────────────────┐   │
│  │ Kernel: discover / install / enable / disable / uninstall           │   │
│  │   ├─ resolver   依赖拓扑 + 版本约束 + 循环检测                       │   │
│  │   ├─ loader     importlib 隔离装载，卸载时清 sys.modules/sys.path     │   │
│  │   ├─ EventBus / ServiceContainer / ExtensionRegistry                 │   │
│  │   └─ PluginContext  声明校验 + 撤销账本（逆序回滚）                  │   │
│  └──────────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                │ 同一套协议 1.0，无特权通道
             ┌──────────────────┼───────────────────┐
             ▼                  ▼                   ▼
      PluginShell(py 版)   任意第三方             本 exe 安装的
      sample_plugins/*     插件文件夹             同一批插件
      （源码不改，直接可用）
```

插件目录在 exe 外部，**不打进 exe**：因此装插件不需要重新打包，
和 py 版一样是「文件夹 + manifest → 安装 → 立即生效」。

---

## 5. 目录结构

```
PluginShellExe/
├── app.py                    入口：路径解析 / --check 自检 / GUI 启动 / 崩溃日志
├── kernel/                   微内核（与 PluginShell core/ 同一套语义）
│   ├── errors.py manifest.py resolver.py bus.py services.py
│   └── registry.py context.py loader.py kernel.py
├── sdk/                      插件 SDK（api = "1.0"，与 py 版一致）
├── ui/
│   ├── main_window.py        空状态 + 分类导航 + main.content 渲染
│   └── plugin_manager.py     列出 / 安装 / 启用 / 禁用 / 卸载
├── plugins/                  运行时插件目录（初始空）
├── tests/
│   ├── test_kernel.py        内核行为（不依赖 Qt / 不依赖外部项目）
│   └── test_compat.py        跨项目兼容：直接加载 py 版示例插件
├── tools/plugin_cli.py       无 GUI 插件管理
├── build_exe.py              PyInstaller 打包 + 端到端验收
├── requirements.txt          运行时（PySide6-Essentials）
└── requirements-build.txt    构建（pyinstaller）
```

---

## 6. 兼容性边界

1. **Qt 子模块**：exe 只打包 `QtCore / QtGui / QtWidgets / QtSvg`。插件若 import
   `QtMultimedia`、`QtCharts`、`QtWebEngine` 等未打包模块会 ImportError（被内核隔离，
   不会拖垮宿主）。需要时把它们加进 `build_exe.py` 的 `HIDDEN_IMPORTS` 重新打包。
2. **纯 Python 依赖**：插件若依赖第三方 PyPI 包，该包也需一起打包（`--hidden-import` /
   `--collect-all`）。只用标准库 + PySide6 的插件无需任何处理。
3. **原生扩展（.pyd）**：插件自带的二进制扩展不会被 PyInstaller 自动收集，需显式配置。
4. **Python 版本**：exe 内固定为打包时的 CPython（当前 3.13）。插件语法需与之兼容。
5. **不打包插件**：`plugins/` 永远在 exe 外部，安装/卸载插件不需要重新构建 exe。

这些是"把 Python 应用冻结成单文件"的固有约束，不是插件协议差异 —— 协议层面 100% 兼容。

---

## 7. 测试与验收

```bash
python -m unittest discover -s tests -v      # 内核 + 跨项目兼容
python build_exe.py                          # 打包 + 对 exe 做端到端验收
```

覆盖：

| 测试 | 内容 |
| --- | --- |
| `test_kernel.py` | 空壳、安装出内容、事件/服务协作、依赖缺失拒绝、声明强制、加载失败隔离、禁用/卸载回滚、`describe()` 快照、依赖解析（缺失/循环/拓扑） |
| `test_compat.py` | 直接安装 `../PluginShell/sample_plugins` 的 A/B/C：三个插件全部加载、3 个内容贡献、分类 `lesson/tool/lab`、服务注入、事件双向协作、自定义扩展点、卸载后完全回滚 |
| `build_exe.py` 验收 | **两个 exe 各跑一遍**：`frozen=True`、Qt 6.12 已内置、离屏 GUI 创建成功、安装 3 个 py 插件后 `groupboxes == 3` 且分类为 `lesson/tool/lab`、服务已注册 |
| `build_exe.py` 采用策略 | 把 3 个插件目录**直接拷进** `plugins/`（不调用安装接口、无启用记录）→ 首次运行自动启用 3 个、内容贡献 3 个 |

`--check` 报告示例（节选）：

```json
{
  "app": "PluginShellExe",
  "version": "1.0.0",
  "protocol": "1.0",
  "frozen": true,
  "qt": { "ok": true, "version": "6.12.0" },
  "gui": { "ok": true, "groupboxes": 3, "empty_state_visible": false },
  "plugins_source": "复用 PluginShell(py 版)插件目录",
  "installed": 3,
  "enabled": ["com.example.content_a", "com.example.content_b", "com.example.lab_coordinate"],
  "categories": [
    { "id": "lesson", "label": "知识点讲解", "order": 10 },
    { "id": "tool", "label": "工具", "order": 20 },
    { "id": "lab", "label": "实验室", "order": 30 }
  ],
  "contributions": [ "…3 项…" ],
  "services": ["com.example.content_a.api"]
}
```

---

## 8. 常见问题

- **双击没反应**：先跑 `PluginShellExe-console.exe --check --report r.json`，看报告里的
  `qt` / `gui` / `failed`；崩溃栈在 `%LOCALAPPDATA%\PluginShellExe\logs\crash.log`。
- **报 `Could not create temporary directory!`**：PyInstaller onefile 需要在 `TEMP` 下解包，
  受限环境（某些沙箱/服务账户）会禁止创建子目录。把 `TEMP`/`TMP` 指向可写目录再运行即可：`set TEMP=D:\temp && PluginShellExe.exe`。
- **空的？** 说明当前插件目录没有插件。用「插件管理 → 安装文件夹…」或在界面点
  「打开插件目录」把插件放进去；也可以 `--plugins` 指向 py 版的 `plugins`。
- **想和 py 版共用插件**：什么都不用做 —— 只要 `%LOCALAPPDATA%\PluginShell\plugins`
  里有插件，exe 会自动复用它。
- **杀毒软件误报**：PyInstaller onefile 的常见现象，未签名 exe 尤其容易触发。
  可改用 `--onedir` 打包，或对 exe 做代码签名。
- **exe 有多大**：取决于内置 Qt 模块，通常在数十 MB 量级；因此 exe 作为 Release
  资产分发，不放进 git 仓库。

---

## 9. 开源许可

MIT License，见 [LICENSE](LICENSE)。Copyright (c) 2026 ml-308。
第三方插件是独立作品，其许可由插件作者自行声明。
