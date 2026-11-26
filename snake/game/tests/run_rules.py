#!/usr/bin/env python3
"""Rule testbench for snake.hex (role C of the RISC-V snake project).

The published ROM may only use the 20 whitelisted instructions on the course
single-cycle CPU.  This testbench models exactly that machine:

  * 1024 words of instruction ROM, 1024 words of data RAM at 0x0000-0x0FFF
  * the SnakeIO register block at 0x1000-0x107F (EVENTS/ACK/SCORE/STATE/
    FOOD/ROW) with the button edge latch described in the plan
  * one instruction per clock cycle

It refuses any machine word outside the whitelist, so a pseudo instruction that
silently expanded into lui/auipc/ecall fails here instead of on the real CPU.

Run:  python snake/game/tests/run_rules.py
"""

import os
import sys

MASK32 = 0xFFFFFFFF
WHITELIST = (
    "add", "sub", "and", "or", "slt", "sltu",
    "addi", "andi", "ori", "xori", "slti", "slli", "srli", "srai",
    "lw", "sw", "beq", "bne", "jal", "jalr",
)


def load_hex(path):
    words = []
    with open(path, "r", encoding="ascii") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("v2.0") or line.startswith("#"):
                continue
            for token in line.replace(",", " ").split():
                words.append(int(token, 16) & MASK32)
    if not 1 <= len(words) <= 1024:
        raise ValueError("ROM must hold 1..1024 words, got %d" % len(words))
    return words


def sext(value, bits):
    sign = 1 << (bits - 1)
    value &= (1 << bits) - 1
    return value - (1 << bits) if value & sign else value


def s32(value):
    return value - (1 << 32) if value & 0x80000000 else value


def u32(value):
    return value & MASK32


