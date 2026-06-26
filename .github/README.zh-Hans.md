[English](../README.md) · [繁體中文](README.zh-Hant.md) · **简体中文**

# altium-kicad-cli — 读取 Altium .SchDoc 与 KiCad .kicad_sch、运行 ERC、绘制 KiCad（无需安装 EDA）

**altium-kicad-cli**（CLI 命令 `akcli`，导入包 `altium_kicad_cli`）是一套零依赖的
Python 工具包与 Claude Code 插件，可在**未安装 Altium 或 KiCad** 的情况下读取
**Altium 二进制 `.SchDoc` / `.SchLib` / `.PcbDoc`** **以及** **KiCad `.kicad_sch` / `.kicad_sym` / `.kicad_pcb`**，
并从命令行运行 ERC / power / pinmap / BOM / diff 等检查，以及依据 JSON 操作列表（op-list）绘制 KiCad 原理图。
它专为 AI 编码代理（coding agent）而打造。

它将两种格式读入同一个归一化模型并对其进行*分析*——解析、检查、比对（diff）、绘制——
为你提供可脚本化、免安装的工作流，让自动化流水线或 LLM 代理都能驱动它。

[![CI](https://github.com/tipoLi5890/altium-kicad-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/tipoLi5890/altium-kicad-cli/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## 亮点

- **两种格式，一个模型。** Altium 二进制 `.SchDoc` 与 KiCad `.kicad_sch` 都会归一化到同一个
  `Schematic`/`Pcb`/`Library` 模型，因此每一项检查、比对和报告都与格式无关。
- **无需安装 EDA。** 纯标准库实现的 OLE2/CFBF + Altium 记录解码，以及一个迭代式的 KiCad
  S-expression 解析器。无需 Altium、无需 KiCad、无需编译扩展——只要 Python ≥ 3.11。
- **零运行时依赖。** 仅使用标准库（包括 `tomllib`）。易于内嵌（vendor）、沙箱化或在 CI 中运行。
- **值得信赖的网络（net）推断。** 重建的 net 层可处理全局同名合并、连接点（junction）、
  T 型连接点和 No-ERC 标记——修复了经典的「同名 net 被拆成单引脚 net」缺陷。
- **对 Altium 只读、对 KiCad 安全写入。** Altium 文件在离线状态下永不被修改；KiCad 写入会经过
  原子化的 快照 → 临时文件 → 校验 → 替换 流水线，并由纯 Python 的连通性闸门把关。
- **AI 代理原生。** 以 Claude Code 插件形式发布，附带 skills/commands，输出带有
  `schema_version` 的结构化 JSON，并接受带版本号的 op-list 以实现确定性、幂等的编辑。

## 在未安装 Altium 的情况下读取 .SchDoc / .SchLib / .PcbDoc

`akcli` 直接打开 Altium 二进制文件。它内含一个加固的 OLE2/CFBF（复合文件二进制格式，
Compound File Binary Format）容器读取器以及一个 Altium 记录解码器——无需 Altium Designer、
无需 Windows、无需许可证。

```bash
akcli read   hardware/insole/main.SchDoc        # 将 .SchDoc 解析为归一化 JSON
akcli net    hardware/insole/main.SchDoc         # 提取网表（net -> pins）
akcli component hardware/insole/main.SchDoc       # 列出元件 / 位号（designator）/ 值
```

支持的 Altium 输入：`.SchDoc`（原理图）、`.SchLib`（符号库）、`.PcbDoc`（电路板——
v1 支持 ASCII 的 `Nets6`/`Components6`/`Classes6`/`Rules6` 段；二进制的焊盘/走线段会被
明确拒绝而非误解析）。所有 Altium 访问均为**只读**。

## 解析 KiCad .kicad_sch / .kicad_sym / .kicad_pcb（S-expression）

同一个 CLI 用一个显式栈（非递归）的分词器解析 KiCad 的 S-expression 格式，
该分词器对深度、原子（atom）和节点都设有上限——因此格式错误或恶意构造的文件无法撑爆调用栈。

```bash
akcli read hardware/board.kicad_sch              # .kicad_sch -> 归一化 JSON
akcli net  hardware/board.kicad_sch              # net 成员关系，共用 net 引擎
```

KiCad 的引脚电气类型在读取时从 `lib_symbols` 解析得到（实例引脚不携带类型），
因此 ERC 拥有所需数据。KiCad 7 与 KiCad 8 的文件都受支持。

## 从命令行运行 ERC 和设计检查（power、pinmap、BOM、diff）

无需打开任何 EDA 工具即可运行电气规则检查（ERC）及其他设计检查：

```bash
akcli check  main.SchDoc                          # ERC-lite + power + BOM 卫生检查
akcli pinmap main.SchDoc -C altium-kicad-cli.toml # MCU 引脚 -> net（+ 可选的预期表）
akcli diff   v1.SchDoc v2.SchDoc                   # 基于 net 成员关系的 diff，而非基于名称
```

power/ground 检测是**基于 net 名称 + power 端口（power-port）**的，而非纯粹基于电气类型，
因为真实电路板上以 `Passive` 引脚为主——一个仅看类型的朴素 ERC 会产生空洞的「通过」结果。
每份报告都会打印一个元数据头（passive 引脚占比、被抑制的 No-ERC 数量、未命名 net 数量、
分数坐标的存在情况），因此一个干净的结果永远不会被误认为空结果。

## 依据 op-list 绘制 / 写入 KiCad 原理图（.kicad_sch）

`akcli` 依据带版本号的 JSON **op-list**（放置元件、导线、连接点、标签、power 端口、文本……）
写入 KiCad 原理图。写入是精准且幂等的（确定性 UUIDv5），由纯 Python 连通性校验器把关，
并要求显式 `--apply`（默认为 dry run）。

```bash
akcli plan  ops.json --target board.kicad_sch     # 校验 op-list，显示将会改动的内容
akcli draw  ops.json --target board.kicad_sch     # 默认 dry-run（不写入文件）
akcli draw  ops.json --target board.kicad_sch --apply   # 原子写入 + 校验 + 备份
```

Altium 的*写入/绘制*仅通过可选的 Windows live driver（需运行 Altium 22+）提供；
离线状态下，Altium 仅支持分析。

## 作为 Claude Code 插件 / 与 AI 编码代理一起使用（及 MCP 路线图）

安装 Claude Code 插件后，你的代理便获得 `/altium-kicad:circuit-review`、
`circuit-pinmap`、`circuit-draw` 和 `circuit-diff` 命令，外加一个 circuit-design skill，
它们底层全都调用 `akcli`。每条命令都输出携带 `schema_version` 的结构化 JSON（`--json`），
op-list 则携带 `protocol_version`，因此代理输出始终可被机器校验且幂等。

一个面向 Altium/KiCad 的原生 **MCP 服务器**已列入路线图（见下文）；如今的集成接口是
Claude Code 插件 + `akcli` CLI，任何代理都可对其进行 shell 调用。

## 安装（akcli CLI + 插件）

```bash
# CLI（推荐）：通过 pipx 隔离安装
pipx install altium-kicad-cli
akcli --version

# 或从 clone 直接运行，无需安装（零运行时依赖）
git clone https://github.com/tipoLi5890/altium-kicad-cli
./altium-kicad-cli/bin/akcli --help
```

Claude Code 插件（marketplace 名称为 `altium-kicad`）：

```text
/plugin marketplace add tipoLi5890/altium-kicad-cli
/plugin install altium-kicad@altium-kicad
```

完整细节与故障排查见 [INSTALL.md](../INSTALL.md)。需要 **Python ≥ 3.11**（用于标准库
`tomllib`）；若你默认的 `python3` 版本过旧，`bin/akcli` 包装器会自动选择一个足够新的解释器。

## 路线图 / 状态

> **状态：pre-alpha / 正在积极建设中。** 本仓库目前包含已冻结的实现规范
> （[`docs/SPEC.md`](../docs/SPEC.md)），并正按里程碑（milestone）逐步构建。**目前尚无 PyPI 发布**，
> 上文的徽章/命令描述的是*目标*行为。请将下表中任何未标记为 **Shipped** 的功能视为尚不可用。

| 能力 | 里程碑 | 状态 |
|---|---|---|
| 基础：模型、ops、错误、安全、单位、配置、schemas、插件脚手架 | MS0 | 进行中 |
| README / SEO / 文档 / CI 矩阵 | MS1 | 进行中 |
| Altium `.SchDoc` 读取 + 重建的 net 推断（STAT/LED1 合并修复） | MS2 | 计划中 |
| 检查（ERC/power/BOM/diff/pinmap）+ CLI 核心 | MS3 | 计划中 |
| KiCad `.kicad_sch` 读取（v7/v8） | MS4 | 计划中 |
| 依据 op-list 写入/绘制 KiCad（连通性闸门、幂等） | MS5 | 计划中 |
| `.SchLib` / `.PcbDoc`（ASCII）读取 | MS6 | 计划中 |
| Claude Code skill + commands + DTS/pinout 适配器 | MS7 | 计划中 |
| **可选** Altium live driver（Windows + Altium 22+） | MS8 | 计划中（仅 Windows） |
| 原生 MCP 服务器 | post-1.0 | 设想 / 路线图 |

**明确推迟（不在 v1 中）：** 离线的 Altium *写入*；以 Altium 为权威的 ERC/网表（需要运行中的
Altium）；Altium `.PcbDoc` 二进制段（焊盘/走线/过孔/圆弧/填充/区域）；分层 / 多图纸的 KiCad
写入（v1 仅支持扁平结构）。详见 `docs/SPEC.md` §8 的风险登记册（Risk register）。

## 常见问题（FAQ）

### 如何在未安装 Altium 的情况下读取/打开 Altium .SchDoc 文件？
要在未安装 Altium 的情况下读取或打开 Altium `.SchDoc` 文件，运行 `akcli read file.SchDoc`
（或 `akcli net file.SchDoc` 获取网表）。`akcli` 是一个零依赖的 Python 工具，直接解码
Altium 二进制 OLE2/CFBF 容器——无需 Altium Designer、无需 Windows、也无需许可证。

### 如何用 Python 解析 .kicad_sch 文件？
要用 Python 解析 `.kicad_sch` 文件，使用 `akcli read board.kicad_sch`，或导入
`altium_kicad_cli.readers.kicad` 并调用 `read_sch(path)`。它使用一个有界的、非递归的
S-expression 解析器（仅标准库），返回一个带有元件、引脚和 net 的归一化 `Schematic`。

### 如何从 Altium 或 KiCad 提取网表？
要从 Altium 或 KiCad 提取网表，运行 `akcli net file.SchDoc` 或 `akcli net board.kicad_sch`。
两种格式共用同一个 net 推断引擎（`netbuild`），它会合并同名 net、连接点和 T 型连接点，
并输出经 `netlist.schema.json` 校验的 net → pin 成员关系 JSON。

### 我能否在不打开 KiCad 的情况下从命令行运行 ERC / 电气规则检查？
可以——你能在不打开 KiCad 的情况下从命令行运行 ERC / 电气规则检查。运行
`akcli check file.SchDoc`。ERC-lite 引擎是纯 Python（无需安装 EDA），使用 net 名称 +
power 端口检测加上类型置信度（type-confidence）门控；当 KiCad 可用时，会使用可选的
`kicad-cli` 二次校验。

### `akcli` 对 Altium 和 KiCad 文件做了什么？
`akcli` 将 Altium 和 KiCad 文件读入同一个归一化模型，并让你从命令行*分析、检查、比对和绘制*：
将原理图解析为 JSON、提取网表、运行 ERC/power/BOM 检查、按 net 成员关系比对两个修订版本，
以及依据 JSON op-list 写入 KiCad 原理图。Altium 访问在离线状态下为只读；KiCad 写入是原子化的
并经过连通性校验。

### 有没有 Altium MCP 服务器 / 如何将 Altium 与 AI 代理一起使用？
一个原生的 Altium/KiCad MCP 服务器已列入路线图；如今你通过本 Claude Code 插件和 `akcli` CLI
将 Altium 与 AI 代理一起使用，任何代理都可对其进行 shell 调用。其设计参考了一种基于文件的
JSON 桥接模式（在 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) 中致谢）；一个可选的
Windows live driver 可驱动运行中的 Altium 22+ 进行写入/绘制。

### 如何比对两个原理图版本（v1 vs v2）？
要比对两个原理图版本（v1 vs v2），运行 `akcli diff v1.SchDoc v2.SchDoc`。该 diff 通过
**成员关系**（Jaccard）匹配 net，通过 UniqueID / 签名匹配元件——而非通过显示名称——因此被
重命名的或以坐标命名的 net 不会显示为虚假的改动。

### Claude Code / Cursor 如何帮助进行 PCB 原理图设计？
Claude Code 或 Cursor 可以通过调用 `akcli` 来帮助进行 PCB 原理图设计：读取你的 `.SchDoc` /
`.kicad_sch`，运行 ERC/power/pinmap/BOM 检查，比对修订版本，并依据 JSON op-list 绘制 KiCad
原理图。Claude Code 插件正是为此工作流暴露了 `/altium-kicad:circuit-review`、`circuit-pinmap`、
`circuit-draw` 和 `circuit-diff`。

---

## 致谢

`akcli jlc` 由他人的开源成果驱动，以**保持距离**的方式使用（未导入或内嵌任何源代码——
见 [ACKNOWLEDGMENTS.md](../ACKNOWLEDGMENTS.md)）：

- **nlbn** 与 **npnp**，作者 **linkyourbin**（均为 **Apache-2.0**）——作为子进程被调用，
  将 LCSC 元件转换为 KiCad（`nlbn`）或 Altium（`npnp`）库。
- **jlcsearch**（tscircuit，MIT）与 **jlcparts**（MIT）——元件搜索后端。
- **EasyEDA / LCSC / JLCPCB**——元件数据来源（非官方、只读的元数据查询；转换委托给 nlbn/npnp）。

完整的署名与许可证文本：[ACKNOWLEDGMENTS.md](../ACKNOWLEDGMENTS.md) 与
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。

---

## 联系方式

如有疑问、缺陷或功能请求：请[开一个 GitHub issue](https://github.com/tipoLi5890/altium-kicad-cli/issues)。

---

## 许可证

MIT © 2026 Li, ching yu。见 [LICENSE](../LICENSE)。第三方署名（JSON 桥接模式链路，
以及 MS10 的 nlbn/npnp/jlcsearch 致谢）记录在
[ACKNOWLEDGMENTS.md](../ACKNOWLEDGMENTS.md) 与 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) 中。
安全模型与强制限制记录在 [SECURITY.md](../SECURITY.md) 中。
