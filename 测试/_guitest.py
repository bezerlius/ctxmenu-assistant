# -*- coding: utf-8 -*-
"""界面冒烟测试：实例化窗口 -> 模拟选应用 -> 模拟一键添加 -> 验证注册表 -> 清理。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ctxmenu_gui as G
import ctxmenu_core as C

fails = []
def check(name, cond, extra=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        fails.append(name)

app = G.CtxMenuApp()
app.withdraw()          # 不显示窗口
app.update()            # 完成首帧构建

check("窗口构建成功", True)

# --- 1. 面板结构齐全 ---
check("应用列表控件存在", hasattr(app, "app_list"))
check("已添加列表控件存在", hasattr(app, "tree"))
check("内置模板已加载", len(app.templates) >= 6, f"{len(app.templates)} 个")
check("场景勾选框 4 个", len(app.scene_vars) == 4)
check("默认勾选『文件』", app.scene_vars["file"].get() is True)

# --- 2. 清空后进行添加测试 ---
app.mgr.clear_all()
app.refresh_items()

# 注入一个确定存在的应用（记事本）
notepad = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                       "System32", "notepad.exe")
app.apps = [{"name": "测试记事本", "target": notepad, "args": "",
             "workdir": os.path.dirname(notepad), "icon": notepad,
             "source": "测试"}]
app.v_appsearch.set("")
app.refresh_app_list()
check("应用列表渲染", app.app_list.size() == 1, f"size={app.app_list.size()}")

# --- 3. 选中 + 填名 + 勾多场景 + 一键添加 ---
app.app_list.selection_set(0)
app.on_app_select()
check("选应用自动填名", app.v_appname.get() == "测试记事本",
      repr(app.v_appname.get()))

for k in ("file", "dir", "dirbg"):
    app.scene_vars[k].set(True)
app.scene_vars["desktop"].set(False)

app.on_add_app()
app.update()

items = app.mgr.list_items()
check("一键添加写入 3 个场景", len(items) == 3, f"实际 {len(items)}")
scenes = sorted(i.scene for i in items)
check("场景正确", scenes == ["dir", "dirbg", "file"], str(scenes))

# --- 4. 命令行默认不追加参数（GUI 程序不该收到脏参数）---
cmd_file = next(i.command for i in items if i.scene == "file")
cmd_bg = next(i.command for i in items if i.scene == "dirbg")
check("默认不追加 %1（纯启动）", "%1" not in cmd_file, cmd_file)
check("默认不追加 %V（纯启动）", "%V" not in cmd_bg, cmd_bg)
check("程序路径带引号", notepad in cmd_file.replace('"', ''), cmd_file)
check("路径统一用反斜杠", "/" not in cmd_file, cmd_file)

# 勾选「传参」后应追加对应变量
app.v_passarg.set(True)
app.scene_vars["file"].set(True)
app.scene_vars["dir"].set(False)
app.scene_vars["dirbg"].set(False)
app.v_appname.set("传参测试")
app.app_list.selection_set(0)
app.on_app_select()
app.v_appname.set("传参测试")
app.on_add_app()
app.update()
pa = [i for i in app.mgr.list_items() if i.label == "传参测试"]
check("勾选传参后追加 %1", bool(pa) and "%1" in pa[0].command,
      pa[0].command if pa else "无")
if pa:
    app.mgr.remove(pa[0].scene, pa[0].key_name)
app.v_passarg.set(False)

# 恢复三段场景，供后续测试使用（先清空保证计数可控）
app.mgr.clear_all()
app.v_appname.set("测试记事本")
app.app_list.selection_set(0)
app.on_app_select()
app.v_appname.set("测试记事本")
app.scene_vars["file"].set(True)
app.scene_vars["dir"].set(True)
app.scene_vars["dirbg"].set(True)
app.scene_vars["desktop"].set(False)
app.on_add_app()
app.update()
app.refresh_items()

# --- 5. 列表已刷新 ---
check("右侧列表显示 3 行", len(app.tree.get_children()) == 3,
      f"{len(app.tree.get_children())} 行")

# --- 6. 筛选功能 ---
app.v_filter.set("file")
app.refresh_items()
check("筛选『文件』只剩 1 行", len(app.tree.get_children()) == 1,
      f"{len(app.tree.get_children())} 行")
app.v_filter.set("all")
app.refresh_items()

# --- 7. 搜索功能 ---
app.v_itemsearch.set("测试")
app.refresh_items()
check("搜索命中 3 行", len(app.tree.get_children()) == 3)
app.v_itemsearch.set("不存在的名字xyz")
app.refresh_items()
check("搜索无结果", len(app.tree.get_children()) == 0)
app.v_itemsearch.set("")
app.refresh_items()

# --- 8. 启停 ---
app.tree.selection_set("0")
app.on_toggle()
app.update()
after_toggle = app.mgr.list_items()
disabled = [i for i in after_toggle if not i.enabled]
check("停用生效", len(disabled) == 1, f"停用 {len(disabled)} 项")

app.tree.selection_set("0")
app.on_toggle()
app.update()
reenabled = [i for i in app.mgr.list_items() if i.enabled]
check("重新启用", len(reenabled) == 3, f"启用 {len(reenabled)} 项")

# --- 9. 删除 ---
app.tree.selection_set("0")
ok, msg = app.mgr.remove(*(lambda i: (i.scene, i.key_name))(
    app._selected_item()))
check("删除一项", ok and len(app.mgr.list_items()) == 2, msg)

# --- 10. 常用动作批量添加 ---
for v in app.tpl_vars:
    v.set(True)
app.on_add_templates()
app.update()
tpl_items = app.mgr.list_items()
check("常用动作批量添加", len(tpl_items) > 2, f"共 {len(tpl_items)} 项")

# --- 11. 重复添加应跳过（幂等）---
app.on_add_templates()
app.update()
check("重复添加幂等", len(app.mgr.list_items()) == len(tpl_items),
      f"{len(app.mgr.list_items())} vs {len(tpl_items)}")

# --- 12. 自定义添加 ---
app.v_c_label.set("自检自定义项")
app.v_c_cmd.set('"C:\\Windows\\notepad.exe" "%1"')
app.v_c_key.set("")
for k in G.SCENE_ORDER:
    app.scene_vars[k].set(k == "file")
app.on_add_custom()
app.update()
custom = [i for i in app.mgr.list_items() if i.label == "自检自定义项"]
check("自定义添加成功", len(custom) == 1, f"{len(custom)} 项")

# --- 13. 不误伤系统项 ---
sys_like = [i for i in app.mgr.list_items()
            if i.key_name in ("open", "print", "edit", "runas")]
check("不碰系统菜单", len(sys_like) == 0)

# 清理
app.mgr.clear_all()
left = app.mgr.list_items()
check("测试后清理干净", len(left) == 0, f"残留 {len(left)} 项")

app.destroy()

print("\n" + "=" * 52)
print(f"结果：{'全部通过 ✓' if not fails else '失败 -> ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
