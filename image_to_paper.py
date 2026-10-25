# -*- coding: utf-8 -*-
"""
Image to Paper  --  Rasmni qog'oz (A3/A4/A5/10x15) ga joylab, printga tayyorlash
Eksport: PDF / PNG / JPG

Sichqoncha:
  - rasm (yoki nusxalar bloki) ustidan sudrab ko'chirish
  - atrofidagi nuqtalarni tortib kattalashtirish / kichraytirish
  - g'ildirak bilan kattalashtirish / kichraytirish
Taqash tugmalari: yuqori chap / yuqori o'ng / past chap / past o'ng / markaz
Ko'paytirish: rasmni ustun/qator bo'yicha nusxalash (masalan 4x2 varaqni pastga
nusxalab 4x4 = 16 foto olish)

Kerak: pip install pillow
"""

import os
import tkinter as tk
from tkinter import filedialog, messagebox

from PIL import Image, ImageDraw, ImageTk

# Qog'oz o'lchamlari (mm), portret holatida (eni, bo'yi)
PAPERS = {
    "A3": (297, 420),
    "A4": (210, 297),
    "A5": (148, 210),
    "10x15 sm": (100, 150),
}
DEFAULT_PAPER = "A4"

ORIENTS = [("auto", "Avto"), ("portrait", "Portret"), ("landscape", "Landshaft")]
FORMATS = ["PDF", "PNG", "JPG"]
DPIS = [150, 200, 300, 600]
DEFAULT_DPI = 300
MODES = [
    ("fit", "Sig'dirish"),
    ("fill", "To'ldirish"),
    ("actual", "Asl o'lcham"),
    ("width", "Eni (mm)"),
    ("manual", "Qo'lda"),
]

BG = "#1e1e2e"
BG_DARK = "#11111b"
BG_MID = "#181825"
BTN = "#313244"
ACCENT = "#89b4fa"
TXT = "#cdd6f4"
MUTED = "#6c7086"

HANDLE_PX = 6      # nuqta yarim o'lchami (px)
HIT_PX = 10        # nuqtani bosish zonasi (px)
MAX_FACTOR = 3.0   # blok eng ko'pi bilan qog'ozning 3 baravari bo'lishi mumkin
MAX_COPIES = 10


def paper_size_mm(paper, orient, img_w, img_h):
    """Yo'nalishni hisobga olib qog'oz o'lchamini (mm) qaytaradi."""
    w, h = PAPERS[paper]
    if orient == "auto":
        orient = "landscape" if img_w > img_h else "portrait"
    if orient == "landscape":
        w, h = h, w
    return float(w), float(h)


def block_size(w, h, cols, rows, gap):
    """Nusxalar blokining umumiy o'lchami (mm)."""
    return cols * w + (cols - 1) * gap, rows * h + (rows - 1) * gap


def place_image(img_w, img_h, pw, ph, margin, mode, src_dpi, width_mm,
                cols=1, rows=1, gap=0.0):
    """
    Avtomatik rejimlar uchun bitta rasm (tile) joyi (mm).
    Nusxalar bloki ish maydonida markazlanadi.
    Qaytaradi: (x, y, w, h), (ax0, ay0, ax1, ay1)
    """
    ax0, ay0 = margin, margin
    ax1, ay1 = pw - margin, ph - margin
    aw, ah = max(1.0, ax1 - ax0), max(1.0, ay1 - ay0)
    gw, gh = (cols - 1) * gap, (rows - 1) * gap
    fw = max(1.0, aw - gw) / (cols * img_w)
    fh = max(1.0, ah - gh) / (rows * img_h)

    if mode == "fill":
        s = max(fw, fh)
    elif mode == "actual":
        s = 25.4 / max(1.0, src_dpi)
    elif mode == "width":
        s = max(1.0, width_mm) / img_w
    else:  # fit
        s = min(fw, fh)

    w, h = img_w * s, img_h * s
    bw, bh = block_size(w, h, cols, rows, gap)
    x = ax0 + (aw - bw) / 2
    y = ay0 + (ah - bh) / 2
    return (x, y, w, h), (ax0, ay0, ax1, ay1)


