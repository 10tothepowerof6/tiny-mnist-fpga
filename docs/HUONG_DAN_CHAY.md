# Hướng dẫn chạy phần cứng

Đây là bản tổng hợp của bộ tăng tốc TinyML MNIST (MLP int8 784-32-10) chạy trên FPGA (Nexys A7-100T / Basys 3).

## Máy mới (người làm chung)

1. Lấy thư mục này về (clone repo), Vivado 2025.x, Python 3.
2. Mở Vivado, trong Tcl Console gõ `source <thư mục repo>/tools/tao_project.tcl`. Script tạo project `TINY_MNIST` nằm cạnh thư mục repo (part xc7a100tcsg324-1, top `nexys_a7_top`, sim top `tb_tinyml_top`).
3. Chạy trang web: bấm đúp `pc\web.bat`. Nếu Vivado không cài ở `D:\VHDL\AMD_VIVADO\2025.2` thì sửa biến `VIVADO` đầu file `pc/tinyml_web.py` (trang cũng tự dò `C:\Xilinx` và `C:\AMDDesignTools`).

## Thư mục

| Thư mục | Nội dung |
|---|---|
| `rtl/` | Code thiết kế (đưa vào **Design Sources**) |
| `tb/`  | Testbench (đưa vào **Simulation Sources**) |
| `constr/` | `nexys_a7_100t.xdc`: chân Nexys A7-100T (đưa vào **Constraints**, top là `nexys_a7_top`) |
| `pc/`  | Trang web Python (`tinyml_web.py`, `web.bat`) chạy mô phỏng và xem kết quả |
| `gen/` | File .mem gốc do bên AI xuất ra (trọng số, bias, ảnh test) |
| `tools/` | `gen_rom.py`: sinh lại ROM từ `gen/*.mem` |
| `docs/` | Các file PDF giải thích |

## rtl/: thứ tự các khối

| File | Chức năng |
|---|---|
| `tinyml_pkg.sv` | Hằng số, kiểu dữ liệu, hàm dùng chung và bias b1/b2 (nhúng sẵn) |
| `uart_rx.sv`, `uart_tx.sv` | UART 8N1 tốc độ 1 Mbaud |
| `img_rx.sv` | Nhận 784 byte ảnh, tiền xử lý (pixel >> 1) rồi ghi vào img_buf |
| `buf_ram.sv` | RAM đệm (img_buf, hid_buf) |
| `mac_pe.sv` | 1 khối nhân-cộng int8 x int8 -> int32 |
| `fc_layer.sv` | Lớp fully-connected. **Cuối file có 2 ROM `w1_rom`, `w2_rom`** |
| `argmax.sv` | Chọn chữ số có logit lớn nhất |
| `top_fsm.sv` | FSM chính: IDLE -> L1 -> L2 -> ARGMAX -> SEND |
| `tinyml_core.sv` | img_buf -> L1 -> hid_buf -> L2 -> argmax |
| `tinyml_system.sv` | uart_rx + img_rx + core + top_fsm + uart_tx |
| `seg7.sv` | LED 7 đoạn |
| `tinyml_top.sv` | **Top chung, không gắn board** (dùng khi chưa có board) |
| `nexys_a7_top.sv`, `basys3_top.sv` | Top cho từng board (khi nạp board thật) |

Không cần file .mem nào: trọng số và bias đã nằm sẵn trong code.

## tb/

| File | Kiểm gì | Cần .mem? |
|---|---|---|
| `tb_tinyml_top.sv` | **Testbench chính.** Gửi 20 ảnh nhúng sẵn qua UART (hoặc bộ mẫu do trang web gửi qua `+ANH_VAO=<file>`), kiểm kết quả, vẽ ảnh và LED 7 đoạn ra Tcl Console, ghi `ket_qua_sim.txt` | Không |
| `tb_uart.sv` | tx -> rx loopback | Không |
| `tb_uart_rx.sv` | 20 khung UART mẫu (lệch baud, nhiễu, sai stop) | Không |
| `tb_img_rx.sv` | Nhận ảnh, bỏ khung dở, timeout | Không |
| `tb_tinyml_core.sv` | 200 ảnh, so bit-exact với Python | Có (`gen/test_*.mem`) |
| `tb_board_top.sv` | Toàn hệ thống qua chân board Basys 3 | Có (`gen/test_*.mem`) |

