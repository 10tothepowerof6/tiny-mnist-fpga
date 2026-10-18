// =============================================================================
// tb_tinyml_core.sv — Kiểm bit-exact lõi tính toán + top_fsm với mô hình Python
// -----------------------------------------------------------------------------
// Với mỗi ảnh trong test_images.mem (200 ảnh do bên AI xuất):
//   1. ghi thẳng 784 pixel (đã tiền xử lý x >> 1) vào img_buf, bỏ qua UART
//   2. phát img_ready cho top_fsm -> top_fsm tự chạy L1 -> L2 -> ARGMAX -> SEND
//   3. so chữ số dự đoán và 10 logit với test_expected.mem
// uart_tx được giả lập: thấy tx_start thì trả tx_done sau vài chu kỳ.
// Cần các file .mem nằm trong thư mục chạy mô phỏng (Vivado tự chép nếu đã
// Add Sources các file .mem).
// =============================================================================
`timescale 1ns/1ps
module tb_tinyml_core;
    import tinyml_pkg::*;

    localparam int N_IMG = 200;

    logic clk = 0, rst = 1;
    always #5 clk = ~clk;                      // 100 MHz

    // ---------------- Lõi + FSM ----------------
    logic      img_we = 0;
    img_addr_t img_waddr = '0;
    act_t      img_wdata = '0;
    logic      img_ready = 0;

    logic   l1_start, l1_done, l2_start, l2_done, argmax_start, argmax_done;
    digit_t argmax_digit, result, logit_idx = '0;
    acc_t   logit_val;
    logic   rx_enable, tx_start, tx_done = 0, result_valid, busy;
    logic [7:0] tx_data;

    tinyml_core u_core (
        .clk, .rst, .img_we, .img_waddr, .img_wdata,
        .l1_start, .l1_done, .l2_start, .l2_done,
        .argmax_start, .argmax_done, .argmax_digit,
        .logit_idx, .logit_val
    );

    top_fsm u_fsm (
        .clk, .rst, .img_ready, .rx_enable,
        .l1_start, .l1_done, .l2_start, .l2_done,
        .argmax_start, .argmax_done, .argmax_digit,
        .tx_start, .tx_data, .tx_done,
        .result, .result_valid, .busy
    );

    // uart_tx giả lập
    always @(posedge clk) begin
        if (tx_start) begin
            repeat (5) @(posedge clk);
            tx_done <= 1; @(posedge clk); tx_done <= 0;
        end
    end

    // ---------------- Dữ liệu từ Python ----------------
    logic [7:0]  images   [N_IMG * N_IN];
    logic [7:0]  labels   [N_IMG];
    logic [31:0] expected [N_IMG * 11];        // mỗi ảnh: pred, logit0..logit9

    int errors = 0, correct = 0, cycles = 0, tx_ok = 0;
    logic [7:0] sent;

    always @(posedge clk) if (tx_start) sent <= tx_data;

    initial begin
        $readmemh("test_images.mem",   images);
        $readmemh("test_labels.mem",   labels);
        $readmemh("test_expected.mem", expected);
        repeat (5) @(posedge clk); rst <= 0; repeat (2) @(posedge clk);

        for (int n = 0; n < N_IMG; n++) begin
            // 1. nạp ảnh
            for (int p = 0; p < N_IN; p++) begin
                img_we    <= 1;
                img_waddr <= img_addr_t'(p);
                img_wdata <= preprocess(images[n * N_IN + p]);
                @(posedge clk);
            end
            img_we <= 0;

            // 2. báo top_fsm, đo số chu kỳ tới khi có kết quả
            img_ready <= 1; @(posedge clk); img_ready <= 0;
            cycles = 1;
            while (!argmax_done) begin @(posedge clk); cycles++; end
            wait (!busy); @(posedge clk);

            // 3. so sánh
            if (result !== digit_t'(expected[n * 11])) begin
                errors++; $display("SAI anh %0d: HW = %0d, Python = %0d", n, result, expected[n * 11]);
            end
            if (sent === 8'h30 + {4'b0, result}) tx_ok++;
            for (int j = 0; j < N_OUT; j++) begin
                logit_idx = digit_t'(j); #1;
                if (logit_val !== $signed(expected[n * 11 + 1 + j])) begin
                    errors++;
                    $display("SAI logit anh %0d [%0d]: HW = %0d, Python = %0d",
                             n, j, logit_val, $signed(expected[n * 11 + 1 + j]));
                end
            end
            if (result == digit_t'(labels[n])) correct++;
        end

        $display("--------------------------------------------------");
        $display("So anh: %0d | chu ky tinh / anh: %0d (%0.1f us @ 100 MHz)", N_IMG, cycles, cycles / 100.0);
        $display("Ky tu gui ve dung: %0d/%0d", tx_ok, N_IMG);
        $display("Do chinh xac so voi nhan that: %0d/%0d", correct, N_IMG);
        if (errors == 0 && tx_ok == N_IMG) $display("PASS tb_tinyml_core: khop bit-exact voi Python");
        else                               $display("FAIL tb_tinyml_core: %0d sai khac", errors);
        $finish;
    end
endmodule
