# Phân tích dự án TinyML Accelerator trên FPGA

Số liệu nào **đã đo** (chạy Python, mô phỏng Icarus) thì ghi rõ là đã đo. Còn lại là **ước tính** tính từ kiến trúc, cần xác nhận bằng báo cáo của Vivado/Quartus.

## 1. Kết luận nhanh

- **Khả thi**, và vừa sức 2 sinh viên trong khoảng 8 tuần, với điều kiện chọn **MNIST + MLP trước**. Toàn bộ trọng số (25.408 tham số int8, khoảng 200 kbit) nằm gọn trong BRAM trên chip, không cần DDR, không cần CPU mềm.
- Nên chọn **Basys 3**: có sẵn USB-UART, Vivado quen thuộc, nhiều DSP. DE10-Lite cũng làm được nhưng phải thêm module USB-UART rời.
- **Keyword spotting khó hơn hẳn**: cần micro (cả hai board đều không có, phải mua Pmod MIC3 hoặc module I2S), cần khối trích đặc trưng MFCC (FFT, mel filter, log) trên FPGA hoặc trên PC. Chỉ nên để làm phần mở rộng.
- Rủi ro lớn nhất không nằm ở phép tính mà ở **hai bạn hiểu khác nhau về cách lượng tử**. Rủi ro này đã được chặn bằng một mô hình tham chiếu int8 bit-exact và testbench so từng bit (xem mục 5).

## 2. So sánh 2 board

| | Basys 3 (XC7A35T) | DE10-Lite (10M50DAF484) |
|---|---|---|
| Logic | 20.800 LUT6, 41.600 FF | 49.760 LE (LUT4) |
| RAM trên chip | 50 BRAM36 = 1.800 kbit | 182 M9K = 1.638 kbit |
| Bộ nhân | 90 DSP48E1 (25×18) | 144 bộ nhân 18×18 (mỗi cái tách được 2 bộ 9×9) |
| Clock board | 100 MHz | 50 MHz |
| Kết nối PC | USB-UART có sẵn | Không có, phải dùng GPIO + module USB-UART |
| Công cụ | Vivado (bản free hỗ trợ) | Quartus Prime Lite |
| **Đánh giá** | **Chọn làm mặc định** | Được, thêm việc phần I/O |

**Nexys A7-100T** (XC7A100T, Vivado, 100 MHz, có USB-UART) dùng chung RTL với Basys 3, chỉ khác top và file chân. Chip lớn hơn khoảng 3 lần (63.400 LUT, 135 BRAM36 = 4.860 kbit, 240 DSP), đủ chỗ cho mạng lớn hơn (784-128-10) hoặc P = 32.

## 3. Chọn mô hình

| Phương án | Tham số | Bộ nhớ int8 | Độ chính xác MNIST | Độ phức tạp phần cứng |
|---|---|---|---|---|
| **MLP 784-32-10 (đang dùng)** | 25.408 | 199 kbit | **96,57 % (đã đo, int8)** | Thấp: chỉ cần 1 khối FC dùng lại |
| MLP 784-64-10 | ~51 k | ~400 kbit | khoảng 97,5 % (ước tính) | Như trên, chỉ đổi tham số |
| MLP 784-128-10 | ~102 k | ~800 kbit | khoảng 98 % (ước tính) | Như trên; DE10-Lite bắt đầu chật |
| CNN nhỏ (2 conv + FC) | 10–30 k | < 250 kbit | khoảng 98,5–99 % | Cao: line buffer, cửa sổ 3×3, pooling, điều khiển phức tạp |

Lý do chọn MLP 784-32-10 làm baseline: cả phần cứng chỉ cần **một** module `dense_layer` dùng lại cho 2 lớp, nên có hệ thống chạy được trên board sớm. Sau đó mới tăng kích thước lớp ẩn (chỉ đổi tham số) hoặc lên CNN để tăng độ chính xác.

## 4. Ước tính tài nguyên (cấu hình mặc định PE1 = 8, PE2 = 10, Basys 3)

| Tài nguyên | Ước tính | Có trên Basys 3 | Tỉ lệ |
|---|---|---|---|
| DSP48E1 | khoảng 22 (8 + 10 MAC, khoảng 4 cho requant 32×32) | 90 | khoảng 25 % |
| BRAM36 | khoảng 8 (ROM w1: 3.136 × 64 bit cần ~7; bộ đệm ảnh ~1) | 50 | khoảng 16 % |
| LUT | khoảng 1–2 nghìn (FSM, mux accumulator, UART, 7 đoạn) | 20.800 | < 10 % |
| FF | khoảng 1–2 nghìn (18 accumulator 32 bit + pipeline) | 41.600 | < 5 % |

Kết luận: tài nguyên dư nhiều, nên có thể tăng P lên 32 (thêm DSP) để giảm độ trễ lớp 1 xuống còn khoảng 1/4.

**Độ rộng bit.** Giá trị lớn nhất của accumulator lớp 1 là 784 × 127 × 127 ≈ 12,6 triệu, cần 25 bit có dấu. int32 dư an toàn, và script Python có `assert` để kiểm tra.

## 5. Hiệu năng

| Chỉ số | Giá trị |
|---|---|
| Chu kỳ / ảnh (đã đo trong mô phỏng) | 3.227 (lớp 1 khoảng 3.190, lớp 2 khoảng 45) |
| Độ trễ @ 100 MHz | khoảng 32 µs, tức khoảng 31.000 ảnh/giây nếu chỉ tính phần tính toán |
| Phép MAC / ảnh | 25.408 |
| Thời gian gửi 1 ảnh qua UART 115.200 baud | 784 × 10 bit / 115.200 ≈ **68 ms** |

