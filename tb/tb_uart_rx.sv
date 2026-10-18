// =============================================================================
// tb_uart_rx.sv — Testbench riêng cho uart_rx
// -----------------------------------------------------------------------------
// Testbench đóng vai PC: task pc_send() tự đảo chân rx theo từng bit 8N1.
// Mỗi byte gửi đi được đẩy vào hàng đợi exp_q; khi uart_rx báo rx_valid,
// testbench so rx_data với byte đầu hàng đợi.
//
// Các bài kiểm tra:
//   1. Gửi đủ 256 giá trị 0x00..0xFF
//   2. 200 byte ngẫu nhiên, gửi sát nhau (không nghỉ giữa các byte)
//   3. Baud của PC lệch -3 % và +3 %
//   4. Gai nhiễu ngắn (< nửa bit) trên đường rx -> phải bị bỏ qua
//   5. Bit stop sai -> phải báo rx_error, không báo rx_valid
//   6. Reset giữa chừng khi đang nhận -> sau reset vẫn nhận đúng
//
// Chạy trong Vivado: Set as Top -> Run Behavioral Simulation -> run all
// Kết quả mong đợi ở Tcl Console:  PASS tb_uart_rx
// =============================================================================
`timescale 1ns/1ps
module tb_uart_rx;
    import tinyml_pkg::*;

    // ---------------- Clock 100 MHz, reset ----------------
    logic clk = 0, rst = 1;
    always #5 clk = ~clk;

    // ---------------- DUT ----------------
    logic       rx = 1'b1;           // đường UART rảnh = 1
    logic [7:0] rx_data;
    logic       rx_valid, rx_error;

    uart_rx dut (.clk(clk), .rst(rst), .rx(rx),
                 .rx_data(rx_data), .rx_valid(rx_valid), .rx_error(rx_error));

    // ---------------- Bộ kiểm tra tự động ----------------
    localparam real BIT_NS = 1.0e9 / UART_BAUD;   // 1000 ns ở 1 Mbaud

    logic [7:0] exp_q[$];            // các byte đang chờ được nhận
    int n_ok = 0, n_err_seen = 0, errors = 0;
    bit expect_error = 0;            // =1 khi đang cố tình gửi bit stop sai

    always @(posedge clk) begin
        if (rx_valid) begin
            if (exp_q.size() == 0) begin
                errors++; $display("[%0t] LOI: rx_valid thua, rx_data=%h", $time, rx_data);
            end else if (rx_data !== exp_q[0]) begin
                errors++; $display("[%0t] LOI: nhan %h, mong doi %h", $time, rx_data, exp_q[0]);
                void'(exp_q.pop_front());
            end else begin
                n_ok++; void'(exp_q.pop_front());
            end
        end
        if (rx_error) begin
            n_err_seen++;
            if (!expect_error) begin errors++; $display("[%0t] LOI: rx_error khong mong doi", $time); end
        end
    end

    // ---------------- PC giả lập ----------------
    // Gửi 1 byte: start(0) + 8 bit LSB trước + stop. bit_ns cho phép lệch baud.
    task automatic pc_send(input logic [7:0] b, input real bit_ns = BIT_NS,
                           input logic stop_bit = 1'b1);
        rx = 1'b0;                 #(bit_ns);
        for (int i = 0; i < 8; i++) begin
            rx = b[i];             #(bit_ns);
        end
        rx = stop_bit;             #(bit_ns);
        rx = 1'b1;
    endtask

    // Gửi và ghi vào hàng đợi kết quả mong đợi
    task automatic send_check(input logic [7:0] b, input real bit_ns = BIT_NS);
        exp_q.push_back(b);
        pc_send(b, bit_ns);
    endtask

    task automatic idle(input int n_bits);
        #(n_bits * BIT_NS);
    endtask

    // ---------------- Kịch bản ----------------
    initial begin
        int n_before;
        $display("UART_BAUD = %0d, CLKS_PER_BIT = %0d", UART_BAUD, CLKS_PER_BIT);
        repeat (10) @(posedge clk);
        rst = 0;
        idle(2);

        // 1. Đủ 256 giá trị
        for (int v = 0; v < 256; v++) begin
            send_check(v[7:0]);
            idle(1);
        end
        $display("Test 1: 256 gia tri          -> da nhan %0d", n_ok);

        // 2. 200 byte ngẫu nhiên, sát nhau
        n_before = n_ok;
        for (int k = 0; k < 200; k++) send_check($urandom_range(0, 255));
        idle(2);
        $display("Test 2: 200 byte sat nhau    -> da nhan %0d", n_ok - n_before);

        // 3. Lệch baud ±3 %
        n_before = n_ok;
        for (int k = 0; k < 20; k++) begin send_check($urandom_range(0, 255), BIT_NS * 0.97); idle(1); end
        for (int k = 0; k < 20; k++) begin send_check($urandom_range(0, 255), BIT_NS * 1.03); idle(1); end
        $display("Test 3: lech baud -3%%/+3%%   -> da nhan %0d/40", n_ok - n_before);

        // 4. Gai nhiễu dài 1/4 bit -> không được tạo byte
        n_before = n_ok;
        for (int k = 0; k < 5; k++) begin
            rx = 1'b0; #(BIT_NS / 4); rx = 1'b1;
            idle(12);
        end
        send_check(8'h5A); idle(2);              // sau nhiễu vẫn nhận đúng
        $display("Test 4: gai nhieu            -> byte thua = %0d (phai 0)", n_ok - n_before - 1);

        // 5. Bit stop sai
        expect_error = 1;
        pc_send(8'hC3, BIT_NS, 1'b0);
        idle(3);
        expect_error = 0;
        if (n_err_seen != 1) begin errors++; $display("LOI: rx_error = %0d lan (phai 1)", n_err_seen); end
        send_check(8'h3C); idle(2);              // sau lỗi vẫn nhận đúng
        $display("Test 5: sai bit stop         -> rx_error %0d lan", n_err_seen);

        // 6. Reset giữa lúc đang nhận
        fork
            pc_send(8'hFF);                      // byte này bị cắt ngang, không kiểm
            begin #(BIT_NS * 4); rst = 1; repeat (3) @(posedge clk); rst = 0; end
        join
        idle(12);
        n_before = n_ok;
        send_check(8'hA7); idle(2);
        $display("Test 6: reset giua chung     -> sau reset nhan %0d/1", n_ok - n_before);

        // ---------------- Tổng kết ----------------
        if (exp_q.size() != 0) begin errors++; $display("LOI: con %0d byte chua nhan", exp_q.size()); end
        $display("--------------------------------------------");
        $display("Tong: nhan dung %0d byte, %0d loi", n_ok, errors);
        if (errors == 0) $display("PASS tb_uart_rx");
        else             $display("FAIL tb_uart_rx");
        $finish;
    end

    // Chống treo
    initial begin
        #(BIT_NS * 12 * 1000);
        $display("FAIL tb_uart_rx: qua thoi gian");
        $finish;
    end

endmodule
