#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
e-hentai 画廊下载器
===================

根据推荐列表或指定 URL 自动下载 Original Archive。

## 功能特点
- 支持从推荐文件批量下载
- 支持单个画廊 URL 下载
- 验证登录状态并显示 GP 余额
- 自动提取 Archiver URL
- 校验下载结果

## 依赖

- Python 3.10+
- 在当前目录同步 Python 依赖：uv sync
- 需要安装浏览器：uv run playwright install chromium

## 使用方法

```bash
# 从推荐文件下载（前 3 个）
uv run python ehentai_downloader.py --input ehentai_recommendations.txt --count 3

# 下载单个画廊
uv run python ehentai_downloader.py --url https://e-hentai.org/g/3825480/ea9a84a5b6/

# 显示浏览器窗口
uv run python ehentai_downloader.py --url https://e-hentai.org/g/3825480/ea9a84a5b6/ --show-browser
```

## 返回值
- Exit Code 0: 所有下载成功
- Exit Code 1: 部分或全部下载失败
"""

import hashlib
import json
import re
import time
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, TypedDict
from zipfile import BadZipFile, ZipFile


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


def parse_netscape_cookie_file(file_path: str) -> list[CookieParam]:
    """解析 Netscape 格式的 Cookie 文件。"""
    cookies: list[CookieParam] = []

    with open(file_path, "r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split("\t")
            if len(parts) < 7:
                continue

            domain, _flag, path, _secure, _expiration, name, value = parts[:7]
            if not domain.startswith("."):
                domain = "." + domain

            cookies.append(
                {
                    "name": name,
                    "value": value,
                    "domain": domain,
                    "path": path,
                }
            )

    return cookies


def check_login_status(page) -> tuple[bool, int]:
    """
    检查登录状态并获取 GP 余额。

    Returns:
        tuple[bool, int]: (是否已登录, GP 余额)
    """
    page.goto("https://e-hentai.org/home.php", wait_until="domcontentloaded")
    page.wait_for_timeout(2000)

    if "login" in page.url.lower():
        return False, 0

    page.goto("https://e-hentai.org/exchange.php?t=gp", wait_until="domcontentloaded")
    page.wait_for_timeout(2000)

    content = page.content()
    gp_match = re.search(r"Available:\s*([\d,]+)\s*kGP", content)
    gp_balance = int(gp_match.group(1).replace(",", "")) * 1000 if gp_match else 0
    return True, gp_balance


def extract_gid_token(gallery_url: str) -> tuple[str | None, str | None]:
    """从画廊 URL 提取 gid 和 token。"""
    match = re.search(r"/g/(\d+)/([a-f0-9]+)", gallery_url)
    if not match:
        return None, None
    return match.group(1), match.group(2)


def _extract_first_match(pattern: str, content: str) -> str | None:
    """提取首个正则匹配组。"""
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        return None
    return match.group(1).strip()


def _parse_int(value: str | None) -> int | None:
    """解析整数文本。"""
    if value is None:
        return None
    normalized = value.replace(",", "").strip()
    if not normalized:
        return None
    return int(normalized)


def _parse_float(value: str | None) -> float | None:
    """解析浮点数文本。"""
    if value is None:
        return None
    normalized = value.replace(",", "").strip()
    if not normalized:
        return None
    return float(normalized)


def _parse_size_to_mib(size_text: str | None) -> float | None:
    """把文件大小文本转换为 MiB。"""
    if not size_text:
        return None

    match = re.search(r"([\d.]+)\s*([KMGT]?i?B)", size_text, re.IGNORECASE)
    if not match:
        return None

    size_value = float(match.group(1))
    size_unit = match.group(2).lower()
    unit_to_mib = {
        "kib": 1 / 1024,
        "kb": 1 / 1024,
        "mib": 1,
        "mb": 1,
        "gib": 1024,
        "gb": 1024,
        "tib": 1024 * 1024,
        "tb": 1024 * 1024,
    }
    multiplier = unit_to_mib.get(size_unit)
    if multiplier is None:
        return None
    return size_value * multiplier


def _build_archive_sidecar_path(save_path: Path) -> Path:
    """为下载文件生成同名 JSON 路径。"""
    return save_path.with_suffix(".json")


def _compute_sha256(file_path: Path) -> str:
    """计算文件 SHA256。"""
    digest = hashlib.sha256()
    with open(file_path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _collect_zip_metadata(file_path: Path) -> dict[str, Any]:
    """收集 ZIP 归档元信息。"""
    metadata: dict[str, Any] = {
        "is_zip": False,
        "entry_count": 0,
        "sample_entries": [],
        "total_uncompressed_bytes": None,
        "comment": "",
    }

    try:
        with ZipFile(file_path, "r") as archive:
            info_list = archive.infolist()
            metadata["is_zip"] = True
            metadata["entry_count"] = len(info_list)
            metadata["sample_entries"] = [info.filename for info in info_list[:20]]
            metadata["total_uncompressed_bytes"] = sum(info.file_size for info in info_list)
            metadata["comment"] = archive.comment.decode("utf-8", errors="replace") if archive.comment else ""
    except BadZipFile:
        metadata["zip_error"] = "invalid_zip"

    return metadata


def extract_gallery_metadata_from_detail_page(content: str, gallery_url: str, gid: str, token: str) -> dict[str, Any]:
    """从画廊详情页提取元信息。"""
    title = _extract_first_match(r'<h1 id="gn">([^<]+)</h1>', content)
    title_jpn = _extract_first_match(r'<h1 id="gj">([^<]+)</h1>', content)
    category = _extract_first_match(r'<div class="cs [^"]+">([^<]+)</div>', content)
    uploader = _extract_first_match(r'<a href="https://e-hentai.org/uploader/[^"]+">([^<]+)</a>', content)
    posted = _extract_first_match(r'Posted:</td>\s*<td[^>]*>([^<]+)</td>', content)
    parent = _extract_first_match(r'Parent:</td>\s*<td[^>]*>(.*?)</td>', content)
    visible = _extract_first_match(r'Visible:</td>\s*<td[^>]*>([^<]+)</td>', content)
    language = _extract_first_match(r'Language:</td>\s*<td[^>]*>([^<]+)</td>', content)
    file_size_text = _extract_first_match(r'File Size:</td>\s*<td[^>]*>([^<]+)</td>', content)
    pages_text = _extract_first_match(r'Length:</td>\s*<td[^>]*>(\d+)\s*pages', content)
    rating_text = _extract_first_match(r'var average_rating\s*=\s*([\d.]+)', content)
    rating_count_text = _extract_first_match(r'id="rating_count">(\d+)</span>', content)
    favorited_text = _extract_first_match(r'id="favcount">(\d+(?:,\d+)*)\s*times', content)
    torrent_count_text = _extract_first_match(r'Torrent Downloads:</td>\s*<td[^>]*>(\d+)</td>', content)

    tag_matches = re.findall(r'<a id="td_[^"]+"[^>]*>(.*?)</a>', content, re.DOTALL)
    tags = [re.sub(r"<[^>]+>", "", tag).strip() for tag in tag_matches if re.sub(r"<[^>]+>", "", tag).strip()]

    return {
        "gid": gid,
        "token": token,
        "url": gallery_url,
        "archiver_url": f"https://e-hentai.org/archiver.php?gid={gid}&token={token}",
        "title": title or "Unknown",
        "title_japanese": title_jpn,
        "category": category,
        "uploader": uploader,
        "posted": posted,
        "parent": re.sub(r"<[^>]+>", "", parent).strip() if parent else None,
        "visible": visible,
        "language": language,
        "file_size_text": file_size_text,
        "file_size_mib": _parse_size_to_mib(file_size_text),
        "pages": _parse_int(pages_text),
        "rating": _parse_float(rating_text),
        "rating_count": _parse_int(rating_count_text),
        "favorited_count": _parse_int(favorited_text),
        "torrent_downloads": _parse_int(torrent_count_text),
        "tags": tags,
        "detail_page_title": _extract_first_match(r"<title>(.*?)</title>", content),
    }


def extract_archiver_metadata_from_page(content: str, archiver_url: str) -> dict[str, Any]:
    """从 Archiver 页面提取元信息。"""
    cost_text = _extract_first_match(r"Download Cost:.*?<strong>(\d+(?:,\d+)*)\s*GP</strong>", content)
    estimated_size_text = _extract_first_match(r"Estimated Size:.*?<strong>([^<]+)</strong>", content)
    resample_text = _extract_first_match(r"Resample:.*?<strong>([^<]+)</strong>", content)
    download_forms = len(re.findall(r'name="dlcheck"', content))
    return {
        "archiver_url": archiver_url,
        "download_cost_gp": _parse_int(cost_text),
        "estimated_size_text": estimated_size_text,
        "estimated_size_mib": _parse_size_to_mib(estimated_size_text),
        "resample": resample_text,
        "archiver_page_title": _extract_first_match(r"<title>(.*?)</title>", content),
        "download_form_count": download_forms,
    }


def write_sidecar_metadata(metadata_path: Path, metadata: dict[str, Any]) -> None:
    """写入 sidecar JSON 文件。"""
    temp_path = metadata_path.with_name(f"{metadata_path.name}.tmp")
    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(metadata, file, ensure_ascii=False, indent=2)
    temp_path.replace(metadata_path)


def build_failure_metadata(
    gallery_url: str,
    gid: str | None,
    token: str | None,
    source_metadata: dict[str, Any] | None,
    runtime_metadata: dict[str, Any],
    error_stage: str,
    error_message: str,
    detail_metadata: dict[str, Any] | None = None,
    archiver_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造失败场景下的 sidecar 元信息。"""
    gallery_metadata = detail_metadata or {
        "gid": gid,
        "token": token,
        "url": gallery_url,
        "archiver_url": f"https://e-hentai.org/archiver.php?gid={gid}&token={token}" if gid and token else None,
        "title": source_metadata.get("title") if source_metadata else "Unknown",
    }
    return {
        "schema_version": 1,
        "_schema_description": "Downloaded archive sidecar metadata for ehentai_downloader.py",
        "success": False,
        "error": {
            "stage": error_stage,
            "message": error_message,
            "recorded_at": datetime.now().astimezone().isoformat(),
        },
        "download": None,
        "gallery": gallery_metadata,
        "archiver": archiver_metadata,
        "recommendation": source_metadata,
        "runtime": runtime_metadata,
        "archive_contents": None,
    }


