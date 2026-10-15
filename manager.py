"""How to Fish Mod Manager. Python 3.11+, Windows, standard library only."""
from __future__ import annotations
import base64
import json
import os
from pathlib import Path, PurePosixPath
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import uuid
import webbrowser
import zipfile
from urllib.parse import urlsplit
from urllib.request import urlopen, Request, getproxies

CATALOG = 'https://thunderstore.io/c/how-to-fish/api/v1/package/'
LIMIT = 150 * 1024 * 1024
META = {'manifest.json', 'readme.md', 'icon.png', 'changelog.md', 'license', 'license.txt', 'license.md'}

def load_translations():
    bundled = Path(__file__).with_name('zh_CN.json')
    external = Path(sys.executable).with_name('zh_CN.json') if getattr(sys, 'frozen', False) else bundled
    try:
        data = json.loads((external if external.is_file() else bundled).read_text('utf-8-sig'))
        return {k: v for k, v in data.items() if isinstance(v, dict) and isinstance(v.get('name'), str) and isinstance(v.get('description'), str)}
    except (OSError, ValueError, AttributeError):
        return {}

TRANSLATIONS = load_translations()

def mod_text(package, chinese=True):
    version = package['versions'][0]
    translation = TRANSLATIONS.get(package['full_name'])
    original = version.get('description', '')
    if chinese and translation:
        description = translation['description']
        if translation.get('source_description') != original:
            description = '作者简介已更新，中文待更新。原文：' + original
        return translation['name'] + ' / ' + package.get('owner', package['full_name'].split('-', 1)[0]), description
    return package['full_name'], ('暂无中文翻译。原文：' if chinese else '') + original

