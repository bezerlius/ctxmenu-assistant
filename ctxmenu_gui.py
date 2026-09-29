# -*- coding: utf-8 -*-
"""
ctxmenu_gui.py —— 一键自定义右键菜单助手 · 图形界面

主流程（对齐参考图）：
   ① 左侧选一个软件（快捷方式，自动扫描开始菜单）
   ② 勾选要加到哪里（文件 / 文件夹 / 文件夹空白 / 桌面）
   ③ 命名 + 一键添加
   下方列表展示已添加的菜单，支持一键删除。

其余能力：
   · 常规动作一键添加（复制路径 / 在此处打开 CMD 等）
   · 手动自定义命令
   · 备份还原、一键清空
"""

from __future__ import annotations

import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ctxmenu_core import (  # noqa: E402
    APP_TITLE, SCENES, MAX_LABEL_LEN,
    ContextMenuManager, MenuItem, build_builtin_templates,
)
from ctxmenu_apps import (  # noqa: E402
    scan_all_apps, build_command, suggest_key, parse_lnk,
)

# ---------------------------------------------------------------------------
# 视觉：浅色主题
# ---------------------------------------------------------------------------
C_BG = "#f5f7fa"
C_CARD = "#ffffff"
C_BORDER = "#e1e5ec"
C_TEXT = "#1f2430"
C_SUB = "#6b7280"
C_ACCENT = "#2f6feb"
C_ACCENT_D = "#2559c4"
C_OK = "#1f9d55"
C_WARN = "#d97706"
C_DANGER = "#dc2626"
C_SEL = "#dde8ff"
C_HEAD = "#eef1f6"

FONT = ("Microsoft YaHei UI", 10)
FONT_S = ("Microsoft YaHei UI", 9)
FONT_XS = ("Microsoft YaHei UI", 8)
FONT_B = ("Microsoft YaHei UI", 11, "bold")
FONT_T = ("Microsoft YaHei UI", 16, "bold")
FONT_MONO = ("Consolas", 9)

# 场景勾选框顺序：界面上按这个顺序排列
SCENE_ORDER = ["file", "dir", "dirbg", "desktop"]
SCENE_SHORT = {
    "file": "文件",
    "dir": "文件夹",
    "dirbg": "文件夹空白",
    "desktop": "桌面空白",
}


def _btn(parent, text, cmd, kind="normal", width=None, font=None):
    style_map = {
        "normal": (C_CARD, C_TEXT, C_BORDER),
        "primary": (C_ACCENT, "#ffffff", C_ACCENT),
        "danger": (C_CARD, C_DANGER, "#f0b9b9"),
        "ok": (C_CARD, C_OK, "#a9dcbd"),
    }
    bg, fg, bd = style_map.get(kind, style_map["normal"])
    b = tk.Button(
        parent, text=text, command=cmd,
        bg=bg, fg=fg,
        activebackground=(C_ACCENT_D if kind == "primary" else C_SEL),
        activeforeground=("#ffffff" if kind == "primary" else fg),
        relief="flat", bd=0, highlightthickness=1,
        highlightbackground=bd, highlightcolor=bd,
        font=font or FONT, padx=12, pady=7, cursor="hand2",
    )
    if width:
        b.configure(width=width)
    return b


class CheckChip(tk.Frame):
    """
    自绘「✓ 复选框」标签。
    不用 ttk.Checkbutton —— clam 主题在选中态画的是 ✗ 而不是 ✓，
    看着像「错误 / 禁用」，这里完全自绘保证是勾。

    外观：[ ✓ ] 标签文字    选中=蓝底白勾 + 深色文字；未选=白底灰框
    """

    BOX = 16          # 方框边长

    def __init__(self, parent, text, variable: tk.BooleanVar,
                 bg=C_CARD, command=None):
        super().__init__(parent, bg=bg, cursor="hand2")
        self.var = variable
        self.text = text
        self._bg = bg
        self._command = command
        self._hover = False

        self.canvas = tk.Canvas(self, width=self.BOX, height=self.BOX,
                                bg=bg, highlightthickness=0, bd=0,
                                cursor="hand2")
        self.canvas.pack(side="left")

        self.label = tk.Label(self, text=text, bg=bg, fg=C_TEXT,
                              font=FONT, cursor="hand2")
        self.label.pack(side="left", padx=(6, 0))

        for w in (self, self.canvas, self.label):
            w.bind("<Button-1>", self._on_click)
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)

        self.var.trace_add("write", lambda *_: self._draw())
        self._draw()

    def _on_click(self, _evt=None):
        self.var.set(not self.var.get())
        if self._command:
            self._command()

    def _on_enter(self, _evt=None):
        self._hover = True
        self._draw()

    def _on_leave(self, _evt=None):
        self._hover = False
        self._draw()

    def _draw(self):
        c = self.canvas
        c.delete("all")
        s = self.BOX
        checked = bool(self.var.get())

        if checked:
            fill = C_ACCENT_D if self._hover else C_ACCENT
            c.create_rectangle(0, 0, s, s, fill=fill, outline=fill)
            # 白色对勾 ✓
            c.create_line(3.5, 8.2, 6.6, 11.6, 12.4, 4.6,
                          fill="#ffffff", width=2.2,
                          capstyle="round", joinstyle="round")
        else:
            fill = "#eef3fd" if self._hover else C_CARD
            outline = C_ACCENT if self._hover else "#c3cbd8"
            c.create_rectangle(0, 0, s, s, fill=fill, outline=outline, width=1.4)

    def set_bg(self, bg):
        """外层背景变色时同步（用于放在非卡片容器里）。"""
        self._bg = bg
        self.configure(bg=bg)
        self.canvas.configure(bg=bg)
        self.label.configure(bg=bg)



class CtxMenuApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.mgr = ContextMenuManager()
        self.apps: list[dict] = []
        self.visible_apps: list[dict] = []
        self.all_items: list[MenuItem] = []
        self.visible_items: list[MenuItem] = []

        # 场景勾选
        self.scene_vars = {k: tk.BooleanVar(value=(k == "file")) for k in SCENE_ORDER}
        self.v_extend = tk.BooleanVar(value=False)   # Shift 隐藏开关
        self.v_passarg = tk.BooleanVar(value=False)  # 是否把路径传给程序
        self.v_appname = tk.StringVar()
        self.v_key = tk.StringVar()
        self.v_args = tk.StringVar()
        self.v_appsearch = tk.StringVar()
        self.v_itemsearch = tk.StringVar()
        self.v_status = tk.StringVar()

        self.title(APP_TITLE)
        self.geometry("1140x760")
        self.minsize(1020, 680)
        self.configure(bg=C_BG)
        ico = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.ico")
        if os.path.exists(ico):
            try:
                self.iconbitmap(ico)
            except tk.TclError:
                pass

        self._init_style()
        self._build_header()
        self._build_main()
        self._build_status()

        # 首屏先渲染空态，再后台扫描应用
        self.refresh_items()
        self.after(80, self.scan_apps_async)

    # ==================================================================
    # 样式
    # ==================================================================
    def _init_style(self):
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure("CM.Treeview", background=C_CARD, fieldbackground=C_CARD,
                     foreground=C_TEXT, rowheight=32, borderwidth=0, font=FONT)
        st.configure("CM.Treeview.Heading", background=C_HEAD, foreground=C_SUB,
                     relief="flat", font=("Microsoft YaHei UI", 9, "bold"),
                     padding=(8, 8))
        st.map("CM.Treeview", background=[("selected", C_SEL)],
               foreground=[("selected", C_TEXT)])

        # Notebook：选中页签用白色底 + 蓝色文字 + 顶部蓝条，未选中灰底
        st.configure("CM.TNotebook", background=C_BG, borderwidth=0,
                     tabmargins=(0, 6, 0, 0), tabposition="nw")
        st.configure("CM.TNotebook.Tab", background="#e8ecf3", foreground=C_SUB,
                     padding=(22, 10), font=FONT, borderwidth=0,
                     lightcolor=C_BORDER, darkcolor=C_BORDER)
        st.map("CM.TNotebook.Tab",
               background=[("selected", C_CARD), ("active", "#f0f3f8")],
               foreground=[("selected", C_ACCENT), ("active", C_TEXT)],
               expand=[("selected", (0, 0, 0, 0))])

    # ==================================================================
    # 顶栏
    # ==================================================================
    def _build_header(self):
        h = tk.Frame(self, bg=C_CARD, height=84)
        h.pack(fill="x", side="top")
        h.pack_propagate(False)

        inner = tk.Frame(h, bg=C_CARD)
        inner.pack(fill="both", expand=True, padx=22, pady=14)

        left = tk.Frame(inner, bg=C_CARD)
        left.pack(side="left", fill="y")

        # 标题行：图标块 + 主标题
        title_row = tk.Frame(left, bg=C_CARD)
        title_row.pack(anchor="w")
        badge = tk.Canvas(title_row, width=30, height=30, bg=C_CARD,
                          highlightthickness=0, bd=0)
        badge.pack(side="left", pady=(1, 0))
        badge.create_rectangle(0, 0, 30, 30, fill=C_ACCENT, outline=C_ACCENT)
        badge.create_line(7, 10, 23, 10, fill="#ffffff", width=2.2,
                          capstyle="round")
        badge.create_line(7, 15, 23, 15, fill="#ffffff", width=2.2,
                          capstyle="round")
        badge.create_line(7, 20, 17, 20, fill="#ffffff", width=2.2,
                          capstyle="round")
        tk.Label(title_row, text=APP_TITLE, bg=C_CARD, fg=C_TEXT,
                 font=FONT_T).pack(side="left", padx=(10, 0))

        # 副标题行：改成分隔点排版，读起来更轻松
        tk.Label(
            left,
            text="选软件  ›  勾选位置  ›  一键添加        "
                 "仅写当前用户 · 免管理员权限 · 随时可撤",
            bg=C_CARD, fg=C_SUB, font=FONT_S,
        ).pack(anchor="w", pady=(7, 0))

        right = tk.Frame(inner, bg=C_CARD)
        right.pack(side="right", fill="y")
        holder = tk.Frame(right, bg=C_CARD)
        holder.pack(expand=True)
        _btn(holder, "↻  让菜单立即生效", self.on_restart_explorer,
             kind="primary").pack()

        tk.Frame(self, bg=C_BORDER, height=1).pack(fill="x", side="top")

    # ==================================================================
    # 主体：左右分栏
    # ==================================================================
    def _build_main(self):
        wrap = tk.Frame(self, bg=C_BG)
        wrap.pack(fill="both", expand=True, padx=18, pady=16)

        paned = tk.PanedWindow(wrap, orient="horizontal", bg=C_BG,
                               sashwidth=8, sashrelief="flat", bd=0)
        paned.pack(fill="both", expand=True)

        left = tk.Frame(paned, bg=C_BG, width=430)
        right = tk.Frame(paned, bg=C_BG, width=640)
        paned.add(left, minsize=360)
        paned.add(right, minsize=520)

        self._build_left(left)
        self._build_right(right)

    # ------------------------------------------------------------------
    # 左栏：添加菜单（三种方式用 Notebook 分页）
    # ------------------------------------------------------------------
    def _build_left(self, parent):
        tk.Label(parent, text="① 添加右键菜单", bg=C_BG, fg=C_TEXT,
                 font=FONT_B).pack(anchor="w", pady=(0, 8))

        nb = ttk.Notebook(parent, style="CM.TNotebook")
        nb.pack(fill="both", expand=True)

        tab_app = tk.Frame(nb, bg=C_CARD)
        tab_quick = tk.Frame(nb, bg=C_CARD)
        tab_custom = tk.Frame(nb, bg=C_CARD)
        nb.add(tab_app, text="  选软件添加  ")
        nb.add(tab_quick, text="  常用动作  ")
        nb.add(tab_custom, text="  自定义  ")
        self.nb = nb

        self._build_tab_app(tab_app)
        self._build_tab_quick(tab_quick)
        self._build_tab_custom(tab_custom)

    # ---- 页签1：选软件添加（主路径）----------------------------------
    def _build_tab_app(self, p):
        pad = tk.Frame(p, bg=C_CARD)
        pad.pack(fill="both", expand=True, padx=14, pady=12)

        # 搜索行
        sr = tk.Frame(pad, bg=C_CARD)
        sr.pack(fill="x")
        tk.Label(sr, text="搜索软件", bg=C_CARD, fg=C_SUB, font=FONT_S).pack(side="left")
        ent = tk.Entry(sr, textvariable=self.v_appsearch, font=FONT, bg="#fbfcfe",
                       fg=C_TEXT, relief="flat", highlightthickness=1,
                       highlightbackground=C_BORDER, highlightcolor=C_ACCENT)
        ent.pack(side="left", fill="x", expand=True, padx=(8, 6), ipady=5)
        self._btn_small(sr, "重扫", self.scan_apps_async).pack(side="left")

        self.app_hint = tk.Label(pad, text="正在扫描本机软件…", bg=C_CARD,
                                 fg=C_SUB, font=FONT_XS, anchor="w")
        self.app_hint.pack(fill="x", pady=(6, 4))

        # 应用列表
        box = tk.Frame(pad, bg=C_BORDER, highlightthickness=1,
                       highlightbackground=C_BORDER)
        box.pack(fill="both", expand=True)
        self.app_list = tk.Listbox(
            box, bg=C_CARD, fg=C_TEXT, selectbackground=C_SEL,
            selectforeground=C_TEXT, relief="flat", bd=0, highlightthickness=0,
            font=FONT, activestyle="none", exportselection=False,
        )
        vs = ttk.Scrollbar(box, orient="vertical", command=self.app_list.yview)
        self.app_list.configure(yscrollcommand=vs.set)
        vs.pack(side="right", fill="y")
        self.app_list.pack(fill="both", expand=True, padx=1, pady=1)
        self.app_list.bind("<<ListboxSelect>>", self.on_app_select)
        self.app_list.bind("<Double-Button-1>", lambda e: self.on_add_app())

        self.v_appsearch.trace_add("write", lambda *_: self.refresh_app_list())

        # 底部：命名 + 场景 + 按钮
        form = tk.Frame(pad, bg=C_CARD)
        form.pack(fill="x", pady=(10, 0))

        r1 = tk.Frame(form, bg=C_CARD)
        r1.pack(fill="x")
        tk.Label(r1, text="菜单名称", bg=C_CARD, fg=C_TEXT, font=FONT,
                 width=9, anchor="w").pack(side="left")
        tk.Entry(r1, textvariable=self.v_appname, font=FONT, bg="#fbfcfe",
                 fg=C_TEXT, relief="flat", highlightthickness=1,
                 highlightbackground=C_BORDER, highlightcolor=C_ACCENT
                 ).pack(side="left", fill="x", expand=True, ipady=5)
        tk.Label(r1, text="可自定义", bg=C_CARD, fg=C_SUB, font=FONT_XS
                 ).pack(side="left", padx=(6, 0))

        r2 = tk.Frame(form, bg=C_CARD)
        r2.pack(fill="x", pady=(9, 0))
        tk.Label(r2, text="添加到", bg=C_CARD, fg=C_TEXT, font=FONT,
                 width=9, anchor="w").pack(side="left", anchor="n")
        chips = tk.Frame(r2, bg=C_CARD)
        chips.pack(side="left", fill="x", expand=True)
        for idx, k in enumerate(SCENE_ORDER):
            c = CheckChip(chips, SCENE_SHORT[k], self.scene_vars[k],
                          bg=C_CARD, command=self._on_scene_chip)
            c.pack(side="left", padx=(0 if idx == 0 else 16, 0))

        # Shift 隐藏开关：让不常用的菜单项只在按住 Shift 右键时才出现
        r2b = tk.Frame(form, bg=C_CARD)
        r2b.pack(fill="x", pady=(7, 0))
        tk.Label(r2b, text="", bg=C_CARD, font=FONT,
                 width=9).pack(side="left")
        self.chip_extend = CheckChip(
            r2b, "仅在按住 Shift 右键时显示（保持菜单清爽）",
            self.v_extend, bg=C_CARD)
        self.chip_extend.pack(side="left")

        # 传参开关：是否需要把选中的文件/文件夹路径交给该程序
        r2c = tk.Frame(form, bg=C_CARD)
        r2c.pack(fill="x", pady=(7, 0))
        tk.Label(r2c, text="", bg=C_CARD, font=FONT,
                 width=9).pack(side="left")
        self.chip_passarg = CheckChip(
            r2c, "把选中的文件/文件夹路径传给该程序（如用记事本打开文件）",
            self.v_passarg, bg=C_CARD, command=self._on_passarg_toggle)
        self.chip_passarg.pack(side="left")

        r3 = tk.Frame(form, bg=C_CARD)
        r3.pack(fill="x", pady=(9, 0))
        tk.Label(r3, text="附加参数", bg=C_CARD, fg=C_TEXT, font=FONT,
                 width=9, anchor="w").pack(side="left")
        self.entry_args = tk.Entry(r3, textvariable=self.v_args, font=FONT_MONO,
                                   bg="#fbfcfe", fg=C_TEXT, relief="flat",
                                   highlightthickness=1,
                                   highlightbackground=C_BORDER,
                                   highlightcolor=C_ACCENT)
        self.entry_args.pack(side="left", fill="x", expand=True, ipady=5)
        self.lbl_args_hint = tk.Label(r3, text="", bg=C_CARD, fg=C_SUB,
                                      font=FONT_XS)
        self.lbl_args_hint.pack(side="left", padx=(6, 0))
        self._on_passarg_toggle()

        btns = tk.Frame(form, bg=C_CARD)
        btns.pack(fill="x", pady=(13, 2))
        _btn(btns, "＋  一键添加菜单", self.on_add_app,
             kind="primary").pack(side="left", fill="x", expand=True)
        self._btn_small(btns, "浏览 exe…", self.on_browse_exe).pack(side="left",
                                                                padx=(8, 0))

    def _on_passarg_toggle(self):
        """传参开关状态变化时，提示会追加哪个变量。"""
        if not hasattr(self, "lbl_args_hint"):
            return
        if self.v_passarg.get():
            sc = self._checked_scenes()
            if sc and sc[0] in ("file", "dir"):
                var = "%1"
            elif sc:
                var = "%V"
            else:
                var = "%1"
            self.lbl_args_hint.configure(text=f"将追加 {var}")
            self.entry_args.configure(state="normal")
        else:
            self.lbl_args_hint.configure(text="纯启动程序，不追加参数")
            self.entry_args.configure(state="normal")

    def _on_scene_chip(self):
        """勾选场景变化时的轻提示。"""
        names = [SCENE_SHORT[k] for k in SCENE_ORDER if self.scene_vars[k].get()]
        if names:
            self.say("将添加到：" + "、".join(names))
        else:
            self.say("尚未勾选任何位置", "warn")
        self._on_passarg_toggle()



    def _btn_small(self, parent, text, cmd):
        return tk.Button(parent, text=text, command=cmd, bg=C_CARD, fg=C_TEXT,
                         relief="flat", bd=0, highlightthickness=1,
                         highlightbackground=C_BORDER, highlightcolor=C_BORDER,
                         font=FONT_S, padx=9, pady=4, cursor="hand2")

    # ---- 页签2：常用动作 ---------------------------------------------
    def _build_tab_quick(self, p):
        pad = tk.Frame(p, bg=C_CARD)
        pad.pack(fill="both", expand=True, padx=14, pady=12)
        tk.Label(pad, text="勾选想要的动作，点下方按钮批量添加（自动放到对应场景）",
                 bg=C_CARD, fg=C_SUB, font=FONT_XS, anchor="w").pack(fill="x",
                                                                   pady=(0, 8))

        box = tk.Frame(pad, bg=C_BORDER, highlightthickness=1,
                       highlightbackground=C_BORDER)
        box.pack(fill="both", expand=True)
        self.tpl_canvas = tk.Canvas(box, bg=C_CARD, highlightthickness=0, bd=0)
        vs = ttk.Scrollbar(box, orient="vertical", command=self.tpl_canvas.yview)
        self.tpl_canvas.configure(yscrollcommand=vs.set)
        vs.pack(side="right", fill="y")
        self.tpl_canvas.pack(fill="both", expand=True, padx=1, pady=1)

        inner = tk.Frame(self.tpl_canvas, bg=C_CARD)
        self.tpl_canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: self.tpl_canvas.configure(
            scrollregion=self.tpl_canvas.bbox("all")))

        self.templates = build_builtin_templates()
        self.tpl_vars: list[tk.BooleanVar] = []
        for t in self.templates:
            v = tk.BooleanVar(value=False)
            self.tpl_vars.append(v)
            row = tk.Frame(inner, bg=C_CARD)
            row.pack(fill="x", padx=10, pady=5)
            CheckChip(row, t["name"], v, bg=C_CARD).pack(anchor="w")
            scenes = "、".join(SCENE_SHORT.get(s["scene"], s["scene"])
                             for s in t["segments"])
            tk.Label(row, text=f"    {t['desc']}　→ {scenes}", bg=C_CARD,
                     fg=C_SUB, font=FONT_XS, anchor="w", justify="left",
                     wraplength=350).pack(anchor="w")

        btns = tk.Frame(pad, bg=C_CARD)
        btns.pack(fill="x", pady=(12, 0))
        _btn(btns, "＋  添加勾选的动作", self.on_add_templates,
             kind="primary").pack(side="left", fill="x", expand=True)
        self._btn_small(btns, "全选", lambda: [v.set(True) for v in self.tpl_vars]
                        ).pack(side="left", padx=(8, 0))

    # ---- 页签3：自定义命令 -------------------------------------------
    def _build_tab_custom(self, p):
        pad = tk.Frame(p, bg=C_CARD)
        pad.pack(fill="both", expand=True, padx=14, pady=12)
        tk.Label(pad, text="自己写命令行，适合高级用法", bg=C_CARD, fg=C_SUB,
                 font=FONT_XS, anchor="w").pack(fill="x", pady=(0, 8))

        def field(label, var, mono=False, hint=""):
            r = tk.Frame(pad, bg=C_CARD)
            r.pack(fill="x", pady=4)
            tk.Label(r, text=label, bg=C_CARD, fg=C_TEXT, font=FONT,
                     width=9, anchor="w").pack(side="left")
            e = tk.Entry(r, textvariable=var, font=(FONT_MONO if mono else FONT),
                         bg="#fbfcfe", fg=C_TEXT, relief="flat",
                         highlightthickness=1, highlightbackground=C_BORDER,
                         highlightcolor=C_ACCENT)
            e.pack(side="left", fill="x", expand=True, ipady=5)
            if hint:
                tk.Label(r, text=hint, bg=C_CARD, fg=C_SUB, font=FONT_XS
                         ).pack(side="left", padx=(6, 0))
            return e

        self.v_c_label = tk.StringVar()
        self.v_c_key = tk.StringVar()
        self.v_c_cmd = tk.StringVar()
        self.v_c_icon = tk.StringVar()
        field("菜单名称", self.v_c_label)
        field("注册表键名", self.v_c_key, mono=True, hint="留空自动生成")
        field("命令行", self.v_c_cmd, mono=True)
        icon_row = tk.Frame(pad, bg=C_CARD)
        icon_row.pack(fill="x", pady=4)
        tk.Label(icon_row, text="图标", bg=C_CARD, fg=C_TEXT, font=FONT,
                 width=9, anchor="w").pack(side="left")
        tk.Entry(icon_row, textvariable=self.v_c_icon, font=FONT_MONO,
                 bg="#fbfcfe", fg=C_TEXT, relief="flat", highlightthickness=1,
                 highlightbackground=C_BORDER, highlightcolor=C_ACCENT
                 ).pack(side="left", fill="x", expand=True, ipady=5)
        self._btn_small(icon_row, "浏览…", self.on_pick_icon).pack(side="left",
                                                                padx=(6, 0))

        sr = tk.Frame(pad, bg=C_CARD)
        sr.pack(fill="x", pady=(10, 0))
        tk.Label(sr, text="添加到", bg=C_CARD, fg=C_TEXT, font=FONT,
                 width=9, anchor="w").pack(side="left", anchor="n")
        chips = tk.Frame(sr, bg=C_CARD)
        chips.pack(side="left", fill="x", expand=True)
        for idx, k in enumerate(SCENE_ORDER):
            CheckChip(chips, SCENE_SHORT[k], self.scene_vars[k],
                      bg=C_CARD, command=self._on_scene_chip).pack(
                side="left", padx=(0 if idx == 0 else 16, 0))

        # Shift 隐藏开关（自定义页签也能设置）
        sr2 = tk.Frame(pad, bg=C_CARD)
        sr2.pack(fill="x", pady=(7, 0))
        tk.Label(sr2, text="", bg=C_CARD, font=FONT, width=9).pack(side="left")
        CheckChip(sr2, "仅在按住 Shift 右键时显示", self.v_extend,
                  bg=C_CARD).pack(side="left")

        tip = tk.Label(
            pad, bg="#f7f9fc", fg=C_SUB, font=FONT_XS, justify="left",
            anchor="w", wraplength=370, padx=10, pady=8,
            text="变量：%1 = 选中的文件/文件夹路径　%V = 当前文件夹路径\n"
                 "示例：\"C:\\Windows\\notepad.exe\" \"%1\"",
        )
        tip.pack(fill="x", pady=(12, 0))

        _btn(pad, "＋  添加自定义菜单", self.on_add_custom,
             kind="primary").pack(fill="x", pady=(12, 0))

    # ------------------------------------------------------------------
    # 右栏：已添加的菜单
    # ------------------------------------------------------------------
    def _build_right(self, parent):
        head = tk.Frame(parent, bg=C_BG)
        head.pack(fill="x", pady=(0, 8))
        tk.Label(head, text="② 已添加的右键菜单", bg=C_BG, fg=C_TEXT,
                 font=FONT_B).pack(side="left")
        self.count_lbl = tk.Label(head, text="", bg=C_BG, fg=C_SUB, font=FONT_S)
        self.count_lbl.pack(side="left", padx=8)

        # 场景筛选
        self.v_filter = tk.StringVar(value="all")
        filt = tk.Frame(head, bg=C_BG)
        filt.pack(side="right")
        tk.Label(filt, text="筛选", bg=C_BG, fg=C_SUB, font=FONT_S).pack(
            side="left", padx=(0, 4))
        for val, txt in (("all", "全部"), ("file", "文件"), ("dir", "文件夹"),
                         ("dirbg", "文件夹空白"), ("desktop", "桌面")):
            tk.Radiobutton(
                filt, text=txt, value=val, variable=self.v_filter,
                command=self.refresh_items, bg=C_BG, fg=C_TEXT,
                activebackground=C_BG, selectcolor=C_CARD, font=FONT_S,
                relief="flat", bd=0, highlightthickness=0, cursor="hand2",
            ).pack(side="left")

        # 搜索
        sr = tk.Frame(parent, bg=C_BG)
        sr.pack(fill="x", pady=(0, 8))
        tk.Entry(sr, textvariable=self.v_itemsearch, font=FONT, bg=C_CARD,
                 fg=C_TEXT, relief="flat", highlightthickness=1,
                 highlightbackground=C_BORDER, highlightcolor=C_ACCENT
                 ).pack(side="left", fill="x", expand=True, ipady=5)
        tk.Label(sr, text="搜索菜单名", bg=C_BG, fg=C_SUB, font=FONT_S
                 ).pack(side="left", padx=(8, 0))
        self.v_itemsearch.trace_add("write", lambda *_: self.refresh_items())

        # 列表
        box = tk.Frame(parent, bg=C_BORDER, highlightthickness=1,
                       highlightbackground=C_BORDER)
        box.pack(fill="both", expand=True)
        cols = ("label", "scene", "state", "cmd")
        self.tree = ttk.Treeview(box, columns=cols, show="headings",
                                 style="CM.Treeview", selectmode="browse")
        for c, txt, w, anchor in (
            ("label", "菜单名称", 155, "w"),
            ("scene", "场景", 84, "center"),
            ("state", "状态", 88, "center"),
            ("cmd", "命令行", 268, "w"),
        ):
            self.tree.heading(c, text=txt)
            self.tree.column(c, width=w, anchor=anchor, stretch=(c == "cmd"))
        vs = ttk.Scrollbar(box, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        vs.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True, padx=1, pady=1)
        self.tree.tag_configure("disabled", foreground="#9aa1ad")
        self.tree.tag_configure("enabled", foreground=C_TEXT)
        self.tree.bind("<Double-Button-1>", lambda e: self.on_toggle())
        self.tree.bind("<<TreeviewSelect>>", self.on_item_select)

        # 操作按钮
        act = tk.Frame(parent, bg=C_BG)
        act.pack(fill="x", pady=(10, 0))
        _btn(act, "🗑  删除选中", self.on_delete, kind="danger").pack(side="left")
        _btn(act, "启用 / 停用", self.on_toggle, kind="ok").pack(side="left",
                                                             padx=(8, 0))
        _btn(act, "载入编辑区", self.on_load_to_custom).pack(side="left",
                                                          padx=(8, 0))
        tk.Label(act, text="双击行 = 启停", bg=C_BG, fg=C_SUB,
                 font=FONT_XS).pack(side="right")

        # 维护行
        mnt = tk.Frame(parent, bg=C_BG)
        mnt.pack(fill="x", pady=(8, 0))
        self._btn_small(mnt, "备份注册表", self.on_backup).pack(side="left")
        self._btn_small(mnt, "还原备份", self.on_restore).pack(side="left",
                                                            padx=(6, 0))
        self._btn_small(mnt, "清空全部", self.on_clear_all).pack(side="left",
                                                              padx=(6, 0))
        tk.Label(mnt, text="只操作本工具添加的项，不碰系统与其他软件",
                 bg=C_BG, fg=C_SUB, font=FONT_XS).pack(side="right")

    # ------------------------------------------------------------------
    # 状态栏
    # ------------------------------------------------------------------
    def _build_status(self):
        tk.Frame(self, bg=C_BORDER, height=1).pack(fill="x", side="bottom")
        bar = tk.Frame(self, bg=C_HEAD, height=34)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        self.status = tk.Label(bar, textvariable=self.v_status, bg=C_HEAD,
                               fg=C_SUB, font=FONT_S, anchor="w")
        self.status.pack(side="left", padx=18)
        tk.Label(bar, text="作用范围：HKCU\\Software\\Classes", bg=C_HEAD,
                 fg=C_SUB, font=FONT_XS).pack(side="right", padx=18)
        self.v_status.set("就绪")

    def say(self, msg, kind="info"):
        color = {"info": C_SUB, "ok": C_OK, "warn": C_WARN,
                 "err": C_DANGER}.get(kind, C_SUB)
        self.v_status.set(msg)
        self.status.configure(fg=color)

    # ==================================================================
    # 应用扫描
    # ==================================================================
    def scan_apps_async(self):
        self.app_hint.configure(text="正在扫描本机软件…")

        def work():
            try:
                apps = scan_all_apps()
            except Exception as e:  # noqa: BLE001
                apps = []
                self.after(0, lambda: self.app_hint.configure(
                    text=f"扫描失败：{e}"))
                return
            self.after(0, lambda: self._on_apps_ready(apps))

        threading.Thread(target=work, daemon=True).start()

    def _on_apps_ready(self, apps):
        self.apps = apps
        self.app_list.delete(0, "end")
        for a in apps:
            self.app_list.insert("end", f"  {a['name']}")
        self.refresh_app_list()
        self.say(f"已扫描到 {len(apps)} 个软件，选中后一键添加", "ok")

    def refresh_app_list(self):
        kw = self.v_appsearch.get().strip().lower()
        self.visible_apps = [
            a for a in self.apps
            if not kw or kw in a["name"].lower() or kw in a["target"].lower()
        ]
        self.app_list.delete(0, "end")
        for a in self.visible_apps:
            self.app_list.insert("end", f"  {a['name']}")
        self.app_hint.configure(
            text=f"共 {len(self.visible_apps)} 个软件"
            + (f"（搜索：{self.v_appsearch.get()}）" if kw else "")
            + "　双击可快速添加")

    def _selected_app(self) -> dict | None:
        sel = self.app_list.curselection()
        if not sel:
            return None
        i = sel[0]
        return self.visible_apps[i] if 0 <= i < len(self.visible_apps) else None

    def on_app_select(self, _evt=None):
        a = self._selected_app()
        if not a:
            return
        # 自动填菜单名（用户可改）
        if not self.v_appname.get().strip():
            self.v_appname.set(a["name"])
        self.say(f"已选：{a['name']}　{a['target']}")

    def on_browse_exe(self):
        p = filedialog.askopenfilename(
            title="选择程序", filetypes=[("程序", "*.exe"), ("所有文件", "*.*")])
        if not p:
            return
        name = os.path.splitext(os.path.basename(p))[0]
        self.apps.insert(0, {"name": name, "target": p, "args": "",
                             "workdir": os.path.dirname(p), "icon": p,
                             "source": "手动"})
        self.v_appsearch.set("")
        self.refresh_app_list()
        self.app_list.selection_clear(0, "end")
        self.app_list.selection_set(0)
        self.v_appname.set(name)
        self.say(f"已载入 {name}，勾选位置后点「一键添加菜单」", "ok")

    # ==================================================================
    # 添加
    # ==================================================================
    def _checked_scenes(self) -> list[str]:
        return [k for k in SCENE_ORDER if self.scene_vars[k].get()]

    def on_add_app(self):
        app = self._selected_app()
        if app is None:
            # 允许用户直接在名称框写 + 用浏览选过的程序
            messagebox.showinfo(APP_TITLE, "请先在列表里选一个软件（或点「浏览 exe…」）。")
            return
        name = self.v_appname.get().strip() or app["name"]
        if len(name) > MAX_LABEL_LEN:
            if not messagebox.askyesno(
                    APP_TITLE,
                    f"菜单名较长（{len(name)} 字），超过 {MAX_LABEL_LEN} 字会让右键菜单变得很宽。\n\n仍要继续吗？"):
                return

        scenes = self._checked_scenes()
        if not scenes:
            messagebox.showwarning(APP_TITLE, "请至少勾选一个「添加到」的位置。")
            return

        args = self.v_args.get().strip() or app.get("args", "")
        hide_shift = self.v_extend.get()
        pass_arg = self.v_passarg.get()
        ok_n, fail_msgs = 0, []
        for sc in scenes:
            cmd = build_command(app["target"], args, sc, pass_arg=pass_arg)
            key = self._auto_key(suggest_key(name), sc)
            item = MenuItem(scene=sc, key_name=key, label=name, command=cmd,
                            icon=app.get("icon") or app["target"],
                            extend=hide_shift)
            ok, msg = self.mgr.add(item)
            if ok:
                ok_n += 1
            else:
                fail_msgs.append(f"{SCENE_SHORT[sc]}: {msg}")

        self.refresh_items()
        if ok_n:
            tip = "（按住 Shift 右键才显示）" if hide_shift else ""
            self.say(f"✓ 已为「{name}」添加 {ok_n} 个位置的右键菜单{tip}，"
                     "点右上角「让菜单立即生效」即可看到", "ok")
        if fail_msgs:
            messagebox.showerror(APP_TITLE, "部分失败：\n" + "\n".join(fail_msgs))

    def on_add_templates(self):
        picked = [t for t, v in zip(self.templates, self.tpl_vars) if v.get()]
        if not picked:
            messagebox.showinfo(APP_TITLE, "请先勾选要添加的动作。")
            return
        ok_n, skip_n = 0, 0
        for t in picked:
            for seg in t["segments"]:
                if not seg.get("command", "").strip():
                    continue
                key_base = f"{t['id']}_{seg['scene']}"
                if self.mgr.exists(seg["scene"], key_base):
                    skip_n += 1
                    continue
                item = MenuItem(
                    scene=seg["scene"], key_name=key_base, label=seg["label"],
                    command=seg["command"], icon=seg.get("icon", ""),
                    extend=seg.get("extend", False), is_builtin=True,
                )
                ok, _ = self.mgr.add(item)
                if ok:
                    ok_n += 1
        self.refresh_items()
        msg = f"✓ 已添加 {ok_n} 个常用动作"
        if skip_n:
            msg += f"（{skip_n} 个已存在，跳过）"
        self.say(msg, "ok")

    def on_add_custom(self):
        label = self.v_c_label.get().strip()
        cmd = self.v_c_cmd.get().strip()
        if not label:
            messagebox.showwarning(APP_TITLE, "请填写菜单名称。")
            return
        if not cmd:
            messagebox.showwarning(APP_TITLE, "请填写命令行。")
            return
        scenes = self._checked_scenes()
        if not scenes:
            messagebox.showwarning(APP_TITLE, "请至少勾选一个「添加到」的位置。")
            return

        key_raw = self.v_c_key.get().strip() or suggest_key(label)
        key_base = "".join(ch for ch in key_raw if ch not in '\\/"*?<>|').strip()
        icon = self.v_c_icon.get().strip()

        ok_n = 0
        for sc in scenes:
            key = self._auto_key(key_base, sc)
            item = MenuItem(scene=sc, key_name=key, label=label, command=cmd,
                            icon=icon, extend=self.v_extend.get())
            ok, _ = self.mgr.add(item)
            if ok:
                ok_n += 1
        self.refresh_items()
        if ok_n:
            self.say(f"✓ 已添加自定义菜单「{label}」到 {ok_n} 个位置", "ok")
            self.v_c_label.set("")
            self.v_c_cmd.set("")
            self.v_c_key.set("")
            self.v_c_icon.set("")

    def _auto_key(self, base: str, scene: str) -> str:
        base = base or "item"
        k = base
        n = 2
        while self.mgr.exists(scene, k):
            k = f"{base}_{n}"
            n += 1
        return k

    # ==================================================================
    # 列表刷新
    # ==================================================================
    def refresh_items(self):
        self.all_items = self.mgr.list_items()
        kw = self.v_itemsearch.get().strip().lower()
        flt = getattr(self, "v_filter", None)
        flt = flt.get() if flt else "all"
        shown: list[MenuItem] = []
        for it in self.all_items:
            if flt != "all" and it.scene != flt:
                continue
            if kw and kw not in it.label.lower() and kw not in it.command.lower():
                continue
            shown.append(it)
        self.visible_items = shown

        self.tree.delete(*self.tree.get_children())
        for i, it in enumerate(shown):
            if not it.enabled:
                state, tag = "○ 已停用", "disabled"
            elif it.extend:
                state, tag = "⇧ Shift", "enabled"
            else:
                state, tag = "● 启用中", "enabled"
            cmd = it.command
            if len(cmd) > 80:
                cmd = cmd[:77] + "…"
            self.tree.insert("", "end", iid=str(i),
                             values=(it.label, SCENE_SHORT.get(it.scene, it.scene),
                                     state, cmd), tags=(tag,))
        en = sum(1 for i in self.all_items if i.enabled)
        self.count_lbl.configure(
            text=f"共 {len(shown)} 项显示 / 全部 {len(self.all_items)} 项（启用 {en}）")

    def _selected_item(self) -> MenuItem | None:
        sel = self.tree.selection()
        if not sel:
            return None
        try:
            i = int(sel[0])
        except ValueError:
            return None
        return self.visible_items[i] if 0 <= i < len(self.visible_items) else None

    def on_item_select(self, _evt=None):
        it = self._selected_item()
        if it:
            self.say(f"已选中「{it.label}」（{SCENE_SHORT.get(it.scene, it.scene)}，"
                     f"{'启用' if it.enabled else '停用'}）")

    # ==================================================================
    # 删除 / 启停 / 载入
    # ==================================================================
    def on_delete(self):
        it = self._selected_item()
        if not it:
            messagebox.showinfo(APP_TITLE, "请先在右侧列表里选中一项。")
            return
        if not messagebox.askyesno(
                APP_TITLE,
                f"确定删除这个右键菜单嗎？\n\n"
                f"位置：{SCENE_SHORT.get(it.scene, it.scene)}\n"
                f"名称：{it.label}\n\n"
                "删除后该菜单会立刻从右键里消失。"):
            return
        ok, msg = self.mgr.remove(it.scene, it.key_name)
        self.say(("✓ " if ok else "✗ ") + msg, "ok" if ok else "err")
        self.refresh_items()

    def on_toggle(self):
        it = self._selected_item()
        if not it:
            messagebox.showinfo(APP_TITLE, "请先在右侧列表里选中一项。")
            return
        will_enable = not it.enabled
        ok, msg = self.mgr.set_enabled(it.scene, it.key_name, will_enable)
        if ok:
            if will_enable:
                self.say(f"✓ 已启用「{it.label}」，右键菜单里可以点开了", "ok")
            else:
                self.say(f"✓ 已停用「{it.label}」—— 该菜单已从右键里隐藏"
                         "（配置保留，点「启用/停用」可恢复）", "warn")
        else:
            self.say("✗ " + msg, "err")
        self.refresh_items()
        self._sync_extend_from_selection()

    def _sync_extend_from_selection(self):
        """选中项变化时，把它的 Shift 状态同步到编辑区复选框，避免误操作。"""
        it = self._selected_item()
        if it:
            self.v_extend.set(it.extend)

    def on_load_to_custom(self):
        it = self._selected_item()
        if not it:
            messagebox.showinfo(APP_TITLE, "请先在右侧列表里选中一项。")
            return
        self.v_c_label.set(it.label)
        self.v_c_key.set(it.key_name)
        self.v_c_cmd.set(it.command)
        self.v_c_icon.set(it.icon)
        self.v_extend.set(it.extend)
        for k in SCENE_ORDER:
            self.scene_vars[k].set(k == it.scene)
        self.nb.select(2)
        self.say("已载入「自定义」页签，改完点添加即会在新键名下生效"
                 "（如需替换请先删除原项）")

    def on_pick_icon(self):
        p = filedialog.askopenfilename(
            title="选择图标或程序",
            filetypes=[("程序/图标", "*.exe;*.dll;*.ico"), ("所有文件", "*.*")])
        if p:
            self.v_c_icon.set(p)

    # ==================================================================
    # 维护
    # ==================================================================
    def on_backup(self):
        p = filedialog.asksaveasfilename(
            title="保存备份", defaultextension=".reg",
            initialfile="ctxmenu-backup.reg",
            filetypes=[("注册表文件", "*.reg")])
        if not p:
            return
        ok, msg = self.mgr.export_backup(p)
        self.say(("✓ " if ok else "✗ ") + msg, "ok" if ok else "err")

    def on_restore(self):
        p = filedialog.askopenfilename(title="选择备份文件",
                                       filetypes=[("注册表文件", "*.reg")])
        if not p:
            return
        ok, msg = self.mgr.import_backup(p)
        self.say(("✓ " if ok else "✗ ") + msg, "ok" if ok else "err")
        self.refresh_items()

    def on_clear_all(self):
        n = len(self.mgr.list_items())
        if n == 0:
            messagebox.showinfo(APP_TITLE, "当前没有本工具添加的菜单项。")
            return
        if not messagebox.askyesno(
                APP_TITLE,
                f"将删除本工具添加的全部 {n} 个右键菜单项。\n\n"
                "只会删除本工具创建的项，系统自带和其他软件的菜单不受影响。\n\n"
                "建议先点「备份注册表」。确定继续？"):
            return
        ok, msg = self.mgr.clear_all()
        self.say(("✓ " if ok else "✗ ") + msg, "ok" if ok else "err")
        self.refresh_items()

    def on_restart_explorer(self):
        if not messagebox.askyesno(
                APP_TITLE,
                "将重启资源管理器让右键菜单立即刷新。\n\n"
                "任务栏和已打开的文件窗口会闪一下，通常几秒内自动恢复。\n\n"
                "现在执行吗？"):
            return
        self.say("正在重启资源管理器…")

        def work():
            ok, msg = self.mgr.restart_explorer()
            self.after(0, lambda: self.say(("✓ " if ok else "✗ ") + msg,
                                           "ok" if ok else "err"))
        threading.Thread(target=work, daemon=True).start()


def main():
    # 单实例守卫：若已有实例在运行，把它的窗口顶到最前，然后本进程静默退出。
    # 避免「右键点菜单看起来没反应」（其实是新窗口开在旧窗口后面）。
    try:
        import ctxmenu_single
        if ctxmenu_single.activate_existing_window():
            return
    except Exception:  # noqa: BLE001  守卫失败不应阻止程序启动
        pass

    app = CtxMenuApp()
    app.lift()
    app.attributes("-topmost", True)
    app.after(400, lambda: app.attributes("-topmost", False))
    app.focus_force()
    app.mainloop()


if __name__ == "__main__":
    main()
