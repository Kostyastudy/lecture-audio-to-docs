---
name: lecture-audio-to-docs
description: 把讲座/课堂录音（m4a/mp3/wav）配合 PPT 或 PDF 课件，整理成《演讲文字稿（校对版）》和《活动总结》两份中文 Word 文档。适用于 C:\Voice 下这类“录音 + 课件 → 两份 docx”的整场整理任务，含 CPU 转写、术语校对、排版与渲染验收。
whenToUse: 用户给出讲座/分享会/课堂的录音（可能还有 PPT/PDF），要求转文字稿、写活动总结、整理成 Word，或说“和上次一样整理”。也用于只做转写、只做总结、或需要把已有 md 转成中文排版 docx 的场景。
user-invocable: true
---

# 讲座录音 + 课件 → 两份 Word

这套流程已经完整跑过两次：2 小时 20 分的经验分享会（纯录音），和 45 分钟的培养方案解读（录音 + 31 页 PPT）。下面的参数、顺序和坑都是实测出来的，不是理论值。

工作区：`C:\Voice`。机器：Windows，16 核 CPU，31.4 GB 内存，**无 GPU**，HuggingFace 不稳，ModelScope 可用（约 3.5–4 MB/s）。

下面所有命令先设这两个变量（PowerShell）：

```powershell
$PY='C:\Users\29459\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
$SK="$env:USERPROFILE\.dsh\skills\lecture-audio-to-docs\scripts"
$env:PYTHONIOENCODING='utf-8'
```

`$SK` 指向本技能自带的脚本目录，直接复制命令即可。

## 0. 开工前 60 秒风险扫描

按顺序确认，任何一项异常都先处理再动手：

1. 文件在不在、多大、什么格式：`Get-Item -LiteralPath $p`。
2. 音频多长：`$SK\prepare_audio.py --src ... --dst work\audio16k.wav` 会打印时长。
3. 课件多少页、有没有文字层：`$SK\extract_slides.py` 会打印 `avg chars/page`；低于 30 基本是扫描件/图片页。
4. 模型在不在：`C:\Voice\models\turbo\.complete`。不在就**立刻后台拉**（1.6 GB，约 6–7 分钟），别等转写时才发现。
5. 内存余量：`FreePhysicalMemory`。每个 ASR 进程约 1.2–1.4 GB。
6. 录音是否从半截开始：把转写第一句和课件第 1 页对照。缺开头是最常见的“隐性缺陷”。

然后给用户一句带 ETA 的话，例如“45 分钟录音，转写约 25 分钟，两份文档约 1 小时”。不要闷头跑两小时再汇报。

## 1. 固定产出（默认，不用问）

| 文件 | 内容 |
|---|---|
| `<主题>_演讲文字稿（校对版）.docx` | 第一人称、按主题分节、每节标时间段；保留例子、插话、问答 |
| `<主题>_活动总结.docx` | 活动概况、总体判断、按课件逻辑展开的 6–12 节、现场答疑表、行动清单、依据说明 |
| `<主题>_原始转写（带时间码）.txt` | 机器原始转写，供核对，不加工 |

命名用讲座主题，不用“录音1”。中间产物全部放 `C:\Voice\work\`，根目录只留交付物。

## 2. 流程（七步，每步有门禁）

### 第 1 步：后台拉模型 + 读课件（并行）

```powershell
$PY='C:\Users\29459\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
$env:PYTHONIOENCODING='utf-8'
# 后台跑，不要等
& $PY $SK\fetch_model.py --dest C:\Voice\models\turbo
```

```powershell
& $PY $SK\extract_slides.py --pdf "...\talk.pdf" `
    --out-text C:\Voice\work\pdf_text.txt --out-img C:\Voice\work\pdf_pages
```

读 `pdf_text.txt` 全文；对**数字表、学分/课时结构、公式页、流程图**用 `read_image` 看原图，因为 PDF 文字层会把表格拆成竖排单字。

产出 `work/notes_slides.md`：只记“可核对的事实”——数字、专有名词、章节标题、时间节点。这份表是后面校对的词典，也是总结的事实底稿。

**门禁 G1**：课件事实表写完；模型 `.complete` 存在。两者缺一，不要开始转写。

### 第 2 步：音频转 16k 单声道 + 切块

```powershell
& $PY $SK\prepare_audio.py --src "C:\...\录音.m4a" --dst C:\Voice\work\audio16k.wav
& $PY $SK\plan_chunks.py --wav C:\Voice\work\audio16k.wav --out C:\Voice\work\chunks.json
```

