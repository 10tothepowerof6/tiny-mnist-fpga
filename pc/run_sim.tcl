# run_sim.tcl - trang web goi file nay:
#   vivado -mode batch -source run_sim.tcl -tclargs <file .xpr> [file anh_vao.txt]
# Co file anh_vao.txt thi testbench doc bo mau do (+ANH_VAO), khong thi dung 20 anh co san.
set xpr [lindex $argv 0]
set anh [lindex $argv 1]
open_project $xpr
set sim [get_filesets sim_1]
set_property top tb_tinyml_top $sim
if {$anh ne ""} {
    set_property -name {xsim.simulate.xsim.more_options} -value "-testplusarg ANH_VAO=$anh" -objects $sim
} else {
    set_property -name {xsim.simulate.xsim.more_options} -value "" -objects $sim
}
launch_simulation -simset sim_1 -mode behavioral
run all
close_sim
set_property -name {xsim.simulate.xsim.more_options} -value "" -objects $sim
close_project
