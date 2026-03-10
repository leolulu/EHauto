# 自动化种子生成与上传工具

基于 qBittorrent Web API 和 e-hentai 平台的自动化种子处理工具集。

---

## 📋 项目背景与目的

### 背景
在 PT/Private Tracker 和 e-hentai 等平台分享资源时，需要：
1. 创建 .torrent 种子文件
2. 配置正确的 tracker 服务器
3. 上传到目标平台

手动操作繁琐，尤其是批量处理时。

### 目的
- **自动化生成种子**：通过 qBittorrent Web API 远程创建种子
- **支持 SMB 路径映射**：本地文件自动上传到远程服务器后生成
- **e-hentai 集成**：自动提取画廊专属 tracker 并上传种子
- **减少重复劳动**：一键完成从本地文件到平台发布的流程

---

## 🛠 环境要求

- Python 3.10+
- qBittorrent v5.0.0+ (Web API v2.10.4+)
- 远程服务器需启用 SMB 共享和 qBittorrent Web UI
- e-hentai 账号（用于上传种子）

### 安装依赖

请先进入当前子项目目录，再执行下面的命令；这个目录本身就是一个独立项目，依赖与锁文件都只在当前目录内维护。

```bash
uv sync
```

---

## 📁 项目结构

```
自动化种子生成做种项目/
├── full_workflow.py           # 完整工作流总控脚本
├── create_torrent.py          # 种子生成脚本（本地→SMB→qBittorrent）
├── ehentai_uploader.py        # e-hentai 种子上传工具
├── seed_personalized.py       # 使用专属种子开始做种
├── eht-netscape.cookie        # e-hentai Cookie 文件（Netscape 格式）
├── .env.example               # 环境变量配置模板
├── pyproject.toml             # 项目元数据与 Python 依赖
├── uv.lock                    # uv 锁文件
└── README.md                 # 项目文档
```

---

## 📖 脚本说明

### 0. full_workflow.py - 完整工作流总控

**功能**：
- 以压缩包路径作为唯一主入口，自动读取旁边同名 JSON 元数据
- 自动获取 e-hentai 画廊专属 tracker
- 上传本地文件到远程服务器并生成原始 torrent
- 上传原始 torrent 到 e-hentai，并自动下载 personalized torrent
- 使用 personalized torrent 在 qBittorrent 中正式开始做种

**工作流程**：
```
本地文件/目录
    ↓
🔗 获取画廊专属 tracker
    ↓
⚙️  生成原始 torrent
    ↓
📤 上传到 e-hentai
    ↓
📥 自动下载 personalized torrent
    ↓
🌱 添加到 qBittorrent 正式做种
```

**推荐使用方法**：

```bash
# 单文件完整流程（自动读取同名 JSON 中的画廊信息）
uv run python full_workflow.py \
  "downloads/文件.zip"

# 目录批处理：逐个处理目录下所有 .zip
uv run python full_workflow.py \
  "downloads"

# 指定分类和远程子目录
uv run python full_workflow.py \
  "downloads/文件.zip" \
  --category "E-Hentai/2026" \
  --remote-dir "ehentai/2026"

# 手动覆盖 JSON 中的 gallery URL
uv run python full_workflow.py \
  "downloads/文件.zip" \
  --gallery-url "https://e-hentai.org/g/3829655/7bc8cc9e4e/"
```

**命令行参数**：

| 参数 | 说明 |
|------|------|
| `source` | 待处理 `.zip` 路径，或包含多个 `.zip` 的目录路径（必需） |
| `--gallery-url` | 手动指定 e-hentai 画廊 URL（仅单文件模式） |
| `--json` | 手动指定 JSON 元数据文件路径（仅单文件模式） |
| `--cookie` | Cookie 字符串 |
| `--cookie-file` | Cookie 文件路径（默认：`eht-netscape.cookie`） |
| `--proxy` | HTTP 代理地址（默认：`http://127.0.0.1:10809`） |
| `--output-dir` | 原始 torrent 与 personalized torrent 的输出目录 |
| `--output` | 原始 torrent 输出路径（默认自动命名） |
| `--remote-dir` | 远程子目录 |
| `--category` | 做种分类（默认：`autoEH`） |
| `--comment` | 上传到 e-hentai 时附带评论 |

**为什么推荐用它**：
- 压缩包本身就是入口，不需要额外把画廊 URL 当主参数
- 画廊链接、标题等信息默认直接从旁边同名 JSON 读取
- 不需要手动在三个脚本之间传递中间文件路径
- 不需要再手动传 tracker、personalized 种子路径、做种目录
- 做种时会先保留生成阶段得到的精确内容路径，再自动转换成 qBittorrent 需要的父目录 save path

