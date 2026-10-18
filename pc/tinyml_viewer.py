"""
tinyml_viewer.py - Chay mo phong TinyML va xem ket qua (khong can board)

* Nut "Chay mo phong": goi Vivado o che do batch (khong mo giao dien),
  chay tb_tinyml_top, roi trang TU HIEN tung anh ngay khi testbench ghi ra.
* Trang luon theo doi file ket_qua_sim.txt: chay mo phong trong Vivado GUI
  cung tu cap nhat len day.

Chay:  python tinyml_viewer.py                (tu tim file mac dinh)
       python tinyml_viewer.py duong_dan.txt  (chi dinh file)
Chi dung thu vien co san cua Python (tkinter), khong can cai them.
"""
import glob
import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog

# Duong dan Vivado tren may nay (doi o day neu cai cho khac)
VIVADO = r"D:\VHDL\AMD_VIVADO\2025.2\Vivado\bin\vivado.bat"
PROJECT = r"D:\PROJECT\TinyAccel_vivado\TINY_MNIST\TINY_MNIST.xpr"
DEFAULT_FILE = (r"D:\PROJECT\TinyAccel_vivado\TINY_MNIST\TINY_MNIST.sim"
                r"\sim_1\behav\xsim\ket_qua_sim.txt")
RUN_TCL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_sim.tcl")


def find_vivado():
    """Tim vivado: trong PATH, roi C:/Xilinx/... va C:/AMDDesignTools/... (ban moi nhat)."""
    if os.path.exists(VIVADO):
        return VIVADO
    for name in ("vivado.bat", "vivado"):
        p = shutil.which(name)
        if p:
            return p
    cands = (glob.glob(r"C:\Xilinx\Vivado\*\bin\vivado.bat")
             + glob.glob(r"C:\Xilinx\*\Vivado\bin\vivado.bat")
             + glob.glob(r"C:\AMDDesignTools\*\Vivado\bin\vivado.bat")
             + glob.glob(r"D:\VHDL\AMD_VIVADO\*\Vivado\bin\vivado.bat"))
    return sorted(cands)[-1] if cands else None

PIX = 9            # kich thuoc 1 pixel tren man hinh
GREEN, RED, GREY = "#2e9d4f", "#d23c3c", "#3a3a3a"

# Doan sang cua LED 7 doan cho tung chu so (a b c d e f g)
SEGMENTS = {
    0: "abcdef", 1: "bc", 2: "abdeg", 3: "abcdg", 4: "bcfg",
    5: "acdfg", 6: "acdefg", 7: "abc", 8: "abcdefg", 9: "abcdfg",
}


def read_results(path):
    """Tra ve (list anh, so loi). Moi anh: dict n, fpga, python, label, ok, pixels."""
    images, errors = [], None
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = [l.rstrip("\n") for l in f]
    i = 0
    while i < len(lines):
        parts = lines[i].split()
        if parts and parts[0] == "IMG" and i + 1 < len(lines):
            hexs = lines[i + 1].strip()
            pixels = [int(hexs[k:k + 2], 16) for k in range(0, min(len(hexs), 1568), 2)]
            images.append({
                "n": int(parts[1]),
                "fpga": parts[2] if len(parts) > 2 else "?",
                "python": int(parts[3]) if len(parts) > 3 else -1,
                "label": int(parts[4]) if len(parts) > 4 else -1,
                "ok": len(parts) > 5 and parts[5] == "1",
                "pixels": pixels,
            })
            i += 2
        else:
            if parts and parts[0] == "END" and len(parts) > 1:
                errors = int(parts[1])
            i += 1
    return images, errors


def draw_seg7(cv, x, y, digit, color, w=46, h=80, t=8):
    """Ve LED 7 doan tai (x, y). digit = None -> hien dau '-'."""
    on = set(SEGMENTS.get(digit, "")) if digit is not None else {"g"}
    rects = {
        "a": (x + t, y, x + w - t, y + t),
        "b": (x + w - t, y + t, x + w, y + h / 2 - t / 2),
        "c": (x + w - t, y + h / 2 + t / 2, x + w, y + h - t),
        "d": (x + t, y + h - t, x + w - t, y + h),
        "e": (x, y + h / 2 + t / 2, x + t, y + h - t),
        "f": (x, y + t, x + t, y + h / 2 - t / 2),
        "g": (x + t, y + h / 2 - t / 2, x + w - t, y + h / 2 + t / 2),
    }
    for s, r in rects.items():
        cv.create_rectangle(*r, fill=color if s in on else "#e6e6e6", outline="")


