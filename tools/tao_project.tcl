# tao_project.tcl - Tao project Vivado TINY_MNIST tu thu muc TONG_HOP_Tiny (dung tren may moi)
# Cach chay: mo Vivado, trong Tcl Console go
#     source <duong dan toi>/TONG_HOP_Tiny/tools/tao_project.tcl
# Project duoc tao canh thu muc TONG_HOP_Tiny:  <cha>/TINY_MNIST/TINY_MNIST.xpr
# (dung vi tri nay thi trang web pc/tinyml_web.py tu tim thay project)
set T [file normalize [file join [file dirname [info script]] ..]]
set P [file normalize [file join $T .. TINY_MNIST]]
if {[file exists [file join $P TINY_MNIST.xpr]]} {
    error "Da co project $P/TINY_MNIST.xpr, khong tao de. Xoa hoac doi ten thu muc do neu muon tao lai."
}
create_project TINY_MNIST $P -part xc7a100tcsg324-1
set_property target_language Verilog [current_project]
add_files -norecurse -fileset sources_1 [glob $T/rtl/*.sv]
add_files -norecurse -fileset constrs_1 [glob $T/constr/*.xdc]
add_files -norecurse -fileset sim_1 [concat [glob $T/tb/*.sv] [glob $T/gen/test_*.mem]]
set_property top nexys_a7_top  [get_filesets sources_1]
set_property top tb_tinyml_top [get_filesets sim_1]
update_compile_order -fileset sources_1
update_compile_order -fileset sim_1
puts "Xong: $P/TINY_MNIST.xpr (top nexys_a7_top, sim top tb_tinyml_top)"