**输入约定**：
- 推荐输入一个压缩包，例如 `downloads/xxx.zip`
- 同目录下应存在同名 JSON，例如 `downloads/xxx.json`
- `full_workflow.py` 默认从 JSON 里的 `gallery.url` 读取画廊链接
- 如果输入的是目录，脚本会只扫描该目录第一层里的所有 `.zip`，并按单文件流程逐个处理
- 目录批处理要求每个 `.zip` 都有同目录同名 `.json`；缺失时会把该项记为失败并继续处理后续 `.zip`
- 目录批处理模式下不支持 `--json`、`--gallery-url`、`--output`
- 目录批处理默认是“继续下一个”模式，不会因为某个 `.zip` 失败就中断整个目录；结束时会输出成功/失败汇总
- 单文件和目录批处理都会在完整成功后自动删除原始 `.zip` 和配套 `.json`；失败条目不会删除，方便排查和重跑

**JSON 元数据最少需要包含**：

```json
{
  "gallery": {
    "url": "https://e-hentai.org/g/3828547/5ca5c1fc0d/"
  },
  "download": {
    "saved_path": "C:/Users/YXY/Downloads/xxx.zip"
  }
}
```

- `gallery.url`：`full_workflow.py` 用来定位画廊、获取专属 tracker、上传种子
- `download.saved_path`：`seed_personalized.py` 在单独重跑第三步时可用来辅助还原原始文件名

**做种成功的关键设置**：
- `save_path` 必须传父目录，而不是单文件完整路径
- `use_auto_torrent_management=False`，对应 qBittorrent UI 里的“手动模式”
- `content_layout="Original"`，对应 qBittorrent UI 里的“内容布局 = 原始”
- `ratio_limit=-1`、`seeding_time_limit=-1`、`inactive_seeding_time_limit=-1`，对应单种子不限时/不限量做种
- 这三点一起满足时，qBittorrent 才会直接在父目录下寻找现有压缩包，而不是额外创建子目录后再去找文件

**不限时做种策略**：
- 当前脚本默认会覆盖 qBittorrent 的全局分享限制设置
- 也就是说，即使你的下载器全局配置里存在默认的做种时长/分享率上限，脚本添加的这类种子仍会按“单种子无限制”处理
- 这套行为是工作流内置策略，不对用户暴露额外参数

### 1. create_torrent.py - 种子生成

**功能**：
- 将本地文件/目录自动上传到远程 SMB 服务器
- 自动转换 SMB 路径为服务器绝对路径
- 调用远程 qBittorrent API 生成种子
- 下载种子文件到本地
- 支持自定义 tracker

**工作流程**：
```
本地文件/目录
    ↓
📤 自动上传到 SMB 服务器（保持目录结构）
    ↓
🔄 路径转换（SMB 路径 → 服务器绝对路径）
    ↓
⚙️  调用远程 qBittorrent 生成种子
    ↓
📥 下载种子文件到本地
```

**配置方法**（必须通过 .env 文件）：

脚本**只从 `.env` 文件读取配置**，不支持环境变量。如果缺少 `.env` 文件或配置项，脚本会报错并提示。

1. 复制模板文件：
```bash
cp .env.example .env
```

2. 编辑 `.env` 文件，填入你的实际配置：
```bash
SMB_ROOT_PATH=//192.168.1.100/share
SERVER_ROOT_PATH=/home/user/data
QB_HOST=192.168.1.100
QB_PORT=8080
QB_USERNAME=admin
QB_PASSWORD=你的密码
```

3. 运行脚本，如有缺失配置会提示补全

**必需配置项**（缺少会报错）：

| 配置项 | 说明 | 示例 |
|--------|------|------|
| `SMB_ROOT_PATH` | SMB 根路径（本地访问方式） | `//192.168.1.100/share` |
| `SERVER_ROOT_PATH` | 服务器绝对路径 | `/home/user/data` |
| `QB_HOST` | qBittorrent 服务器 IP | `192.168.1.100` |
| `QB_PORT` | Web UI 端口 | `8080` |
| `QB_USERNAME` | 登录用户名 | `admin` |
| `QB_PASSWORD` | 登录密码 | - |

