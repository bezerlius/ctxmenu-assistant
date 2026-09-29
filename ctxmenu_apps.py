# -*- coding: utf-8 -*-
"""
ctxmenu_apps.py —— 应用扫描层

职责：
  1. 扫描系统里已安装的软件（开始菜单快捷方式 + 常见安装目录）
  2. 解析 .lnk 快捷方式，拿到目标 exe / 参数 / 图标
  3. 供界面「选择应用 → 一键添加」使用

不依赖 pywin32 / winshell，.lnk 用纯 Python 解析（Shell Link Binary 格式），
保证打包成 exe 后零第三方依赖。
"""

from __future__ import annotations

import os
import struct
import glob

# ---------------------------------------------------------------------------
# 常见绿色版 / 常用程序的关键字（用于在 Program Files 里挑出值得进右键菜单的）
# ---------------------------------------------------------------------------
POPULAR_KEYWORDS = [
    "vscode", "code", "notepad++", "sublime", "pycharm", "idea", "goland",
    "webstorm", "clion", "rider", "datagrip", "android studio",
    "7-zip", "winrar", "bandizip", "360zip", "peazip",
    "wps", "office", "word", "excel", "powerpoint", "onenote", "visio",
    "chrome", "edge", "firefox", "brave", "opera",
    "qq", "wechat", "weixin", "dingtalk", "feishu", "lark", "telegram",
    "xmind", "mindmaster", "processon",
    "photoshop", "illustrator", "premiere", "after effects", "lightroom",
    "gimp", "inkscape", "krita", "blender", "autocad", "solidworks",
    "git", "tortoisegit", "sourcetree", "github desktop",
    "putty", "xshell", "xftp", "winscp", "mobaxterm", "finalshell",
    "vmware", "virtualbox", "docker",
    "vlc", "potplayer", "mpv", "obs", "snipaste", "picpick",
    "typora", "obsidian", "notion", "evernote", "onenote",
    "cmder", "conemu", "windows terminal", "powershell",
    "python", "java", "node", "git bash", "mingw",
    "fiddler", "wireshark", "charles", "postman", "apifox",
    "keil", "iar", "stm32", "cubemx", "arduino", "platformio",
    "source insight", "understand", "beyond compare",
]


# ---------------------------------------------------------------------------
# .lnk 解析（Shell Link Binary File Format 精简实现）
# ---------------------------------------------------------------------------

