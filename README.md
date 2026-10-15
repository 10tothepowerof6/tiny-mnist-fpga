# TinyML MNIST Accelerator on FPGA

A lightweight hardware accelerator for MNIST handwritten digit recognition implemented on FPGA (Digilent Basys 3) using an 8-bit quantized Multilayer Perceptron (MLP).

## Overview

This project consists of an end-to-end TinyML hardware-software co-design:
- **Software (AI)**: Model training in Python, post-training 8-bit quantization (`int8`), and target ROM export (`.mem`/`.coe`).
- **Hardware (RTL)**: SystemVerilog implementation featuring parallel MAC execution units, ReLU activation, re-quantization logic, and UART interface.

## Repository Structure

```text
tinyml-fpga/
├── ai/          # Python scripts for training, quantization, and serial interface
├── rtl/         # SystemVerilog source code for FPGA hardware design
├── gen/         # Output directory for generated ROM weights and test vectors
├── tb/          # Simulation testbenches and verification scripts
└── README.md
```

## Hardware Architecture

- **Target Board**: Digilent Basys 3 (Xilinx Artix-7 XC7A35T)
- **Model Architecture**: MLP 784 -> 32 -> 10
- **Data Format**: Symmetric 8-bit Signed Integers (`int8`)
- **Host Communication**: UART at 115200 baud rate

## Status

Initial repository setup. Active development in progress.