def render_sheet(img, pw, ph, k, rect, clip, resample, guide,
                 cols=1, rows=1, gap=0.0):
    """
    Qog'ozni k (px/mm) masshtabda chizadi.
    rect -- birinchi (yuqori chap) rasm; qolganlari cols x rows setkada.
    Clip maydonidan chiqqan qismlar qirqiladi.
    """
    W, H = max(1, round(pw * k)), max(1, round(ph * k))
    sheet = Image.new("RGB", (W, H), (255, 255, 255))

    x, y, w, h = rect
    ax0, ay0 = round(clip[0] * k), round(clip[1] * k)
    ax1, ay1 = round(clip[2] * k), round(clip[3] * k)
    d = ImageDraw.Draw(sheet) if guide else None
    line_w = max(1, round(0.15 * k))
    cache = {}

    for r in range(rows):
        for c in range(cols):
            fx = x + c * (w + gap)
            fy = y + r * (h + gap)
            tx0, ty0 = round(fx * k), round(fy * k)
            tx1, ty1 = round((fx + w) * k), round((fy + h) * k)
            tw, th = max(1, tx1 - tx0), max(1, ty1 - ty0)

            left, top = max(ax0, tx0), max(ay0, ty0)
            right, bottom = min(ax1, tx0 + tw), min(ay1, ty0 + th)
            if right <= left or bottom <= top:
                continue

            key = (tw, th)
            if key not in cache:
                cache[key] = img.resize(key, resample)
            piece = cache[key].crop(
                (left - tx0, top - ty0, right - tx0, bottom - ty0))
            sheet.paste(piece, (left, top))

            if d is not None:
                d.rectangle((left, top, right - 1, bottom - 1),
                            outline=(150, 150, 150), width=line_w)
    return sheet