def parse_lnk(path: str) -> dict | None:
    """
    解析 Windows .lnk 快捷方式，返回 {target, args, icon, workdir, name}。
    解析失败返回 None。纯 Python 实现，不依赖 pywin32。
    """
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return None

    if len(data) < 76 or data[:4] != b"\x4c\x00\x00\x00":
        return None

    # Header 里读 flags
    flags = struct.unpack_from("<I", data, 20)[0]
    has_link_target_idlist = bool(flags & 0x01)
    has_link_info = bool(flags & 0x02)
    has_name = bool(flags & 0x04)
    has_rel_path = bool(flags & 0x08)
    has_workdir = bool(flags & 0x10)
    has_args = bool(flags & 0x20)
    has_icon = bool(flags & 0x40)

    off = 76
    result: dict = {"target": "", "args": "", "icon": "", "workdir": "",
                    "name": os.path.splitext(os.path.basename(path))[0]}

    # 跳过 LinkTargetIDList
    if has_link_target_idlist:
        if off + 2 > len(data):
            return result
        idlist_size = struct.unpack_from("<H", data, off)[0]
        off += 2 + idlist_size

    # LinkInfo：里面有本地目标路径
    if has_link_info and off + 4 <= len(data):
        li_size = struct.unpack_from("<I", data, off)[0]
        li_start = off
        try:
            li_flags = struct.unpack_from("<I", data, li_start + 8)[0]
            # VolumeIDAndLocalBasePath = 0x01
            if li_flags & 0x01:
                voloff = struct.unpack_from("<I", data, li_start + 12)[0]
                locoff = struct.unpack_from("<I", data, li_start + 16)[0]
                if locoff:
                    p = li_start + locoff
                    end = data.find(b"\x00", p)
                    if end > p:
                        result["target"] = data[p:end].decode(
                            "mbcs" if os.name == "nt" else "utf-8", errors="ignore")
        except (struct.error, IndexError):
            pass
        off = li_start + li_size

    def _read_string_table(offset: int, unicode_flag: bool):
        """读 CountCharacters 前缀的字符串。"""
        if offset + 2 > len(data):
            return "", offset
        cnt = struct.unpack_from("<H", data, offset)[0]
        offset += 2
        if unicode_flag:
            n = cnt * 2
            if offset + n > len(data):
                return "", len(data)
            return data[offset:offset + n].decode("utf-16-le", errors="ignore"), offset + n
        else:
            if offset + cnt > len(data):
                return "", len(data)
            return data[offset:offset + cnt].decode("mbcs", errors="ignore"), offset + cnt

    # StringData 区（顺序固定：NAME, RELPATH, WORKDIR, ARGS, ICON）
    if has_name:
        s, off = _read_string_table(off, True)   # 总是 Unicode
        if s:
            result["name"] = s
    if has_rel_path:
        _, off = _read_string_table(off, True)
    if has_workdir:
        s, off = _read_string_table(off, True)
        result["workdir"] = s
    if has_args:
        s, off = _read_string_table(off, True)
        result["args"] = s
    if has_icon:
        s, off = _read_string_table(off, True)
        result["icon"] = s

    # 兜底：如果没从 LinkInfo 拿到 target，用 ExtraData 里的 EnvironmentVariableDataBlock
    if not result["target"] and off < len(data):
        result["target"] = _scan_env_block(data, off)

    return result


def _scan_env_block(data: bytes, off: int) -> str:
    """在 ExtraData 里找 EnvironmentVariableDataBlock(0xA0000001) 的目标路径。"""
    sig = struct.pack("<I", 0xA0000001)
    idx = data.find(sig, off)
    if idx < 0:
        return ""
    p = idx + 8
    end = data.find(b"\x00", p)
    if end <= p:
        return ""
    return data[p:end].decode("utf-16-le", errors="ignore")


# ---------------------------------------------------------------------------
# 应用扫描
# ---------------------------------------------------------------------------

def _start_menu_dirs() -> list[str]:
    """返回开始菜单里所有程序快捷方式所在目录。"""
    dirs: list[str] = []
    appdata = os.environ.get("APPDATA", "")
    programdata = os.environ.get("ProgramData", r"C:\ProgramData")
    if appdata:
        dirs.append(os.path.join(appdata, "Microsoft", "Windows",
                                 "Start Menu", "Programs"))
    dirs.append(os.path.join(programdata, "Microsoft", "Windows",
                             "Start Menu", "Programs"))
    return [d for d in dirs if os.path.isdir(d)]


def scan_start_menu() -> list[dict]:
    """扫描开始菜单，返回可用的应用列表。"""
    apps: list[dict] = []
    seen: set[str] = set()
    for base in _start_menu_dirs():
        for root, _dirs, files in os.walk(base):
            for fn in files:
                if not fn.lower().endswith(".lnk"):
                    continue
                # 跳过卸载 / 帮助 / 文档之类
                low = fn.lower()
                if any(k in low for k in ("卸载", "uninstall", "帮助", "help",
                                          "readme", "说明", "文档", "document",
                                          "官网", "website", "手册", "manual")):
                    continue
                full = os.path.join(root, fn)
                info = parse_lnk(full)
                if not info:
                    continue
                target = info.get("target", "")
                if not target:
                    continue
                # 只保留 exe 目标，且文件真实存在
                if not target.lower().endswith(".exe"):
                    continue
                if not os.path.exists(target):
                    continue
                key = target.lower()
                if key in seen:
                    continue
                seen.add(key)
                apps.append({
                    "name": _pick_display_name(fn, info.get("name", ""), target),
                    "target": target,
                    "args": info.get("args", ""),
                    "workdir": info.get("workdir", "") or os.path.dirname(target),
                    "icon": info.get("icon", "") or target,
                    "source": "开始菜单",
                    "lnk": full,
                })
    return apps


