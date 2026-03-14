#!/usr/bin/env python3
"""
e-hentai 种子上传工具

功能：
  1. 使用 Cookie 登录 e-hentai
  2. 访问种子上传页面，获取官方 Tracker 信息
  3. 可选：自动上传种子文件

依赖：
    uv sync

使用示例：
    # 获取 tracker 信息
    uv run python ehentai_uploader.py --cookie "你的 Cookie" https://e-hentai.org/g/3828071/76966bded7/
    
    # 上传种子
    uv run python ehentai_uploader.py --cookie "你的 Cookie" --upload "种子.torrent" https://e-hentai.org/g/3828071/76966bded7/
"""

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import bencodepy
import requests
from bs4 import BeautifulSoup


def sanitize_title(title: str) -> str:
    sanitized = re.sub(r'[\\/:*?"<>|]', '_', title)
    sanitized = sanitized.rstrip(' .')
    return sanitized or 'untitled'


def build_personalized_torrent_path(title: str, output_dir: str) -> Path:
    return Path(output_dir) / f"{sanitize_title(title)}_personalized.torrent"


def is_valid_torrent_bytes(data: bytes) -> bool:
    try:
        decoded = bencodepy.decode(data)
    except Exception:
        return False

    if not isinstance(decoded, dict):
        return False

    return b'info' in decoded and b'announce' in decoded


