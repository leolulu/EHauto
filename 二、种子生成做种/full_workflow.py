#!/usr/bin/env python3
"""
完整工作流总控脚本：
1. 获取 e-hentai 画廊专属 tracker
2. 上传本地文件到远程服务器并生成 torrent
3. 上传 torrent 到 e-hentai，并自动下载 personalized torrent
4. 使用 personalized torrent 在 qBittorrent 中开始做种
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import dotenv_values

from create_torrent import (
    convert_smb_to_server_path,
    create_torrent_remote,
    upload_to_smb,
)
from ehentai_uploader import EHentaiUploader, build_personalized_torrent_path, load_cookie_from_file
from seed_personalized import add_torrent_for_seeding, derive_qb_save_path


def load_config() -> dict[str, str]:
    env_file = Path(".env")
    if not env_file.exists():
        raise FileNotFoundError("找不到 .env 配置文件，请先复制 .env.example 为 .env")

    raw_config = dotenv_values(env_file)
    required_keys = (
        "SMB_ROOT_PATH",
        "SERVER_ROOT_PATH",
        "QB_HOST",
        "QB_PORT",
        "QB_USERNAME",
        "QB_PASSWORD",
    )

    missing = [key for key in required_keys if not raw_config.get(key) or raw_config.get(key) == "你的密码"]
    if missing:
        raise ValueError(f".env 缺少必需配置项: {', '.join(missing)}")

    return {key: str(value) for key, value in raw_config.items() if value is not None}


def build_generated_torrent_path(local_source: str, output_dir: str) -> Path:
    source_path = Path(local_source)
    base_name = source_path.stem if source_path.is_file() else source_path.name
    return Path(output_dir) / f"{base_name}.torrent"


def find_sidecar_json(source_path: Path) -> Path:
    json_path = source_path.with_suffix(".json")
    if not json_path.exists():
        raise FileNotFoundError(f"找不到同名 JSON 元数据文件: {json_path}")
    return json_path


def collect_workflow_sources(source_path: Path) -> list[Path]:
    if source_path.is_file():
        return [source_path]

    if not source_path.is_dir():
        raise FileNotFoundError(f"本地路径不存在: {source_path}")

    zip_sources = sorted(path for path in source_path.iterdir() if path.is_file() and path.suffix.lower() == ".zip")
    if not zip_sources:
        raise FileNotFoundError(f"目录中未找到任何 .zip 文件: {source_path}")

    return zip_sources


def load_gallery_url_from_json(json_path: Path) -> str:
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    gallery_url = data.get("gallery", {}).get("url")
    if not gallery_url:
        raise ValueError(f"JSON 中缺少 gallery.url: {json_path}")
    return str(gallery_url)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="完整工作流总控：以压缩包为入口，生成 torrent -> 上传 -> 下载 personalized -> 开始做种",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    # 单文件完整流程（自动读取同名 JSON 中的画廊信息）
    uv run python full_workflow.py \
      "downloads/文件.zip"

    # 指定分类和远程子目录
    uv run python full_workflow.py \
      "downloads/文件.zip" \
      --category "E-Hentai/2026" \
      --remote-dir "ehentai/2026"

    # 如有需要，可手动覆盖 JSON 中的画廊链接
    uv run python full_workflow.py \
      "downloads/文件.zip" \
      --gallery-url "https://e-hentai.org/g/3829655/7bc8cc9e4e/"
        """,
    )

    parser.add_argument("source", help="待处理的 .zip 文件路径，或包含多个 .zip 的目录路径")
    parser.add_argument("--gallery-url", help="手动指定 e-hentai 画廊 URL（仅单文件模式可用，默认从同名 JSON 读取）")
    parser.add_argument("--json", help="手动指定 JSON 元数据文件路径（仅单文件模式可用，默认使用同名 JSON）")
    parser.add_argument("--cookie", "-c", help="e-hentai Cookie 字符串")
    parser.add_argument("--cookie-file", default="eht-netscape.cookie", help="Cookie 文件路径（默认：eht-netscape.cookie）")
    parser.add_argument("--proxy", default="http://127.0.0.1:10809", help="HTTP 代理地址")
    parser.add_argument("--output-dir", default="generated_torrents", help="本地 torrent 输出目录")
    parser.add_argument("--output", help="生成的原始 torrent 输出路径（默认自动命名）")
    parser.add_argument("--remote-dir", default="", help="远程子目录（在 SMB 根路径下）")
    parser.add_argument("--category", default="autoEH", help="做种分类（默认：autoEH）")
    parser.add_argument("--comment", default="", help="上传到 e-hentai 时附带的评论")
    return parser.parse_args()


