# -*- coding: utf-8 -*-
"""Tina · 今日行情 + 今日任务  —— Windows 透明桌面小窗 (Python + tkinter)

一个程序包办：显示两个小窗 + 每天自动更新数据（内置，不依赖计划任务或 AI）。
运行：pythonw.exe desk_widgets.py，或用 build_exe.bat 打包成 TinaDesk.exe。
"""
import ctypes
import json
import math
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import datetime, timedelta, timezone
from tkinter import font as tkfont
from tkinter import messagebox

# ───────────────────────── 路径 / 常量 ─────────────────────────
import update_data as ud   # noqa: E402  数据更新逻辑

DATA_DIR = ud.DATA_DIR

PRICES = os.path.join(DATA_DIR, "prices.json")
TASKS = os.path.join(DATA_DIR, "tasks.json")
ECON = os.path.join(DATA_DIR, "econ_news.json")
WORDS = os.path.join(DATA_DIR, "english_words.json")
DEALS = os.path.join(DATA_DIR, "deals.json")
CONTROL = os.path.join(DATA_DIR, "control.json")   # 外部遥控：{"theme": "墨色", "refresh": "任意变化的字符串"}
SETTINGS = os.path.join(DATA_DIR, "settings.json")  # 本地：主题和窗口位置

KEY = "#010101"                       # 透明键色
FONT = "Microsoft YaHei UI"
CN = timezone(timedelta(hours=8))     # Asia/Shanghai
RELOAD_MS = 30_000          # 今日行情：重读本地 prices.json
TASKS_RELOAD_MS = 3_600_000  # 今日任务：每小时自动刷新一次
PAGE_MS = 8_000
PAGE_ANIM_MS = 320
COL_IDS = ["crypto", "oil", "shares", "gold", "fx"]
COL_DEFAULT_NAMES = {"crypto": "加密货币", "oil": "汽油", "shares": "股票指数",
                     "gold": "国内金价", "fx": "汇率"}
US_STOCKS = {"英伟达", "特斯拉", "英特尔", "闪迪"}

# 主文字 / 次要文字 / 标题强调 / 涨 / 跌
THEMES = [
    ("墨色", dict(main="#111111", sub="#3a3f4a", title="#1f4fa8", up="#c0392b", down="#2e7d32")),
    ("藏青", dict(main="#0b1f3a", sub="#2c4a72", title="#14407a", up="#b71c1c", down="#1b6e2e")),
    ("暖棕", dict(main="#4a2c17", sub="#7a5638", title="#8a4b14", up="#b3261e", down="#2f6b1f")),
    ("原白", dict(main="#f5f7fa", sub="#c5cad3", title="#8cb6ff", up="#ff6b6b", down="#9fe870")),
]
DEFAULT_THEME = 3  # 原白

IS_WIN = sys.platform == "win32"
if IS_WIN:
    user32 = ctypes.windll.user32
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    user32.GetParent.argtypes = [ctypes.c_void_p]
    user32.GetParent.restype = ctypes.c_void_p
    user32.FindWindowExW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p]
    user32.FindWindowExW.restype = ctypes.c_void_p
    user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    user32.FindWindowW.restype = ctypes.c_void_p
    user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]


# ───────────────────────── Windows 桌面层 ─────────────────────────
def _find_desktop_host():
    """找到承载桌面图标的窗口 (Progman 或某个 WorkerW)。"""
    found = []
    proc_t = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def cb(hwnd, _lp):
        if user32.FindWindowExW(hwnd, None, "SHELLDLL_DefView", None):
            found.append(hwnd)
            return False
        return True

    try:
        user32.EnumWindows(proc_t(cb), 0)
    except Exception:
        pass
    return found[0] if found else user32.FindWindowW("Progman", None)


def _hwnd(win):
    return user32.GetParent(win.winfo_id()) or win.winfo_id()


def make_desktop_window(win):
    """不抢焦点、不进任务栏。"""
    if not IS_WIN:
        return
    h = _hwnd(win)
    style = user32.GetWindowLongW(h, -20)
    user32.SetWindowLongW(h, -20, style | 0x00000080 | 0x08000000)  # TOOLWINDOW | NOACTIVATE


def sink_to_desktop(win):
    """放到桌面图层：在所有普通窗口之下，但仍盖在壁纸/桌面上。"""
    if not IS_WIN:
        return
    try:
        h = _hwnd(win)
        flags = 0x0001 | 0x0002 | 0x0010  # NOSIZE | NOMOVE | NOACTIVATE
        user32.SetWindowPos(h, 1, 0, 0, 0, 0, flags)          # HWND_BOTTOM
        host = _find_desktop_host()
        if host:
            user32.SetWindowPos(host, h, 0, 0, 0, 0, flags)    # 让桌面宿主窗口退到我们后面
    except Exception:
        pass


HWND_TOPMOST = -1


def raise_ui(win, activate=True):
    """把普通对话框抬到所有窗口前面，避免跟在已沉到桌面层的小窗后面。"""
    if win is None:
        return
    try:
        if not win.winfo_exists():
            return
    except Exception:
        return
    try:
        win.deiconify()
    except Exception:
        pass
    try:
        win.attributes("-topmost", True)
    except tk.TclError:
        pass
    try:
        win.lift()
    except Exception:
        pass
    if not IS_WIN:
        if activate:
            try:
                win.focus_force()
            except Exception:
                pass
        return
    try:
        h = _hwnd(win)
        flags = 0x0001 | 0x0002 | 0x0040  # NOSIZE | NOMOVE | SHOWWINDOW
        if not activate:
            flags |= 0x0010  # NOACTIVATE
        user32.SetWindowPos(h, HWND_TOPMOST, 0, 0, 0, 0, flags)
        if activate:
            user32.SetForegroundWindow(h)
            win.focus_force()
    except Exception:
        pass


def popup_menu(menu, x, y, app):
    """用一个置顶的隐藏宿主弹出菜单，避免菜单跟着桌面小窗沉到别的程序后面。"""
    host = getattr(app, "_popup_host", None)
    try:
        alive = host is not None and host.winfo_exists()
    except Exception:
        alive = False
    if not alive:
        host = tk.Toplevel(app.root)
        host.withdraw()
        host.overrideredirect(True)
        host.configure(bg=KEY)
        app._popup_host = host
    try:
        host.geometry(f"1x1+{int(x)}+{int(y)}")
        host.deiconify()
        raise_ui(host, activate=True)
        menu.tk_popup(int(x), int(y))
    finally:
        try:
            menu.grab_release()
        except Exception:
            pass
        try:
            if host.winfo_exists():
                host.withdraw()
        except Exception:
            pass


# ───────────────────────── 数据工具 ─────────────────────────
def load_json(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return None


def load_settings():
    d = load_json(SETTINGS)
    return d if isinstance(d, dict) else {}


def write_settings(d):
    tmp = SETTINGS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SETTINGS)


def mtime(path):
    try:
        return datetime.fromtimestamp(os.path.getmtime(path), CN)
    except Exception:
        return None


