.text
# ==================================================================
# snake.asm - 16x16 snake game for the course single-cycle RISC-V CPU
# Role C of the team project. Published ROM: only the .text segment.
#
# Machine instructions used (20, all from the project whitelist):
#   add sub and or slt sltu
#   addi andi ori xori slti slli srli srai
#   lw sw beq bne jal jalr
# No ecall, no lui/auipc, no variable sll/srl/sra, no blt/bge, no xor.
# Any 1<<x is built by the sh1_bit loop; signed compares use slt + branches.
#
# CPU byte addresses (all word aligned, data RAM 0x0000-0x0FFF):
#   0x0000-0x03FF  snake ring queue, 256 entries of 32 bit, slot i at 4*i
#   0x0400-0x043F  16 row occupancy masks, row y at 0x400+4*y
#   0x0440        head index (0..255)
#   0x0444        tail index
#   0x0448        length
#   0x044C        current direction (last executed move)
#   0x0450        pending direction
#   0x0454        food cell (16*y+x)
#   0x0458        score
#   0x045C        run state 0 wait / 1 run / 2 pause / 3 fail / 4 win
#   0x0460        move timer (poll iterations left before next step)
#   0x0464        turn lock (1 = a turn is already accepted this period)
#   0x0468        second row offset to render (4*ty, or 4*ny when only one)
#   0x0500-0x07FF workspace, 0x0800-0x0FFF stack, top 0x0FF0
#   0x1000-0x107F MMIO (s0 relative): +0 EVENTS +4 ACK +8 SCORE
#                  +12 STATE +16 FOOD +64 ROW0, row y at +64+4*y
#
# dir encoding: 0 up, 1 right, 2 down, 3 left.  cell = 16*y+x, bit x of row y.
# ==================================================================

.eqv MOVE_TICKS 60          # poll iterations per snake step (speed knob)

# ------------------------------------------------------------------
# Main loop
# ------------------------------------------------------------------
_start:
	addi sp, zero, 1
	slli sp, sp, 12          # sp = 0x1000
	addi sp, sp, -16         # sp = 0x0FF0, 16 byte aligned
	addi s0, zero, 1
	slli s0, s0, 12          # s0 = 0x1000 MMIO base
	addi s1, zero, 1024      # s1 = 0x0400 row mask base
	addi s3, zero, 1088      # s3 = 0x0440 state base
	jal ra, ig_init

ml_loop:
	jal ra, pi_poll          # sample and consume pending key events
	lw t0, 28(s3)            # run state
	addi t1, zero, 1
	bne t0, t1, ml_loop      # not running: keep polling only
	lw t0, 32(s3)            # move timer
	addi t0, t0, -1
	sw t0, 32(s3)
	bne t0, zero, ml_loop    # timer not expired
	jal ra, sg_step          # one movement period
	addi t0, zero, MOVE_TICKS
	sw t0, 32(s3)
	jal zero, ml_loop

# ------------------------------------------------------------------
# Device access (all MMIO touches are s0 relative, inside these procs)
# ------------------------------------------------------------------
pi_poll:
	addi sp, sp, -8
	sw ra, 0(sp)
	lw t0, 0(s0)             # EVENTS
	sw t0, 4(s0)             # ACK: write the mask just read
	beq t0, zero, pi_ret     # nothing pending
	andi t1, t0, 32          # bit5 restart has top priority
	beq t1, zero, pi_sp
	jal ra, ig_init          # restart: back to the waiting board
	jal zero, pi_ret

pi_sp:                       # 0x10 start / pause
	andi t1, t0, 16
	beq t1, zero, pi_dir
	lw t2, 28(s3)
	beq t2, zero, pi_go      # 0 wait  -> run
	addi t3, zero, 1
	beq t2, t3, pi_pause     # 1 run   -> pause
	addi t3, zero, 2
	beq t2, t3, pi_go        # 2 pause -> run
	jal zero, pi_ret         # 3 fail / 4 win: only restart works

pi_pause:
	addi t3, zero, 2
	sw t3, 28(s3)
	sw t3, 12(s0)            # STATE = pause
	jal zero, pi_ret

pi_go:
	addi t3, zero, 1
	sw t3, 28(s3)
	sw t3, 12(s0)            # STATE = run
	addi t3, zero, MOVE_TICKS
	sw t3, 32(s3)            # reload the move timer
	jal zero, pi_ret