**Điểm nghẽn thực sự là UART chứ không phải bộ tăng tốc**: gửi ảnh chậm hơn tính toán khoảng 2.000 lần. Khi demo hoặc viết báo cáo, nên:
1. Thêm bộ đếm chu kỳ trong phần cứng và gửi về PC để đo **thời gian tính toán thật**.
2. Hoặc nạp sẵn vài trăm ảnh test vào BRAM rồi chạy liên tục để đo throughput.
3. Nếu muốn nhanh hơn, tăng baud (chip FTDI trên Basys 3 chạy được vài Mbaud) và nhớ sửa `CLKS_PER_BIT`.

So sánh nên đưa vào báo cáo: cùng mô hình chạy bằng numpy trên laptop, hoặc trên MicroBlaze (nếu có thời gian), về độ trễ, ảnh/giây, công suất (Vivado Power Report), và ảnh/giây/W.

## 6. Các lựa chọn thiết kế và lý do

| Quyết định | Lựa chọn | Lý do / phương án khác |
|---|---|---|
| Kiểu luồng dữ liệu | Output-stationary: P neuron giữ accumulator, quét hết đầu vào | Mỗi chu kỳ chỉ đọc 1 byte đầu vào dùng chung cho P MAC; ROM chỉ cần 1 cổng đọc rộng P×8 bit. |
| Song song | Tham số P (ước của số neuron) | Một núm vặn duy nhất để đánh đổi DSP/BRAM với tốc độ, rất hợp để vẽ biểu đồ trade-off cho báo cáo. |
| Lượng tử | int8 đối xứng, per-tensor, không zero-point | Phần cứng đơn giản nhất (không phải trừ zero-point), mất 0,06 % độ chính xác (đã đo). Per-channel tốt hơn nhưng cần 1 hệ số M cho mỗi neuron. |
| Đầu vào | `pixel >> 1` | Pixel 0..255 không vừa int8 có dấu; dịch 1 bit gần như không làm mất thông tin, và phần cứng không cần thêm gì. |
| Requant | Nhân số nguyên M rồi dịch phải SHIFT = 24 | Không cần dấu phẩy động; cùng công thức mà TFLite Micro dùng. |
| Hàm kích hoạt | ReLU gộp vào bước clamp [0, 127] | Không tốn thêm phần cứng. |
| Lớp cuối | Giữ logit int32, chỉ lấy argmax | Không cần softmax trên phần cứng. |
| Khởi tạo ROM | `$readmemh` + file `.mem` | Chạy được cả trên Vivado, Quartus và Icarus; `.coe` để dự phòng nếu muốn dùng IP Block Memory. |
| Kiểm chứng | Python là golden model, testbench so bit-exact cả pred và 10 logit | Phát hiện ngay khi một bên đổi quy ước. Đã thử làm sai M1 một chút, testbench báo 49 sai khác (testbench có tác dụng thật). |

## 7. Rủi ro và cách giảm

| Rủi ro | Mức độ | Cách giảm |
|---|---|---|
| Hai bạn lệch quy ước lượng tử (làm tròn, dịch số học, thứ tự bit) | Cao | Hợp đồng trong README mục 3, cộng `run_sim.sh` phải PASS trước mỗi lần merge. |
| Vivado không suy ra BRAM (dùng LUT thay vào, tốn tài nguyên) | Trung bình | Kiểm tra Utilization Report; giữ kiểu đọc đồng bộ như code mẫu; dự phòng bằng IP Block Memory + `.coe`. |
| Không đạt timing 100 MHz | Thấp–TB | Phép nhân requant đã có pipeline; nếu vẫn trượt thì thêm 1 tầng register sau mux accumulator, hoặc hạ clock xuống 50 MHz. |
| Khung UART bị lệch (mất byte) | Trung bình | Đã có timeout 10 ms để reset bộ đếm; có thể thêm byte đánh dấu đầu khung hoặc checksum. |
| Ảnh vẽ tay thật cho kết quả kém hơn ảnh MNIST | Trung bình | Tiền xử lý giống MNIST (căn giữa theo trọng tâm, chuẩn hoá 20×20 trong khung 28×28) ở phía PC. |
| Ôm đồm (KWS, CNN) khi baseline chưa chạy | Cao | Cột mốc tuần 2: baseline phải chạy trên board rồi mới mở rộng. |
| Phần mềm: PyTorch hoặc Vivado cài đặt lâu | Thấp | Script train chỉ cần numpy. |

## 8. Hướng mở rộng để bài nổi bật hơn

1. **Zero-skipping**: khoảng 82 % pixel MNIST (sau `>>1`) bằng 0 (đã đo trên 200 ảnh test). Bỏ qua chúng có thể giảm số chu kỳ lớp 1 vài lần.
2. **2 MAC int8 trên 1 DSP48** (kỹ thuật packing của Xilinx): gấp đôi throughput mà không tốn thêm DSP.
3. **Trọng số 4 bit / nhị phân**: giảm một nửa BRAM, phân tích độ chính xác giảm bao nhiêu.
4. **Pipeline 2 lớp** để tăng throughput khi chạy nhiều ảnh liên tục.
5. **CNN** hoặc **KWS** khi phần trên đã xong.
