# lecture-audio-to-docs

把**讲座 / 课堂录音**（m4a、mp3、wav）配合 **PPT / PDF 课件**，整理成两份中文 Word：

- `<主题>_演讲文字稿（校对版）.docx` —— 第一人称、按主题分节、保留例子与问答；
- `<主题>_活动总结.docx` —— 活动概况、总体判断、按课件逻辑展开、现场答疑表、行动清单；
- `<主题>_原始转写（带时间码）.txt` —— 机器原始转写，供核对。

这是一个 [SKILL.md](SKILL.md) 形式的技能，面向 **DeepSeek Harness / Claude 风格的 skills 目录**：把整个仓库放进 `~/.dsh/skills/`（或 `~/.claude/skills/`），下次遇到“录音 + 课件”的任务时模型会自动加载。

> A reusable skill for turning a Chinese lecture recording plus slides into a cleaned transcript and a structured event summary — on a CPU-only Windows machine, with a resumable parallel ASR pipeline and a Chinese Word renderer.

## 为什么不是“直接跑 Whisper”

这套流程来自两次真实任务：一场 2 小时 20 分的经验分享会，和一场 45 分钟的培养方案解读。第一次跑了 **8 小时**，第二次只用了 **1 小时**。差别不在模型，而在参数和流程：

| 做法 | 结果 |
|---|---|
| `large-v3`，单进程 | 0.3x，2h20 要 7 小时 |
| turbo，17 分钟大块，beam 5，3 进程 × 4 线程 | 单块 7.6 小时（0.04x），整场 8 小时 |
| turbo，60 秒小块，beam 1，3 进程 × 5 线程 | 45 分钟录音约 25 分钟转完 |

技能里固化了后一种配置，并处理了这些实际会卡住的地方：

- HuggingFace 下载失败 / 308 / TLS 断流 → ModelScope 断点续传；
- 微信 MP3 的 LAME 头 → PyAV 失败时自动回退 `imageio-ffmpeg`；
- 8 个 worker 内存溢出 → 每进程约 1.3 GB，默认 3 个；
- `initial_prompt` 泄漏成正文第一段 → 不传提示词；
- Whisper 中文输出夹繁体 → OpenCC 繁转简；
- PDF 表格文字层被拆成竖排单字 → 同时导出页面图，人工核对；
- PowerShell 写中文文件变 GBK 乱码 → 只用编辑工具改中文。

## 安装

Windows（PowerShell）：

```powershell
git clone https://github.com/Kostyastudy/lecture-audio-to-docs.git
cd lecture-audio-to-docs
.\install.ps1
```

或手动把 `SKILL.md`、`scripts/`、`references/` 复制到：

```text
%USERPROFILE%\.dsh\skills\lecture-audio-to-docs\
```

安装后技能会出现在会话的技能列表里，直接用自然语言说“按 lecture-audio-to-docs 整理这段录音”即可。

## 依赖

- Python 3.10+（脚本在 3.12 上验证）
- `faster-whisper`、`av==13.1.0`、`numpy`
- `pymupdf`（读 PPT/PDF）、`python-docx`（生成 Word）
- `opencc-python-reimplemented`（繁转简）
- `imageio-ffmpeg`（转码兜底）
- 可选：LibreOffice Kit（渲染验收，见 `office-render` 技能）

```powershell
pip install faster-whisper "av==13.1.0" pymupdf python-docx opencc-python-reimplemented imageio-ffmpeg
```

首次运行会从 ModelScope 下载 `faster-whisper-large-v3-turbo`（约 1.6 GB，3.5–4 MB/s，约 6 分钟）。之后复用本地目录，不必重复下载。

## 快速开始

```powershell
$PY='python'
$SK="$env:USERPROFILE\.dsh\skills\lecture-audio-to-docs\scripts"
$env:PYTHONIOENCODING='utf-8'

# 0) 模型（只需一次）
& $PY $SK\fetch_model.py --dest C:\Voice\models\turbo

# 1) 课件：文字 + 逐页图
& $PY $SK\extract_slides.py --pdf talk.pdf --out-text work\pdf_text.txt --out-img work\pdf_pages

# 2) 音频：转 16k 单声道，按低能量点切 60 秒块
& $PY $SK\prepare_audio.py --src talk.m4a --dst work\audio16k.wav
& $PY $SK\plan_chunks.py --wav work\audio16k.wav --out work\chunks.json

# 3) 并行转写（可断点续跑）
& $PY $SK\run_asr.py --wav work\audio16k.wav --plan work\chunks.json `
    --out-dir work\asr_chunks --model C:\Voice\models\turbo --workers 3 --threads 5

# 4) 合并 + 繁转简
& $PY $SK\merge_asr.py --dir work\asr_chunks --prefix work\transcript_raw

# 5) 写 md，再转 Word
& $PY $SK\md2docx.py --md work\summary.md --out "活动总结.docx" `
    --title "某某讲座 · 活动总结" --subtitle "2026 年 11 月 · 内容提炼与行动建议"
```

完整流程、门禁、文档模板和避坑表见 [SKILL.md](SKILL.md)；两次任务的时间线见 [references/lessons.md](references/lessons.md)。

## 目录结构

```text
SKILL.md                    # 技能主文件：七步流程、参数、模板、质量红线
references/lessons.md       # 两次实战记录与时间线
scripts/
  fetch_model.py            # ModelScope 分块下载 / 断点续传
  prepare_audio.py          # 任意音频 → 16k 单声道 WAV
  plan_chunks.py            # 低能量点切块
  run_asr.py                # 起 N 个 worker、监控、重试、ETA
  asr_chunks.py             # 单 worker 转写
  asr_full.py               # 短音频单进程转写
  merge_asr.py              # 合并、去重、繁转简、带时间码输出
  extract_slides.py         # PDF 文字 + 页面 PNG
  md2docx.py                # 中文排版 Word（标题、表格、页码）
  polish_md.py              # 引号、空格、括号清理
install.ps1                 # 安装到 ~/.dsh/skills
```

## 适用与不适用

适用：

- 中文讲座、分享会、课堂、宣讲会；
- 有或没有课件都行；有课件时用课件校正术语和数字；
- 需要“逐字稿 + 总结”两份交付，而不只是一段摘要。

不适用：

- 多人重叠说话、强噪声、远场录音（转写会明显退化）；
- 纯板书、无课件、大量公式推导的课程（公式只能人工补）；
- 需要说话人分离（本流程不做 diarization）。

## 说明

- `SKILL.md` 里的 `C:\Voice`、`C:\Users\...` 是作者机器上的路径，换机器时按实际路径替换；脚本本身都接受命令行参数。
- 转写质量取决于录音质量。45 分钟讲座通常得到 7k–10k 字原始转写，成稿约 7k–8k 字。
- 所有数字、政策、时间节点都应回到课件或原始转写核对；技能明确要求“不编、不补全、缺口要注明”。

## License

MIT
