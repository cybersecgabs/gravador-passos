import base64
import html
import os
import shutil
import zipfile
from datetime import datetime
from io import BytesIO
from typing import List, Optional, Tuple

from PIL import Image

from .models import Step

TYPE_LABELS = {
    "left_click": "Clique esquerdo",
    "right_click": "Clique direito",
    "keyboard_input": "Entrada de teclado",
    "ctrl_command": "Atalho de teclado",
    "comment": "Comentário",
}

PRIMARY = "#7c3aed"
PRIMARY_LIGHT = "#f3eefe"

_STYLE = """
* { box-sizing: border-box; }
body {
  font-family: "Segoe UI", Tahoma, Arial, sans-serif;
  background: #f5f6f8;
  color: #222;
  margin: 0;
  padding: 24px 12px;
}
.container { max-width: 1000px; margin: 0 auto; }
h1 { color: #7c3aed; margin: 0 0 6px 0; font-size: 26px; }
.meta { color: #666; font-size: 13px; margin-bottom: 24px; }
.steps { display: flex; flex-direction: column; gap: 18px; }
.step {
  display: flex;
  gap: 14px;
  background: #fff;
  border: 1px solid #e6e8eb;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}
.badge {
  flex: 0 0 36px;
  width: 36px; height: 36px;
  border-radius: 50%;
  background: #7c3aed;
  color: #fff;
  font-weight: 700;
  font-size: 16px;
  display: flex; align-items: center; justify-content: center;
}
.content { flex: 1; min-width: 0; }
.head {
  display: flex; justify-content: space-between; align-items: baseline;
  border-bottom: 1px solid #f0f0f0; padding-bottom: 6px; margin-bottom: 10px;
}
.type { font-weight: 600; color: #7c3aed; }
.time { color: #888; font-size: 12px; }
.desc { margin: 4px 0 8px 0; }
.pos { color: #888; font-size: 12px; margin-left: 6px; }
.shot {
  max-width: 100%;
  border: 1px solid #e6e8eb;
  border-radius: 4px;
  margin-top: 6px;
  display: block;
  cursor: zoom-in;
}
.shot-link { display: inline-block; }
.keys {
  background: #f3f4f6;
  border: 1px solid #e6e8eb;
  border-radius: 4px;
  padding: 10px 12px;
  font-family: Consolas, "Courier New", monospace;
  font-size: 14px;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 6px 0 0 0;
}
.comment {
  border-left: 4px solid #7c3aed;
  background: #f3eefe;
  margin: 4px 0 0 0;
  padding: 10px 14px;
  color: #333;
  font-style: italic;
  border-radius: 0 4px 4px 0;
}
kbd {
  background: #eee;
  border: 1px solid #ccc;
  border-bottom-width: 2px;
  border-radius: 4px;
  padding: 2px 8px;
  font-family: Consolas, monospace;
  font-size: 14px;
}
footer { text-align: center; color: #aaa; font-size: 12px; margin-top: 28px; }
"""


def _esc(s: Optional[str]) -> str:
    return html.escape(str(s)) if s is not None else ""


def _fmt_time(dt: Optional[datetime]) -> str:
    return dt.strftime("%H:%M:%S") if dt else "--:--:--"


def _img_to_base64(path: str, max_width: int = 1280, quality: int = 85) -> Optional[str]:
    try:
        with Image.open(path) as im:
            im = im.convert("RGB")
            if im.width > max_width:
                ratio = max_width / im.width
                im = im.resize((max_width, int(im.height * ratio)), Image.LANCZOS)
            buf = BytesIO()
            im.save(buf, format="JPEG", quality=quality)
            return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return None


def _copy_image(src: str, images_dir: str, index: int) -> Optional[str]:
    try:
        fname = f"step_{index:02d}.png"
        dst = os.path.join(images_dir, fname)
        shutil.copy2(src, dst)
        return fname
    except Exception:
        return None


