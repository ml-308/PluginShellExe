; PluginShellExe · 安装程序（Inno Setup 6）
; 页面结构与选项由 common.iss 统一提供；这里只声明应用身份与要安装的文件。
; 构建：installer\build-setup.cmd   产物：dist\PluginShellExe-Setup-1.2.0.exe
;
; 前置：先跑 python build_exe.py，产出 dist\PluginShellExe.exe

#define AppName "PluginShellExe"
#define AppSlug "PluginShellExe"
#define DirName "PluginShellExe"
#define AppVersion "1.2.0"
#define AppId "{{5CAE3F47-8DB6-4B5C-C034-6EB19D7CAF58}"
#define AppExe "PluginShellExe.exe"
#define AppRepo "PluginShellExe"
#define AppTagline "单文件插件宿主：目标机不需要 Python 运行时，插件协议与 py 版完全一致。"
#define IconPath "assets\app.ico"

#include "common.iss"

[Files]
Source: "{#AppRoot}\dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#AppRoot}\README.md"; DestDir: "{app}"
Source: "{#AppRoot}\LICENSE"; DestDir: "{app}"
Source: "{#AppRoot}\plugins\README.md"; DestDir: "{app}\plugins"

[Dirs]
; 即使不放插件也先建好目录，首次启动是「空壳」而不是报错
Name: "{app}\plugins"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: startmenuicon
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: desktopicon