class Cpu:
    """Minimal course-CPU model plus the SnakeIO contract."""

    def __init__(self, rom):
        self.rom = list(rom)
        self.ram = [0] * 1024          # words, byte addresses 0x000..0xFFF
        self.reg = [0] * 32
        self.pc = 0
        self.cycles = 0
        # device state
        self.buttons = 0
        self.prev_buttons = 0
        self.pending = 0
        self.new_edges = 0
        self.score = 0
        self.state = 0
        self.food = 0
        self.rows = [0] * 16
        self.writes = []

    # ---------------- memory / device access ----------------
    def read_word(self, addr):
        addr = u32(addr)
        if addr < 0x1000:
            return self.ram[(addr >> 2) & 0x3FF]
        if 0x1000 <= addr <= 0x107F:
            off = addr - 0x1000
            if off == 0:
                return self.pending          # EVENTS
            return 0                         # reserved indexes read zero
        return 0

    def write_word(self, addr, value):
        addr = u32(addr)
        value = u32(value)
        if addr < 0x1000:
            self.ram[(addr >> 2) & 0x3FF] = value
            return
        if not 0x1000 <= addr <= 0x107F:
            return                            # stray write: ignored
        off = addr - 0x1000
        self.writes.append((off, value))
        if off == 4:                          # ACK
            # a press in this same cycle survives the acknowledgement
            self.pending = (self.pending & ~value) | self.new_edges
        elif off == 8:
            self.score = value & 0xFF
        elif off == 12:
            self.state = value & 0x7
        elif off == 16:
            self.food = value
        elif 0x40 <= off < 0x80 and (off - 0x40) % 4 == 0:
            self.rows[(off - 0x40) // 4] = value & 0xFFFF

    # ---------------- execution ----------------
    def step(self):
        self.new_edges = self.buttons & ~self.prev_buttons
        self.pending |= self.new_edges
        self.prev_buttons = self.buttons

        ins = self.rom[self.pc] if self.pc < len(self.rom) else 0
        rd = (ins >> 7) & 0x1F
        rs1 = (ins >> 15) & 0x1F
        rs2 = (ins >> 20) & 0x1F
        funct3 = (ins >> 12) & 0x7
        funct7 = (ins >> 25) & 0x7F
        opcode = ins & 0x7F
        imm_i = sext(ins >> 20, 12)
        imm_s = sext(((ins >> 25) << 5) | ((ins >> 7) & 0x1F), 12)
        imm_b = sext(((ins >> 31) << 12) | (((ins >> 7) & 1) << 11) |
                     (((ins >> 25) & 0x3F) << 5) | (((ins >> 8) & 0xF) << 1), 13)
        imm_j = sext(((ins >> 31) << 20) | (((ins >> 12) & 0xFF) << 12) |
                     (((ins >> 20) & 1) << 11) | (((ins >> 21) & 0x3FF) << 1), 21)

        a = self.reg[rs1]
        b = self.reg[rs2]
        nxt = self.pc + 1

        if opcode == 0x33:
            if funct3 == 0x0 and funct7 == 0x00:
                value = a + b
            elif funct3 == 0x0 and funct7 == 0x20:
                value = a - b
            elif funct3 == 0x7 and funct7 == 0x00:
                value = a & b
            elif funct3 == 0x6 and funct7 == 0x00:
                value = a | b
            elif funct3 == 0x2 and funct7 == 0x00:
                value = int(s32(a) < s32(b))
            elif funct3 == 0x3 and funct7 == 0x00:
                value = int(a < b)
            else:
                raise AssertionError("illegal R-type at pc=%d word=%08x" % (self.pc, ins))
            self.reg[rd] = u32(value)
        elif opcode == 0x13:
            if funct3 == 0x0:
                value = a + imm_i
            elif funct3 == 0x7:
                value = a & u32(imm_i)
            elif funct3 == 0x6:
                value = a | u32(imm_i)
            elif funct3 == 0x4:
                value = a ^ u32(imm_i)
            elif funct3 == 0x2:
                value = int(s32(a) < imm_i)
            elif funct3 == 0x1:
                if funct7 != 0x00:
                    raise AssertionError("illegal slli at pc=%d" % self.pc)
                value = a << ((ins >> 20) & 0x1F)
            elif funct3 == 0x5:
                shamt = (ins >> 20) & 0x1F
                if funct7 == 0x00:
                    value = a >> shamt
                elif funct7 == 0x20:
                    value = s32(a) >> shamt
                else:
                    raise AssertionError("illegal srli/srai at pc=%d" % self.pc)
            else:
                raise AssertionError("illegal I-type at pc=%d word=%08x" % (self.pc, ins))
            self.reg[rd] = u32(value)
        elif opcode == 0x03:
            if funct3 != 0x2:
                raise AssertionError("only lw is allowed, pc=%d" % self.pc)
            self.reg[rd] = self.read_word(u32(a) + imm_i)
        elif opcode == 0x23:
            if funct3 != 0x2:
                raise AssertionError("only sw is allowed, pc=%d" % self.pc)
            self.write_word(u32(a) + imm_s, b)
        elif opcode == 0x63:
            if funct3 == 0x0:
                take = a == b
            elif funct3 == 0x1:
                take = a != b
            else:
                raise AssertionError("only beq/bne are allowed, pc=%d" % self.pc)
            if take:
                nxt = self.pc + imm_b // 4
        elif opcode == 0x6F:
            self.reg[rd] = (self.pc + 1) * 4
            nxt = self.pc + imm_j // 4
        elif opcode == 0x67:
            if funct3 != 0x0:
                raise AssertionError("only jalr is allowed, pc=%d" % self.pc)
            target = u32(a) + imm_i
            self.reg[rd] = (self.pc + 1) * 4
            nxt = target // 4
        else:
            raise AssertionError("opcode 0x%02x not in the whitelist, pc=%d" % (opcode, self.pc))

        self.reg[0] = 0
        self.pc = nxt
        self.cycles += 1

    def run(self, n):
        for _ in range(n):
            self.step()

    def run_until(self, predicate, limit=2_000_000):
        for _ in range(limit):
            if predicate(self):
                return
            self.step()
        raise AssertionError("cycle budget exhausted (pc=%d)" % self.pc)

    # ---------------- game-state helpers ----------------
    def ram_word(self, addr):
        return self.ram[(addr >> 2) & 0x3FF]

    def cell(self, index):
        return self.ram[index & 0xFF]

    def head_index(self):
        return self.ram_word(0x440)

    def tail_index(self):
        return self.ram_word(0x444)

    def length(self):
        return self.ram_word(0x448)

    def direction(self):
        return self.ram_word(0x44C)

    def head_cell(self):
        return self.cell(self.head_index())

    def row_mask(self, y):
        return self.ram_word(0x400 + 4 * y) & 0xFFFF

    def press(self, bits, hold=3, gap=80):
        self.buttons |= bits
        self.run(hold)
        self.buttons &= ~bits
        self.run(gap)

    def tap(self, bit, hold=3, gap=80):
        self.press(1 << bit, hold, gap)

    def next_move(self, limit=20000):
        """Run until the head index changes, then finish the period."""
        head = self.head_index()
        self.run_until(lambda c: c.head_index() != head, limit)
        self.run(200)

    def set_board(self, body, direction, food=0xFFFF, score=0, state=1, timer=8):
        """Install a fabricated position: body is listed tail..head.

        The game inits its own board at reset, so let the boot code run first
        and then overwrite RAM and the device registers.
        """
        self.run(600)
        self.ram[0:256] = [0] * 256
        for y in range(16):
            self.ram[(0x400 >> 2) + y] = 0
            self.rows[y] = 0
        for i, cell in enumerate(body):
            self.ram[i] = cell
            y, x = divmod(cell, 16)
            mask = self.ram[(0x400 >> 2) + y] | (1 << x)
            self.ram[(0x400 >> 2) + y] = mask
            self.rows[y] = mask
        self.ram[(0x440 >> 2)] = len(body) - 1
        self.ram[(0x444 >> 2)] = 0
        self.ram[(0x448 >> 2)] = len(body)
        self.ram[(0x44C >> 2)] = direction
        self.ram[(0x450 >> 2)] = direction
        self.ram[(0x454 >> 2)] = food
        self.ram[(0x458 >> 2)] = score
        self.ram[(0x45C >> 2)] = state
        self.ram[(0x460 >> 2)] = timer
        self.ram[(0x464 >> 2)] = 0
        self.ram[(0x468 >> 2)] = 0
        self.state = state
        self.score = score
        self.food = food if food != 0xFFFF else 0
        self.pending = 0
        self.buttons = 0
        self.prev_buttons = 0


def decode_all(words):
    """Static check: every word must be one of the 20 whitelisted instructions."""
    seen = set()
    for pc, ins in enumerate(words):
        opcode = ins & 0x7F
        funct3 = (ins >> 12) & 0x7
        funct7 = (ins >> 25) & 0x7F
        if opcode == 0x33:
            name = {0x0: ("sub" if funct7 == 0x20 else "add"),
                    0x7: "and", 0x6: "or", 0x2: "slt", 0x3: "sltu"}.get(funct3)
        elif opcode == 0x13:
            name = {0x0: "addi", 0x7: "andi", 0x6: "ori", 0x4: "xori", 0x2: "slti",
                    0x1: "slli", 0x5: ("srai" if funct7 == 0x20 else "srli")}.get(funct3)
        elif opcode == 0x03:
            name = "lw" if funct3 == 2 else None
        elif opcode == 0x23:
            name = "sw" if funct3 == 2 else None
        elif opcode == 0x63:
            name = {0x0: "beq", 0x1: "bne"}.get(funct3)
        elif opcode == 0x6F:
            name = "jal"
        elif opcode == 0x67:
            name = "jalr" if funct3 == 0 else None
        else:
            name = None
        if name is None or name not in WHITELIST:
            raise AssertionError("word %d (%08x) uses a forbidden instruction" % (pc, ins))
        seen.add(name)
    return seen


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    hex_path = os.path.join(here, os.pardir, "snake.hex")
    rom = load_hex(hex_path)

    results = []

    def check(name, fn):
        try:
            detail = fn() or ""
            results.append(True)
            print("PASS %s%s" % (name, ("  " + detail) if detail else ""))
        except AssertionError as err:
            results.append(False)
            print("FAIL %s: %s" % (name, err))

    # ---------- static instruction whitelist ----------
    def t_whitelist():
        seen = decode_all(rom)
        return "%d words, %d mnemonics: %s" % (len(rom), len(seen), " ".join(sorted(seen)))
    check("whitelist", t_whitelist)

    # ---------- T1 cold start ----------
    def t_cold():
        cpu = Cpu(rom)
        cpu.run(2000)
        assert cpu.ram_word(0x440) == 2, "head index"
        assert cpu.ram_word(0x444) == 0, "tail index"
        assert cpu.ram_word(0x448) == 3, "length"
        assert cpu.ram_word(0x44C) == 1, "direction"
        assert cpu.ram_word(0x454) == 0x88, "food cell"
        assert [cpu.cell(i) for i in range(3)] == [133, 134, 135], "initial body"
        assert cpu.row_mask(8) == 0x00E0, "row 8 mask"
        assert all(cpu.row_mask(y) == 0 for y in list(range(8)) + list(range(9, 16))), "other rows"
        assert cpu.state == 0, "STATE waits for the start key"
        assert cpu.score == 0, "SCORE is 0"
        assert cpu.food == 0x188, "FOOD enable and (8,8)"
        assert cpu.rows[8] == 0x00E0, "painted ROW8"
        assert all(cpu.rows[y] == 0 for y in list(range(8)) + list(range(9, 16))), "painted rows"
        assert cpu.reg[2] == 0x0FF0, "sp"
        return "ROW8=0x00E0 sp=0x%04X after %d cycles" % (cpu.reg[2], cpu.cycles)
    check("T1 cold start", t_cold)

    # ---------- T2 first food ----------
    def t_first_food():
        cpu = Cpu(rom)
        cpu.run(1500)
        cpu.tap(4)
        cpu.next_move()
        assert cpu.ram_word(0x44C) == 1, "still moving right"
        assert cpu.head_cell() == 136, "head at (8,8)"
        assert cpu.length() == 4, "length grew"
        assert cpu.score == 1, "score 01"
        assert cpu.row_mask(8) == 0x01E0, "row 8 becomes 0x01E0"
        assert cpu.rows[8] == 0x01E0, "painted ROW8"
        assert cpu.ram_word(0x454) == 137, "food cell (9,8)"
        assert cpu.food == 0x189, "FOOD = enable | 137"
        assert cpu.state == 1, "still running"
        return "ROW8=0x01E0 FOOD=0x189 SCORE=01"
    check("T2 first food", t_first_food)

    # ---------- T3 no reversal ----------
    def t_no_reversal():
        cpu = Cpu(rom)
        cpu.run(1500)
        cpu.tap(4)
        cpu.next_move()
        before = cpu.head_cell()
        cpu.tap(3)                      # left, opposite of right
        cpu.next_move()
        assert cpu.ram_word(0x44C) == 1, "reversal rejected, still right"
        assert cpu.head_cell() == before + 1, "one more cell to the right"
        before = cpu.head_cell()
        cpu.tap(0)                      # up is legal
        cpu.next_move()
        assert cpu.ram_word(0x44C) == 0, "up accepted"
        assert cpu.head_cell() == before - 16, "head moved up one row"
        return "left rejected, up accepted"
    check("T3 no reversal", t_no_reversal)

    # ---------- T4 enter the vacating tail cell ----------
    def t_vacating_tail():
        cpu = Cpu(rom)
        body = [0, 1, 17, 16]           # tail (0,0) .. head (0,1)
        cpu.set_board(body, 0)
        cpu.next_move()
        assert cpu.head_cell() == 0, "head entered the tail cell"
        assert cpu.tail_index() == 1, "tail advanced"
        assert cpu.length() == 4, "no growth"
        assert cpu.state == 1, "accepted, not a collision"
        assert cpu.row_mask(0) == 0x03, "row 0 keeps both bits"
        assert cpu.row_mask(1) == 0x03, "row 1 unchanged"
        assert cpu.rows[0] == 0x03 and cpu.rows[1] == 0x03, "painted rows"
        return "head (0,0) taken while the tail vacates it"
    check("T4 enter vacating tail", t_vacating_tail)

    # ---------- T5 self collision ----------
    def t_self_hit():
        cpu = Cpu(rom)
        body = [0, 1, 2, 33, 34, 18, 17]
        cpu.set_board(body, 2)
        cpu.run_until(lambda c: c.state != 1, 20000)
        cpu.run(100)
        assert cpu.state == 3, "STATE = fail"
        assert cpu.ram_word(0x44C) == 2, "direction kept"
        assert cpu.tail_index() == 0, "tail not advanced"
        assert cpu.row_mask(0) == 0x07, "row 0 mask preserved"
        assert cpu.row_mask(1) == 0x06, "row 1 mask preserved"
        assert cpu.row_mask(2) == 0x06, "row 2 mask preserved"
        assert cpu.rows[1] == 0x06 and cpu.rows[2] == 0x06, "frame preserved"
        return "STATE=3, last frame untouched"
    check("T5 self collision", t_self_hit)

    # ---------- T6..T9 walls ----------
    def wall_case(body, direction, label):
        def run():
            cpu = Cpu(rom)
            cpu.set_board(body, direction)
            cpu.run_until(lambda c: c.state != 1, 20000)
            cpu.run(100)
            assert cpu.state == 3, "STATE = fail"
            assert cpu.length() == len(body), "no growth"
            return "STATE=3 on the %s wall" % label
        return run
    check("T6 wall up", wall_case([37, 21, 5], 0, "top"))
    check("T7 wall right", wall_case([221, 237, 253], 1, "right"))
    check("T8 wall down", wall_case([213, 229, 245], 2, "bottom"))
    check("T9 wall left", wall_case([82, 81, 80], 3, "left"))

    # ---------- T10 pause freezes the snake ----------
    def t_pause():
        cpu = Cpu(rom)
        cpu.run(1500)
        cpu.tap(4)
        cpu.next_move()
        cpu.tap(4)                     # pause
        assert cpu.state == 2, "STATE = pause"
        head = cpu.head_cell()
        rows = list(cpu.rows)
        cpu.run(6000)                  # many movement intervals
        assert cpu.head_cell() == head, "head frozen"
        assert cpu.rows == rows, "frame frozen"
        assert cpu.state == 2, "still paused"
        cpu.tap(4)                     # resume
        assert cpu.state == 1, "STATE = run again"
        cpu.next_move()
        assert cpu.state == 1, "running after resume"
        return "frame held over 6000 cycles, then resumed"
    check("T10 pause and resume", t_pause)

    # ---------- T11 restart rebuilds the board ----------
    def t_restart():
        cpu = Cpu(rom)
        cpu.run(1500)
        cpu.tap(4)
        cpu.next_move()
        cpu.press(0x20)                # restart
        cpu.run_until(lambda c: c.state == 0, 400)
        assert cpu.pending == 0, "the restart event was acknowledged"
        assert cpu.score == 0, "SCORE = 0"
        assert cpu.food == 0x188, "FOOD back to (8,8)"
        assert cpu.row_mask(8) == 0x00E0, "row 8 reset"
        assert all(cpu.row_mask(y) == 0 for y in list(range(8)) + list(range(9, 16))), "rows cleared"
        assert [cpu.cell(i) for i in range(3)] == [133, 134, 135], "body reset"
        assert cpu.head_index() == 2 and cpu.tail_index() == 0, "ring reset"
        assert cpu.rows[8] == 0x00E0, "painted row 8"
        assert all(cpu.rows[y] == 0 for y in list(range(8)) + list(range(9, 16))), "painted rows cleared"
        return "restart clears rows, score and food"
    check("T11 restart", t_restart)

    # ---------- T12 restart beats start ----------
    def t_restart_priority():
        cpu = Cpu(rom)
        cpu.run(1500)
        cpu.tap(4)
        cpu.next_move()
        cpu.press(0x20 | 0x10)         # restart and start in the same sample
        cpu.run_until(lambda c: c.state == 0, 400)
        cpu.run(300)
        assert cpu.state == 0, "restart wins, the start key is dropped"
        return "simultaneous restart+start leaves STATE=wait"
    check("T12 restart priority", t_restart_priority)

    # ---------- T13 simultaneous keys, up first ----------
    def t_key_priority():
        cpu = Cpu(rom)
        cpu.run(1500)
        cpu.tap(4)
        cpu.next_move()
        head = cpu.head_cell()
        cpu.press(0x01 | 0x02)         # up and right together
        cpu.next_move()
        assert cpu.ram_word(0x44C) == 0, "up wins over right"
        assert cpu.head_cell() == head - 16, "head went up one row"
        return "up beats right in the same sample"
    check("T13 key priority up>right", t_key_priority)

    # ---------- T14 reversal rejected, the other key still applies ----------
    def t_reversal_plus_key():
        cpu = Cpu(rom)
        cpu.run(1500)
        cpu.tap(4)
        cpu.next_move()
        head = cpu.head_cell()
        cpu.press(0x08 | 0x01)         # left (a reversal) and up
        cpu.next_move()
        assert cpu.ram_word(0x44C) == 0, "up accepted, left dropped"
        assert cpu.head_cell() == head - 16, "head went up"
        return "left dropped, up applied"
    check("T14 reversal plus valid key", t_reversal_plus_key)

    # ---------- T15 one accepted turn per period ----------
    def t_turn_lock():
        cpu = Cpu(rom)
        cpu.run(1500)
        cpu.tap(4)
        cpu.next_move()
        head = cpu.head_cell()
        cpu.tap(0)                     # up
        cpu.tap(1)                     # right, still in the same period
        cpu.next_move()
        assert cpu.ram_word(0x44C) == 0, "the second key of one period is ignored"
        assert cpu.head_cell() == head - 16, "moved up"
        cpu.tap(1)                     # the next period accepts right again
        cpu.next_move()
        assert cpu.ram_word(0x44C) == 1, "next period accepts right"
        return "one turn per movement period"
    check("T15 turn lock", t_turn_lock)

    # ---------- T16 only one free cell left: full board wins ----------
    def t_full_board():
        seq = []
        for y in range(16):
            row = [y * 16 + x for x in range(16)]
            seq.extend(row if y % 2 == 0 else row[::-1])
        body = seq[:255]
        free = seq[255]
        head = body[-1]
        hy, hx = divmod(head, 16)
        fy, fx = divmod(free, 16)
        direction = 0 if fy < hy else (2 if fy > hy else (1 if fx > hx else 3))
        cpu = Cpu(rom)
        cpu.set_board(body, direction, food=free, score=254)
        cpu.run_until(lambda c: c.state != 1, 200000)
        cpu.run(100)
        assert cpu.state == 4, "STATE = win"
        assert cpu.length() == 256, "length 256"
        assert cpu.score == 255, "last food scored"
        assert cpu.food == 0, "food hidden"
        assert cpu.row_mask(fy) & (1 << fx), "last cell painted"
        cpu.press(0x20)                # restart from the win screen
        cpu.run_until(lambda c: c.state == 0, 400)
        assert cpu.row_mask(8) == 0x00E0, "restart clears the full board"
        assert cpu.score == 0 and cpu.food == 0x188, "score and food reset"
        assert cpu.head_index() == 2 and cpu.length() == 3, "ring reset"
        return "STATE=4 after %d cycles, 256 cells, food hidden, restart works" % cpu.cycles
    check("T16 full board win", t_full_board)

    # ---------- T17 holding a key is one event only ----------
    def t_hold_once():
        cpu = Cpu(rom)
        cpu.run(1500)
        cpu.buttons |= 0x10            # hold start for many periods
        cpu.run(4000)
        cpu.buttons &= ~0x10
        cpu.run(200)
        assert cpu.state == 1, "still running: the held key did not toggle again"
        assert cpu.pending == 0, "event consumed by the ACK write"
        cpu.next_move()
        assert cpu.state == 1, "one start event, one transition"
        return "hold 4000 cycles -> single event, ACK clears it"
    check("T17 hold one event", t_hold_once)

    # ---------- T18 direction keys are ignored before the start ----------
    def t_wait_ignores_dir():
        cpu = Cpu(rom)
        cpu.run(1500)
        cpu.press(0x01)                # up while still waiting
        assert cpu.ram_word(0x44C) == 1, "direction unchanged while waiting"
        cpu.tap(4)                     # start
        cpu.next_move()
        assert cpu.ram_word(0x44C) == 1, "first step still goes right"
        assert cpu.head_cell() == 136, "first step scores at (8,8)"
        assert cpu.score == 1, "score 01"
        return "waiting board ignores direction keys, first step eats"
    check("T18 waiting ignores direction", t_wait_ignores_dir)

    # ---------- T19 food scan wraps to the low cells ----------
    def t_food_wrap():
        cpu = Cpu(rom)
        cpu.set_board([252, 253, 254], 1, food=255, score=5)
        cpu.next_move()
        assert cpu.length() == 4 and cpu.score == 6, "ate the food at (15,15)"
        assert cpu.row_mask(15) == 0xF000, "row 15 holds x=12..15"
        assert cpu.ram_word(0x454) == 0, "scan wrapped to cell 0"
        assert cpu.food == 0x100, "FOOD = enable | cell 0"
        return "food wrapped from cell 255 to cell 0"
    check("T19 food scan wrap", t_food_wrap)

    # ---------- T20 head and tail in different rows: two row writes ----------
    def t_two_rows():
        cpu = Cpu(rom)
        cpu.set_board([37, 53], 2)
        cpu.next_move()
        assert cpu.head_cell() == 69, "head at (5,4)"
        assert cpu.row_mask(2) == 0, "vacated row 2 cleared"
        assert cpu.row_mask(3) == 0x20, "row 3 keeps the body"
        assert cpu.row_mask(4) == 0x20, "row 4 painted"
        assert cpu.rows[2] == 0 and cpu.rows[3] == 0x20 and cpu.rows[4] == 0x20, "painted rows"
        assert cpu.rows[5] == 0, "untouched row not rewritten"
        return "rows 2 and 4 rewritten, row 3 kept"
    check("T20 two row render", t_two_rows)

    # ---------- T21 a reversal key is skipped, the next valid key applies ----------
    def t_skip_reversal():
        cpu = Cpu(rom)
        cpu.set_board([53, 69], 2)     # head (5,4) moving down
        cpu.press(0x01 | 0x02)         # up (reversal of down) and right
        cpu.next_move()
        assert cpu.ram_word(0x44C) == 1, "up skipped, right accepted"
        assert cpu.head_cell() == 70, "head moved right"
        return "up (a reversal of down) skipped, right applied"
    check("T21 skip reversal key", t_skip_reversal)

    # ---------- speed probe ----------
    def t_speed():
        cpu = Cpu(rom)
        cpu.run(1500)
        cpu.tap(4)
        marks = []
        start = cpu.cycles
        for _ in range(3):
            head = cpu.head_index()
            cpu.run_until(lambda c: c.head_index() != head, 20000)
            marks.append(cpu.cycles)
        intervals = [marks[0] - start] + [marks[i] - marks[i - 1] for i in range(1, len(marks))]
        per_iter = intervals[-1] / 60.0      # MOVE_TICKS is 60 in snake.asm
        return "cycles between moves %s, %.1f instructions per poll iteration" % (
            intervals, per_iter)
    check("speed probe", t_speed)

    passed = sum(1 for ok in results if ok)
    print("\n%d/%d checks passed" % (passed, len(results)))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
