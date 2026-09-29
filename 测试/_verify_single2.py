# -*- coding: utf-8 -*-
"""
正确的单实例验证：以「窗口数量」为准，而不是 Popen 返回的进程。
PyInstaller --onefile 会有引导进程，Popen 拿到的那个退出是正常的。
"""
import ctypes
import ctypes.wintypes as wt
import subprocess
import time
import os

EXE = r"dist\右键菜单助手.exe"
user32 = ctypes.windll.user32


def count_windows():
    hits = []

    def cb(hwnd, _lp):
        if user32.IsWindowVisible(hwnd):
            ln = user32.GetWindowTextLengthW(hwnd)
            if ln > 0:
                buf = ctypes.create_unicode_buffer(ln + 1)
                user32.GetWindowTextW(hwnd, buf, ln + 1)
                if buf.value == "一键自定义右键菜单助手":
                    hits.append(hwnd)
        return True

    CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    user32.EnumWindows(CB(cb), 0)
    return hits


def kill():
    subprocess.run(["taskkill", "/F", "/IM", "右键菜单助手.exe"],
                   capture_output=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


print("=" * 66)
print("单实例守卫验证（以窗口数为准）")
print("=" * 66)

kill()
time.sleep(1.5)
print(f"起始窗口数: {len(count_windows())}\n")

print("[第1次启动]")
p1 = subprocess.Popen([EXE])
time.sleep(11)
w1 = count_windows()
print(f"  窗口数: {len(w1)}   {'✓ 正常打开' if len(w1) == 1 else '异常'}")
hwnd1 = w1[0] if w1 else None

print("\n[第2次启动]  应激活已有窗口，不新开")
p2 = subprocess.Popen([EXE])
time.sleep(8)
w2 = count_windows()
print(f"  窗口数: {len(w2)}")
same = bool(w2) and w2[0] == hwnd1
print(f"  窗口句柄是否仍是同一个: {same}  (原={hwnd1}, 现={w2[0] if w2 else None})")

print("\n[第3次启动]  再确认一次")
p3 = subprocess.Popen([EXE])
time.sleep(8)
w3 = count_windows()
print(f"  窗口数: {len(w3)}")

print()
print("=" * 66)
ok = len(w1) == 1 and len(w2) == 1 and len(w3) == 1
if ok:
    print("✓ 单实例守卫完全生效：始终只有 1 个窗口，重复启动被正确拦截")
else:
    print(f"✗ 守卫异常：{len(w1)} -> {len(w2)} -> {len(w3)}")

for p in (p1, p2, p3):
    try:
        p.kill()
    except Exception:
        pass
kill()
time.sleep(1)
print(f"清理后窗口数: {len(count_windows())}")