class Viewer(tk.Tk):
    def __init__(self, path):
        super().__init__()
        self.title("TinyML FPGA - ket qua mo phong")
        self.configure(bg="white")
        self.path = path
        self.images, self.idx = [], 0

        top = tk.Frame(self, bg="white")
        top.pack(fill="x", padx=10, pady=6)
        self.run_btn = tk.Button(top, text="Chay mo phong", command=self.run_sim,
                                 bg="#3b6fd8", fg="white")
        self.run_btn.pack(side="left", padx=(0, 12))
        tk.Button(top, text="Mo file...", command=self.choose).pack(side="left")
        tk.Button(top, text="Tai lai", command=self.load).pack(side="left", padx=4)
        tk.Button(top, text="< Truoc", command=lambda: self.step(-1)).pack(side="left", padx=(20, 2))
        tk.Button(top, text="Sau >", command=lambda: self.step(1)).pack(side="left")
        self.info = tk.Label(top, text="", bg="white", anchor="w")
        self.info.pack(side="left", padx=12)

        self.cv = tk.Canvas(self, width=28 * PIX + 330, height=28 * PIX + 20,
                            bg="white", highlightthickness=0)
        self.cv.pack(padx=10)

        tk.Label(self, text="Tat ca anh:", bg="white", anchor="w").pack(fill="x", padx=10)
        self.strip = tk.Canvas(self, height=70, bg="white", highlightthickness=0)
        self.strip.pack(fill="x", padx=10, pady=(0, 10))
        self.strip.bind("<Button-1>", self.click_strip)

        self.bind("<Left>", lambda e: self.step(-1))
        self.bind("<Right>", lambda e: self.step(1))

        self.status = tk.Label(self, text="", bg="white", fg=GREY, anchor="w")
        self.status.pack(fill="x", padx=10, pady=(0, 6))
        self.proc, self.last_mtime = None, None
        self.load()
        self.watch()

    # ---------- Theo doi file: co anh moi la tu ve len ----------
    def watch(self):
        try:
            m = os.path.getmtime(self.path)
        except OSError:
            m = None
        if m != self.last_mtime:
            self.last_mtime = m
            self.load()
        self.after(500, self.watch)

    # ---------- Goi Vivado chay mo phong ----------
    def run_sim(self):
        if self.proc and self.proc.poll() is None:
            return
        vivado = find_vivado()
        if not vivado:
            self.status.config(text="Khong tim thay vivado.bat. Sua bien VIVADO o dau file tinyml_viewer.py.",
                               fg=RED)
            return
        if os.path.exists(self.path):
            try:
                os.remove(self.path)            # xoa ket qua cu de thay anh hien dan
            except OSError:
                pass
        self.images, self.idx = [], 0
        self.draw()
        self.draw_strip()
        self.run_btn.config(state="disabled", text="Dang chay...")
        self.status.config(text="Vivado dang bien dich va chay mo phong (mat vai phut)...", fg=GREY)
        cmd = [vivado, "-mode", "batch", "-nojournal", "-nolog",
               "-source", RUN_TCL, "-tclargs", PROJECT]
        log_lines = []

        def worker():
            try:
                self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                             text=True, errors="replace",
                                             cwd=os.path.dirname(PROJECT))
                for line in self.proc.stdout:
                    log_lines.append(line.rstrip())
                    if line.startswith(("OK", "SAI", "PASS", "FAIL", "ERROR", "---")):
                        self.after(0, lambda l=line.strip(): self.status.config(text=l, fg=GREY))
                rc = self.proc.wait()
            except OSError as e:
                log_lines.append(str(e))
                rc = -1
            self.after(0, lambda: self.sim_done(rc, log_lines))

        threading.Thread(target=worker, daemon=True).start()

    def sim_done(self, rc, log_lines):
        self.run_btn.config(state="normal", text="Chay mo phong")
        errs = [l for l in log_lines if l.startswith("ERROR")]
        if rc != 0 or errs:
            msg = errs[0] if errs else f"Vivado ket thuc voi ma {rc}"
            self.status.config(text=msg[:150], fg=RED)
        else:
            self.status.config(text="Mo phong xong.", fg=GREEN)
        self.load()

    def choose(self):
        p = filedialog.askopenfilename(title="Chon ket_qua_sim.txt",
                                       filetypes=[("Ket qua mo phong", "*.txt"), ("Tat ca", "*.*")])
        if p:
            self.path = p
            self.load()

    def load(self):
        if not os.path.exists(self.path):
            self.info.config(text=f"Chua co file: {self.path}  (chay mo phong truoc)", fg=RED)
            return
        old = len(self.images)
        self.images, errors = read_results(self.path)
        if len(self.images) > old:              # co anh moi -> nhay toi anh moi nhat
            self.idx = len(self.images) - 1
        self.idx = min(self.idx, max(len(self.images) - 1, 0))
        n_ok = sum(im["ok"] for im in self.images)
        state = ("dang chay..." if errors is None
                 else "PASS" if errors == 0 else f"FAIL ({errors} loi)")
        self.info.config(text=f"{len(self.images)} anh, dung {n_ok}  |  testbench: {state}",
                         fg=GREEN if errors == 0 else (RED if errors else GREY))
        self.draw()
        self.draw_strip()

    def step(self, d):
        if self.images:
            self.idx = (self.idx + d) % len(self.images)
            self.draw()
            self.draw_strip()

    def draw(self):
        cv = self.cv
        cv.delete("all")
        if not self.images:
            cv.create_text(150, 120, text="Chua co anh nao", fill=GREY)
            return
        im = self.images[self.idx]
        for p, v in enumerate(im["pixels"]):
            r, c = divmod(p, 28)
            g = 255 - v
            cv.create_rectangle(c * PIX, r * PIX + 10, (c + 1) * PIX, (r + 1) * PIX + 10,
                                fill=f"#{g:02x}{g:02x}{g:02x}", outline="")
        x0 = 28 * PIX + 30
        color = GREEN if im["ok"] else RED
        digit = int(im["fpga"]) if im["fpga"].isdigit() else None
        cv.create_text(x0, 20, text=f"Anh {im['n']}", anchor="w", font=("Arial", 14, "bold"))
        cv.create_text(x0, 45, text="LED 7 doan (FPGA):", anchor="w", fill=GREY)
        draw_seg7(cv, x0 + 10, 60, digit, color)
        y = 165
        for name, val in (("FPGA tra ve", im["fpga"]), ("Python du doan", im["python"]),
                          ("Nhan that", im["label"])):
            cv.create_text(x0, y, text=f"{name}:", anchor="w", fill=GREY)
            cv.create_text(x0 + 130, y, text=str(val), anchor="w", font=("Arial", 13, "bold"))
            y += 24
        cv.create_text(x0, y + 8, text="KHOP" if im["ok"] else "SAI", anchor="w",
                       fill=color, font=("Arial", 16, "bold"))

    def draw_strip(self):
        s = self.strip
        s.delete("all")
        for k, im in enumerate(self.images):
            x = k * 62
            for p, v in enumerate(im["pixels"]):
                if v > 60:
                    r, c = divmod(p, 28)
                    s.create_rectangle(x + c * 2, r * 2, x + c * 2 + 2, r * 2 + 2,
                                       fill="black", outline="")
            s.create_text(x + 28, 62, text=im["fpga"],
                          fill=GREEN if im["ok"] else RED, font=("Arial", 10, "bold"))
            if k == self.idx:
                s.create_rectangle(x - 2, -1, x + 58, 57, outline="#3b6fd8", width=2)

    def click_strip(self, e):
        k = e.x // 62
        if 0 <= k < len(self.images):
            self.idx = k
            self.draw()
            self.draw_strip()


if __name__ == "__main__":
    Viewer(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_FILE).mainloop()