def load_cookie(args: argparse.Namespace) -> str:
    if args.cookie:
        print("使用 Cookie 字符串")
        return args.cookie

    cookie_file = Path(args.cookie_file)
    if not cookie_file.exists():
        raise FileNotFoundError(f"Cookie 文件不存在: {cookie_file}")

    print(f"从文件加载 Cookie: {cookie_file}")
    return load_cookie_from_file(str(cookie_file))


def run_single_workflow(
    source_path: Path,
    json_path: Path,
    gallery_url: str,
    args: argparse.Namespace,
    config: dict[str, str],
    cookie_str: str,
) -> None:
    generated_torrent_path = Path(args.output) if args.output else build_generated_torrent_path(str(source_path), args.output_dir)

    print("=" * 60)
    print("🚀 完整工作流开始")
    print("=" * 60)
    print(f"本地源: {source_path}")
    print(f"元数据: {json_path}")
    print(f"画廊: {gallery_url}")
    print(f"原始种子输出: {generated_torrent_path}")
    print(f"分类: {args.category}")
    print(f"分享率上限: 不限")
    print(f"做种时长上限(分钟): 不限")
    print(f"非活跃做种时长上限(分钟): 不限")

    uploader = EHentaiUploader(cookie_str, proxy=args.proxy)

    print("\n" + "-" * 60)
    print("🔗 步骤 1/4: 获取画廊专属 tracker")
    print("-" * 60)
    tracker_info = uploader.get_tracker_info(gallery_url)
    tracker = str(tracker_info["tracker"])
    title = str(tracker_info["title"])
    personalized_torrent_path = build_personalized_torrent_path(title, args.output_dir)
    invalid_personalized_path = personalized_torrent_path.with_suffix('.invalid.bin')
    if personalized_torrent_path.exists():
        personalized_torrent_path.unlink()
    if invalid_personalized_path.exists():
        invalid_personalized_path.unlink()

    print("\n" + "-" * 60)
    print("📤 步骤 2/4: 上传源文件并生成原始 torrent")
    print("-" * 60)
    remote_smb_path = upload_to_smb(
        local_path_str=str(source_path),
        smb_root=config["SMB_ROOT_PATH"],
        remote_subdir=args.remote_dir,
        username=config.get("SMB_USER", ""),
        password=config.get("SMB_PASS", ""),
    )
    server_source_path = convert_smb_to_server_path(
        smb_path=remote_smb_path,
        smb_root=config["SMB_ROOT_PATH"],
        server_root=config["SERVER_ROOT_PATH"],
    )
    qb_save_path = derive_qb_save_path(server_source_path)
    create_torrent_remote(
        server_source_path=server_source_path,
        local_output_path=str(generated_torrent_path),
        qb_host=config["QB_HOST"],
        qb_port=int(config["QB_PORT"]),
        qb_username=config["QB_USERNAME"],
        qb_password=config["QB_PASSWORD"],
        trackers=[tracker],
        comment=config.get("TORRENT_COMMENT") or "",
    )

    print("\n" + "-" * 60)
    print("📥 步骤 3/4: 上传到 e-hentai 并下载 personalized torrent")
    print("-" * 60)
    upload_success = uploader.upload_torrent(
        gallery_url=gallery_url,
        torrent_path=str(generated_torrent_path),
        comment=args.comment,
        download_personalized=True,
        output_dir=args.output_dir,
    )
    if not upload_success:
        raise RuntimeError("上传到 e-hentai 失败")
    if not personalized_torrent_path.exists():
        raise RuntimeError(f"上传成功，但未找到 personalized torrent: {personalized_torrent_path}")

    print("\n" + "-" * 60)
    print("🌱 步骤 4/4: 使用 personalized torrent 开始做种")
    print("-" * 60)
    seed_success = add_torrent_for_seeding(
        torrent_path=str(personalized_torrent_path),
        save_path=qb_save_path,
        category=args.category,
        config=config,
    )
    if not seed_success:
        raise RuntimeError("添加 personalized torrent 到 qBittorrent 失败")

    print("\n" + "=" * 60)
    print("✅ 完整工作流完成")
    print("=" * 60)
    print(f"原始 torrent: {generated_torrent_path}")
    print(f"personalized torrent: {personalized_torrent_path}")
    print(f"内容路径: {server_source_path}")
    print(f"做种目录: {qb_save_path}")
    print(f"分类: {args.category}")