## Chạy mô phỏng

**Cách 1: trong Vivado.** Set top sim là `tb_tinyml_top`, bấm **Run Behavioral Simulation**, rồi gõ `run all`.
Kết quả hiện trong Tcl Console, có ảnh 28x28, LED 7 đoạn ảo và dòng PASS/FAIL.

**Cách 2: trang web (nên dùng)**
1. Đóng Vivado GUI.
2. Bấm đúp `pc\web.bat`. Trình duyệt sẽ tự mở `http://127.0.0.1:8765`.
3. Chọn bộ mẫu thử trên thanh ribbon: 20 ảnh có sẵn, số điện thoại, ngày tháng, dãy 0 đến 9, có ảnh khó, 20 ảnh ngẫu nhiên, hoặc tự gõ tối đa 20 chữ số (trang tự chọn ảnh viết tay cho từng chữ số trong 200 ảnh test).
4. Bấm **▶ Chạy mô phỏng**. Trang ghi bộ mẫu ra `pc/_tam/anh_vao.txt`, gọi Vivado chạy ngầm `tb_tinyml_top`, rồi mỗi byte ASCII FPGA gửi về qua UART được gõ lên một trang giấy trắng giống Word, kèm mã hex, bảng chi tiết (ký tự, hex, dec, nhị phân, Python, nhãn thật) và thanh trạng thái Khớp Python / Đúng nhãn. Nút **Lưu .txt** lưu chuỗi ký tự, **In** để in trang.
   Gạch sóng đỏ dưới ký tự nghĩa là AI đoán khác nhãn thật (lỗi mô hình, phần cứng vẫn đúng); chữ đỏ nghĩa là FPGA khác Python (lỗi phần cứng).
5. **Mẫu thử từ ảnh tự chụp:** bấm **📷 Tải ảnh**, chọn ảnh giấy có viết số. Trang tự xoay ảnh, cắt từng chữ số và đổi thành ảnh 28x28 kiểu MNIST (nét trắng nền đen). Nếu ảnh bị ngược thì bấm Xoay; kéo chuột trên ảnh để chỉ chọn vùng có chữ số. Gõ các chữ số đúng vào ô nhãn, đặt tên rồi bấm **Lưu thành bộ mẫu**. Bộ mẫu được lưu trong `pc/mau_tu_chup/*.json` và hiện thành nút 📷 trong danh sách bộ mẫu. Số "Python đoán" được tính bằng mô hình int8 giống hệt phần cứng (đã kiểm khớp 200/200 ảnh test).
6. Muốn tắt trang thì đóng cửa sổ đen (cửa sổ server).

**Cách 3: cửa sổ Tkinter đơn giản.** Bấm đúp `pc\chay_viewer.bat`.

Đường dẫn Vivado được khai báo ở biến `VIVADO` đầu file `pc/tinyml_web.py` (hoặc `pc/tinyml_viewer.py`). Nếu cài Vivado chỗ khác thì sửa ở đó.

## Khi bên AI train lại

1. Chép các file `.mem` mới vào `gen/`.
2. Chạy `python tools\gen_rom.py`. Script viết lại phần ROM trong `fc_layer.sv`, phần bias trong `tinyml_pkg.sv` và phần ảnh mẫu trong `tb_tinyml_top.sv`.
3. Chạy lại `tb_tinyml_top` để kiểm tra.

## Thông số đã đo (mô phỏng)

- 200/200 ảnh khớp bit-exact với Python, 198/200 ảnh đúng nhãn thật.
- Tính 1 ảnh mất 3231 chu kỳ, tức 32,3 µs ở 100 MHz.
- Nhận 1 ảnh qua UART 1 Mbaud mất khoảng 7,8 ms.
