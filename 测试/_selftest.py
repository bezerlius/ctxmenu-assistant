# -*- coding: utf-8 -*-
"""核心层真机回归测试：写入 -> 读取 -> 启停 -> 删除 -> 清理，全程用 HKCU 实际测试后复原。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ctxmenu_core import ContextMenuManager, MenuItem, SCENES

m = ContextMenuManager()
fails = []

def check(name, cond, extra=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        fails.append(name)

before = {i.key_name for i in m.list_items()}
print(f"测试前已有项：{before or '无'}\n")

# 1. 新增（file 场景）
it = MenuItem(scene="file", key_name="_selftest_a", label="自检项A",
              command='cmd.exe /c echo %1', icon=r"C:\Windows\explorer.exe")
ok, msg = m.add(it)
check("新增菜单项", ok, msg)

# 2. 读取回验
found = m.find("file", "_selftest_a")
check("读回菜单项", found is not None and found.label == "自检项A",
      f"label={found.label if found else None}")
check("命令行正确", found and found.command == 'cmd.exe /c echo %1')
check("图标正确", found and found.icon == r"C:\Windows\explorer.exe")

# 3. 带 Extended（Shift 显示）
it2 = MenuItem(scene="dir", key_name="_selftest_b", label="自检项B",
               command='cmd.exe /c pushd "%1"', extend=True)
ok2, _ = m.add(it2)
f2 = m.find("dir", "_selftest_b")
check("Extended 标记写入", ok2 and f2 and f2.extend is True)

# 4. 停用 -> 应从启用列表消失
ok3, msg3 = m.set_enabled("file", "_selftest_a", False)
enabled_keys = {i.key_name for i in m.list_items() if i.enabled}
check("停用后不在启用列表", ok3 and "_selftest_a" not in enabled_keys, msg3)
all_keys = {i.key_name for i in m.list_items()}
check("停用后仍在总列表(带 disabled 标记)", "_selftest_a" in all_keys)
still = m.find("file", "_selftest_a")
check("停用状态读取正确", still is not None and still.enabled is False)

# 5. 重新启用
ok4, msg4 = m.set_enabled("file", "_selftest_a", True)
enabled_keys2 = {i.key_name for i in m.list_items() if i.enabled}
check("重新启用成功", ok4 and "_selftest_a" in enabled_keys2, msg4)
back = m.find("file", "_selftest_a")
check("重新启用后命令行仍在", back and back.command == 'cmd.exe /c echo %1')

# 6. 覆盖同名项（改名字）
it.label = "自检项A改名"
ok5, _ = m.add(it)
renamed = m.find("file", "_selftest_a")
check("覆盖更新生效", ok5 and renamed and renamed.label == "自检项A改名")

# 7. 删除
ok6, msg6 = m.remove("file", "_selftest_a")
check("删除菜单项", ok6 and m.find("file", "_selftest_a") is None, msg6)

ok7, _ = m.remove("dir", "_selftest_b")
check("删除第二项", ok7 and m.find("dir", "_selftest_b") is None)

# 8. 删除不存在的项应返回 False
ok8, _ = m.remove("file", "_not_exist_xyz")
check("删除不存在项返回False", ok8 is False)

# 9. 不误伤系统项：确认系统自带项未被列进来
sys_items = [i for i in m.list_items() if not i.key_name.startswith("_selftest")]
check("不误列系统/第三方菜单项", all(i.key_name not in ("open", "print", "edit")
                                     for i in sys_items), f"列到 {len(sys_items)} 项")

# 10. 备份导出 -> 清理 -> 还原
import tempfile
bak = os.path.join(tempfile.gettempdir(), "ctxmenu_selftest.reg")
it3 = MenuItem(scene="desktop", key_name="_selftest_c", label="自检项C",
               command='cmd.exe /c echo hi')
m.add(it3)
ok9, msg9 = m.export_backup(bak)
check("备份导出", ok9 and os.path.exists(bak), msg9)
if os.path.exists(bak):
    sz = os.path.getsize(bak)
    check("备份文件非空", sz > 100, f"{sz} bytes")

ok10, msg10 = m.clear_all()
check("一键清理", ok10 and len(m.list_items()) == 0, msg10)

if os.path.exists(bak):
    ok11, msg11 = m.import_backup(bak)
    restored = {i.key_name for i in m.list_items()}
    check("备份还原", ok11 and "_selftest_c" in restored, msg11)
    os.remove(bak)

# 最终清理，保证不留下任何痕迹
m.clear_all()

after = {i.key_name for i in m.list_items()}
print(f"\n测试后残留：{after or '无'}")
check("测试无残留", after == before and len(after) == 0)

print("\n" + "=" * 50)
print(f"结果：{'全部通过 ✓' if not fails else '存在失败 -> ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
