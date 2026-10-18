// =============================================================================
// tinyml_pkg.sv — Khu lưu biến dùng chung của toàn bộ thiết kế
// -----------------------------------------------------------------------------
// Mọi module khác chỉ cần:   import tinyml_pkg::*;
// là dùng được các hằng số, kiểu dữ liệu và hàm bên dưới.
//
// Quy tắc:
//   * KHÔNG viết "số ma thuật" (784, 32, 8...) trong các module khác,
//     luôn lấy từ package này.
//   * Các giá trị trong mục 2 và 4 phải khớp với quy ước AI <-> phần cứng
//     (README mục 4). Khi bạn AI đổi mô hình, chỉ cần sửa ở đây.
//   * File này phải được biên dịch ĐẦU TIÊN (trước mọi module import nó).
// =============================================================================
package tinyml_pkg;

    // =========================================================================
    // 1. Hệ thống: xung nhịp và UART
    // =========================================================================
    localparam int CLK_FREQ_HZ  = 100_000_000;               // 100 MHz, cả Basys 3 và Nexys A7
    localparam int UART_BAUD    = 1_000_000;                 // 1 Mbaud, 8N1
    localparam int CLKS_PER_BIT = CLK_FREQ_HZ / UART_BAUD;   // = 100 chu kỳ / bit (chia hết, không sai số)
    localparam int GAP_TIMEOUT  = CLK_FREQ_HZ / 100;         // nghỉ 10 ms -> bắt đầu khung ảnh mới

    // =========================================================================
    // 2. Kích thước mạng nơ-ron: MLP 784-32-10
    // =========================================================================
    localparam int IMG_W   = 28;                 // ảnh 28 x 28
    localparam int IMG_H   = 28;
    localparam int N_IN    = IMG_W * IMG_H;      // 784 đầu vào  (lớp 1)
    localparam int N_HID   = 32;                 // 32 neuron ẩn (lớp 1 ra, lớp 2 vào)
    localparam int N_OUT   = 10;                 // 10 lớp ra (chữ số 0..9)

    // Số MAC chạy song song mỗi lớp (P). Bắt buộc: N_HID % PE1 == 0, N_OUT % PE2 == 0
    localparam int PE1     = 8;
    localparam int PE2     = 10;

    // =========================================================================
    // 3. Độ rộng bit của từng loại dữ liệu
    // =========================================================================
    localparam int PIXEL_W  = 8;    // pixel thô từ PC: uint8 0..255
    localparam int ACT_W    = 8;    // activation int8 (đầu vào sau tiền xử lý, lớp ẩn)
    localparam int WEIGHT_W = 8;    // trọng số int8
    localparam int BIAS_W   = 32;   // bias int32
    localparam int ACC_W    = 32;   // bộ cộng dồn int32 (cần tối thiểu 25 bit: 784*127*127 ~ 2^23.6)
    localparam int PROD_W   = ACT_W + WEIGHT_W;   // tích int8 x int8 = 16 bit

    // =========================================================================
    // 4. Lượng tử hoá (do bạn AI tính và cung cấp)
    // -------------------------------------------------------------------------
    //   h = clamp( (acc * M1 + 2^(SHIFT-1)) >>> SHIFT , 0 , ACT_MAX )
    //   M1 = round( s_w1 * s_x / s_h * 2^SHIFT )
    // =========================================================================
    localparam int SHIFT    = 24;
    localparam int M1       = 9525;               // GIÁ TRỊ MẪU — thay bằng số bạn AI xuất ra
    localparam int M_W      = 18;                 // độ rộng hệ số M1 (có dấu), M1 < 2^17
    localparam int ACT_MAX  = 127;                // giá trị int8 dương lớn nhất (ReLU + bão hoà)
    localparam int ACT_MIN  = 0;                  // ReLU: không cho giá trị âm
    localparam int RQ_W     = ACC_W + M_W;        // độ rộng tích acc * M1 = 50 bit

    // =========================================================================
    // 5. Bộ nhớ: kích thước và độ rộng địa chỉ
    // -------------------------------------------------------------------------
    // Bố cục ROM trọng số (quy ước chung):
    //   địa chỉ         = g * IN + i
    //   word[8k+7:8k]   = W[g*P + k][i]          (k = 0..P-1)
    // =========================================================================
    // Bộ đệm
    localparam int IMG_DEPTH   = N_IN;                      // bộ đệm ảnh: 784 x 8 bit
    localparam int HID_DEPTH   = N_HID;                     // bộ đệm lớp ẩn: 32 x 8 bit
    localparam int IMG_ADDR_W  = $clog2(IMG_DEPTH);         // 10 bit
    localparam int HID_ADDR_W  = $clog2(HID_DEPTH);         // 5 bit
    localparam int OUT_IDX_W   = $clog2(N_OUT);             // 4 bit (chỉ số chữ số 0..9)

    // ROM trọng số lớp 1: 3136 word x 64 bit
    localparam int W1_WORD_W   = PE1 * WEIGHT_W;
    localparam int W1_DEPTH    = (N_HID / PE1) * N_IN;
    localparam int W1_ADDR_W   = $clog2(W1_DEPTH);

    // ROM trọng số lớp 2: 32 word x 80 bit
    localparam int W2_WORD_W   = PE2 * WEIGHT_W;
    localparam int W2_DEPTH    = (N_OUT / PE2) * N_HID;
    localparam int W2_ADDR_W   = $clog2(W2_DEPTH);

    // ROM bias
    localparam int B1_DEPTH    = N_HID;
    localparam int B2_DEPTH    = N_OUT;

    // Trọng số / bias nhúng sẵn trong w1_rom.sv, w2_rom.sv, tinyml_bias_pkg.sv
    // (không còn dùng file .mem)

    // =========================================================================
    // 6. Kiểu dữ liệu dùng chung
    // =========================================================================
    typedef logic        [PIXEL_W-1:0]    pixel_t;     // pixel thô 0..255
    typedef logic signed [ACT_W-1:0]      act_t;       // activation int8
    typedef logic signed [WEIGHT_W-1:0]   weight_t;    // trọng số int8
    typedef logic signed [BIAS_W-1:0]     bias_t;      // bias int32
    typedef logic signed [ACC_W-1:0]      acc_t;       // bộ cộng dồn int32 / logit
    typedef logic signed [PROD_W-1:0]     prod_t;      // tích int8 x int8

    typedef logic [IMG_ADDR_W-1:0]        img_addr_t;
    typedef logic [HID_ADDR_W-1:0]        hid_addr_t;
    typedef logic [OUT_IDX_W-1:0]         digit_t;     // kết quả: chữ số 0..9

    typedef logic [W1_WORD_W-1:0]         w1_word_t;   // 1 word ROM lớp 1 = PE1 trọng số
    typedef logic [W1_ADDR_W-1:0]         w1_addr_t;
    typedef logic [W2_WORD_W-1:0]         w2_word_t;   // 1 word ROM lớp 2 = PE2 trọng số
    typedef logic [W2_ADDR_W-1:0]         w2_addr_t;

    // =========================================================================
    // 7. Hàm dùng chung (phải cho kết quả GIỐNG HỆT mô hình tham chiếu Python)
    // =========================================================================

    // Tiền xử lý: x_q = pixel >> 1  (0..127, vừa int8 dương)
    // Bit thấp nhất px[0] bị bỏ đi có chủ ý.
    /* verilator lint_off UNUSEDSIGNAL */
    function automatic act_t preprocess(input pixel_t px);
        return act_t'({1'b0, px[PIXEL_W-1:1]});
    endfunction
    /* verilator lint_on UNUSEDSIGNAL */

    // Lấy trọng số thứ k trong 1 word ROM (neuron nhỏ ở bit thấp)
    function automatic weight_t w1_slice(input w1_word_t word, input int k);
        return weight_t'(word[k*WEIGHT_W +: WEIGHT_W]);
    endfunction

    function automatic weight_t w2_slice(input w2_word_t word, input int k);
        return weight_t'(word[k*WEIGHT_W +: WEIGHT_W]);
    endfunction

    // Requant + ReLU cho lớp ẩn: int32 -> int8 trong [0, 127]
    function automatic act_t requant_relu(input acc_t acc);
        logic signed [RQ_W-1:0] prod;
        logic signed [RQ_W-1:0] shifted;
        prod    = RQ_W'(acc) * RQ_W'(M1);                                     // nhân có dấu
        shifted = (prod + (RQ_W'(1) <<< (SHIFT - 1))) >>> SHIFT;              // làm tròn + dịch số học
        if (shifted < RQ_W'(ACT_MIN))      return act_t'(ACT_MIN);
        else if (shifted > RQ_W'(ACT_MAX)) return act_t'(ACT_MAX);
        else                                return act_t'(shifted);
    endfunction

    // =========================================================================
    // Bias của 2 lớp, nhúng sẵn (sinh tự động từ gen/b1.mem, gen/b2.mem — đừng sửa tay)
    // =========================================================================
    // b1.mem
    function automatic bias_t b1_val(input int i);
        case (i)
            0: return 32'hfffff899;
            1: return 32'h00000ec7;
            2: return 32'h000000ed;
            3: return 32'hfffff7ce;
            4: return 32'h00000856;
            5: return 32'h00000587;
            6: return 32'h0000088c;
            7: return 32'hfffffcf1;
            8: return 32'h000009ca;
            9: return 32'hfffffe39;
            10: return 32'h00001700;
            11: return 32'h00001037;
            12: return 32'h00000d4b;
            13: return 32'hfffff952;
            14: return 32'h0000103b;
            15: return 32'h00000a35;
            16: return 32'h00000363;
            17: return 32'hfffff63d;
            18: return 32'h0000060f;
            19: return 32'h00000b80;
            20: return 32'h0000151e;
            21: return 32'hffffeef6;
            22: return 32'hfffff88f;
            23: return 32'h000003f6;
            24: return 32'h0000039f;
            25: return 32'hfffffee9;
            26: return 32'hfffff713;
            27: return 32'h000005f1;
            28: return 32'h00000d96;
            29: return 32'hfffff928;
            30: return 32'hfffff9f7;
            31: return 32'hfffffa28;
            default: return '0;
        endcase
    endfunction

    // b2.mem
    function automatic bias_t b2_val(input int i);
        case (i)
            0: return 32'hfffffead;
            1: return 32'h0000007f;
            2: return 32'hffffffd9;
            3: return 32'hffffffde;
            4: return 32'h000000cb;
            5: return 32'h000000c9;
            6: return 32'h00000019;
            7: return 32'hffffffda;
            8: return 32'hffffff6a;
            9: return 32'hfffffff7;
            default: return '0;
        endcase
    endfunction

endpackage
