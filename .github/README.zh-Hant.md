[English](../README.md) · **繁體中文** · [简体中文](README.zh-Hans.md)

# altium-kicad-cli — 讀取 Altium .SchDoc 與 KiCad .kicad_sch、執行 ERC、繪製 KiCad（免安裝 EDA）

**altium-kicad-cli**（CLI 指令 `akcli`，匯入套件名 `altium_kicad_cli`）是一套零相依的
Python 工具包與 Claude Code 外掛，能在**未安裝 Altium 或 KiCad** 的情況下讀取 **Altium 二進位
`.SchDoc` / `.SchLib` / `.PcbDoc`** **以及** **KiCad `.kicad_sch` / `.kicad_sym` / `.kicad_pcb`**，
並從命令列執行 ERC／電源／pinmap／BOM／diff 檢查，再從 JSON op-list 繪製 KiCad 電路圖。
它是為 AI 程式代理（AI coding agents）打造的。

它將兩種格式都讀入同一套正規化模型，並對其進行*分析*——解析、檢查、比對、繪製——
讓你擁有一套可腳本化、免安裝的工作流程，能由自動化管線或 LLM 代理來驅動。

[![CI](https://github.com/tipoLi5890/altium-kicad-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/tipoLi5890/altium-kicad-cli/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## 重點特色

- **兩種格式，一套模型。** Altium 二進位 `.SchDoc` 與 KiCad `.kicad_sch` 都會正規化為同一套
  `Schematic`／`Pcb`／`Library` 模型，因此每一項檢查、比對與報表都與格式無關。
- **免安裝 EDA。** 純標準函式庫的 OLE2/CFBF 與 Altium 記錄解碼，加上一個迭代式的 KiCad
  S-expression 解析器。不需要 Altium、不需要 KiCad、不需要任何編譯的擴充——只要 Python ≥ 3.11。
- **零執行期相依。** 僅使用標準函式庫（包含 `tomllib`）。易於 vendoring、沙箱化或在 CI 中執行。
- **可信賴的網路（net）推論。** 重建的 net 層能處理全域同名合併、junction、T 型接點與 No-ERC 標記
  ——修正了經典的「同名 net 被拆成單腳 net」的 bug。
- **對 Altium 唯讀、對 KiCad 安全寫入。** 離線時絕不修改 Altium 檔案；KiCad 的寫入會經過
  atomic 快照 → 暫存 → 驗證 → 取代的管線，並搭配純 Python 的連通性閘門。
- **AI 代理原生支援。** 以 Claude Code 外掛形式發布，內含 skills／commands，輸出帶有
  `schema_version` 的結構化 JSON，並接受帶版本的 op-list 以進行確定性、冪等的編輯。

## 在未安裝 Altium 的情況下讀取 .SchDoc / .SchLib / .PcbDoc

`akcli` 可直接開啟 Altium 二進位檔。它內含一個強化過的 OLE2/CFBF（Compound File Binary
Format）容器讀取器與 Altium 記錄解碼器——不需要 Altium Designer、不需要 Windows、不需要授權。

```bash
akcli read   hardware/insole/main.SchDoc        # 將 .SchDoc 解析為正規化 JSON
akcli net    hardware/insole/main.SchDoc         # 擷取 netlist（net -> pins）
akcli component hardware/insole/main.SchDoc       # 列出元件／designator／值
```

支援的 Altium 輸入：`.SchDoc`（電路圖）、`.SchLib`（符號庫）、`.PcbDoc`（電路板——v1 支援
ASCII 的 `Nets6`／`Components6`／`Classes6`／`Rules6` 區段；二進位的 pad/track 區段會明確報錯拒絕，
而不會誤解析）。所有 Altium 存取皆為**唯讀**。

## 解析 KiCad .kicad_sch / .kicad_sym / .kicad_pcb（S-expression）

同一套 CLI 以一個顯式堆疊（非遞迴）的 tokenizer 解析 KiCad 的 S-expression 格式，
該 tokenizer 對深度、atom 與節點數量都有界限——因此格式錯誤或惡意的檔案無法撐爆堆疊。

```bash
akcli read hardware/board.kicad_sch              # .kicad_sch -> 正規化 JSON
akcli net  hardware/board.kicad_sch              # net 成員關係，共用的 net 引擎
```

KiCad 的 pin 電氣型別會在讀取時從 `lib_symbols` 解析出來（實例 pin 不帶型別），
因此 ERC 擁有所需的資料。KiCad 7 與 KiCad 8 的檔案皆受支援。

## 從命令列執行 ERC 與設計檢查（power、pinmap、BOM、diff）

不必開啟任何 EDA 工具，即可執行電氣規則檢查（ERC）與其他設計檢查：

```bash
akcli check  main.SchDoc                          # ERC-lite + power + BOM 衛生檢查
akcli pinmap main.SchDoc -C altium-kicad-cli.toml # MCU pin -> net（+ 選用的預期對照表）
akcli diff   v1.SchDoc v2.SchDoc                   # 以 net 成員關係比對，而非以名稱比對
```

電源／接地偵測是**以 net 名稱 + power port 為基礎**，而非純粹以電氣型別判斷，因為
真實電路板大多是 `Passive` pin——只看型別的天真 ERC 會產生空洞的通過結果。每份報表都會
印出一段中繼資料標頭（passive-pin 比例、被抑制的 No-ERC 數量、未命名 net 數量、是否含有小數座標），
因此乾淨的結果絕不會被誤認為空結果。

## 從 op-list 繪製／寫入 KiCad 電路圖（.kicad_sch）

`akcli` 會從帶版本的 JSON **op-list**（放置元件、wire、junction、label、power port、文字……）
寫出 KiCad 電路圖。寫入是精準且冪等的（確定性 UUIDv5），由純 Python 的連通性驗證器把關，
並需要明確的 `--apply`（預設為 dry run）。

```bash
akcli plan  ops.json --target board.kicad_sch     # 驗證 op-list，顯示將會變更的內容
akcli draw  ops.json --target board.kicad_sch     # 預設為 dry-run（不寫入檔案）
akcli draw  ops.json --target board.kicad_sch --apply   # atomic 寫入 + 驗證 + 備份
```

Altium 的*寫入／繪製*僅能透過選用的 Windows 即時驅動（需執行中的 Altium 22+）；
離線時，Altium 僅供分析。

## 作為 Claude Code 外掛／搭配 AI 程式代理使用（以及 MCP 路線圖）

安裝 Claude Code 外掛後，你的代理便擁有 `/altium-kicad:circuit-review`、
`circuit-pinmap`、`circuit-draw` 與 `circuit-diff` 指令，外加一個 circuit-design skill，
這些底層全都呼叫 `akcli`。每個指令都會輸出帶有 `schema_version` 的結構化 JSON（`--json`），
而 op-list 帶有 `protocol_version`，因此代理的輸出可保持機器可驗證且冪等。

原生的 **MCP server**（Altium／KiCad）已列入路線圖（見下文）；目前的整合介面為
Claude Code 外掛 + `akcli` CLI，任何代理都可透過 shell 呼叫。

## 安裝（akcli CLI + 外掛）

```bash
# CLI（推薦）：以 pipx 進行隔離安裝
pipx install altium-kicad-cli
akcli --version

# 或從 clone 直接執行，免安裝（零執行期相依）
git clone https://github.com/tipoLi5890/altium-kicad-cli
./altium-kicad-cli/bin/akcli --help
```

Claude Code 外掛（marketplace 名稱為 `altium-kicad`）：

```text
/plugin marketplace add tipoLi5890/altium-kicad-cli
/plugin install altium-kicad@altium-kicad
```

完整細節與疑難排解請見 [INSTALL.md](../INSTALL.md)。需要 **Python ≥ 3.11**（用於標準函式庫
`tomllib`）；若你預設的 `python3` 版本過舊，`bin/akcli` wrapper 會自動選用夠新的直譯器。

## 路線圖／狀態

> **狀態：pre-alpha／積極建構中。** 本倉庫目前包含凍結的實作規格
> （[`docs/SPEC.md`](../docs/SPEC.md)），並正逐里程碑（milestone）建構中。**尚無 PyPI 發布**，
> 上方的徽章／指令描述的是*目標*行為。下方未標記為 **Shipped** 的任何功能，都請視為尚未可用。

| 能力 | 里程碑 | 狀態 |
|---|---|---|
| 基礎：model、ops、errors、safety、units、config、schemas、外掛 scaffold | MS0 | 進行中 |
| README／SEO／docs／CI matrix | MS1 | 進行中 |
| Altium `.SchDoc` 讀取 + 重建的 net 推論（STAT/LED1 合併修正） | MS2 | 規劃中 |
| 檢查（ERC/power/BOM/diff/pinmap）+ CLI 核心 | MS3 | 規劃中 |
| KiCad `.kicad_sch` 讀取（v7/v8） | MS4 | 規劃中 |
| 從 op-list 寫入／繪製 KiCad（連通性閘門，冪等） | MS5 | 規劃中 |
| `.SchLib`／`.PcbDoc`（ASCII）讀取 | MS6 | 規劃中 |
| Claude Code skill + commands + DTS/pinout 轉接器 | MS7 | 規劃中 |
| **選用** 的 Altium 即時驅動（Windows + Altium 22+） | MS8 | 規劃中（僅限 Windows） |
| 原生 MCP server | post-1.0 | 構想／路線圖 |

**明確延後（不在 v1）：** 離線 Altium *寫入*；以 Altium 為權威來源的 ERC/netlist（需要
即時 Altium）；Altium `.PcbDoc` 二進位區段（pad/track/via/arc/fill/region）；階層／
多 sheet 的 KiCad 寫入（v1 僅支援單層 flat）。詳見 `docs/SPEC.md` §8 的風險登記表。

## 常見問題（FAQ）

### 在未安裝 Altium 的情況下，要如何讀取／開啟 Altium .SchDoc 檔？
要在未安裝 Altium 的情況下讀取或開啟 Altium `.SchDoc` 檔，請執行 `akcli read file.SchDoc`
（或以 `akcli net file.SchDoc` 取得 netlist）。`akcli` 是一套零相依的 Python 工具，
直接解碼 Altium 二進位 OLE2/CFBF 容器——不需要 Altium Designer、不需要 Windows、也不需要授權。

### 要如何在 Python 中解析 .kicad_sch 檔？
要在 Python 中解析 `.kicad_sch` 檔，請使用 `akcli read board.kicad_sch`，或匯入
`altium_kicad_cli.readers.kicad` 並呼叫 `read_sch(path)`。它使用一個有界、非遞迴的
S-expression 解析器（僅標準函式庫），並回傳含有 components、pins 與 nets 的正規化 `Schematic`。

### 要如何從 Altium 或 KiCad 擷取 netlist？
要從 Altium 或 KiCad 擷取 netlist，請執行 `akcli net file.SchDoc` 或 `akcli net board.kicad_sch`。
兩種格式共用同一套 net 推論引擎（`netbuild`），它會合併同名 net、junction 與 T 型接點，
並輸出 net → pin 成員關係的 JSON，並以 `netlist.schema.json` 驗證。

### 我可以不開啟 KiCad，就從命令列執行 ERC／電氣規則檢查嗎？
可以——你可以不開啟 KiCad，就從命令列執行 ERC／電氣規則檢查。請執行
`akcli check file.SchDoc`。ERC-lite 引擎是純 Python（免安裝 EDA），採用 net 名稱 +
power port 偵測，加上型別信心度閘控；當 KiCad 可用時，可選用 `kicad-cli` 作為次級驗證。

### `akcli` 對 Altium 與 KiCad 檔案能做什麼？
`akcli` 將 Altium 與 KiCad 檔案讀入同一套正規化模型，讓你從命令列*分析、檢查、比對與繪製*：
將電路圖解析為 JSON、擷取 netlist、執行 ERC/power/BOM 檢查、以 net 成員關係比對兩個版本，
並從 JSON op-list 寫出 KiCad 電路圖。Altium 在離線時為唯讀；KiCad 的寫入為 atomic 並經連通性驗證。

### 有 Altium MCP server 嗎／要如何搭配 AI 代理使用 Altium？
原生的 Altium／KiCad MCP server 已列入路線圖；目前你透過這個 Claude Code 外掛與 `akcli` CLI
搭配 AI 代理使用 Altium，任何代理皆可透過 shell 呼叫。其設計參考了一種以檔案為基礎的 JSON 橋接
模式（已於 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) 中註明出處）；選用的 Windows
即時驅動會驅動一個執行中的 Altium 22+ 進行寫入／繪製。

### 要如何比對兩個電路圖版本（v1 vs v2）？
要比對兩個電路圖版本（v1 vs v2），請執行 `akcli diff v1.SchDoc v2.SchDoc`。此 diff 以**成員關係**
（Jaccard）比對 net，並以 UniqueID／signature 比對元件——而非以顯示名稱——因此被重新命名或
以座標命名的 net 不會被當成虛假的變更顯示出來。

### Claude Code／Cursor 要如何協助 PCB 電路圖設計？
Claude Code 或 Cursor 可透過呼叫 `akcli` 來讀取你的 `.SchDoc`／`.kicad_sch`、執行
ERC/power/pinmap/BOM 檢查、比對版本，並從 JSON op-list 繪製 KiCad 電路圖，藉此協助 PCB 電路圖設計。
Claude Code 外掛即為此工作流程提供了 `/altium-kicad:circuit-review`、`circuit-pinmap`、
`circuit-draw` 與 `circuit-diff`。

---

## 致謝

`akcli jlc` 由其他人的開源成果驅動，並以**保持距離**的方式使用（未匯入或 vendoring 任何原始碼
——詳見 [ACKNOWLEDGMENTS.md](../ACKNOWLEDGMENTS.md)）：

- **nlbn** 與 **npnp**，作者 **linkyourbin**（皆為 **Apache-2.0**）——以子行程方式呼叫，
  將 LCSC 零件轉換為 KiCad（`nlbn`）或 Altium（`npnp`）庫。
- **jlcsearch**（tscircuit，MIT）與 **jlcparts**（MIT）——零件搜尋後端。
- **EasyEDA／LCSC／JLCPCB**——元件資料來源（非官方、唯讀的中繼資料查詢；轉換工作委派給 nlbn/npnp）。

完整出處標註與授權條款全文：[ACKNOWLEDGMENTS.md](../ACKNOWLEDGMENTS.md) 與
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。

---

## 聯絡方式

問題、bug 或功能請求：請[開一個 GitHub issue](https://github.com/tipoLi5890/altium-kicad-cli/issues)。

---

## 授權

MIT © 2026 Li, ching yu。詳見 [LICENSE](../LICENSE)。第三方出處標註（JSON 橋接模式的鏈結，
加上 MS10 的 nlbn/npnp/jlcsearch 致謝）記錄於 [ACKNOWLEDGMENTS.md](../ACKNOWLEDGMENTS.md) 與
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。安全模型與強制限制記錄於 [SECURITY.md](../SECURITY.md)。
