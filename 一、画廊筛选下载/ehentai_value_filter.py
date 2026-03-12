#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
e-hentai 高价值画廊筛选器
========================

本脚本用于自动筛选 e-hentai 网站上高价值的画廊（无 torrent 资源），
通过综合评估 Rating、收藏数、GP 成本、文件大小等指标，
推荐投入产出比（性价比）最高的画廊进行 Original Archive 下载。

## 背景说明

e-hentai 是一个大型画廊网站，用户可以通过以下方式下载内容：
1. Torrent 下载 - 免费，但需要种子资源
2. Archive Download - 使用 GP (Gallery Points) 购买下载权限
   - Original Archive: 原始画质，文件较大，GP 成本较高
   - （本脚本仅支持 Original Archive）

GP 是网站的虚拟货币，通过以下方式获得：
- 画廊访问
- Torrent 完成
- 归档下载
- Hentai@Home

由于 GP 有限，本脚本帮助你在预算内选择最值得下载的画廊。

## 评分模型（满分 100 分）

| 因素           | 权重 | 评分标准                                    |
|----------------|------|---------------------------------------------|
| Rating         | 30 分 | 4.0+ 得满分，2.0 以下得 0 分，线性插值          |
| 收藏次数       | 20 分 | 100+ 收藏得满分，线性插值                     |
| GP/页 成本     | 25 分 | 越低越好，10GP/页以内高分                   |
| GP/MB 成本     | 15 分 | 越低越好，50GP/MB 以内高分                  |
| 页数充足度     | 10 分 | 100-300 页最佳，过少或过多都会扣分          |

## 筛选流程

1. 登录账户，获取可用 GP 余额
2. 访问指定列表页，提取无 torrent 的画廊
3. 用列表页 Rating 和页数做初筛，减少详情页访问
3. 对每个画廊：
    - 访问详情页获取 Rating、收藏数、文件大小
    - 访问 Archiver 页面获取下载所需 GP
4. 按最大文件大小限制过滤超大画廊
5. 计算综合价值评分
6. 按评分排序，输出 Top N 推荐

## 依赖

- Python 3.10+
- 在当前目录同步 Python 依赖：uv sync
- 需要安装浏览器：uv run playwright install chromium

## 使用方法

### 基本使用
```bash
# 使用默认参数（处理 20 个，返回 Top 10）
uv run python ehentai_value_filter.py

# 使用 Cookie 文件
uv run python ehentai_value_filter.py -f eht-netscape.cookie
```

### 自定义参数
```bash
# 扫描更多列表页（默认 2 页）
uv run python ehentai_value_filter.py --pages 10

# 降低 Rating 门槛
uv run python ehentai_value_filter.py --min-rating 2.0

# 跳过超过 1.5GB 的画廊
uv run python ehentai_value_filter.py --max-size-gb 1.5

# 显示浏览器窗口（调试用）
uv run python ehentai_value_filter.py --show-browser

# 指定输出文件
uv run python ehentai_value_filter.py -o my_recommendations.txt
```

### 完整参数列表

| 参数 | 简写 | 默认值 | 说明 |
|------|------|--------|------|
| --cookie-file | -f | eht-netscape.cookie | Netscape 格式的 Cookie 文件路径 |
| --proxy | -s | http://127.0.0.1:10809 | 代理服务器地址 |
| --url | -u | https://e-hentai.org/?f_cats=1019 | 目标列表页 URL |
| --pages | -p | 2 | 抓取的列表页数 |
| --min-rating | | 3.0 | 最低 Rating 要求 |
| --min-pages | | 40 | 最低页数要求 |
| --max-size-gb | | 1.0 | 最大原始文件大小（GB），超过则跳过 |
| --output | -o | ehentai_recommendations.txt | 输出文件名 |
| --show-browser | | | 显示浏览器窗口（默认无头模式） |

## Cookie 获取方法

1. 在浏览器中登录 e-hentai.org
2. 安装 Cookie 编辑扩展（如 Cookie-Editor）
3. 导出 Netscape 格式的 Cookie 文件
4. 或使用本项目的 eht-netscape.cookie 文件

需要的 Cookie：
- ipb_member_id
- ipb_pass_hash

## 输出示例

