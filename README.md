# TinyML Accelerator trên FPGA

Bộ tăng tốc phần cứng cho mạng nơ-ron lượng tử hoá int8, nhận diện chữ số viết tay MNIST, thiết kế bằng SystemVerilog trên FPGA Xilinx Artix-7.

---

## 1. Mục tiêu

Thiết kế và demo một bộ tăng tốc phần cứng nhận ảnh chữ số viết tay 28×28 từ máy tính, chạy suy luận mạng nơ-ron int8 ngay trên FPGA và trả về chữ số dự đoán.

| Hạng mục | Nội dung |
|---|---|
| Bài toán | Nhận diện chữ số viết tay (MNIST, 10 lớp) |
| Mô hình | MLP 784-32-10, trọng số int8 |
| Board demo | **Digilent Basys 3** (Artix-7 XC7A35T) và **Digilent Nexys A7-100T** (Artix-7 XC7A100T) |
| Công cụ | Vivado (thiết kế phần cứng), Python (huấn luyện, lượng tử hoá) |
| Kịch bản demo | PC gửi ảnh qua UART → FPGA suy luận → kết quả hiện trên LED 7 đoạn và gửi về PC |
| Tiêu chí đạt | Độ chính xác ≥ 95 % · kết quả phần cứng khớp 100 % với mô hình tham chiếu · độ trễ ≤ 50 µs/ảnh tại 100 MHz |

---

## 2. Cấu trúc thư mục

```
tinyml-fpga/
├── README.md
├── ai/                          # Huấn luyện và lượng tử hoá (Python)
│   ├── train_quant_export.py    #   huấn luyện, lượng tử int8, xuất file ROM và test vector
│   ├── send_image.py            #   gửi ảnh xuống board qua UART, nhận kết quả
│   └── cpu_baseline.py          #   đo tốc độ CPU để so sánh
├── gen/                         # File trao đổi AI ↔ phần cứng (tự sinh, không sửa tay)
│   ├── w1.mem, w2.mem           #   trọng số int8
│   ├── b1.mem, b2.mem           #   bias int32
│   ├── w1.coe, w2.coe           #   trọng số cho IP Block Memory (dự phòng)
│   ├── quant_params.svh         #   kích thước mạng, số MAC song song, hệ số requant
│   ├── test_images.mem          #   ảnh kiểm thử
│   └── test_expected.mem        #   kết quả chuẩn từ mô hình tham chiếu
├── rtl/                         # Thiết kế phần cứng (SystemVerilog)
│   ├── mac_pe.sv                #   khối nhân - cộng dồn int8 × int8 → int32
│   ├── dense_layer.sv           #   lớp fully-connected: FSM, ROM BRAM, P MAC song song
│   ├── tinyml_accel.sv          #   lõi tăng tốc: bộ đệm, 2 lớp, argmax
│   ├── uart.sv                  #   UART RX/TX
│   ├── basys3_top.sv            #   top cho Basys 3
│   └── nexys_a7_top.sv          #   top cho Nexys A7-100T
├── tb/                          # Testbench
│   ├── tb_tinyml_accel.sv       #   so sánh từng bit với mô hình tham chiếu
│   └── tb_board_top.sv          #   kiểm thử toàn hệ thống qua UART
├── constr/                      # Ràng buộc chân
│   ├── basys3.xdc
│   └── nexys_a7_100t.xdc
├── scripts/
│   └── create_project.tcl       # Tạo project Vivado cho từng board
└── docs/                        # Tài liệu
    ├── De_cuong_tong_hop_TinyML_FPGA.pdf
    ├── PHAN_TICH.md
    └── So_do_cau_truc.pdf / .png
```

Luồng dữ liệu giữa các thư mục:

```
ai/  ──(xuất)──►  gen/  ──(nạp ROM, test vector)──►  rtl/ + tb/  ──(Vivado)──►  Basys 3 / Nexys A7-100T
```

---

## 3. Nhiệm vụ

