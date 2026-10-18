// =============================================================================
// nexys_a7_top.sv — Top cho Digilent Nexys A7-100T (XC7A100T, clock 100 MHz)
// -----------------------------------------------------------------------------
// Giống basys3_top, chỉ khác tên chân (theo Nexys-A7-100T-Master.xdc)
// và LED 7 đoạn có 8 chữ số.
//   CPU_RESETN (chân C12): nút reset đỏ, TÍCH CỰC MỨC THẤP (nhấn = 0)
//   UART_TXD_IN : PC -> FPGA     UART_RXD_OUT : FPGA -> PC
// =============================================================================
module nexys_a7_top
    import tinyml_pkg::*;
(
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,    // nhấn = 0 -> reset
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT,
    output logic [15:0] LED,
    output logic [6:0]  SEG,           // CA..CG
    output logic        DP,
    output logic [7:0]  AN
);
    logic [1:0] rst_sync = 2'b11;
    always_ff @(posedge CLK100MHZ) rst_sync <= {rst_sync[0], ~CPU_RESETN};  // đảo: nhấn nút = reset
    wire rst = rst_sync[1];

    digit_t result;
    logic   result_valid, busy, err_seen;

    tinyml_system u_sys (
        .clk(CLK100MHZ), .rst(rst), .uart_rxd(UART_TXD_IN), .uart_txd(UART_RXD_OUT),
        .result(result), .result_valid(result_valid), .busy(busy), .err_seen(err_seen)
    );

    seg7 #(.N_AN(8)) u_seg7 (
        .digit(result), .valid(result_valid), .seg(SEG), .dp(DP), .an(AN)
    );

    always_comb begin
        LED = '0;
        if (result_valid) LED[result] = 1'b1;
        LED[14] = err_seen;
        LED[15] = busy;
    end
endmodule
