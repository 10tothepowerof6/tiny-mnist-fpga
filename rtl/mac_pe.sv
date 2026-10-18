// =============================================================================
// mac_pe.sv — Processing Element: nhân - cộng dồn int8 x int8 -> int32
// -----------------------------------------------------------------------------
//   load = 1 : acc <= load_val          (nạp bias trước khi tính 1 neuron)
//   en   = 1 : acc <= acc + w * x       (cộng dồn 1 tích)
// Vivado map phép nhân 8x8 + cộng 32 bit vào 1 khối DSP48E1.
// =============================================================================
module mac_pe
    import tinyml_pkg::*;
(
    input  logic    clk,
    input  logic    load,
    input  acc_t    load_val,
    input  logic    en,
    input  weight_t w,
    input  act_t    x,
    output acc_t    acc
);
    prod_t prod;
    assign prod = w * x;                       // int8 x int8 = int16 có dấu

    always_ff @(posedge clk) begin
        if (load)    acc <= load_val;
        else if (en) acc <= acc + acc_t'(prod); // mở rộng dấu lên 32 bit
    end
endmodule