| # | Nhiệm vụ | Kết quả cần có |
|---|---|---|
| 1 | Thống nhất quy ước giao tiếp AI ↔ phần cứng (mục 4) | Bảng quy ước được chốt |
| 2 | Huấn luyện mô hình MLP 784-32-10 trên MNIST | Mô hình float32, độ chính xác ≥ 96 % |
| 3 | Lượng tử hoá int8 và xây dựng mô hình tham chiếu số nguyên | Mô hình int8, mất ≤ 1 % độ chính xác |
| 4 | Xuất trọng số ra file ROM và sinh test vector | Các file trong `gen/` |
| 5 | Thiết kế khối MAC và lớp fully-connected | `mac_pe.sv`, `dense_layer.sv` |
| 6 | Ghép lõi tăng tốc: bộ đệm, 2 lớp, argmax | `tinyml_accel.sv` |
| 7 | Kiểm chứng bằng mô phỏng | Testbench khớp 100 % với mô hình tham chiếu |
| 8 | Giao tiếp board: UART, LED 7 đoạn, ràng buộc chân | Top và `.xdc` cho 2 board |
| 9 | Tổng hợp, đạt timing 100 MHz, nạp board | Bitstream chạy trên Basys 3 và Nexys A7-100T |
| 10 | Đo đạc và tối ưu | Báo cáo tài nguyên, độ trễ, công suất; so sánh với CPU |
| 11 | Demo và báo cáo | Demo nhận dạng trực tiếp trên board |

---

## 4. Quy ước giao tiếp giữa AI và phần cứng

Mọi thay đổi quy ước phải được cập nhật đồng thời ở mô hình tham chiếu Python và thiết kế RTL, sau đó chạy lại testbench cho đến khi đạt.

### 4.1. Dữ liệu đầu vào

| Thông số | Quy ước |
|---|---|
| Kích thước ảnh | 28 × 28 pixel, uint8 (0–255) |
| Thứ tự lưu | Theo hàng: `địa chỉ = hàng × 28 + cột` |
| Tiền xử lý | `x_q = pixel >> 1` (dải 0–127) |
| Thang đo đầu vào | `s_x = 1/127`; mô hình được huấn luyện trên `x_q / 127` |

### 4.2. Lượng tử hoá

| Thông số | Quy ước |
|---|---|
| Trọng số | int8 đối xứng, dải [−127, 127], một scale cho cả tensor: `W_q = round(W / s_w)`, `s_w = max\|W\| / 127` |
| Bias | int32: `b_q = round(b / (s_w · s_in))` |
| Bộ cộng dồn | int32 có dấu |
| Requant lớp ẩn | `h = clamp((acc · M1 + 2^23) >>> 24, 0, 127)`, trong đó `M1 = round(s_w1 · s_x / s_h · 2^24)` |
| Phép dịch | Dịch phải số học (`>>>`), làm tròn về phía âm vô cùng |
| Hàm kích hoạt | ReLU, gộp vào bước clamp |
| Lớp đầu ra | Logit int32, không requant |
| Kết quả | `argmax` của 10 logit; khi bằng nhau chọn chỉ số nhỏ nhất |

### 4.3. Định dạng file trao đổi

| File | Nội dung | Định dạng |
|---|---|---|
| `w1.mem`, `w2.mem` | Trọng số | Hex, một word mỗi dòng |
| `b1.mem`, `b2.mem` | Bias | Hex, một số int32 bù 2 mỗi dòng (8 ký tự) |
| `quant_params.svh` | `N_IN`, `N_HID`, `N_OUT`, `PE1`, `PE2`, `M1`, `SHIFT` | Hằng số SystemVerilog |
| `test_images.mem` | Ảnh kiểm thử | Hex, một pixel mỗi dòng |
| `test_expected.mem` | Kết quả chuẩn | Mỗi ảnh 11 dòng: dự đoán, logit 0–9 (int32) |

Bố cục bộ nhớ trọng số, với P là số MAC song song của lớp:

```
địa chỉ                = g × IN + i            (g: nhóm neuron, i: chỉ số đầu vào)
word[8k+7 : 8k]        = W_q[g × P + k][i]     (k = 0 … P−1, neuron nhỏ ở bit thấp)
```

### 4.4. Giao tiếp board

| Thông số | Quy ước |
|---|---|
| Xung nhịp | 100 MHz (cả hai board) |
| UART | 115200 baud, 8N1 |
| Khung dữ liệu vào | Đúng 784 byte mỗi ảnh; nghỉ quá 10 ms thì bắt đầu khung mới |
| Dữ liệu trả về | Một ký tự ASCII `'0'`–`'9'` |
| Hiển thị | Chữ số trên LED 7 đoạn, đèn LED tương ứng sáng |
| Reset | Nút giữa (BTNC) |