- 默认 60 秒一块，在目标点 ±6 秒内找能量最低的 0.3 秒下刀，避免切断字词。
- 不要用 5 分钟以上的大块。实测：17 分钟一块 + beam 5 + 4 线程，单块跑了 7.6 小时（0.04x），是这套流程最大的时间坑。
- 不要加重叠。重叠带来的重复文本比丢半个字更难清理。

### 第 3 步：并行转写

```powershell
& $PY $SK\run_asr.py --wav C:\Voice\work\audio16k.wav `
    --plan C:\Voice\work\chunks.json --out-dir C:\Voice\work\asr_chunks `
    --model C:\Voice\models\turbo --workers 3 --threads 5
```

默认 `turbo + int8 + beam 1 + 3 进程 × 5 线程`。这是本机唯一稳定的组合：

- `large-v3` 在 CPU 上只有 0.3x，2 小时录音要 7 小时，直接放弃。
- 8 进程 × 2 线程必 OOM（8 × 1.3 GB + 系统），进程会静默崩。
- `beam 5` 不比 `beam 1` 明显更准，但慢一倍以上。
- 每块输出独立 JSONL，写完才 rename，崩了重跑会自动跳过。

**门禁 G2**：`run_asr.py` 退出码 0，`chunk*.jsonl` 全部非空。用字符量做体检：中文演讲约 180–260 字/分钟；45 分钟应有 8k–12k 字。明显偏低就是有块没跑或全程静音。

### 第 4 步：合并 + 通读 + 术语校对

```powershell
& $PY $SK\merge_asr.py --dir C:\Voice\work\asr_chunks --prefix C:\Voice\work\transcript_raw
```

`merge_asr.py` 默认用 OpenCC 做繁转简；Whisper 的中文输出会随机夹繁体（“學分”“開放時間”），不转会在成稿里很难看。缺包时 `pip install opencc-python-reimplemented`。

然后**通读全文**，不要只看开头。分段读，边读边记三类错误：

1. 同音术语（用 `notes_slides.md` 对照）；
2. 人名、机构名、课程名；
3. 数字、学分、日期、比例。

写成 `work/transcript.md`：

- 合并 2–4 秒的碎句为自然段，补标点，去“嗯/呃/就是说”；
- 保留讲者的语气、犹豫、举例、跑题和自嘲——这是文字稿的价值，不要改成新闻稿；
- 听不清就写“（听不清）”，一页不超过两处；**绝不替讲者补全**；
- 按主题分节，每节标题下写 `（约 00:00—05:30）`。

**门禁 G3**：文字稿时间跨度覆盖录音全长；抽 3 个随机位置与原始转写比对，没有整段漏译。

### 第 5 步：写总结

先列提纲再写。提纲必须同时回答两个问题：这场讲座**讲了什么**（课件逻辑），**讲者怎么讲**（现场逻辑）。

结构见第 5 节模板。硬要求：

- 每个数字、政策、时间节点都能在 `notes_slides.md` 或转写里找到出处；
- 课件有、录音没讲的，写“据课件补足”；
- 录音有、课件没有的，才是总结的增量（举例、提醒、现场问答）；
- 现场问答单独成表；问题听不清时按回答反推，并标注“据回答整理”。

### 第 6 步：md → docx → 渲染验收

```powershell
& $PY $SK\polish_md.py C:\Voice\work\transcript.md C:\Voice\work\summary.md
& $PY $SK\md2docx.py --md C:\Voice\work\transcript.md `
    --out "C:\Voice\<主题>_演讲文字稿（校对版）.docx" `
    --title "<主题> · 演讲文字稿（校对版）" `
    --subtitle "2026 年 X 月 X 日 · 依现场录音整理"
& $PY $SK\md2docx.py --md C:\Voice\work\summary.md `
    --out "C:\Voice\<主题>_活动总结.docx" `
    --title "<主题> · 活动总结" `
    --subtitle "2026 年 X 月 X 日 · 内容提炼与行动建议"
```

注意：md 里**不要写 H1 标题**，标题由 `--title` 给，否则 docx 会出现两个标题。

渲染检查（用 `office-render` 技能里的 LibreOffice Kit 命令，输出目录要先 `New-Item` 建好，否则报 `ENOENT mkdir`）：

- 看第 1 页、任一含表格页、最后一页；
- 检查表格是否压字、跨页表头是否重复、页码是否正常；
- 检查正文有没有残留 `**`、`##`、`|`；
- 页数合理：45 分钟讲座约 9–11 页文字稿、12–14 页总结；2 小时约 35–40 页文字稿。

### 第 7 步：清理 + 交付

