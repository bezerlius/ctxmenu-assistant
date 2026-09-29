# -*- coding: utf-8 -*-
"""
Shift 隐藏功能测试 + 界面截图
1. 验证 v_extend 复选框能正确写入 Extended 注册表属性
2. 验证列表状态列显示 ⇧ Shift
3. 验证载入编辑区能带回 extend 状态
4. 截图保存，肉眼确认复选框画的是 ✓ 而不是 ✗
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ctxmenu_gui as G
import ctxmenu_core as C

fails = []
def check(name, cond, extra=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        fails.append(name)

app = G.CtxMenuApp()
app.geometry("1180x790+60+40")
app.update()
time.sleep(0.5)
app.update()

# ---------- 1. 复选框组件自检 ----------
check("CheckChip 类存在", hasattr(G, "CheckChip"))
check("v_extend 变量存在", hasattr(app, "v_extend"))
check("Shift 复选框已创建", hasattr(app, "chip_extend"))

# 初始应为未勾选
check("Shift 默认未勾选", app.v_extend.get() is False)

# 模拟点击（canvas 上派发点击事件）
app.chip_extend._on_click()
app.update()
check("点击后变为勾选", app.v_extend.get() is True)
app.chip_extend._on_click()
app.update()
check("再次点击取消勾选", app.v_extend.get() is False)

# ---------- 2. 添加带 Shift 的项 ----------
app.mgr.clear_all()
notepad = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                       "System32", "notepad.exe")
app.apps = [{"name": "Shift测试项", "target": notepad, "args": "",
             "workdir": os.path.dirname(notepad), "icon": notepad,
             "source": "测试"}]
app.v_appsearch.set("")
app.refresh_app_list()
app.app_list.selection_set(0)
app.on_app_select()

for k in G.SCENE_ORDER:
    app.scene_vars[k].set(k == "file")
app.v_extend.set(True)          # 打开 Shift 隐藏
app.on_add_app()
app.update()

items = app.mgr.list_items()
check("已添加 1 项", len(items) == 1, f"{len(items)} 项")
check("Extended 属性已写入", items and items[0].extend is True,
      f"extend={items[0].extend if items else None}")

# ---------- 3. 列表状态列显示 ----------
vals = app.tree.item(app.tree.get_children()[0], "values")
check("状态列显示 ⇧ Shift", vals[2] == "⇧ Shift", f"实际={vals[2]!r}")

# ---------- 4. 载入编辑区带回 extend ----------
app.tree.selection_set("0")
app.on_load_to_custom()
app.update()
check("载入后 extend 保持", app.v_extend.get() is True,
      f"extend={app.v_extend.get()}")

# ---------- 5. 不带 Shift 的项 ----------
app.v_extend.set(False)
app.scene_vars["file"].set(False)
app.scene_vars["dir"].set(True)
app.v_appname.set("普通项")
app.app_list.selection_set(0)
app.on_app_select()
app.v_appname.set("普通项")
app.on_add_app()
app.update()

normal = [i for i in app.mgr.list_items() if i.label == "普通项"]
check("普通项 extend=False", normal and normal[0].extend is False)
check("共 2 项", len(app.mgr.list_items()) == 2)

# 状态列应有区分
states = [app.tree.item(i, "values")[2] for i in app.tree.get_children()]
check("状态列区分 Shift 与普通",
      "⇧ Shift" in states and any("启用" in s for s in states),
      str(states))
check("状态列文字含 ● 启用中", any(s == "● 启用中" for s in states), str(states))

# ---------- 6. 截图 ----------
app.update()
time.sleep(0.3)
app.update()
try:
    from PIL import ImageGrab  # noqa
    have_pil = True
except ImportError:
    have_pil = False

if have_pil:
    from PIL import ImageGrab
    x, y = app.winfo_rootx(), app.winfo_rooty()
    w, h = app.winfo_width(), app.winfo_height()
    img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
    img.save("_shot.png")
    check("截图已保存", os.path.exists("_shot.png"))
else:
    # 无 PIL 时用 PowerShell 截屏
    app.update_idletasks()
    x, y = app.winfo_rootx(), app.winfo_rooty()
    w, h = app.winfo_width(), app.winfo_height()
    with open("_shot_bounds.txt", "w") as f:
        f.write(f"{x} {y} {w} {h}")
    print(f"[INFO] 无 PIL，窗口边界 {x},{y} {w}x{h} 已写入 _shot_bounds.txt")

# 清理
app.mgr.clear_all()
check("清理干净", len(app.mgr.list_items()) == 0)
app.destroy()

print("\n" + "=" * 52)
print(f"结果：{'全部通过 ✓' if not fails else '失败 -> ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