def parse_recommendations_file(file_path: str) -> list[dict[str, Any]]:
    """解析推荐文件，提取画廊 URL 和评分信息。"""
    galleries: list[dict[str, Any]] = []

    with open(file_path, "r", encoding="utf-8") as file:
        lines = file.readlines()

    current_gallery: dict[str, Any] | None = None

    for line in lines:
        line = line.strip()

        title_match = re.match(r"\[\s*(\d+)\]\s*(.+)$", line)
        if title_match:
            if current_gallery and current_gallery["url"]:
                galleries.append(current_gallery)
            current_gallery = {
                "index": int(title_match.group(1)),
                "title": title_match.group(2).strip(),
                "url": None,
                "gp_cost": 0,
                "score": 0.0,
                "category": None,
                "uploader": None,
                "pages": None,
                "size_mib": None,
                "rating": None,
                "rating_count": None,
                "favorited_count": None,
                "gp_per_page": None,
                "gp_per_mb": None,
                "archiver_url": None,
            }
            continue

        if current_gallery is None:
            continue

        if line.startswith("URL:"):
            url_match = re.search(r"(https://e-hentai.org/g/\d+/[a-f0-9]+/)", line)
            if url_match:
                current_gallery["url"] = url_match.group(1)
            continue

        if line.startswith("分类："):
            category_uploader_match = re.search(r"分类：(.+?)\s*\|\s*上传者：(.+)", line)
            if category_uploader_match:
                current_gallery["category"] = category_uploader_match.group(1).strip()
                current_gallery["uploader"] = category_uploader_match.group(2).strip()
            continue

        if line.startswith("页数："):
            pages_size_match = re.search(r"页数：(\d+)\s*\|\s*大小：([\d.]+)\s*MiB", line)
            if pages_size_match:
                current_gallery["pages"] = int(pages_size_match.group(1))
                current_gallery["size_mib"] = float(pages_size_match.group(2))
            continue

        if line.startswith("Rating:"):
            rating_match = re.search(r"Rating:\s*([\d.]+)\s*\((\d+)人评分\)\s*\|\s*收藏：(\d+)次", line)
            if rating_match:
                current_gallery["rating"] = float(rating_match.group(1))
                current_gallery["rating_count"] = int(rating_match.group(2))
                current_gallery["favorited_count"] = int(rating_match.group(3))
            continue

        if "GP 成本" in line:
            gp_match = re.search(r"(\d+(?:,\d+)*)\s*GP", line)
            if gp_match:
                current_gallery["gp_cost"] = int(gp_match.group(1).replace(",", ""))
            continue

        if line.startswith("GP/页："):
            gp_efficiency_match = re.search(r"GP/页：([\d.]+)\s*\|\s*GP/MB:\s*([\d.]+)", line)
            if gp_efficiency_match:
                current_gallery["gp_per_page"] = float(gp_efficiency_match.group(1))
                current_gallery["gp_per_mb"] = float(gp_efficiency_match.group(2))
            continue

        if "综合评分" in line:
            score_match = re.search(r"([\d.]+)/100", line)
            if score_match:
                current_gallery["score"] = float(score_match.group(1))
            continue

        if line.startswith("下载链接："):
            download_link_match = re.search(r"下载链接：\s*(https://e-hentai.org/archiver\.php\?gid=\d+&token=[a-f0-9]+)", line)
            if download_link_match:
                current_gallery["archiver_url"] = download_link_match.group(1)

    if current_gallery and current_gallery["url"]:
        galleries.append(current_gallery)

    return galleries


