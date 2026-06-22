import os
import queue
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from typing import List, Optional, Tuple

from PIL import Image
from pynput import mouse
from pynput.keyboard import Key, KeyCode

from . import screenshot
from .models import Step

CTRL_FRIENDLY = {
    "a": "Selecionar tudo",
    "c": "Copiar",
    "v": "Colar",
    "x": "Recortar",
    "z": "Desfazer",
    "y": "Refazer",
    "s": "Salvar",
    "o": "Abrir",
    "n": "Novo",
    "p": "Imprimir",
    "f": "Localizar",
    "w": "Fechar",
    "r": "Atualizar",
    "t": "Nova guia",
    "l": "Endereço",
    "d": "Excluir/Bookmark",
    "g": "Localizar próximo",
    "h": "Substituir",
    "k": "Atalho",
    "u": "Sublinhado",
    "b": "Negrito",
    "i": "Itálico",
}

_MODIFIERS = {
    Key.ctrl, Key.ctrl_l, Key.ctrl_r,
    Key.alt, Key.alt_l, Key.alt_r, Key.alt_gr,
    Key.cmd, Key.cmd_l, Key.cmd_r,
    Key.shift, Key.shift_l, Key.shift_r,
}

_CTRL_KEYS = {Key.ctrl, Key.ctrl_l, Key.ctrl_r}
_SHIFT_KEYS = {Key.shift, Key.shift_l, Key.shift_r}

_SPECIAL_KEY_NAMES = {
    "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f12",
    "f13", "f14", "f15", "f16", "f17", "f18", "f19",
    "up", "down", "left", "right",
    "esc", "home", "end", "page_up", "page_down",
    "insert", "delete", "caps_lock",
    "print_screen", "menu",
    "num_lock", "scroll_lock",
}

_SPECIAL_KEY_DISPLAY = {
    "up": "Seta para Cima", "down": "Seta para Baixo",
    "left": "Seta para Esquerda", "right": "Seta para Direita",
    "esc": "Esc", "home": "Home", "end": "End",
    "page_up": "Page Up", "page_down": "Page Down",
    "insert": "Insert", "delete": "Delete",
    "caps_lock": "Caps Lock",
    "print_screen": "Print Screen",
    "menu": "Menu",
    "backspace": "Backspace",
    "tab": "Tab", "enter": "Enter",
    "space": "Espaço",
    "num_lock": "Num Lock", "scroll_lock": "Scroll Lock",
}


