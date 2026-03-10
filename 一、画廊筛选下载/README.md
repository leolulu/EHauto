# e-hentai 高价值画廊筛选器

自动筛选 e-hentai 网站上性价比最高的无 torrent 画廊，通过综合评估 Rating、收藏数、GP 成本、文件大小等指标，推荐最值得下载的 **Original Archive**。

## 功能特性

- ✅ 自动筛选无 torrent 的画廊
- ✅ 获取 Original Archive 的 GP 成本和文件大小
- ✅ 综合评分模型（Rating、收藏数、GP/页、GP/MB、页数）
- ✅ 按投入产出比排序
- ✅ 支持自定义筛选条件
- ✅ 输出详细的推荐报告

## 评分模型（满分 100 分）

| 因素 | 权重 | 说明 |
|------|------|------|
| Rating | 30 分 | 4.0+ 满分，2.0 以下 0 分 |
| 收藏次数 | 20 分 | 100+ 收藏满分 |
| GP/页 成本 | 25 分 | 越低越好，10GP/页以内高分 |
| GP/MB 成本 | 15 分 | 越低越好，50GP/MB 以内高分 |
| 页数充足度 | 10 分 | 100-300 页最佳 |

## 快速开始

### 安装依赖

请先进入当前子项目目录，再执行下面的命令；这个目录本身就是一个独立项目，依赖与锁文件都只在当前目录内维护。

```bash
# 在当前子项目目录同步依赖
uv sync

# 安装浏览器
uv run playwright install chromium
```

### 基本使用

```bash
# 使用默认参数
uv run python ehentai_value_filter.py

# 查看帮助
uv run python ehentai_value_filter.py --help
```

### 常用命令

```bash
# 扫描更多列表页（默认 2 页）
uv run python ehentai_value_filter.py --pages 10

# 降低 Rating 门槛（2.0 分以上）
uv run python ehentai_value_filter.py --min-rating 2.0

# 显示浏览器窗口（调试用，默认无头模式）
uv run python ehentai_value_filter.py --show-browser

# 自定义输出文件
uv run python ehentai_value_filter.py -o my_recommendations.txt
```

## 参数说明

| 参数 | 简写 | 默认值 | 说明 |
|------|------|--------|------|
| --cookie-file | -f | eht-netscape.cookie | Cookie 文件路径 |
| --proxy | -s | http://127.0.0.1:10809 | 代理地址 |
| --url | -u | https://e-hentai.org/?f_cats=1019 | 列表页 URL |
| --pages | -p | 2 | 抓取列表页数 |
| --min-rating | | 3.0 | 最低 Rating |
| --min-pages | | 40 | 最低页数 |
| --output | -o | ehentai_recommendations.txt | 输出文件 |
| --show-browser | | | 显示浏览器窗口（默认无头模式） |

## Cookie 获取

1. 浏览器登录 e-hentai.org
2. 使用 Cookie 编辑扩展（如 Cookie-Editor）
3. 导出 Netscape 格式 Cookie 文件
4. 或使用现有的 `eht-netscape.cookie` 文件

需要的 Cookie：
- `ipb_member_id`
- `ipb_pass_hash`

## 输出示例

```
可用 GP: 39,000 | 筛选出 2 个高价值画廊
================================================================================

[ 1] [榊歌丸] むちナビ（Chinese）【更新中】
     URL: https://e-hentai.org/g/3827467/a45576b0b0/
     分类：Manga | 上传者：战栗的大白菜
     页数：105 | 大小：98.03 MiB
     Rating: 2.79 (38 人评分) | 收藏：213 次
     GP 成本：2,056 GP
     GP/页：19.58 | GP/MB: 20.97
     【综合评分：59.6/100】

[ 2] [migiwa×MoonKOKi] 誰も言わない、みんなクズ 第 01 巻
     URL: https://e-hentai.org/g/3827743/01a4d4db13/
     分类：Manga | 上传者：msfly99
     页数：166 | 大小：80.09 MiB
     Rating: 2.91 (11 人评分) | 收藏：25 次
     GP 成本：1,680 GP
     GP/页：10.12 | GP/MB: 20.98
     【综合评分：45.5/100】
```

