// =============================================================================
// buf_ram.sv — RAM đệm 1 cổng ghi + 1 cổng đọc (đọc trễ 1 chu kỳ)
// -----------------------------------------------------------------------------
// Dùng chung cho:
//   img_buf : DEPTH = N_IN  (784) x 8 bit — ảnh sau tiền xử lý
//   hid_buf : DEPTH = N_HID (32)  x 8 bit — kết quả lớp 1
// Vivado tự chọn BRAM (bộ đệm lớn) hoặc LUTRAM (bộ đệm nhỏ).
// =============================================================================
module buf_ram #(
    parameter int DEPTH = 784,
    parameter int WIDTH = 8,
    localparam int AW   = $clog2(DEPTH)
) (
    input  logic             clk,
    // cổng ghi
    input  logic             we,
    input  logic [AW-1:0]    waddr,
    input  logic [WIDTH-1:0] wdata,
    // cổng đọc: rdata có ở chu kỳ sau khi đặt raddr
    input  logic [AW-1:0]    raddr,
    output logic [WIDTH-1:0] rdata
);
    logic [WIDTH-1:0] mem [DEPTH];

    always_ff @(posedge clk) begin
        if (we) mem[waddr] <= wdata;
        rdata <= mem[raddr];
    end
endmodule