pi_dir:                      # bits 0..3 up right down left, first valid wins
	lw t2, 28(s3)
	addi t3, zero, 1
	bne t2, t3, pi_ret       # direction keys only while running
	lw t2, 36(s3)            # turn lock
	bne t2, zero, pi_ret     # one accepted turn per movement period
	andi t1, t0, 15          # pending direction bits only
	addi t4, zero, 0         # candidate direction, 0 = up
	beq t1, zero, pi_ret
pi_dir_loop:                 # walk up, right, down, left on the shifted mask
	andi t5, t1, 1
	beq t5, zero, pi_dir_next
	lw t2, 12(s3)            # last executed direction
	xori t3, t2, 2           # opposite direction
	beq t4, t3, pi_dir_next  # a reversal is skipped, try the next key
	sw t4, 16(s3)            # pending direction
	addi t3, zero, 1
	sw t3, 36(s3)            # lock this movement period
	jal zero, pi_ret
pi_dir_next:
	srli t1, t1, 1
	addi t4, t4, 1
	addi t5, zero, 4
	bne t4, t5, pi_dir_loop
pi_ret:
	lw ra, 0(sp)
	addi sp, sp, 8
	jalr zero, 0(ra)

# ------------------------------------------------------------------
# Rules: init a deterministic board
# ------------------------------------------------------------------
ig_init:
	addi t2, zero, 0         # byte offset
	addi t1, zero, 16
ig_clr:
	add t3, s1, t2
	sw zero, 0(t3)           # RAM row mask = 0
	add t4, s0, t2
	sw zero, 64(t4)          # ROW y = 0, clears any old picture
	addi t2, t2, 4
	addi t1, t1, -1
	bne t1, zero, ig_clr

	addi t0, zero, 133       # tail  (5,8), cell = 16*y+x
	sw t0, 0(zero)
	addi t0, zero, 134       # mid   (6,8)
	sw t0, 4(zero)
	addi t0, zero, 135       # head  (7,8)
	sw t0, 8(zero)
	addi t0, zero, 224       # 0x00E0: bits 5,6,7 of row 8
	sw t0, 32(s1)
	sw t0, 96(s0)            # ROW8 = 0x00E0

	addi t0, zero, 2
	sw t0, 0(s3)             # head index
	sw zero, 4(s3)           # tail index
	addi t0, zero, 3
	sw t0, 8(s3)             # length
	addi t0, zero, 1
	sw t0, 12(s3)            # dir = right
	sw t0, 16(s3)            # pending = right
	addi t0, zero, 136       # food cell (8,8)
	sw t0, 20(s3)
	sw zero, 24(s3)          # score
	sw zero, 28(s3)          # state = wait
	sw zero, 32(s3)          # timer
	sw zero, 36(s3)          # turn lock
	sw zero, 40(s3)          # second render row

	sw zero, 8(s0)           # SCORE = 00
	addi t0, zero, 392       # 0x188 = enable | (8,8)
	sw t0, 16(s0)            # FOOD
	sw zero, 12(s0)          # STATE waits last, so the panel is consistent
	jalr zero, 0(ra)

# ------------------------------------------------------------------
# Rules: 1<<x for variable x (the only way, variable sll is not supported)
# ------------------------------------------------------------------
sh1_bit:                     # in a0 = x (0..15), out a1 = 1<<x
	addi a1, zero, 1
	beq a0, zero, sh1_ret
sh1_loop:
	slli a1, a1, 1
	addi a0, a0, -1
	bne a0, zero, sh1_loop
sh1_ret:
	jalr zero, 0(ra)

# ------------------------------------------------------------------
# Rules: one movement period
# ------------------------------------------------------------------
sg_step:
	addi sp, sp, -8
	sw ra, 0(sp)
	lw t4, 16(s3)            # pending direction becomes the executed one
	sw t4, 12(s3)
	sw zero, 36(s3)          # unlock: next period accepts a new turn
	lw t0, 0(s3)             # head index
	slli a0, t0, 2
	lw t1, 0(a0)             # head cell
	andi t2, t1, 15          # x
	srli t3, t1, 4           # y

	beq t4, zero, sg_up
	addi t5, zero, 1
	beq t4, t5, sg_right
	addi t5, zero, 2
	beq t4, t5, sg_down
	beq t2, zero, sg_fail    # left, x == 0 hits the wall
	addi t5, t1, -1
	jal zero, sg_move

sg_up:
	beq t3, zero, sg_fail    # y == 0 hits the wall
	addi t5, t1, -16
	jal zero, sg_move