def parse_time(s):
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None
    return d.astimezone(CN) if d.tzinfo else d


def num(v):
    try:
        return float(v)
    except Exception:
        return None


def fmt_price(v, strip):
    p = num(v)
    if p is None:
        return str(v) if v not in (None, "") else "—"
    if strip:
        s = f"{p:,.2f}" if abs(p) >= 1 else f"{p:.4f}"
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        return s
    return f"{p:,.2f}"


def direction(text, pct):
    """1 涨(红) / -1 跌(绿) / 0 平"""
    if text:
        t = str(text).strip()
        if "上调" in t or t.startswith("+"):
            return 1
        if "下调" in t or t[:1] in ("-", "−", "–"):
            return -1
        return 0
    p = num(pct)
    if p is None or abs(p) < 1e-9:
        return 0
    return 1 if p > 0 else -1


def row_texts(cid, it):
    """-> (名称, 报价, 涨跌, 方向)"""
    name = it.get("name") or it.get("display_name") or it.get("label") or it.get("symbol") or ""
    if it.get("display"):
        price = str(it["display"])
    else:
        unit = it.get("unit")
        if not unit:
            if cid == "crypto":
                unit = "美元"
            elif cid == "oil":
                unit = "元/升"
            elif cid == "gold":
                unit = "元/克"
            elif cid == "shares":
                code = str(it.get("code") or "")
                if "指数" in name or code in ("sh000001", "sz399001", "sh000300", "sz399006"):
                    unit = "点"
                elif code.startswith("us") or name in US_STOCKS:
                    unit = "美元"
                elif code.startswith("hk"):
                    unit = "港元"
                else:
                    unit = "元"
            else:
                unit = "元"
        price = f"{fmt_price(it.get('price'), cid == 'crypto')} {unit}"
    if it.get("change_text"):
        chg = str(it["change_text"])
    else:
        p = num(it.get("change_pct"))
        if p is None:
            chg = ""
        elif abs(p) < 1e-9:
            chg = "0.00%"
        else:
            chg = f"{p:+.2f}%"
    return name, price, chg, direction(it.get("change_text"), it.get("change_pct"))


def items_of(v):
    if isinstance(v, dict):
        v = v.get("items") or v.get("rows") or []
    return v if isinstance(v, list) else []


def titles_of(v):
    """兼容旧调用，只返回标题字符串。"""
    return [it["title"] for it in news_of(v)]


def news_of(v):
    out = []
    for it in items_of(v):
        if isinstance(it, dict):
            title = it.get("title")
            url = str(it.get("url") or it.get("link") or "").strip()
        else:
            title, url = it, ""
        if title:
            out.append({"title": str(title), "url": url})
    return out


def deals_of(v):
    """羊毛条目：[{title, kind}]，kind 为 coupon / token。兼容旧的「消费：」「额度：」前缀。"""
    raw = []
    for it in items_of(v):
        kind = None
        url = ""
        if isinstance(it, dict):
            t = it.get("title")
            kind = it.get("kind") or it.get("type") or it.get("cat")
            url = str(it.get("url") or it.get("link") or "").strip()
        else:
            t = it
        if not t:
            continue
        t = str(t).strip()
        k = str(kind).strip().lower() if kind else ""
        if k in ("coupon", "优惠券", "consumer", "消费"):
            kind = "coupon"
        elif k in ("token", "额度", "ai", "tokens"):
            kind = "token"
        else:
            kind = None
        if t.startswith("消费：") or t.startswith("额度："):
            if kind is None:
                kind = "coupon" if t.startswith("消费：") else "token"
            t = t[3:]
        raw.append({"title": t, "kind": kind, "url": url})
    if raw and all(d["kind"] is None for d in raw):
        for i, d in enumerate(raw):
            d["kind"] = "coupon" if i < 5 else "token"
    else:
        for d in raw:
            if d["kind"] is None:
                d["kind"] = "coupon"
    return raw


def load_tasks():
    """返回 (econ条目, 单词dict列表, 羊毛条目, 更新时间)。
    优先读三个源 JSON；都没有时再尝试合并后的 tasks.json。"""
    econ = news_of(load_json(ECON))
    words = [w for w in items_of(load_json(WORDS)) if isinstance(w, dict) and w.get("word")]
    deals = deals_of(load_json(DEALS))
    stamp = max([t for t in (mtime(ECON), mtime(WORDS), mtime(DEALS)) if t], default=None)
    if not (econ or words or deals):
        d = load_json(TASKS)
        if isinstance(d, dict):
            for k, v in d.items():
                kl = k.lower()
                if "econ" in kl or "news" in kl:
                    econ = news_of(v)
                elif "english" in kl or "word" in kl:
                    words = [w for w in items_of(v) if isinstance(w, dict) and w.get("word")]
                elif "deal" in kl or "wool" in kl:
                    deals = deals_of(v)
            stamp = parse_time(d.get("updated_at")) or mtime(TASKS)
    return econ, words, deals, stamp


# ───────────────────────── 面板基类 ─────────────────────────
class Panel:
    def __init__(self, app, win, title):
        self.app, self.win = app, win
        self.moved = False
        self._dx = self._dy = 0
        win.title(title)
        win.overrideredirect(True)
        win.configure(bg=KEY)
        try:
            win.attributes("-transparentcolor", KEY)
        except tk.TclError:
            pass

    @property
    def th(self):
        return self.app.theme

    def font(self, size):
        return tkfont.Font(family=FONT, size=size, weight="bold")

    def label(self, parent, text="", size=9, role="main", **kw):
        kw.setdefault("anchor", "w")
        kw.setdefault("justify", "left")
        lb = tk.Label(parent, text=text, font=self.font(size), fg=self.th[role],
                      bg=KEY, bd=0, padx=0, pady=0, **kw)
        return lb

    # 拖动 / 右键
    def bindall(self, w):
        w.bind("<ButtonPress-1>", self._press)
        w.bind("<B1-Motion>", self._drag)
        w.bind("<ButtonRelease-1>", self._release)
        w.bind("<ButtonPress-3>", self._menu)
        for c in w.winfo_children():
            self.bindall(c)

    def _post_menu(self, x, y, widget=None):
        now = time.perf_counter()
        if now - getattr(self, "_menu_at", 0) < 0.25:
            return
        self._menu_at = now
        popup_menu(self.app.menu, x, y, self.app)

    def _press(self, e):
        self._dx = e.x_root - self.win.winfo_x()
        self._dy = e.y_root - self.win.winfo_y()
        self._press_xy = (e.x_root, e.y_root)
        self._did_drag = False

    def _drag(self, e):
        px, py = getattr(self, "_press_xy", (e.x_root, e.y_root))
        if abs(e.x_root - px) < 5 and abs(e.y_root - py) < 5:
            return
        self._did_drag = True
        self.moved = True
        self.win.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def _release(self, e):
        sink_to_desktop(self.win)
        if getattr(self, "_did_drag", False):
            try:
                self.app.save_layout()
            except Exception:
                pass
        else:
            self._open_link(getattr(e, "widget", None))

    def _open_link(self, w):
        url = ""
        cur = w
        while cur is not None:
            url = str(getattr(cur, "_tina_url", "") or "")
            if url:
                break
            cur = getattr(cur, "master", None)
            if cur is self.win:
                break
        if not url:
            return
        try:
            os.startfile(url)
        except Exception:
            try:
                import webbrowser
                webbrowser.open(url)
            except Exception:
                pass

    def _menu(self, e):
        x, y, widget = int(e.x_root), int(e.y_root), e.widget
        # 等这次右键松开后再弹出，避免刚出现就被同一次松开关掉
        self.win.after(10, lambda: self._post_menu(x, y, widget))

    def set_size(self, w, h):
        self.win.geometry(f"{w}x{h}")


