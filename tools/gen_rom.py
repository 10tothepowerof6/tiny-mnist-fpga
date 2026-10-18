"""
gen_rom.py - Sinh lai trong so / bias / anh mau dang .sv tu cac file gen/*.mem

Dung khi ban AI train lai va xuat file .mem moi:
    1. Chep w1.mem, b1.mem, w2.mem, b2.mem, test_*.mem moi vao thu muc gen/
    2. Chay:  python tools/gen_rom.py
Script viet de ba phan sinh tu dong trong:
    rtl/fc_layer.sv     (2 module w1_rom, w2_rom o cuoi file)
    rtl/tinyml_pkg.sv   (ham b1_val, b2_val)
    tb/tb_tinyml_top.sv (package tb_data_pkg o dau file, N_ANH anh dau)
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN = os.path.join(ROOT, "gen")
N_ANH = 20


def rd(name):
    with open(os.path.join(GEN, name)) as f:
        return [l.strip() for l in f if l.strip()]


def rom(name, words, aw, dw, src):
    s = f"""// =============================================================================
// {name}.sv — ROM trọng số {src}, nhúng sẵn (không cần file .mem)
// -----------------------------------------------------------------------------
// File này được sinh tự động từ gen/{src}.mem. Đừng sửa tay:
// khi bên AI train lại thì sinh lại file này.
// Đọc trễ 1 chu kỳ, Vivado suy ra Block RAM (ROM).
// =============================================================================
module {name} (
    input  logic          clk,
    input  logic [{aw-1}:0]   addr,
    output logic [{dw-1}:0]  data
);
    (* rom_style = "block" *) logic [{dw-1}:0] q;
    always_ff @(posedge clk) begin
        case (addr)
"""
    for i, w in enumerate(words):
        s += f"            {aw}'d{i}: q <= {dw}'h{w};\n"
    return s + "            default: q <= '0;\n        endcase\n    end\n    assign data = q;\nendmodule\n"


def bias_func(name, vals, src):
    s = f"    // {src}.mem\n    function automatic bias_t {name}(input int i);\n        case (i)\n"
    for i, v in enumerate(vals):
        s += f"            {i}: return 32'h{v};\n"
    return s + "            default: return '0;\n        endcase\n    endfunction\n\n"


def tb_data(img, exp, lab, n_img):
    s = f"""// =============================================================================
// tb_data_pkg.sv — Dữ liệu mẫu cho testbench, nhúng sẵn (không cần file .mem)
// -----------------------------------------------------------------------------
// {n_img} ảnh đầu của tập test MNIST, sinh tự động từ gen/test_images.mem,
// test_expected.mem và test_labels.mem. Đừng sửa tay.
//   tb_image(n)    : 784 pixel của ảnh n, pixel 0 nằm ở 8 bit thấp nhất
//   tb_expected(n) : chữ số mà mô hình Python dự đoán
//   tb_label(n)    : nhãn thật
// =============================================================================
package tb_data_pkg;
    localparam int TB_N_IMG = {n_img};

    function automatic logic [784*8-1:0] tb_image(input int n);
        case (n)
"""
    for n in range(n_img):
        hexs = "".join(reversed(img[n * 784:(n + 1) * 784]))
        parts = [hexs[i:i + 112] for i in range(0, len(hexs), 112)]
        s += f"            {n}: return {{\n" + ",\n".join(
            f"                {len(p) * 4}'h{p}" for p in parts) + "\n            };\n"
    s += "            default: return '0;\n        endcase\n    endfunction\n\n"
    s += "    function automatic int tb_expected(input int n);\n        case (n)\n"
    for n in range(n_img):
        s += f"            {n}: return {int(exp[n * 11], 16)};\n"
    s += "            default: return -1;\n        endcase\n    endfunction\n\n"
    s += "    function automatic int tb_label(input int n);\n        case (n)\n"
    for n in range(n_img):
        s += f"            {n}: return {int(lab[n], 16)};\n"
    return s + "            default: return -1;\n        endcase\n    endfunction\nendpackage\n"


def replace_block(path, start, end, new_text):
    """Thay doan [start, end) trong file. start/end la (chuoi, lui_ve_dong_ngang?)."""
    with open(path, encoding="utf-8") as f:
        s = f.read()
    a = s.index(start)
    a = s.rfind("// =====", 0, a) if start.startswith("//") else s.rfind("\n", 0, a) + 1
    b = len(s) if end is None else s.index(end, a)
    if end == "endpackage":
        b = s.index("\n", b) + 1
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(s[:a] + new_text + s[b:])
    print("da cap nhat", os.path.relpath(path, ROOT))


if __name__ == "__main__":
    w1, w2, b1, b2 = rd("w1.mem"), rd("w2.mem"), rd("b1.mem"), rd("b2.mem")
    assert len(w1) == 3136 and len(w2) == 32 and len(b1) == 32 and len(b2) == 10, "kich thuoc .mem khong dung"

    # 1) 2 module ROM o cuoi fc_layer.sv
    replace_block(os.path.join(ROOT, "rtl", "fc_layer.sv"), "// w1_rom.sv —", None,
                  rom("w1_rom", w1, 12, 64, "w1") + "\n" + rom("w2_rom", w2, 5, 80, "w2"))

    # 2) Ham bias o cuoi tinyml_pkg.sv (ngay truoc endpackage)
    with open(os.path.join(ROOT, "rtl", "tinyml_pkg.sv"), encoding="utf-8") as f:
        s = f.read()
    a = s.index("    // b1.mem")
    b = s.rindex("endpackage")
    with open(os.path.join(ROOT, "rtl", "tinyml_pkg.sv"), "w", encoding="utf-8", newline="") as f:
        f.write(s[:a] + bias_func("b1_val", b1, "b1") + bias_func("b2_val", b2, "b2") + s[b:])
    print("da cap nhat rtl/tinyml_pkg.sv")

    # 3) Package anh mau o dau tb_tinyml_top.sv
    replace_block(os.path.join(ROOT, "tb", "tb_tinyml_top.sv"), "// tb_data_pkg.sv —", "endpackage",
                  tb_data(rd("test_images.mem"), rd("test_expected.mem"), rd("test_labels.mem"), N_ANH))
    print("Xong.")