```
可用 GP: 39,000 | 筛选出 2 个高价值画廊
================================================================================

[ 1] [榊歌丸] むちナビ（Chinese）【更新中】
     URL: https://e-hentai.org/g/3827467/a45576b0b0/
     分类：Manga | 上传者：战栗的大白菜
     页数：105 | 大小：98.03 MiB
     Rating: 2.79 (38 人评分) | 收藏：212 次
     GP 成本：2,056 GP
     GP/页：19.58 | GP/MB: 20.97
     【综合评分：59.6/100】

[ 2] [migiwa×MoonKOKi] 誰も言わない、みんなクズ 第 01 巻
     URL: https://e-hentai.org/g/3827743/01a4d4db13/
     分类：Manga | 上传者：msfly99
     页数：166 | 大小：80.09 MiB
     Rating: 2.70 (10 人评分) | 收藏：24 次
     GP 成本：1,680 GP
     GP/页：10.12 | GP/MB: 20.98
     【综合评分：43.8/100】
```

## 注意事项

1. 脚本会自动筛选无 torrent 的画廊（有 torrent 的可以直接下载）
2. GP 成本基于 Original Archive（原始画质）
3. 列表页会先按 Rating 和页数做初筛，降低详情页访问量
4. 原始文件大小超过最大限制的画廊会被跳过（默认 1GB）
5. 评分是相对的，高分表示在当前列表中性价比更高
6. 建议先用小号或少量画廊测试

## 作者

自动化下载做种项目

## 许可证

PolyForm Noncommercial License 1.0.0