**可选配置项**：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `SMB_USER` | SMB 用户名 | 空 |
| `SMB_PASS` | SMB 密码 | 空 |
| `TRACKERS` | Tracker 列表（逗号分隔） | 空 |
| `TORRENT_COMMENT` | 种子注释 | Created by auto torrent workflow |

**使用方法**：

```bash
# 上传单个文件并生成种子
uv run python create_torrent.py -f "C:\Users\YXY\Videos\movie.mkv" -o "movie.torrent"

# 上传目录（递归）
uv run python create_torrent.py -d "C:\Users\YXY\Videos\合集" -o "合集.torrent"

# 指定远程子目录
uv run python create_torrent.py -f movie.mkv -o movie.torrent --remote-dir "movies/2024"

# 添加自定义 tracker
uv run python create_torrent.py -f movie.mkv -o movie.torrent \
  -t "https://tracker.example.com/announce"

# 从文件读取 tracker 列表
uv run python create_torrent.py -f movie.mkv -o movie.torrent \
  --trackers-file trackers.txt
```

**命令行参数**：

| 参数 | 说明 |
|------|------|
| `-f, --file` | 本地文件路径 |
| `-d, --dir` | 本地目录路径（递归上传） |
| `-o, --output` | 输出种子文件路径（必需） |
| `--remote-dir` | 远程子目录（在 SMB 根路径下） |
| `-t, --tracker` | 添加 tracker（可多次使用） |
| `--trackers-file` | 从文件读取 tracker 列表 |
| `--smb-user` | SMB 用户名（无认证留空） |
| `--smb-pass` | SMB 密码 |

---

### 2. ehentai_uploader.py - e-hentai 种子上传

**功能**：
- 自动读取 Cookie 文件（支持 Netscape 格式）
- 提取画廊专属 tracker（格式：`http://ehtracker.org/{gid}/announce`）
- 上传种子文件到 e-hentai
- 上传成功后自动下载 personalized 种子
- 支持评论添加

**工作流程**：
```
e-hentai 画廊页面
    ↓
🔐 使用 Cookie 登录
    ↓
📊 获取画廊信息（GID, Token, Title）
    ↓
🔗 提取专属 tracker（http://ehtracker.org/{gid}/announce）
    ↓
📤 上传种子文件到 repo.e-hentai.org
```

**配置方法**：
- Cookie 文件：默认为当前目录的 `eht-netscape.cookie`
- 或使用命令行参数 `--cookie` 指定 Cookie 字符串

**获取 Cookie**：
1. 浏览器登录 e-hentai.org
2. 按 F12 打开开发者工具
3. 复制 `Cookie` 请求头
4. 使用 Cookie Editor 等扩展导出为 Netscape 格式

**使用方法**：

```bash
# 获取画廊专属 tracker（自动读取 eht-netscape.cookie）
uv run python ehentai_uploader.py https://e-hentai.org/g/3828071/76966bded7/

# 保存 tracker 到文件
uv run python ehentai_uploader.py https://e-hentai.org/g/3828071/76966bded7/ -o tracker.txt

# 指定 Cookie 文件
uv run python ehentai_uploader.py -f mycookie.txt https://e-hentai.org/g/xxx/yyy/

# 使用 Cookie 字符串
uv run python ehentai_uploader.py -c "ipb_member_id=xxx; ipb_pass_hash=xxx;" https://e-hentai.org/g/xxx/

# 上传种子
uv run python ehentai_uploader.py -f eht-netscape.cookie \
  --upload "种子.torrent" \
  https://e-hentai.org/g/3828071/76966bded7/

# 带评论上传
uv run python ehentai_uploader.py -f eht-netscape.cookie \
  --upload "种子.torrent" \
  --comment "感谢发布！" \
  https://e-hentai.org/g/3828071/76966bded7/
```

**命令行参数**：

| 参数 | 说明 |
|------|------|
| `url` | e-hentai 画廊 URL（必需） |
| `-c, --cookie` | Cookie 字符串 |
| `-f, --cookie-file` | Cookie 文件路径（默认：eht-netscape.cookie） |
| `-u, --upload` | 上传种子文件（指定.torrent 文件路径） |
| `--comment` | 种子评论 |
| `-o, --output` | 输出文件路径（保存 tracker） |
| `--skip-download` | 上传后不下载 personalized 种子 |
| `--output-dir` | personalized 种子保存目录（默认：generated_torrents） |

**e-hentai 要求**：
- 最大种子文件大小：**10 MB**
- Tracker 格式：`http://ehtracker.org/{gid}/announce`（每个画廊专属）
- 需要登录才能上传

---

