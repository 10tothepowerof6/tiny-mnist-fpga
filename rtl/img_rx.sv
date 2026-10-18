// =============================================================================
// img_rx.sv — Khối nhận ảnh
// -----------------------------------------------------------------------------
// Nhận từng byte từ uart_rx, tiền xử lý rồi ghi vào img_buf theo thứ tự:
//     byte thứ 0   -> địa chỉ 0      (hàng 0, cột 0)
//     byte thứ 783 -> địa chỉ 783    (hàng 27, cột 27)
// Đủ N_IN = 784 byte thì phát xung img_ready cho top_fsm.
//
// Dữ liệu ghi vào img_buf là x_q = pixel >> 1 (0..127), dùng hàm preprocess()
// của tinyml_pkg, nên lớp 1 đọc ra là dùng được ngay.
//
// Bỏ khung dở (bắt đầu đếm lại từ 0) khi:
//   * nghỉ quá GAP_TIMEOUT (10 ms) giữa 2 byte  -> PC bị ngắt giữa chừng
//   * uart_rx báo rx_error (byte hỏng)
// Khi rx_enable = 0 (top_fsm đang tính), mọi byte đến đều bị bỏ qua,
// để không ghi đè img_buf trong lúc lớp 1 đang đọc.
// =============================================================================
module img_rx
    import tinyml_pkg::*;
(
    input  logic       clk,
    input  logic       rst,

    // Từ uart_rx
    input  logic [7:0] rx_data,
    input  logic       rx_valid,
    input  logic       rx_error,

    // Từ / tới top_fsm
    input  logic       rx_enable,     // 1 = được phép nhận ảnh mới
    output logic       img_ready,     // xung 1 chu kỳ: đã ghi đủ 784 pixel

    // Tới img_buf (cổng ghi)
    output logic       img_we,
    output img_addr_t  img_waddr,
    output act_t       img_wdata,

    // Gỡ lỗi (có thể nối ra LED)
    output logic       frame_drop     // xung 1 chu kỳ: vừa bỏ một khung dở
);

    localparam int GAP_W = $clog2(GAP_TIMEOUT + 1);

    img_addr_t        byte_cnt;      // số byte đã nhận trong khung hiện tại
    logic [GAP_W-1:0] gap_cnt;       // số chu kỳ từ byte gần nhất

    wire accept  = rx_valid && rx_enable;
    wire timeout = (byte_cnt != '0) && (gap_cnt == GAP_W'(GAP_TIMEOUT));

    // Địa chỉ ghi của byte hiện tại: nếu vừa quá thời gian nghỉ thì byte này
    // là byte đầu của khung mới (địa chỉ 0)
    img_addr_t addr;
    logic      last_byte;
    assign addr      = timeout ? '0 : byte_cnt;
    assign last_byte = (addr == img_addr_t'(N_IN - 1));

    always_ff @(posedge clk) begin
        if (rst) begin
            byte_cnt   <= '0;
            gap_cnt    <= '0;
            img_we     <= 1'b0;
            img_waddr  <= '0;
            img_wdata  <= '0;
            img_ready  <= 1'b0;
            frame_drop <= 1'b0;
        end else begin
            img_we     <= 1'b0;
            img_ready  <= 1'b0;
            frame_drop <= 1'b0;

            // Bộ đếm thời gian nghỉ: về 0 mỗi khi có byte, dừng ở GAP_TIMEOUT
            if (rx_valid)                          gap_cnt <= '0;
            else if (gap_cnt != GAP_W'(GAP_TIMEOUT)) gap_cnt <= gap_cnt + 1'b1;

            if (!rx_enable) begin
                byte_cnt <= '0;                    // đang bận: không nhận
            end else if (rx_error) begin
                if (byte_cnt != '0) frame_drop <= 1'b1;
                byte_cnt <= '0;                    // byte hỏng: bỏ khung dở
            end else begin
                if (timeout) begin
                    frame_drop <= 1'b1;            // nghỉ quá 10 ms: bỏ khung dở
                    byte_cnt   <= '0;
                end
                if (accept) begin
                    img_we    <= 1'b1;             // ghi pixel vào img_buf
                    img_waddr <= addr;
                    img_wdata <= preprocess(rx_data);
                    if (last_byte) begin
                        byte_cnt  <= '0;
                        img_ready <= 1'b1;         // đủ 784 byte
                    end else begin
                        byte_cnt  <= addr + 1'b1;
                    end
                end
            end
        end
    end

endmodule
