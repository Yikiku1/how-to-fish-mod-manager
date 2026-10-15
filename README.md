# 渔力全开 Mod 管理器

面向 Windows 的《渔力全开》（How to Fish）BepInEx Mod 管理工具。支持选择本地游戏 EXE、直接启动游戏、从 Thunderstore 下载插件及依赖，以及离线导入 ZIP。无需通过 Steam 启动，无需 Overwolf。

## 下载与使用

到本仓库 **Releases** 下载 `HowToFishModManager-v1.2.exe`，双击运行。

1. 关闭游戏，在管理器中选择游戏本体 EXE；旁边应有同名 `*_Data` 文件夹。
2. 打开“在线 Mod”，点击“刷新在线列表”，搜索需要的插件。
3. 点击“下载并安装（含依赖）”，确认安装清单。
4. 点击“直接启动游戏”。也可在本地页导入 Mod ZIP 或 BepInExPack ZIP。

在线列表默认显示中文参考译名和简介。搜索框旁点击“切换英文 / English”查看网站原文，再点击返回中文。中英文搜索均可用，选中项下方显示完整简介及原始包标识。

## 功能

- Thunderstore 的 How to Fish 社区目录、搜索、依赖解析与下载。
- 本地 BepInExPack 和 BepInEx 插件 ZIP 安装。
- 插件启用、停用和卸载；加载器覆盖前备份原文件。
- 240 个 Mod 的中文名称与简介；切换语言不改变实际包标识或依赖。
- 系统 curl 下载，失败时尝试 PowerShell；兼容系统代理，失败时显示诊断码。
- 不包含后台更新、开机启动、账号系统或遥测。

## 支持范围

当前自动安装策略支持 **Windows Mono Unity / BepInEx 5**。IL2CPP、MelonLoader、ReShade、地图制作项目及复杂安装包不能按普通 BepInEx 插件自动安装。在线目录包含这些项目，选择前请阅读作者说明。

本工具不修改游戏认证或启动器。直接启动是运行所选 EXE；游戏本身若要求其他运行组件，仍需满足其要求。

只管理本工具安装的插件，不自动接管原有插件。更新同名插件前需要卸载旧版；不自动判断停用依赖对其他插件的影响。目前只有 Thunderstore 已接入，其他网站仅预留代码接口。

翻译依据作者简介整理，是参考译名，不是游戏内汉化。作者更新简介后会标记中文待更新，新包没有译文时显示原文。

## 源码运行

需要 Windows、带 Tk 的 Python 3.11+。应用源码仅使用 Python 标准库。

```powershell
python manager.py
```

`zh_CN.json` 与源码放在同一目录。发布版 EXE 已内嵌词典，也支持在 EXE 旁放置同名 JSON 覆盖词典，修改后重启生效。

## 构建与验证

```powershell
python -m pip install -r requirements-dev.txt
pwsh -File ./build.ps1
python -m unittest discover -s tests -v
```

EXE 输出至 `dist/`。构建目录与 EXE 不提交到 Git，通过 GitHub Releases 分发。

网络自检会访问真实 Thunderstore，并将结果写入指定 JSON 文件：

```powershell
python manager.py --network-check network-check.json
```

已验证：ZIP 路径保护、插件安装与启停及卸载、加载器备份和安装失败回滚、实际 Tk 界面中英文搜索与切换、备用下载、真实目录读取和隔离下载安装。尚未验证所有游戏版本与所有第三方插件的运行兼容性。

详细行为与备份恢复方法见 [使用说明](docs/usage.md)，验证范围见 [验证记录](docs/verification.md)。

## 来源与归属

Mod 目录及下载来自 [Thunderstore How to Fish 社区](https://thunderstore.io/c/how-to-fish/)。游戏和第三方 Mod 归各自作者所有；本仓库不包含游戏资源、第三方 Mod DLL 或存档。在线源适配器位于 `manager.py` 的 `ThunderstoreSource`。