class ImageToPaper:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Image to Paper  --  Print tayyorlash")
        self.root.configure(bg=BG)
        self.root.geometry("1150x940")
        self.root.minsize(900, 680)

        self.original = None
        self.preview_src = None
        self.src_path = None
        self.tk_img = None

        self.manual_rect = None     # (x, y, w, h) mm -- bitta rasm, Qo'lda rejim
        self._view = (0, 0, 1.0)    # (ox, oy, k) -- preview koordinatalari
        self._cur_block = None      # nusxalar blokining (x, y, w, h) mm
        self._drag = None

        self.paper_var = tk.StringVar(value=DEFAULT_PAPER)
        self.orient_var = tk.StringVar(value="auto")
        self.fmt_var = tk.StringVar(value="PDF")
        self.mode_var = tk.StringVar(value="fit")
        self.dpi_var = tk.IntVar(value=DEFAULT_DPI)
        self.margin_var = tk.StringVar(value="5")
        self.srcdpi_var = tk.StringVar(value="200")
        self.width_var = tk.StringVar(value="150")
        self.guide_var = tk.BooleanVar(value=False)
        self.cols_var = tk.IntVar(value=1)
        self.rows_var = tk.IntVar(value=1)
        self.gap_var = tk.StringVar(value="0")

        self._seg_paint = {}
        self._build_ui()

        for v in (self.margin_var, self.srcdpi_var, self.width_var, self.gap_var):
            v.trace_add("write", lambda *_: self._redraw())
        self.guide_var.trace_add("write", lambda *_: self._redraw())

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        top = tk.Frame(self.root, bg=BG_DARK, padx=14, pady=10)
        top.pack(fill=tk.X)
        tk.Label(top, text="Image to Paper", font=("Segoe UI", 14, "bold"),
                 bg=BG_DARK, fg=TXT).pack(side=tk.LEFT)

        self.btn_save = self._btn(top, "Saqlash", ACCENT, self.export,
                                  tk.RIGHT, tk.DISABLED)
        self.btn_rot = self._btn(top, "90 burish", BTN, self.rotate_img,
                                 tk.RIGHT, tk.DISABLED, fg=TXT)
        self._btn(top, "Rasm ochish", "#a6e3a1", self.open_image, tk.RIGHT)

        bar1 = tk.Frame(self.root, bg=BG_MID, padx=14, pady=8)
        bar1.pack(fill=tk.X)

        self._label(bar1, "Qog'oz:").pack(side=tk.LEFT, padx=(0, 6))
        self._seg(bar1, [(p, p) for p in PAPERS], self.paper_var)
        self._sep(bar1)
        self._label(bar1, "Yo'nalish:").pack(side=tk.LEFT, padx=(0, 6))
        self._seg(bar1, ORIENTS, self.orient_var)
        self._sep(bar1)
        self._label(bar1, "Format:").pack(side=tk.LEFT, padx=(0, 6))
        self._seg(bar1, [(f, f) for f in FORMATS], self.fmt_var)

        bar2 = tk.Frame(self.root, bg=BG_MID, padx=14, pady=8)
        bar2.pack(fill=tk.X)

        self._label(bar2, "Joylash:").pack(side=tk.LEFT, padx=(0, 6))
        self._seg(bar2, MODES, self.mode_var)
        self._sep(bar2)

        self._label(bar2, "Chekka mm:").pack(side=tk.LEFT, padx=(0, 4))
        self._entry(bar2, self.margin_var, 4).pack(side=tk.LEFT)
        self._label(bar2, "  Asl DPI:").pack(side=tk.LEFT, padx=(8, 4))
        self._entry(bar2, self.srcdpi_var, 4).pack(side=tk.LEFT)
        self._label(bar2, "  Eni mm:").pack(side=tk.LEFT, padx=(8, 4))
        self._entry(bar2, self.width_var, 5).pack(side=tk.LEFT)
        self._sep(bar2)

        self._label(bar2, "Chiqish DPI:").pack(side=tk.LEFT, padx=(0, 6))
        self._seg(bar2, [(d, str(d)) for d in DPIS], self.dpi_var)

        bar3 = tk.Frame(self.root, bg=BG_MID, padx=14, pady=8)
        bar3.pack(fill=tk.X)

        self._label(bar3, "Taqash:").pack(side=tk.LEFT, padx=(0, 6))
        for text, where in (("Yuqori chap", "tl"), ("Yuqori o'ng", "tr"),
                            ("Past chap", "bl"), ("Past o'ng", "br"),
                            ("Markaz", "c")):
            self._small_btn(bar3, text, lambda w=where: self.snap(w))
        self._sep(bar3)

        self._label(bar3, "O'lcham:").pack(side=tk.LEFT, padx=(0, 6))
        self._small_btn(bar3, "  -  ", lambda: self.scale_by(1 / 1.1))
        self._small_btn(bar3, "  +  ", lambda: self.scale_by(1.1))
        self._sep(bar3)
        self._small_btn(bar3, "Tiklash", self.reset_layout)
        self._sep(bar3)

        tk.Checkbutton(bar3, text="Qirqish chizig'i", variable=self.guide_var,
                       bg=BG_MID, fg=TXT, selectcolor=BTN,
                       activebackground=BG_MID, activeforeground=TXT,
                       font=("Segoe UI", 9)).pack(side=tk.LEFT)

        bar4 = tk.Frame(self.root, bg=BG_MID, padx=14, pady=8)
        bar4.pack(fill=tk.X)

        self._label(bar4, "Ko'paytirish:").pack(side=tk.LEFT, padx=(0, 6))
        self._small_btn(bar4, "Pastga nusxa", lambda: self._add_copies(0, 1))
        self._small_btn(bar4, "O'ngga nusxa", lambda: self._add_copies(1, 0))
        self._sep(bar4)

        self._label(bar4, "Ustun:").pack(side=tk.LEFT, padx=(0, 4))
        self._small_btn(bar4, " - ", lambda: self._add_copies(-1, 0))
        tk.Label(bar4, textvariable=self.cols_var, width=3, bg=BG_MID, fg=TXT,
                 font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        self._small_btn(bar4, " + ", lambda: self._add_copies(1, 0))

        self._label(bar4, "   Qator:").pack(side=tk.LEFT, padx=(8, 4))
        self._small_btn(bar4, " - ", lambda: self._add_copies(0, -1))
        tk.Label(bar4, textvariable=self.rows_var, width=3, bg=BG_MID, fg=TXT,
                 font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        self._small_btn(bar4, " + ", lambda: self._add_copies(0, 1))
        self._sep(bar4)

        self._label(bar4, "Oraliq mm:").pack(side=tk.LEFT, padx=(0, 4))
        self._entry(bar4, self.gap_var, 4).pack(side=tk.LEFT)
        self._sep(bar4)
        self._small_btn(bar4, "1x1", lambda: self._set_counts(1, 1))

        self.status_var = tk.StringVar(value="Rasm oching.")
        tk.Label(self.root, textvariable=self.status_var, anchor=tk.W,
                 bg=BTN, fg="#a6adc8", font=("Segoe UI", 9),
                 padx=12, pady=6).pack(fill=tk.X)

        self.cv = tk.Canvas(self.root, bg="#2a2a3c", highlightthickness=0)
        self.cv.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.cv.bind("<Configure>", lambda _: self._redraw())
        self.cv.bind("<ButtonPress-1>", self._press)
        self.cv.bind("<B1-Motion>", self._drag_move)
        self.cv.bind("<ButtonRelease-1>", self._release)
        self.cv.bind("<Motion>", self._hover)
        self.cv.bind("<MouseWheel>", self._wheel)
        self.cv.bind("<Button-4>", lambda e: self._wheel(e, 1))
        self.cv.bind("<Button-5>", lambda e: self._wheel(e, -1))

        self.info_var = tk.StringVar()
        tk.Label(self.root, textvariable=self.info_var, bg=BG_DARK,
                 fg="#585b70", font=("Segoe UI", 8), pady=4).pack(fill=tk.X)

    @staticmethod
    def _label(parent, text):
        return tk.Label(parent, text=text, bg=BG_MID, fg=MUTED,
                        font=("Segoe UI", 9))

    @staticmethod
    def _entry(parent, var, width):
        return tk.Entry(parent, textvariable=var, width=width,
                        font=("Segoe UI", 10, "bold"), bg=BTN, fg=TXT,
                        insertbackground=TXT, relief=tk.FLAT)

    @staticmethod
    def _sep(parent):
        tk.Frame(parent, bg="#45475a", width=1).pack(
            side=tk.LEFT, fill=tk.Y, padx=12, pady=2)

    @staticmethod
    def _btn(parent, text, color, cmd, side=tk.LEFT, state=tk.NORMAL, fg="#1e1e2e"):
        b = tk.Button(parent, text=text, command=cmd, bg=color, fg=fg,
                      activebackground=color, font=("Segoe UI", 10, "bold"),
                      relief=tk.FLAT, bd=0, padx=14, pady=7,
                      cursor="hand2", state=state)
        b.pack(side=side, padx=4)
        return b

    @staticmethod
    def _small_btn(parent, text, cmd):
        b = tk.Button(parent, text=text, command=cmd, bg=BTN, fg=TXT,
                      activebackground="#45475a", activeforeground=TXT,
                      font=("Segoe UI", 9, "bold"), relief=tk.FLAT, bd=0,
                      padx=10, pady=4, cursor="hand2")
        b.pack(side=tk.LEFT, padx=2)
        return b

    def _seg(self, parent, options, var):
        """Segmentli tugmalar guruhi (tanlangani ko'k)."""
        buttons = {}

        def paint():
            cur = str(var.get())
            for val, b in buttons.items():
                on = (val == cur)
                b.config(bg=ACCENT if on else BTN,
                         fg="#1e1e2e" if on else TXT)

        def pick(val):
            # Avtomatik rejimdan "Qo'lda" ga o'tishda joriy joyni saqlab qolamiz
            if (var is self.mode_var and val == "manual"
                    and self.mode_var.get() != "manual" and self.original):
                self.manual_rect = self._auto_rect()
            var.set(type(var.get())(val))
            paint()
            self._redraw()

        for val, text in options:
            b = tk.Button(parent, text=text, command=lambda v=val: pick(v),
                          bg=BTN, fg=TXT, activebackground="#45475a",
                          font=("Segoe UI", 9, "bold"), relief=tk.FLAT, bd=0,
                          padx=10, pady=4, cursor="hand2")
            b.pack(side=tk.LEFT, padx=2)
            buttons[str(val)] = b
        self._seg_paint[id(var)] = paint
        paint()

    def _set_mode(self, val):
        self.mode_var.set(val)
        self._seg_paint[id(self.mode_var)]()

    # ── Hisob-kitob ───────────────────────────────────────────────────────────

    @staticmethod
    def _num(var, default, lo=0.0):
        try:
            return max(lo, float(str(var.get()).replace(",", ".")))
        except (ValueError, tk.TclError):
            return default

    def _counts(self):
        try:
            c, r = int(self.cols_var.get()), int(self.rows_var.get())
        except (ValueError, tk.TclError):
            c, r = 1, 1
        return max(1, c), max(1, r)

    def _gap(self):
        return self._num(self.gap_var, 0.0, 0.0)

    def _paper(self):
        iw, ih = self.original.size
        pw, ph = paper_size_mm(self.paper_var.get(), self.orient_var.get(), iw, ih)
        margin = min(self._num(self.margin_var, 5.0), min(pw, ph) / 2 - 1)
        return pw, ph, margin

    def _block(self, rect):
        """Nusxalar blokining (x, y, w, h) si (mm)."""
        cols, rows = self._counts()
        x, y, w, h = rect
        bw, bh = block_size(w, h, cols, rows, self._gap())
        return x, y, bw, bh

    def _auto_rect(self):
        """Avtomatik rejim bo'yicha bitta rasm joyi (Qo'lda bo'lsa -- sig'dirish)."""
        iw, ih = self.original.size
        pw, ph, margin = self._paper()
        mode = self.mode_var.get()
        if mode == "manual":
            mode = "fit"
        cols, rows = self._counts()
        rect, _ = place_image(
            iw, ih, pw, ph, margin, mode,
            self._num(self.srcdpi_var, 200.0, 1.0),
            self._num(self.width_var, 100.0, 1.0),
            cols, rows, self._gap())
        return rect

    def _geometry(self):
        """
        Qaytaradi: pw, ph, rect, clip, area
          rect -- birinchi rasm joyi (mm), clip -- qirqish maydoni,
          area -- chekka maydoni.
        """
        pw, ph, margin = self._paper()
        area = (margin, margin, pw - margin, ph - margin)

        if self.mode_var.get() == "manual":
            if self.manual_rect is None:
                self.manual_rect = self._auto_rect()
            rect = self.manual_rect
            clip = (0.0, 0.0, pw, ph)   # qo'lda rejimda butun varaq ichida erkin
        else:
            rect = self._auto_rect()
            clip = area
        return pw, ph, rect, clip, area

    def _enter_manual(self):
        """Hozirgi joyni saqlab, Qo'lda rejimga o'tish."""
        if self.mode_var.get() != "manual":
            self.manual_rect = self._auto_rect()
            self._set_mode("manual")
        elif self.manual_rect is None:
            self.manual_rect = self._auto_rect()

    # ── Rasm ──────────────────────────────────────────────────────────────────

    def open_image(self):
        path = filedialog.askopenfilename(
            title="Rasm tanlang",
            filetypes=[("Rasmlar", "*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp")])
        if not path:
            return
        try:
            img = Image.open(path)
            dpi = img.info.get("dpi")
            rgb = img.convert("RGB")
        except Exception as e:
            messagebox.showerror("Xato", f"Rasmni ochib bo'lmadi: {e}")
            return

        # Avval hamma narsani to'liq o'rnatamiz, keyin o'zgaruvchilarga tegamiz
        # (ular _redraw ni ishga tushiradi).
        self.original = rgb
        self.src_path = path
        self.manual_rect = None
        self._make_preview_src()
        self.btn_save.config(state=tk.NORMAL)
        self.btn_rot.config(state=tk.NORMAL)

        if dpi and dpi[0] and 30 <= dpi[0] <= 1200:
            self.srcdpi_var.set(str(round(dpi[0])))
        self._redraw()

    def _make_preview_src(self):
        p = self.original.copy()
        p.thumbnail((1600, 1600), Image.LANCZOS)
        self.preview_src = p

    def rotate_img(self):
        if not self.original:
            return
        self.original = self.original.rotate(-90, expand=True)
        self.manual_rect = None
        self._make_preview_src()
        self._redraw()

    # ── Taqash / o'lcham / nusxa / tiklash ────────────────────────────────────

    def snap(self, where):
        """Rasmni (yoki nusxalar blokini) chekka maydonining burchagiga taqash."""
        if not self.original:
            return
        pw, ph, rect, _, area = self._geometry()
        _, _, w, h = rect
        _, _, bw, bh = self._block(rect)
        ax0, ay0, ax1, ay1 = area
        if where == "tl":
            x, y = ax0, ay0
        elif where == "tr":
            x, y = ax1 - bw, ay0
        elif where == "bl":
            x, y = ax0, ay1 - bh
        elif where == "br":
            x, y = ax1 - bw, ay1 - bh
        else:
            x, y = (pw - bw) / 2, (ph - bh) / 2
        self.manual_rect = (x, y, w, h)
        self._set_mode("manual")
        self._redraw()

    def scale_by(self, factor, cx=None, cy=None):
        """Rasmlarni markaz (yoki berilgan nuqta) atrofida kattalashtirish."""
        if not self.original:
            return
        pw, ph, rect, _, _ = self._geometry()
        cols, rows = self._counts()
        gap = self._gap()
        bx, by, bw, bh = self._block(rect)
        _, _, w, h = rect

        max_w = max(pw, ph) * MAX_FACTOR / cols
        nw = max(3.0, min(w * factor, max_w))
        nh = nw * h / w
        nbw, nbh = block_size(nw, nh, cols, rows, gap)

        if cx is None:
            cx, cy = bx + bw / 2, by + bh / 2
        nx = cx - (cx - bx) * nbw / bw
        ny = cy - (cy - by) * nbh / bh
        self.manual_rect = (nx, ny, nw, nh)
        self._set_mode("manual")
        self._redraw()

    def _set_counts(self, cols, rows):
        """
        Nusxalar sonini o'zgartirish. Avval hozirgi rasm o'lchami va joyi
        saqlanadi (Qo'lda rejim), shuning uchun rasm kichrayib ketmaydi.
        """
        cols = max(1, min(MAX_COPIES, cols))
        rows = max(1, min(MAX_COPIES, rows))
        if self.original:
            self._enter_manual()
        self.cols_var.set(cols)
        self.rows_var.set(rows)
        self._redraw()

    def _add_copies(self, dc, dr):
        c, r = self._counts()
        self._set_counts(c + dc, r + dr)

    def reset_layout(self):
        if not self.original:
            return
        self.manual_rect = None
        self._set_mode("fit")
        self._redraw()

    # ── Sichqoncha ────────────────────────────────────────────────────────────

    def _to_mm(self, ex, ey):
        ox, oy, k = self._view
        return (ex - ox) / k, (ey - oy) / k

    def _handle_points(self):
        """Nuqtalar (blok atrofida): [(hx, hy, canvas_x, canvas_y), ...]"""
        if not self._cur_block:
            return []
        ox, oy, k = self._view
        x, y, w, h = self._cur_block
        x0, y0, cw, ch = ox + x * k, oy + y * k, w * k, h * k
        pts = []
        for hy in (-1, 0, 1):
            for hx in (-1, 0, 1):
                if hx == 0 and hy == 0:
                    continue
                pts.append((hx, hy, x0 + (hx + 1) * cw / 2, y0 + (hy + 1) * ch / 2))
        return pts

    def _hit(self, ex, ey):
        """('handle', hx, hy) | ('move',) | None"""
        if not self.original or not self._cur_block:
            return None
        best, best_d = None, HIT_PX + 1
        for hx, hy, px, py in self._handle_points():
            d = max(abs(ex - px), abs(ey - py))
            if d <= HIT_PX and d < best_d:
                best, best_d = ("handle", hx, hy), d
        if best:
            return best
        mx, my = self._to_mm(ex, ey)
        x, y, w, h = self._cur_block
        if x <= mx <= x + w and y <= my <= y + h:
            return ("move",)
        return None

    @staticmethod
    def _cursor_for(hit):
        if hit is None:
            return ""
        if hit[0] == "move":
            return "fleur"
        hx, hy = hit[1], hit[2]
        if hx != 0 and hy != 0:
            return "size_nw_se" if hx == hy else "size_ne_sw"
        return "sb_h_double_arrow" if hx != 0 else "sb_v_double_arrow"

    def _set_cursor(self, name):
        try:
            self.cv.config(cursor=name)
        except tk.TclError:
            self.cv.config(cursor="fleur" if name else "")

    def _hover(self, e):
        if self._drag:
            return
        self._set_cursor(self._cursor_for(self._hit(e.x, e.y)))

    def _press(self, e):
        hit = self._hit(e.x, e.y)
        if not hit:
            self._drag = None
            return
        mx, my = self._to_mm(e.x, e.y)
        _, _, rect, _, _ = self._geometry()
        self._drag = {
            "hit": hit,
            "block": self._block(rect),   # boshlang'ich blok
            "tile": rect[2:],             # boshlang'ich rasm (w, h)
            "m0": (mx, my),
        }

    def _release(self, e):
        self._drag = None

    def _drag_move(self, e):
        d = self._drag
        if not d:
            return
        self._enter_manual()
        pw, ph, _ = self._paper()
        _, _, k = self._view
        _, _, _, _, area = self._geometry()
        cols, rows = self._counts()
        gap = self._gap()
        gw, gh = (cols - 1) * gap, (rows - 1) * gap
        mx, my = self._to_mm(e.x, e.y)
        sx, sy, sbw, sbh = d["block"]
        sw, sh = d["tile"]

        if d["hit"][0] == "move":
            x = sx + (mx - d["m0"][0])
            y = sy + (my - d["m0"][1])
            w, h = sw, sh
            thr = 6.0 / k   # magnit zonasi (mm)
            x = self._magnet(x, [area[0], area[2] - sbw, (pw - sbw) / 2], thr)
            y = self._magnet(y, [area[1], area[3] - sbh, (ph - sbh) / 2], thr)
            x = max(-sbw / 2, min(x, pw - sbw / 2))
            y = max(-sbh / 2, min(y, ph - sbh / 2))
        else:
            _, hx, hy = d["hit"]
            asp = sw / sh
            axm = sx if hx == 1 else (sx + sbw if hx == -1 else sx + sbw / 2)
            aym = sy if hy == 1 else (sy + sbh if hy == -1 else sy + sbh / 2)
            cand = []
            if hx != 0:
                cand.append((abs(mx - axm) - gw) / cols)
            if hy != 0:
                cand.append(((abs(my - aym) - gh) / rows) * asp)
            max_w = max(pw, ph) * MAX_FACTOR / cols
            w = max(3.0, min(max(cand), max_w))
            h = w / asp
            bw, bh = block_size(w, h, cols, rows, gap)
            x = axm if hx == 1 else (axm - bw if hx == -1 else axm - bw / 2)
            y = aym if hy == 1 else (aym - bh if hy == -1 else aym - bh / 2)

        self.manual_rect = (x, y, w, h)
        self._redraw()

    @staticmethod
    def _magnet(value, targets, thr):
        best, best_d = value, thr
        for t in targets:
            dist = abs(value - t)
            if dist < best_d:
                best, best_d = t, dist
        return best

    def _wheel(self, e, direction=None):
        if not self.original:
            return
        if direction is None:
            direction = 1 if e.delta > 0 else -1
        mx, my = self._to_mm(e.x, e.y)
        self.scale_by(1.05 if direction > 0 else 1 / 1.05, mx, my)

    # ── Preview ───────────────────────────────────────────────────────────────

    def _redraw(self):
        if not self.original or self.preview_src is None:
            return
        try:
            pw, ph, rect, clip, area = self._geometry()
        except Exception:
            return

        cols, rows = self._counts()
        gap = self._gap()

        cw = self.cv.winfo_width() or 960
        ch = self.cv.winfo_height() or 640
        pad = 28
        k = min((cw - 2 * pad) / pw, (ch - 2 * pad) / ph)
        if k <= 0:
            return

        sheet = render_sheet(self.preview_src, pw, ph, k, rect, clip,
                             Image.BILINEAR, self.guide_var.get(),
                             cols, rows, gap)
        self.tk_img = ImageTk.PhotoImage(sheet)
        ox = (cw - sheet.width) // 2
        oy = (ch - sheet.height) // 2
        block = self._block(rect)
        self._view = (ox, oy, k)
        self._cur_block = block

        self.cv.delete("all")
        self.cv.create_rectangle(ox + 4, oy + 4, ox + sheet.width + 4,
                                 oy + sheet.height + 4, fill="#15151f", outline="")
        self.cv.create_image(ox, oy, anchor=tk.NW, image=self.tk_img)
        self.cv.create_rectangle(ox, oy, ox + sheet.width, oy + sheet.height,
                                 outline="#585b70")
        # Chekka (ish maydoni) belgisi
        self.cv.create_rectangle(
            ox + area[0] * k, oy + area[1] * k, ox + area[2] * k, oy + area[3] * k,
            outline="#a6adc8", dash=(3, 5))

        # Blok ramkasi va nuqtalar
        bx, by, bw, bh = block
        self.cv.create_rectangle(ox + bx * k, oy + by * k,
                                 ox + (bx + bw) * k, oy + (by + bh) * k,
                                 outline=ACCENT, width=1)
        for _, _, px, py in self._handle_points():
            self.cv.create_rectangle(px - HANDLE_PX, py - HANDLE_PX,
                                     px + HANDLE_PX, py + HANDLE_PX,
                                     fill=ACCENT, outline=BG_DARK, width=1)

        self._update_info(pw, ph, rect, block, clip)

    def _update_info(self, pw, ph, rect, block, clip):
        iw, ih = self.original.size
        _, _, w, h = rect
        bx, by, bw, bh = block
        cols, rows = self._counts()
        dpi = self.dpi_var.get()
        out_w, out_h = round(pw * dpi / 25.4), round(ph * dpi / 25.4)
        eff = iw / (w / 25.4) if w > 0 else 0

        copies = f"Nusxa: {cols}x{rows} = {cols * rows} ta  |  " if cols * rows > 1 else ""
        self.info_var.set(
            f"Qog'oz: {self.paper_var.get()} {pw:.0f}x{ph:.0f} mm  |  "
            f"Chiqish: {out_w}x{out_h} px @ {dpi} DPI  |  "
            f"Rasm: {w/10:.1f}x{h/10:.1f} sm  |  {copies}"
            f"Blok: {bw/10:.1f}x{bh/10:.1f} sm  |  "
            f"Joyi: x={bx:.1f} y={by:.1f} mm  |  "
            f"Sifat: {eff:.0f} DPI")

        msg = f"{os.path.basename(self.src_path)}  ({iw}x{ih} px)"
        clipped = (bx < clip[0] - 0.01 or by < clip[1] - 0.01 or
                   bx + bw > clip[2] + 0.01 or by + bh > clip[3] + 0.01)
        if clipped:
            msg += "  |  Diqqat: rasm maydondan chiqib ketgan, qirqiladi."
        elif eff < 150:
            msg += f"  |  Diqqat: print sifati past ({eff:.0f} DPI)."
        else:
            msg += "  |  Sudrab ko'chiring, nuqtalardan torting, g'ildirak bilan o'lchamni o'zgartiring."
        self.status_var.set(msg)

    # ── Eksport ───────────────────────────────────────────────────────────────

    def export(self):
        if not self.original:
            return
        fmt = self.fmt_var.get()
        ext = {"PDF": ".pdf", "PNG": ".png", "JPG": ".jpg"}[fmt]
        base = os.path.splitext(os.path.basename(self.src_path or "print"))[0]

        save_path = filedialog.asksaveasfilename(
            title=f"{fmt} sifatida saqlang",
            initialfile=f"{base}_{self.paper_var.get().replace(' ', '')}{ext}",
            defaultextension=ext,
            filetypes=[(fmt, f"*{ext}"), ("Barcha fayllar", "*.*")])
        if not save_path:
            return

        try:
            self.root.config(cursor="watch")
            self.root.update_idletasks()

            dpi = self.dpi_var.get()
            cols, rows = self._counts()
            pw, ph, rect, clip, _ = self._geometry()
            sheet = render_sheet(self.original, pw, ph, dpi / 25.4, rect, clip,
                                 Image.LANCZOS, self.guide_var.get(),
                                 cols, rows, self._gap())

            if fmt == "PDF":
                sheet.save(save_path, "PDF", resolution=float(dpi))
            elif fmt == "PNG":
                sheet.save(save_path, "PNG", dpi=(dpi, dpi), optimize=True)
            else:
                sheet.save(save_path, "JPEG", quality=95, dpi=(dpi, dpi),
                           optimize=True)
        except Exception as e:
            messagebox.showerror("Xato", f"Saqlashda xato: {e}")
            return
        finally:
            self.root.config(cursor="")

        messagebox.showinfo(
            "Saqlandi!",
            f"Fayl:     {os.path.basename(save_path)}\n\n"
            f"Qog'oz:   {self.paper_var.get()} ({pw:.0f} x {ph:.0f} mm)\n"
            f"Format:   {fmt}\n"
            f"DPI:      {dpi}\n"
            f"Nusxa:    {cols}x{rows} = {cols * rows} ta\n"
            f"O'lcham:  {sheet.width} x {sheet.height} px")


def main():
    root = tk.Tk()
    ImageToPaper(root)
    root.mainloop()


if __name__ == "__main__":
    main()
