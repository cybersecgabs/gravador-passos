import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

import tkinter as tk
from tkinter import colorchooser, ttk
from PIL import Image, ImageDraw, ImageFont, ImageTk

PRESET_COLORS = [
    "#000000", "#ff0000", "#0000cc", "#00aa00",
    "#ffaa00", "#ff6600", "#9900cc", "#ffffff",
]
TOOL_NAMES = {
    "rectangle": "Retangulo",
    "ellipse": "Elipse",
    "line": "Linha",
    "arrow": "Seta",
    "text": "Texto",
    "pencil": "Lapis",
}
WIDTH_OPTIONS = [2, 3, 5, 8]
DEFAULT_FONT_SIZE = 14


@dataclass
class Annotation:
    tool: str
    coords: tuple
    color: str
    width: int
    text: str = ""
    font_size: int = DEFAULT_FONT_SIZE


class ImageEditor:
    def __init__(self, parent, screenshot_path, on_save=None):
        self.screenshot_path = screenshot_path
        self.on_save = on_save
        self.original_image = Image.open(screenshot_path).convert("RGB")
        self.annotations: List[Annotation] = []
        self.current_tool = "arrow"
        self.current_color = "#ff0000"
        self.current_width = 3

        self.top = tk.Toplevel(parent)
        self.top.title("Editor de Imagem")
        self.top.geometry("1100x750")
        self.top.minsize(700, 500)
        self.top.transient(parent)
        self.top.grab_set()
        self.top.protocol("WM_DELETE_WINDOW", self._cancel)

        self._scale = 1.0
        self._drag_start = None
        self._preview_item = None
        self._pencil_points: List[Tuple[float, float]] = []
        self._pencil_item = None
        self._text_entry: Optional[tk.Entry] = None
        self._text_pos = None
        self._text_window = None
        self._resize_after = None
        self._photo = None

        self._build_ui()
        self.top.after(50, self._fit_and_redraw)

    def _build_ui(self):
        toolbar = ttk.Frame(self.top, padding=4)
        toolbar.pack(fill=tk.X)

        tools_frame = ttk.Frame(toolbar)
        tools_frame.pack(side=tk.LEFT)
        self.tool_buttons = {}
        for tool, name in TOOL_NAMES.items():
            btn = tk.Button(
                tools_frame, text=name, relief=tk.FLAT,
                padx=6, pady=2,
                command=lambda t=tool: self._select_tool(t),
            )
            btn.pack(side=tk.LEFT, padx=1)
            self.tool_buttons[tool] = btn
        self._update_tool_buttons()

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=8)

        color_frame = ttk.Frame(toolbar)
        color_frame.pack(side=tk.LEFT)
        ttk.Label(color_frame, text="Cor:").pack(side=tk.LEFT)
        self.color_swatch = tk.Label(
            color_frame, bg=self.current_color, width=2, relief=tk.SUNKEN)
        self.color_swatch.pack(side=tk.LEFT, padx=2)
        for color in PRESET_COLORS:
            btn = tk.Button(
                color_frame, bg=color, width=1, relief=tk.FLAT,
                command=lambda c=color: self._select_color(c),
            )
            btn.pack(side=tk.LEFT, padx=1)
        tk.Button(
            color_frame, text="...", relief=tk.FLAT,
            command=self._choose_custom_color,
        ).pack(side=tk.LEFT, padx=2)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=8)

        width_frame = ttk.Frame(toolbar)
        width_frame.pack(side=tk.LEFT)
        ttk.Label(width_frame, text="Espessura:").pack(side=tk.LEFT)
        self.width_var = tk.StringVar(value=str(self.current_width))
        width_combo = ttk.Combobox(
            width_frame, textvariable=self.width_var,
            values=[str(w) for w in WIDTH_OPTIONS],
            width=3, state="readonly",
        )
        width_combo.pack(side=tk.LEFT, padx=2)
        width_combo.bind("<<ComboboxSelected>>", self._on_width_change)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=8)

        ttk.Button(toolbar, text="Desfazer",
                   command=self._undo).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Limpar",
                   command=self._clear).pack(side=tk.LEFT, padx=2)

        canvas_frame = ttk.Frame(self.top)
        canvas_frame.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(
            canvas_frame, bg="#cccccc", highlightthickness=0)
        hsb = ttk.Scrollbar(
            canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        vsb = ttk.Scrollbar(
            canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=hsb.set,
                              yscrollcommand=vsb.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)

        self.canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        bottom = ttk.Frame(self.top, padding=4)
        bottom.pack(fill=tk.X)
        ttk.Button(bottom, text="Reset",
                   command=self._reset).pack(side=tk.LEFT)
        ttk.Button(bottom, text="Cancelar",
                   command=self._cancel).pack(side=tk.RIGHT)
        ttk.Button(bottom, text="Salvar",
                   command=self._save).pack(side=tk.RIGHT)

    def _select_tool(self, tool):
        self.current_tool = tool
        self._update_tool_buttons()

    def _update_tool_buttons(self):
        for tool, btn in self.tool_buttons.items():
            btn.config(relief=(tk.SUNKEN if tool == self.current_tool
                               else tk.FLAT))

    def _select_color(self, color):
        self.current_color = color
        self.color_swatch.config(bg=color)

    def _choose_custom_color(self):
        result = colorchooser.askcolor(self.current_color, parent=self.top)
        if result and result[1]:
            self._select_color(result[1])

    def _on_width_change(self, _event):
        try:
            self.current_width = int(self.width_var.get())
        except ValueError:
            pass

    def _on_canvas_configure(self, _event):
        if self._resize_after:
            self.top.after_cancel(self._resize_after)
        self._resize_after = self.top.after(100, self._fit_and_redraw)

    def _fit_and_redraw(self):
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 10 or ch < 10:
            cw, ch = 1000, 600
        iw, ih = self.original_image.size
        self._scale = min(cw / iw, ch / ih, 1.0)
        self._redraw()

    def _redraw(self):
        self.canvas.delete("all")
        iw, ih = self.original_image.size
        dw, dh = int(iw * self._scale), int(ih * self._scale)
        display_img = self.original_image.resize((dw, dh), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(display_img)
        self.canvas.create_image(0, 0, image=self._photo, anchor="nw")
        self.canvas.config(scrollregion=(0, 0, dw, dh))
        for ann in self.annotations:
            self._draw_annotation(ann)

    def _draw_annotation(self, ann):
        x1, y1 = self._to_canvas(ann.coords[0], ann.coords[1])
        if ann.tool == "text":
            self.canvas.create_text(
                x1, y1, text=ann.text, fill=ann.color,
                font=("Arial", ann.font_size), anchor="nw")
        elif ann.tool == "pencil":
            pts = [self._to_canvas(x, y) for x, y in ann.coords]
            if len(pts) >= 2:
                self.canvas.create_line(
                    pts, fill=ann.color, width=ann.width,
                    smooth=True, capstyle=tk.ROUND, joinstyle=tk.ROUND)
        else:
            x2, y2 = self._to_canvas(ann.coords[2], ann.coords[3])
            if ann.tool == "rectangle":
                self.canvas.create_rectangle(
                    x1, y1, x2, y2, outline=ann.color, width=ann.width)
            elif ann.tool == "ellipse":
                self.canvas.create_oval(
                    x1, y1, x2, y2, outline=ann.color, width=ann.width)
            elif ann.tool == "line":
                self.canvas.create_line(
                    x1, y1, x2, y2, fill=ann.color, width=ann.width)
            elif ann.tool == "arrow":
                self.canvas.create_line(
                    x1, y1, x2, y2, fill=ann.color, width=ann.width,
                    arrow=tk.LAST, arrowshape=(16, 16, 4))

    def _to_canvas(self, img_x, img_y):
        return img_x * self._scale, img_y * self._scale

    def _to_image(self, canvas_x, canvas_y):
        return canvas_x / self._scale, canvas_y / self._scale

    def _on_canvas_press(self, event):
        self._cancel_text()
        if self.current_tool == "text":
            self._start_text(event)
            return
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        ix, iy = self._to_image(cx, cy)
        self._drag_start = (ix, iy)
        if self.current_tool == "pencil":
            self._pencil_points = [(ix, iy)]
            self._pencil_item = None

    def _on_canvas_motion(self, event):
        if not self._drag_start:
            return
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        ix, iy = self._to_image(cx, cy)

        if self.current_tool == "pencil":
            self._pencil_points.append((ix, iy))
            canvas_pts = [self._to_canvas(x, y) for x, y in self._pencil_points]
            if self._pencil_item:
                self.canvas.coords(self._pencil_item, *canvas_pts)
            elif len(canvas_pts) >= 2:
                self._pencil_item = self.canvas.create_line(
                    canvas_pts, fill=self.current_color,
                    width=self.current_width,
                    smooth=True, capstyle=tk.ROUND, joinstyle=tk.ROUND)
        else:
            if self._preview_item:
                self.canvas.delete(self._preview_item)
            sx, sy = self._to_canvas(*self._drag_start)
            ex, ey = self._to_canvas(ix, iy)
            tool = self.current_tool
            if tool == "rectangle":
                self._preview_item = self.canvas.create_rectangle(
                    sx, sy, ex, ey, outline=self.current_color,
                    width=self.current_width)
            elif tool == "ellipse":
                self._preview_item = self.canvas.create_oval(
                    sx, sy, ex, ey, outline=self.current_color,
                    width=self.current_width)
            elif tool == "line":
                self._preview_item = self.canvas.create_line(
                    sx, sy, ex, ey, fill=self.current_color,
                    width=self.current_width)
            elif tool == "arrow":
                self._preview_item = self.canvas.create_line(
                    sx, sy, ex, ey, fill=self.current_color,
                    width=self.current_width, arrow=tk.LAST,
                    arrowshape=(16, 16, 4))

    def _on_canvas_release(self, event):
        if not self._drag_start:
            return
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        ix, iy = self._to_image(cx, cy)
        sx, sy = self._drag_start

        if self.current_tool == "pencil":
            if len(self._pencil_points) >= 2:
                ann = Annotation(
                    tool="pencil", coords=tuple(self._pencil_points),
                    color=self.current_color, width=self.current_width)
                self.annotations.append(ann)
            self._pencil_points = []
            self._pencil_item = None
        else:
            if self._preview_item:
                self.canvas.delete(self._preview_item)
                self._preview_item = None
            if abs(ix - sx) > 2 or abs(iy - sy) > 2:
                ann = Annotation(
                    tool=self.current_tool, coords=(sx, sy, ix, iy),
                    color=self.current_color, width=self.current_width)
                self.annotations.append(ann)
                self._draw_annotation(ann)

        self._drag_start = None

    def _start_text(self, event):
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        ix, iy = self._to_image(cx, cy)
        self._text_pos = (ix, iy)
        self._text_entry = tk.Entry(
            self.canvas, font=("Arial", DEFAULT_FONT_SIZE),
            relief=tk.FLAT, bd=1, bg="#ffffe0")
        self._text_window = self.canvas.create_window(
            cx, cy, window=self._text_entry, anchor="nw")
        self._text_entry.focus_set()
        self._text_entry.bind("<Return>", self._commit_text)
        self._text_entry.bind("<Escape>", self._cancel_text)
        self._text_entry.bind("<FocusOut>", self._commit_text)

    def _commit_text(self, _event=None):
        if not self._text_entry:
            return
        text = self._text_entry.get().strip()
        if text:
            ann = Annotation(
                tool="text", coords=self._text_pos,
                color=self.current_color, width=self.current_width,
                text=text, font_size=DEFAULT_FONT_SIZE)
            self.annotations.append(ann)
            self._draw_annotation(ann)
        self._destroy_text_entry()

    def _cancel_text(self, _event=None):
        self._destroy_text_entry()

    def _destroy_text_entry(self):
        if self._text_window:
            self.canvas.delete(self._text_window)
            self._text_window = None
        if self._text_entry:
            self._text_entry.destroy()
            self._text_entry = None
        self._text_pos = None

    def _undo(self):
        if self.annotations:
            self.annotations.pop()
            self._redraw()

    def _clear(self):
        self.annotations = []
        self._redraw()

    def _reset(self):
        self.annotations = []
        self._redraw()

    def _save(self):
        img = self.original_image.copy()
        self._apply_annotations(img)
        img.save(self.screenshot_path)
        if self.on_save:
            self.on_save(self.screenshot_path)
        self.top.destroy()

    def _cancel(self):
        self.top.destroy()

    def _apply_annotations(self, img):
        draw = ImageDraw.Draw(img)
        for ann in self.annotations:
            w = max(1, int(ann.width / self._scale))
            x1, y1 = ann.coords[0], ann.coords[1]
            if ann.tool == "text":
                fs = max(8, int(ann.font_size / self._scale))
                try:
                    font = ImageFont.truetype("arial.ttf", fs)
                except Exception:
                    font = ImageFont.load_default()
                draw.text((x1, y1), ann.text, fill=ann.color, font=font)
            elif ann.tool == "pencil":
                pts = list(ann.coords)
                if len(pts) >= 2:
                    draw.line(pts, fill=ann.color, width=w, joint="curve")
            else:
                x2, y2 = ann.coords[2], ann.coords[3]
                if ann.tool == "rectangle":
                    draw.rectangle([x1, y1, x2, y2],
                                   outline=ann.color, width=w)
                elif ann.tool == "ellipse":
                    draw.ellipse([x1, y1, x2, y2],
                                 outline=ann.color, width=w)
                elif ann.tool == "line":
                    draw.line([x1, y1, x2, y2],
                              fill=ann.color, width=w)
                elif ann.tool == "arrow":
                    self._draw_arrow(draw, x1, y1, x2, y2, ann.color, w)

    @staticmethod
    def _draw_arrow(draw, x1, y1, x2, y2, color, width):
        draw.line([(x1, y1), (x2, y2)], fill=color, width=width)
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length < 1:
            return
        ux, uy = dx / length, dy / length
        perp_x, perp_y = -uy, ux
        head = max(12, width * 4)
        bx = x2 - head * ux
        by = y2 - head * uy
        spread = head * 0.4
        p1 = (bx + spread * perp_x, by + spread * perp_y)
        p2 = (bx - spread * perp_x, by - spread * perp_y)
        draw.polygon([(x2, y2), p1, p2], fill=color, outline=color)
