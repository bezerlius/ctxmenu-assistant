# -*- coding: utf-8 -*-
"""启动界面并保持打开，供外部截屏验证渲染效果。"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ctxmenu_gui as G

app = G.CtxMenuApp()
app.geometry("1180x790+40+30")

# 预置演示数据：让列表里有 Shift 项和普通项
notepad = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                       "System32", "notepad.exe")
app.apps = [
    {"name": "用记事本打开", "target": notepad, "args": "",
     "workdir": os.path.dirname(notepad), "icon": notepad, "source": "演示"},
    {"name": "Windows Terminal", "target": notepad, "args": "",
     "workdir": os.path.dirname(notepad), "icon": notepad, "source": "演示"},
    {"name": "Visual Studio Code", "target": notepad, "args": "",
     "workdir": os.path.dirname(notepad), "icon": notepad, "source": "演示"},
]
app.v_appsearch.set("")
app.refresh_app_list()

# 造假数据让右侧列表有内容
import ctxmenu_core as C
app.mgr.clear_all()
for i, (lbl, sc, ext) in enumerate([
        ("用记事本打开", "file", False),
        ("复制路径(Shift)", "file", True),
        ("此处打开 CMD", "dirbg", False)]):
    app.mgr.add(C.MenuItem(scene=sc, key_name=f"_demo_{i}", label=lbl,
                           command=f'"{notepad}" "%1"', icon=notepad,
                           extend=ext))
app.refresh_items()

# 勾选状态：让界面同时展示「已勾选」和「未勾选」两种状态
app.scene_vars["file"].set(True)
app.scene_vars["folder"] = None  # 不存在，跳过
app.scene_vars["dir"].set(False)
app.scene_vars["dirbg"].set(True)
app.scene_vars["desktop"].set(False)
app.v_extend.set(True)
app.app_list.selection_set(0)
app.on_app_select()
app.say("已选：用记事本打开　C:\\Windows\\System32\\notepad.exe")

app.after(9000, lambda: (app.mgr.clear_all(), app.destroy()))
app.mainloop()
print("已关闭")
