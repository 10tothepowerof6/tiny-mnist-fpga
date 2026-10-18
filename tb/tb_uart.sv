`timescale 1ns/1ps
module tb_uart;
  import tinyml_pkg::*;
  logic clk=0, rst=1; always #5 clk=~clk;      // 100 MHz
  // --- loopback: tx -> rx
  logic tx_start=0, tx, tx_busy, tx_done; logic [7:0] tx_data=0;
  logic [7:0] rx_data; logic rx_valid, rx_error;
  logic [7:0] rx2_data; logic rx2_valid, rx2_error; logic line=1;
  uart_tx utx(.*);
  uart_rx urx(.clk, .rst, .rx(tx), .rx_data, .rx_valid, .rx_error);
  uart_rx urx2(.clk, .rst, .rx(line), .rx_data(rx2_data), .rx_valid(rx2_valid), .rx_error(rx2_error));
  int errors=0, got=0, n_done=0;
  logic [7:0] exp_q[$];
  always @(posedge clk) begin
    if (tx_done) n_done++;
    if (rx_valid) begin got++; if (rx_data !== exp_q[0]) begin errors++; $display("ERR loopback %h != %h", rx_data, exp_q[0]); end void'(exp_q.pop_front()); end
    if (rx_error) begin errors++; $display("ERR framing loopback"); end
  end
  // PC gia lap gui 1 byte voi baud lech (ns moi bit)
  task automatic pc_send(input logic [7:0] b, input real bit_ns, input logic stop);
    line=0; #(bit_ns); for (int i=0;i<8;i++) begin line=b[i]; #(bit_ns); end line=stop; #(bit_ns); line=1; #(bit_ns);
  endtask
  initial begin
    real nom; nom = 1e9/UART_BAUD;
    repeat(5) @(posedge clk); rst<=0; repeat(5) @(posedge clk);
    // 1) loopback 256 gia tri
    for (int v=0; v<256; v++) begin
      @(posedge clk); exp_q.push_back(v[7:0]); tx_data<=v[7:0]; tx_start<=1; @(posedge clk); tx_start<=0;
      @(posedge clk); tx_start<=1; @(posedge clk); tx_start<=0;   // start khi dang ban -> phai bi bo qua
      wait(tx_done); @(posedge clk);
    end
    repeat(CLKS_PER_BIT*2) @(posedge clk);
    if (got!=256 || n_done!=256) begin errors++; $display("ERR got=%0d done=%0d", got, n_done); end
    // 2) PC gui voi baud lech +-3%
    begin
      logic [7:0] pat[4]; real skew[3];
      pat[0]=8'hA5; pat[1]=8'h3C; pat[2]=8'h00; pat[3]=8'hFF; skew[0]=0.97; skew[1]=1.0; skew[2]=1.03;
      foreach (skew[s]) foreach (pat[k]) begin
        fork pc_send(pat[k], nom*skew[s], 1'b1); join_none
        @(posedge rx2_valid or posedge rx2_error);
        if (!rx2_valid || rx2_data!==pat[k]) begin errors++; $display("ERR skew %f: %h", skew[s], rx2_data); end
        #(nom*2);
      end
      // 3) bit stop sai -> rx_error
      fork pc_send(8'h55, nom, 1'b0); join_none
      @(posedge rx2_valid or posedge rx2_error);
      if (!rx2_error) begin errors++; $display("ERR khong bao loi khung"); end
      #(nom*3);
    end
    $display("loopback %0d byte, tx_done %0d", got, n_done);
    if (errors==0) $display("PASS uart"); else $display("FAIL uart (%0d loi)", errors);
    $finish;
  end
endmodule