def _pick_display_name(lnk_filename: str, lnk_internal_name: str, target: str) -> str:
    """
    挑一个好看的显示名。
    开始菜单里 Office 之类快捷方式的内部 name 常是一整句描述文字，
    文件名反而更干净，所以取「更短且像程序名」的那个。
    """
    fname = os.path.splitext(os.path.basename(lnk_filename))[0]
    iname = (lnk_internal_name or "").strip()

    def bad(s: str) -> bool:
        # 太长、含句号结尾、有大段英文描述 -> 不像程序名
        return (not s) or len(s) > 40 or s.endswith(".") or s.count(" ") >= 5

    if bad(iname) and not bad(fname):
        return fname
    if bad(fname) and not bad(iname):
        return iname
    # 都正常时优先文件名（通常更贴合快捷方式在菜单里的显示）
    name = fname if fname else iname
    # 目标 exe 名比快捷方式名更贴近本名时，用 exe 名兜底
    if not name:
        name = os.path.splitext(os.path.basename(target))[0]
    return name


def scan_program_files() -> list[dict]:
    """扫描 Program Files 下常见软件的 exe（只挑关键字命中的，避免噪音）。"""
    apps: list[dict] = []
    seen: set[str] = set()
    roots = [
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs"),
    ]
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        # 只下钻两层，控制扫描时间
        for lvl1 in _safe_listdir(root):
            p1 = os.path.join(root, lvl1)
            if not os.path.isdir(p1):
                continue
            if not _keyword_hit(lvl1):
                continue
            for exe in _find_main_exe(p1):
                key = exe.lower()
                if key in seen:
                    continue
                seen.add(key)
                apps.append({
                    "name": os.path.splitext(os.path.basename(exe))[0],
                    "target": exe,
                    "args": "",
                    "workdir": os.path.dirname(exe),
                    "icon": exe,
                    "source": "安装目录",
                })
    return apps


def _keyword_hit(name: str) -> bool:
    low = name.lower()
    return any(k in low for k in POPULAR_KEYWORDS)


def _safe_listdir(p: str) -> list[str]:
    try:
        return os.listdir(p)
    except OSError:
        return []


def _find_main_exe(folder: str, max_depth: int = 2) -> list[str]:
    """在一个软件目录里找主程序 exe：优先同名 exe，其次目录下最大的 exe。"""
    cands: list[str] = []
    folder_name = os.path.basename(folder).lower()

    def walk(d: str, depth: int):
        if depth > max_depth or len(cands) >= 3:
            return
        for fn in _safe_listdir(d):
            fp = os.path.join(d, fn)
            if os.path.isdir(fp):
                # 跳过明显的非程序目录
                if fn.lower() in ("locales", "resources", "plugins", "themes",
                                  "docs", "help", "uninstall", "redist",
                                  "tools", "sdk", "include", "lib"):
                    continue
                walk(fp, depth + 1)
            elif fn.lower().endswith(".exe"):
                low = fn.lower()
                if any(k in low for k in ("unins", "setup", "install", "update",
                                          "updater", "crashpad", "helper",
                                          "vcredist", "report", "service")):
                    continue
                cands.append(fp)

    walk(folder, 0)
    if not cands:
        return []
    # 优先名字和目录名相近的
    def score(p: str) -> tuple:
        base = os.path.splitext(os.path.basename(p))[0].lower()
        same = 0 if base in folder_name or folder_name in base else 1
        try:
            size = os.path.getsize(p)
        except OSError:
            size = 0
        return (same, -size)
    cands.sort(key=score)
    return cands[:1]


