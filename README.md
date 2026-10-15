# TinyML Accelerator trên FPGA: nhận diện chữ số MNIST

> Giai đoạn hiện tại: **lập kế hoạch**. Repo mới có kế hoạch và tài liệu, chưa có code.

Nhóm 2 người tự thiết kế một bộ tăng tốc phần cứng trên FPGA, chạy mạng nơ-ron int8 nhỏ để nhận diện chữ số viết tay (MNIST). Công cụ dùng là **Vivado**.

## 1. Board

| Board | Chip | LUT | BRAM | DSP | Clock | Vai trò |
|---|---|---|---|---|---|---|
| Digilent **Basys 3** | XC7A35T-1CPG236C | 20.800 | 50 × 36 Kb | 90 | 100 MHz | board chính |
| Digilent **Nexys A7-100T** | XC7A100T-1CSG324C | 63.400 | 135 × 36 Kb | 240 | 100 MHz | chạy cấu hình lớn hơn (P = 32, mạng 784-128-10) |

Hai board sẽ dùng chung RTL, chỉ khác file top và file gán chân (`.xdc`). Cả hai đều có sẵn USB-UART để nhận ảnh từ PC.

## 2. Mục tiêu

**Tổng quát:** tự thiết kế bằng SystemVerilog (không dùng HLS) một bộ tăng tốc int8 trên FPGA giá rẻ. Bộ tăng tốc phải chạy nhanh hơn nhiều lần so với bộ xử lý nhúng cùng tầm giá, với độ chính xác gần bằng mô hình float32.

| Mã | Mục tiêu | Mức cơ bản | Mức mở rộng |
|---|---|---|---|
| MT1 | Độ chính xác int8 (10.000 ảnh test) | ≥ 95 %, mất ≤ 1 % so với float32 | ≥ 97,5 % |
| MT2 | Phần cứng khớp mô hình Python | 100 % từng bit | — |
| MT3 | Độ trễ mỗi ảnh @ 100 MHz | ≤ 50 µs | ≤ 10 µs |
| MT4 | So với CPU mềm MicroBlaze trên cùng chip | nhanh hơn ≥ 20 lần | ≥ 100 lần |
| MT5 | Tài nguyên | ≤ 50 % DSP và BRAM | bảng đánh đổi theo P |
| MT6 | Năng lượng mỗi ảnh | có số đo từ Vivado Power Report | so với CPU và vi điều khiển |
| MT7 | Demo | nhận dạng ảnh gửi từ PC qua UART | ảnh vẽ tay thật |

## 3. Phân công

| Bạn AI (Python) | Bạn vi mạch (SystemVerilog, Vivado) |
|---|---|
| Huấn luyện MLP 784-32-10 trên MNIST | Thiết kế khối MAC int8 × int8 → int32 |
| Lượng tử hoá float32 → int8, chọn scale | Thiết kế lớp fully-connected: FSM, ROM BRAM, P MAC song song |
| Viết mô hình tham chiếu int8 (đáp án chuẩn) | Ghép 2 lớp, argmax, UART, LED 7 đoạn |
| Xuất trọng số ra file ROM (`.mem`, `.coe`) + test vector | Testbench so khớp từng bit với Python |
| Công cụ gửi ảnh từ PC, đo CPU để so sánh | Tổng hợp Vivado, đo tài nguyên/timing/công suất, nạp board |

## 4. Kiến trúc dự kiến

```
PC ─UART─► bộ đệm ảnh 784 B ─► FC1 784→32 (P MAC) + ReLU ─► bộ đệm ẩn 32 B
                                   ▲ ROM trọng số (BRAM)              │
PC ◄─UART─ LED 7 đoạn ◄─ argmax ◄─ FC2 32→10 ◄─────────────────────────┘
```

- Một module lớp fully-connected dùng lại cho cả 2 lớp. Mỗi lớp tính P neuron song song, quét lần lượt các đầu vào. Số chu kỳ ước tính ≈ (OUT/P)·(IN+P+3).
- Trọng số nằm trong BRAM trên chip (khoảng 200 kbit), không cần DDR hay CPU mềm.
- Toàn bộ phép tính dùng số nguyên, không có dấu phẩy động trên FPGA.

## 5. Quy ước chung giữa 2 bạn (chốt trước khi code)