def print_batch_summary(successes: list[Path], failures: list[tuple[Path, str]]) -> None:
    print("\n" + "=" * 60)
    print("📊 批处理汇总")
    print("=" * 60)
    print(f"成功: {len(successes)}")
    for path in successes:
        print(f"  [OK] {path.name}")

    print(f"失败: {len(failures)}")
    for path, error in failures:
        print(f"  [FAIL] {path.name}: {error}")


def cleanup_processed_source(source_path: Path, json_path: Path) -> None:
    for path in (source_path, json_path):
        if path.exists():
            path.unlink()
            print(f"🧹 已删除: {path}")


def main() -> None:
    args = parse_args()
    source_path = Path(args.source)
    if not source_path.exists():
        raise FileNotFoundError(f"本地路径不存在: {source_path}")

    config = load_config()
    cookie_str = load_cookie(args)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    workflow_sources = collect_workflow_sources(source_path)
    if source_path.is_dir() and args.json:
        raise ValueError("目录批处理模式不支持 --json；请为目录中的每个 .zip 准备同名 .json")
    if source_path.is_dir() and args.gallery_url:
        raise ValueError("目录批处理模式不支持 --gallery-url；请从每个 .zip 的同名 .json 读取 gallery.url")
    if source_path.is_dir() and args.output:
        raise ValueError("目录批处理模式不支持 --output；每个 .zip 会自动生成各自的原始 torrent 文件")

    is_batch_mode = source_path.is_dir()
    successes: list[Path] = []
    failures: list[tuple[Path, str]] = []

    if is_batch_mode:
        print(f"发现目录批处理输入，共 {len(workflow_sources)} 个 .zip，开始逐个处理")

    for index, workflow_source in enumerate(workflow_sources, start=1):
        if is_batch_mode:
            print("\n" + "#" * 60)
            print(f"批处理进度 {index}/{len(workflow_sources)}: {workflow_source.name}")
            print("#" * 60)

        try:
            json_path = Path(args.json) if args.json else find_sidecar_json(workflow_source)
            if not json_path.exists():
                raise FileNotFoundError(f"JSON 元数据文件不存在: {json_path}")
            gallery_url = args.gallery_url or load_gallery_url_from_json(json_path)

            run_single_workflow(
                source_path=workflow_source,
                json_path=json_path,
                gallery_url=gallery_url,
                args=args,
                config=config,
                cookie_str=cookie_str,
            )
            cleanup_processed_source(workflow_source, json_path)
            successes.append(workflow_source)
        except Exception as exc:
            if not is_batch_mode:
                raise
            error_message = str(exc)
            failures.append((workflow_source, error_message))
            print(f"\n❌ 当前文件处理失败，继续下一个: {workflow_source.name}")
            print(f"原因: {error_message}")

    if is_batch_mode:
        print_batch_summary(successes, failures)
        if failures:
            raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\n❌ 错误: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
