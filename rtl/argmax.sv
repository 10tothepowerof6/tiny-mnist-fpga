// =============================================================================
// argmax.sv — Chọn chữ số có logit lớn nhất
// -----------------------------------------------------------------------------
// So sánh trực tuyến: mỗi khi lớp 2 ghi ra 1 logit (in_valid), argmax so ngay
// với giá trị lớn nhất hiện tại. Logit đến theo thứ tự 0, 1, ..., 9.
// Dùng '>' (không phải '>=') nên khi bằng nhau giữ chỉ số nhỏ hơn — giống
// numpy.argmax của mô hình tham chiếu Python.
//
// Vì đã so xong trong lúc lớp 2 chạy, khi top_fsm phát start thì kết quả
// có sẵn: done được phát ngay chu kỳ sau.
// Logit cũng được lưu lại để testbench / gỡ lỗi đọc qua logit_idx.
// =============================================================================
module argmax
    import tinyml_pkg::*;
(
    input  logic   clk,
    input  logic   rst,

    // Từ lớp 2
    input  logic   in_valid,
    input  digit_t in_idx,
    input  acc_t   in_logit,

    // Từ / tới top_fsm
    input  logic   start,
    output logic   done,
    output digit_t digit,          // chữ số dự đoán

    // Đọc logit (gỡ lỗi)
    input  digit_t logit_idx,
    output acc_t   logit_val
);
    acc_t best;
    acc_t logits [N_OUT];

    always_ff @(posedge clk) begin
        if (rst) begin
            best  <= '0;
            digit <= '0;
            done  <= 1'b0;
        end else begin
            done <= start;
            if (in_valid) begin
                logits[in_idx] <= in_logit;
                if (in_idx == '0 || in_logit > best) begin   // logit 0 luôn làm giá trị đầu
                    best  <= in_logit;
                    digit <= in_idx;
                end
            end
        end
    end

    assign logit_val = logits[logit_idx];

endmodule
