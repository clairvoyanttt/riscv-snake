# RISC-V 贪吃蛇

硬件综合训练三人团队项目，基于自制单周期 RISC-V CPU，在课程版 Logisim 中运行 16×16 贪吃蛇。

## 开工说明

先阅读 [三人协作计划书](docs/三人协作计划书.md)，再使用其中对应角色的 Agent 启动指令。

| 角色 | 工作范围 | 实现目录 |
|---|---|---|
| A | CPU 访存、外设译码、整机集成和打包 | snake/system/ |
| B | 按键事件、点阵、食物、分数和状态显示 | snake/io/ |
| C | 游戏汇编、规则测试和 ROM 导出 | snake/game/ |

三人按计划书第 3 节共用接口，独立验证模块后进行联调。A 维护最终电路，B 交付独立外设，C 交付汇编与 ROM。

## 当前进度

已完成三人协作计划及 A 的独立 CPU/MMIO 接入与诊断 ROM，原生仿真通过，课程版 GUI 已打开并运行诊断。B 外设和 C 游戏程序待接入。

从 [A 阶段运行与交接](snake/运行与演示.md) 开始，打开 `snake/system/SnakeSystem.circ` 可运行内嵌诊断 ROM。课程基础电路、两个依赖 JAR、课程版 Logisim 和 RARS 的分发清单见计划书第 2 节。

后续可分别使用 feat/cpu-system、feat/io-panel、feat/snake-game 分支提交各自的模块。