## 工作原理

1. **登录账户** - 使用 Cookie 登录
2. **获取 GP 余额** - 从 GP Exchange 页面读取可用 GP
3. **提取画廊列表** - 访问列表页，筛选无 torrent 画廊
4. **获取详情** - 访问每个画廊详情页获取 Rating、收藏数
5. **获取 GP 成本** - 访问 Archiver 页面获取 Original Archive 的 GP
6. **计算评分** - 综合各项指标计算价值评分
7. **排序输出** - 按评分降序输出推荐列表

## 注意事项

1. 脚本只筛选无 torrent 的画廊（有 torrent 的可以直接下载）
2. GP 成本基于 **Original Archive**（原始画质）
3. 评分是相对的，高分表示在当前列表中性价比更高
4. 建议先用小号或少量画廊测试

## 完整工作流程

```bash
# 1. 筛选高价值画廊（默认扫描 2 页；这里演示扫描 5 页）
uv run python ehentai_value_filter.py --pages 5

# 2. 下载筛选出的画廊（前 3 个）
uv run python ehentai_downloader.py --input ehentai_recommendations.txt --count 3
```

### 脚本说明

**`ehentai_value_filter.py`** - 完整版本，包含综合评分和推荐

**`ehentai_downloader.py`** - 画廊下载器，根据推荐文件自动下载 Original Archive，并在压缩包旁边生成同名 JSON 元信息文件

| 参数 | 简写 | 默认值 | 说明 |
|------|------|--------|------|
| --input | -i | ehentai_recommendations.txt | 推荐文件路径 |
| --url | -u | | 单个画廊 URL（使用此参数时忽略 --input） |
| --count | -n | 999 | 下载前 N 个画廊 |
| --min-score | | 0 | 最低评分要求，只下载评分大于等于此值的画廊 |
| --output | -o | downloads | 输出目录 |
| --cookie-file | -f | eht-netscape.cookie | Cookie 文件路径 |
| --proxy | -s | http://127.0.0.1:10809 | 代理地址 |
| --delay | | 5 | 下载间隔秒数（防 ban） |
| --show-browser | | | 显示浏览器窗口（默认无头模式） |

### 下载流程

1. **筛选阶段** - `ehentai_value_filter.py` 扫描画廊列表，计算综合评分，生成推荐文件
2. **下载阶段** - `ehentai_downloader.py` 读取推荐文件，访问 Archiver 页面，自动点击下载按钮
3. **保存阶段** - 脚本保存下载的 Original Archive 压缩包，并在同一路径生成同名 `.json` 元信息文件
4. **验证阶段** - 脚本自动验证下载文件完整性，输出文件大小、保存位置和元信息文件名

### 下载结果

每个下载结果会生成两个彼此对应的文件：

- `downloads/<archive-name>.zip` - 下载得到的 Original Archive 压缩包
- `downloads/<archive-name>.json` - 与压缩包同名的元信息文件

JSON 中会尽可能保存下载时能获取到的关联信息，包括但不限于：

- 推荐文件中的排名、评分、GP 成本、GP/页、GP/MB
- 画廊详情页中的标题、分类、上传者、页数、评分人数、收藏数、标签、画廊 URL
- Archiver 页中的下载成本、估算大小、Archiver URL
- 本地文件信息，如保存路径、文件大小、SHA256、ZIP 条目概览
- 下载运行时信息，如批次序号、下载模式、可用 GP、输出目录、代理设置

**注意**：下载功能需要有效的 Cookie（已登录账户），并且账户需要有足够的 GP 余额。

## 环境要求

- Python 3.10+
- playwright
- Chromium 浏览器

## 许可证

MIT License
