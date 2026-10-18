"""
tinyml_web.py - Trang web "go chu" bang bo tang toc TinyML (MNIST int8, FPGA)

Chay:   python tinyml_web.py         (hoac bam dup web.bat)
-> tu mo trinh duyet tai http://127.0.0.1:8765

* Chon 1 bo mau thu (20 anh co san, so dien thoai, ngay thang, tu nhap...).
* Bam "Chay mo phong": trang ghi file anh_vao.txt roi goi Vivado (batch) chay
  tb_tinyml_top voi bo mau do. Moi ky tu ASCII FPGA tra ve qua UART duoc
  "go" len 1 trang giay trang giong Word, kem ma ASCII cua no.
* Trang luon doc ket_qua_sim.txt, nen chay testbench trong Vivado GUI cung hien.
Chi dung thu vien co san cua Python, khong can cai them gi.
"""
import glob
import json
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# ----------------------------------------------------------------------------
# Cau hinh (sua o day neu may khac)
# ----------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                                   # TONG_HOP_Tiny
GEN = os.path.join(ROOT, "gen")
VIVADO = os.environ.get("TINYML_VIVADO", r"D:\VHDL\AMD_VIVADO\2025.2\Vivado\bin\vivado.bat")
PROJECT = os.environ.get("TINYML_PROJECT", os.path.normpath(
    os.path.join(ROOT, "..", "TINY_MNIST", "TINY_MNIST.xpr")))
RESULT = os.path.join(os.path.dirname(PROJECT), "TINY_MNIST.sim", "sim_1", "behav",
                      "xsim", "ket_qua_sim.txt")
RUN_TCL = os.path.join(HERE, "run_sim.tcl")
INPUT = os.path.join(HERE, "_tam", "anh_vao.txt")              # bo mau gui cho testbench
CHUP = os.path.join(HERE, "mau_tu_chup")                       # bo mau tao tu anh chup (.json)
PORT = 8765
MAX_ANH = 20
N_CO_SAN = 20                                                  # so anh nhung trong testbench


def find_vivado():
    if os.path.exists(VIVADO):
        return VIVADO
    for name in ("vivado.bat", "vivado"):
        p = shutil.which(name)
        if p:
            return p
    cands = []
    for pat in (r"C:\Xilinx\Vivado\*\bin\vivado.bat", r"C:\Xilinx\*\Vivado\bin\vivado.bat",
                r"C:\AMDDesignTools\*\Vivado\bin\vivado.bat",
                r"D:\VHDL\AMD_VIVADO\*\Vivado\bin\vivado.bat"):
        cands += glob.glob(pat)
    return sorted(cands)[-1] if cands else None