### 3. seed_personalized.py - 使用专属种子做种

**功能**：
- 读取 e-hentai 生成的专属种子（personalized torrent）
- 自动推断远程服务器上的文件路径
- 添加到 qBittorrent 做种（跳过哈希检查）
- 支持设置分类便于管理

**工作流程**：
```
personalized torrent 文件
    ↓
🤖 自动推断远程文件路径
    ↓
➕ 添加到 qBittorrent
    ↓
⚡ 跳过哈希检查，直接做种
```

**使用方法**：

```bash
# 基本用法（自动推断目录，默认分类 "autoEH"）
uv run python seed_personalized.py \
  "generated_torrents/[Kakutou Oukoku] Katei Saien Vol. 1 [Digital]_personalized.torrent"

# 指定分类
uv run python seed_personalized.py \
  "generated_torrents/种子_personalized.torrent" \
  -c "E-Hentai/2024"

# 使用 JSON 元数据精确推断路径
uv run python seed_personalized.py \
  "generated_torrents/种子_personalized.torrent" \
  -j "downloads/文件.json"

# 手动指定做种目录（覆盖自动推断）
uv run python seed_personalized.py \
  "generated_torrents/种子_personalized.torrent" \
  -s "/mnt/data/files"
```

**命令行参数**：

| 参数 | 说明 |
|------|------|
| `torrent` | personalized torrent 文件路径（必需） |
| `-c, --category` | 分类名称（默认：autoEH） |
| `-s, --save-path` | 做种目录（覆盖自动推断） |
| `-j, --json` | JSON 元数据文件（用于精确推断路径） |

**路径推断逻辑**：
1. 如果提供 `-j JSON` 参数，从元数据读取原始文件名
2. 否则从种子文件名（去掉 `_personalized` 后缀）推断
3. 结合 `.env` 中的 `SERVER_ROOT_PATH` 构建完整内容路径
4. 再自动转换为 qBittorrent 需要的“父目录 save path”

**注意**：
- 必须使用 personalized 版本（包含 e-hentai 专属 tracker）
- 需要确保远程服务器上的文件仍然存在
- 使用 `is_skip_checking=True` 跳过哈希验证，直接做种
- 做种时会显式使用手动模式（`use_auto_torrent_management=False`）
- 内容布局会显式设置为 `Original`，避免 qBittorrent 自动新建子文件夹后找不到文件
- 如果手动传 `--save-path`，这里应该传父目录，而不是单文件完整路径

---

## 🔗 完整工作流

### 场景 1：从本地文件到 e-hentai 发布

```bash
# 推荐：直接使用总控脚本完成全部流程
uv run python full_workflow.py \
  "downloads/文件.zip" \
  --category "E-Hentai"
```

说明：
- `full_workflow.py` 会自动串联 tracker 获取、原始 torrent 生成、上传、personalized 下载和正式做种
- 默认会读取压缩包旁边的同名 JSON，并从 `gallery.url` 里获取画廊链接
- 下载得到的 personalized 种子会保存到 `generated_torrents/`，文件名后缀为 `_personalized.torrent`
- 正式做种时会直接使用生成阶段得到的服务器精确路径，而不是依赖文件名反推
- 正式做种时会强制使用 qBittorrent 手动模式，并把内容布局设为 `Original`

### 场景 2：远程服务器已有文件

```bash
# 如果文件已在 SMB 服务器上，直接生成原始种子（更偏底层调试/单步使用）
uv run python create_torrent.py \
  -f "文件.zip" \
  -o "种子.torrent" \
  -t "https://your-tracker.com/announce"
```

说明：
- 这个场景更适合单独调试“生成种子”步骤
- 如果目标是完整 e-hentai 工作流，仍建议优先使用 `full_workflow.py`

---

## ⚠️ 注意事项

### qBittorrent 配置
1. 启用 **Web UI**（工具 → 选项 → Web UI）
2. 设置用户名和密码
3. 版本要求：**v5.0.0+**（需要 Torrent Creator API）
4. 确保远程服务器可以访问 SMB 共享路径

### SMB 配置
- Windows：右键文件夹 → 属性 → 共享
- Linux：配置 Samba（/etc/samba/smb.conf）
- 确保 qBittorrent 所在服务器可以访问 SMB 路径
- 当前脚本在 Windows 下通过 UNC 路径直接复制文件，默认复用系统/资源管理器已登录的共享凭据
- `.env` 里的 `SMB_USER` / `SMB_PASS` 当前保留为兼容字段，通常无需填写