def external_run(args, timeout=45):
    """Avoid passing PyInstaller's DLL search directory to external tools."""
    previous = None
    if os.name == 'nt' and getattr(sys, 'frozen', False):
        import ctypes
        buf = ctypes.create_unicode_buffer(32768)
        ctypes.windll.kernel32.GetDllDirectoryW(len(buf), buf)
        previous = buf.value
        ctypes.windll.kernel32.SetDllDirectoryW(None)
    try:
        return subprocess.run(args, capture_output=True, timeout=timeout,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    finally:
        if previous is not None:
            ctypes.windll.kernel32.SetDllDirectoryW(previous or None)

def download_windows(url, dest):
    failures = []
    curl = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'curl.exe'
    if curl.is_file():
        args = [str(curl), '--location', '--fail', '--silent', '--show-error',
                '--connect-timeout', '8', '--max-time', '30', '--max-filesize', str(LIMIT),
                '--proto', '=https', '--proto-redir', '=https', '--output', str(dest)]
        proxy = getproxies().get('https') or getproxies().get('http')
        if proxy:
            args += ['--proxy', proxy if '://' in proxy else 'http://' + proxy]
        try:
            proc = external_run(args + [url], 35)
            if proc.returncode == 0:
                if dest.stat().st_size > LIMIT: raise ValueError('下载超过大小限制')
                return dest.read_bytes()
            # curl's standard error can contain local paths or proxy credentials;
            # report only its numeric diagnostic code to the UI.
            codes = re.findall(r'curl: \((\d+)\)', proc.stderr.decode('utf-8', errors='replace'))
            failures.append('curl 错误码 ' + (codes[-1] if codes else str(proc.returncode)))
        except (OSError, subprocess.TimeoutExpired) as e:
            failures.append('curl ' + type(e).__name__)
    esc = lambda s: str(s).replace("'", "''")
    script = ("$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; "
              "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
              "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; "
              "try { "
              f"Invoke-WebRequest -UseBasicParsing -Uri '{esc(url)}' -OutFile '{esc(dest)}' -TimeoutSec 30; "
              f"if ((Get-Item -LiteralPath '{esc(dest)}').Length -gt {LIMIT}) {{ throw 'Download too large' }} "
              "} catch { [Console]::Out.WriteLine($_.Exception.GetType().Name); exit 1 }")
    encoded = base64.b64encode(script.encode('utf-16le')).decode()
    shells = [shutil.which('pwsh'), str(Path(os.environ.get('SystemRoot', r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe')]
    for shell in dict.fromkeys(s for s in shells if s and Path(s).is_file()):
        try:
            proc = external_run([shell, '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded], 35)
            if proc.returncode == 0:
                return dest.read_bytes()
            reason = proc.stdout.decode('utf-8-sig', errors='replace').strip()
            reason = reason if re.fullmatch(r'[A-Za-z]+Exception', reason) else '请求失败'
            failures.append(Path(shell).name + ': ' + reason)
        except (OSError, subprocess.TimeoutExpired) as e:
            failures.append(Path(shell).name + ': ' + type(e).__name__)
    hints = {'5': '无法解析代理地址', '6': '无法解析网站域名', '7': '连接被拒绝或无法连接',
             '22': '服务器返回 HTTP 错误', '28': '连接或下载超时', '35': 'TLS 握手失败',
             '60': '证书验证失败', '56': '连接中断'}
    hint = next((value for code, value in hints.items() if 'curl 错误码 '+code in failures), '所有下载方式均失败')
    raise RuntimeError(f'{hint}。\n网站：{urlsplit(url).hostname}\n' + '\n'.join(failures))

def fetch(url: str) -> bytes:
    p = urlsplit(url)
    if p.scheme != 'https' or not p.hostname or p.username or p.password:
        raise ValueError('下载地址必须是无登录信息的 HTTPS URL')
    if os.name == 'nt':
        with tempfile.TemporaryDirectory(prefix='htf-net-') as temp:
            return download_windows(url, Path(temp) / 'download')
    with urlopen(Request(url, headers={'User-Agent': 'HTFModManager/1.0'}), timeout=45) as r:
        data = r.read(LIMIT + 1)
        if len(data) > LIMIT:
            raise ValueError('下载超过大小限制')
        return data

class ThunderstoreSource:
    name = 'Thunderstore / How to Fish'
    def catalog(self):
        raw = json.loads(fetch(CATALOG))
        return [p for p in raw if not p.get('is_deprecated') and p.get('versions') and p['name'] != 'r2modman']

    def plan(self, selected, catalog):
        exact = {v['full_name']: (p, v) for p in catalog for v in p['versions']}
        result, active, seen = [], set(), set()
        def visit(p, v):
            key = v['full_name']
            if key in active:
                raise ValueError('依赖存在循环：' + key)
            if key in seen:
                return
            active.add(key)
            for dep in v.get('dependencies', []):
                if dep not in exact:
                    raise ValueError('找不到指定版本的依赖：' + dep)
                visit(*exact[dep])
            active.remove(key)
            seen.add(key)
            result.append((p, v))
        visit(selected, selected['versions'][0])
        return result

def zip_entries(path):
    out = []
    with zipfile.ZipFile(path) as z:
        total = 0
        seen = set()
        for item in z.infolist():
            if item.is_dir():
                continue
            name = item.filename.replace('\\', '/')
            parts = PurePosixPath(name).parts
            if not parts or name.startswith('/') or any(x in ('..', '.') or ':' in x or x.endswith(('.', ' ')) for x in parts):
                raise ValueError('压缩包含有不安全路径：' + name)
            if (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('不支持压缩包中的符号链接')
            for part in parts:
                if part.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *('COM'+str(i) for i in range(1,10)), *('LPT'+str(i) for i in range(1,10))}:
                    raise ValueError('不支持的 Windows 文件名')
            key = name.casefold()
            if key in seen:
                raise ValueError('压缩包含有重复路径')
            seen.add(key)
            total += item.file_size
            if total > LIMIT or item.file_size > LIMIT:
                raise ValueError('解压大小超过 150 MB')
            out.append((parts, z.read(item)))
    return out

class Store:
    def __init__(self, game):
        self.game = Path(game).resolve()
        if not self.game.is_dir():
            raise ValueError('游戏目录不存在')
        self.root = self.game / '.htf-mod-manager'
        self.check_path(self.root)
        self.root.mkdir(exist_ok=True)
        self.statefile = self.root / 'state.json'
        self.state = json.loads(self.statefile.read_text('utf-8')) if self.statefile.exists() else {'mods': [], 'loader': None}
        for mod in self.state['mods']:
            if not re.fullmatch('[0-9a-f]{32}', mod['id']):
                raise ValueError('管理器记录损坏：无效插件 ID')
        self.check_path(self.game / 'BepInEx' / 'plugins')

    def check_path(self, path):
        path = Path(path)
        if not path.resolve().is_relative_to(self.game):
            raise ValueError('路径超出游戏目录，请检查目录链接')
        cur = path
        while cur != self.game:
            if cur.is_symlink() or (hasattr(cur, 'is_junction') and cur.is_junction()):
                raise ValueError('不支持 Mod 路径中的目录链接')
            cur = cur.parent
        return path

    def save(self):
        temp = self.root / 'state.tmp'
        temp.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), 'utf-8')
        temp.replace(self.statefile)

    def modpath(self, mod, enabled=None):
        enabled = mod['enabled'] if enabled is None else enabled
        base = self.game / 'BepInEx' / 'plugins' if enabled else self.root / 'disabled'
        return self.check_path(base / ('HTFMM_' + mod['id']))

    def install_mod(self, path, package=None, version=None):
        entries = zip_entries(path)
        if any(parts[-1].lower() == 'winhttp.dll' for parts, _ in entries):
            raise ValueError('这是加载器包，请使用“安装 BepInEx”')
        manifest = next((json.loads(data.decode('utf-8-sig')) for parts, data in entries if parts[-1].lower() == 'manifest.json'), {})
        name = package or manifest.get('name') or Path(path).stem
        if any(m['name'].casefold() == name.casefold() for m in self.state['mods']):
            raise ValueError(name + ' 已安装；更新前请先卸载旧版本')
        files = []
        for parts, data in entries:
            low = [p.lower() for p in parts]
            if low[-1] in META:
                continue
            if 'bepinex' in low:
                i = low.index('bepinex')
                if len(parts) <= i+2 or low[i+1] != 'plugins':
                    raise ValueError('此包包含 plugins 之外的文件，请按作者说明手动安装')
                parts = parts[i+2:]
            elif 'plugins' in low:
                parts = parts[low.index('plugins')+1:]
            if parts:
                files.append((parts, data))
        if not any(parts[-1].lower().endswith('.dll') for parts, _ in files):
            raise ValueError('没有找到插件 DLL；此工具只自动安装 BepInEx 插件')
        mod = {'id': uuid.uuid4().hex, 'name': name, 'version': version or manifest.get('version_number', '本地'), 'enabled': True}
        dest = self.modpath(mod)
        try:
            for parts, data in files:
                target = self.check_path(dest.joinpath(*parts))
                if target.exists():
                    raise ValueError('插件目标路径重复')
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            self.state['mods'].append(mod)
            self.save()
        except Exception:
            if mod in self.state['mods']:
                self.state['mods'].remove(mod)
            if dest.exists():
                shutil.rmtree(dest)
            raise

    def toggle(self, mod):
        src, dest = self.modpath(mod), self.modpath(mod, not mod['enabled'])
        if not src.is_dir() or dest.exists():
            raise ValueError('插件文件已被外部修改，请检查目录')
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        mod['enabled'] = not mod['enabled']
        try:
            self.save()
        except Exception:
            mod['enabled'] = not mod['enabled']
            shutil.move(str(dest), str(src))
            raise

    def uninstall(self, mod):
        src = self.modpath(mod)
        trash = self.root / ('removed_' + mod['id'])
        if src.exists():
            shutil.move(str(src), str(trash))
        self.state['mods'].remove(mod)
        try:
            self.save()
        except Exception:
            self.state['mods'].append(mod)
            if trash.exists():
                shutil.move(str(trash), str(src))
            raise
        if trash.exists():
            shutil.rmtree(trash)

    def install_loader(self, path):
        if self.state.get('loader'):
            raise ValueError('本工具已安装过加载器，不重复覆盖；备份在 .htf-mod-manager/loader-backup')
        entries = zip_entries(path)
        roots = [parts[:-1] for parts, _ in entries if parts[-1].lower() == 'winhttp.dll']
        if len(roots) != 1:
            raise ValueError('不是支持的 BepInExPack：没有找到唯一的 winhttp.dll')
        prefix = roots[0]
        files = [(parts[len(prefix):], data) for parts, data in entries if parts[:len(prefix)] == prefix and len(parts)>len(prefix)]
        if not any(p[0].lower() == 'bepinex' for p, _ in files) or not any(p[-1].lower() == 'doorstop_config.ini' for p, _ in files):
            raise ValueError('加载器包不完整')
        backup = self.root / 'loader-backup'
        changed = []
        try:
            for parts, data in files:
                if parts[-1].lower() in META:
                    continue
                if parts[0].lower() not in ('bepinex', 'winhttp.dll', 'doorstop_config.ini', '.doorstop_version'):
                    continue
                target = self.check_path(self.game.joinpath(*parts))
                rel = '/'.join(parts)
                old = backup.joinpath(*parts)
                existed = target.exists()
                if existed:
                    old.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, old)
                changed.append((rel, existed))
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            self.state['loader'] = changed
            self.save()
        except Exception:
            self.state['loader'] = None
            for rel, existed in reversed(changed):
                target = self.game / rel
                if existed:
                    shutil.copy2(backup / rel, target)
                else:
                    target.unlink(missing_ok=True)
            raise

class App:
    def __init__(self, root):
        self.root, self.store, self.catalog, self.busy = root, None, [], False
        self.events = queue.Queue()
        self.source = ThunderstoreSource()
        self.chinese = True
        root.title('渔力全开 · Mod 管理器 v1.2')
        root.geometry('960x690')
        root.minsize(820, 580)
        style = ttk.Style()
        style.theme_use('vista' if 'vista' in style.theme_names() else 'clam')
        style.configure('.', font=('Microsoft YaHei UI', 10))
        outer = ttk.Frame(root, padding=18)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='渔力全开 Mod 管理器', font=('Microsoft YaHei UI', 19, 'bold')).pack(anchor='w')
        ttk.Label(outer, text='本地 ZIP 与 Thunderstore 在线安装 · 直接启动游戏', foreground='#586575').pack(anchor='w', pady=(4,14))
        row = ttk.Frame(outer); row.pack(fill='x')
        self.gamevar = tk.StringVar()
        ttk.Entry(row, textvariable=self.gamevar, state='readonly').pack(side='left', fill='x', expand=True)
        self.buttons = []
        self.button(row, '选择游戏 EXE', self.choose).pack(side='left', padx=(8,0))
        self.tabs = ttk.Notebook(outer); self.tabs.pack(fill='both', expand=True, pady=14)
        local = ttk.Frame(self.tabs, padding=12); online = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(local, text='已安装 / 本地导入'); self.tabs.add(online, text='在线 Mod')
        bar = ttk.Frame(local); bar.pack(fill='x', pady=(0,10))
        for label, fn in [('安装 BepInEx ZIP', self.loader), ('导入 Mod ZIP', self.import_mod), ('启用 / 停用', self.toggle), ('卸载选中 Mod', self.remove)]:
            self.button(bar, label, fn).pack(side='left', padx=(0,8))
        self.local = self.tree(local, ('名称','版本','状态'))
        ttk.Label(local, text='仅管理本工具安装的插件。外部已有 Mod 不会自动接管。\n更新请先卸载旧版本；依赖不能随意停用。操作前请关闭游戏。', foreground='#586575').pack(anchor='w', pady=10)
        searchbar = ttk.Frame(online); searchbar.pack(fill='x', pady=(0,10))
        self.query = tk.StringVar()
        entry = ttk.Entry(searchbar, textvariable=self.query); entry.pack(side='left', fill='x', expand=True)
        self.query.trace_add('write', lambda *_: self.filter())
        self.button(searchbar, '刷新在线列表', self.refresh_online).pack(side='left', padx=8)
        self.language_button = self.button(searchbar, '切换英文 / English', self.toggle_language)
        self.language_button.pack(side='left')
        self.remote = self.tree(online, ('名称 / 作者','最新版本','简介'))
        self.remote.bind('<<TreeviewSelect>>', lambda _: self.show_details())
        self.details = tk.Text(online, height=5, wrap='word', font=('Microsoft YaHei UI', 10), relief='flat', background='#f4f6f8')
        self.details.pack(fill='x', pady=(8,0))
        self.details.configure(state='disabled')
        bar2 = ttk.Frame(online); bar2.pack(fill='x', pady=10)
        self.button(bar2, '下载并安装（含依赖）', self.install_online).pack(side='left', padx=(0,8))
        self.button(bar2, '打开 Mod 网页', self.open_page).pack(side='left')
        ttk.Label(online, text='当前源：Thunderstore / How to Fish。支持 plugins 插件和 BepInExPack；复杂安装包会提示手动处理。', wraplength=820, foreground='#586575').pack(anchor='w')
        foot = ttk.Frame(outer); foot.pack(fill='x')
        self.button(foot, '直接启动游戏', self.launch).pack(side='left')
        self.button(foot, '打开游戏目录', self.folder).pack(side='left', padx=8)
        self.status = tk.StringVar(value='先选择游戏文件夹内的游戏 EXE，无需通过 Steam 启动。')
        ttk.Label(outer, textvariable=self.status, wraplength=880).pack(anchor='w', pady=(12,0))
        self.exe = None
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100, self.poll)

    def close(self):
        if self.busy:
            messagebox.showinfo('操作进行中', '请等待下载或安装结束后再关闭。')
        else:
            self.root.destroy()

    def button(self, frame, text, fn):
        b = ttk.Button(frame, text=text, command=lambda: self.guard(fn)); self.buttons.append(b); return b

    def tree(self, frame, columns):
        container = ttk.Frame(frame); container.pack(fill='both', expand=True)
        t = ttk.Treeview(container, columns=columns, show='headings', selectmode='browse')
        for c in columns:
            t.heading(c, text=c); t.column(c, width=170 if c != '简介' else 390)
        s = ttk.Scrollbar(container, command=t.yview); t.configure(yscrollcommand=s.set)
        s.pack(side='right', fill='y'); t.pack(fill='both', expand=True)
        return t

    def guard(self, fn):
        if self.busy: return
        try: fn()
        except Exception as e: messagebox.showerror('操作未完成', str(e))

    def worker(self, fn, success):
        self.busy = True
        for b in self.buttons: b.state(['disabled'])
        def run():
            try: self.events.put((success, fn(), None))
            except Exception as e: self.events.put((None, None, str(e)))
        threading.Thread(target=run, daemon=True).start()

    def poll(self):
        try:
            while True:
                callback, value, error = self.events.get_nowait()
                self.busy = False
                for b in self.buttons: b.state(['!disabled'])
                if error:
                    self.status.set('操作未完成：' + error)
                    messagebox.showerror('操作未完成', error)
                    self.render()
                else: self.guard(lambda: callback(value))
        except queue.Empty: pass
        self.root.after(100, self.poll)

    def need_game(self):
        if not self.store: raise ValueError('请先选择游戏 EXE')

    def choose(self):
        p = filedialog.askopenfilename(title='选择渔力全开的游戏 EXE', filetypes=[('游戏程序','*.exe')])
        if not p: return
        exe = Path(p)
        if not (exe.parent / (exe.stem + '_Data')).is_dir():
            raise ValueError('没有找到对应的 Unity *_Data 目录，请选择游戏本体 EXE')
        if (exe.parent / 'GameAssembly.dll').exists():
            raise ValueError('检测到 IL2CPP；本工具当前仅支持 Mono BepInExPack')
        self.store = Store(exe.parent); self.exe = exe
        self.gamevar.set(str(exe)); self.render()
        self.status.set('已选择游戏；安装加载器后可导入本地 ZIP，或在在线页安装 Mod。')

    def render(self):
        self.local.delete(*self.local.get_children())
        if self.store:
            for m in self.store.state['mods']:
                translated = TRANSLATIONS.get(m['name'], {})
                name = translated.get('name', m['name']) if self.chinese else m['name']
                self.local.insert('', 'end', iid=m['id'], values=(name,m['version'],'已启用' if m['enabled'] else '已停用'))

    def selected_mod(self):
        self.need_game()
        s = self.local.selection()
        if not s: raise ValueError('请先选择已安装的 Mod')
        return next(m for m in self.store.state['mods'] if m['id']==s[0])

    def loader(self):
        self.need_game()
        p = filedialog.askopenfilename(filetypes=[('BepInExPack ZIP','*.zip')])
        if p:
            self.store.install_loader(p); self.status.set('加载器已安装，覆盖前的文件已备份。请启动一次游戏检查加载情况。')

    def import_mod(self):
        self.need_game()
        p = filedialog.askopenfilename(filetypes=[('Mod ZIP','*.zip')])
        if p:
            self.store.install_mod(p); self.render(); self.status.set('Mod 已导入并启用；依赖请在在线页安装或另行导入。')

    def toggle(self):
        m = self.selected_mod(); self.store.toggle(m); self.render(); self.status.set('插件状态已更新。')

    def remove(self):
        m = self.selected_mod()
        if messagebox.askyesno('卸载 Mod', '卸载 '+m['name']+'？其他 Mod 可能依赖它。'):
            self.store.uninstall(m); self.render(); self.status.set('已卸载选中插件。')

    def refresh_online(self):
        self.status.set('正在获取 Thunderstore 列表…')
        def done(value):
            self.catalog = value; self.filter(); self.status.set(f'已加载 {len(value)} 个 Mod。支持中英文名称、作者和简介搜索；中文为本工具整理的参考译名。')
        self.worker(self.source.catalog, done)

    def filter(self):
        selected = self.remote.selection()
        self.remote.delete(*self.remote.get_children())
        query = self.query.get().casefold()
        for i,p in enumerate(self.catalog):
            v=p['versions'][0]
            title, description = mod_text(p, self.chinese)
            translated = TRANSLATIONS.get(p['full_name'], {})
            haystack = ' '.join((p['full_name'],v.get('description',''),translated.get('name',''),translated.get('description','')))
            if query in haystack.casefold():
                self.remote.insert('', 'end', iid=str(i), values=(title,v['version_number'],description))
        if selected and self.remote.exists(selected[0]):
            self.remote.selection_set(selected[0]); self.remote.see(selected[0])
        self.show_details()

    def toggle_language(self):
        self.chinese = not self.chinese
        self.language_button.configure(text='切换英文 / English' if self.chinese else '切换中文 / 中文')
        self.filter(); self.render()
        self.status.set('Mod 名称和简介：' + ('中文参考译文' if self.chinese else '网站原始文本') + '。安装仍使用原始包标识。')

    def show_details(self):
        selected = self.remote.selection()
        text = '选择一个 Mod 查看完整简介和原始包标识。'
        if selected:
            p = self.catalog[int(selected[0])]
            title, description = mod_text(p, self.chinese)
            text = title + '\n原始包标识：' + p['full_name'] + '\n' + description
        self.details.configure(state='normal'); self.details.delete('1.0','end')
        self.details.insert('1.0',text); self.details.configure(state='disabled')

    def selected_online(self):
        s=self.remote.selection()
        if not s: raise ValueError('请先选择在线 Mod')
        return self.catalog[int(s[0])]

    def open_page(self):
        url=self.selected_online()['package_url']
        if urlsplit(url).scheme == 'https': webbrowser.open(url)

    def install_online(self):
        self.need_game()
        plan=self.source.plan(self.selected_online(), self.catalog)
        pending=[]
        for p,v in plan:
            if p['full_name']=='BepInEx-BepInExPack':
                if not self.store.state.get('loader'): pending.append((p,v))
                continue
            installed=next((m for m in self.store.state['mods'] if m['name']==p['full_name']),None)
            if installed:
                if installed['version']!=v['version_number'] or not installed['enabled']:
                    raise ValueError(p['full_name']+' 的已有版本不符或已停用，请先处理该依赖')
            else: pending.append((p,v))
        if not pending:
            self.status.set('此 Mod 及所需依赖已经安装并启用。'); return
        labels = [(TRANSLATIONS.get(p['full_name'],{}).get('name',p['name'])+' — '+v['full_name']) if self.chinese else v['full_name'] for p,v in pending]
        if not messagebox.askyesno('确认安装清单', '将下载并安装以下包：\n\n'+'\n'.join(labels)+'\n\n请确认游戏已关闭。'):
            return
        self.status.set('正在下载和安装；请等待。已完成的依赖在后续失败时会保留。')
        def run():
            with tempfile.TemporaryDirectory(prefix='htf-mods-') as temp:
                downloads=[]
                for i,(p,v) in enumerate(pending):
                    path=Path(temp)/f'{i}.zip'; path.write_bytes(fetch(v['download_url']))
                    zip_entries(path)
                    downloads.append((p,v,path))
                for p,v,path in downloads:
                    if p['full_name']=='BepInEx-BepInExPack': self.store.install_loader(path)
                    else: self.store.install_mod(path,p['full_name'],v['version_number'])
            return len(downloads)
        def done(n):
            self.render(); self.status.set(f'安装完成：{n} 个包。可点击“直接启动游戏”。')
        self.worker(run,done)

    def launch(self):
        self.need_game()
        subprocess.Popen([str(self.exe)], cwd=str(self.exe.parent))
        self.status.set('已启动游戏进程；控制台 Mod 安装成功后可按 F1 或 ~ 检查。')

    def folder(self):
        self.need_game(); os.startfile(self.store.game)

if __name__ == '__main__' and len(sys.argv) == 3 and sys.argv[1] == '--network-check':
    try:
        packages = ThunderstoreSource().catalog()
        Path(sys.argv[2]).write_text(json.dumps({'ok': True, 'count': len(packages), 'translations': len(TRANSLATIONS), 'frozen': getattr(sys, 'frozen', False)}, ensure_ascii=False), 'utf-8')
    except Exception as e:
        Path(sys.argv[2]).write_text(json.dumps({'ok': False, 'error': str(e)}, ensure_ascii=False), 'utf-8')
        sys.exit(1)
elif __name__ == '__main__':
    root=tk.Tk()
    App(root)
    root.mainloop()