class Recorder:
    def __init__(self, event_queue: "queue.Queue", temp_dir: str):
        self.queue = event_queue
        self.temp_dir = temp_dir
        self.state = "idle"
        self.steps: List[Step] = []
        self.keyboard_buffer: List[str] = []
        self.ctrl_held = False
        self.shift_held = False
        self.gui_rect: Optional[Tuple[int, int, int, int]] = None
        self.started_at: Optional[datetime] = None
        self.ended_at: Optional[datetime] = None
        self._input_blocked = False

        self._lock = threading.Lock()
        self._mouse_listener: Optional[mouse.Listener] = None
        self._kb_listener = None

    def start_listeners(self):
        self._mouse_listener = mouse.Listener(on_click=self._on_click)
        self._mouse_listener.daemon = True
        self._mouse_listener.start()

        from pynput import keyboard
        self._kb_listener = keyboard.Listener(
            on_press=self._on_press, on_release=self._on_release
        )
        self._kb_listener.daemon = True
        self._kb_listener.start()

    def stop_listeners(self):
        if self._mouse_listener:
            self._mouse_listener.stop()
        if self._kb_listener:
            self._kb_listener.stop()

    def toggle(self):
        with self._lock:
            if self.state == "idle":
                self.state = "recording"
                self.steps = []
                self.keyboard_buffer = []
                self.started_at = datetime.now()
                self.ended_at = None
            elif self.state == "recording":
                self.state = "paused"
                self._flush_keyboard_locked()
            else:
                self.state = "recording"
        self.queue.put(("status", self.state))

    def stop(self):
        with self._lock:
            if self.state == "idle":
                return
            self.state = "idle"
            self._flush_keyboard_locked()
            self.ended_at = datetime.now()
        self.queue.put(("status", "idle"))
        self.queue.put(("stopped",))

    def add_comment(self, text: str, after_index: Optional[int] = None):
        if not text:
            return
        with self._lock:
            self._input_blocked = False
            if self.state not in ("recording", "paused"):
                return

            if after_index is None:
                insert_pos = len(self.steps)
            elif after_index == 0:
                insert_pos = 0
            else:
                insert_pos = len(self.steps)
                for i, s in enumerate(self.steps):
                    if s.index == after_index:
                        insert_pos = i + 1
                        break

            new_step = Step(
                index=insert_pos + 1,
                timestamp=datetime.now(),
                step_type="comment",
                description="Comentário do usuário",
                comment_text=text,
            )
            self.steps.insert(insert_pos, new_step)
            self._renumber_and_remark_locked()

        self.queue.put(("step", new_step))

    @contextmanager
    def blocked_input(self):
        with self._lock:
            self._input_blocked = True
        try:
            yield
        finally:
            with self._lock:
                self._input_blocked = False

    def clear(self):
        with self._lock:
            self.steps = []
            self.keyboard_buffer = []
            self.started_at = None
            self.ended_at = None
        self.queue.put(("cleared",))

    def reorder_steps(self, new_order: List[int]):
        with self._lock:
            index_to_step = {s.index: s for s in self.steps}
            new_steps = [index_to_step[i] for i in new_order if i in index_to_step]
            for s in self.steps:
                if s.index not in new_order:
                    new_steps.append(s)
            self.steps = new_steps
            self._renumber_and_remark_locked()
        self.queue.put(("reordered",))

    def remove_step(self, index: int):
        with self._lock:
            self.steps = [s for s in self.steps if s.index != index]
            self._renumber_and_remark_locked()
        self.queue.put(("removed",))

    def _renumber_and_remark_locked(self):
        for i, step in enumerate(self.steps):
            new_index = i + 1
            if step.index != new_index:
                step.index = new_index
                if step.screenshot_path and step.click_position:
                    try:
                        img = Image.open(step.screenshot_path)
                        origin = screenshot.get_virtual_screen_rect()[:2]
                        marked = screenshot.mark_click(
                            img, step.click_position, origin, new_index
                        )
                        marked.save(step.screenshot_path)
                    except Exception:
                        pass

    def get_steps(self) -> List[Step]:
        with self._lock:
            return list(self.steps)

    def get_session(self):
        with self._lock:
            return self.started_at, self.ended_at

    def _in_gui(self, x: int, y: int) -> bool:
        r = self.gui_rect
        if not r:
            return False
        rx, ry, rw, rh = r
        return rx <= x < rx + rw and ry <= y < ry + rh

    def _on_click(self, x, y, button, pressed):
        if not pressed:
            return
        if button not in (mouse.Button.left, mouse.Button.right):
            return

        with self._lock:
            if self._input_blocked:
                return
            if self.state != "recording":
                return
            if self._in_gui(x, y):
                return
            self._flush_keyboard_locked()

            if button == mouse.Button.left:
                stype = "left_click"
                desc = "Clique esquerdo"
            else:
                stype = "right_click"
                desc = "Clique direito"

            index = len(self.steps) + 1
            path = None
            try:
                img, origin = screenshot.capture()
                marked = screenshot.mark_click(img, (x, y), origin, index)
                path = os.path.join(
                    self.temp_dir, f"step_{index}_{int(time.time() * 1000)}.png"
                )
                marked.save(path)
            except Exception:
                path = None

            step = Step(
                index=index,
                timestamp=datetime.now(),
                step_type=stype,
                description=desc,
                click_position=(int(x), int(y)),
                screenshot_path=path,
            )
            self.steps.append(step)
            self.queue.put(("step", step))

    def _on_press(self, key):
        if key == Key.f9:
            self.toggle()
            return
        if key == Key.f10:
            self.stop()
            return
        if key == Key.f11:
            with self._lock:
                if self.state in ("recording", "paused"):
                    self._input_blocked = True
                    self.queue.put(("comment_request",))
            return

        with self._lock:
            if self._input_blocked:
                return
            if self.state != "recording":
                return

            if key in _CTRL_KEYS:
                self.ctrl_held = True
                return
            if key in _SHIFT_KEYS:
                self.shift_held = True
                return
            if key in _MODIFIERS:
                return

            if self.ctrl_held:
                label = self._ctrl_label(key)
                self._flush_keyboard_locked()
                self._add_step_locked(
                    "ctrl_command", label, keys_text=label
                )
                return

            if key in (Key.tab, Key.enter):
                self._flush_keyboard_locked()
                return

            if key == Key.backspace:
                if self.keyboard_buffer:
                    self.keyboard_buffer.pop()
                return

            if key == Key.space:
                self.keyboard_buffer.append(" ")
                return

            if isinstance(key, Key) and key.name in _SPECIAL_KEY_NAMES:
                label = self._key_name(key)
                self._flush_keyboard_locked()
                self._add_step_locked(
                    "keyboard_input", "Entrada de teclado",
                    keys_text=f"[{label}]",
                )
                return

            if isinstance(key, KeyCode) and key.char:
                self.keyboard_buffer.append(key.char)
                return

    def _on_release(self, key):
        if key in _CTRL_KEYS:
            self.ctrl_held = False
        elif key in _SHIFT_KEYS:
            self.shift_held = False

    def _flush_keyboard_locked(self):
        if self.keyboard_buffer:
            text = "".join(self.keyboard_buffer)
            self.keyboard_buffer = []
            self._add_step_locked(
                "keyboard_input",
                "Entrada de teclado",
                keys_text=text,
            )

    def _add_step_locked(self, step_type, description, keys_text="",
                         click_position=None, screenshot_path=None,
                         comment_text=""):
        step = Step(
            index=len(self.steps) + 1,
            timestamp=datetime.now(),
            step_type=step_type,
            description=description,
            keys_text=keys_text,
            click_position=click_position,
            screenshot_path=screenshot_path,
            comment_text=comment_text,
        )
        self.steps.append(step)
        self.queue.put(("step", step))

    @staticmethod
    def _key_name(key) -> str:
        if isinstance(key, KeyCode):
            if key.char and key.char.isprintable() and not key.char.isspace():
                return key.char.upper()
            if key.vk is not None:
                try:
                    ch = chr(key.vk)
                    if ch.isalpha():
                        return ch.upper()
                except (ValueError, OverflowError):
                    pass
        if isinstance(key, Key):
            name = key.name
            if name.startswith("f") and len(name) > 1 and name[1:].isdigit():
                return name.upper()
            if name in _SPECIAL_KEY_DISPLAY:
                return _SPECIAL_KEY_DISPLAY[name]
            return name.replace("_", " ").title()
        return "?"

    def _ctrl_label(self, key) -> str:
        letter = self._key_name(key)
        base = f"Ctrl+{letter}"
        friendly = CTRL_FRIENDLY.get(letter.lower())
        if friendly:
            return f"{base} ({friendly})"
        return base
