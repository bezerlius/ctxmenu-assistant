# -*- coding: utf-8 -*-
"""
ctxmenu_core.py —— 一键自定义右键菜单助手 · 注册表核心层

职责：
  1. 四种右键场景（文件 / 目录 / 目录背景 / 桌面背景）的菜单项增删改查
  2. 全部写入 HKCU，不需要管理员权限
  3. 只管理带本工具标记(_owner=ctxmenu-assistant)的项，不误伤系统与其他软件菜单

Windows 右键菜单注册表位置速查：
  右键「文件」     -> HKCU\\Software\\Classes\\*\\shell\\<name>
  右键「文件夹」   -> HKCU\\Software\\Classes\\Directory\\shell\\<name>
  右键「文件夹空白」-> HKCU\\Software\\Classes\\Directory\\Background\\shell\\<name>
  右键「桌面空白」 -> HKCU\\Software\\Classes\\DesktopBackground\\shell\\<name>
"""

from __future__ import annotations

import os
import sys
import winreg
from dataclasses import dataclass, field, asdict

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

APP_ID = "ctxmenu-assistant"
APP_TITLE = "一键自定义右键菜单助手"

# 停用状态的键名前缀：整项改名即可让菜单消失，配置完整保留
DISABLED_PREFIX = "_disabled_"

# 场景 key: (中文名, 注册表父路径, 说明)
SCENES: dict[str, tuple[str, str, str]] = {
    "file": (
        "文件",
        r"Software\Classes\*\shell",
        "选中任意文件后右键（可传文件路径 %1）",
    ),
    "dir": (
        "文件夹",
        r"Software\Classes\Directory\shell",
        "选中文件夹后右键（可传文件夹路径 %1）",
    ),
    "dirbg": (
        "文件夹空白处",
        r"Software\Classes\Directory\Background\shell",
        "在文件夹内空白处右键（当前目录 %V，需扩展名 .dll）",
    ),
    "desktop": (
        "桌面空白处",
        r"Software\Classes\DesktopBackground\shell",
        "在桌面空白处右键",
    ),
}

# 变量提示：给界面做悬浮说明用
VARIABLES = {
    "%1": "选中的文件 / 文件夹的完整路径",
    "%V": "当前所在文件夹路径（仅缓存类菜单生效）",
    "%*": "所有选中项的路径",
    "%W": "当前工作目录",
}

# MUIVerb 的显示上限，太长会把菜单撑爆
MAX_LABEL_LEN = 40


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class MenuItem:
    """一个右键菜单项。"""
    scene: str = "file"                 # 场景 key
    key_name: str = ""                  # 逻辑键名（用户看到的名字，不带停用前缀）
    real_key: str = ""                  # 注册表里真实的子键名（可能带 _disabled_ 前缀）
    label: str = ""                     # 菜单显示文字
    command: str = ""                   # 要执行的命令行
    icon: str = ""                      # 图标路径或 "exe,索引"
    extend: bool = False                # True=按 Shift 才显示
    enabled: bool = True                # 是否启用
    is_builtin: bool = False            # 是否内置模板生成

    def to_dict(self) -> dict:
        d = asdict(self)
        d["scene_label"] = SCENES.get(self.scene, ("?",))[0]
        return d


# ---------------------------------------------------------------------------
# 注册表工具
# ---------------------------------------------------------------------------

def _set_value(hive_root, path: str, name: str, value: str, reg_type: int) -> None:
    """安全写一个注册表值。"""
    with winreg.CreateKeyEx(hive_root, path, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, name, 0, reg_type, value)


def _get_value(hive_root, path: str, name: str):
    """读一个注册表值，不存在返回 None。"""
    try:
        with winreg.OpenKey(hive_root, path, 0, winreg.KEY_READ) as k:
            v, _ = winreg.QueryValueEx(k, name)
            return v
    except (FileNotFoundError, OSError):
        return None


