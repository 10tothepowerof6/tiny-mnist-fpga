// =============================================================================
// tinyml_system.sv — Toàn bộ hệ thống, không phụ thuộc board
// -----------------------------------------------------------------------------
//   PC -rx-> uart_rx -> img_rx -> tinyml_core (img_buf, L1, hid_buf, L2, argmax)
//                         ^            ^
//                         |  top_fsm --+--> uart_tx -tx-> PC
// basys3_top và nexys_a7_top chỉ bọc module này, thêm reset, LED và LED 7 đoạn.
// =============================================================================
module tinyml_system
    import tinyml_pkg::*;
(
    input  logic   clk,
    input  logic   rst,            // reset đồng bộ, mức cao
    input  logic   uart_rxd,       // PC -> FPGA
    output logic   uart_txd,       // FPGA -> PC

    output digit_t result,         // chữ số dự đoán gần nhất
    output logic   result_valid,
    output logic   busy,           // đang tính
    output logic   err_seen        // đã từng bỏ khung hoặc lỗi UART (giữ tới khi reset)
);
    // ---------------- UART RX ----------------
    logic [7:0] rx_data;
    logic       rx_valid, rx_error;

    uart_rx u_rx (
        .clk(clk), .rst(rst), .rx(uart_rxd),
        .rx_data(rx_data), .rx_valid(rx_valid), .rx_error(rx_error)
    );  

    // ---------------- Khối nhận ảnh ----------------
    logic      rx_enable, img_ready, img_we, frame_drop;
    img_addr_t img_waddr;
    act_t      img_wdata;

    img_rx u_img_rx (
        .clk(clk), .rst(rst),
        .rx_data(rx_data), .rx_valid(rx_valid), .rx_error(rx_error),
        .rx_enable(rx_enable), .img_ready(img_ready),
        .img_we(img_we), .img_waddr(img_waddr), .img_wdata(img_wdata),
        .frame_drop(frame_drop)
    );

    // ---------------- Lõi tính toán ----------------
    logic   l1_start, l1_done, l2_start, l2_done, argmax_start, argmax_done;
    digit_t argmax_digit;

    /* verilator lint_off PINCONNECTEMPTY */
    tinyml_core u_core (
        .clk(clk), .rst(rst),
        .img_we(img_we), .img_waddr(img_waddr), .img_wdata(img_wdata),
        .l1_start(l1_start), .l1_done(l1_done),
        .l2_start(l2_start), .l2_done(l2_done),
        .argmax_start(argmax_start), .argmax_done(argmax_done), .argmax_digit(argmax_digit),
        .logit_idx('0), .logit_val()
    );

    // ---------------- FSM chính ----------------
    logic       tx_start, tx_done;
    logic [7:0] tx_data;

    top_fsm u_fsm (
        .clk(clk), .rst(rst),
        .img_ready(img_ready), .rx_enable(rx_enable),
        .l1_start(l1_start), .l1_done(l1_done),
        .l2_start(l2_start), .l2_done(l2_done),
        .argmax_start(argmax_start), .argmax_done(argmax_done), .argmax_digit(argmax_digit),
        .tx_start(tx_start), .tx_data(tx_data), .tx_done(tx_done),
        .result(result), .result_valid(result_valid), .busy(busy)
    );

    // ---------------- UART TX ----------------
    uart_tx u_tx (
        .clk(clk), .rst(rst),
        .tx_start(tx_start), .tx_data(tx_data),
        .tx(uart_txd), .tx_busy(), .tx_done(tx_done)
    );
    /* verilator lint_on PINCONNECTEMPTY */

    // ---------------- Cờ lỗi (gỡ lỗi trên LED) ----------------
    always_ff @(posedge clk) begin
        if (rst)                        err_seen <= 1'b0;
        else if (frame_drop || rx_error) err_seen <= 1'b1;
    end

endmodule