sg_right:
	addi t6, zero, 15
	beq t2, t6, sg_fail      # x == 15 hits the wall
	addi t5, t1, 1
	jal zero, sg_move

sg_down:
	addi t6, zero, 15
	beq t3, t6, sg_fail      # y == 15 hits the wall
	addi t5, t1, 16

sg_move:                     # t5 = new head cell
	srli a2, t5, 4
	slli a2, a2, 2           # a2 = 4*y, the row offset used all over
	andi a0, t5, 15
	jal ra, sh1_bit          # a1 = bit of the new head
	add t6, s1, a2
	lw a3, 0(t6)             # current row mask
	and a4, a3, a1
	beq a4, zero, sg_free    # cell is empty
	lw a4, 20(s3)
	beq t5, a4, sg_free      # an eaten cell is never occupied
	lw a4, 4(s3)             # tail index
	slli a4, a4, 2
	lw a4, 0(a4)             # tail cell
	beq t5, a4, sg_free      # may enter the cell the tail vacates now
	jal zero, sg_fail

sg_free:
	lw a4, 20(s3)            # food cell
	beq t5, a4, sg_grow      # eating: keep the tail
	lw a5, 4(s3)             # tail index
	slli a4, a5, 2
	lw a4, 0(a4)             # tail cell
	addi a5, a5, 1
	andi a5, a5, 255
	sw a5, 4(s3)             # advance the ring tail
	srli a6, a4, 4
	slli a6, a6, 2           # a6 = 4*ty
	sw a6, 40(s3)
	andi a0, a4, 15
	jal ra, sh1_bit
	xori a1, a1, -1          # one bit complement
	add a5, s1, a6
	lw a4, 0(a5)
	and a4, a4, a1
	sw a4, 0(a5)             # clear the vacated tail bit
	jal zero, sg_head

sg_grow:
	sw a2, 40(s3)            # only the head row changes

sg_head:                     # set the head bit, then push the ring head
	andi a0, t5, 15
	jal ra, sh1_bit          # recompute, the tail path clobbered a1
	add t6, s1, a2
	lw a3, 0(t6)
	or a3, a3, a1
	sw a3, 0(t6)
	addi t0, t0, 1
	andi t0, t0, 255
	sw t0, 0(s3)             # new head index
	slli t0, t0, 2
	sw t5, 0(t0)             # queue[head] = new cell

	lw a4, 20(s3)
	bne t5, a4, sg_render    # no food here, done
	lw a4, 8(s3)             # length
	addi a4, a4, 1
	sw a4, 8(s3)
	lw a5, 24(s3)            # score
	addi a5, a5, 1
	sw a5, 24(s3)
	sw a5, 8(s0)             # SCORE = low 8 bits of the score
	addi a6, zero, 256
	beq a4, a6, sg_win       # 256 cells: board full

	sw zero, 20(s3)          # hunt a free cell, scanning forward from the head
	addi a4, zero, 0
sg_scan:
	add a5, t5, a4
	andi a5, a5, 255
	andi a0, a5, 15
	jal ra, sh1_bit
	srli a0, a5, 4
	slli a0, a0, 2
	add a0, s1, a0
	lw a0, 0(a0)
	and a0, a0, a1
	beq a0, zero, sg_found
	addi a4, a4, 1
	addi a0, zero, 256
	bne a4, a0, sg_scan
	sw zero, 16(s0)          # no free cell: only reachable when full
	jal zero, sg_render
sg_found:
	sw a5, 20(s3)            # food cell
	addi a0, zero, 256
	add a0, a0, a5           # 0x100 | cell
	sw a0, 16(s0)
	jal zero, sg_render

sg_win:
	addi a6, zero, 4
	sw a6, 28(s3)
	sw a6, 12(s0)            # STATE = win
	sw zero, 16(s0)          # hide the food

sg_render:                   # write only the rows that changed
	add t6, s0, a2
	add a5, s1, a2
	lw a4, 0(a5)
	sw a4, 64(t6)            # ROW y of the head
	lw a6, 40(s3)
	beq a6, a2, sg_done      # head and tail in the same row: one write
	add t6, s0, a6
	add a5, s1, a6
	lw a4, 0(a5)
	sw a4, 64(t6)            # ROW y of the vacated tail
sg_done:
	lw ra, 0(sp)
	addi sp, sp, 8
	jalr zero, 0(ra)

sg_fail:                     # keep the last frame, light the fail lamp
	addi a4, zero, 3
	sw a4, 28(s3)
	sw a4, 12(s0)            # STATE = fail
	jal zero, sg_done