详见项目根目录 `LICENSE` 文件：
https://polyformproject.org/licenses/noncommercial/1.0.0/
"""

import re
import sys
from dataclasses import asdict, dataclass
from typing import Literal, TypedDict


class CookieParam(TypedDict, total=False):
    name: str
    value: str
    url: str | None
    domain: str | None
    path: str | None
    expires: float | None
    httpOnly: bool | None
    secure: bool | None
    sameSite: Literal['Lax', 'None', 'Strict'] | None
    partitionKey: str | None


@dataclass
class GalleryInfo:
    """画廊信息"""
    gid: str
    token: str
    title: str
    url: str
    source_list_url: str
    category: str
    uploader: str
    pub_date: str
    pages: int
    file_size_mb: float  # 原始文件大小 (MiB)
    rating: float  # 平均评分 (0-5)
    rating_count: int  # 评分人数
    favorited_count: int  # 收藏次数
    list_rating: float = 0  # 列表页解析出的 0.5 精度评分
    list_rating_votes_hint: int | None = None  # 列表页 opacity 反推出的评分人数强度
    list_rating_style: str = ''  # 列表页 .ir 原始 style
    
    # 下载信息 (Original Archive)
    cost_gp: float = 0  # GP 成本
    size_mb: float = 0  # 下载大小
    
    # 评分指标
    value_score: float = 0  # 综合价值评分
    gp_per_page: float = 0  # 每页 GP 成本
    gp_per_mb: float = 0  # 每 MB GP 成本
    
    def to_dict(self):
        return asdict(self)
    
    def get_archiver_url(self) -> str:
        """获取 Archiver 下载页面 URL"""
        return f'https://e-hentai.org/archiver.php?gid={self.gid}&token={self.token}'


def parse_netscape_cookie_file(file_path: str) -> list[CookieParam]:
    """解析 Netscape 格式的 cookie 文件"""
    cookies: list[CookieParam] = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t')
            if len(parts) >= 7:
                domain, flag, path, secure, expiration, name, value = parts[:7]
                if not domain.startswith('.'):
                    domain = '.' + domain
                cookies.append({
                    'name': name,
                    'value': value,
                    'domain': domain,
                    'path': path,
                })
    return cookies


def parse_size_to_mb(size_str: str) -> float:
    """将文件大小字符串转换为 MB"""
    size_str = size_str.strip()
    match = re.search(r'([\d.]+)\s*(MiB|GiB|KiB|MB|GB|KB)', size_str, re.IGNORECASE)
    if not match:
        return 0
    
    value = float(match.group(1))
    unit = match.group(2).upper()
    
    if 'GIB' in unit or 'GB' in unit:
        return value * 1024
    elif 'KIB' in unit or 'KB' in unit:
        return value / 1024
    else:  # MiB or MB
        return value


def parse_list_rating_style(style: str) -> tuple[float, int | None]:
    """解析列表页 .ir 样式，返回 0.5 精度评分和评分人数提示。"""
    match = re.search(
        r'background-position:\s*(-?\d+)px\s+(-?\d+)px(?:;opacity:([\d.]+))?',
        style,
    )
    if not match:
        return 0.0, None

    pos_x = int(match.group(1))
    pos_y = int(match.group(2))
    opacity_text = match.group(3)

    column = (pos_x + 80) // 16
    half_steps = column * 2 if pos_y == -1 else column * 2 - 1
    rounded_rating = max(0, min(10, half_steps)) / 2

    if opacity_text is None:
        return rounded_rating, None

    opacity = float(opacity_text)
    if opacity >= 1:
        return rounded_rating, 10

    rating_count_hint = max(0, round(opacity * 15 - 5))
    return rounded_rating, rating_count_hint


def shorten_title(title: str, max_length: int = 42) -> str:
    """简短化标题，便于日志输出。"""
    clean_title = ' '.join(title.split())
    if len(clean_title) <= max_length:
        return clean_title
    return clean_title[: max_length - 3] + '...'


def print_skip_details(header: str, details: list[str]) -> None:
    """打印初筛跳过明细。"""
    if not details:
        print(f'{header}无')
        return

    for detail in details:
        print(f'{header}{detail}')


def gb_to_mib(size_gb: float) -> float:
    """把 GB 转换为 MiB。"""
    return size_gb * 1024


def extract_gallery_info_from_list(page, source_list_url: str) -> list[dict[str, object]]:
    """从列表页提取画廊基本信息"""
    galleries = []
    
    # 网格布局（Thumbnail 模式）
    items = page.locator('.itg.gld .gl1t')
    count = items.count()
    use_grid = count > 0
    
    if not use_grid:
        # 表格布局
        items = page.locator('table.itg tbody tr')
        count = items.count()
    
    for i in range(count):
        try:
            item = items.nth(i)
            rating_elem = item.locator('.ir').first
            rating_style = rating_elem.get_attribute('style') if rating_elem.count() > 0 else ''
            list_rating, list_rating_votes_hint = parse_list_rating_style(rating_style or '')
            
            if use_grid:
                # 网格布局
                title_link = item.locator('a[href*="/g/"]').first
                href = title_link.get_attribute('href')
                if not href:
                    continue
                
                # 解析 gid 和 token
                match = re.search(r'/g/(\d+)/([a-f0-9]+)', href)
                if not match:
                    continue
                
                gid = match.group(1)
                token = match.group(2)
                
                title = item.locator('.gl4t.glink').first.inner_text().strip()
                category_elem = item.locator('.gl5t .cs').first
                category = category_elem.inner_text().strip() if category_elem.count() > 0 else ''
                
                date_elem = item.locator('.gl5t div[id^="posted_"]').first
                pub_date = date_elem.inner_text().strip() if date_elem.count() > 0 else ''
                
                pages_elem = item.locator('.gl5t .ir + div').first
                pages_text = pages_elem.inner_text().strip() if pages_elem.count() > 0 else '0'
                pages_match = re.search(r'(\d+)', pages_text)
                pages = int(pages_match.group(1)) if pages_match else 0
                
                uploader = ''  # 网格布局通常没有上传者信息
                
            else:
                # 表格布局（跳过表头）
                if i == 0:
                    continue
                
                title_link = item.locator('.gl3c.glname a').first
                href = title_link.get_attribute('href')
                if not href:
                    continue
                
                match = re.search(r'/g/(\d+)/([a-f0-9]+)', href)
                if not match:
                    continue
                
                gid = match.group(1)
                token = match.group(2)
                
                title = title_link.locator('.glink').first.inner_text().strip()
                category_elem = item.locator('.gl1c .cn').first
                category = category_elem.inner_text().strip() if category_elem.count() > 0 else ''
                
                date_elem = item.locator('.gl2c div[id^="posted_"]').first
                pub_date = date_elem.inner_text().strip() if date_elem.count() > 0 else ''
                
                pages_elem = item.locator('.gl4c.glhide div:last-child').first
                pages_text = pages_elem.inner_text().strip() if pages_elem.count() > 0 else '0'
                pages_match = re.search(r'(\d+)', pages_text)
                pages = int(pages_match.group(1)) if pages_match else 0
                
                uploader_elem = item.locator('.gl4c.glhide a').first
                uploader = uploader_elem.inner_text().strip() if uploader_elem.count() > 0 else ''
            
            # 检测 torrent 状态
            has_torrent = True
            torrent_elem = item.locator('.gldown').first
            if torrent_elem.count() > 0:
                torrent_img = torrent_elem.locator('img').first
                if torrent_img.count() > 0:
                    title_attr = torrent_img.get_attribute('title')
                    if title_attr and 'No torrents available' in title_attr:
                        has_torrent = False
            
            # 只保留没有 torrent 的
            if has_torrent:
                continue
            
            galleries.append({
                'gid': gid,
                'token': token,
                'title': title,
                'url': f'https://e-hentai.org/g/{gid}/{token}/',
                'source_list_url': source_list_url,
                'category': category,
                'uploader': uploader,
                'pub_date': pub_date,
                'pages': pages,
                'list_rating': list_rating,
                'list_rating_votes_hint': list_rating_votes_hint,
                'list_rating_style': rating_style or '',
            })
            
        except Exception as e:
            print(f"解析第 {i} 个条目失败：{e}", file=sys.stderr)
            continue
    
    return galleries


def get_gallery_detail_info(page, gid: str, token: str) -> GalleryInfo | None:
    """获取画廊详情信息（包括 Rating、文件大小等）"""
    url = f'https://e-hentai.org/g/{gid}/{token}/'
    
    try:
        page.goto(url, wait_until='domcontentloaded')
        page.wait_for_timeout(1500)
        
        content = page.content()
        
        # 提取标题
        title_match = re.search(r'<h1 id="gn">([^<]+)</h1>', content)
        title = title_match.group(1).strip() if title_match else ''
        
        # 提取 Rating
        rating_match = re.search(r'var average_rating\s*=\s*([\d.]+)', content)
        rating = float(rating_match.group(1)) if rating_match else 0
        
        # 提取评分人数
        rating_count_match = re.search(r'id="rating_count">(\d+)</span>', content)
        rating_count = int(rating_count_match.group(1)) if rating_count_match else 0
        
        # 提取收藏次数
        fav_match = re.search(r'id="favcount">(\d+(?:,\d+)*)\s*times', content)
        favorited_count = int(fav_match.group(1).replace(',', '')) if fav_match else 0
        
        # 提取文件大小
        size_match = re.search(r'File Size:</td>\s*<td[^>]*>([^<]+)</td>', content)
        file_size_mb = parse_size_to_mb(size_match.group(1)) if size_match else 0
        
        # 提取页数
        pages_match = re.search(r'Length:</td>\s*<td[^>]*>(\d+)\s*pages', content)
        pages = int(pages_match.group(1)) if pages_match else 0
        
        # 提取分类
        category_match = re.search(r'<div class="cs ([^"]+)">([^<]+)</div>', content)
        category = category_match.group(2).strip() if category_match else ''
        
        # 提取上传者
        uploader_match = re.search(r'<a href="https://e-hentai.org/uploader/[^"]+">([^<]+)</a>', content)
        uploader = uploader_match.group(1).strip() if uploader_match else ''
        
        # 提取发布日期
        date_match = re.search(r'Posted:</td>\s*<td[^>]*>([^<]+)</td>', content)
        pub_date = date_match.group(1).strip() if date_match else ''
        
        return GalleryInfo(
            gid=gid,
            token=token,
            title=title,
            url=url,
            source_list_url='',
            category=category,
            uploader=uploader,
            pub_date=pub_date,
            pages=pages,
            file_size_mb=file_size_mb,
            rating=rating,
            rating_count=rating_count,
            favorited_count=favorited_count,
        )
        
    except Exception as e:
        print(f"获取 {gid} 详情失败：{e}", file=sys.stderr)
        return None


def get_archiver_info(page, gid: str, token: str, gallery: GalleryInfo) -> bool:
    """获取 archiver 页面的 GP 成本信息（仅 Original Archive）"""
    url = f'https://e-hentai.org/archiver.php?gid={gid}&token={token}'
    
    try:
        page.goto(url, wait_until='domcontentloaded')
        page.wait_for_timeout(1500)
        
        content = page.content()
        
        original_block_match = re.search(
            r'Download Cost:\s*&nbsp;\s*<strong>(Free!|\d+(?:,\d+)?\s*GP)</strong>.*?'
            r'<input type="hidden" name="dltype" value="org">.*?'
            r'Estimated Size:\s*&nbsp;\s*<strong>([^<]+)</strong>',
            content,
            re.DOTALL,
        )

        if not original_block_match:
            return False

        cost_text = original_block_match.group(1).strip()
        size_text = original_block_match.group(2).strip()

        if cost_text == 'Free!':
            gallery.cost_gp = 0
        else:
            cost_match = re.search(r'(\d+(?:,\d+)*)\s*GP', cost_text)
            if not cost_match:
                return False
            gallery.cost_gp = float(cost_match.group(1).replace(',', ''))

        gallery.size_mb = parse_size_to_mb(size_text)
        return True
        
    except Exception as e:
        print(f"获取 {gid} archiver 信息失败：{e}", file=sys.stderr)
        return False


def calculate_value_score(gallery: GalleryInfo, available_gp: float) -> float:
    """
    计算综合价值评分
    
    评分因素：
    1. Rating (权重 30%) - 越高越好
    2. 收藏次数 (权重 20%) - 越多越好
    3. GP/页 成本 (权重 25%) - 越低越好
    4. GP/MB 成本 (权重 15%) - 越低越好
    5. 页数充足度 (权重 10%) - 适中为好 (100-300 页最佳)
    
    Returns: 0-100 的评分
    """
    score = 0
    
    # 1. Rating 评分 (0-30 分)
    # 4.0+ 得满分，2.0 以下得 0 分
    rating_score = min(30, max(0, (gallery.rating / 4.0) * 30))
    score += rating_score
    
    # 2. 收藏次数评分 (0-20 分)
    # 100+ 收藏得满分，线性插值
    fav_score = min(20, (gallery.favorited_count / 100) * 20)
    score += fav_score
    
    # 3. GP/页 成本评分 (0-25 分)
    # 假设每页 10GP 以内是可以接受的
    gallery.gp_per_page = gallery.cost_gp / max(1, gallery.pages)
    gp_per_page_score = max(0, 25 - (gallery.gp_per_page * 2.5))
    score += gp_per_page_score
    
    # 4. GP/MB 成本评分 (0-15 分)
    # 假设每 MB 50GP 以内是可以接受的
    gallery.gp_per_mb = gallery.cost_gp / max(1, gallery.size_mb)
    gp_per_mb_score = max(0, 15 - (gallery.gp_per_mb * 0.3))
    score += gp_per_mb_score
    
    # 5. 页数充足度评分 (0-10 分)
    # 100-300 页最佳
    if 100 <= gallery.pages <= 300:
        pages_score = 10
    elif gallery.pages < 100:
        pages_score = (gallery.pages / 100) * 10
    else:
        pages_score = max(0, 10 - (gallery.pages - 300) / 100)
    score += pages_score
    
    gallery.value_score = score
    return score


def filter_galleries(galleries: list[GalleryInfo],
                     available_gp: float,
                     min_rating: float = 3.0,
                     min_pages: int = 50,
                     max_size_mb: float = 1024,
top_n: int = 10) -> list[GalleryInfo]:
    """
    筛选高价值画廊

    Args:
        galleries: 画廊列表
        available_gp: 可用 GP
        min_rating: 最低 Rating
        min_pages: 最低页数
        max_size_mb: 最大文件大小 (MiB)
        top_n: 返回前 N 个

    Returns: 排序后的画廊列表
    """
    # 过滤（GP 成本不超过可用 GP）
    filtered = [
        g for g in galleries
        if g.rating >= min_rating
        and g.pages >= min_pages
        and g.file_size_mb <= max_size_mb
        and g.cost_gp <= available_gp
        and g.cost_gp >= 0
    ]
    
    # 计算评分并排序
    for g in filtered:
        calculate_value_score(g, available_gp)
    
    # 按价值评分降序排序
    filtered.sort(key=lambda x: x.value_score, reverse=True)
    
    return filtered[:top_n]


def print_galleries(galleries: list[GalleryInfo], available_gp: float):
    """打印画廊信息"""
    if not galleries:
        print("没有找到符合条件的画廊")
        return
    
    print("\n" + "=" * 120)
    print(f"可用 GP: {available_gp:,.0f} | 共 {len(galleries)} 个画廊")
    print("=" * 120)
    
    for i, g in enumerate(galleries, 1):
        print(f"\n[{i:2d}] {g.title}")
        print(f"     URL: {g.url}")
        print(f"     入口列表：{g.source_list_url}")
        print(f"     分类：{g.category} | 上传者：{g.uploader}")
        print(f"     页数：{g.pages} | 大小：{g.size_mb:.2f} MiB")
        print(f"     列表页 Rating: {g.list_rating:.1f} | 列表页评分人数强度：{g.list_rating_votes_hint}")
        print(f"     Rating: {g.rating:.2f} ({g.rating_count}人评分) | 收藏：{g.favorited_count}次")
        print(f"     GP 成本：{g.cost_gp:,.0f} GP")
        print(f"     GP/页：{g.gp_per_page:.2f} | GP/MB: {g.gp_per_mb:.2f}")
        print(f"     【综合评分：{g.value_score:.1f}/100】")
        print(f"     下载链接：{g.get_archiver_url()}")
    
    print("\n" + "=" * 120)


def save_results(galleries: list[GalleryInfo], available_gp: float, output_file: str, max_size_gb: float):
    """保存结果到文件"""
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"可用 GP: {available_gp:,.0f}\n")
        f.write(f"筛选出 {len(galleries)} 个高价值画廊\n\n")
        f.write(f"最大大小限制: {max_size_gb:.2f} GB\n\n")
        f.write("=" * 120 + "\n\n")
        
        for i, g in enumerate(galleries, 1):
            f.write(f"[{i:2d}] {g.title}\n")
            f.write(f"     URL: {g.url}\n")
            f.write(f"     入口列表：{g.source_list_url}\n")
            f.write(f"     分类：{g.category} | 上传者：{g.uploader}\n")
            f.write(f"     页数：{g.pages} | 大小：{g.size_mb:.2f} MiB\n")
            f.write(f"     列表页 Rating: {g.list_rating:.1f} | 列表页评分人数强度：{g.list_rating_votes_hint}\n")
            f.write(f"     Rating: {g.rating:.2f} ({g.rating_count}人评分) | 收藏：{g.favorited_count}次\n")
            f.write(f"     GP 成本：{g.cost_gp:,.0f} GP\n")
            f.write(f"     GP/页：{g.gp_per_page:.2f} | GP/MB: {g.gp_per_mb:.2f}\n")
            f.write(f"     【综合评分：{g.value_score:.1f}/100】\n")
            f.write(f"     下载链接：{g.get_archiver_url()}\n\n")



def main():
    import argparse
    from importlib import import_module

    sync_playwright = import_module('playwright.sync_api').sync_playwright
    
    parser = argparse.ArgumentParser(
        description='e-hentai 画廊筛选器 - 扫描指定页数并输出全量结果',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  基本使用（扫描 2 页，输出所有结果）:
    %(prog)s
  
  扫描更多页数:
    %(prog)s --pages 10

  提供多个入口列表:
    %(prog)s --url https://e-hentai.org/?f_cats=1019 --url https://e-hentai.org/?f_cats=767
  
  降低 Rating 门槛:
    %(prog)s --min-rating 2.0

  限制最大文件大小为 1.5GB:
    %(prog)s --max-size-gb 1.5
 
  显示浏览器窗口:
    %(prog)s --show-browser

详细说明请查看脚本顶部的文档字符串。
        """
    )
    parser.add_argument('--cookie-file', '-f', default='eht-netscape.cookie',
                        help='Netscape 格式的 Cookie 文件路径 (默认：eht-netscape.cookie)')
    parser.add_argument('--proxy', '-s', default='http://127.0.0.1:10809',
                        help='代理服务器地址 (默认：http://127.0.0.1:10809)')
    parser.add_argument('--url', '-u', action='append', default=None,
                        help='目标列表页 URL，可提供多次；不提供时默认使用 https://e-hentai.org/?f_cats=1019')

    parser.add_argument('--min-rating', type=float, default=3.0,
                        help='最低 Rating 要求 (默认：3.0)')
    parser.add_argument('--min-pages', type=int, default=40,
                        help='最低页数要求 (默认：40)')
    parser.add_argument('--max-size-gb', type=float, default=1.0,
                        help='最大原始文件大小，单位 GB，超过则跳过 (默认：1.0)')
    parser.add_argument('--pages', '-p', type=int, default=2,
                        help='抓取的列表页数 (默认：2 页)')
    parser.add_argument('--output', '-o', default='ehentai_recommendations.txt',
                        help='输出文件名 (默认：ehentai_recommendations.txt)')
    parser.add_argument('--show-browser', action='store_true',
                        help='显示浏览器窗口（默认无头模式）')
    
    args = parser.parse_args()
    
    source_urls = args.url or ['https://e-hentai.org/?f_cats=1019']

    print("=" * 80)
    print("e-hentai 画廊筛选器")
    print("=" * 80)
    print(f"\n加载 Cookie: {args.cookie_file}")
    print(f"目标 URL 数量: {len(source_urls)}")
    for index, source_url in enumerate(source_urls, 1):
        print(f"  [{index}] {source_url}")
    print(f"参数设置:")
    print(f"  - 抓取页数：{args.pages} 页（默认 2 页）")
    print(f"  - 最低 Rating: {args.min_rating}")
    print(f"  - 最低页数：{args.min_pages}")
    print(f"  - 最大大小：{args.max_size_gb} GB")
    print(f"  - 输出文件：{args.output}")
    print(f"  - 显示浏览器：{'是' if args.show_browser else '否（无头模式）'}")
    print()
    cookies = parse_netscape_cookie_file(args.cookie_file)
    print(f"加载了 {len(cookies)} 个 cookie\n")
    max_size_mb = gb_to_mib(args.max_size_gb)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.show_browser, proxy={'server': args.proxy})
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080}
        )
        context.add_cookies(cookies)
        page = context.new_page()
        
        # 1. 获取可用 GP
        print("获取可用 GP...")
        page.goto('https://e-hentai.org/exchange.php?t=gp', wait_until='domcontentloaded')
        page.wait_for_timeout(2000)
        
        content = page.content()
        gp_match = re.search(r'Available:\s*([\d,]+)\s*kGP', content)
        available_gp = int(gp_match.group(1).replace(',', '')) * 1000 if gp_match else 0
        print(f"可用 GP: {available_gp:,}\n")
        
        # 2. 访问列表页提取画廊（支持多页）
        print(f"计划每个入口抓取 {args.pages} 页\n")
        
        all_galleries_basic = []

        for source_index, source_url in enumerate(source_urls, 1):
            print(f"访问入口列表 [{source_index}/{len(source_urls)}]: {source_url}")
            page.goto(source_url, wait_until='domcontentloaded')
            page.wait_for_timeout(3000)

            for page_num in range(args.pages):
                if page_num > 0:
                    next_page = page.locator('#unext')
                    if next_page.count() > 0:
                        print(f"  翻到第 {page_num + 1} 页...")
                        next_page.click()
                        page.wait_for_load_state('domcontentloaded')
                        page.wait_for_timeout(2000)
                    else:
                        print(f"  已是最后一页")
                        break

                print(f"  处理第 {page_num + 1} 页...")
                galleries_basic = extract_gallery_info_from_list(page, source_url)
                print(f"    找到 {len(galleries_basic)} 个无 torrent 的画廊")
                all_galleries_basic.extend(galleries_basic)
        
        print(f"\n共找到 {len(all_galleries_basic)} 个无 torrent 的画廊\n")
        
        if not all_galleries_basic:
            print("没有找到画廊")
            browser.close()
            return
        
        # 3. 先用列表页 rating 做初筛，减少详情页访问
        prefiltered_galleries_basic = []
        skipped_by_list_rating = 0
        skipped_by_list_pages = 0
        skipped_rating_details = []
        skipped_pages_details = []

        for basic in all_galleries_basic:
            list_rating = float(basic.get('list_rating', 0.0))
            pages = int(basic.get('pages', 0))
            short_title = shorten_title(str(basic.get('title', '')))

            if list_rating < args.min_rating:
                skipped_by_list_rating += 1
                skipped_rating_details.append(
                    f'{short_title} | 列表页星级 {list_rating:.1f} < 要求 {args.min_rating:.1f}'
                )
                continue

            if pages < args.min_pages:
                skipped_by_list_pages += 1
                skipped_pages_details.append(
                    f'{short_title} | 页数 {pages} < 要求 {args.min_pages}'
                )
                continue

            prefiltered_galleries_basic.append(basic)

        print('列表页初筛结果:')
        print(f'  - 因列表页 Rating 跳过：{skipped_by_list_rating} 个')
        print_skip_details('    ', skipped_rating_details)
        print(f'  - 因页数不够跳过：{skipped_by_list_pages} 个')
        print_skip_details('    ', skipped_pages_details)
        print(f'  - 需要进入详情页：{len(prefiltered_galleries_basic)} / {len(all_galleries_basic)} 个\n')

        # 4. 获取通过初筛画廊的详细信息
        galleries = []
        skipped_by_file_size = 0
        skipped_file_size_details = []
        
        for i, basic in enumerate(prefiltered_galleries_basic, 1):
            print(f"[{i}/{len(prefiltered_galleries_basic)}] 处理：{basic['title'][:50]}...")
            print(
                f"  - 列表页预筛: Rating={float(basic.get('list_rating', 0.0)):.1f}, "
                f"VotesHint={basic.get('list_rating_votes_hint')}, Pages={basic['pages']}"
            )
            
            # 获取详情信息
            gallery = get_gallery_detail_info(page, basic['gid'], basic['token'])
            if not gallery:
                print(f"  └─ 获取详情失败，跳过")
                continue

            gallery.list_rating = float(basic.get('list_rating', 0.0))
            gallery.list_rating_votes_hint = basic.get('list_rating_votes_hint')
            gallery.list_rating_style = str(basic.get('list_rating_style', ''))
            gallery.source_list_url = str(basic.get('source_list_url', ''))
            
            # 获取 archiver 信息
            if not get_archiver_info(page, basic['gid'], basic['token'], gallery):
                print(f"  └─ 获取 GP 成本失败，跳过")
                continue
            
            # 初步筛选
            if gallery.cost_gp < 0:
                print(f"  - GP 成本无效，跳过")
                continue
            
            if gallery.rating < args.min_rating:
                print(f"  - Rating 过低 ({gallery.rating:.2f} < {args.min_rating})，跳过")
                continue

            if gallery.file_size_mb > max_size_mb:
                skipped_by_file_size += 1
                skipped_file_size_details.append(
                    f'{shorten_title(gallery.title)} | 大小 {gallery.file_size_mb:.2f} MiB > 要求 {max_size_mb:.2f} MiB'
                )
                print(f"  - 文件过大 ({gallery.file_size_mb:.2f} MiB > {max_size_mb:.2f} MiB)，跳过")
                continue
            
            galleries.append(gallery)
            print(
                f"  - ✅ ListRating={gallery.list_rating:.1f}, Rating={gallery.rating:.2f}, "
                f"GP={gallery.cost_gp:,.0f}, Pages={gallery.pages}"
            )

        print(f"\n详情页补充筛选结果:")
        print(f'  - 因文件过大跳过：{skipped_by_file_size} 个')
        print_skip_details('    ', skipped_file_size_details)
        
        # 5. 计算综合评分并排序
        print("\n计算综合评分...")
        for g in galleries:
            calculate_value_score(g, available_gp)
        
        # 按评分排序
        galleries.sort(key=lambda x: x.value_score, reverse=True)
        
        # 6. 输出所有结果
        print_galleries(galleries, available_gp)
        save_results(galleries, available_gp, args.output, args.max_size_gb)
        print(f"\n结果已保存到：{args.output} (共 {len(galleries)} 个画廊)")
        
        browser.close()


if __name__ == '__main__':
    main()