# ----------------------------------------------------------------------------
# 200 anh test lay tu gen/*.mem (cung du lieu ban AI xuat ra)
# ----------------------------------------------------------------------------
def load_samples():
    def rd(name):
        with open(os.path.join(GEN, name)) as f:
            return [l.strip() for l in f if l.strip()]
    img, exp, lab = rd("test_images.mem"), rd("test_expected.mem"), rd("test_labels.mem")
    n = min(len(lab), len(img) // 784, len(exp) // 11)
    return [{"i": k, "py": int(exp[k * 11], 16), "lab": int(lab[k], 16),
             "px": "".join(img[k * 784:(k + 1) * 784]).lower()} for k in range(n)]


SAMPLES = load_samples()


# ----------------------------------------------------------------------------
# Mo hinh int8 giong het phan cung (de tinh "Python du doan" cho anh tu chup)
#   x = pixel >> 1 ; h = clamp((acc*M1 + 2^(SHIFT-1)) >>> SHIFT, 0, 127) ; argmax
# ----------------------------------------------------------------------------
def _s(v, bits):
    return v - (1 << bits) if v >= 1 << (bits - 1) else v


def _unpack(name, n_out, n_in, pe):
    W = [[0] * n_in for _ in range(n_out)]
    with open(os.path.join(GEN, name)) as f:
        for a, line in enumerate(l for l in f if l.strip()):
            w = int(line, 16)
            g, i = divmod(a, n_in)
            for k in range(pe):
                W[g * pe + k][i] = _s((w >> (8 * k)) & 0xFF, 8)
    return W


def _pkg_param(name):
    with open(os.path.join(ROOT, "rtl", "tinyml_pkg.sv"), encoding="utf-8") as f:
        return int(re.search(r"localparam\s+int\s+%s\s*=\s*(\d+)" % name, f.read()).group(1))


class Int8Model:
    def __init__(self):
        self.W1 = _unpack("w1.mem", 32, 784, 8)
        self.W2 = _unpack("w2.mem", 10, 32, 10)
        with open(os.path.join(GEN, "b1.mem")) as f:
            self.B1 = [_s(int(l, 16), 32) for l in f if l.strip()]
        with open(os.path.join(GEN, "b2.mem")) as f:
            self.B2 = [_s(int(l, 16), 32) for l in f if l.strip()]
        self.M1, self.SHIFT = _pkg_param("M1"), _pkg_param("SHIFT")

    def scores(self, px):
        x = [p >> 1 for p in px]
        h = []
        for o in range(32):
            acc = self.B1[o] + sum(w * v for w, v in zip(self.W1[o], x))
            r = (acc * self.M1 + (1 << (self.SHIFT - 1))) >> self.SHIFT
            h.append(min(max(r, 0), 127))
        sc = [self.B2[o] + sum(w * v for w, v in zip(self.W2[o], h)) for o in range(10)]
        return max(range(10), key=lambda o: (sc[o], -o)), sc  # bằng nhau thì lấy số nhỏ, như argmax RTL

    def predict(self, px):
        return self.scores(px)[0]


MODEL = Int8Model()


def load_chup():
    """Cac bo mau da luu tu anh chup: pc/mau_tu_chup/*.json"""
    out = []
    for fn in sorted(glob.glob(os.path.join(CHUP, "*.json"))):
        try:
            with open(fn, encoding="utf-8") as f:
                d = json.load(f)
            items = [{"i": -1, "px": it["px"], "lab": int(it["lab"]),
                      "py": MODEL.predict([int(it["px"][k:k + 2], 16) for k in range(0, 1568, 2)])}
                     for it in d["items"]][:MAX_ANH]
            out.append({"id": "chup_" + os.path.splitext(os.path.basename(fn))[0],
                        "ten": "📷 " + d.get("ten", "Ảnh chụp"), "mo_ta": "Bộ mẫu cắt từ ảnh bạn chụp",
                        "items": items})
        except (OSError, ValueError, KeyError):
            continue
    return out


CHUP_SETS = load_chup()

SETS = [
    {"id": "co_san", "ten": "20 ảnh có sẵn", "mo_ta": "20 ảnh nhúng sẵn trong testbench, không cần file"},
    {"id": "so_dt", "ten": "Số điện thoại", "text": "0987654321", "mo_ta": "Mỗi chữ số lấy 1 ảnh viết tay"},
    {"id": "ngay", "ten": "Ngày tháng", "text": "18102026", "mo_ta": "Ngày 18/10/2026"},
    {"id": "day_so", "ten": "Dãy 0 đến 9", "text": "01234567890123456789", "mo_ta": "Hai lượt 0 đến 9, mỗi lượt ảnh khác"},
    {"id": "kho", "ten": "Có ảnh khó", "mo_ta": "Ảnh 140 đến 159, có 2 ảnh AI đoán sai"},
    {"id": "ngau_nhien", "ten": "20 ảnh ngẫu nhiên", "mo_ta": "Bốc ngẫu nhiên trong 200 ảnh test"},
    {"id": "tu_nhap", "ten": "Tự nhập", "text": "", "mo_ta": "Gõ tối đa 20 chữ số"},
]


def pick_for_text(text):
    """Chon anh cho tung chu so: uu tien anh ma AI doan dung, lan luot anh khac nhau."""
    used = {}
    out = []
    for ch in text:
        if not ch.isdigit():
            continue
        d = int(ch)
        good = [s for s in SAMPLES if s["lab"] == d and s["py"] == d] or \
               [s for s in SAMPLES if s["py"] == d]
        if good:
            out.append(good[used.get(d, 0) % len(good)])
            used[d] = used.get(d, 0) + 1
        if len(out) >= MAX_ANH:
            break
    return out


def all_sets():
    return SETS + [{k: v for k, v in c.items() if k != "items"} for c in CHUP_SETS]


def build_set(set_id, text="", seed=0):
    chup = next((c for c in CHUP_SETS if c["id"] == set_id), None)
    if chup:
        return {"id": set_id, "ten": chup["ten"], "items": chup["items"]}
    if set_id == "co_san":
        items = SAMPLES[:N_CO_SAN]
    elif set_id == "kho":
        items = SAMPLES[140:160]
    elif set_id == "ngau_nhien":
        items = random.Random(seed).sample(SAMPLES, min(MAX_ANH, len(SAMPLES)))
    else:
        if not text:
            text = next((s.get("text", "") for s in SETS if s["id"] == set_id), "")
        items = pick_for_text(text)
    ten = next((s["ten"] for s in all_sets() if s["id"] == set_id), set_id)
    return {"id": set_id, "ten": ten, "items": items}


def read_results(path):
    images, errors = [], None
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = [l.rstrip("\n") for l in f]
    except OSError:
        return None, None
    i = 0
    while i < len(lines):
        p = lines[i].split()
        if p and p[0] == "IMG" and i + 1 < len(lines):
            ch = p[2] if len(p) > 2 else "?"
            code = int(p[6], 16) if len(p) > 6 else (ord(ch[0]) if ch else 0)
            images.append({
                "n": int(p[1]), "ch": ch, "code": code,
                "py": int(p[3]) if len(p) > 3 else -1,
                "lab": int(p[4]) if len(p) > 4 else -1,
                "ok": len(p) > 5 and p[5] == "1",
                "px": lines[i + 1].strip()[:1568].lower(),
            })
            i += 2
        else:
            if p and p[0] == "END" and len(p) > 1:
                errors = int(p[1])
            i += 1
    return images, errors


# ----------------------------------------------------------------------------
# Chay Vivado o che do batch
# ----------------------------------------------------------------------------
class SimRunner:
    def __init__(self):
        self.lock = threading.Lock()
        self.proc = None
        self.log = []
        self.state = "idle"          # idle | running | done | error
        self.message = ""
        self.t0 = self.t1 = None
        self.plan = None             # bo mau dang chay

    def start(self, plan):
        with self.lock:
            if self.state == "running":
                return False, "Mô phỏng đang chạy"
            vivado = find_vivado()
            if not vivado:
                self.state, self.message = "error", "Không tìm thấy vivado.bat (sửa biến VIVADO trong tinyml_web.py)"
                return False, self.message
            if not os.path.exists(PROJECT):
                self.state, self.message = "error", f"Không tìm thấy project: {PROJECT}"
                return False, self.message
            if not plan["items"]:
                return False, "Bộ mẫu trống, hãy nhập ít nhất 1 chữ số"
            try:
                if os.path.exists(RESULT):
                    os.remove(RESULT)
            except OSError:
                pass
            cmd = [vivado, "-mode", "batch", "-nojournal", "-nolog",
                   "-source", RUN_TCL, "-tclargs", PROJECT]
            if plan["id"] != "co_san":
                # File cho testbench (+ANH_VAO): so anh, roi moi anh: python nhan 784 pixel (hex)
                os.makedirs(os.path.dirname(INPUT), exist_ok=True)
                with open(INPUT, "w") as f:
                    f.write(f"{len(plan['items']):x}\n")
                    for s in plan["items"]:
                        f.write(f"{s['py']:x} {s['lab']:x}\n")
                        px = s["px"]
                        for r in range(28):
                            f.write(" ".join(px[(r * 28 + c) * 2:(r * 28 + c) * 2 + 2]
                                             for c in range(28)) + "\n")
                cmd.append(INPUT.replace("\\", "/"))
            self.plan = plan
            self.log, self.state, self.message = [], "running", "Vivado đang biên dịch..."
            self.t0, self.t1 = time.time(), None
            threading.Thread(target=self._run, args=(cmd,), daemon=True).start()
            return True, "Đã bắt đầu"

    def _run(self, cmd):
        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         text=True, errors="replace",
                                         cwd=os.path.dirname(PROJECT))
            for line in self.proc.stdout:
                line = line.rstrip()
                with self.lock:
                    self.log.append(line)
                    self.log = self.log[-400:]
                    if line.startswith(("INFO: [VRFC", "INFO: [XSIM")):
                        self.message = "Vivado đang biên dịch..."
                    elif line.startswith("--- Phan 1"):
                        self.message = "Đang gửi ảnh qua UART..."
                    elif line.startswith("--- Phan 2"):
                        self.message = "Đang thử khung lỗi (ngừng 11 ms)..."
                    elif line.startswith("OK  anh"):
                        self.message = "FPGA vừa trả ký tự cho ảnh " + line.split()[2].rstrip(":")
                    elif line.startswith("SAI"):
                        self.message = "Có lỗi: " + line.strip()
            rc = self.proc.wait()
        except OSError as e:
            with self.lock:
                self.log.append(str(e))
            rc = -1
        try:
            if os.path.exists(INPUT):
                os.remove(INPUT)
        except OSError:
            pass
        with self.lock:
            self.t1 = time.time()
            errs = [l for l in self.log if l.startswith(("ERROR", "FATAL"))]
            if rc != 0 or errs:
                self.state = "error"
                self.message = errs[0] if errs else f"Vivado kết thúc với mã {rc}"
            else:
                self.state, self.message = "done", "Mô phỏng xong"

    def snapshot(self):
        with self.lock:
            el = None
            if self.t0:
                el = round((self.t1 or time.time()) - self.t0)
            plan = None
            if self.plan:
                plan = {"id": self.plan["id"], "ten": self.plan["ten"], "n": len(self.plan["items"])}
            return {"state": self.state, "message": self.message,
                    "log": self.log[-60:], "elapsed": el, "plan": plan}


