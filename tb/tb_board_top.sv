// =============================================================================
// tb_board_top.sv — Kiểm toàn hệ thống trên basys3_top qua UART thật
// -----------------------------------------------------------------------------
// Testbench đóng vai PC:
//   * pc_send() gửi 784 byte của 1 ảnh vào chân RsRx (1 Mbaud, 8N1)
//   * pc_recv() đọc ký tự FPGA trả về trên chân RsTx
// Kiểm: ký tự trả về = '0' + chữ số Python dự đoán, LED và LED 7 đoạn đúng.
// Mỗi ảnh mất khoảng 7,8 ms thời gian mô phỏng, nên chỉ chạy N_IMG ảnh.
// =============================================================================
`timescale 1ns/1ps
module tb_board_top;
    import tinyml_pkg::*;

    localparam int  N_IMG  = 3;
    localparam real BIT_NS = 1.0e9 / UART_BAUD;

    logic clk = 0, btnC = 1, RsRx = 1;
    logic RsTx, dp;
    logic [15:0] led;
    logic [6:0]  seg;
    logic [3:0]  an;
    always #5 clk = ~clk;

    basys3_top dut (.*);

    logic [7:0]  images   [200 * N_IN];
    logic [31:0] expected [200 * 11];

    // mã LED 7 đoạn mong đợi (tích cực mức thấp)
    function automatic logic [6:0] seg_of(input int d);
        case (d)
            0: return 7'b1000000; 1: return 7'b1111001; 2: return 7'b0100100;
            3: return 7'b0110000; 4: return 7'b0011001; 5: return 7'b0010010;
            6: return 7'b0000010; 7: return 7'b1111000; 8: return 7'b0000000;
            default: return 7'b0010000;
        endcase
    endfunction

    task automatic pc_send(input logic [7:0] b);
        RsRx = 0; #(BIT_NS);
        for (int i = 0; i < 8; i++) begin RsRx = b[i]; #(BIT_NS); end
        RsRx = 1; #(BIT_NS);
    endtask

    task automatic pc_recv(output logic [7:0] b);
        @(negedge RsTx);                    // bit start
        #(BIT_NS * 1.5);                    // tới giữa bit D0
        for (int i = 0; i < 8; i++) begin b[i] = RsTx; #(BIT_NS); end
    endtask

    int errors = 0;

    initial begin
        $readmemh("test_images.mem",   images);
        $readmemh("test_expected.mem", expected);
        #(BIT_NS * 3); btnC = 0; #(BIT_NS * 3);

        for (int n = 0; n < N_IMG; n++) begin
            logic [7:0] ch;
            int exp_d;
            exp_d = int'(expected[n * 11]);
            fork
                for (int p = 0; p < N_IN; p++) pc_send(images[n * N_IN + p]);
                pc_recv(ch);
            join
            #(BIT_NS * 3);
            if (ch !== 8'h30 + exp_d[7:0]) begin
                errors++; $display("SAI anh %0d: FPGA tra '%c', Python = %0d", n, ch, exp_d);
            end else if (led[exp_d] !== 1'b1 || seg !== seg_of(exp_d) || an !== 4'b1110) begin
                errors++; $display("SAI hien thi anh %0d: led=%b seg=%b", n, led, seg);
            end else
                $display("OK  anh %0d: FPGA tra '%c' (Python %0d), LED[%0d] sang, 7 doan dung", n, ch, exp_d, exp_d);
        end

        if (led[14]) begin errors++; $display("SAI: co bao loi khung/UART"); end
        if (errors == 0) $display("PASS tb_board_top");
        else             $display("FAIL tb_board_top (%0d loi)", errors);
        $finish;
    end
endmodule
