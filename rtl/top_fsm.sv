// =============================================================================
// top_fsm.sv — Bộ điều khiển chính (FSM chính) của bộ tăng tốc TinyML
// -----------------------------------------------------------------------------
// Nhiệm vụ: điều phối thứ tự công việc, KHÔNG tự tính toán gì.
//
//   S_IDLE  : chờ khối nhận ảnh báo đã đủ 784 byte      (img_ready)
//   S_L1    : phát l1_start, chờ lớp 1 xong             (l1_done)
//   S_L2    : phát l2_start, chờ lớp 2 xong             (l2_done)
//   S_ARGMAX: phát argmax_start, chờ argmax xong        (argmax_done) -> chốt kết quả
//   S_SEND  : phát tx_start gửi 1 ký tự '0'..'9', chờ   (tx_done)
//   -> quay lại S_IDLE
//
// Giao thức start/done (dùng chung cho mọi khối con):
//   * xxx_start : xung 1 chu kỳ, FSM phát ra đúng lúc VÀO trạng thái tương ứng
//   * xxx_done  : xung 1 chu kỳ, khối con báo đã xong
//
// Mọi ngõ ra đều là thanh ghi (không có đường tổ hợp từ ngõ vào ra ngõ ra),
// giúp dễ đạt timing 100 MHz.
// =============================================================================
module top_fsm
    import tinyml_pkg::*;
(
    input  logic   clk,
    input  logic   rst,            // reset đồng bộ, mức cao (nút BTNC)

    // Khối nhận ảnh
    input  logic   img_ready,      // xung: đã ghi đủ N_IN pixel vào img_buf
    output logic   rx_enable,      // 1 = cho phép ghi ảnh mới vào img_buf

    // Lớp 1 (784 -> 32)
    output logic   l1_start,
    input  logic   l1_done,

    // Lớp 2 (32 -> 10)
    output logic   l2_start,
    input  logic   l2_done,

    // Argmax
    output logic   argmax_start,
    input  logic   argmax_done,
    input  digit_t argmax_digit,   // chữ số dự đoán, hợp lệ khi argmax_done = 1

    // UART TX
    output logic   tx_start,
    output logic [7:0] tx_data,    // ký tự ASCII '0'..'9'
    input  logic   tx_done,

    // Hiển thị và trạng thái
    output digit_t result,         // kết quả lần chạy gần nhất (cho LED 7 đoạn)
    output logic   result_valid,   // 1 = đã có ít nhất 1 kết quả
    output logic   busy            // 1 = đang xử lý một ảnh
);

    // -------------------------------------------------------------------------
    // Khai báo trạng thái
    // -------------------------------------------------------------------------
    typedef enum logic [2:0] {
        S_IDLE   = 3'd0,
        S_L1     = 3'd1,
        S_L2     = 3'd2,
        S_ARGMAX = 3'd3,
        S_SEND   = 3'd4
    } state_t;

    state_t state, state_n;

    // -------------------------------------------------------------------------
    // 1. Logic chuyển trạng thái (tổ hợp)
    // -------------------------------------------------------------------------
    always_comb begin
        state_n = state;
        unique case (state)
            S_IDLE  : if (img_ready)   state_n = S_L1;
            S_L1    : if (l1_done)     state_n = S_L2;
            S_L2    : if (l2_done)     state_n = S_ARGMAX;
            S_ARGMAX: if (argmax_done) state_n = S_SEND;
            S_SEND  : if (tx_done)     state_n = S_IDLE;
            default :                  state_n = S_IDLE;
        endcase
    end

    // -------------------------------------------------------------------------
    // 2. Thanh ghi trạng thái
    // -------------------------------------------------------------------------
    always_ff @(posedge clk) begin
        if (rst) state <= S_IDLE;
        else     state <= state_n;
    end

    // -------------------------------------------------------------------------
    // 3. Xung start: phát 1 chu kỳ đúng lúc vừa chuyển sang trạng thái mới
    // -------------------------------------------------------------------------
    wire entering = (state_n != state);

    always_ff @(posedge clk) begin
        if (rst) begin
            l1_start     <= 1'b0;
            l2_start     <= 1'b0;
            argmax_start <= 1'b0;
            tx_start     <= 1'b0;
        end else begin
            l1_start     <= entering && (state_n == S_L1);
            l2_start     <= entering && (state_n == S_L2);
            argmax_start <= entering && (state_n == S_ARGMAX);
            tx_start     <= entering && (state_n == S_SEND);
        end
    end

    // -------------------------------------------------------------------------
    // 4. Chốt kết quả argmax (giữ nguyên cho LED cho tới ảnh sau)
    // -------------------------------------------------------------------------
    always_ff @(posedge clk) begin
        if (rst) begin
            result       <= '0;
            result_valid <= 1'b0;
        end else if (state == S_ARGMAX && argmax_done) begin
            result       <= argmax_digit;
            result_valid <= 1'b1;
        end
    end

    // Ký tự ASCII gửi về PC: '0' = 8'h30
    assign tx_data = 8'h30 + {4'b0, result};

    // -------------------------------------------------------------------------
    // 5. Ngõ ra trạng thái
    // -------------------------------------------------------------------------
    // Chỉ cho ghi ảnh mới khi rảnh, tránh ghi đè img_buf lúc lớp 1 đang đọc.
    assign rx_enable = (state == S_IDLE);
    assign busy      = (state != S_IDLE);

endmodule