def _delete_tree(hive_root, path: str) -> bool:
    """递归删除注册表键。返回是否删除了东西。"""
    try:
        with winreg.OpenKey(hive_root, path, 0, winreg.KEY_ALL_ACCESS) as k:
            # 先删所有子键
            while True:
                try:
                    sub = winreg.EnumKey(k, 0)
                except OSError:
                    break
                _delete_tree(hive_root, f"{path}\\{sub}")
        winreg.DeleteKey(hive_root, path)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def _subkeys(hive_root, path: str) -> list[str]:
    """列出一个注册表键下的子键名。不存在返回空列表。"""
    out: list[str] = []
    try:
        with winreg.OpenKey(hive_root, path, 0, winreg.KEY_READ) as k:
            i = 0
            while True:
                try:
                    out.append(winreg.EnumKey(k, i))
                    i += 1
                except OSError:
                    break
    except (FileNotFoundError, OSError):
        pass
    return out


def _dump_tree(hive_root, path: str) -> dict:
    """
    递归把一个注册表键读成纯 Python 结构：
        {"__values__": {name: (value, type)}, "子键名": {...嵌套...}}
    用于导出备份 / 整树复制，完全不依赖 reg.exe。
    """
    out: dict = {"__values__": {}}
    try:
        with winreg.OpenKey(hive_root, path, 0, winreg.KEY_READ) as k:
            i = 0
            while True:
                try:
                    name, val, typ = winreg.EnumValue(k, i)
                    out["__values__"][name] = (val, typ)
                    i += 1
                except OSError:
                    break
    except (FileNotFoundError, OSError):
        return out
    for sub in _subkeys(hive_root, path):
        out[sub] = _dump_tree(hive_root, f"{path}\\{sub}")
    return out


def _load_tree(hive_root, path: str, tree: dict) -> None:
    """_dump_tree 的逆操作：把结构写回注册表。"""
    with winreg.CreateKeyEx(hive_root, path, 0, winreg.KEY_SET_VALUE) as k:
        for name, (val, typ) in tree.get("__values__", {}).items():
            try:
                winreg.SetValueEx(k, name, 0, typ, val)
            except OSError:
                pass
    for sub, child in tree.items():
        if sub == "__values__":
            continue
        _load_tree(hive_root, f"{path}\\{sub}", child)


def _reg_escape(s: str) -> str:
    """按 .reg 文件格式转义字符串。"""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _type_name(typ: int) -> str:
    return {
        winreg.REG_SZ: "REG_SZ",
        winreg.REG_EXPAND_SZ: "REG_EXPAND_SZ",
        winreg.REG_MULTI_SZ: "REG_MULTI_SZ",
        winreg.REG_DWORD: "REG_DWORD",
        winreg.REG_QWORD: "REG_QWORD",
        winreg.REG_BINARY: "REG_BINARY",
    }.get(typ, "REG_SZ")


def _tree_to_reg_lines(tree: dict, full_path: str, out: list[str]) -> None:
    """把 _dump_tree 的结构渲染成 .reg 文本行。"""
    out.append(f"[{full_path}]")
    for name, (val, typ) in tree.get("__values__", {}).items():
        key = "@" if name == "" else f'"{_reg_escape(name)}"'
        tn = _type_name(typ)
        if typ in (winreg.REG_SZ, winreg.REG_EXPAND_SZ):
            out.append(f'{key}="{_reg_escape(str(val))}"')
        elif typ == winreg.REG_MULTI_SZ:
            parts = "\\0".join(_reg_escape(str(x)) for x in (val or []))
            out.append(f'{key}=hex(7):' + "".join(
                f"{b:02x}," for b in (parts + "\\0\\0").encode("utf-16-le")
            ).rstrip(","))
        elif typ == winreg.REG_DWORD:
            out.append(f"{key}=dword:{int(val) & 0xFFFFFFFF:08x}")
        elif typ == winreg.REG_QWORD:
            out.append(f"{key}=hex(b):" + "".join(
                f"{b:02x}," for b in int(val).to_bytes(8, "little")
            ).rstrip(","))
        elif typ == winreg.REG_BINARY:
            out.append(f"{key}=hex:" + "".join(f"{b:02x}," for b in (val or b"")).rstrip(","))
        else:
            out.append(f'{key}="{_reg_escape(str(val))}"')
    out.append("")
    for sub, child in tree.items():
        if sub == "__values__":
            continue
        _tree_to_reg_lines(child, f"{full_path}\\{sub}", out)