删 `work\audio16k.wav`、`work\asr_chunks`、`work\pdf_pages`、`.dsh-office-*`。**保留** `models\turbo`（下次省 7 分钟）、`transcript_raw.txt`、两个 md。

用 `present` 交付两份 docx，正文里给出页数、字数、以及“依据与缺口”的一句话说明。

## 3. 实测性能与预算

| 任务 | 音频 | 配置 | 转写 | 全流程 |
|---|---|---|---|---|
| 经验分享会 | 2h20m | turbo，8 块×17min，3 进程×4 线程，beam5 | **8 小时**（病态，勿复现） | 约 9 小时 |
| 培养方案解读 | 45m28s | turbo，46×60s，6→3 进程×3–5 线程，beam1 | 约 25 分钟 | 约 1 小时 |
| 单进程基准 | — | turbo，16 线程，beam1 | 2.2x（180s 用 82s） | — |
| 单进程基准 | — | large-v3，16 线程，int8 | 0.3x | — |

预算公式：**转写 ≈ 音频时长 × 0.45；写作 + 排版 ≈ 音频时长 × 0.6–1.0**。即 45 分钟讲座约 1 小时，2 小时讲座约 2.5–3 小时。超过 3 小时录音先和用户确认是否分段交付。

## 4. 会碰壁的地方（症状 → 处理）

| 症状 | 真实原因 | 处理 |
|---|---|---|
| `SetNamedSecurityInfoW failed (Win32 5): grantWrite(C:\Voice)` | 工作区 ACL 被破坏 | 立即加载 `diagnose-windows-sandbox-acl` 技能修，不要反复重试写文件 |
| `ffmpeg` 找不到 / PyAV 报 `Invalid data`（MP3 的 LAME 头） | 机器没装 ffmpeg；PyAV 对某些微信 MP3 不兼容 | `prepare_audio.py` 已内置 `imageio-ffmpeg` 回退，不要手动装 ffmpeg |
| `WhisperModel` 初始化卡住 / 反复重试下载 | faster-whisper 自动走 HuggingFace | 永远先 `fetch_model.py`，再把本地目录传给 `--model` |
| hf-mirror 返回 308、huggingface TLS 断流 | 网络对 HF 不稳定 | 不要修网络，直接用 ModelScope；实测 1.54 GB / 383 秒 |
| 转写 0.0x–0.3x，越跑越慢 | 大块 + beam5 + 多进程争抢 CPU | 60 秒块、beam1、3 进程；单进程上限约 2.2x |
| 8 个 worker 同时消失/JSONL 只有几百字节 | 内存不足被系统杀 | 降到 3 个 worker；`FreePhysicalMemory` 低于 6 GB 就再降 |
| 第一段文字就是提示词本身 | `initial_prompt` 泄漏 | 不要传 prompt；术语靠第 4 步人工校对 |
| `BatchedInferencePipeline` 直接 `exit -1073741571` | 该版本 batch 推理在本机崩溃 | 不要用 batch，老实用 chunk 并行 |
| Python 打印中文报 `UnicodeEncodeError: 'gbk'` | 控制台代码页 | 每条命令前 `$env:PYTHONIOENCODING='utf-8'` |
| PowerShell 改写中文脚本后全文乱码 | `Set-Content`/`-replace` 用 GBK 写回 | **不要用 PowerShell 编辑含中文的文件**，用 write/edit 工具 |
| `$pid` 赋值报“只读变量” | `$PID` 是 PowerShell 内置变量 | 换名 `$procId` |
| pypdf 提取中文报错或输出乱码 | 字体编码 + 控制台编码 | 用 `pymupdf`（`extract_slides.py`），并且必须看页面图核对表格 |
| 转写里夹繁体（學分、開放時間） | Whisper 中文输出不稳定，会混繁体 | `merge_asr.py` 默认 OpenCC 繁转简；不要靠提示词 |
| 转写每句只有 2–4 秒、读起来支离破碎 | Whisper 的中文切分粒度 | 正常现象；第 4 步按语义合并成段，不要逐句保留 |
| 课件页 `avg chars/page < 30` | 扫描件/图片型 PPT | 只能 `read_image` 人工读；必要时向用户要可复制版 |
| docx 里出现 `**`、`##` | md 写法超出渲染器支持 | 表格单元格内不要嵌套列表；标题只用 `##`/`###`；重建后看 `[warn]` |
| LibreOffice 渲染报 `ENOENT mkdir` | 输出根目录不存在 | 先 `New-Item -ItemType Directory -Force <root>` |
| 录音开头缺失/从半截开始 | 现场才开始录 | 两份文档都写明缺口；总结用课件补，文字稿不补 |

## 5. 文档模板

### 文字稿

