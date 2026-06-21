import os
import queue
import shutil
import tempfile
from datetime import datetime
from typing import Optional

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

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
    "Atalhos:  F9 Iniciar/Pausar   |   F10 Parar e exportar   |   F11 Adicionar comentário"
)


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
                                      command=self.prompt_comment)
        self.btn_comment.pack(side=tk.LEFT, padx=2)
        self.btn_export = ttk.Button(btns, text="Exportar HTML",
                                     command=self.export)
        self.btn_export.pack(side=tk.LEFT, padx=2)
        self.btn_clear = ttk.Button(btns, text="Limpar",
                                    command=self.clear)
        self.btn_clear.pack(side=tk.LEFT, padx=2)

        help_frame = ttk.Frame(self.root, padding=(10, 0, 10, 6))
        help_frame.pack(fill=tk.X)
        ttk.Label(help_frame, text=HOTKEYS_TEXT, foreground="gray").pack(anchor=tk.W)

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
            self._add_step_row(ev[1])
        elif kind == "comment_request":
            self.prompt_comment()
        elif kind == "stopped":
            self.export()
        elif kind == "cleared":
            self._clear_tree()

    def _set_status(self, state: str):
        self.status_label.config(
            text=STATUS_LABELS.get(state, state),
            fg=STATUS_COLORS.get(state, "#666666"),
        )

    def _add_step_row(self, step: Step):
        tlabel = TYPE_LABELS.get(step.step_type, step.step_type)
        desc = step.comment_text or step.keys_text or step.description
        if len(desc) > 80:
            desc = desc[:77] + "..."
        self.tree.insert("", tk.END, iid=str(step.index),
                         values=(step.index, step.timestamp.strftime("%H:%M:%S"),
                                 tlabel, desc))
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
        text = simpledialog.askstring(
            "Adicionar comentário", "Digite o comentário para esta etapa:",
            parent=self.root,
        )
        if text is not None:
            self.recorder.add_comment(text)

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

    def _on_close(self):
        self.recorder.stop_listeners()
        try:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass
        self.root.destroy()
