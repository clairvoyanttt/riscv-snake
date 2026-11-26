.text
# A independent diagnostic ROM. B is not required for this test.
# All addresses below are CPU byte addresses.
addi t0, zero, 1
slli t0, t0, 12          # MMIO base 0x1000
addi t1, zero, 85
sw t1, 0(zero)          # RAM[0] sentinel 0x55
addi t1, zero, 102
sw t1, 8(zero)          # RAM[8] sentinel 0x66
lw t2, 0(t0)            # temporary EVENTS input = 2
sw t2, 1280(zero)       # result record RAM[0x500]
sw t2, 4(t0)            # ACK
addi t1, zero, 1
sw t1, 8(t0)            # SCORE
addi t1, zero, 2
sw t1, 12(t0)           # STATE = paused
addi t1, zero, 392
sw t1, 16(t0)           # FOOD = 0x188
addi t1, zero, 1
slli t4, t1, 15
sw t1, 64(t0)           # ROW0 = 1
sw t4, 124(t0)          # ROW15 = 0x8000, consecutive MMIO stores
lw t3, 0(zero)
sw t3, 1284(zero)       # result record RAM[0x504]
lw t4, 8(zero)
sw t4, 1288(zero)       # result record RAM[0x508]
addi t5, zero, 2
bne t2, t5, failed
addi t5, zero, 85
bne t3, t5, failed
addi t5, zero, 102
bne t4, t5, failed
addi t6, zero, 6
slli t6, t6, 12
addi t6, t6, 13         # PASS = 0x600d
sw t6, 1292(zero)       # result record RAM[0x50c]
done:
jal zero, done
failed:
addi t6, zero, -1
sw t6, 1292(zero)
jal zero, failed