RUNNER = SimRunner()


# ----------------------------------------------------------------------------
# Web server
# ----------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj):
        self._send(200, json.dumps(obj), "application/json")

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path in ("/", "/index.html"):
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif u.path == "/api/sets":
            self._json({"sets": all_sets(), "max": MAX_ANH, "tong": len(SAMPLES)})
        elif u.path == "/api/plan":
            try:
                seed = int(q.get("seed", "0"))
            except ValueError:
                seed = 0
            self._json(build_set(q.get("set", "co_san"), q.get("text", "")[:MAX_ANH], seed))
        elif u.path == "/api/status":
            images, errors = read_results(RESULT)
            out = RUNNER.snapshot()
            out.update({"images": images or [], "errors": errors,
                        "has_file": images is not None,
                        "result_path": RESULT, "project": PROJECT,
                        "vivado": find_vivado() or ""})
            self._json(out)
        else:
            self._send(404, "not found", "text/plain")

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return {}

    def do_POST(self):
        global CHUP_SETS
        if self.path == "/api/du_doan":
            # {"px": ["<1568 hex>", ...]} -> chữ số mô hình int8 dự đoán cho từng ảnh
            req = self._body()
            res = [MODEL.scores([int(h[k:k + 2], 16) for k in range(0, 1568, 2)])
                   for h in req.get("px", [])[:MAX_ANH] if len(h) == 1568]
            # do tu tin = diem cao nhat - diem cao nhi (dung de doan huong xoay anh)
            self._json({"py": [p for p, _ in res],
                        "margin": [sorted(sc)[-1] - sorted(sc)[-2] for _, sc in res]})
        elif self.path == "/api/luu_bo":
            # {"ten": "...", "items": [{"px": hex, "lab": d}, ...]} -> pc/mau_tu_chup/<ten>.json
            req = self._body()
            ten = str(req.get("ten", "")).strip()[:40] or "Ảnh chụp"
            items = [{"px": str(it["px"]).lower(), "lab": int(it["lab"])}
                     for it in req.get("items", [])[:MAX_ANH]
                     if len(str(it.get("px", ""))) == 1568 and 0 <= int(it.get("lab", -1)) <= 9]
            if not items:
                self._json({"ok": False, "message": "Chưa có chữ số nào"})
                return
            ascii_ten = unicodedata.normalize("NFKD", ten.lower().replace("đ", "d")).encode("ascii", "ignore").decode()
            slug = re.sub(r"[^a-z0-9]+", "_", ascii_ten).strip("_") or "anh"
            if os.path.exists(os.path.join(CHUP, slug + ".json")):
                slug += time.strftime("_%m%d_%H%M%S")
            os.makedirs(CHUP, exist_ok=True)
            with open(os.path.join(CHUP, slug + ".json"), "w", encoding="utf-8") as f:
                json.dump({"ten": ten, "items": items}, f, ensure_ascii=False, indent=0)
            CHUP_SETS = load_chup()
            self._json({"ok": True, "id": "chup_" + slug})
        elif self.path == "/api/run":
            try:
                n = int(self.headers.get("Content-Length", "0"))
                req = json.loads(self.rfile.read(n) or b"{}")
                seed = int(req.get("seed", 0) or 0)
            except ValueError:
                req, seed = {}, 0
            plan = build_set(req.get("set", "co_san"), str(req.get("text", ""))[:MAX_ANH], seed)
            ok, msg = RUNNER.start(plan)
            self._json({"ok": ok, "message": msg})
        else:
            self._send(404, "not found", "text/plain")


PAGE = r"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TinyML Gõ Chữ</title>
<style>
:root{
  --chrome:#f3f2f1; --panel:#ffffff; --ink:#201f1e; --muted:#605e5c; --line:#e1dfdd;
  --brand:#2b579a; --brand2:#1e4378; --desk:#e8e6e4; --sel:#deecf9;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){ --chrome:#1f1f1f; --panel:#292929; --ink:#f3f2f1; --muted:#b3b0ad;
    --line:#3b3a39; --desk:#141414; --sel:#203a5c; }
}
:root[data-theme="dark"]{ --chrome:#1f1f1f; --panel:#292929; --ink:#f3f2f1; --muted:#b3b0ad;
    --line:#3b3a39; --desk:#141414; --sel:#203a5c; }
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:var(--desk);color:var(--ink);display:flex;flex-direction:column;
     font:14px/1.45 "Segoe UI",system-ui,-apple-system,Roboto,sans-serif}
