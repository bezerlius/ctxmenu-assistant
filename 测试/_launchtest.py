# -*- coding: utf-8 -*-
"""带超时自动关闭的 GUI 启动验证：确认窗口能正常创建、扫描能完成、然后自己退出。"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ctxmenu_gui as G

app = G.CtxMenuApp()
app.geometry("1140x760")

log = []

def probe():
    # 等扫描完成
    for _ in range(40):
        app.update()
        time.sleep(0.1)
    log.append(("应用数", len(app.apps)))
    log.append(("列表可见行", app.app_list.size()))
    # 选中第一个并触发添加
    if app.app_list.size() > 0:
        app.app_list.selection_set(0)
        app.on_app_select()
        log.append(("自动填名", app.v_appname.get()))
    app.update()
    app.after(300, app.destroy)

app.after(200, probe)
app.mainloop()

print("=== GUI 启动验证 ===")
for k, v in log:
    print(f"  {k}: {v}")
if log and log[0][1] > 0:
    print("\n结论：窗口正常创建，应用扫描成功 ✓")
    sys.exit(0)
print("\n结论：未能扫描到应用 ✗")
sys.exit(1)
