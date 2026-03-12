#!/usr/bin/env python3
"""
使用个人专属种子开始做种

功能：
  1. 读取 personalized torrent 文件
  2. 自动推断远程服务器上的文件路径
  3. 添加到 qBittorrent 做种（跳过哈希检查）
  4. 支持设置分类

使用示例：
    # 基本用法（自动推断目录和分类）
    uv run python seed_personalized.py "generated_torrents/文件_personalized.torrent"
    
    # 指定分类
    uv run python seed_personalized.py "generated_torrents/文件_personalized.torrent" --category "E-Hentai"
    
    # 指定服务器路径（覆盖自动推断）
    uv run python seed_personalized.py "generated_torrents/文件_personalized.torrent" --save-path "/mnt/data/files"
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath

import bencodepy
from dotenv import dotenv_values
from qbittorrentapi import Client


def load_config() -> dict[str, str]:
    """从 .env 文件加载配置"""
    env_file = Path(".env")
    
    if not env_file.exists():
        print("❌ 错误：找不到 .env 配置文件", file=sys.stderr)
        print("\n请复制 .env.example 为 .env 并填写配置", file=sys.stderr)
        sys.exit(1)
    
    raw_config = dotenv_values(env_file)
    
    # 检查必需配置
    required = ["QB_HOST", "QB_PORT", "QB_USERNAME", "QB_PASSWORD", "SERVER_ROOT_PATH"]
    missing = [k for k in required if not raw_config.get(k)]
    
    if missing:
        print(f"❌ 错误：.env 缺少配置项: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)
    
    return {key: str(value) for key, value in raw_config.items() if value is not None}


def infer_save_path(torrent_path: str, config: dict[str, str], json_metadata: str | None = None) -> str:
    """
    推断远程服务器上的文件路径
    
    策略：
    1. 如果有 JSON 元数据，从里面读取上传路径
    2. 否则基于种子文件名和 SERVER_ROOT_PATH 推断
    """
    server_root = config.get("SERVER_ROOT_PATH", "")
    
    # 尝试从 JSON 读取
    if json_metadata and Path(json_metadata).exists():
        try:
            with open(json_metadata, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 从下载记录中获取文件名
                saved_path = data.get('download', {}).get('saved_path', '')
                if saved_path:
                    # 提取文件名
                    filename = Path(saved_path).name
                    # 构建服务器路径
                    return f"{server_root}/{filename}".replace('//', '/')
        except Exception as e:
            print(f"⚠️ 读取 JSON 元数据失败: {e}")
    
    # 从种子文件名推断
    torrent_name = Path(torrent_path).stem  # 去掉 .torrent
    
    # 去掉 _personalized 后缀
    if torrent_name.endswith("_personalized"):
        base_name = torrent_name[:-13]  # 移除 "_personalized"
    else:
        base_name = torrent_name
    
    # 构建服务器路径
    save_path = f"{server_root}/{base_name}".replace('//', '/')
    
    return save_path


def derive_qb_save_path(content_path: str) -> str:
    """将内容路径转换为 qBittorrent 需要的保存目录。"""
    path_cls = PureWindowsPath if (":" in content_path or "\\" in content_path) else PurePosixPath
    return str(path_cls(content_path).parent)


def calculate_torrent_infohash(torrent_path: str) -> str:
    data = Path(torrent_path).read_bytes()
    decoded = bencodepy.decode(data)
    info = decoded[b'info']
    return hashlib.sha1(bencodepy.encode(info)).hexdigest()


def add_torrent_for_seeding(
    torrent_path: str,
    save_path: str,
    category: str,
    config: dict[str, str],
) -> bool:
    """
    添加种子到 qBittorrent 做种
    """
    qb_host = config.get("QB_HOST")
    qb_port = config.get("QB_PORT")
    qb_username = config.get("QB_USERNAME")
    qb_password = config.get("QB_PASSWORD")
    
    print(f"\n🔌 连接 qBittorrent ({qb_host}:{qb_port})...")
    client = Client(
        host=f"{qb_host}:{qb_port}",
        username=qb_username,
        password=qb_password
    )
    
    try:
        client.auth_log_in()
        print(f"✅ 已连接，版本: {client.app.version}")
    except Exception as e:
        raise ConnectionError(f"连接失败: {e}")
    
    # 读取种子文件
    print(f"\nℹ️ 读取种子: {torrent_path}")
    with open(torrent_path, 'rb') as f:
        torrent_data = f.read()

    print(f"  大小: {len(torrent_data):,} bytes")
    print(f"  做种目录: {save_path}")
    if category:
        print(f"  分类: {category}")
    
    # 添加到 qBittorrent
    print("\n➕ 添加种子...")
    print("  [跳过哈希检查] 直接做种")
    print("  [Torrent 管理模式] 手动")
    print("  [内容布局] Original")
    print("  [分享率上限] 不限")
    print("  [做种时长上限(分钟)] 不限")
    print("  [非活跃做种时长上限(分钟)] 不限")
    torrent_hash = calculate_torrent_infohash(torrent_path)
    print(f"  [Torrent Hash] {torrent_hash}")
    
    try:
        torrent_name = Path(torrent_path).name
        with open(torrent_path, 'rb') as torrent_file:
            result = client.torrents_add(
                torrent_files={torrent_name: torrent_file},
                save_path=save_path,
                category=category,
                is_skip_checking=True,  # 关键：跳过哈希检查，直接做种
                is_paused=False,         # 立即开始
                use_auto_torrent_management=False,  # 手动模式，允许显式控制保存位置
                content_layout="Original",         # 保持原始布局，不创建额外子文件夹
                ratio_limit=-1,                    # 不限分享率
                seeding_time_limit=-1,            # 不限做种时长
                inactive_seeding_time_limit=-1,   # 不限非活跃时长
            )
        
        if isinstance(result, str):
            normalized = result.strip().lower()
            success = normalized in {"ok", "ok."}
        else:
            success = bool(result)

        if success:
            print("✅ 添加成功！已开始做种")
            return True
        else:
            existing = client.torrents_info(torrent_hashes=torrent_hash)
            if existing:
                print("ℹ️ 该 torrent 已存在于 qBittorrent，中断重复添加并视为成功")
                return True
            print(f"⚠️ 添加结果: {result}")
            return False
            
    except Exception as e:
        print(f"❌ 添加失败: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='使用个人专属种子开始做种',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    # 基本用法（自动推断目录）
    uv run python seed_personalized.py "generated_torrents/文件_personalized.torrent"
    
    # 指定分类
    uv run python seed_personalized.py "generated_torrents/文件_personalized.torrent" -c "E-Hentai"
    
    # 使用 JSON 元数据精确推断路径
    uv run python seed_personalized.py "generated_torrents/文件_personalized.torrent" -j "downloads/文件.json"
        """
    )
    
    parser.add_argument('torrent', help='personalized torrent 文件路径')
    parser.add_argument('-c', '--category', default='autoEH', help='分类名称（默认：autoEH）')
    parser.add_argument('-s', '--save-path', help='做种保存目录/父目录（覆盖自动推断）')
    parser.add_argument('-j', '--json', help='JSON 元数据文件（用于精确推断路径）')
    
    args = parser.parse_args()
    
    # 检查种子文件
    torrent_path = Path(args.torrent)
    if not torrent_path.exists():
        print(f"❌ 错误：找不到种子文件: {torrent_path}", file=sys.stderr)
        sys.exit(1)
    
    # 检查是否是 personalized 版本
    if "_personalized" not in torrent_path.name:
        print("⚠️ 警告：建议上传 personalized 版本（包含专属 tracker）", file=sys.stderr)
        response = input("是否继续？(y/N): ")
        if response.lower() != 'y':
            sys.exit(0)
    
    # 加载配置
    print("ℹ️ 加载配置...")
    config = load_config()
    
    # 推断或获取保存路径
    if args.save_path:
        save_path = args.save_path
        print(f"✅ 使用指定路径: {save_path}")
    else:
        content_path = infer_save_path(str(torrent_path), config, args.json)
        save_path = derive_qb_save_path(content_path)
        print(f"✅ 自动推断内容路径: {content_path}")
        print(f"✅ 转换后的做种目录: {save_path}")
    
    # 添加种子
    try:
        success = add_torrent_for_seeding(
            str(torrent_path),
            save_path,
            args.category,
            config,
        )
        
        if success:
            print("\n" + "=" * 60)
            print("✅ 做种任务已启动")
            print("=" * 60)
            print(f"种子: {torrent_path}")
            print(f"目录: {save_path}")
            print(f"分类: {args.category}")
            sys.exit(0)
        else:
            sys.exit(1)
            
    except Exception as e:
        print(f"\n❌ 错误: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