# ───────────────────────── 今日行情 ─────────────────────────
class QuotesPanel(Panel):
    def __init__(self, app, win):
        super().__init__(app, win, "Tina · 今日行情")
        S = app.S
        self.rotate = 5
        self.min_w, self.max_w_cfg = 880, 1300
        outer = tk.Frame(win, bg=KEY)
        outer.pack(fill="both", expand=True, padx=S(12), pady=S(8))

        top = tk.Frame(outer, bg=KEY)
        top.pack(fill="x")
        self.title = self.label(top, "Tina · 今日行情", 11, "title")
        self.title.pack(side="left")
        self.clock = self.label(top, "", 9, "sub")
        self.clock.pack(side="right")

        body = tk.Frame(outer, bg=KEY)
        body.pack(fill="x", pady=(S(4), S(2)))
        self.body = body
        self.cols = []
        for i in range(5):
            f = tk.Frame(body, bg=KEY)
            f.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else S(12), 0))
            body.columnconfigure(i, weight=1)
            n = self.label(f, "", 9, "sub")
            p = self.label(f, "", 12, "main")
            c = self.label(f, "", 10, "sub")
            n.pack(anchor="w")
            p.pack(anchor="w")
            c.pack(anchor="w")
            self.cols.append(dict(id=COL_IDS[i], frame=f, n=n, p=p, c=c, rows=[], idx=0))

        self.foot = self.label(outer, "", 8, "sub")
        self.foot.pack(fill="x", pady=(S(2), 0))
        self.bindall(outer)
        self.reload(first=True)
        for i in range(5):  # 各栏起步错开约 1 秒
            win.after(int(self.rotate * 1000) + i * 1000, lambda i=i: self._tick(i))

    def reload(self, first=False):
        S = self.app.S
        data = load_json(PRICES) or {}
        self.rotate = max(1, num(data.get("rotate_seconds")) or 5)
        by_id = {c.get("id"): c for c in data.get("columns", []) if isinstance(c, dict)}
        fN, fP, fC = self.font(9), self.font(12), self.font(10)
        total = 0
        for col in self.cols:
            items = [it for it in items_of(by_id.get(col["id"])) if isinstance(it, dict)]
            rows = [row_texts(col["id"], it) for it in items]
            if not rows:
                rows = [row_texts(col["id"], it) for it in ud.placeholder_items(col["id"])] or \
                       [(COL_DEFAULT_NAMES[col["id"]], "暂无数据", "", 0)]
            col["rows"] = rows
            col["idx"] %= len(col["rows"])
            w = max(max(fN.measure(r[0]), fP.measure(r[1]), fC.measure(r[2])) for r in col["rows"])
            self.body.columnconfigure(self.cols.index(col), minsize=w)
            total += w
        total += 4 * S(12) + 2 * S(12) + S(8)
        max_w = min(S(self.max_w_cfg), self.app.sw - S(250) - S(24))
        self.W = int(max(S(self.min_w), min(total, max_w)))
        for i in range(5):
            self._render(i)

        t = parse_time(data.get("updated_at")) or (mtime(PRICES) if data else None)
        self.foot.config(text=f"更新 {t:%H:%M:%S} · 右键菜单" if (data and t) else "右键：刷新 / 打开文件夹 / 退出")
        self.win.update_idletasks()
        h = self.win.winfo_reqheight()
        self.set_size(self.W, h)
        if first or not self.moved:
            x = (self.app.sw - self.W) // 2
            x = max(0, min(x, self.app.sw - S(250) - S(8) - S(8) - self.W))  # 不压到右侧任务窗
            self.win.geometry(f"{self.W}x{h}+{x}+{S(8)}")

    def _render(self, i):
        col = self.cols[i]
        name, price, chg, d = col["rows"][col["idx"] % len(col["rows"])]
        th = self.th
        col["n"].config(text=name, fg=th["sub"])
        col["p"].config(text=price, fg=th["main"])
        col["c"].config(text=chg, fg=th["up"] if d > 0 else th["down"] if d < 0 else th["sub"])

    def _tick(self, i):
        col = self.cols[i]
        if len(col["rows"]) > 1:
            col["idx"] = (col["idx"] + 1) % len(col["rows"])
            self._render(i)
        self.win.after(int(self.rotate * 1000), lambda: self._tick(i))

    def recolor(self):
        self.title.config(fg=self.th["title"])
        self.clock.config(fg=self.th["sub"])
        self.foot.config(fg=self.th["sub"])
        for i in range(5):
            self._render(i)

    def _col_from_widget(self, w):
        while w:
            for col in self.cols:
                if w is col.get("frame"):
                    return col
            if w is self.win or w is self.body:
                break
            w = getattr(w, "master", None)
        return None

    def _col_at(self, x_root, y_root):
        hit, best = None, None
        for col in self.cols:
            f = col.get("frame")
            if f is None:
                continue
            try:
                x, y = f.winfo_rootx(), f.winfo_rooty()
                w, h = f.winfo_width(), f.winfo_height()
            except tk.TclError:
                continue
            if x <= x_root < x + w and y <= y_root < y + h:
                return col
            # 点在两栏缝隙时，算到较近的一栏
            cx = x + w / 2
            dist = abs(x_root - cx)
            if y - 8 <= y_root < y + h + 8 and (best is None or dist < best):
                hit, best = col, dist
        return hit

    def _menu(self, e):
        x, y, widget = int(e.x_root), int(e.y_root), e.widget
        self.win.after(10, lambda: self._post_menu(x, y, widget))

    def _post_menu(self, x, y, widget=None):
        now = time.perf_counter()
        if now - getattr(self, "_menu_at", 0) < 0.25:
            return
        self._menu_at = now
        col = self._col_at(x, y) or self._col_from_widget(widget)
        if col and col["id"] in ("crypto", "oil", "shares", "fx"):
            self._column_menu(col, x, y)
        else:
            popup_menu(self.app.menu, x, y, self.app)

    def _column_menu(self, col, x, y):
        labels = {"crypto": "管理币种…", "oil": "管理汽油…", "shares": "管理股票…", "fx": "管理汇率…"}
        m = tk.Menu(self.win, tearoff=0, bg="#1f2430", fg="#f5f7fa",
                    activebackground="#8cb6ff", activeforeground="#111111", bd=0,
                    font=(FONT, 9, "bold"))
        m.add_command(label=labels[col["id"]], command=lambda: self._manage_quotes(col["id"]))
        name, *_ = col["rows"][col["idx"] % len(col["rows"])]
        if name and name != "暂无数据" and "—" not in name:
            m.add_command(label=f"删除「{name}」", command=lambda n=name, k=col["id"]: self._remove_shown(k, n))
        m.add_separator()
        m.add_command(label="刷新", command=self.app.refresh)
        m.add_command(label=f"换文字颜色（当前：{THEMES[self.app.theme_i][0]}）", command=self.app.cycle_theme)
        m.add_command(label="打开数据文件夹", command=self.app.open_folder)
        m.add_command(label="立即更新数据", command=self.app.update_now)
        m.add_command(label="编辑手动数据", command=self.app.edit_manual)
        m.add_command(label=f"开机自启：{'开' if self.app._autostart_on() else '关'}（点击切换）",
                      command=self.app.toggle_autostart)
        m.add_separator()
        m.add_command(label="退出", command=self.app.root.destroy)
        popup_menu(m, x, y, self.app)

    def _remove_shown(self, kind, name):
        ok, msg = ud.watchlist_remove_by_label(kind, name)
        if not ok:
            messagebox.showinfo("今日行情", msg, parent=self.win)
            return
        self._refresh_prices()

    def _refresh_prices(self, status=None):
        if status:
            status("已保存，正在更新行情…")

        def work():
            err = None
            try:
                ud.update_prices()
            except Exception as e:
                err = str(e)
                ud.log(f"watchlist: 更新行情失败 {e!r}")

            def done():
                self.reload()
                if status:
                    status("已更新" if not err else f"列表已保存，但更新失败：{err}")

            self.win.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def _manage_quotes(self, kind):
        titles = {"crypto": "管理币种", "oil": "管理汽油", "shares": "管理股票", "fx": "管理汇率"}
        hints = {
            "crypto": "输入名称或代码，例如 BTC、以太坊、SOL",
            "oil": "输入城市名，例如 北京、杭州、深圳",
            "shares": "输入股票代码，例如 600519、sz000001、AAPL、00700",
            "fx": "输入货币名称或代码，例如 英镑、HKD、欧元",
        }
        dlg = tk.Toplevel(self.app.root)
        dlg.title(titles[kind])
        dlg.resizable(False, False)
        # 不要 transient 到已沉到桌面层的小窗，否则对话框会被别的程序挡住
        pad = self.app.S(10)
        box = tk.Frame(dlg, padx=pad, pady=pad)
        box.pack(fill="both", expand=True)
        tk.Label(box, text="当前列表", font=(FONT, 9, "bold"), anchor="w").pack(fill="x")
        lst = tk.Listbox(box, height=8, width=36, font=(FONT, 10), exportselection=False)
        lst.pack(fill="both", expand=True, pady=(self.app.S(4), self.app.S(6)))

        def refill():
            lst.delete(0, "end")
            for line in ud.watchlist_labels(kind):
                lst.insert("end", line)

        refill()
        status = tk.StringVar(value="")

        def set_status(text):
            status.set(text)

        def do_remove():
            sel = lst.curselection()
            if not sel:
                set_status("请先选中要删除的一项")
                return
            ok, msg = ud.watchlist_remove_at(kind, sel[0])
            set_status(msg)
            refill()
            if ok:
                self._refresh_prices(set_status)

        tk.Button(box, text="删除选中", command=do_remove, font=(FONT, 9)).pack(anchor="w")
        tk.Label(box, text="添加", font=(FONT, 9, "bold"), anchor="w").pack(fill="x", pady=(self.app.S(8), 0))
        tk.Label(box, text=hints[kind], font=(FONT, 8), fg="#555", anchor="w").pack(fill="x")
        row = tk.Frame(box)
        row.pack(fill="x", pady=(self.app.S(4), 0))
        entry = tk.Entry(row, font=(FONT, 10), width=22)
        entry.pack(side="left", fill="x", expand=True)
        grade_vars = {}
        if kind == "oil":
            grow = tk.Frame(box)
            grow.pack(fill="x", pady=(self.app.S(4), 0))
            for g, text in (("92", "92#"), ("95", "95#"), ("98", "98#"), ("0", "0#柴油")):
                grade_vars[g] = tk.BooleanVar(value=g in ("92", "95"))
                tk.Checkbutton(grow, text=text, variable=grade_vars[g], font=(FONT, 9)).pack(side="left", padx=(0, 8))

        busy = {"on": False}

        def do_add():
            if busy["on"]:
                return
            q = entry.get().strip()
            if not q:
                set_status(hints[kind])
                return
            grades = None
            if kind == "oil":
                grades = [g for g, var in grade_vars.items() if var.get()]
                if not grades:
                    set_status("请至少选一种油号")
                    return
            busy["on"] = True
            add_btn.config(state="disabled")
            set_status("正在查找…")

            def work():
                ok, msg = ud.watchlist_add(kind, q, grades=grades)

                def done():
                    busy["on"] = False
                    add_btn.config(state="normal")
                    set_status(msg)
                    if ok:
                        entry.delete(0, "end")
                        refill()
                        self._refresh_prices(set_status)

                self.win.after(0, done)

            threading.Thread(target=work, daemon=True).start()

        add_btn = tk.Button(row, text="添加", command=do_add, font=(FONT, 9))
        add_btn.pack(side="left", padx=(self.app.S(6), 0))
        entry.bind("<Return>", lambda _e: do_add())
        tk.Label(box, textvariable=status, font=(FONT, 8), fg="#555", anchor="w").pack(fill="x", pady=(self.app.S(6), 0))
        tk.Button(box, text="完成", command=dlg.destroy, font=(FONT, 9)).pack(anchor="e", pady=(self.app.S(8), 0))
        entry.focus_set()
        dlg.update_idletasks()
        x = self.win.winfo_rootx() + self.app.S(24)
        y = self.win.winfo_rooty() + self.app.S(36)
        dlg.geometry(f"+{x}+{y}")
        raise_ui(dlg, activate=True)
        entry.focus_set()

        def _keep_front(_e=None):
            if not dlg.winfo_exists():
                return
            try:
                dlg.attributes("-topmost", True)
                dlg.lift()
            except tk.TclError:
                return

        dlg.bind("<FocusOut>", lambda _e: dlg.after(50, _keep_front))
        dlg.after(200, _keep_front)