# ---------------------------------------------------------------------------
# 主管理类
# ---------------------------------------------------------------------------

class ContextMenuManager:
    """右键菜单管理器：所有操作都收敛在 HKCU 下，安全可撤。"""

    def __init__(self) -> None:
        self.hive = winreg.HKEY_CURRENT_USER

    # -- 路径拼接 ---------------------------------------------------------
    def item_path(self, scene: str, key_name: str) -> str:
        return f"{SCENES[scene][1]}\\{key_name}"

    def cmd_path(self, scene: str, key_name: str) -> str:
        return f"{self.item_path(scene, key_name)}\\command"

    # -- 写入 -------------------------------------------------------------
    def add(self, item: MenuItem) -> tuple[bool, str]:
        """新增或覆盖一个菜单项。"""
        if item.scene not in SCENES:
            return False, f"未知场景：{item.scene}"
        if not item.key_name.strip():
            return False, "注册表键名不能为空"
        if not item.label.strip():
            return False, "菜单显示文字不能为空"
        if not item.command.strip():
            return False, "命令行不能为空"

        base = self.item_path(item.scene, item.key_name)
        try:
            # 主键
            with winreg.CreateKeyEx(self.hive, base, 0, winreg.KEY_SET_VALUE) as k:
                winreg.SetValueEx(k, "MUIVerb", 0, winreg.REG_SZ, item.label)
                winreg.SetValueEx(k, "_owner", 0, winreg.REG_SZ, APP_ID)
                winreg.SetValueEx(
                    k, "_created_by", 0, winreg.REG_SZ, APP_TITLE
                )
                if item.icon.strip():
                    winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, item.icon)
                if item.extend:
                    winreg.SetValueEx(k, "Extended", 0, winreg.REG_SZ, "")
                else:
                    self._del_value(k, "Extended")
                # 让菜单文字自动加粗不加 & 转义风险：用 MUIVerb 已足够

            # command 子键
            with winreg.CreateKeyEx(
                self.hive, self.cmd_path(item.scene, item.key_name),
                0, winreg.KEY_SET_VALUE,
            ) as ck:
                winreg.SetValueEx(ck, "", 0, winreg.REG_SZ, item.command)

            return True, f"已写入：{SCENES[item.scene][0]} → {item.label}"
        except PermissionError:
            return False, "权限不足，请以当前用户身份重试"
        except OSError as e:
            return False, f"写注册表失败：{e}"

    @staticmethod
    def _del_value(key, name: str) -> None:
        try:
            winreg.DeleteValue(key, name)
        except OSError:
            pass

    # -- 删除 -------------------------------------------------------------
    def _resolve_real_key(self, scene: str, key_name: str) -> str | None:
        """
        把用户给的逻辑键名解析成注册表里的真实子键名。
        先找原始键，再找 _disabled_ 前缀键，都不在返回 None。
        """
        parent = SCENES[scene][1]
        subs = _subkeys(self.hive, parent)
        if key_name in subs:
            return key_name
        dis = f"{DISABLED_PREFIX}{key_name}"
        if dis in subs:
            return dis
        return None

    def remove(self, scene: str, key_name: str) -> tuple[bool, str]:
        """删除一个菜单项（整棵子树），启用/停用状态都能删。"""
        if scene not in SCENES:
            return False, f"未知场景：{scene}"
        real = self._resolve_real_key(scene, key_name)
        if real is None:
            return False, f"未找到该项：{key_name}"
        path = self.item_path(scene, real)
        if _delete_tree(self.hive, path):
            return True, f"已删除：{SCENES[scene][0]} → {key_name}"
        return False, f"删除失败（可能被占用）：{key_name}"

    # -- 启停 -------------------------------------------------------------
    def set_enabled(self, scene: str, key_name: str, enabled: bool) -> tuple[bool, str]:
        """
        启用/停用。
        停用策略：整项改名为 _disabled_<key>，配置完整保留但菜单立即消失。
        """
        if scene not in SCENES:
            return False, f"未知场景：{scene}"
        real = self._resolve_real_key(scene, key_name)
        if real is None:
            return False, f"未找到该项：{key_name}"

        is_disabled = real.startswith(DISABLED_PREFIX)
        if enabled and not is_disabled:
            return True, "该项本就处于启用状态"
        if not enabled and is_disabled:
            return True, "该项本就处于停用状态"

        # 计算目标真实键名
        if enabled:
            target = real[len(DISABLED_PREFIX):]
        else:
            target = f"{DISABLED_PREFIX}{real}"
        return self._rename(scene, real, target)

    def _rename(self, scene: str, old: str, new: str) -> tuple[bool, str]:
        """
        把注册表子树整体改名：读出整树 -> 写到新键 -> 删旧键。
        纯 Python 实现，不依赖 reg.exe。
        """
        try:
            src = self.item_path(scene, old)
            dst = self.item_path(scene, new)
            tree = _dump_tree(self.hive, src)
            if not tree.get("__values__") and len(tree) <= 1:
                return False, f"未找到该项：{old}"
            _load_tree(self.hive, dst, tree)
            _delete_tree(self.hive, src)
            return True, "状态已切换（点右上角「让菜单立即生效」即可看到变化）"
        except OSError as e:
            return False, f"重命名异常：{e}"

    # -- 读取 -------------------------------------------------------------
    def list_items(self, include_disabled: bool = True) -> list[MenuItem]:
        """枚举本工具创建的所有菜单项。"""
        result: list[MenuItem] = []
        for scene in SCENES:
            parent = SCENES[scene][1]
            for sub in _subkeys(self.hive, parent):
                owner = _get_value(self.hive, f"{parent}\\{sub}", "_owner")
                if owner != APP_ID:
                    continue  # 不是我们建的，跳过，绝不碰别人的
                if sub.startswith(DISABLED_PREFIX) and not include_disabled:
                    continue
                label = _get_value(self.hive, f"{parent}\\{sub}", "MUIVerb") or sub
                icon = _get_value(self.hive, f"{parent}\\{sub}", "Icon") or ""
                extend = _get_value(self.hive, f"{parent}\\{sub}", "Extended") is not None
                cmd = _get_value(self.hive, f"{parent}\\{sub}\\command", "") or ""
                disabled = sub.startswith(DISABLED_PREFIX)
                key = sub[len(DISABLED_PREFIX):] if disabled else sub
                result.append(MenuItem(
                    scene=scene,
                    key_name=key,       # 干净的逻辑键名
                    real_key=sub,       # 注册表真实子键名
                    label=str(label),
                    command=str(cmd),
                    icon=str(icon),
                    extend=extend,
                    enabled=not disabled,
                ))
        return result

    def find(self, scene: str, key_name: str) -> MenuItem | None:
        for it in self.list_items():
            if it.scene == scene and it.key_name == key_name:
                return it
        return None

    def exists(self, scene: str, key_name: str) -> bool:
        """判断某个逻辑键名在指定场景下是否已存在（含停用项）。"""
        return self._resolve_real_key(scene, key_name) is not None

    # -- 备份 / 还原 -------------------------------------------------------
    def export_backup(self, file_path: str) -> tuple[bool, str]:
        """把本工具涉及的全部注册表分支导出成 .reg 备份（纯 Python 实现）。"""
        lines: list[str] = ["Windows Registry Editor Version 5.00", ""]
        got = 0
        for s in SCENES:
            rel = SCENES[s][1]
            tree = _dump_tree(self.hive, rel)
            if len(tree) <= 1 and not tree.get("__values__"):
                continue
            _tree_to_reg_lines(tree, f"HKEY_CURRENT_USER\\{rel}", lines)
            got += 1
        if got == 0:
            lines.append("; 当前没有任何本工具创建的右键菜单项")
            lines.append("")
        try:
            with open(file_path, "w", encoding="utf-16") as f:
                f.write("\n".join(lines) + "\n")
            return True, f"备份已保存（{got} 个分支）：{file_path}"
        except OSError as e:
            return False, f"写备份失败：{e}"

    def import_backup(self, file_path: str) -> tuple[bool, str]:
        """
        从 .reg 文件还原。用 winreg 解析，不调用 reg.exe。
        支持 REG_SZ / REG_EXPAND_SZ / REG_DWORD / REG_MULTI_SZ。
        """
        import re
        if not os.path.exists(file_path):
            return False, "备份文件不存在"
        # 尝试多种编码：.reg 通常是 UTF-16LE，也可能是 UTF-8/ANSI
        text = ""
        for enc in ("utf-16", "utf-8-sig", "gbk", "latin-1"):
            try:
                with open(file_path, "r", encoding=enc) as f:
                    text = f.read()
                if text:
                    break
            except (UnicodeDecodeError, OSError):
                continue
        if not text:
            return False, "备份文件无法读取"

        cur = None
        count = 0
        errors = 0
        for raw in text.splitlines():
            ln = raw.strip()
            if not ln or ln.startswith(";"):
                continue
            if ln.lower().startswith("windows registry editor"):
                continue
            if ln.startswith("[") and ln.endswith("]"):
                p = ln[1:-1].strip()
                p = re.sub(r"^HKEY_CURRENT_USER\\", "", p, flags=re.I)
                p = re.sub(r"^HKCU\\", "", p, flags=re.I)
                cur = p
                continue
            if cur is None or "=" not in ln:
                continue
            name_part, _, val_part = ln.partition("=")
            name_part = name_part.strip()
            val_part = val_part.strip()
            name = "" if name_part == "@" else name_part.strip('"').replace('\\"', '"')
            name = name.replace("\\\\", "\\")
            try:
                if val_part.startswith('"'):
                    val = val_part.strip('"').replace('\\"', '"').replace("\\\\", "\\")
                    typ = winreg.REG_SZ
                elif val_part.lower().startswith("dword:"):
                    val = int(val_part[6:], 16)
                    typ = winreg.REG_DWORD
                elif val_part.lower().startswith("hex(7):"):
                    hexs = val_part[7:].replace(",", "").replace("\\", "")
                    b = bytes.fromhex(hexs)
                    s = b.decode("utf-16-le", errors="ignore")
                    parts = [x for x in s.split("\x00") if x]
                    val, typ = parts, winreg.REG_MULTI_SZ
                elif val_part.lower().startswith("hex("):
                    continue  # 暂不还原其他 hex 类型
                else:
                    continue
                _set_value(self.hive, cur, name, val, typ)
                count += 1
            except (OSError, ValueError):
                errors += 1
        msg = f"还原完成：写入 {count} 个值"
        if errors:
            msg += f"，{errors} 个失败"
        return True, msg + "（点「让菜单立即生效」刷新右键）"

    def clear_all(self) -> tuple[bool, str]:
        """删除本工具创建的全部菜单项。"""
        n = 0
        for it in self.list_items():
            key = it.key_name if it.enabled else f"_disabled_{it.key_name}"
            if _delete_tree(self.hive, self.item_path(it.scene, key)):
                n += 1
        return True, f"已清理 {n} 项（重启资源管理器后生效）"

    # -- 让菜单立即生效 -----------------------------------------------------
    @staticmethod
    def restart_explorer() -> tuple[bool, str]:
        """重启资源管理器，让右键菜单立即刷新。"""
        import subprocess
        try:
            subprocess.run(
                ["taskkill", "/f", "/im", "explorer.exe"],
                capture_output=True, text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            # Windows 一般会自动拉起 explorer，兜底再启一次
            try:
                subprocess.Popen(
                    ["explorer.exe"],
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except OSError:
                pass
            return True, "资源管理器已重启，右键菜单已刷新"
        except OSError as e:
            return False, f"重启资源管理器失败：{e}"


# ---------------------------------------------------------------------------
# 内置模板：常用动作一键添加
# ---------------------------------------------------------------------------

def _find_exe(*candidates: str) -> str:
    """在常见路径里找一个存在的 exe。"""
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return ""


def build_builtin_templates() -> list[dict]:
    """
    返回内置模板列表。每个模板含三种场景的推荐配置。
    字段: id / name / desc / label / scene / command / icon
    """
    win = os.environ.get("SystemRoot", r"C:\Windows")
    sys32 = os.path.join(win, "System32")
    local = os.environ.get("LOCALAPPDATA", "")
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")

    ps = _find_exe(
        os.path.join(sys32, "WindowsPowerShell", "v1.0", "powershell.exe"),
        os.path.join(sys32, "WindowsPowerShell", "v1.0", "pwsh.exe"),
    )
    cmd = os.path.join(sys32, "cmd.exe")
    notepad = os.path.join(sys32, "notepad.exe")
    explorer = os.path.join(win, "explorer.exe")
    code = _find_exe(
        os.path.join(local, "Programs", "Microsoft VS Code", "Code.exe"),
        os.path.join(pf, "Microsoft VS Code", "Code.exe"),
        os.path.join(pf86, "Microsoft VS Code", "Code.exe"),
    )
    wt = _find_exe(os.path.join(local, "Microsoft", "WindowsApps", "wt.exe"))

    tpls: list[dict] = []

    # --- 1. 复制完整路径 -------------------------------------------------
    tpls.append({
        "id": "copypath",
        "name": "复制完整路径",
        "desc": "把选中文件/文件夹的绝对路径复制到剪贴板",
        "segments": [
            {
                "scene": "file",
                "label": "复制完整路径",
                "command": (
                    f'cmd.exe /c echo %1| clip'
                ),
                "icon": explorer,
            },
            {
                "scene": "dir",
                "label": "复制完整路径",
                "command": (
                    f'cmd.exe /c echo %1| clip'
                ),
                "icon": explorer,
            },
        ],
    })

    # --- 2. 在此处打开 CMD ----------------------------------------------
    tpls.append({
        "id": "cmd_here",
        "name": "在此处打开命令行",
        "desc": "用 cmd.exe 在当前目录打开黑窗口，路径自动切换",
        "segments": [
            {
                "scene": "dir",
                "label": "在此处打开 CMD",
                "command": f'"{cmd}" /s /k pushd "%1"',
                "icon": cmd,
            },
            {
                "scene": "dirbg",
                "label": "在此处打开 CMD",
                "command": f'"{cmd}" /s /k pushd "%V"',
                "icon": cmd,
            },
            {
                "scene": "desktop",
                "label": "在此处打开 CMD",
                "command": f'"{cmd}" /s /k pushd "%V"',
                "icon": cmd,
            },
        ],
    })

    # --- 3. 在此处打开 PowerShell ---------------------------------------
    if ps:
        tpls.append({
            "id": "ps_here",
            "name": "在此处打开 PowerShell",
            "desc": "用 PowerShell 在当前目录打开窗口",
            "segments": [
                {
                    "scene": "dir",
                    "label": "在此处打开 PowerShell",
                    "command": f'"{ps}" -NoExit -Command "Set-Location -LiteralPath \'%1\'"',
                    "icon": ps,
                },
                {
                    "scene": "dirbg",
                    "label": "在此处打开 PowerShell",
                    "command": f'"{ps}" -NoExit -Command "Set-Location -LiteralPath \'%V\'"',
                    "icon": ps,
                },
                {
                    "scene": "desktop",
                    "label": "在此处打开 PowerShell",
                    "command": f'"{ps}" -NoExit -Command "Set-Location -LiteralPath \'%V\'"',
                    "icon": ps,
                },
            ],
        })

    # --- 4. 用 VS Code 打开 ---------------------------------------------
    if code:
        tpls.append({
            "id": "vscode",
            "name": "用 VS Code 打开",
            "desc": "文件直接用 VS Code 打开，文件夹作为工作区打开",
            "segments": [
                {"scene": "file", "label": "用 VS Code 打开",
                 "command": f'"{code}" "%1"', "icon": code},
                {"scene": "dir", "label": "用 VS Code 打开",
                 "command": f'"{code}" "%1"', "icon": code},
                {"scene": "dirbg", "label": "用 VS Code 打开当前目录",
                 "command": f'"{code}" "%V"', "icon": code},
                {"scene": "desktop", "label": "用 VS Code 打开",
                 "command": f'"{code}" "%V"', "icon": code},
            ],
        })

    # --- 5. 用 Windows Terminal 打开 ------------------------------------
    if wt:
        tpls.append({
            "id": "wt_here",
            "name": "在此处打开 Windows Terminal",
            "desc": "用 Windows Terminal 在当前目录打开",
            "segments": [
                {"scene": "dir", "label": "在此处打开终端",
                 "command": f'"{wt}" -d "%1"', "icon": wt},
                {"scene": "dirbg", "label": "在此处打开终端",
                 "command": f'"{wt}" -d "%V"', "icon": wt},
                {"scene": "desktop", "label": "在此处打开终端",
                 "command": f'"{wt}" -d "%V"', "icon": wt},
            ],
        })

    # --- 6. 用记事本打开 ------------------------------------------------
    tpls.append({
        "id": "notepad",
        "name": "用记事本打开",
        "desc": "用系统记事本打开选中文件，方便快速看小文件",
        "segments": [
            {"scene": "file", "label": "用记事本打开",
             "command": f'"{notepad}" "%1"', "icon": notepad},
        ],
    })

    # --- 7. 打开文件所在位置 --------------------------------------------
    tpls.append({
        "id": "reveal",
        "name": "打开所在文件夹",
        "desc": "在资源管理器中定位到选中文件",
        "segments": [
            {"scene": "file", "label": "打开所在文件夹",
             "command": f'"{explorer}" /select,"%1"', "icon": explorer},
        ],
    })

    # --- 8. 复制文件夹路径（Shift 显示）---------------------------------
    tpls.append({
        "id": "copy_dir_shift",
        "name": "复制路径（按住Shift才显示）",
        "desc": "菜单默认隐藏，按住 Shift 右键才出现，保持菜单清爽",
        "segments": [
            {"scene": "file", "label": "复制路径(Shift)",
             "command": 'cmd.exe /c echo %1| clip', "icon": explorer, "extend": True},
        ],
    })

    return tpls


# ---------------------------------------------------------------------------
# 自检入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    m = ContextMenuManager()
    print(f"{APP_TITLE} 核心层自检")
    print("-" * 50)
    items = m.list_items()
    print(f"当前本工具创建的菜单项：{len(items)} 个")
    for it in items:
        flag = "启用" if it.enabled else "停用"
        print(f"  [{SCENES[it.scene][0]}] {it.label} ({flag})")
        print(f"      {it.command}")
    print("-" * 50)
    tpls = build_builtin_templates()
    print(f"内置模板：{len(tpls)} 个")
    for t in tpls:
        print(f"  - {t['name']}：{len(t['segments'])} 个场景配置")
    print("-" * 50)
    print("注册表根路径（HKCU，无需管理员）：")
    for k, v in SCENES.items():
        print(f"  {v[0]:<10} -> {v[1]}")