/* ---- thanh tieu de + ribbon kieu Word ---- */
.titlebar{background:var(--brand);color:#fff;display:flex;align-items:center;gap:12px;padding:8px 16px}
.titlebar .logo{width:26px;height:26px;border-radius:4px;background:#fff;color:var(--brand);
  display:grid;place-items:center;font-weight:800;font-size:15px}
.titlebar .name{font-size:14px;opacity:.95}
.titlebar .name b{font-weight:600}
.titlebar .sp{flex:1}
.titlebar .who{font-size:12px;opacity:.85}
.ribbon{background:var(--chrome);border-bottom:1px solid var(--line);padding:10px 16px;
  display:flex;flex-wrap:wrap;gap:14px;align-items:stretch}
.group{display:flex;flex-direction:column;gap:6px;padding-right:14px;border-right:1px solid var(--line)}
.group:last-child{border-right:0}
.group .gl{font-size:11px;color:var(--muted);text-align:center;margin-top:auto}
.sets{display:flex;flex-wrap:wrap;gap:6px;max-width:470px}
.chip{border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:4px;
  padding:5px 10px;cursor:pointer;font:inherit;font-size:13px}
.chip:hover{border-color:var(--brand)}
.chip.on{background:var(--sel);border-color:var(--brand);font-weight:600}
.row{display:flex;gap:8px;align-items:center}
input.txt{font:15px/1 Consolas,"Cascadia Mono",monospace;letter-spacing:2px;padding:6px 8px;width:250px;
  border:1px solid var(--line);border-radius:4px;background:var(--panel);color:var(--ink)}
.btn{border:0;border-radius:4px;padding:8px 16px;font:inherit;font-weight:600;cursor:pointer;
  background:var(--brand);color:#fff;display:inline-flex;align-items:center;justify-content:center;gap:8px}
.btn:hover{background:var(--brand2)}
.btn:disabled{opacity:.55;cursor:default}
.btn.ghost{background:transparent;color:var(--ink);border:1px solid var(--line);font-weight:500;padding:5px 12px}
.btn.ghost:hover{background:var(--sel)}
.hint{font-size:12px;color:var(--muted);max-width:300px}
.strip{display:grid;grid-template-columns:repeat(10,26px);gap:3px}
.strip canvas{width:26px;height:26px;border:1px solid var(--line);background:#fff;border-radius:2px;image-rendering:pixelated}
/* ---- ban lam viec + trang giay ---- */
.desk{flex:1;overflow:auto;padding:28px 16px 40px}
.page{background:#fff;color:#1b1b1b;width:min(794px,100%);min-height:1050px;margin:0 auto;
  box-shadow:0 1px 3px rgba(0,0,0,.18),0 6px 24px rgba(0,0,0,.08);padding:72px 80px 64px;
  font-family:"Times New Roman",Georgia,serif;font-size:16px;line-height:1.5}
.page h1{font-size:26px;font-weight:700;margin:0 0 4px;color:#1b1b1b;font-family:Calibri,"Segoe UI",sans-serif}
.page .meta{color:#555;font-size:14px;margin-bottom:22px}
.page h2{font-family:Calibri,"Segoe UI",sans-serif;font-size:17px;color:#2b579a;margin:28px 0 10px}
.typed{display:flex;flex-wrap:wrap;align-items:flex-end;gap:2px 4px;min-height:96px;
  padding:10px 0 4px;border-bottom:1px dashed #ddd}
.ch{display:flex;flex-direction:column;align-items:center;animation:pop .18s ease-out}
.ch .g{font-family:Consolas,"Cascadia Mono","Courier New",monospace;font-size:46px;line-height:1.05;
  padding:0 3px;color:#111}
.ch .h{font-family:Consolas,monospace;font-size:11px;color:#777}
.ch.wrong .g{text-decoration:underline wavy #e81123;text-decoration-thickness:2px;text-underline-offset:6px}
.ch.hw .g{color:#e81123}
.caret{width:2px;height:46px;background:#111;margin:0 0 18px 2px;animation:blink 1s steps(1) infinite}
@keyframes blink{50%{opacity:0}}
@keyframes pop{from{transform:translateY(6px);opacity:0}to{transform:none;opacity:1}}
.empty{color:#999;font-style:italic;align-self:center}
.ascii{font-family:Consolas,"Courier New",monospace;font-size:13.5px;color:#333;word-break:break-word;
  background:#f7f7f7;border:1px solid #eee;padding:10px 12px;border-radius:2px;min-height:40px}
.tw{overflow-x:auto}
table.t{border-collapse:collapse;width:100%;font-size:14px;font-family:Calibri,"Segoe UI",sans-serif}
table.t th,table.t td{border:1px solid #bfbfbf;padding:4px 8px;text-align:center}
table.t th{background:#dbe5f1;color:#1f3864;font-weight:600}
table.t tr:nth-child(even) td{background:#f8f9fb}
table.t td canvas{width:36px;height:36px;image-rendering:pixelated;display:block;margin:auto}
table.t .mono{font-family:Consolas,monospace}
table.t td:last-child{white-space:nowrap}
.ok{color:#107c10;font-weight:600}.bad{color:#c50f1f;font-weight:600}.warn{color:#9d5d00;font-weight:600}
.note{font-size:13.5px;color:#444}
.legend{font-size:12.5px;color:#555;margin-top:6px}
.legend .w{text-decoration:underline wavy #e81123;text-underline-offset:3px}
.legend .r{color:#e81123}
/* ---- nhat ky + thanh trang thai ---- */
details.log{width:min(794px,100%);margin:14px auto 0;background:var(--panel);border:1px solid var(--line);border-radius:4px}
details.log summary{cursor:pointer;padding:8px 12px;color:var(--muted);font-size:13px}
details.log pre{margin:0;padding:8px 12px 12px;max-height:240px;overflow:auto;font:12px/1.4 Consolas,monospace;color:var(--ink)}
.status{background:var(--brand);color:#fff;font-size:12px;display:flex;gap:18px;padding:4px 16px;align-items:center;flex-wrap:wrap}
.status .sp{flex:1}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:#9fd89f;margin-right:6px}
.dot.run{background:#ffd335;animation:blink 1s steps(1) infinite}
.dot.err{background:#ff8a8a}
.spin{width:14px;height:14px;border:2px solid rgba(255,255,255,.5);border-top-color:#fff;border-radius:50%;animation:sp 1s linear infinite;display:none}
.running .spin{display:inline-block}
@keyframes sp{to{transform:rotate(360deg)}}
/* ---- khung tai anh chup ---- */
.up{background:var(--panel);border-bottom:1px solid var(--line);padding:14px 16px;display:flex;gap:18px;flex-wrap:wrap}
.up[hidden]{display:none}
.up .view{flex:1 1 420px;max-width:620px}
.up canvas#upCv{width:100%;border:1px solid var(--line);border-radius:4px;background:#fff;touch-action:none;cursor:crosshair;display:block}
.up .ctl{flex:1 1 320px;display:flex;flex-direction:column;gap:10px}
.up label{font-size:12.5px;color:var(--muted)}
.up input[type=range]{width:180px;vertical-align:middle}
.drop{border:2px dashed var(--line);border-radius:6px;padding:26px;text-align:center;color:var(--muted);cursor:pointer}
.drop.hov{border-color:var(--brand);background:var(--sel)}
.digs{display:flex;flex-wrap:wrap;gap:8px}
.dg{display:flex;flex-direction:column;align-items:center;gap:3px;font-size:12px;color:var(--muted)}
.dg canvas{width:56px;height:56px;image-rendering:pixelated;border:1px solid var(--line);background:#000;border-radius:3px}
.dg b{font-size:15px;color:var(--ink)}
.dg .x{color:#c50f1f}
@media (max-width:700px){
  .page{padding:36px 20px;min-height:0}
  .ch .g{font-size:34px}.caret{height:34px}
  .group{border-right:0;padding-right:0}
  input.txt{width:100%}
}
@media print{.titlebar,.ribbon,.status,details.log{display:none}.desk{padding:0}.page{box-shadow:none}}
</style>
</head>
<body>
<div class="titlebar">
  <div class="logo">T</div>
  <div class="name"><b>ket_qua_FPGA.docx</b> · TinyML MNIST int8</div>
  <div class="sp"></div>
  <div class="who">Mô phỏng Vivado, chưa cần board</div>
</div>

<div class="ribbon">
  <div class="group">
    <div class="sets" id="sets"></div>
    <div class="gl">Bộ mẫu thử</div>
  </div>
  <div class="group">
    <div class="row">
      <input class="txt" id="txt" maxlength="20" inputmode="numeric" placeholder="gõ chữ số, vd 0987654321">
      <button class="btn ghost" id="reroll" title="Bốc lại ảnh ngẫu nhiên">Bốc lại</button>
    </div>
    <div class="strip" id="strip"></div>
    <div class="gl" id="stripLabel">Ảnh sẽ gửi</div>
  </div>
  <div class="group">
    <button class="btn" id="run"><span class="spin"></span><span id="runLbl">▶ Chạy mô phỏng</span></button>
    <div class="row">
      <button class="btn ghost" id="save">Lưu .txt</button>
      <button class="btn ghost" id="print">In</button>
      <button class="btn ghost" id="upBtn">📷 Tải ảnh</button>
    </div>
    <div class="hint" id="hint"></div>
    <div class="gl">Chạy</div>
  </div>
</div>

<section class="up" id="up" hidden>
  <div class="view">
    <div class="drop" id="drop">Bấm để chọn ảnh hoặc kéo thả ảnh vào đây (jpg, png)<input type="file" id="file" accept="image/*" hidden></div>
    <canvas id="upCv" hidden></canvas>
    <div class="hint" id="upInfo" style="max-width:none;margin-top:6px"></div>
  </div>
  <div class="ctl">
    <div class="row">
      <button class="btn ghost" id="rotL">↺ Xoay trái</button>
      <button class="btn ghost" id="rotR">↻ Xoay phải</button>
      <button class="btn ghost" id="noCrop">Bỏ vùng chọn</button>
    </div>
    <div><label>Độ nhạy mực <input type="range" id="th" min="10" max="90" value="35"> <span id="thV">35</span></label></div>
    <div><label>Độ đậm nét <input type="range" id="thick" min="0" max="3" step="0.25" value="1.25"> <span id="thickV">1.25</span></label></div>
    <div><label>Chữ số đúng (nhãn thật, theo thứ tự trái sang phải)</label><br>
      <input class="txt" id="labs" maxlength="20" inputmode="numeric" placeholder="vd 12345678"></div>
    <div class="digs" id="digs"></div>
    <div class="row">
      <input class="txt" id="setName" maxlength="40" placeholder="tên bộ mẫu" style="letter-spacing:0;width:180px">
      <button class="btn" id="saveSet">Lưu thành bộ mẫu</button>
    </div>
    <div class="hint" style="max-width:none">Kéo chuột trên ảnh để chỉ chọn vùng có chữ số. Chữ dưới mỗi ô là số mô hình int8 (giống phần cứng) đoán ra; đỏ là khác nhãn bạn nhập.</div>
  </div>
</section>

<div class="desk">
  <div class="page" id="page">
    <h1>Kết quả nhận dạng chữ số viết tay</h1>
    <div class="meta" id="meta">Bộ tăng tốc MLP 784‑32‑10 int8 trên FPGA · UART 1 Mbaud · mỗi ảnh FPGA trả về 1 ký tự ASCII</div>

    <h2>Văn bản FPGA gõ ra</h2>
    <div class="typed" id="typed"><span class="empty">Chưa có ký tự nào. Bấm “Chạy mô phỏng”.</span><span class="caret"></span></div>
    <div class="legend">Dưới mỗi ký tự là mã ASCII FPGA gửi qua UART. <span class="w">Gạch sóng đỏ</span>: AI đoán khác nhãn thật (lỗi mô hình, phần cứng vẫn đúng). <span class="r">Chữ đỏ</span>: FPGA khác Python (lỗi phần cứng).</div>

    <h2>Chuỗi byte nhận được qua UART</h2>
    <div class="ascii" id="ascii">—</div>

    <h2>Chi tiết từng ảnh</h2>
    <div class="tw"><table class="t">
      <thead><tr><th>STT</th><th>Ảnh gửi</th><th>Ký tự</th><th>ASCII hex</th><th>Dec</th><th>Nhị phân</th><th>Python</th><th>Nhãn thật</th><th>Kết quả</th></tr></thead>
      <tbody id="rows"><tr><td colspan="9" class="note">Chưa có dữ liệu</td></tr></tbody>
    </table></div>

    <h2>Cách đổi ra mã ASCII</h2>
    <p class="note">Phần cứng tính ra chữ số d (0 đến 9) ở khối argmax, rồi khối UART gửi về byte <b>0x30 + d</b>.
    Ví dụ d = 7 thì byte gửi là 0x37, đúng mã ASCII của ký tự “7”. Trang này chỉ hiện đúng byte testbench đã nhận được từ chân TX của FPGA.</p>
  </div>
  <details class="log"><summary>Nhật ký Vivado</summary><pre id="log">(trống)</pre></details>
</div>

<div class="status">
  <span><span class="dot" id="dot"></span><span id="stMsg">Sẵn sàng</span></span>
  <span id="stChars">0 ký tự</span>
  <span id="stPy">Khớp Python: –</span>
  <span id="stLab">Đúng nhãn: –</span>
  <span class="sp"></span>
  <span id="stTime"></span>
  <span>Tiếng Việt</span>
</div>

<script>
const $ = id => document.getElementById(id);
let SETS = [], cur = "co_san", seed = 1, shown = 0, lastKey = "", typing = false, queue = [], lastImgs = [], runId = "";

function drawPx(cv, hex){
  const ctx = cv.getContext("2d"), im = ctx.createImageData(28, 28);
  for (let p = 0; p < 784; p++){
    const v = parseInt(hex.substr(p*2, 2), 16) || 0, ink = 255 - v;   // mực đen trên giấy trắng
    im.data[p*4] = ink; im.data[p*4+1] = ink; im.data[p*4+2] = ink; im.data[p*4+3] = 255;
  }
  ctx.putImageData(im, 0, 0);
}
function canvas(hex){ const c = document.createElement("canvas"); c.width = c.height = 28; drawPx(c, hex); return c; }
const hex2 = n => "0x" + n.toString(16).toUpperCase().padStart(2, "0");
const digits = () => $("txt").value.replace(/\D/g, "");

async function loadSets(){
  if (!SETS.length) SETS = (await (await fetch("/api/sets")).json()).sets;
  const box = $("sets"); box.innerHTML = "";
  for (const s of SETS){
    const b = document.createElement("button");
    b.className = "chip" + (s.id === cur ? " on" : ""); b.textContent = s.ten; b.title = s.mo_ta || "";
    b.onclick = () => { cur = s.id; if ("text" in s) $("txt").value = s.text; loadSets(); loadPlan(); };
    box.appendChild(b);
  }
  let s = SETS.find(x => x.id === cur);
  if (!s){ cur = "co_san"; s = SETS[0]; box.firstChild.classList.add("on"); }
  $("txt").style.display = ("text" in s) ? "" : "none";
  $("reroll").style.display = cur === "ngau_nhien" ? "" : "none";
  $("hint").textContent = (s.mo_ta || "") + ". Vivado biên dịch khoảng 1 phút rồi mới bắt đầu gõ.";
}
async function loadPlan(){
  const plan = await (await fetch(`/api/plan?set=${cur}&text=${digits()}&seed=${seed}`)).json();
  const st = $("strip"); st.innerHTML = "";
  for (const it of plan.items){ const c = canvas(it.px); c.title = `ảnh test #${it.i}, nhãn ${it.lab}`; st.appendChild(c); }
  $("stripLabel").textContent = plan.items.length ? `${plan.items.length} ảnh sẽ gửi qua UART` : "Chưa có ảnh nào";
}
$("txt").addEventListener("input", () => {
  const v = digits(); if (v !== $("txt").value) $("txt").value = v;
  const s = SETS.find(x => x.id === cur); if (s && v !== s.text && cur !== "tu_nhap"){ cur = "tu_nhap"; loadSets(); }
  clearTimeout(window._pt); window._pt = setTimeout(loadPlan, 250);
});
$("reroll").onclick = () => { seed = Math.floor(Math.random()*1e6); loadPlan(); };

$("run").onclick = async () => {
  $("run").disabled = true;
  const r = await (await fetch("/api/run", {method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({set: cur, text: digits(), seed})})).json();
  if (!r.ok){ $("stMsg").textContent = r.message; $("run").disabled = false; }
  else resetPage();
  poll();
};
$("save").onclick = () => {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([lastImgs.map(i => i.ch).join("") + "\n"], {type: "text/plain"}));
  a.download = "ket_qua_FPGA.txt"; a.click();
};
$("print").onclick = () => window.print();

function resetPage(){
  shown = 0; queue = []; lastKey = "";
  $("typed").innerHTML = '<span class="empty">Đang chờ FPGA trả ký tự đầu tiên…</span><span class="caret"></span>';
  $("ascii").textContent = "—";
  $("rows").innerHTML = '<tr><td colspan="9" class="note">Đang chạy…</td></tr>';
}

function typeNext(){
  if (!queue.length){ typing = false; return; }
  typing = true;
  const im = queue.shift(), box = $("typed");
  box.querySelector(".empty")?.remove();
  const el = document.createElement("span");
  el.className = "ch" + (im.py !== im.lab ? " wrong" : "") + (!im.ok ? " hw" : "");
  el.title = `Ảnh ${im.n}: FPGA gửi ${hex2(im.code)}, Python ${im.py}, nhãn thật ${im.lab}`;
  el.innerHTML = `<span class="g"></span><span class="h">${hex2(im.code)}</span>`;
  el.querySelector(".g").textContent = im.ch;
  box.insertBefore(el, box.querySelector(".caret"));
  setTimeout(typeNext, 140);
}

function render(st){
  const imgs = st.images || [];
  lastImgs = imgs;
  if (imgs.length < shown) resetPage();
  if (imgs.length > shown){
    for (const im of imgs.slice(shown)) queue.push(im);
    shown = imgs.length;
    if (!typing) typeNext();
  }
  const key = imgs.length + ":" + (st.plan ? st.plan.ten : "");
  if (key !== lastKey){
    lastKey = key;
    $("ascii").textContent = imgs.length ? imgs.map(i => hex2(i.code)).join(" ") +
      `   →   "${imgs.map(i => i.ch).join("")}"` : "—";
    const rows = $("rows");
    if (imgs.length){
      rows.innerHTML = "";
      imgs.forEach((im, k) => {
        const tr = document.createElement("tr");
        const res = !im.ok ? '<span class="bad">SAI phần cứng</span>' :
                    im.py !== im.lab ? '<span class="warn">AI đoán sai</span>' : '<span class="ok">Đúng</span>';
        tr.innerHTML = `<td>${k+1}</td><td></td><td class="mono" style="font-size:20px">${im.ch}</td>
          <td class="mono">${hex2(im.code)}</td><td class="mono">${im.code}</td>
          <td class="mono">${im.code.toString(2).padStart(8,"0")}</td><td>${im.py}</td><td>${im.lab}</td><td>${res}</td>`;
        tr.children[1].appendChild(canvas(im.px));
        rows.appendChild(tr);
      });
    }
    if (st.plan) $("meta").textContent = `Bộ mẫu: ${st.plan.ten} · ${st.plan.n} ảnh · MLP 784‑32‑10 int8 trên FPGA · UART 1 Mbaud`;
  }
  const n = imgs.length, okPy = imgs.filter(i => i.ok).length, okLab = imgs.filter(i => i.ok && i.py === i.lab).length;
  $("stChars").textContent = st.plan ? `${n}/${st.plan.n} ký tự` : `${n} ký tự`;
  $("stPy").textContent = n ? `Khớp Python: ${okPy}/${n}` : "Khớp Python: –";
  $("stLab").textContent = n ? `Đúng nhãn: ${okLab}/${n}` : "Đúng nhãn: –";
  const run = st.state === "running";
  document.body.classList.toggle("running", run);
  $("run").disabled = run;
  $("runLbl").textContent = run ? "Đang chạy…" : "▶ Chạy mô phỏng";
  $("dot").className = "dot" + (run ? " run" : st.state === "error" ? " err" : "");
  let msg = st.message || (st.has_file ? "Đang hiện kết quả lần chạy trước" : "Sẵn sàng");
  if (run && n && msg.includes("biên dịch")) msg = "Đang nhận ký tự từ FPGA…";
  if (st.state === "done" && st.errors !== null) msg = st.errors === 0 ? "Mô phỏng xong · PASS" : `Mô phỏng xong · ${st.errors} lỗi`;
  $("stMsg").textContent = msg;
  $("stTime").textContent = st.elapsed != null ? `${st.elapsed} s` : "";
  if (st.log && st.log.length) $("log").textContent = st.log.join("\n");
}

// ================= Tải ảnh chụp -> cắt chữ số -> 28x28 kiểu MNIST =================
const UP = {img: null, rot: 0, crop: null, digits: [], drag: null};
$("upBtn").onclick = () => { $("up").hidden = !$("up").hidden; };
$("drop").onclick = () => $("file").click();
$("drop").ondragover = e => { e.preventDefault(); $("drop").classList.add("hov"); };
$("drop").ondragleave = () => $("drop").classList.remove("hov");
$("drop").ondrop = e => { e.preventDefault(); $("drop").classList.remove("hov"); if (e.dataTransfer.files[0]) loadFile(e.dataTransfer.files[0]); };
$("file").onchange = () => { if ($("file").files[0]) loadFile($("file").files[0]); };
function loadFile(f){
  const im = new Image();
  im.onload = () => { UP.img = im; UP.rot = 0; UP.crop = null; autoRotate(); };
  im.src = URL.createObjectURL(f);
}
// Ảnh đã xoay, thu nhỏ cạnh dài còn 1000 px
function rotated(){
  const im = UP.img, k = Math.min(1, 1000 / Math.max(im.naturalWidth, im.naturalHeight));
  const w = Math.round(im.naturalWidth * k), h = Math.round(im.naturalHeight * k);
  const c = document.createElement("canvas"), q = UP.rot % 2 ? [h, w] : [w, h];
  c.width = q[0]; c.height = q[1];
  const x = c.getContext("2d");
  x.translate(q[0] / 2, q[1] / 2); x.rotate(UP.rot * Math.PI / 2); x.drawImage(im, -w / 2, -h / 2, w, h);
  return c;
}
// Độ đậm mực: nền (làm mờ 51x51) trừ kênh tối nhất -> chịu được bóng đổ và mực xanh/đen
function inkMap(c){
  const W = c.width, H = c.height, d = c.getContext("2d").getImageData(0, 0, W, H).data;
  const mn = new Float32Array(W * H);
  for (let i = 0; i < W * H; i++) mn[i] = Math.min(d[i*4], d[i*4+1], d[i*4+2]);
  const S = new Float64Array((W + 1) * (H + 1));
  for (let y = 0; y < H; y++){ let r = 0; for (let x = 0; x < W; x++){ r += mn[y*W+x]; S[(y+1)*(W+1)+x+1] = S[y*(W+1)+x+1] + r; } }
  const R = 25, ink = new Float32Array(W * H);
  for (let y = 0; y < H; y++){
    const y0 = Math.max(0, y-R), y1 = Math.min(H, y+R+1);
    for (let x = 0; x < W; x++){
      const x0 = Math.max(0, x-R), x1 = Math.min(W, x+R+1);
      const bg = (S[y1*(W+1)+x1] - S[y0*(W+1)+x1] - S[y1*(W+1)+x0] + S[y0*(W+1)+x0]) / ((y1-y0)*(x1-x0));
      ink[y*W+x] = Math.max(0, bg - mn[y*W+x]);
    }
  }
  return {W, H, ink};
}
// Tách thành phần liên thông, bỏ vụn và vật chạm mép, gộp các nét chồng nhau theo chiều ngang thành 1 chữ số
function segment(m, th, crop){
  const {W, H, ink} = m, lab = new Int32Array(W * H), comps = [];
  const cx0 = crop ? crop.x0 : 0, cy0 = crop ? crop.y0 : 0, cx1 = crop ? crop.x1 : W, cy1 = crop ? crop.y1 : H;
  const minA = (cx1-cx0) * (cy1-cy0) * 5e-5, st = [];
  for (let y = cy0; y < cy1; y++) for (let x = cx0; x < cx1; x++){
    const i = y*W+x; if (lab[i] || ink[i] <= th) continue;
    const id = comps.length + 1; let a = 0, bx0 = x, bx1 = x, by0 = y, by1 = y, edge = false;
    lab[i] = id; st.push(i);
    while (st.length){
      const j = st.pop(), jx = j % W, jy = (j - jx) / W; a++;
      if (jx < bx0) bx0 = jx; if (jx > bx1) bx1 = jx; if (jy < by0) by0 = jy; if (jy > by1) by1 = jy;
      if (jx == cx0 || jy == cy0 || jx == cx1-1 || jy == cy1-1) edge = true;
      for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++){
        const nx = jx+dx, ny = jy+dy; if (nx < cx0 || ny < cy0 || nx >= cx1 || ny >= cy1) continue;
        const k = ny*W+nx; if (!lab[k] && ink[k] > th){ lab[k] = id; st.push(k); }
      }
    }
    comps.push({ids: [id], x0: bx0, x1: bx1+1, y0: by0, y1: by1+1, a, keep: a >= minA && !edge});
  }
  // nét lớn (cao >= 1/2 chiều cao trung vị) là 1 chữ số; nét nhỏ (gạch đầu số 5, mảnh rời...)
  // gộp vào chữ số trùng nhiều nhất theo chiều ngang
  const cs = comps.filter(c => c.keep), hs = cs.map(c => c.y1 - c.y0).sort((a, b) => a - b);
  const big = c => c.y1 - c.y0 >= 0.5 * (hs[Math.floor(hs.length / 2)] || 0);
  const g = cs.filter(big).map(c => ({...c, ids: [...c.ids]}));
  for (const c of cs){
    if (big(c) || !g.length) continue;
    const ov = q => Math.min(q.x1, c.x1) - Math.max(q.x0, c.x0) - Math.abs((q.x0+q.x1) - (c.x0+c.x1)) * 1e-3;
    const L = g.reduce((p, q) => ov(q) > ov(p) ? q : p);
    L.x0 = Math.min(L.x0, c.x0); L.x1 = Math.max(L.x1, c.x1); L.y0 = Math.min(L.y0, c.y0); L.y1 = Math.max(L.y1, c.y1);
    L.ids.push(...c.ids);
  }
  g.sort((p, q) => (p.x0+p.x1) - (q.x0+q.x1));
  return {lab, groups: g.slice(0, 20)};
}
// 1 chữ số -> 28x28: nét trắng trên nền đen, cạnh dài 20 px, dời tâm khối về giữa (giống MNIST)
function toMnist(m, lab, g, thick){
  const {W, ink} = m, w = g.x1-g.x0, h = g.y1-g.y0, ids = new Set(g.ids);
  let v = new Float32Array(w * h); const nz = [];
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++){
    const i = (g.y0+y)*W + g.x0+x; if (ids.has(lab[i])){ v[y*w+x] = ink[i]; nz.push(ink[i]); }
  }
  nz.sort((a, b) => a - b); const ref = nz[Math.floor(nz.length * 0.9)] || 1;
  for (let i = 0; i < v.length; i++) v[i] = Math.min(255, v[i] / ref * 255);
  const s = 20 / Math.max(w, h), k = Math.round(thick / s / 2);          // làm đậm nét trước khi thu nhỏ
  if (k > 0){
    const t = new Float32Array(w * h);
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++){
      let b = 0; for (let dy = -k; dy <= k; dy++) for (let dx = -k; dx <= k; dx++){
        const xx = x+dx, yy = y+dy; if (xx >= 0 && yy >= 0 && xx < w && yy < h && v[yy*w+xx] > b) b = v[yy*w+xx]; }
      t[y*w+x] = b;
    }
    v = t;
  }
  const tw = Math.max(1, Math.round(w * s)), thh = Math.max(1, Math.round(h * s)), small = new Float32Array(tw * thh);
  for (let ty = 0; ty < thh; ty++) for (let tx = 0; tx < tw; tx++){              // trung bình vùng
    const x0 = Math.floor(tx / s), x1 = Math.max(x0+1, Math.floor((tx+1) / s)), y0 = Math.floor(ty / s), y1 = Math.max(y0+1, Math.floor((ty+1) / s));
    let sum = 0, n = 0; for (let y = y0; y < Math.min(h, y1); y++) for (let x = x0; x < Math.min(w, x1); x++){ sum += v[y*w+x]; n++; }
    small[ty*tw+tx] = n ? sum / n : 0;
  }
  let mx = 0, sx = 0, sy = 0;
  for (let y = 0; y < thh; y++) for (let x = 0; x < tw; x++){ const q = small[y*tw+x]; mx += q; sx += q*x; sy += q*y; }
  const ox = Math.round(14 - (mx ? sx/mx : tw/2) - 0.5), oy = Math.round(14 - (mx ? sy/mx : thh/2) - 0.5);
  const out = new Uint8Array(784);
  for (let y = 0; y < thh; y++) for (let x = 0; x < tw; x++){
    const X = x+ox, Y = y+oy; if (X >= 0 && Y >= 0 && X < 28 && Y < 28) out[Y*28+X] = Math.min(255, Math.round(small[y*tw+x]));
  }
  return out;
}
const toHex = a => Array.from(a, v => v.toString(16).padStart(2, "0")).join("");
async function autoRotate(){
  // Đoán hướng xoay: chữ số phải xếp thành hàng ngang (dọc hay ngang), rồi giữa 2 hướng
  // ngược nhau chọn hướng mà mô hình int8 tự tin hơn (chênh điểm giữa số nhất và nhì).
  $("upInfo").textContent = "Đang dò hướng ảnh…";
  const th = +$("th").value, cand = [];
  for (let r = 0; r < 2; r++){
    UP.rot = r; const m = inkMap(rotated()), sg = segment(m, th, null);
    if (!sg.groups.length) continue;
    const tall = sg.groups.filter(g => g.y1-g.y0 >= 0.8*(g.x1-g.x0)).length / sg.groups.length;
    cand.push({r, sc: sg.groups.length * tall});
  }
  cand.sort((a, b) => b.sc - a.sc);
  const base = cand.length ? cand[0].r : 0;
  let best = base, bm = -Infinity;
  for (const r of [base, base + 2]){
    UP.rot = r; const m = inkMap(rotated()), sg = segment(m, th, null);
    const px = sg.groups.map(g => toHex(toMnist(m, sg.lab, g, +$("thick").value)));
    if (!px.length) continue;
    const res = await (await fetch("/api/du_doan", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({px})})).json();
    const mean = res.margin.reduce((a, b) => a + b, 0) / res.margin.length;
    if (mean > bm){ bm = mean; best = r; }
  }
  UP.rot = best; process();
}
let procT = null;
function process(){
  if (!UP.img) return;
  const c = rotated(), m = inkMap(c), sg = segment(m, +$("th").value, UP.crop);
  UP.canvas = c; UP.scale = 1;
  UP.digits = sg.groups.map(g => ({g, px: toMnist(m, sg.lab, g, +$("thick").value)}));
  drawView(); predict();
}
function drawView(){
  const cv = $("upCv"), c = UP.canvas; cv.hidden = false; $("drop").style.padding = "8px";
  cv.width = c.width; cv.height = c.height;
  const x = cv.getContext("2d"); x.drawImage(c, 0, 0);
  x.lineWidth = Math.max(2, c.width / 400); x.font = `bold ${Math.round(c.width/30)}px Segoe UI, sans-serif`;
  UP.digits.forEach((d, k) => { const g = d.g; x.strokeStyle = "#e81123"; x.strokeRect(g.x0-4, g.y0-4, g.x1-g.x0+8, g.y1-g.y0+8);
    x.fillStyle = "#e81123"; x.fillText(String(k+1), g.x0, g.y0 - 8); });
  if (UP.crop){ x.strokeStyle = "#2b579a"; x.setLineDash([10, 6]); x.strokeRect(UP.crop.x0, UP.crop.y0, UP.crop.x1-UP.crop.x0, UP.crop.y1-UP.crop.y0); x.setLineDash([]); }
  $("upInfo").textContent = `Tìm thấy ${UP.digits.length} chữ số. Ô đỏ là chỗ cắt, số là thứ tự gửi. Ảnh bị ngược hoặc nằm nghiêng thì bấm Xoay.`;
}
async function predict(){
  const r = await (await fetch("/api/du_doan", {method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({px: UP.digits.map(d => toHex(d.px))})})).json();
  UP.digits.forEach((d, k) => d.py = r.py[k]);
  drawDigits();
}
function drawDigits(){
  const box = $("digs"), labs = $("labs").value.replace(/\D/g, ""); box.innerHTML = "";
  UP.digits.forEach((d, k) => {
    const el = document.createElement("div"); el.className = "dg";
    const c = document.createElement("canvas"); c.width = c.height = 28;
    const ctx = c.getContext("2d"), im = ctx.createImageData(28, 28);
    for (let p = 0; p < 784; p++){ im.data[p*4] = im.data[p*4+1] = im.data[p*4+2] = d.px[p]; im.data[p*4+3] = 255; }
    ctx.putImageData(im, 0, 0); el.appendChild(c);
    const lb = labs[k], bad = lb !== undefined && +lb !== d.py;
    el.insertAdjacentHTML("beforeend", `<span>#${k+1} đoán <b class="${bad ? "x" : ""}">${d.py ?? "?"}</b></span>`);
    box.appendChild(el);
  });
}
$("rotL").onclick = () => { if (!UP.img) return; UP.rot = (UP.rot + 3) % 4; UP.crop = null; process(); };
$("rotR").onclick = () => { if (!UP.img) return; UP.rot = (UP.rot + 1) % 4; UP.crop = null; process(); };
$("noCrop").onclick = () => { UP.crop = null; process(); };
for (const id of ["th", "thick"]) $(id).oninput = () => { $(id + "V").textContent = $(id).value; clearTimeout(procT); procT = setTimeout(process, 200); };
$("labs").oninput = () => { $("labs").value = $("labs").value.replace(/\D/g, ""); drawDigits(); };
// Kéo chuột để chọn vùng
const pt = e => { const r = $("upCv").getBoundingClientRect(); return [Math.round((e.clientX - r.left) / r.width * $("upCv").width), Math.round((e.clientY - r.top) / r.height * $("upCv").height)]; };
$("upCv").onpointerdown = e => { UP.drag = pt(e); $("upCv").setPointerCapture(e.pointerId); };
$("upCv").onpointermove = e => { if (!UP.drag) return; const [x, y] = pt(e), [a, b] = UP.drag;
  UP.crop = {x0: Math.max(0, Math.min(a, x)), y0: Math.max(0, Math.min(b, y)), x1: Math.min(UP.canvas.width, Math.max(a, x)), y1: Math.min(UP.canvas.height, Math.max(b, y))}; drawView(); };
$("upCv").onpointerup = () => { UP.drag = null; if (UP.crop && (UP.crop.x1 - UP.crop.x0 < 20 || UP.crop.y1 - UP.crop.y0 < 20)) UP.crop = null; process(); };
$("saveSet").onclick = async () => {
  const labs = $("labs").value.replace(/\D/g, "");
  if (!UP.digits.length){ $("upInfo").textContent = "Chưa có chữ số nào để lưu."; return; }
  const items = UP.digits.map((d, k) => ({px: toHex(d.px), lab: labs[k] !== undefined ? +labs[k] : d.py}));
  const r = await (await fetch("/api/luu_bo", {method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ten: $("setName").value || ("Ảnh chụp " + (labs || "")), items})})).json();
  if (!r.ok){ $("upInfo").textContent = r.message; return; }
  SETS = []; cur = r.id; await loadSets(); await loadPlan();
  $("upInfo").textContent = "Đã lưu thành bộ mẫu. Bấm ▶ Chạy mô phỏng để gửi bộ này cho FPGA.";
};

let pollT = null;
async function poll(){
  clearTimeout(pollT);
  try { render(await (await fetch("/api/status")).json()); } catch (e) { $("stMsg").textContent = "Mất kết nối tới tinyml_web.py"; }
  pollT = setTimeout(poll, 700);
}
loadSets().then(loadPlan); poll();
</script>
</body>
</html>
"""


def main():
    global PORT
    for port in range(PORT, PORT + 20):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            PORT = port
            break
        except OSError:
            continue
    else:
        print("Khong mo duoc cong web")
        sys.exit(1)
    url = f"http://127.0.0.1:{PORT}"
    print(f"Trang web: {url}   (dong cua so nay de tat)")
    if "--no-browser" not in sys.argv:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
