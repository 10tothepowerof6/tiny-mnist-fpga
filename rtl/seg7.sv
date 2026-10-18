// =============================================================================
// seg7.sv — Hiển thị chữ số kết quả trên LED 7 đoạn
// -----------------------------------------------------------------------------
// LED 7 đoạn của Basys 3 / Nexys A7 tích cực mức THẤP:
//   seg[0] = a, seg[1] = b, ..., seg[6] = g;   an[i] = 0 -> bật chữ số thứ i
// Chỉ dùng chữ số ngoài cùng bên phải (an[0]); chưa có kết quả thì hiện '-'.
// =============================================================================
module seg7
    import tinyml_pkg::*;
#(
    parameter int N_AN = 4              // Basys 3: 4 chữ số, Nexys A7: 8 chữ số
) (
    input  digit_t          digit,
    input  logic            valid,
    output logic [6:0]      seg,
    output logic            dp,
    output logic [N_AN-1:0] an
);
    always_comb begin
        if (!valid) seg = 7'b0111111;   // '-'
        else begin
            unique case (digit)
                4'd0: seg = 7'b1000000;
                4'd1: seg = 7'b1111001;
                4'd2: seg = 7'b0100100;
                4'd3: seg = 7'b0110000;
                4'd4: seg = 7'b0011001;
                4'd5: seg = 7'b0010010;
                4'd6: seg = 7'b0000010;
                4'd7: seg = 7'b1111000;
                4'd8: seg = 7'b0000000;
                4'd9: seg = 7'b0010000;
                default: seg = 7'b0111111;
            endcase
        end
    end

    assign dp = 1'b1;                                   // tắt dấu chấm
    assign an = {{(N_AN-1){1'b1}}, 1'b0};               // chỉ bật chữ số phải nhất
endmodule
