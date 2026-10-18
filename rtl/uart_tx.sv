// =============================================================================
// uart_tx.sv — Bộ phát UART 8N1
// -----------------------------------------------------------------------------
//   S_IDLE : tx = 1, chờ tx_start; chốt tx_data
//   S_START: phát bit start (0) trong 1 bit
//   S_DATA : phát 8 bit, LSB trước
//   S_STOP : phát bit stop (1) trong 1 bit, xong thì xuất tx_done
//
// Giao thức khớp với top_fsm: tx_start là xung 1 chu kỳ, tx_done là xung 1 chu kỳ.
// tx_start đến khi đang bận (tx_busy = 1) sẽ bị bỏ qua.
// =============================================================================
module uart_tx
    import tinyml_pkg::*;
(
    input  logic       clk,
    input  logic       rst,
    input  logic       tx_start,    // xung: bắt đầu gửi tx_data
    input  logic [7:0] tx_data,
    output logic       tx,          // chân TX tới USB-UART
    output logic       tx_busy,     // 1 = đang gửi
    output logic       tx_done      // xung 1 chu kỳ: gửi xong bit stop
);

    localparam int CNT_W = $clog2(CLKS_PER_BIT);

    typedef enum logic [1:0] { S_IDLE, S_START, S_DATA, S_STOP } state_t;
    state_t state;

    logic [CNT_W-1:0] clk_cnt;
    logic [2:0]       bit_idx;
    logic [7:0]       shift;

    wire bit_end = (clk_cnt == CNT_W'(CLKS_PER_BIT - 1));

    always_ff @(posedge clk) begin
        if (rst) begin
            state   <= S_IDLE;
            clk_cnt <= '0;
            bit_idx <= '0;
            shift   <= '0;
            tx      <= 1'b1;
            tx_done <= 1'b0;
        end else begin
            tx_done <= 1'b0;
            clk_cnt <= (state == S_IDLE || bit_end) ? '0 : clk_cnt + 1'b1;

            unique case (state)
                S_IDLE: begin
                    tx      <= 1'b1;
                    bit_idx <= '0;
                    if (tx_start) begin
                        shift <= tx_data;
                        tx    <= 1'b0;                 // bit start
                        state <= S_START;
                    end
                end

                S_START: if (bit_end) begin
                    tx    <= shift[0];
                    shift <= {1'b0, shift[7:1]};
                    state <= S_DATA;
                end

                S_DATA: if (bit_end) begin
                    if (bit_idx == 3'd7) begin
                        tx    <= 1'b1;                 // bit stop
                        state <= S_STOP;
                    end else begin
                        tx    <= shift[0];
                        shift <= {1'b0, shift[7:1]};
                    end
                    bit_idx <= bit_idx + 1'b1;
                end

                S_STOP: if (bit_end) begin
                    tx_done <= 1'b1;
                    state   <= S_IDLE;
                end

                default: state <= S_IDLE;
            endcase
        end
    end

    assign tx_busy = (state != S_IDLE);

endmodule