def _render_step(step: Step, embed_images: bool,
                 images_dir: Optional[str], rel_dir: Optional[str]) -> str:
    tlabel = TYPE_LABELS.get(step.step_type, step.step_type)
    out = [
        "<div class='step'>",
        f"<div class='badge'>{step.index}</div>",
        "<div class='content'>",
        "<div class='head'>",
        f"<span class='type'>{_esc(tlabel)}</span>",
        f"<span class='time'>{_fmt_time(step.timestamp)}</span>",
        "</div>",
    ]

    if step.step_type == "comment":
        out.append(f"<blockquote class='comment'>{_esc(step.comment_text)}</blockquote>")
    elif step.step_type == "keyboard_input":
        out.append(f"<div class='desc'>{_esc(step.description)}</div>")
        out.append(f"<pre class='keys'>{_esc(step.keys_text)}</pre>")
    elif step.step_type == "ctrl_command":
        out.append(f"<div class='desc'><kbd>{_esc(step.keys_text)}</kbd></div>")
    else:
        pos_txt = ""
        if step.click_position:
            pos_txt = f"({step.click_position[0]}, {step.click_position[1]})"
        out.append(
            f"<div class='desc'>{_esc(step.description)} "
            f"<span class='pos'>{_esc(pos_txt)}</span></div>"
        )
        if step.screenshot_path:
            if embed_images:
                b64 = _img_to_base64(step.screenshot_path)
                if b64:
                    out.append(
                        f"<a class='shot-link' href='data:image/jpeg;base64,{b64}' "
                        f"target='_blank'>"
                        f"<img class='shot' src='data:image/jpeg;base64,{b64}' "
                        f"alt='screenshot'></a>"
                    )
            else:
                fname = _copy_image(step.screenshot_path, images_dir, step.index)
                if fname and rel_dir:
                    src = f"{rel_dir}/{fname}"
                    out.append(
                        f"<a class='shot-link' href='{src}' target='_blank'>"
                        f"<img class='shot' src='{src}' alt='screenshot'></a>"
                    )

    out.append("</div></div>")
    return "".join(out)


def _create_zip(zip_path: str, html_path: str, images_dir: Optional[str]) -> str:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(html_path, arcname=os.path.basename(html_path))
        if images_dir and os.path.isdir(images_dir):
            folder_name = os.path.basename(images_dir)
            for fname in sorted(os.listdir(images_dir)):
                fpath = os.path.join(images_dir, fname)
                if os.path.isfile(fpath):
                    zf.write(fpath, arcname=f"{folder_name}/{fname}")
    return zip_path


def export_html(path: str, title: str, started_at: Optional[datetime],
                ended_at: Optional[datetime], steps: List[Step],
                embed_images: bool = True,
                create_zip: bool = False) -> dict:
    images_dir: Optional[str] = None
    rel_dir: Optional[str] = None
    if not embed_images:
        base = os.path.splitext(path)[0]
        images_dir = base + "_files"
        os.makedirs(images_dir, exist_ok=True)
        rel_dir = os.path.basename(images_dir)

    parts = [
        "<!DOCTYPE html><html lang='pt-BR'><head><meta charset='utf-8'>",
        f"<title>{_esc(title)}</title>",
        f"<style>{_STYLE}</style>",
        "</head><body><div class='container'>",
        f"<h1>{_esc(title)}</h1>",
        (f"<div class='meta'>Gravação iniciada em {_fmt_time(started_at)} e "
         f"finalizada em {_fmt_time(ended_at)} &bull; {len(steps)} etapa(s)</div>"),
        "<div class='steps'>",
    ]
    if steps:
        for step in steps:
            parts.append(_render_step(step, embed_images, images_dir, rel_dir))
    else:
        parts.append("<div class='step'><div class='content'>Nenhuma etapa registrada.</div></div>")
    parts.append("</div>")
    parts.append("<footer>Gerado por Gravador de Passos</footer>")
    parts.append("</div></body></html>")

    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(parts))

    result = {"html_path": path, "images_dir": images_dir, "zip_path": None}

    if create_zip:
        zip_path = os.path.splitext(path)[0] + ".zip"
        _create_zip(zip_path, path, images_dir)
        result["zip_path"] = zip_path

    return result
