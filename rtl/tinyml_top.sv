// =============================================================================
// tinyml_top.sv — Top chung, KHÔNG gắn với board nào
// -----------------------------------------------------------------------------
// Dùng để chạy Synthesis / mô phỏng khi chưa nạp board.
// Chỉ thêm bộ đồng bộ reset rồi bọc tinyml_system; mọi tín hiệu đưa thẳng ra cổng.
// Khi nạp board thật thì đổi top sang basys3_top hoặc nexys_a7_top.
//   clk      : clock 100 MHz
//   rst_btn  : nút reset (mức cao, chưa đồng bộ)
//   uart_rxd : PC -> FPGA       uart_txd : FPGA -> PC
// =============================================================================
module tinyml_top
    import tinyml_pkg::*;
(
    input  logic   clk,
    input  logic   rst_btn,
    input  logic   uart_rxd,
    output logic   uart_txd,
    output digit_t result,          // chữ số dự đoán gần nhất (0..9)
    output logic   result_valid,    // 1 = result hợp lệ
    output logic   busy,            // 1 = đang tính
    output logic   err_seen         // 1 = đã có lỗi UART hoặc bỏ khung
);
    // Đồng bộ nút reset vào miền clock (2 flip-flop)
    logic [1:0] rst_sync = 2'b11;
    always_ff @(posedge clk) rst_sync <= {rst_sync[0], rst_btn};
    wire rst = rst_sync[1];

    tinyml_system u_sys (
        .clk(clk), .rst(rst), .uart_rxd(uart_rxd), .uart_txd(uart_txd),
        .result(result), .result_valid(result_valid), .busy(busy), .err_seen(err_seen)
    );
endmodule
