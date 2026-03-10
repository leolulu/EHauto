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

import sys
import argparse
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import re

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
    
    def upload_torrent(self, gallery_url: str, torrent_path: str, comment: str = "", download_personalized: bool = True, output_dir: str = "generated_torrents") -> bool:
        """
        上传种子文件到 e-hentai
        
        Args:
            gallery_url: 画廊 URL
            torrent_path: 种子文件路径
            comment: 种子评论
            download_personalized: 上传成功后是否下载专属种子
            output_dir: 专属种子保存目录
        
        Returns:
            上传是否成功
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
            print(f"[ERROR] 种子文件超过 10MB 限制")
            return False
        
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
            print("[OK] 上传成功!")
            
            # 下载专属种子
            if download_personalized:
                downloaded_path = self._download_personalized_torrent(gid, token, title, output_dir)
                if not downloaded_path:
                    print("[ERROR] 上传成功，但下载专属种子失败")
                    return False
            
            return True
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
            if error:
                print(f"[ERROR] 上传失败：{error.get_text().strip()}")
            else:
                print("[ERROR] 上传失败（未知原因）")
                # 保存响应以便调试
                with open('upload_response.html', 'w', encoding='utf-8') as f:
                    f.write(response.text)
                print("响应已保存到：upload_response.html")
            return False
    
    def _download_personalized_torrent(self, gid: str, token: str, title: str, output_dir: str = "generated_torrents") -> str | None:
        """
        上传成功后，从画廊种子页面下载专属种子
        
        Returns:
            保存的文件路径，失败返回 None
        """
        import time
        from pathlib import Path
        
        print("\n📥 下载专属种子...")
        torrent_url = f"https://e-hentai.org/gallerytorrents.php?gid={gid}&t={token}"
        download_link: str | None = None

        for attempt in range(1, 6):
            resp = self.session.get(torrent_url, timeout=30)
            if resp.status_code != 200:
                print(f"⚠ 无法访问种子页面，状态码：{resp.status_code}")
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
            print(f"  第 {attempt} 次未找到下载链接，{wait_seconds} 秒后重试...")
            time.sleep(wait_seconds)

        if not download_link:
            print("⚠ 未找到专属种子下载链接")
            return None
        
        # 下载种子并校验完整性
        dl_url = download_link if download_link.startswith('http') else f'https://e-hentai.org{download_link}'
        output_path = build_personalized_torrent_path(title, output_dir)
        output_path.parent.mkdir(exist_ok=True)

        last_content = b''
        for attempt in range(1, 4):
            dl = self.session.get(dl_url, timeout=30)
            last_content = dl.content

            if dl.status_code != 200:
                print(f"⚠ 下载失败，状态码：{dl.status_code}")
                return None

            if is_valid_torrent_bytes(last_content):
                with open(output_path, 'wb') as f:
                    f.write(last_content)

                print(f"✓ 已保存：{output_path} ({len(last_content):,} bytes)")
                return str(output_path)

            print(f"⚠ 第 {attempt} 次下载到的专属种子无效，准备重试...")

        debug_path = output_path.with_suffix('.invalid.bin')
        with open(debug_path, 'wb') as f:
            f.write(last_content)
        print(f"⚠ 专属种子连续重试后仍无效，已保存调试文件：{debug_path}")
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
            print(f"[ERROR] Cookie 文件不存在：{cookie_file}", file=sys.stderr)
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
            print("[OK] 登录成功")
        elif args.cookie:
            print("[WARNING] 可能未成功登录，请检查 Cookie 是否正确")
        else:
            print("[INFO] 继续（未验证登录状态）")
        
        if args.upload:
            # 上传种子
            download_personalized = not args.skip_download
            success = uploader.upload_torrent(
                args.url, 
                args.upload, 
                args.comment,
                download_personalized=download_personalized,
                output_dir=args.output_dir
            )
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
                print(f"\n[OK] 已保存到：{args.output}")
        
    except Exception as e:
        print(f"\n[ERROR] 错误：{e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