### e-hentai 配置
- 需要注册账号并登录
- Cookie 文件需保持最新（过期后重新导出）
- 每个画廊有专属 tracker，不可混用
- 种子文件大小限制：**10 MB**

---

## 📝 常见问题

### Q: 路径映射如何配置？
```python
# 本地通过 SMB 访问的路径
SMB_ROOT_PATH = r"\\192.168.1.100\share"

# 服务器上该 share 对应的绝对路径
SERVER_ROOT_PATH = "/home/user/data"

# 映射关系：
# \\192.168.1.100\share\movies\file.mkv  →  /home/user/data/movies/file.mkv
```

### Q: 如何获取 e-hentai Cookie？
1. 浏览器安装 Cookie Editor 扩展
2. 登录 e-hentai.org
3. 导出 Cookie 为 Netscape 格式
4. 保存为 `eht-netscape.cookie`

### Q: 种子生成失败？
- 检查 qBittorrent 版本（需 v5.0.0+）
- 确认 Web UI 可访问
- 检查 SMB 路径映射是否正确
- 查看脚本输出的错误信息

### Q: 做种任务添加成功了，但 qBittorrent 里提示找不到文件？
这是这套流程里最容易踩的坑，通常由以下三个条件不满足导致：

1. **保存路径必须是父目录，不是单文件完整路径**
   - 正确：`D:\transfer\torrent adder\auto`
   - 错误：`D:\transfer\torrent adder\auto\file.zip`
2. **Torrent 管理模式必须是手动模式**
   - 脚本中对应 `use_auto_torrent_management=False`
   - 如果启用自动管理，qBittorrent 可能忽略你指定的保存位置
3. **内容布局必须是 `Original`**
   - 脚本中对应 `content_layout="Original"`
   - 否则 qBittorrent 可能新建子文件夹，进而去错误的嵌套路径里找文件

当前脚本已经显式按上面三点提交参数。

### Q: 为什么 `full_workflow.py` 要从压缩包旁边读取同名 JSON？
因为压缩包本身是工作流的真实入口，而画廊链接、原始下载信息都已经在元数据里：

- `gallery.url`：用于获取 e-hentai 画廊、专属 tracker、上传种子
- `download.saved_path`：用于在需要时还原原始文件名/路径信息

推荐文件组织方式：

```text
downloads/
├── example.zip
└── example.json
```

### Q: 如果第一步和第二步已经成功，怎么只重跑第三步（开始做种）？
直接使用已经下载好的 personalized torrent：

```bash
uv run python seed_personalized.py \
  "generated_torrents/example_personalized.torrent" \
  -j "downloads/example.json"
```

这适用于：
- 只是想重新测试做种参数
- 之前因为保存路径/管理模式/内容布局配置不对，想单独重试第三步
- 不想重复向 e-hentai 上传

### Q: 上传成功但没有下载到 personalized torrent？
- 脚本会自动重试刷新 `gallerytorrents.php` 页面多次
- 页面里的 `href` 往往只是静态占位链接，浏览器真实点击时通常会走 `onclick` 里的动态专属下载地址
- 当前脚本会优先提取这个动态专属链接，而不是直接使用静态 `href`
- 如果仍失败，先检查 e-hentai 页面上是否真的已经生成新种子
- 失败时优先查看终端输出；上传失败时还会生成 `upload_response.html` 便于排查
- 如果连续下载到无效文件，脚本会保存 `*_personalized.invalid.bin` 调试文件

### Q: 如果同一个 personalized torrent 已经加到 qBittorrent 里，再跑一次会怎样？
- 当前脚本会把“已存在同 hash torrent”的情况视为成功
- 也就是说，第 4 步现在是幂等的：重复执行不会因为已存在而把整条流程判失败
- 这对重新验证流程、重跑绝对路径输入、或重复测试脚本特别有用

### Q: Windows 终端里中文输出乱码怎么办？
- 旧的控制台编码注入方案已经移除，不再通过脚本内修改 `stdout/stderr` 编码来处理
- 如果仍有个别终端乱码，优先使用 Windows Terminal 或确认终端代码页/字体支持 UTF-8

---

## 📄 许可证

本项目仅供学习研究使用。

---

## 🙏 致谢

- [qBittorrent](https://www.qbittorrent.org/) - 强大的 BT 客户端
- [qbittorrent-api](https://github.com/rmartin16/qbittorrent-api) - Python API 封装
- [e-hentai](https://e-hentai.org/) - 资源分享平台
