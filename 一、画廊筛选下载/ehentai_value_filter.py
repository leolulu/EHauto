#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import html
import re
import sys
from dataclasses import asdict, dataclass, field
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

    # 详情页标签（规范化为 "namespace:tag"；tag 内空格保留）
    tags: list[str] = field(default_factory=list)
    
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


def _strip_html_tags(text: str) -> str:
    """移除 HTML 标签并解码实体。"""
    if not text:
        return ''
    without_tags = re.sub(r'<[^>]+>', '', text)
    return html.unescape(without_tags)


def _normalize_space(text: str) -> str:
    return ' '.join(text.strip().split())


def extract_tags_from_detail_html(content: str) -> list[str]:
    """从详情页 HTML 提取 tag 列表。

    返回值为规范化后的 tag："namespace:tag"（小写；tag 内空格保留）。
    
    说明：E-Hentai 详情页的 tag 链接通常形如 <a id="td_male:males_only">...</a>
    - id 会携带 namespace:slug（slug 常用下划线表示空格）
    - 可见文本更贴近真实 tag（例如 "males only"）
    """
    if not content:
        return []

    tags: list[str] = []
    seen: set[str] = set()

    for raw_id, inner_html in re.findall(r'<a id="td_([^"]+)"[^>]*>(.*?)</a>', content, re.DOTALL):
        raw_id = (raw_id or '').strip().lower()
        if not raw_id or ':' not in raw_id:
            continue

        namespace, slug = raw_id.split(':', 1)
        visible_text = _normalize_space(_strip_html_tags(inner_html))
        tag_value = visible_text or _normalize_space(slug.replace('_', ' '))
        if not tag_value:
            continue

        normalized = f'{namespace}:{tag_value}'.strip().lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        tags.append(normalized)

    return tags


def _tag_variants(tag: str) -> set[str]:
    """为匹配生成一些等价写法（空格/下划线/加号）。"""
    base = _normalize_space(tag).lower()
    if not base:
        return set()
    return {
        base,
        base.replace(' ', '_'),
        base.replace(' ', '+'),
    }


def match_excluded_tags(excluded: list[str], gallery_tags: list[str]) -> list[str]:
    """返回命中的排除 tag（按 excluded 顺序）。

    规则：
    - excluded 包含 ':' 时：匹配完整 "namespace:tag"（允许空格/下划线/加号写法差异）
    - excluded 不包含 ':' 时：匹配任意 tag 的 value 部分（namespace 后的部分）
    """
    if not excluded or not gallery_tags:
        return []

    gallery_full_variants: set[str] = set()
    gallery_value_variants: set[str] = set()
    for t in gallery_tags:
        gallery_full_variants |= _tag_variants(t)
        if ':' in t:
            _ns, value = t.split(':', 1)
            gallery_value_variants |= _tag_variants(value)

    hits: list[str] = []
    for raw in excluded:
        token = _normalize_space(str(raw)).lower()
        if not token:
            continue
        if ':' in token:
            if _tag_variants(token) & gallery_full_variants:
                hits.append(token)
        else:
            if _tag_variants(token) & gallery_value_variants:
                hits.append(token)
    return hits


def format_tags_for_display(tags: list[str], limit: int = 12) -> str:
    """把 tags 格式化为一行可读文本（截断）。"""
    if not tags:
        return ''
    shown = tags[:limit]
    suffix = f' ... (+{len(tags) - limit})' if len(tags) > limit else ''
    return ', '.join(shown) + suffix


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

        # 提取 tags（详情页右侧 taglist 区域）
        tags = extract_tags_from_detail_html(content)
        
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
            tags=tags,
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
        if g.tags:
            print(f"     Tags: {format_tags_for_display(g.tags)}")
        print(f"     GP 成本：{g.cost_gp:,.0f} GP")
        print(f"     GP/页：{g.gp_per_page:.2f} | GP/MB: {g.gp_per_mb:.2f}")
        print(f"     【综合评分：{g.value_score:.1f}/100】")
        print(f"     下载链接：{g.get_archiver_url()}")
    
    print("\n" + "=" * 120)


def save_results(
    galleries: list[GalleryInfo],
    available_gp: float,
    output_file: str,
    max_size_gb: float,
    exclude_tags: list[str] | None = None,
):
    """保存结果到文件"""
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"可用 GP: {available_gp:,.0f}\n")
        f.write(f"筛选出 {len(galleries)} 个高价值画廊\n\n")
        f.write(f"最大大小限制: {max_size_gb:.2f} GB\n\n")
        if exclude_tags:
            f.write(f"排除 tag: {', '.join(exclude_tags)}\n\n")
        f.write("=" * 120 + "\n\n")
        
        for i, g in enumerate(galleries, 1):
            f.write(f"[{i:2d}] {g.title}\n")
            f.write(f"     URL: {g.url}\n")
            f.write(f"     入口列表：{g.source_list_url}\n")
            f.write(f"     分类：{g.category} | 上传者：{g.uploader}\n")
            f.write(f"     页数：{g.pages} | 大小：{g.size_mb:.2f} MiB\n")
            f.write(f"     列表页 Rating: {g.list_rating:.1f} | 列表页评分人数强度：{g.list_rating_votes_hint}\n")
            f.write(f"     Rating: {g.rating:.2f} ({g.rating_count}人评分) | 收藏：{g.favorited_count}次\n")
            if g.tags:
                f.write(f"     Tags: {format_tags_for_display(g.tags, limit=24)}\n")
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

    parser.add_argument(
        '--exclude-tag',
        action='append',
        default=None,
        help=(
            '排除包含指定 tag 的画廊（可多次指定）。支持 "namespace:tag"（推荐）或仅 "tag"。\n'
            '示例：--exclude-tag "male:males only" --exclude-tag "yaoi"'
        ),
    )
    
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
    exclude_tags = args.exclude_tag or []
    if exclude_tags:
        print(f"  - 排除 tag: {', '.join(exclude_tags)}")
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
        skipped_by_exclude_tag = 0
        skipped_exclude_tag_details = []
        
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

            # tag 排除筛选（尽量在访问 archiver 前拦截）
            if exclude_tags and gallery.tags:
                hits = match_excluded_tags(exclude_tags, gallery.tags)
                if hits:
                    skipped_by_exclude_tag += 1
                    short_title = shorten_title(gallery.title)
                    skipped_exclude_tag_details.append(
                        f'{short_title} | 命中排除 tag: {", ".join(hits[:5])}'
                    )
                    print(f"  - 命中排除 tag ({', '.join(hits[:5])})，跳过")
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
        if exclude_tags:
            print(f'  - 因命中排除 tag 跳过：{skipped_by_exclude_tag} 个')
            print_skip_details('    ', skipped_exclude_tag_details)
        
        # 5. 计算综合评分并排序
        print("\n计算综合评分...")
        for g in galleries:
            calculate_value_score(g, available_gp)
        
        # 按评分排序
        galleries.sort(key=lambda x: x.value_score, reverse=True)
        
        # 6. 输出所有结果
        print_galleries(galleries, available_gp)
        save_results(galleries, available_gp, args.output, args.max_size_gb, exclude_tags=exclude_tags)
        print(f"\n结果已保存到：{args.output} (共 {len(galleries)} 个画廊)")
        
        browser.close()


if __name__ == '__main__':
    main()
