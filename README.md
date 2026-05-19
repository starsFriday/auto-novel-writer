# Auto Novel Writer

给一个小说开端，自动生成小说规划并逐章写正文。当前日常只需要用两个脚本：

```text
write_from_opening.sh   # 新书：根据开端规划 + 写正文
continue_writing.sh     # 续写：只继续写章节
```

## 下载和安装

从 GitHub 下载项目：

```bash
git clone https://github.com/starsFriday/auto-novel-writer.git
cd auto-novel-writer
```

安装 Python 依赖：

```bash
python3 -m pip install -r requirements.txt
```

准备模型配置：

```bash
cp .env.example .env
```

编辑 `.env`，填写你的模型接口信息。例如使用 `codex-lb`：

```bash
LLM_PROFILE=codex-lb
CODEX_LB_API_KEY="你的 key"
CODEX_LB_BASE_URL=https://codex-lb.vvicat.dev/v1
```

或者使用 OpenAI 官方接口：

```bash
LLM_PROFILE=openai
OPENAI_API_KEY="你的 key"
OPENAI_BASE_URL=https://api.openai.com/v1
```

## 1. 写一本新书

打开并编辑：

```text
write_from_opening.sh
```

主要改这几项：

```bash
PROJECT_ID="Urban-cultivation-in-ancient-times"
TARGET_CHAPTERS="20"
TARGET_CHARS="5500"
```

然后把脚本里的多行 `OPENING` 换成你的小说开端：

```bash
if [[ -z "${OPENING:-}" ]]; then
  read -r -d '' OPENING <<'EOF' || true
这里写你的小说开端
EOF
fi
```

运行：

```bash
./write_from_opening.sh
```

这个脚本只做两步：

```text
plan  -> 根据开端生成 novel_plan.json
write -> 按规划逐章写正文
```

它不会重新抽规则，也不会重新读取 `novalv1/novalv2`。前提是规则书已经存在：

```text
data/final/novel_rulebook.json
```

输出在：

```text
data/projects/<PROJECT_ID>/
```

常看这些文件：

```text
data/projects/<PROJECT_ID>/novel_plan.json
data/projects/<PROJECT_ID>/chapters/chapter_001.md
data/projects/<PROJECT_ID>/novel.md
data/projects/<PROJECT_ID>/quality_report.json
```

也可以不改脚本，临时传开端和项目名：

```bash
OPENING="这里写你的小说开端" PROJECT_ID="my-novel" ./write_from_opening.sh
```

## 2. 续写已有小说

如果已经写完 20 章，要从第 21 章继续，打开并编辑：

```text
continue_writing.sh
```

主要改这几项：

```bash
PROJECT_ID="Urban-cultivation-in-ancient-times"
START_CHAPTER="21"
CHAPTER_COUNT="20"
```

运行：

```bash
./continue_writing.sh
```

只续写 5 章可以这样临时覆盖：

```bash
PROJECT_ID="Urban-cultivation-in-ancient-times" START_CHAPTER=21 CHAPTER_COUNT=5 ./continue_writing.sh
```

`CHAPTER_COUNT=0` 或 `CHAPTER_COUNT=all` 表示从 `START_CHAPTER` 一直写到规划里的最后一章：

```bash
PROJECT_ID="Urban-cultivation-in-ancient-times" START_CHAPTER=21 CHAPTER_COUNT=0 ./continue_writing.sh
```

续写脚本只执行：

```text
write
```

它不会重新规划，也不会重新抽规则。

## 3. 扩展大纲

如果当前 `novel_plan.json` 只有 20 章，但你想继续写第 21 章以后，先扩展大纲：

```bash
PROJECT_ID="Urban-cultivation-in-ancient-times" TARGET_CHAPTERS=40 ./extend_outline.sh
```

这个脚本会读取：

```text
data/projects/<PROJECT_ID>/novel_plan.json
data/projects/<PROJECT_ID>/writing_state.json
data/projects/<PROJECT_ID>/chapters/*.json
```

然后把 `chapter_plan` 扩展到 `TARGET_CHAPTERS`。它会自动备份旧规划，备份文件类似：

```text
data/projects/<PROJECT_ID>/novel_plan.before_extend_20260519_140000.json
```

扩展完成后，再续写：

```bash
PROJECT_ID="Urban-cultivation-in-ancient-times" START_CHAPTER=21 CHAPTER_COUNT=10 ./continue_writing.sh
```

## 4. 如果缺少规则书

如果运行新书脚本时报错：

```text
未找到规则书 data/final/novel_rulebook.json
```

先执行一次：

```bash
./build_rules.sh --run-mode fresh --limit-rule-novels 120
```

这一步会读取 `novalv1/novalv2` 抽取写作规则，耗时较长。跑完后，后续写新书和续写都不需要再跑。

## 5. 模型配置

模型配置在：

```text
.env
```

常用配置示例：

```bash
LLM_PROFILE=codex-lb
CODEX_LB_API_KEY="你的 key"
CODEX_LB_BASE_URL=https://codex-lb.vvicat.dev/v1
```

或者 OpenAI：

```bash
LLM_PROFILE=openai
OPENAI_API_KEY="你的 key"
OPENAI_BASE_URL=https://api.openai.com/v1
```

## 6. 注意事项

写正文阶段是顺序执行，所以你会看到：

```text
[write] start total=..., concurrency=1
```

这是正常的。章节之间要读取前文摘要、章节尾巴、伏笔和 `writing_state.json`，并行写容易导致逻辑错乱。