def _hex_rgb(c):
    c = str(c or "").lstrip("#")
    if len(c) != 6:
        return (1, 1, 1)
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _rgb_hex(rgb):
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def _mix_color(c1, c2, t):
    a, b = _hex_rgb(c1), _hex_rgb(c2)
    return _rgb_hex(tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3)))


def _all_labels(w):
    out = []

    def walk(x):
        if isinstance(x, tk.Label):
            out.append(x)
        try:
            kids = x.winfo_children()
        except tk.TclError:
            return
        for c in kids:
            walk(c)

    walk(w)
    return out


# ───────────────────────── 今日任务 ─────────────────────────
class TasksPanel(Panel):
    PER_PAGE = 5

    def __init__(self, app, win):
        super().__init__(app, win, "Tina · 定时任务")
        S = app.S
        self.W = S(250)
        self.econ, self.words, self.deals, self.stamp = [], [], [], None
        self.outer = tk.Frame(win, bg=KEY)
        self.outer.pack(fill="both", expand=True, padx=S(10), pady=S(8))
        top = tk.Frame(self.outer, bg=KEY)
        top.pack(fill="x")
        self.title = self.label(top, "Tina · 今日任务", 11, "title")
        self.title.pack(side="left")
        self.clock = self.label(top, "", 9, "sub")
        self.clock.pack(side="right")
        self.body = tk.Frame(self.outer, bg=KEY)
        self.body.pack(fill="x", pady=(S(6), 0))
        self.foot = self.label(self.outer, "", 8, "sub")
        self.foot.pack(fill="x", pady=(S(8), 0))
        self._anim = None
        self._lock_clips = False
        self._econ_h = self._deals_h = 0
        self.reload(first=True)

    def reload(self, first=False):
        econ, words, deals, stamp = load_tasks()
        unchanged = (not first
                     and (econ, words, deals) == (self.econ, self.words, self.deals)
                     and getattr(self, "_k", None) is not None)
        self.econ, self.words, self.deals, self.stamp = econ, words, deals, stamp
        has = bool(self.econ or self.words or self.deals)
        self.foot.config(text=f"更新 {self.stamp:%H:%M:%S} · 右键菜单" if (has and self.stamp)
                         else "右键：刷新 / 打开文件夹 / 退出")
        if unchanged:
            return
        self.render(first)

    def _words_at(self, x_root, y_root):
        box = getattr(self, "_words_box", None)
        if box is None:
            return False
        try:
            x, y = box.winfo_rootx(), box.winfo_rooty()
            w, h = box.winfo_width(), box.winfo_height()
        except tk.TclError:
            return False
        return x <= x_root < x + w and y <= y_root < y + h

    def _menu(self, e):
        x, y, widget = int(e.x_root), int(e.y_root), e.widget
        self.win.after(10, lambda: self._post_menu(x, y, widget))

    def _post_menu(self, x, y, widget=None):
        now = time.perf_counter()
        if now - getattr(self, "_menu_at", 0) < 0.25:
            return
        self._menu_at = now
        if self._words_at(x, y):
            self._words_menu(x, y)
            return
        popup_menu(self.app.menu, x, y, self.app)

    def _shuffle_words(self):
        try:
            ud.replace_english_words(n=10, exclude=self.words)
        except Exception as e:
            self.foot.config(text=f"更换单词失败：{e}")
            return
        self.reload()

    def _words_menu(self, x, y):
        m = tk.Menu(self.win, tearoff=0, bg="#1f2430", fg="#f5f7fa",
                    activebackground="#8cb6ff", activeforeground="#111111", bd=0,
                    font=(FONT, 9, "bold"))
        m.add_command(label="随机更换十个单词", command=self._shuffle_words)
        m.add_separator()
        m.add_command(label="刷新", command=self.app.refresh)
        m.add_command(label=f"换文字颜色（当前：{THEMES[self.app.theme_i][0]}）", command=self.app.cycle_theme)
        m.add_command(label="打开数据文件夹", command=self.app.open_folder)
        m.add_command(label="立即更新数据", command=self.app.update_now)
        m.add_command(label="编辑手动数据", command=self.app.edit_manual)
        m.add_command(label=f"开机自启：{'开' if self.app._autostart_on() else '关'}（点击切换）",
                      command=self.app.toggle_autostart)
        m.add_separator()
        m.add_command(label="退出", command=self.app.root.destroy)
        popup_menu(m, x, y, self.app)

    def _deal_groups(self):
        coupons = [d for d in self.deals if d.get("kind") == "coupon"]
        tokens = [d for d in self.deals if d.get("kind") == "token"]
        return coupons, tokens

    def pages(self):
        coupons, tokens = self._deal_groups()
        deal_pages = 0
        if coupons:
            deal_pages += math.ceil(len(coupons) / self.PER_PAGE)
        if tokens:
            deal_pages += math.ceil(len(tokens) / self.PER_PAGE)
        econ_pages = math.ceil(max(len(self.econ), 1) / self.PER_PAGE)
        return max(1, econ_pages, deal_pages or 1)

    MAX_K = 16   # 行距放大的上限（单位 px），避免在很高的屏幕上拉得太散

    def _gaps(self, k):
        S = self.app.S
        return S(k), S(round(k * 2.2)), S(max(1, round(k * 0.6)))   # 条目间距、分组间距、例句下间距

    def _make_probe(self):
        """后台测量用的隐藏窗，避免在可见小窗上把每一页都画一遍。"""
        S = self.app.S
        pr = tk.Toplevel(self.win)
        pr.withdraw()
        pr.overrideredirect(True)
        pr.configure(bg=KEY)
        outer = tk.Frame(pr, bg=KEY)
        outer.pack(fill="both", expand=True, padx=S(10), pady=S(8))
        top = tk.Frame(outer, bg=KEY)
        top.pack(fill="x")
        self.label(top, "Tina · 今日任务", 11, "title").pack(side="left")
        self.label(top, "00:00", 9, "sub").pack(side="right")
        body = tk.Frame(outer, bg=KEY)
        body.pack(fill="x", pady=(S(6), 0))
        self.label(outer, "更新 00:00:00 · 右键菜单", 8, "sub").pack(fill="x", pady=(S(8), 0))
        return pr, body

    def _page_height(self, k, page):
        pr, body = self._make_probe()
        cur_body, cur_page = self.body, self.app.page
        locked = getattr(self, "_lock_clips", True)
        self.body = body
        self.app.page = page
        self._lock_clips = False
        try:
            self._build(*self._gaps(k), bind=False)
            pr.update_idletasks()
            return (pr.winfo_reqheight(),
                    self._econ_clip.winfo_reqheight(),
                    self._deals_clip.winfo_reqheight())
        finally:
            self.body = cur_body
            self.app.page = cur_page
            self._lock_clips = locked
            try:
                pr.destroy()
            except Exception:
                pass

    def _fit_spacing(self):
        """按所有页里最高的那一页来定行距和窗口高度，避免翻页时忽疏忽密。"""
        S = self.app.S
        limit = self.app.sh - S(8) - S(52)       # 上边距 + 任务栏/下边距
        n = max(1, self.pages())

        def stats(k):
            triples = [self._page_height(k, p) for p in range(n)]
            win_h = max(t[0] for t in triples)
            econ_h = max(t[1] for t in triples)
            deals_h = max(t[2] for t in triples)
            # 经济热点和羊毛各自按最高页锁定后，总高度可能比「某一页的总高」还大一点
            locked = max(t[0] - t[1] - t[2] for t in triples) + econ_h + deals_h
            return max(win_h, locked), econ_h, deals_h

        h1 = stats(1)[0]
        h2 = stats(2)[0]
        slope = max(1, h2 - h1)                  # 行距每加 1px，总高度增加多少
        k = max(1, min(self.MAX_K, int((limit - h1) / slope) + 1))
        h, econ_h, deals_h = stats(k)
        while h > limit and k > 1:
            k -= 1
            h, econ_h, deals_h = stats(k)
        self._k, self._h, self._econ_h, self._deals_h = k, h, econ_h, deals_h

    def _cancel_anim(self):
        a = getattr(self, "_anim", None)
        self._anim = None
        if not a:
            return
        if a.get("id"):
            try:
                self.win.after_cancel(a["id"])
            except Exception:
                pass
        fin = a.get("finish")
        if callable(fin):
            try:
                fin(snap=True)
            except Exception:
                pass

    def render(self, first=False, refit=True, animate=False):
        """行距自适应：把屏幕上多余的竖向空间摊到各行之间，刚好不被任务栏盖住。
        翻页时只换内容、不重算行距，并用短滑动过渡；数据更新时再按最高页重新计算。"""
        S = self.app.S
        self._cancel_anim()
        if refit or getattr(self, "_k", None) is None or getattr(self, "_h", None) is None:
            self._lock_clips = False
            self._fit_spacing()
            self._lock_clips = True
            self._build(*self._gaps(self._k))
            self.win.update_idletasks()
            self.set_size(self.W, self._h)
            if first or not self.moved:
                self.win.geometry(f"{self.W}x{self._h}+{self.app.sw - self.W - S(8)}+{S(8)}")
            self.bindall(self.outer)
            return
        if animate and getattr(self, "_econ_clip", None) and self._econ_clip.winfo_exists() and self.pages() > 1:
            self._animate_page()
            return
        self._lock_clips = True
        self._build(*self._gaps(self._k))
        self.win.update_idletasks()
        self.set_size(self.W, self._h)
        if first or not self.moved:
            self.win.geometry(f"{self.W}x{self._h}+{self.app.sw - self.W - S(8)}+{S(8)}")
        self.bindall(self.outer)

    def _animate_page(self):
        """透明键色窗口上移动控件会闪，翻页改成文字淡出再淡入。"""
        item_gap, group_gap, ex_gap = self._gaps(self._k)
        page = self.app.page % self.pages()
        old_e, old_d = self._econ_inner, self._deals_inner
        new_e = tk.Frame(self._econ_clip, bg=KEY)
        new_d = tk.Frame(self._deals_clip, bg=KEY)
        self._fill_econ(new_e, page, item_gap, group_gap, ex_gap)
        self._fill_deals(new_d, page, item_gap, group_gap, ex_gap)
        for lb in _all_labels(new_e) + _all_labels(new_d):
            lb._orig_fg = lb.cget("fg")
            lb.config(fg=KEY)
        old_fgs = [(lb, lb.cget("fg")) for lb in _all_labels(old_e) + _all_labels(old_d)]
        steps = 5
        dt = max(16, int(PAGE_ANIM_MS / (steps * 2)))
        state = {"phase": "out", "i": 0, "swapped": False}

        def swap():
            if state["swapped"]:
                return
            state["swapped"] = True
            try:
                if old_e.winfo_exists():
                    old_e.destroy()
                if old_d.winfo_exists():
                    old_d.destroy()
            except tk.TclError:
                pass
            new_e.pack(fill="x")
            new_d.pack(fill="x")
            self._econ_inner, self._deals_inner = new_e, new_d

        def apply_fade(labels, t, to_key=True):
            for item in labels:
                if to_key:
                    lb, src = item
                    dest = KEY
                else:
                    lb = item
                    src, dest = KEY, getattr(lb, "_orig_fg", self.th["main"])
                try:
                    if lb.winfo_exists():
                        lb.config(fg=_mix_color(src, dest, t))
                except tk.TclError:
                    pass

        def finish(snap=False):
            if state.get("done"):
                return
            state["done"] = True
            swap()
            for lb in _all_labels(new_e) + _all_labels(new_d):
                try:
                    if lb.winfo_exists():
                        lb.config(fg=getattr(lb, "_orig_fg", self.th["main"]))
                except tk.TclError:
                    pass
            self._anim = None
            if not snap:
                self.bindall(self.outer)

        def step():
            a = getattr(self, "_anim", None)
            if not a or a.get("finish") is not finish:
                return
            if state["phase"] == "out":
                state["i"] += 1
                apply_fade(old_fgs, state["i"] / steps, True)
                if state["i"] >= steps:
                    swap()
                    state["phase"] = "in"
                    state["i"] = 0
                a["id"] = self.win.after(dt, step)
                return
            state["i"] += 1
            apply_fade(_all_labels(new_e) + _all_labels(new_d), state["i"] / steps, False)
            if state["i"] >= steps:
                finish()
                return
            a["id"] = self.win.after(dt, step)

        self._anim = dict(id=None, finish=finish)
        step()

    def _make_clip(self, height):
        clip = tk.Frame(self.body, bg=KEY)
        if getattr(self, "_lock_clips", False) and height:
            clip.configure(height=height)
            clip.pack_propagate(False)
        clip.pack(fill="x")
        inner = tk.Frame(clip, bg=KEY)
        inner.pack(fill="x")
        return clip, inner

    def _build(self, item_gap, group_gap, ex_gap, bind=True):
        for w in self.body.winfo_children():
            w.destroy()
        page = self.app.page % self.pages()
        self._econ_clip, self._econ_inner = self._make_clip(getattr(self, "_econ_h", 0))
        self._fill_econ(self._econ_inner, page, item_gap, group_gap, ex_gap)
        self._words_box = tk.Frame(self.body, bg=KEY)
        self._words_box.pack(fill="x")
        self._fill_words(self._words_box, item_gap, group_gap, ex_gap)
        self._deals_clip, self._deals_inner = self._make_clip(getattr(self, "_deals_h", 0))
        self._fill_deals(self._deals_inner, page, item_gap, group_gap, ex_gap)
        if bind:
            self.bindall(self.body)
            self.bindall(self.foot)

    def _group_title(self, parent, title, first_group=False, group_gap=None):
        S = self.app.S
        if group_gap is None:
            group_gap = self._gaps(getattr(self, "_k", 1))[1]
        self.label(parent, title, 9, "sub").pack(
            fill="x", pady=(0 if first_group else group_gap, S(3)))

    def _item_title(self, it):
        return str(it.get("title") or "") if isinstance(it, dict) else str(it or "")

    def _item_url(self, it):
        if isinstance(it, dict):
            return str(it.get("url") or it.get("link") or "").strip()
        return ""

    def _numbered(self, parent, items, empty, chunk, item_gap):
        S = self.app.S
        wrap = S(214)
        if not items:
            self.label(parent, empty, 10, "main", wraplength=wrap).pack(fill="x")
            return
        numw = self.font(10).measure("5.  ")   # 序号列固定宽度：换行后的第二行与标题首字对齐
        for n, it in enumerate(chunk, 1):
            t = self._item_title(it)
            url = self._item_url(it)
            row = tk.Frame(parent, bg=KEY)
            row.pack(fill="x", pady=(0, item_gap))
            row.columnconfigure(0, minsize=numw)
            nlb = self.label(row, f"{n}.", 10, "main")
            nlb.grid(row=0, column=0, sticky="nw")
            tlb = self.label(row, t, 10, "main", wraplength=wrap - numw)
            tlb.grid(row=0, column=1, sticky="nw")
            if url:
                for w in (row, nlb, tlb):
                    w._tina_url = url
                nlb.config(cursor="hand2")
                tlb.config(cursor="hand2")

    def _fill_econ(self, parent, page, item_gap, group_gap, ex_gap):
        lo = page * self.PER_PAGE
        self._group_title(parent, "经济热点", True, group_gap)
        self._numbered(parent, self.econ, "暂无数据", self.econ[lo:lo + self.PER_PAGE], item_gap)

    def _fill_words(self, parent, item_gap, group_gap, ex_gap):
        S = self.app.S
        wrap = S(214)
        self._group_title(parent, "今日英文", group_gap=group_gap)
        if not self.words:
            self.label(parent, "暂无数据", 10, "main").pack(fill="x")
            return
        for w in self.words[:10]:
            ipa = str(w.get("ipa", "")).strip("/ ")
            line = f"{w.get('word', '')}  /{ipa}/  {w.get('zh', '')}" if ipa else f"{w.get('word', '')}  {w.get('zh', '')}"
            has_ex = bool(w.get("example"))
            self.label(parent, line, 10, "main", wraplength=wrap).pack(
                fill="x", pady=(0, ex_gap if has_ex else item_gap))
            if has_ex:
                self.label(parent, str(w["example"]), 8, "sub", wraplength=wrap).pack(
                    fill="x", pady=(0, item_gap))

    def _fill_deals(self, parent, page, item_gap, group_gap, ex_gap):
        coupons, tokens = self._deal_groups()
        n_c = math.ceil(len(coupons) / self.PER_PAGE) if coupons else 0
        n_t = math.ceil(len(tokens) / self.PER_PAGE) if tokens else 0
        if not self.deals:
            self._group_title(parent, "今日羊毛", group_gap=group_gap)
            self._numbered(parent, [], "暂无数据", [], item_gap)
            return
        total_d = n_c + n_t
        dp = (page % total_d) if total_d else 0
        if n_c and dp < n_c:
            self._group_title(parent, "今日羊毛（优惠券）", group_gap=group_gap)
            chunk = coupons[dp * self.PER_PAGE:(dp + 1) * self.PER_PAGE]
            self._numbered(parent, coupons, "暂无数据", chunk, item_gap)
        else:
            self._group_title(parent, "今日羊毛（token）", group_gap=group_gap)
            off = dp - n_c
            chunk = tokens[off * self.PER_PAGE:(off + 1) * self.PER_PAGE]
            self._numbered(parent, tokens, "暂无数据", chunk, item_gap)

    def recolor(self):
        self.title.config(fg=self.th["title"])
        self.clock.config(fg=self.th["sub"])
        self.foot.config(fg=self.th["sub"])
        self.render()


