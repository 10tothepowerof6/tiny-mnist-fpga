// =============================================================================
// uart_rx.sv — Bộ nhận UART 8N1 (1 start, 8 data LSB trước, 1 stop, không parity)
// -----------------------------------------------------------------------------
//   S_IDLE : chờ cạnh xuống của rx (bit start)
//   S_START: đợi nửa bit, kiểm tra rx vẫn = 0 (lọc nhiễu), canh giữa bit
//   S_DATA : mỗi CLKS_PER_BIT chu kỳ lấy mẫu 1 bit, đủ 8 bit
//   S_STOP : đợi 1 bit, rx phải = 1; xuất rx_valid (hoặc rx_error nếu sai)
//
// Lấy mẫu ở GIỮA mỗi bit để chịu được lệch baud giữa PC và FPGA.
// Ngõ vào rx đi qua 2 flip-flop đồng bộ vì nó đến từ bên ngoài (khác miền clock).
// =============================================================================
module uart_rx
    import tinyml_pkg::*;
(
    input  logic       clk,
    input  logic       rst,
    input  logic       rx,          // chân RX từ USB-UART
    output logic [7:0] rx_data,     // byte nhận được
    output logic       rx_valid,    // xung 1 chu kỳ: rx_data hợp lệ
    output logic       rx_error     // xung 1 chu kỳ: bit stop sai (lỗi khung)
);

    localparam int CNT_W = $clog2(CLKS_PER_BIT);

    typedef enum logic [1:0] { S_IDLE, S_START, S_DATA, S_STOP } state_t;
    state_t state;

    // Đồng bộ 2 tầng, khởi tạo = 1 (đường UART rảnh ở mức 1)
    logic rx_s1 = 1'b1, rx_s2 = 1'b1;
    always_ff @(posedge clk) begin
        rx_s1 <= rx;
        rx_s2 <= rx_s1;
    end

    logic [CNT_W-1:0] clk_cnt;      // đếm chu kỳ trong 1 bit
    logic [2:0]       bit_idx;      // bit dữ liệu đang nhận (0..7)
    logic [7:0]       shift;

    always_ff @(posedge clk) begin
        if (rst) begin
            state    <= S_IDLE;
            clk_cnt  <= '0;
            bit_idx  <= '0;
            shift    <= '0;
            rx_data  <= '0;
            rx_valid <= 1'b0;
            rx_error <= 1'b0;
        end else begin
            rx_valid <= 1'b0;
            rx_error <= 1'b0;

            unique case (state)
                S_IDLE: begin
                    clk_cnt <= '0;
                    bit_idx <= '0;
                    if (!rx_s2) state <= S_START;          // phát hiện bit start
                end

                S_START: begin
                    if (clk_cnt == CNT_W'(CLKS_PER_BIT/2 - 1)) begin
                        clk_cnt <= '0;
                        if (!rx_s2) state <= S_DATA;       // đúng là bit start
                        else        state <= S_IDLE;       // chỉ là nhiễu
                    end else begin
                        clk_cnt <= clk_cnt + 1'b1;
                    end
                end

                S_DATA: begin
                    if (clk_cnt == CNT_W'(CLKS_PER_BIT - 1)) begin
                        clk_cnt <= '0;
                        shift   <= {rx_s2, shift[7:1]};    // LSB đến trước
                        if (bit_idx == 3'd7) state <= S_STOP;
                        bit_idx <= bit_idx + 1'b1;
                    end else begin
                        clk_cnt <= clk_cnt + 1'b1;
                    end
                end

                S_STOP: begin
                    if (clk_cnt == CNT_W'(CLKS_PER_BIT - 1)) begin
                        clk_cnt <= '0;
                        state   <= S_IDLE;
                        if (rx_s2) begin
                            rx_data  <= shift;
                            rx_valid <= 1'b1;
                        end else begin
                            rx_error <= 1'b1;
                        end
                    end else begin
                        clk_cnt <= clk_cnt + 1'b1;
                    end
                end

                default: state <= S_IDLE;
            endcase
        end
    end

endmodule
