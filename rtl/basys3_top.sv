// =============================================================================
// basys3_top.sv — Top cho Digilent Basys 3 (XC7A35T, clock 100 MHz)
// -----------------------------------------------------------------------------
//   btnC      : reset
//   RsRx/RsTx : USB-UART, 1 Mbaud 8N1 (PC gửi 784 byte, FPGA trả '0'..'9')
//   seg/an    : chữ số dự đoán ở LED 7 đoạn phải nhất
//   led[0..9] : LED ứng với chữ số dự đoán sáng
//   led[14]   : đã có lỗi khung / lỗi UART      led[15] : đang tính
// Tên cổng khớp với Basys-3-Master.xdc của Digilent.
// =============================================================================
module basys3_top
    import tinyml_pkg::*;
(
    input  logic        clk,
    input  logic        btnC,
    input  logic        RsRx,
    output logic        RsTx,
    output logic [15:0] led,
    output logic [6:0]  seg,
    output logic        dp,
    output logic [3:0]  an
);
    // Đồng bộ nút reset (nút bấm là tín hiệu bên ngoài)
    logic [1:0] rst_sync = 2'b11;
    always_ff @(posedge clk) rst_sync <= {rst_sync[0], btnC};
    wire rst = rst_sync[1];

    digit_t result;
    logic   result_valid, busy, err_seen;

    tinyml_system u_sys (
        .clk(clk), .rst(rst), .uart_rxd(RsRx), .uart_txd(RsTx),
        .result(result), .result_valid(result_valid), .busy(busy), .err_seen(err_seen)
    );

    seg7 #(.N_AN(4)) u_seg7 (
        .digit(result), .valid(result_valid), .seg(seg), .dp(dp), .an(an)
    );

    always_comb begin
        led = '0;
        if (result_valid) led[result] = 1'b1;
        led[14] = err_seen;
        led[15] = busy;
    end
endmodule