# ───────────────────────── 应用 ─────────────────────────
class App:
    def __init__(self):
        self.root = tk.Tk()
        self.scale = self.root.winfo_fpixels("1i") / 96.0
        self.S = lambda v: int(round(v * self.scale))
        self.sw = self.root.winfo_screenwidth()
        self.sh = self.root.winfo_screenheight()
        self.theme_i = DEFAULT_THEME
        self.page = 0
        saved = load_settings()
        for i, (name, _) in enumerate(THEMES):
            if name == saved.get("theme"):
                self.theme_i = i
                break
        # 主窗口只做隐藏宿主：今日行情不能再用 root 本身，否则菜单和对话框会跟着沉到桌面层后面
        self.root.withdraw()

        self.menu = tk.Menu(self.root, tearoff=0, bg="#1f2430", fg="#f5f7fa",
                            activebackground="#8cb6ff", activeforeground="#111111", bd=0,
                            font=(FONT, 9, "bold"))
        self.menu.add_command(label="刷新", command=self.refresh)
        self.menu.add_command(label="", command=self.cycle_theme)
        self.menu.add_command(label="打开数据文件夹", command=self.open_folder)
        self.menu.add_command(label="立即更新数据", command=self.update_now)
        self.menu.add_command(label="编辑手动数据", command=self.edit_manual)
        self.menu.add_command(label="", command=self.toggle_autostart)
        self.menu.add_separator()
        self.menu.add_command(label="退出", command=self.root.destroy)
        self._menu_label()
        self._autostart_label()

        self.quotes = QuotesPanel(self, tk.Toplevel(self.root))
        self.tasks = TasksPanel(self, tk.Toplevel(self.root))
        self.panels = [self.quotes, self.tasks]

        self.root.update()
        for p in self.panels:
            make_desktop_window(p.win)
            sink_to_desktop(p.win)
        self._apply_saved_layout(saved)
        self._repair_autostart()
        self._clock()
        self.root.after(RELOAD_MS, self._reload_loop)
        self.root.after(TASKS_RELOAD_MS, self._tasks_reload_loop)
        self.root.after(PAGE_MS, self._page_loop)
        self.root.after(2000, self._sink_loop)
        # 外部遥控：启动时只记录当前状态，之后 control.json 有变化才响应（主题以 settings.json 为准）
        self._ctl_mtime = self._ctl_stat()
        self._ctl_token = (load_json(CONTROL) or {}).get("refresh")
        self.root.after(2000, self._control_loop)
        # 内置每日更新：后台线程，只处理文件，界面由 _control_loop 发现 _dirty 后刷新
        self._dirty = False
        self._force = False
        self._wake = threading.Event()
        threading.Thread(target=self._scheduler, daemon=True).start()

    @property
    def theme(self):
        return THEMES[self.theme_i][1]

    def _menu_label(self):
        self.menu.entryconfig(1, label=f"换文字颜色（当前：{THEMES[self.theme_i][0]}）")

    def cycle_theme(self):
        self.theme_i = (self.theme_i + 1) % len(THEMES)
        self._menu_label()
        for p in self.panels:
            p.recolor()
        self.save_layout()

    def save_layout(self):
        d = load_settings()
        d["theme"] = THEMES[self.theme_i][0]
        for p, key in ((self.quotes, "quotes"), (self.tasks, "tasks")):
            try:
                d[key] = {"x": int(p.win.winfo_x()), "y": int(p.win.winfo_y())}
            except Exception:
                pass
        try:
            write_settings(d)
        except Exception:
            pass

    def _apply_saved_layout(self, s=None):
        s = s if isinstance(s, dict) else load_settings()
        for p, key in ((self.quotes, "quotes"), (self.tasks, "tasks")):
            pos = s.get(key)
            if not isinstance(pos, dict):
                continue
            try:
                x, y = int(pos["x"]), int(pos["y"])
            except Exception:
                continue
            try:
                self.root.update_idletasks()
                w = p.win.winfo_width() or getattr(p, "W", 80)
                h = p.win.winfo_height() or 80
            except Exception:
                w, h = getattr(p, "W", 80), 80
            x = max(0, min(x, self.sw - max(40, w)))
            y = max(0, min(y, self.sh - max(40, h)))
            p.moved = True
            try:
                p.win.geometry(f"+{x}+{y}")
                sink_to_desktop(p.win)
            except Exception:
                pass

    def refresh(self):
        for p in self.panels:
            p.reload()

    def open_folder(self):
        try:
            os.startfile(DATA_DIR)
        except Exception as e:
            messagebox.showerror("TinaDesk", f"无法打开数据文件夹：{e}")

    def _clock(self):
        t = datetime.now(CN).strftime("%H:%M")
        for p in self.panels:
            p.clock.config(text=t)
        self.root.after(10_000, self._clock)

    def _reload_loop(self):
        self.quotes.reload()
        self.root.after(RELOAD_MS, self._reload_loop)

    def _tasks_reload_loop(self):
        self.tasks.reload()
        self.root.after(TASKS_RELOAD_MS, self._tasks_reload_loop)

    def _page_loop(self):  # 经济热点 / 今日羊毛 共用页码，一起翻
        self.page = (self.page + 1) % self.tasks.pages()
        self.tasks.render(refit=False, animate=True)
        self.root.after(PAGE_MS, self._page_loop)

    def _sink_loop(self):  # 应用窗口起来后，始终让小窗留在它们下面
        for p in self.panels:
            sink_to_desktop(p.win)
        self.root.after(2000, self._sink_loop)

    def _ctl_stat(self):
        try:
            return os.path.getmtime(CONTROL)
        except OSError:
            return None

    def _control_loop(self):
        if self._dirty:
            self._dirty = False
            self.refresh()
        m = self._ctl_stat()
        if m and m != self._ctl_mtime:
            self._ctl_mtime = m
            d = load_json(CONTROL) or {}
            for i, (name, _) in enumerate(THEMES):
                if name == d.get("theme") and i != self.theme_i:
                    self.theme_i = i
                    self._menu_label()
                    for p in self.panels:
                        p.recolor()
                    self.save_layout()
            tok = d.get("refresh")
            if tok != self._ctl_token:
                self._ctl_token = tok
                self.refresh()
        self.root.after(2000, self._control_loop)

    def _data_missing(self, name):
        """本地还没有可展示的数据（例如第一次打开）时返回 True。"""
        if name == "prices":
            d = load_json(PRICES)
            cols = d.get("columns") if isinstance(d, dict) else None
            return not (isinstance(cols, list) and any(items_of(c) for c in cols if isinstance(c, dict)))
        econ, words, deals, _ = load_tasks()
        return not (econ or words or deals)

    # ── 每日自动更新（行情 06:50 之后，任务内容 07:45 之后；失败每 10 分钟重试） ──
    # 本地还没有数据时（例如用户第一次打开）立刻更新，不必等到整点。
    def _scheduler(self):
        done = {"prices": None, "tasks": None}
        last_try = {"prices": 0.0, "tasks": 0.0}
        jobs = (("prices", (6, 50), ud.update_prices), ("tasks", (7, 45), ud.update_tasks))
        while True:
            force, self._force = self._force, False
            now = datetime.now(CN)
            for name, hm, fn in jobs:
                if not force:
                    missing = self._data_missing(name)
                    if not missing and (done[name] == now.date() or (now.hour, now.minute) < hm):
                        continue
                    if time.time() - last_try[name] < 600:
                        continue
                last_try[name] = time.time()
                try:
                    ok = bool(fn())
                except Exception as e:
                    ud.log(f"{name}: 更新异常 {e!r}")
                    ok = False
                if ok:
                    done[name] = now.date()
                self._dirty = True
            self._wake.wait(30)
            self._wake.clear()

    def update_now(self):
        self._force = True
        self._wake.set()

    def edit_manual(self):
        ud.load_manual()   # 确保文件存在
        try:
            subprocess.Popen(["notepad.exe", ud.MANUAL_PATH])
        except Exception as e:
            messagebox.showerror("TinaDesk", f"无法打开记事本：{e}")

    # ── 开机自启（写当前用户的 Run 注册表项，不需要管理员权限） ──
    RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
    RUN_NAME = "TinaDesk"

    def _autostart_cmd(self):
        if getattr(sys, "frozen", False):
            return f'"{sys.executable}"'
        py = sys.executable
        pyw = os.path.join(os.path.dirname(py), "pythonw.exe")
        return f'"{pyw if os.path.exists(pyw) else py}" "{os.path.abspath(__file__)}"'

    def _autostart_registered_cmd(self):
        if not IS_WIN:
            return None
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.RUN_KEY) as k:
                val, _ = winreg.QueryValueEx(k, self.RUN_NAME)
            return val
        except Exception:
            return None

    def _autostart_on(self):
        return bool(self._autostart_registered_cmd())

    def _repair_autostart(self):
        """文件夹或 exe 搬家后，把开机自启路径改成当前这一份。"""
        cur = self._autostart_registered_cmd()
        if not cur:
            return
        want = self._autostart_cmd()
        if cur.strip() == want.strip():
            return
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
                winreg.SetValueEx(k, self.RUN_NAME, 0, winreg.REG_SZ, want)
        except Exception:
            pass

    def _autostart_label(self):
        self.menu.entryconfig(5, label=f"开机自启：{'开' if self._autostart_on() else '关'}（点击切换）")

    def toggle_autostart(self):
        if not IS_WIN:
            messagebox.showerror("TinaDesk", "开机自启仅支持 Windows。")
            return
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
                if self._autostart_on():
                    winreg.DeleteValue(k, self.RUN_NAME)
                else:
                    winreg.SetValueEx(k, self.RUN_NAME, 0, winreg.REG_SZ, self._autostart_cmd())
        except Exception as e:
            messagebox.showerror("TinaDesk", f"无法更改开机自启：{e}")
            return
        self._autostart_label()

    def run(self):
        self.root.mainloop()


_mutex = None

if __name__ == "__main__":
    if IS_WIN:   # 只允许开一个实例，避免桌面上叠出两层
        _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "TinaDeskSingleInstance")
        if ctypes.windll.kernel32.GetLastError() == 183:
            try:
                ctypes.windll.user32.MessageBoxW(
                    None, "TinaDesk 已经在运行，请在桌面上查看小窗。", "TinaDesk", 0x00040040)
            except Exception:
                pass
            sys.exit(0)
    App().run()