def download_gallery(page, gallery_url: str, output_dir: str, source_metadata: dict[str, Any] | None, runtime_metadata: dict[str, Any]) -> dict[str, Any] | None:
    """下载单个画廊的 Original Archive。"""
    from importlib import import_module

    PlaywrightTimeout = import_module('playwright.sync_api').TimeoutError

    gid: str | None = None
    token: str | None = None
    gallery_metadata: dict[str, Any] | None = None
    archiver_metadata: dict[str, Any] | None = None
    metadata_path: Path | None = None
    try:
        gid, token = extract_gid_token(gallery_url)
        if not gid or not token:
            print(f"  [X] 无法从 URL 提取 gid/token: {gallery_url}")
            fallback_name = (source_metadata or {}).get("title") or "download_failure"
            safe_title = re.sub(r'[<>:"/\\|?*]', "_", fallback_name)[:100] or "download_failure"
            metadata_path = _build_archive_sidecar_path(Path(output_dir) / f"{safe_title}.zip")
            write_sidecar_metadata(
                metadata_path,
                build_failure_metadata(
                    gallery_url,
                    gid,
                    token,
                    source_metadata,
                    runtime_metadata,
                    "extract_gid_token",
                    "无法从 URL 提取 gid/token",
                ),
            )
            return None

        archiver_url = f"https://e-hentai.org/archiver.php?gid={gid}&token={token}"
        download_started_at = datetime.now().astimezone().isoformat()

        print(f"  访问详情页：{gallery_url}")
        page.goto(gallery_url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        detail_content = page.content()
        gallery_metadata = extract_gallery_metadata_from_detail_page(detail_content, gallery_url, gid, token)
        title = gallery_metadata["title"]
        safe_title = re.sub(r'[<>:"/\\|?*]', "_", title)[:100]
        metadata_path = _build_archive_sidecar_path(Path(output_dir) / f"{safe_title}.zip")

        print(f"  画廊：{title[:50]}...")
        print("  访问 Archiver 页面...")
        page.goto(archiver_url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        archiver_content = page.content()
        archiver_metadata = extract_archiver_metadata_from_page(archiver_content, archiver_url)

        print("  查找下载按钮...")
        download_button = page.locator('input[value="Download Original Archive"]')
        if download_button.count() == 0:
            download_button = page.locator('input[type="submit"][name="dlcheck"]')
        if download_button.count() == 0:
            download_button = page.locator('input[type="submit"]').first

        if download_button.count() == 0:
            print("  [X] 未找到下载按钮")
            with open("debug_archiver.html", "w", encoding="utf-8") as file:
                file.write(archiver_content)
            print("  已保存调试文件：debug_archiver.html")
            write_sidecar_metadata(
                metadata_path,
                build_failure_metadata(
                    gallery_url,
                    gid,
                    token,
                    source_metadata,
                    runtime_metadata,
                    "locate_download_button",
                    "未找到下载按钮",
                    detail_metadata=gallery_metadata,
                    archiver_metadata=archiver_metadata,
                ),
            )
            return None

        print("  点击下载 Original Archive...")
        with page.expect_download(timeout=300000) as download_info:
            download_button.click()
            print("  等待下载开始...")

        download = download_info.value
        suggested_filename = download.suggested_filename or f"{safe_title}.zip"
        save_path = Path(output_dir) / suggested_filename
        metadata_path = _build_archive_sidecar_path(save_path)

        print(f"  正在保存：{save_path.name}")
        download.save_as(save_path)

        if save_path.exists():
            file_size_bytes = save_path.stat().st_size
            file_size = file_size_bytes / (1024 * 1024)
            file_sha256 = _compute_sha256(save_path)
            zip_metadata = _collect_zip_metadata(save_path)
            detail_size_mib = gallery_metadata.get("file_size_mib")
            metadata = {
                "schema_version": 1,
                "_schema_description": "Downloaded archive sidecar metadata for ehentai_downloader.py",
                "success": True,
                "download": {
                    "started_at": download_started_at,
                    "completed_at": datetime.now().astimezone().isoformat(),
                    "download_url": getattr(download, "url", None),
                    "saved_filename": save_path.name,
                    "saved_path": str(save_path.resolve()),
                    "saved_dir": str(save_path.parent.resolve()),
                    "sidecar_json_filename": metadata_path.name,
                    "sidecar_json_path": str(metadata_path.resolve()),
                    "suggested_filename": suggested_filename,
                    "safe_title_fallback": f"{safe_title}.zip",
                    "file_size_bytes": file_size_bytes,
                    "file_size_mib": round(file_size, 2),
                    "sha256": file_sha256,
                    "size_matches_detail_estimate": None if detail_size_mib is None else abs(detail_size_mib - file_size) < 1,
                },
                "gallery": gallery_metadata,
                "archiver": archiver_metadata,
                "recommendation": source_metadata,
                "runtime": runtime_metadata,
                "archive_contents": zip_metadata,
            }
            write_sidecar_metadata(metadata_path, metadata)
            print(f"  [OK] 下载完成：{file_size:.2f} MiB")
            print(f"  保存位置：{save_path}")
            print(f"  元信息：{metadata_path.name}")
            return metadata

        print("  [X] 文件保存失败")
        if metadata_path is not None:
            write_sidecar_metadata(
                metadata_path,
                build_failure_metadata(
                    gallery_url,
                    gid,
                    token,
                    source_metadata,
                    runtime_metadata,
                    "save_archive",
                    "文件保存失败",
                    detail_metadata=gallery_metadata,
                    archiver_metadata=archiver_metadata,
                ),
            )
        return None

    except PlaywrightTimeout:
        print("  [X] 操作超时")
        if metadata_path is not None:
            write_sidecar_metadata(
                metadata_path,
                build_failure_metadata(
                    gallery_url,
                    gid,
                    token,
                    source_metadata,
                    runtime_metadata,
                    "timeout",
                    "操作超时",
                    detail_metadata=gallery_metadata,
                    archiver_metadata=archiver_metadata,
                ),
            )
        return None
    except Exception as error:
        print(f"  [X] 下载失败：{error}")
        import traceback

        traceback.print_exc()
        if metadata_path is not None:
            write_sidecar_metadata(
                metadata_path,
                build_failure_metadata(
                    gallery_url,
                    gid,
                    token,
                    source_metadata,
                    runtime_metadata,
                    "exception",
                    str(error),
                    detail_metadata=gallery_metadata,
                    archiver_metadata=archiver_metadata,
                ),
            )
        return None


def main() -> int:
    """CLI 入口。"""
    import argparse
    from importlib import import_module

    sync_playwright = import_module('playwright.sync_api').sync_playwright

    parser = argparse.ArgumentParser(
        description="e-hentai 画廊下载器 - 自动下载 Original Archive",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  从推荐文件下载（前 3 个）:
    %(prog)s --input ehentai_recommendations.txt --count 3

  下载单个画廊:
    %(prog)s --url https://e-hentai.org/g/3825480/ea9a84a5b6/

  显示浏览器窗口:
    %(prog)s --url https://e-hentai.org/g/3825480/ea9a84a5b6/ --show-browser
        """,
    )
    parser.add_argument(
        "--input",
        "-i",
        default="ehentai_recommendations.txt",
        help="推荐文件路径 (默认：ehentai_recommendations.txt)",
    )
    parser.add_argument(
        "--url",
        "-u",
        default=None,
        help="单个画廊 URL（使用此参数时忽略 --input）",
    )
    parser.add_argument(
        "--count",
        "-n",
        type=int,
        default=999,
        help="下载前 N 个画廊 (默认：999，即下载全部)",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0,
        help="最低综合评分要求，只下载评分大于等于此值的画廊 (默认：0，下载全部)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="downloads",
        help="输出目录 (默认：downloads)",
    )
    parser.add_argument(
        "--cookie-file",
        "-f",
        default="eht-netscape.cookie",
        help="Cookie 文件路径",
    )
    parser.add_argument(
        "--proxy",
        "-s",
        default="http://127.0.0.1:10809",
        help="代理服务器地址",
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=5,
        help="每个下载之间的延迟秒数 (默认：5)",
    )
    parser.add_argument(
        "--show-browser",
        action="store_true",
        help="显示浏览器窗口（默认无头模式）",
    )

    args = parser.parse_args()

    print("=" * 80)
    print("e-hentai 画廊下载器")
    print("=" * 80)

    if args.url:
        galleries = [
            {
                "url": args.url,
                "title": "Single Gallery",
                "gp_cost": 0,
                "score": 0.0,
            }
        ]
        print("\n模式：单画廊下载")
        print(f"画廊 URL: {args.url}")
    else:
        print(f"\n推荐文件：{args.input}")
        if not Path(args.input).exists():
            print(f"错误：推荐文件不存在：{args.input}")
            return 1

        print("解析推荐列表...")
        galleries = parse_recommendations_file(args.input)
        print(f"找到 {len(galleries)} 个推荐的画廊")

        if not galleries:
            print("没有可下载的画廊")
            return 1

        if args.min_score > 0:
            galleries = [gallery for gallery in galleries if gallery["score"] >= args.min_score]
            print(f"评分筛选 (>= {args.min_score}): 剩余 {len(galleries)} 个画廊")

        galleries = galleries[: args.count]
        print(f"将下载前 {len(galleries)} 个画廊")

    print(f"输出目录：{args.output}")
    print(f"Cookie 文件：{args.cookie_file}")
    print(f"代理：{args.proxy}")
    print(f"无头模式：{'否（显示浏览器）' if args.show_browser else '是'}")
    print()

    if not Path(args.cookie_file).exists():
        print(f"错误：Cookie 文件不存在：{args.cookie_file}")
        return 1

    cookies = parse_netscape_cookie_file(args.cookie_file)
    print(f"加载了 {len(cookies)} 个 Cookie")

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        print("\n启动浏览器...")
        browser = playwright.chromium.launch(
            headless=not args.show_browser,
            proxy={"server": args.proxy},
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            accept_downloads=True,
        )
        context.add_cookies(cookies)
        page = context.new_page()

        print("\n[步骤 1/4] 验证登录状态...")
        logged_in, gp_balance = check_login_status(page)
        if logged_in:
            print("[OK] 已登录")
            print(f"可用 GP: {gp_balance:,}")
        else:
            print("[X] 未登录！Cookie 可能已过期")
            print(f"请重新导出 Cookie 文件：{args.cookie_file}")
            browser.close()
            return 1

        success_count = 0
        failed_count = 0

        for index, gallery in enumerate(galleries, 1):
            gallery_url = str(gallery["url"])
            gallery_title = str(gallery.get("title", "Unknown"))
            gallery_gp_cost = int(gallery.get("gp_cost", 0) or 0)
            gallery_score = float(gallery.get("score", 0.0) or 0.0)
            runtime_metadata = {
                "download_mode": "single_url" if args.url else "recommendations_file",
                "recommendations_file": None if args.url else str(Path(args.input).resolve()),
                "requested_url": args.url,
                "gallery_index_in_batch": index,
                "gallery_count_in_batch": len(galleries),
                "gp_balance_before_download": gp_balance,
                "output_dir": str(output_dir.resolve()),
                "show_browser": args.show_browser,
                "delay_seconds": args.delay,
                "downloaded_via": "ehentai_downloader.py",
            }

            print(f"\n{'=' * 80}")
            if not args.url:
                print(f"下载 [{index}/{len(galleries)}]: {gallery_title[:60]}")
                print(f"URL: {gallery_url}")
                print(f"GP 成本：{gallery_gp_cost:,} GP | 评分：{gallery_score}")
                print(f"{'=' * 80}")

            print("\n[步骤 2/4] 访问画廊详情...")
            metadata = download_gallery(page, gallery_url, str(output_dir), gallery, runtime_metadata)
            if metadata is not None:
                success_count += 1
            else:
                failed_count += 1

            if index < len(galleries) and metadata is not None:
                print(f"\n等待 {args.delay} 秒...")
                time.sleep(args.delay)

        browser.close()

    print(f"\n{'=' * 80}")
    print("下载完成")
    print(f"{'=' * 80}")
    print(f"成功：{success_count} 个")
    print(f"失败：{failed_count} 个")
    print(f"输出目录：{output_dir.absolute()}")

    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n用户中断下载")
        sys.exit(130)
    except Exception as error:
        print(f"\n错误：{error}")
        sys.exit(1)
