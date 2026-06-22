import os
import queue
import shutil
import tempfile
from datetime import datetime
from typing import Optional

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .exporter import export_html
from .models import Step
from .recorder import Recorder

TYPE_LABELS = {
    "left_click": "Clique esquerdo",
    "right_click": "Clique direito",
    "keyboard_input": "Teclado",
    "ctrl_command": "Ctrl",
    "comment": "Comentário",
}

STATUS_LABELS = {"idle": "Ocioso", "recording": "Gravando", "paused": "Pausado"}
STATUS_COLORS = {"idle": "#666666", "recording": "#1e8e3e", "paused": "#e37400"}

HOTKEYS_TEXT = (
    "Atalhos:  F9 Iniciar/Pausar   |   F10 Parar e exportar   |   "
    "F11 Adicionar comentário   |   Del Remover etapa selecionada"
)
DRAG_HINT = "Dica: arraste uma etapa para outra posição para reordená-la"


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Gravador de Passos")
        root.geometry("820x540")
        root.minsize(640, 420)

        self.temp_dir = tempfile.mkdtemp(prefix="gravador_passos_")
        self.event_queue: "queue.Queue" = queue.Queue()
        self.recorder = Recorder(self.event_queue, self.temp_dir)
        self.recorder.start_listeners()
        self.current_state = "idle"
        self._drag_source = None
        self._drag_start_y = 0
        self._dragging = False

        self._build_ui()
        self._update_gui_rect()
        self._poll_queue()
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill=tk.X)

        ttk.Label(top, text="Status:").pack(side=tk.LEFT)
        self.status_label = tk.Label(top, text="Ocioso", fg="#666666",
                                     font=("Segoe UI", 10, "bold"))
        self.status_label.pack(side=tk.LEFT, padx=(4, 18))

        self.count_var = tk.StringVar(value="0 etapas")
        ttk.Label(top, textvariable=self.count_var).pack(side=tk.LEFT)

        btns = ttk.Frame(top)
        btns.pack(side=tk.RIGHT)
        self.btn_start = ttk.Button(btns, text="Iniciar/Pausar (F9)",
                                    command=self.toggle_record)
        self.btn_start.pack(side=tk.LEFT, padx=2)
        self.btn_stop = ttk.Button(btns, text="Parar (F10)",
                                   command=self.stop_record)
        self.btn_stop.pack(side=tk.LEFT, padx=2)
        self.btn_comment = ttk.Button(btns, text="Comentar (F11)",
                                      command=self.prompt_comment,
                                      state=tk.DISABLED)
        self.btn_comment.pack(side=tk.LEFT, padx=2)
        self.btn_export = ttk.Button(btns, text="Exportar HTML",
                                     command=self.export)
        self.btn_export.pack(side=tk.LEFT, padx=2)
        self.btn_remove = ttk.Button(btns, text="Remover (Del)",
                                     command=self._remove_selected)
        self.btn_remove.pack(side=tk.LEFT, padx=2)
        self.btn_clear = ttk.Button(btns, text="Limpar",
                                    command=self.clear)
        self.btn_clear.pack(side=tk.LEFT, padx=2)

        help_frame = ttk.Frame(self.root, padding=(10, 0, 10, 6))
        help_frame.pack(fill=tk.X)
        ttk.Label(help_frame, text=HOTKEYS_TEXT, foreground="gray").pack(anchor=tk.W)
        ttk.Label(help_frame, text=DRAG_HINT, foreground="#7c3aed").pack(anchor=tk.W)

        tree_frame = ttk.Frame(self.root, padding=10)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        cols = ("num", "time", "type", "desc")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings")
        self.tree.heading("num", text="#")
        self.tree.heading("time", text="Horário")
        self.tree.heading("type", text="Tipo")
        self.tree.heading("desc", text="Descrição")
        self.tree.column("num", width=46, anchor=tk.CENTER, stretch=False)
        self.tree.column("time", width=90, anchor=tk.CENTER, stretch=False)
        self.tree.column("type", width=130, anchor=tk.W, stretch=False)
        self.tree.column("desc", width=480, anchor=tk.W)
        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<ButtonPress-1>", self._on_tree_press)
        self.tree.bind("<B1-Motion>", self._on_tree_motion)
        self.tree.bind("<ButtonRelease-1>", self._on_tree_release)
        self.tree.bind("<Delete>", lambda e: self._remove_selected())
        self.tree.bind("<Control-Delete>", lambda e: self._remove_selected())

    def _update_gui_rect(self):
        try:
            self.root.update_idletasks()
            x = self.root.winfo_rootx()
            y = self.root.winfo_rooty()
            w = self.root.winfo_width()
            h = self.root.winfo_height()
            self.recorder.gui_rect = (x, y, w, h)
        except Exception:
            pass
        self.root.after(250, self._update_gui_rect)

    def _poll_queue(self):
        try:
            while True:
                self._handle_event(self.event_queue.get_nowait())
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _handle_event(self, ev):
        kind = ev[0]
        if kind == "status":
            self._set_status(ev[1])
        elif kind == "step":
            self._refresh_tree()
        elif kind == "comment_request":
            self.prompt_comment()
        elif kind == "stopped":
            self.export()
        elif kind == "cleared":
            self._clear_tree()
        elif kind in ("reordered", "removed"):
            self._refresh_tree()

    def _set_status(self, state: str):
        self.current_state = state
        self.status_label.config(
            text=STATUS_LABELS.get(state, state),
            fg=STATUS_COLORS.get(state, "#666666"),
        )
        if state in ("recording", "paused"):
            self.btn_comment.config(state=tk.NORMAL)
        else:
            self.btn_comment.config(state=tk.DISABLED)

    def _add_step_row(self, step: Step):
        tlabel = TYPE_LABELS.get(step.step_type, step.step_type)
        desc = step.comment_text or step.keys_text or step.description
        if len(desc) > 80:
            desc = desc[:77] + "..."
        self.tree.insert("", tk.END, iid=str(step.index),
                         values=(step.index, step.timestamp.strftime("%H:%M:%S"),
                                 tlabel, desc))

    def _refresh_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for step in self.recorder.get_steps():
            self._add_step_row(step)
        if self.tree.get_children():
            self.tree.yview_moveto(1.0)
        self.count_var.set(f"{len(self.tree.get_children())} etapas")

    def _clear_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.count_var.set("0 etapas")

    def toggle_record(self):
        self.recorder.toggle()

    def stop_record(self):
        self.recorder.stop()

    def prompt_comment(self):
        if self.current_state not in ("recording", "paused"):
            return
        steps = self.recorder.get_steps()
        if not steps:
            messagebox.showinfo("Gravador de Passos",
                                "Nenhuma etapa registrada para comentar.")
            return
        with self.recorder.blocked_input():
            result = self._show_comment_dialog(steps)
        if result is None:
            return
        text, after_index = result
        self.recorder.add_comment(text, after_index=after_index)

    def _show_comment_dialog(self, steps):
        dialog = tk.Toplevel(self.root)
        dialog.title("Adicionar comentário")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("560x360")
        dialog.minsize(480, 320)

        ttk.Label(dialog,
                  text="Inserir comentário:",
                  padding=(12, 10, 12, 4)).pack(anchor=tk.W)

        step_options = ["— Antes de todos os passos (pré-comentário) —"]
        for s in steps:
            tlabel = TYPE_LABELS.get(s.step_type, s.step_type)
            desc = s.comment_text or s.keys_text or s.description
            if len(desc) > 60:
                desc = desc[:57] + "..."
            step_options.append(f"Após o passo {s.index} — {tlabel}: {desc}")

        step_var = tk.StringVar(value=step_options[-1])
        combo = ttk.Combobox(dialog, textvariable=step_var,
                             values=step_options, state="readonly",
                             width=70)
        combo.pack(padx=12, pady=4, fill=tk.X)
        combo.focus_set()

        ttk.Label(dialog, text="Comentário:",
                  padding=(12, 8, 12, 4)).pack(anchor=tk.W)

        text_frame = ttk.Frame(dialog, padding=(12, 0, 12, 4))
        text_frame.pack(fill=tk.BOTH, expand=True)
        text_widget = tk.Text(text_frame, height=6, width=60, wrap=tk.WORD,
                              undo=True)
        vsb = ttk.Scrollbar(text_frame, orient=tk.VERTICAL,
                            command=text_widget.yview)
        text_widget.configure(yscrollcommand=vsb.set)
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        result = {"value": None}

        def on_ok():
            comment_text = text_widget.get("1.0", tk.END).strip()
            if not comment_text:
                return
            sel = step_var.get()
            if sel.startswith("— Antes de todos"):
                after_index = 0
            else:
                try:
                    num_str = sel.split("—")[0].strip().split()[-1]
                    after_index = int(num_str)
                except (ValueError, IndexError):
                    after_index = None
            result["value"] = (comment_text, after_index)
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        btns = ttk.Frame(dialog, padding=(12, 4, 12, 10))
        btns.pack(fill=tk.X)
        ttk.Button(btns, text="Cancelar", command=on_cancel).pack(side=tk.RIGHT)
        ttk.Button(btns, text="OK", command=on_ok).pack(
            side=tk.RIGHT, padx=(0, 6))

        dialog.bind("<Escape>", lambda e: on_cancel())
        dialog.bind("<Control-Return>", lambda e: on_ok())
        dialog.protocol("WM_DELETE_WINDOW", on_cancel)
        self.root.wait_window(dialog)
        return result["value"]

    def _ask_export_mode(self) -> Optional[tuple]:
        dialog = tk.Toplevel(self.root)
        dialog.title("Modo de exportação")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.grab_set()

        ttk.Label(dialog, text="Escolha o modo de exportação do HTML:",
                  padding=(12, 12, 12, 4)).pack(anchor=tk.W)

        var = tk.IntVar(value=1)
        ttk.Radiobutton(
            dialog, variable=var, value=0,
            text="HTML único com imagens embutidas (portátil, qualidade reduzida)"
        ).pack(anchor=tk.W, padx=20, pady=2)
        ttk.Radiobutton(
            dialog, variable=var, value=1,
            text="HTML + pasta de imagens (qualidade total, zoom nítido)"
        ).pack(anchor=tk.W, padx=20, pady=2)

        zip_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            dialog, variable=zip_var,
            text="Também gerar arquivo ZIP (HTML + imagens em um só arquivo para compartilhar)"
        ).pack(anchor=tk.W, padx=20, pady=(10, 2))

        result = {"value": None}

        def on_ok():
            result["value"] = (bool(var.get()), bool(zip_var.get()))
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        btns = ttk.Frame(dialog, padding=10)
        btns.pack(fill=tk.X)
        ttk.Button(btns, text="Cancelar", command=on_cancel).pack(side=tk.RIGHT)
        ttk.Button(btns, text="OK", command=on_ok).pack(side=tk.RIGHT)

        dialog.protocol("WM_DELETE_WINDOW", on_cancel)
        self.root.wait_window(dialog)
        return result["value"]

    def export(self):
        steps = self.recorder.get_steps()
        if not steps:
            messagebox.showinfo("Gravador de Passos",
                                "Nenhuma etapa registrada para exportar.")
            return

        mode = self._ask_export_mode()
        if mode is None:
            return
        folder_mode, also_zip = mode

        started_at, ended_at = self.recorder.get_session()
        default_name = f"gravacao_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        path = filedialog.asksaveasfilename(
            title="Salvar relatório HTML",
            defaultextension=".html",
            initialfile=default_name,
            filetypes=[("Arquivo HTML", "*.html"), ("Todos os arquivos", "*.*")],
        )
        if not path:
            return
        try:
            result = export_html(
                path, "Gravação de Passos", started_at, ended_at, steps,
                embed_images=not folder_mode, create_zip=also_zip,
            )
        except Exception as exc:
            messagebox.showerror("Erro ao exportar", str(exc))
            return

        lines = [f"Relatório salvo em:\n{result['html_path']}"]
        if result["images_dir"]:
            lines.append(f"\nImagens em:\n{result['images_dir']}")
        if result["zip_path"]:
            lines.append(f"\nPacote ZIP em:\n{result['zip_path']}")
        lines.append("\n\nAbrir o HTML no navegador?")
        if messagebox.askyesno("Exportação concluída", "".join(lines)):
            try:
                os.startfile(result["html_path"])
            except Exception:
                pass

    def clear(self):
        self.recorder.clear()

    def _on_tree_press(self, event):
        self._drag_source = self.tree.identify_row(event.y)
        self._drag_start_y = event.y
        self._dragging = False

    def _on_tree_motion(self, event):
        if not self._drag_source:
            return
        if not self._dragging:
            if abs(event.y - self._drag_start_y) > 6:
                self._dragging = True
                self.tree.config(cursor="hand2")
        if self._dragging:
            target = self.tree.identify_row(event.y)
            if target and target != self._drag_source:
                self.tree.selection_set(target)
                self.tree.yview_moveto(
                    self.tree.yview()[0]
                    + (event.y - self._drag_start_y) / max(self.tree.winfo_height(), 1) * 0.05
                )

    def _on_tree_release(self, event):
        source = self._drag_source
        was_dragging = self._dragging
        self._drag_source = None
        self._dragging = False
        self.tree.config(cursor="")
        if not was_dragging or not source:
            return
        target = self.tree.identify_row(event.y)
        if not target or target == source:
            return
        self._reorder_step(source, target)

    def _reorder_step(self, source_iid, target_iid):
        items = list(self.tree.get_children())
        if source_iid not in items or target_iid not in items:
            return
        new_order = [int(iid) for iid in items]
        source_pos = items.index(source_iid)
        target_pos = items.index(target_iid)
        new_order.pop(source_pos)
        new_order.insert(target_pos, int(source_iid))
        self.recorder.reorder_steps(new_order)

    def _remove_selected(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Gravador de Passos",
                                "Selecione uma etapa na lista para remover.")
            return
        iid = selected[0]
        try:
            index = int(iid)
        except ValueError:
            return
        if not messagebox.askyesno(
            "Remover etapa",
            f"Remover a etapa {index}? As etapas seguintes serão renumeradas."
        ):
            return
        self.recorder.remove_step(index)

    def _on_close(self):
        self.recorder.stop_listeners()
        try:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass
        self.root.destroy()
