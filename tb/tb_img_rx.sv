// =============================================================================
// tb_img_rx.sv — Testbench cho img_rx
// -----------------------------------------------------------------------------
// Đưa byte thẳng vào cổng rx_data/rx_valid (giả lập uart_rx, chạy nhanh hơn
// đi qua UART thật). Một mảng img_mem giả lập img_buf, ghi theo img_we.
//
//   1. Gửi 1 ảnh đủ 784 byte  -> img_ready 1 lần, img_mem = pixel >> 1
//   2. Gửi 300 byte rồi nghỉ > 10 ms -> bỏ khung dở (frame_drop), ảnh sau vẫn đúng
//   3. rx_enable = 0 -> mọi byte bị bỏ qua, không ghi, không img_ready
//   4. rx_error giữa khung -> bỏ khung dở, ảnh sau vẫn đúng
//   5. Nghỉ 5 ms giữa chừng (< 10 ms) -> vẫn là cùng một khung
//   6. Gửi 2 ảnh liên tiếp -> img_ready 2 lần, ảnh thứ 2 ghi đè đúng
// =============================================================================
`timescale 1ns/1ps
module tb_img_rx;
    import tinyml_pkg::*;

    logic clk = 0, rst = 1;
    always #5 clk = ~clk;

    logic [7:0] rx_data = '0;
    logic       rx_valid = 0, rx_error = 0, rx_enable = 1;
    logic       img_ready, img_we, frame_drop;
    img_addr_t  img_waddr;
    act_t       img_wdata;

    img_rx dut (.*);

    // ----- img_buf giả lập + đếm sự kiện -----
    act_t img_mem [N_IN];
    int   n_ready = 0, n_drop = 0, n_write = 0, errors = 0;
    always @(posedge clk) begin
        if (img_we) begin img_mem[img_waddr] <= img_wdata; n_write++; end
        if (img_ready)  n_ready++;
        if (frame_drop) n_drop++;
    end

    logic [7:0] pix [N_IN];

    // Gửi 1 byte giống uart_rx: rx_valid lên 1 chu kỳ, cách nhau `gap` chu kỳ
    task automatic put_byte(input logic [7:0] b, input int gap = 20);
        @(posedge clk); rx_data <= b; rx_valid <= 1;
        @(posedge clk); rx_valid <= 0;
        repeat (gap) @(posedge clk);
    endtask

    task automatic new_image(input int seed);
        for (int i = 0; i < N_IN; i++) pix[i] = 8'((seed * 97 + i * 31 + (i * i) % 251) ^ (i >> 3));
    endtask

    task automatic send_image(input int from = 0, input int to = N_IN);
        for (int i = from; i < to; i++) put_byte(pix[i]);
    endtask

    task automatic check_image(input string name);
        int bad = 0;
        repeat (3) @(posedge clk);
        for (int i = 0; i < N_IN; i++)
            if (img_mem[i] !== act_t'(pix[i] >> 1)) bad++;
        if (bad != 0) begin errors++; $display("LOI %s: %0d pixel sai", name, bad); end
    endtask

    task automatic expect_cnt(input string name, input int ready, input int drop);
        if (n_ready != ready || n_drop != drop) begin
            errors++;
            $display("LOI %s: img_ready=%0d (mong %0d), frame_drop=%0d (mong %0d)",
                     name, n_ready, ready, n_drop, drop);
        end else
            $display("OK  %s", name);
    endtask

    int w0;
    initial begin
        $display("N_IN = %0d, GAP_TIMEOUT = %0d chu ky (10 ms)", N_IN, GAP_TIMEOUT);
        repeat (5) @(posedge clk); rst <= 0; repeat (5) @(posedge clk);

        // 1. Một ảnh đầy đủ
        new_image(1); send_image();
        check_image("test 1");
        expect_cnt("test 1: 1 anh day du, ghi dung 784 pixel (x >> 1)", 1, 0);
        if (n_write != N_IN) begin errors++; $display("LOI: ghi %0d lan (mong 784)", n_write); end

        // 2. Khung dở + nghỉ quá 10 ms
        new_image(2); send_image(0, 300);
        repeat (GAP_TIMEOUT + 10) @(posedge clk);
        expect_cnt("test 2a: 300 byte roi nghi > 10 ms -> bo khung", 1, 1);
        new_image(3); send_image();
        check_image("test 2b");
        expect_cnt("test 2b: anh sau khung bi bo van dung", 2, 1);

        // 3. rx_enable = 0
        rx_enable <= 0;
        w0 = n_write;
        new_image(4); send_image(0, 784);
        if (n_write != w0) begin errors++; $display("LOI test 3: van ghi khi rx_enable=0"); end
        expect_cnt("test 3: rx_enable = 0 -> bo qua moi byte", 2, 1);
        rx_enable <= 1;

        // 4. rx_error giữa khung
        new_image(5); send_image(0, 400);
        @(posedge clk); rx_error <= 1; @(posedge clk); rx_error <= 0;
        repeat (3) @(posedge clk);
        expect_cnt("test 4a: rx_error giua khung -> bo khung", 2, 2);
        new_image(6); send_image();
        check_image("test 4b");
        expect_cnt("test 4b: anh sau loi van dung", 3, 2);

        // 5. Nghỉ 5 ms giữa chừng (chưa tới 10 ms)
        new_image(7); send_image(0, 500);
        repeat (GAP_TIMEOUT / 2) @(posedge clk);
        send_image(500, N_IN);
        check_image("test 5");
        expect_cnt("test 5: nghi 5 ms giua khung -> van la 1 anh", 4, 2);

        // 6. Hai ảnh liên tiếp
        new_image(8); send_image();
        new_image(9); send_image();
        check_image("test 6");
        expect_cnt("test 6: 2 anh lien tiep, anh 2 ghi de dung", 6, 2);

        if (errors == 0) $display("PASS tb_img_rx");
        else             $display("FAIL tb_img_rx (%0d loi)", errors);
        $finish;
    end
endmodule