def scan_common_tools() -> list[dict]:
    """补充一批系统自带 / 常见工具（即使扫描不到也一定有）。"""
    win = os.environ.get("SystemRoot", r"C:\Windows")
    sys32 = os.path.join(win, "System32")
    local = os.environ.get("LOCALAPPDATA", "")
    tools = [
        ("命令提示符", os.path.join(sys32, "cmd.exe")),
        ("Windows PowerShell", os.path.join(
            sys32, "WindowsPowerShell", "v1.0", "powershell.exe")),
        ("记事本", os.path.join(sys32, "notepad.exe")),
        ("计算器", os.path.join(sys32, "calc.exe")),
        ("画图", os.path.join(sys32, "mspaint.exe")),
        ("资源管理器", os.path.join(win, "explorer.exe")),
        ("任务管理器", os.path.join(sys32, "Taskmgr.exe")),
        ("Windows Terminal", os.path.join(local, "Microsoft", "WindowsApps", "wt.exe")),
    ]
    out: list[dict] = []
    for name, p in tools:
        if os.path.exists(p):
            out.append({
                "name": name, "target": p, "args": "", "workdir": os.path.dirname(p),
                "icon": p, "source": "系统",
            })
    return out


def scan_all_apps() -> list[dict]:
    """全量扫描，合并去重，按名称排序。"""
    merged: dict[str, dict] = {}
    for fn in (scan_common_tools, scan_start_menu, scan_program_files):
        try:
            for app in fn():
                key = app["target"].lower()
                if key not in merged:
                    merged[key] = app
        except Exception:  # noqa: BLE001  扫描层绝不能因单个失败而整体崩
            continue
    return sorted(merged.values(), key=lambda a: a["name"].lower())


# ---------------------------------------------------------------------------
# 由应用生成菜单项命令
# ---------------------------------------------------------------------------

def build_command(target: str, args: str = "", scene: str = "file",
                  pass_arg: bool = False) -> str:
    """
    根据目标程序 + 场景生成命令行。

      pass_arg=True  ：把选中项路径作为参数传给程序（适合「用 XX 打开此文件」）
                       file/dir 场景用 %1，dirbg/desktop 场景用 %V
      pass_arg=False ：只启动程序本身，不传任何参数（默认，适合绝大多数 GUI 程序）

    为什么要区分：像「右键菜单助手」这类 GUI 程序不接收命令行参数，
    硬塞一个 %V 进去是脏参数，可能被程序当成非法输入。
    只有记事本、VS Code 这种「打开指定文件」的用途才需要 pass_arg=True。

    路径统一用反斜杠，避免个别程序/解析器对正斜杠处理不一致。
    """
    exe = '"' + target.replace("/", "\\") + '"'
    extra = f" {args}" if args.strip() else ""
    if not pass_arg:
        return f"{exe}{extra}"
    if scene in ("file", "dir"):
        return f'{exe}{extra} "%1"'
    if scene in ("dirbg", "desktop"):
        return f'{exe}{extra} "%V"'
    return f"{exe}{extra}"


def suggest_key(name: str) -> str:
    """由应用名生成一个安全的注册表键名。"""
    keep = []
    for ch in name:
        if ch.isalnum():
            keep.append(ch)
        elif ch in " -_":
            keep.append("_")
    s = "".join(keep).strip("_")
    return ("open_" + s) if s else "open_app"


# ---------------------------------------------------------------------------
# 自检
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import time
    t0 = time.time()
    apps = scan_all_apps()
    print(f"扫描到 {len(apps)} 个应用，耗时 {time.time()-t0:.2f}s\n")
    for a in apps[:40]:
        print(f"  [{a['source']}] {a['name']}")
        print(f"        {a['target']}")
    if len(apps) > 40:
        print(f"  ... 其余 {len(apps)-40} 个")
    print()
    print("命令生成示例：")
    demo = apps[0] if apps else {"target": r"C:\Windows\notepad.exe", "args": ""}
    for sc in ("file", "dir", "dirbg"):
        print(f"  {sc:8} -> {build_command(demo['target'], demo['args'], sc)}")
    print(f"  键名建议 -> {suggest_key(demo['name'])}")