```markdown
（说明：录音自“……”开始，此前内容未录到。）

## 一、<主题>（约 00:00—05:30）

正文第一段……

### 1. <小标题>

……
```

- 只用 `##` 和 `###`；
- 时间段放在标题下一行，斜体或括号；
- 问答部分用 `**问：**……` / `**答：**……`，不要用引用块堆叠。

### 总结

```markdown
## 一、活动概况

**活动性质：**……
**时间与对象：**……
**主讲与形式：**……
**录音情况：**……（时长、缺口、音质）

| 板块 | 主要内容 | 记录依据 |
|---|---|---|
| …… | …… | 录音 + 课件第 X 页 |

---

## 二、总体印象：<一句判断>

<3–5 段；最后给三条主线>

## 三、<按课件逻辑分节>

### 1. <小节>

| 表 | 表 |
|---|---|

## 现场答疑

| 问题 | 回答要点 |
|---|---|

## 行动清单

1. ……

## 附：依据与说明

- 采信：……
- 未采信/无法确认：……
```

## 6. 质量红线

1. **不把课件文字伪装成现场原话。** 文字稿只写录音里真实出现的；课件补的内容在总结里注明。
2. **不编数字、人名、政策。** 不确定就写“录音中未明确”，或直接不写。
3. **不把不同人的观点抹平。** 分享会里互相“拆台”、问答里的分歧，是内容价值所在。
4. **不逐句保留碎句。** 文字稿是“可读的口语”，不是 ASR 输出。
5. **不省略缺口说明。** 录音缺开头、问答听不清、板书没录到，都要在文末交代。
6. **docx 必须渲染看过。** 只看字符数不算验收；表格压字和空页只有看图才发现。

## 7. 微积分/公式类讲座的额外处理

数学讲座的难点不在转写速度，在**术语和公式**。

1. **先建术语表**：从课件抄下全部术语（极限、连续、可导、罗尔/拉格朗日/柯西中值定理、洛必达、泰勒/麦克劳林、换元积分、分部积分、反常积分、级数收敛半径……），再在转写里全局搜同音错写。
2. **高频同音错**：洛必达→“洛比达/罗比达”，拉格朗日→“拉格朗”，柯西→“科西”，泰勒→“泰了”，驻点→“住点”，拐点→“怪点”，极值→“机制”，偏导→“偏倒”，梯度→“提度”。逐个替换后再读一遍。
3. **公式只从课件取**。课件没有的推导，写成口语描述（“对 x 从 0 到 1 积分”），不要凭 ASR 拼符号。
4. **行内符号用 Unicode**：`∫`、`∑`、`∂`、`√`、`≤`、`≥`、`∞`、`→`、`x²`。不要在 docx 里插入 Word 公式对象——md2docx 不支持，且容易变成空框。
5. **板书推导**：标“（板书推导，录音无法还原）”，不要假装完整。
6. **学生提问**通常离麦克风远、听不清：按老师的回答反推问题，标“（据回答整理）”；连续多个问题听不清时，合并成一个“现场提问集中在……”的段落。

## 8. 不要做的事

- 不要用 `large-v3` 跑整场；不要用 5 分钟以上的块；不要开 `beam 5`。
- 不要让 faster-whisper 自己下模型；不要反复试 HuggingFace。
- 不要用 PowerShell 批量替换中文文本。
- 不要把 2 小时录音一次性丢给单进程。
- 不要在没读课件的情况下写总结。
- 不要在转写没跑完时先写完整总结——后面的问答往往会推翻前面的判断。
- 不要删除 `models\turbo`；不要删原始转写。

## 脚本清单

| 脚本 | 用途 |
|---|---|
| `scripts/prepare_audio.py` | 探测 + 转 16k 单声道 WAV（PyAV，失败回退 imageio-ffmpeg） |
| `scripts/plan_chunks.py` | 在低能量点切 60 秒块，输出 chunks.json |
| `scripts/run_asr.py` | 起 N 个 worker、监控、断点续跑、报 ETA |
| `scripts/asr_chunks.py` | 单 worker 转写（一般由 run_asr 调） |
| `scripts/asr_full.py` | 短音频/抽样试跑（单进程） |
| `scripts/merge_asr.py` | 合并 chunk JSONL，去重，出带时间码 txt |
| `scripts/extract_slides.py` | PDF 文字 + 逐页 PNG |
| `scripts/fetch_model.py` | ModelScope 断点续传拉 turbo 模型 |
| `scripts/md2docx.py` | 中文排版 docx（标题/页脚/表格/页码）+ 残留检查 |
| `scripts/polish_md.py` | 引号、空格、无意义括号清理 |
