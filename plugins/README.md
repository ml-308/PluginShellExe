# 插件目录

本宿主扫描此目录下的一级子目录，每个子目录必须是「文件夹 + `manifest.json`」，
且目录名等于清单里的 `id`。

初始为空 —— 这正是"未安装插件时显示「请安装插件」"的验收状态。

## 与 py 版共享插件

`PluginShellExe.exe` 按以下优先级选择插件目录，因此**可以直接使用 PluginShell
（py 版）已经装好的插件，无需重新安装**：

1. `--plugins <目录>` 参数
2. `PLUGINSHELL_PLUGINS` 环境变量
3. exe 同级的 `plugins/`（便携模式，且其中确实有插件）
4. `%LOCALAPPDATA%\PluginShell\plugins` ← py 版安装/安装包默认位置
5. exe 同级 `plugins/` 或 `%LOCALAPPDATA%\PluginShellExe\plugins`（默认安装目标）

用 `tools/plugin_cli.py path` 或界面状态栏可以确认当前实际使用的目录。
插件代码不需要任何改动：同一份 `manifest.json` + `plugin.py` 在两个宿主上行为一致。