| Mục | Quy ước |
|---|---|
| Đầu vào | pixel 0..255, thứ tự hàng trước; `x_q = pixel >> 1` (0..127) |
| Trọng số | int8 đối xứng, một scale cho cả tensor: `W_q = round(W / s_w)`, `s_w = max\|W\| / 127` |
| Bias | int32: `b_q = round(b / (s_w · s_in))` |
| Requant lớp ẩn | `h = clamp((acc·M1 + 2^23) >>> 24, 0, 127)`, `>>>` là dịch phải số học |
| Lớp ra | logit int32, `pred = argmax`; nếu bằng nhau thì lấy chỉ số nhỏ hơn |
| Bố cục ROM | `addr = g·IN + i`; `word[8k+7:8k] = W_q[g·P+k][i]` |
| Test vector | mỗi ảnh: pred + 10 logit, do mô hình Python sinh ra |

Mỗi khi đổi một quy ước, phải sửa cả Python lẫn RTL và chạy lại testbench cho tới khi PASS.

## 6. Kế hoạch 8 tuần

| Tuần | Bạn AI | Bạn vi mạch | Xong khi |
|---|---|---|---|
| 1 | Train + lượng tử, mô hình tham chiếu int8 | MAC + lớp FC, testbench đơn vị | Hai bên chạy được phần của mình |
| 2 | Xuất ROM + test vector, công cụ gửi ảnh | Ghép lõi, UART, Vivado trên Basys 3 | **Board nhận đúng ảnh test qua UART** |
| 3–4 | Thử lớp ẩn 16/64/128, huấn luyện có lượng tử (QAT) | Quét P = 4/8/16/32, chạy cấu hình lớn trên Nexys A7 | Bảng độ chính xác và bảng tài nguyên |
| 5–6 | Scale riêng từng neuron hoặc trọng số 4 bit, đo CPU | Bỏ qua pixel 0, 2 MAC mỗi DSP, đo MicroBlaze | Số đo trước và sau tối ưu |
| 7 | (Tuỳ chọn) CNN hoặc keyword spotting | (Tuỳ chọn) khối tích chập | Chỉ làm khi tuần 2–6 xong |
| 8 | Báo cáo, slide | Báo cáo, demo | **Demo** |

## 7. Đối tượng so sánh

| Nền tảng | Độ trễ mỗi ảnh | Loại số liệu |
|---|---|---|
| CPU mềm MicroBlaze trên Basys 3 @ 100 MHz | ~2–2,5 ms | ước tính, sẽ đo ở tuần 6 |
| Vi điều khiển Cortex-M4 @ 84 MHz | ~0,3–1,5 ms | ước tính |
| CPU máy tính (Xeon 2,8 GHz, C, 1 luồng) | ~5 µs | đo thử |
| [FINN](https://arxiv.org/pdf/1612.07119) SFC, ZC706 (trọng số 1 bit) | 0,31–240 µs | công bố |
| [SNN 784-128-10 trên Basys 3](https://arxiv.org/pdf/2507.07284) | 520 µs, 0,381 W | công bố |

## 8. Rủi ro chính

| Rủi ro | Cách giảm |
|---|---|
| Hai bạn hiểu khác nhau về cách lượng tử | Chốt quy ước ở mục 5, testbench so từng bit |
| Vivado không suy ra BRAM, hoặc không đạt timing 100 MHz | Kiểm tra báo cáo sớm (tuần 2), thêm tầng register, dùng IP Block Memory |
| UART chậm (khoảng 68 ms mỗi ảnh) che mất tốc độ phần cứng | Đếm chu kỳ trong phần cứng để đo |
| Ôm đồm CNN/KWS khi bản cơ bản chưa chạy | Mốc tuần 2 bắt buộc phải chạy trên board |

## 9. Cấu trúc repo dự kiến

```
ai/       Python: train, lượng tử, xuất ROM, gửi ảnh, đo CPU       (bạn AI)
gen/      File tự sinh: trọng số .mem/.coe, tham số, test vector   (bạn AI tạo, bạn vi mạch dùng)
rtl/      SystemVerilog: MAC, lớp FC, lõi, UART, top từng board   (bạn vi mạch)
tb/       Testbench                                               (bạn vi mạch)
constr/   File chân: basys3.xdc, nexys_a7_100t.xdc                (bạn vi mạch)
scripts/  Script Tcl tạo project Vivado
docs/     Đề cương (PDF), phân tích
```

Chi tiết: [docs/De_cuong_TinyML_FPGA.pdf](docs/De_cuong_TinyML_FPGA.pdf), [docs/PHAN_TICH.md](docs/PHAN_TICH.md).
