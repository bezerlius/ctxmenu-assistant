# -*- coding: utf-8 -*-
"""
ctxmenu_single.py —— 单实例守卫

问题背景：右键菜单点击启动程序时，如果程序已经在运行，
新实例会再开一个窗口，而且往往被旧窗口盖住，用户看到的就是「点了没反应」。

解决方案：
  1. 用命名互斥量（Mutex）实现跨进程单实例检测
  2. 若已有实例在运行，则找到它的窗口 -> 还原 -> 置顶 -> 激活
  3. 然后本进程静默退出，不再开第二个窗口

纯 ctypes 实现，零第三方依赖。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import sys

# ---- Win32 常量 ----------------------------------------------------------
ERROR_ALREADY_EXISTS = 183
SW_RESTORE = 9
SW_SHOW = 5
HWND_TOP = 0

k32 = ctypes.windll.kernel32
user32 = ctypes.windll.user32


# ---- 互斥量 --------------------------------------------------------------

def acquire_mutex(name: str = "Global\\CtxMenuAssistant_SingleInstance"):
    """
    尝试创建命名互斥量。
    返回 (handle, is_first)。
      is_first=True  -> 本进程是第一个实例，正常继续
      is_first=False -> 已有实例在运行，应激活它然后退出
    """
    # Windows 保留字，用 Local\ 避免权限问题；换成本机范围即可
    name = name.replace("Global\\", "Local\\")
    handle = k32.CreateMutexW(None, False, name)
    if not handle:
        # 拿不到互斥量时退化为"总是新实例"，保证程序至少能用
        return None, True
    already = (k32.GetLastError() == ERROR_ALREADY_EXISTS)
    return handle, (not already)


def release_mutex(handle) -> None:
    if handle:
        try:
            k32.ReleaseMutex(handle)
            k32.CloseHandle(handle)
        except Exception:  # noqa: BLE001
            pass


# ---- 窗口激活 ------------------------------------------------------------

def _window_pids():
    """返回 {pid: [hwnd, ...]}，只含可见的顶层窗口。"""
    result: dict[int, list[int]] = {}

    def cb(hwnd, _lp):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wt.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        result.setdefault(pid.value, []).append(hwnd)
        return True

    CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    user32.EnumWindows(CB(cb), 0)
    return result


def _find_other_instance_windows() -> list[int]:
    """
    找出「本程序的其他实例」的窗口。
    注意 PyInstaller --onefile 会有一个父进程 + 一个子进程，
    我们要排除自己所在进程树，只找真正的另一个实例。
    """
    my_pid = k32.GetCurrentProcessId()
    # PyInstaller onefile 会 fork 子进程，父进程退出后子进程继续。
    # 简单可靠的做法：找标题匹配的窗口，且 pid 不等于自己。
    hwnds = []
    titles: dict[int, str] = {}

    def cb(hwnd, _lp):
        if not user32.IsWindowVisible(hwnd):
            return True
        ln = user32.GetWindowTextLengthW(hwnd)
        if ln <= 0:
            return True
        buf = ctypes.create_unicode_buffer(ln + 1)
        user32.GetWindowTextW(hwnd, buf, ln + 1)
        titles[hwnd] = buf.value
        return True

    CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    user32.EnumWindows(CB(cb), 0)

    for hwnd, title in titles.items():
        if not title or "右键菜单助手" not in title:
            continue
        pid = wt.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == my_pid:
            continue
        # 排除明显的非主窗口（如浏览器标题里恰好含关键字）
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if cls.value in ("TkTopLevel", "TkChild"):
            hwnds.append(hwnd)
    return hwnds


def activate_existing_window() -> bool:
    """
    激活已在运行的实例窗口：还原 + 置顶 + 抢焦点。
    成功返回 True。
    """
    hwnds = _find_other_instance_windows()
    if not hwnds:
        return False

    hwnd = hwnds[0]
    # 若最小化则还原
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    else:
        user32.ShowWindow(hwnd, SW_SHOW)

    # 置顶 + 抢焦点（Windows 有前台锁，用附加线程输入的技巧绕过）
    user32.SetWindowPos(hwnd, HWND_TOP, 0, 0, 0, 0, 0x0001 | 0x0002)
    user32.SetForegroundWindow(hwnd)
    user32.BringWindowToTop(hwnd)

    # 若 SetForegroundWindow 被系统拒绝，尝试附加输入线程
    fg = user32.GetForegroundWindow()
    if fg != hwnd:
        fg_thread = user32.GetWindowThreadProcessId(fg, None)
        my_thread = k32.GetCurrentThreadId()
        target_thread = user32.GetWindowThreadProcessId(hwnd, None)
        user32.AttachThreadInput(my_thread, target_thread, True)
        user32.SetForegroundWindow(hwnd)
        user32.AttachThreadInput(my_thread, target_thread, False)
    return True


def already_running() -> bool:
    """给主程序启动时调用的便捷函数。"""
    return bool(_find_other_instance_windows())


# ---- 自检 ----------------------------------------------------------------

if __name__ == "__main__":
    print("单实例模块自检")
    print("-" * 50)
    h, first = acquire_mutex()
    print(f"第一个互斥量: first={first}")
    h2, first2 = acquire_mutex()
    print(f"第二个互斥量: first={first2}  (同一进程内，应为 False 或 True)")
    release_mutex(h)
    release_mutex(h2)
    print()
    print(f"检测到其他实例窗口: {already_running()}")
    print(f"标题匹配窗口: {_find_other_instance_windows()}")
