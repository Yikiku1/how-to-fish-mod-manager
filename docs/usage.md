# 渔力全开 Mod 管理器

双击最新版 `HowToFishModManager-v1.2.exe` 即可运行，无需安装 Python、Steam 或 Overwolf。源码在 `manager.py`。

## v1.2 中文 Mod 列表

- 为当前目录中的 240 个 Mod 提供中文参考名称与简要介绍，依据作者简介整理；不代表游戏内界面汉化。
- 在线页搜索框旁点击“切换英文 / English”，显示网站原始名称和简介；再点“切换中文 / 中文”返回中文。其他软件按钮保持中文。
- 中文模式和英文模式都支持中文译名、英文包名、作者与简介搜索。切换时保留在线列表选中项，不改变实际安装包及其依赖。
- 选中 Mod 后，下方详情区显示完整简介及原始包标识；已安装列表和安装确认清单也使用对应语言的名称。
- 翻译已内嵌在 EXE 中。旁边的 `zh_CN.json` 是可编辑词典，存在时优先读取，修改后重启生效。新增包没有译文时显示原始信息；作者更新简介后会标记中文待更新。

v1.1 使用系统 curl 下载，失败后尝试 PowerShell，兼容系统代理，并对 PowerShell 5.1 显式启用 TLS 1.2；调用外部程序时清除打包器的 DLL 搜索目录影响。失败时显示网站、curl 错误码和 PowerShell 异常类型。不会关闭证书检查。

v1.1 的打包 EXE 已在仅保留 Windows 系统工具的 PATH 下测试在线目录刷新，读取到 240 个包；另已通过 curl 失败后切换 PowerShell、全部失败时保留诊断码的测试。原 v1.0 截图中的网络失败未能稳定复现，尚不能确定其具体根因。

## 第一次使用

1. 关闭游戏，点击“选择游戏 EXE”，选择游戏本体，而非启动器。旁边应有同名的 `*_Data` 文件夹。
2. 打开“在线 Mod”，点击“刷新在线列表”。
3. 搜索 `HowToFishDevConsole`，选择 `NekoTeam-HowToFishDevConsole`。
4. 点击“下载并安装（含依赖）”，核对清单。首次安装会包含 `BepInEx-BepInExPack`。
5. 下载和安装结束后点击“直接启动游戏”。本工具直接运行你选择的 EXE。
6. 进入游戏后按 F1 或 ~，输入 `help` 检查控制台。生成物品的指令由该 Mod 提供，本工具不内置河豚鳍 ID。

也可以在本地页手动导入 BepInExPack ZIP 和 Mod ZIP。无需先解压。

## 安装行为

- 本版支持 Mono Unity 的 BepInExPack 和包含 DLL 的 BepInEx 插件；IL2CPP 及复杂安装包不自动处理。
- 插件分别放在 `BepInEx/plugins/HTFMM_<id>`。停用时移至游戏目录内 `.htf-mod-manager/disabled`；卸载只删除本工具管理的插件文件。
- 不自动接管原有插件，也不自动卸载依赖。请勿停用其他 Mod 所需的依赖。
- 同名插件不自动覆盖。要更新，请关闭游戏、卸载旧版后安装新版。
- 加载器覆盖前的原文件备份在 `.htf-mod-manager/loader-backup`，变更清单记录在 `state.json` 的 `loader` 字段。当前没有一键移除加载器按钮；需要还原时，按清单恢复有备份的文件，并移除清单中标记为原本不存在的文件。不要直接删除整个 BepInEx 目录。
- 在线安装先下载所有包再逐个安装。后续插件安装失败时，前面安装成功的依赖保留，可在本地页查看。
- 压缩包不允许路径穿越、链接、重复路径和超过 150 MB 的解压数据。
- 当前无后台更新、开机启动、账号和遥测。

## 在线源接口与其他网站

当前已经实现且验证的是 **Thunderstore 的 How to Fish 社区**。`ThunderstoreSource` 将网站访问与本地安装分开：

```python
class AnotherSource:
    name = '网站显示名称'
    def catalog(self):
        # 返回规范化的包列表（下述结构）
        ...
    def plan(self, selected, catalog):
        # 返回按依赖优先顺序排列的 (package, version) 列表
        ...
```

包结构使用 Thunderstore 的公开 JSON 形式：

```json
{
  "name": "Example",
  "full_name": "Author-Example",
  "package_url": "https://example.com/mod",
  "versions": [{
    "full_name": "Author-Example-1.0.0",
    "version_number": "1.0.0",
    "description": "说明",
    "dependencies": [],
    "download_url": "https://example.com/mod.zip"
  }]
}
```

新增来源时实现 `catalog()` 和 `plan()`，并替换 `App.source`；UI 使用相同结构。本版尚未提供来源切换界面，也未接入 Nexus Mods 等其他站点。网站需提供真实、可授权使用的下载接口；需要 API Key 或登录的网站要另加认证处理，不能只改域名。非 BepInEx 格式仍需新增对应安装策略。

## 验证范围

已验证安装/停用/启用/卸载、持久化记录、重复安装保护、ZIP 路径保护、加载器备份及失败回滚、GUI 创建和事件循环。已请求真实 Thunderstore 目录并检查控制台的指定版本依赖。实际下载、安装的测试结论见随附验证记录。

尚未在你的游戏副本中运行；游戏版本、加载器以及插件的实际兼容性需要选择游戏目录后验证。

## 从源码运行与打包

源码仅使用 Python 标准库，需要带 Tk 的 Python 3.11 或以上。运行 `python manager.py`。

打包：`python -m pip install pyinstaller`，然后在源码目录执行 `python -m PyInstaller --onefile --windowed --add-data "zh_CN.json;." --name HowToFishModManager-v1.2 manager.py`。
