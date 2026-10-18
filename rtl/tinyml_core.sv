// =============================================================================
// tinyml_core.sv — Lõi tính toán: img_buf -> L1 -> hid_buf -> L2 -> argmax
// -----------------------------------------------------------------------------
// Không chứa UART và FSM, chỉ có đường dữ liệu. top_fsm điều khiển qua các
// cặp start/done của từng khối. Tách riêng để testbench có thể nạp ảnh thẳng
// vào img_buf và kiểm bit-exact 200 ảnh mà không phải chờ UART.
// =============================================================================
module tinyml_core
    import tinyml_pkg::*;
(
    input  logic      clk,
    input  logic      rst,

    // Cổng ghi img_buf (từ img_rx hoặc testbench)
    input  logic      img_we,
    input  img_addr_t img_waddr,
    input  act_t      img_wdata,

    // Điều khiển từ top_fsm
    input  logic      l1_start,
    output logic      l1_done,
    input  logic      l2_start,
    output logic      l2_done,
    input  logic      argmax_start,
    output logic      argmax_done,
    output digit_t    argmax_digit,

    // Đọc logit (gỡ lỗi)
    input  digit_t    logit_idx,
    output acc_t      logit_val
);
    // ---------------- img_buf: 784 x 8 ----------------
    img_addr_t l1_x_addr;
    act_t      l1_x_data;

    buf_ram #(.DEPTH(IMG_DEPTH), .WIDTH(ACT_W)) u_img_buf (
        .clk(clk),
        .we(img_we), .waddr(img_waddr), .wdata(img_wdata),
        .raddr(l1_x_addr), .rdata(l1_x_data)
    );

    // ---------------- Lớp 1: 784 -> 32, requant + ReLU ----------------
    logic      l1_we;
    hid_addr_t l1_waddr;
    /* verilator lint_off UNUSEDSIGNAL */
    acc_t      l1_wdata;              // sau ReLU chỉ còn 0..127, chỉ dùng 8 bit thấp
    /* verilator lint_on UNUSEDSIGNAL */

    /* verilator lint_off PINCONNECTEMPTY */
    fc_layer #(
        .IN(N_IN), .OUT(N_HID), .P(PE1),
        .LAYER(1), .RELU(1'b1)
    ) u_l1 (
        .clk(clk), .rst(rst), .start(l1_start), .done(l1_done), .busy(),
        .x_addr(l1_x_addr), .x_data(l1_x_data),
        .out_we(l1_we), .out_addr(l1_waddr), .out_data(l1_wdata)
    );

    // ---------------- hid_buf: 32 x 8 ----------------
    hid_addr_t l2_x_addr;
    act_t      l2_x_data;

    buf_ram #(.DEPTH(HID_DEPTH), .WIDTH(ACT_W)) u_hid_buf (
        .clk(clk),
        .we(l1_we), .waddr(l1_waddr), .wdata(act_t'(l1_wdata[ACT_W-1:0])),  // đã nằm trong 0..127
        .raddr(l2_x_addr), .rdata(l2_x_data)
    );

    // ---------------- Lớp 2: 32 -> 10, logit int32 ----------------
    logic   l2_we;
    digit_t l2_waddr;
    acc_t   l2_wdata;

    fc_layer #(
        .IN(N_HID), .OUT(N_OUT), .P(PE2),
        .LAYER(2), .RELU(1'b0)
    ) u_l2 (
        .clk(clk), .rst(rst), .start(l2_start), .done(l2_done), .busy(),
        .x_addr(l2_x_addr), .x_data(l2_x_data),
        .out_we(l2_we), .out_addr(l2_waddr), .out_data(l2_wdata)
    );
    /* verilator lint_on PINCONNECTEMPTY */

    // ---------------- Argmax ----------------
    argmax u_argmax (
        .clk(clk), .rst(rst),
        .in_valid(l2_we), .in_idx(l2_waddr), .in_logit(l2_wdata),
        .start(argmax_start), .done(argmax_done), .digit(argmax_digit),
        .logit_idx(logit_idx), .logit_val(logit_val)
    );

endmodule