class EHentaiUploader:
    def __init__(self, cookie: str, proxy: str | None = None):
        """
        初始化上传器
        
        Args:
            cookie: e-hentai 的 Cookie 字符串（包含 ipb_member_id, ipb_pass_hash, sk 等）
            proxy: HTTP 代理地址，例如 "http://127.0.0.1:10809"
        """
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://e-hentai.org/',
        })
        self.session.cookies.update(self._parse_cookie(cookie))
        
        # 配置代理
        if proxy:
            self.session.proxies.update({
                'http': proxy,
                'https': proxy,
            })
            print(f"使用代理：{proxy}")
        
        self.base_url = "https://e-hentai.org"
    
    def _parse_cookie(self, cookie_str: str) -> dict[str, str]:
        """解析 Cookie 字符串为字典"""
        cookies = {}
        for item in cookie_str.split(';'):
            if '=' in item:
                key, value = item.split('=', 1)
                cookies[key.strip()] = value.strip()
        return cookies
    
    def get_gallery_info(self, gallery_url: str) -> tuple[str, str, str]:
        """
        获取画廊信息
        
        Returns:
            (gid, token, title)
        """
        parsed = urlparse(gallery_url)
        
        # 从 URL 提取 gid 和 token
        if '/g/' in gallery_url:
            parts = gallery_url.strip('/').split('/')
            gid = parts[-2]
            token = parts[-1]
        elif 'gid=' in gallery_url:
            params = parse_qs(parsed.query)
            gid = params.get('gid', [''])[0]
            token = params.get('t', [''])[0]
        else:
            raise ValueError(f"无效的画廊 URL: {gallery_url}")
        
        # 获取画廊标题
        response = self.session.get(f"{self.base_url}/g/{gid}/{token}/", timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 提取标题
        title_tag = soup.find('h1', id='gn')
        title = title_tag.text.strip() if title_tag else f"Gallery {gid}"
        
        return gid, token, title
    
    def get_tracker_info(self, gallery_url: str) -> dict[str, str | int]:
        """
        获取种子上传页面的 Tracker 信息
        
        Returns:
            包含 tracker 信息的字典
        """
        gid, token, title = self.get_gallery_info(gallery_url)
        
        print(f"\n画廊：{title}")
        print(f"GID: {gid}, Token: {token}")
        
        # 访问种子页面
        torrent_url = f"{self.base_url}/gallerytorrents.php?gid={gid}&t={token}"
        print(f"访问：{torrent_url}")
        
        response = self.session.get(torrent_url, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        text = soup.get_text()
        
        result = {
            'gid': gid,
            'token': token,
            'title': title,
            'tracker': f"http://ehtracker.org/{gid}/announce",  # 根据 GID 生成专属 tracker
            'max_size': 10 * 1024 * 1024,  # 10MB (截图显示)
            'instructions': '',
        }
        
        # 从页面提取实际 tracker URL（优先使用页面上的）
        # 查找 ehtracker.org/{gid}/announce 格式
        tracker_match = re.search(r'(https?://ehtracker\.org/[^/\s<>"\']+/announce)', text)
        if tracker_match:
            result['tracker'] = tracker_match.group(1)
            print(f"\n从页面提取 Tracker: {result['tracker']}")
        else:
            # 备用：根据 GID 生成
            result['tracker'] = f"http://ehtracker.org/{gid}/announce"
            print(f"\n使用 GID 生成 Tracker: {result['tracker']}")
        
        # 提取大小限制
        size_match = re.search(r'(\d+)\s*(MB|KB)', text, re.IGNORECASE)
        if size_match:
            size = int(size_match.group(1))
            unit = size_match.group(2).upper()
            if unit == 'KB':
                result['max_size'] = size * 1024
            else:
                result['max_size'] = size * 1024 * 1024
        
        return result
    
    def upload_torrent(self, gallery_url: str, torrent_path: str, comment: str = "", download_personalized: bool = True, output_dir: str = "generated_torrents") -> tuple[bool, bool, str | None]:
        """
        上传种子文件到 e-hentai
        
        Args:
            gallery_url: 画廊 URL
            torrent_path: 种子文件路径
            comment: 种子评论
            download_personalized: 上传成功后是否下载专属种子
            output_dir: 专属种子保存目录
        
        Returns:
            (success, is_replaced, replacement_url) - 上传是否成功，画廊是否被替换，新画廊 URL（如有）
        """
        gid, token, title = self.get_gallery_info(gallery_url)
        
        print(f"\n上传种子到：{title}")
        print(f"种子文件：{torrent_path}")
        
        # 读取种子文件
        with open(torrent_path, 'rb') as f:
            torrent_data = f.read()
        
        # 检查文件大小（10MB 限制）
        max_size = 10 * 1024 * 1024
        if len(torrent_data) > max_size:
            print("❌ 种子文件超过 10MB 限制")
            return False, False, None
        
        print(f"文件大小：{len(torrent_data) / 1024:.1f} KB")
        
        # 构建上传表单
        # 字段名必须是 torrentfile
        files = {
            'torrentfile': (Path(torrent_path).name, torrent_data, 'application/x-bittorrent'),
        }
        
        # 包含 MAX_FILE_SIZE 隐藏字段
        data = {
            'MAX_FILE_SIZE': str(max_size),
        }
        
        if comment:
            data['comment'] = comment
        
        # 上传 URL（注意是 repo.e-hentai.org）
        upload_url = f"https://repo.e-hentai.org/torrent_post.php?gid={gid}&t={token}"
        print(f"上传到：{upload_url}")
        
        # 设置 Referer
        headers = {
            'Referer': f'https://e-hentai.org/gallerytorrents.php?gid={gid}&t={token}',
            'Origin': 'https://e-hentai.org',
        }
        
        response = self.session.post(upload_url, files=files, data=data, headers=headers, timeout=60)
        response.raise_for_status()
        
        # 检查上传结果
        if 'success' in response.text.lower() or 'uploaded' in response.text.lower() or 'complete' in response.text.lower():
            print("✅ 上传成功!")
            
            # 下载专属种子
            if download_personalized:
                downloaded_path = self._download_personalized_torrent(gid, token, title, output_dir)
                if not downloaded_path:
                    print("❌ 上传成功，但下载专属种子失败")
                    return False, False, None
            
            return True, False, None
        else:
            # 尝试提取错误信息
            soup = BeautifulSoup(response.text, 'html.parser')
            error = soup.find('div', class_='error')
            if error is None:
                for paragraph in soup.find_all('p'):
                    style_attr = str(paragraph.get('style', ''))
                    if 'color:red' in style_attr.replace(' ', '').lower():
                        error = paragraph
                        break
            if error is None:
                error = soup.find('font', color='red')
            
            error_message = ""
            if error:
                error_message = error.get_text().strip()
                print(f"❌ 上传失败：{error_message}")
            else:
                print("❌ 上传失败（未知原因）")
                error_message = "Unknown upload error"
                # 保存响应以便调试
                with open('upload_response.html', 'w', encoding='utf-8') as f:
                    f.write(response.text)
                print("响应已保存到：upload_response.html")
            
            # 如果是 "Invalid gallery" 错误，检查画廊是否被替换
            if "Invalid gallery" in error_message or "Invalid gallery" in response.text.lower():
                print("\n🔍 检测到 'Invalid gallery' 错误，检查画廊状态...")
                is_replaced, replacement_url = self.check_gallery_replaced(gallery_url)
                if is_replaced:
                    print("⚠️ 画廊已被替换，上传失败是预期的")
                    if replacement_url:
                        print(f"💡 请使用新画廊 URL 重试：{replacement_url}")
                    return False, is_replaced, replacement_url
            
            return False, False, None
    
    def check_gallery_replaced(self, gallery_url: str) -> tuple[bool, str | None]:
        """
        检查画廊是否已被替换（replaced）
        
        Args:
            gallery_url: 画廊 URL
        
        Returns:
            (is_replaced, replacement_url) - 如果被替换，返回 True 和新画廊 URL（如有）
        """
        gid, token, title = self.get_gallery_info(gallery_url)
        
        print(f"\n检查画廊状态：{title}")
        print(f"GID: {gid}, Token: {token}")
        
        # 访问画廊页面
        response = self.session.get(f"{self.base_url}/g/{gid}/{token}/", timeout=30)
        response.raise_for_status()
        
        # 检查是否被替换
        if "This gallery has been replaced" in response.text or "(Replaced)" in response.text:
            print("⚠️ 画廊已被替换（Replaced）")
            
            # 尝试提取新画廊 URL
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 查找 "There are newer versions of this gallery available:" 部分
            newer_versions_div = soup.find('div', id='gnd')
            if newer_versions_div:
                newer_links = newer_versions_div.find_all('a', href=True)
                if newer_links:
                    # 获取最后一个（最新）的画廊链接
                    latest_link = newer_links[-1]
                    latest_url = str(latest_link.get('href', ''))
                    if latest_url:
                        print(f"📌 找到更新版本：{latest_url}")
                        return True, latest_url
            
            print("ℹ️ 未找到新画廊 URL（可能有多个版本，建议手动检查）")
            return True, None
        
        print("✅ 画廊状态正常")
        return False, None
    
    def _download_personalized_torrent(self, gid: str, token: str, title: str, output_dir: str = "generated_torrents") -> str | None:
        """
        上传成功后，从画廊种子页面下载专属种子
        
        Returns:
            保存的文件路径，失败返回 None
        """
        import time
        
        start_monotonic = time.monotonic()
        link_wait_seconds_total = 0
        network_wait_seconds_total = 0
        validation_wait_seconds_total = 0
        validation_checks = 0

        print("\n⬇️ 下载专属种子...")
        torrent_url = f"https://e-hentai.org/gallerytorrents.php?gid={gid}&t={token}"
        download_link: str | None = None
        link_max_attempts = 5

        print(f"  🔎 [获取下载链接] 开始 ({link_max_attempts} 次以内)")
        link_attempts_used = 0
        for attempt in range(1, link_max_attempts + 1):
            link_attempts_used = attempt
            resp = self.session.get(torrent_url, timeout=30)
            if resp.status_code != 200:
                print(f"⚠️ [获取下载链接] 无法访问种子页面，状态码：{resp.status_code}")
                return None

            soup = BeautifulSoup(resp.text, 'html.parser')

            # 优先提取 onclick 里的动态专属下载地址。
            # 页面中的 href 往往只是静态占位链接，浏览器实际点击时会跳到 onclick 里的专属 token 链接。
            for a in soup.find_all('a'):
                onclick = str(a.get('onclick', ''))
                if onclick and 'ehtracker.org/get/' in onclick:
                    match = re.search(r"document\.location='(https://ehtracker\.org/get/[^']+)'", onclick)
                    if match:
                        download_link = match.group(1)
                        break

            if not download_link:
                for a in soup.find_all('a', href=True):
                    href = str(a['href'])
                    if 'ehtracker.org/get/' in href:
                        download_link = href
                        break

            if not download_link:
                for a in soup.find_all('a'):
                    onclick = str(a.get('onclick', ''))
                    if onclick and ('ehtracker' in onclick.lower() or 'download' in onclick.lower()):
                        match = re.search(r"['\"](https?://ehtracker\.org/[^'\"]+)['\"]", onclick)
                        if match:
                            download_link = match.group(1)
                            break

            if not download_link and 'ehtracker.org/get/' in resp.text:
                match = re.search(r'href="(https://ehtracker\.org/get/[^"]+)"', resp.text)
                if match:
                    download_link = match.group(1)

            if download_link:
                break

            wait_seconds = attempt * 2
            link_wait_seconds_total += wait_seconds
            print(f"⚠️ [获取下载链接] 第 {attempt}/{link_max_attempts} 次未找到专属下载链接，{wait_seconds} 秒后重试...")
            time.sleep(wait_seconds)

        if not download_link:
            elapsed = time.monotonic() - start_monotonic
            print("❌ [获取下载链接] 未找到专属种子下载链接")
            print(f"ℹ️ [下载专属种子] 本次耗时 {elapsed:.1f} 秒（等待：链接 {link_wait_seconds_total}s / 网络 {network_wait_seconds_total}s / 校验 {validation_wait_seconds_total}s）")
            return None

        print("✅ [获取下载链接] 已找到专属下载链接")
        
        # 下载种子并校验完整性
        dl_url = download_link if download_link.startswith('http') else f'https://e-hentai.org{download_link}'
        output_path = build_personalized_torrent_path(title, output_dir)
        output_path.parent.mkdir(exist_ok=True)

        # 这里的失败分两类：
        # 1) 网络/TLS/对端临时断流（例如 SSLEOFError、连接失败、超时、非 200），需要长间隔重试。
        # 2) HTTP 请求成功返回了内容，但内容不是合法 torrent（偶发生成延迟/占位内容），这种不应套用长等待。
        import requests

        download_timeout_seconds = 30

        # 第二层：真实下载请求的网络级重试（按你的策略：30 秒间隔、最多 10 次）
        network_retry_interval_seconds = 30
        network_max_attempts = 10

        # 第三层：内容校验失败的短重试（避免和网络长重试叠加导致总耗时过长）
        validation_max_attempts = 3
        validation_retry_interval_seconds = 2

        last_content = b''
        last_error: str | None = None
        network_attempts_used = 0

        print(f"  ⬇️ [下载专属种子] 开始（网络重试：{network_max_attempts} 次，每次间隔 {network_retry_interval_seconds}s；校验短重试：{validation_max_attempts} 次，每次间隔 {validation_retry_interval_seconds}s）")
        for net_attempt in range(1, network_max_attempts + 1):
            network_attempts_used = net_attempt
            try:
                dl = self.session.get(dl_url, timeout=download_timeout_seconds)
                last_content = dl.content

                if dl.status_code != 200:
                    last_error = f"HTTP {dl.status_code}"
                    print(f"⚠️ [下载专属种子] 第 {net_attempt}/{network_max_attempts} 次下载失败：HTTP {dl.status_code}")
                else:
                    # 网络请求成功后，进入内容校验短重试。
                    for val_attempt in range(1, validation_max_attempts + 1):
                        validation_checks += 1
                        if is_valid_torrent_bytes(last_content):
                            with open(output_path, 'wb') as f:
                                f.write(last_content)

                            print(f"✅ 已保存：{output_path} ({len(last_content):,} bytes)")
                            elapsed = time.monotonic() - start_monotonic
                            print(f"ℹ️ [下载专属种子] 本次耗时 {elapsed:.1f} 秒（等待：链接 {link_wait_seconds_total}s / 网络 {network_wait_seconds_total}s / 校验 {validation_wait_seconds_total}s；校验次数：{validation_checks}）")
                            return str(output_path)

                        last_error = "invalid torrent bytes"
                        if val_attempt >= validation_max_attempts:
                            break

                        validation_wait_seconds_total += validation_retry_interval_seconds
                        print(f"⚠️ [校验下载内容] 第 {val_attempt}/{validation_max_attempts} 次校验失败：返回内容不是合法 torrent，{validation_retry_interval_seconds} 秒后快速重试...")
                        time.sleep(validation_retry_interval_seconds)
                        dl = self.session.get(dl_url, timeout=download_timeout_seconds)
                        if dl.status_code != 200:
                            last_error = f"HTTP {dl.status_code}"
                            print(f"⚠️ [校验下载内容] 快速重试时下载失败：HTTP {dl.status_code}，交回网络重试")
                            break
                        last_content = dl.content

            except (requests.exceptions.SSLError, requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                print(f"⚠️ [下载专属种子] 第 {net_attempt}/{network_max_attempts} 次下载遇到网络异常：{type(exc).__name__}: {exc}")

            if net_attempt < network_max_attempts:
                network_wait_seconds_total += network_retry_interval_seconds
                if last_error:
                    print(f"  ⏳ [下载专属种子] {network_retry_interval_seconds} 秒后重试网络下载 ({net_attempt}/{network_max_attempts})，原因：{last_error}")
                else:
                    print(f"  ⏳ [下载专属种子] {network_retry_interval_seconds} 秒后重试网络下载 ({net_attempt}/{network_max_attempts})")
                time.sleep(network_retry_interval_seconds)

        debug_path = output_path.with_suffix('.invalid.bin')
        with open(debug_path, 'wb') as f:
            f.write(last_content)
        if last_error:
            elapsed = time.monotonic() - start_monotonic
            print(f"❌ [下载专属种子] 连续重试后仍失败（最后错误：{last_error}），已保存调试文件：{debug_path}")
            print(f"ℹ️ [下载专属种子] 本次耗时 {elapsed:.1f} 秒（等待：链接 {link_wait_seconds_total}s / 网络 {network_wait_seconds_total}s / 校验 {validation_wait_seconds_total}s；链接尝试：{link_attempts_used}/{link_max_attempts}；网络尝试：{network_attempts_used}/{network_max_attempts}；校验次数：{validation_checks}）")
        else:
            elapsed = time.monotonic() - start_monotonic
            print(f"❌ [下载专属种子] 连续重试后仍无效，已保存调试文件：{debug_path}")
            print(f"ℹ️ [下载专属种子] 本次耗时 {elapsed:.1f} 秒（等待：链接 {link_wait_seconds_total}s / 网络 {network_wait_seconds_total}s / 校验 {validation_wait_seconds_total}s；校验次数：{validation_checks}）")
        return None


def load_cookie_from_file(filepath: str) -> str:
    """从 Netscape 格式 Cookie 文件加载 Cookie 字符串"""
    cookies: dict[str, str] = {}
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t')
            if len(parts) >= 7:
                _, _, _, _, _, name, value = parts[:7]
                cookies[name] = value
    
    # 转换为 Cookie 字符串
    return '; '.join([f"{k}={v}" for k, v in cookies.items()])


def main():
    parser = argparse.ArgumentParser(
        description='e-hentai 种子上传工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    # 从默认文件读取 Cookie (eht-netscape.cookie)
    uv run python ehentai_uploader.py https://e-hentai.org/g/3828071/76966bded7/
    
    # 指定 Cookie 文件
    uv run python ehentai_uploader.py -f mycookie.txt https://e-hentai.org/g/3828071/76966bded7/
    
    # 使用 Cookie 字符串
    uv run python ehentai_uploader.py -c "ipb_member_id=xxx; ipb_pass_hash=xxx;" https://e-hentai.org/g/xxx/
    
    # 上传种子
    uv run python ehentai_uploader.py -f eht-netscape.cookie --upload "种子.torrent" https://e-hentai.org/g/3828071/76966bded7/
        """
    )
    
    parser.add_argument('url', help='e-hentai 画廊 URL')
    parser.add_argument('--cookie', '-c', help='e-hentai Cookie 字符串')
    parser.add_argument('--cookie-file', '-f', default='eht-netscape.cookie', help='Cookie 文件路径（默认：eht-netscape.cookie）')
    parser.add_argument('--upload', '-u', help='上传种子文件（指定.torrent 文件路径）')
    parser.add_argument('--get-tracker', '-g', action='store_true', help='仅获取 tracker 信息')
    parser.add_argument('--output', '-o', help='输出文件路径（保存 tracker）')
    parser.add_argument('--comment', help='种子评论（上传时使用）')
    parser.add_argument('--proxy', '-p', default='http://127.0.0.1:10809', help='HTTP 代理地址（默认：http://127.0.0.1:10809）')
    parser.add_argument('--skip-download', action='store_true', help='上传后不下载专属种子')
    parser.add_argument('--output-dir', default='generated_torrents', help='专属种子保存目录（默认：generated_torrents）')
    
    args = parser.parse_args()
    
    # 获取 Cookie
    if args.cookie:
        cookie_str = args.cookie
        print("使用 Cookie 字符串")
    else:
        cookie_file = Path(args.cookie_file)
        if not cookie_file.exists():
            print(f"❌ Cookie 文件不存在：{cookie_file}", file=sys.stderr)
            sys.exit(1)
        cookie_str = load_cookie_from_file(str(cookie_file))
        print(f"从文件加载 Cookie: {cookie_file}")
    
    try:
        uploader = EHentaiUploader(cookie_str, proxy=args.proxy)
        
        # 测试登录
        print("测试登录状态...")
        test_url = f"{uploader.base_url}/home.php"
        response = uploader.session.get(test_url, timeout=10)
        if 'Welcome back' in response.text or 'Favorites' in response.text or 'My Home' in response.text:
            print("✅ 登录成功")
        elif args.cookie:
            print("⚠️ 可能未成功登录，请检查 Cookie 是否正确")
        else:
            print("ℹ️ 继续（未验证登录状态）")
        
        if args.upload:
            # 上传种子
            download_personalized = not args.skip_download
            success, is_replaced, replacement_url = uploader.upload_torrent(
                args.url, 
                args.upload, 
                args.comment,
                download_personalized=download_personalized,
                output_dir=args.output_dir
            )
            if not success and is_replaced:
                print("\n⚠️ 画廊已被替换")
                if replacement_url:
                    print(f"💡 新画廊 URL: {replacement_url}")
            sys.exit(0 if success else 1)
        else:
            # 获取 tracker 信息
            print("\n获取 tracker 信息...")
            info = uploader.get_tracker_info(args.url)
            
            print("\n" + "=" * 60)
            print("Tracker 信息")
            print("=" * 60)
            
            if info.get('tracker'):
                print(f"Tracker: {info['tracker']}")
            else:
                print("Tracker: https://ehgt.net/t.php (e-hentai 官方)")
            
            max_size = info.get('max_size')
            if isinstance(max_size, int):
                print(f"最大种子大小：{max_size / 1024:.1f} KB")
            
            if info.get('instructions'):
                print(f"\n说明:\n{info['instructions']}")
            
            # 保存到文件
            if args.output and info.get('tracker'):
                with open(args.output, 'w', encoding='utf-8') as f:
                    f.write(f"{info['tracker']}\n")
                    print(f"\n✅ 已保存到：{args.output}")
        
    except Exception as e:
        print(f"\n❌ 错误：{e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
