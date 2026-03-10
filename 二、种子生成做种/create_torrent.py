#!/usr/bin/env python3
"""
qBittorrent 远程生成种子脚本（完整版：上传 + 生成 + 下载）

配置说明：
  只需配置一对路径映射：
    SMB_ROOT_PATH（本地访问的 SMB 根路径）↔ SERVER_ROOT_PATH（服务器绝对路径）

工作流程：
  1. 将本地文件/目录上传到 SMB（保持相对目录结构）
  2. 自动转换为服务器绝对路径
  3. 调用远程 qBittorrent API 生成种子
  4. 下载种子到本地

依赖安装：
    uv sync

使用示例：
    # 单个文件
    uv run python create_torrent.py --file "C:/Users/YXY/Videos/movie.mkv" --output "movie.torrent"
    
    # 目录（自动递归上传）
    uv run python create_torrent.py --dir "C:/Users/YXY/Videos/合集" --output "合集.torrent"
    
    # 指定远程子目录
    uv run python create_torrent.py --file movie.mkv --output movie.torrent --remote-dir "movies/2024"
"""

import os
import sys
import shutil
import argparse
from pathlib import Path, PureWindowsPath

from dotenv import dotenv_values
from qbittorrentapi import Client, TaskStatus


def parse_smb_path(smb_path: str) -> tuple[str, str, str]:
    """
    解析 SMB 路径
    
    输入: //192.168.1.100/share/movies 或 \\\\192.168.1.100\\share\\movies (Windows)
    返回: (server, share, base_path)
          ("192.168.1.100", "share", "movies")
    """
    # 统一为斜杠格式
    path = smb_path.replace('\\', '/')
    
    # 移除开头的 //
    if path.startswith('//'):
        path = path[2:]
    
    parts = path.split('/')
    server = parts[0]
    share = parts[1] if len(parts) > 1 else ""
    base_path = '/'.join(parts[2:]) if len(parts) > 2 else ""
    
    return server, share, base_path


def upload_to_smb(
    local_path_str: str,
    smb_root: str,
    remote_subdir: str = "",
    username: str = "",
    password: str = ""
) -> str:
    """
    上传本地文件或目录到 SMB 服务器（使用 Windows UNC 路径，依赖资源管理器已登录）
    
    Args:
        local_path_str: 本地文件或目录路径
        smb_root: SMB 根路径，例如 "//192.168.1.100/share" 或 "\\\\192.168.1.100\\share"
        remote_subdir: 远程子目录（在 smb_root 之下）
        username: SMB 用户名（未使用，保留参数兼容性）
        password: SMB 密码（未使用，保留参数兼容性）
    
    Returns:
        上传后的远程 SMB 完整路径（含子目录）
    """
    local_path = Path(local_path_str)
    if not local_path.exists():
        raise FileNotFoundError(f"本地路径不存在: {local_path}")
    
    # 解析 SMB 路径
    server, share, base_path = parse_smb_path(smb_root)
    
    # 构建目标相对路径
    if remote_subdir:
        target_relative = f"{remote_subdir}/{local_path.name}".strip('/')
    else:
        target_relative = local_path.name
    
    # 构建完整远程路径
    if base_path:
        full_remote_path = f"{base_path}/{target_relative}".strip('/')
    else:
        full_remote_path = target_relative
    
    # 构建 UNC 路径 (Windows 格式: \\server\share\path)
    unc_path = f"\\\\{server}\\{share}"
    if base_path:
        base_path_windows = base_path.replace('/', '\\')
        unc_path += f"\\{base_path_windows}"
    if remote_subdir:
        remote_subdir_windows = remote_subdir.replace('/', '\\')
        unc_path += f"\\{remote_subdir_windows}"
    
    # 用于返回的路径格式 (URI 格式)
    remote_smb_result = f"//{server}/{share}/{full_remote_path}"
    
    print(f"\n📤 开始上传...")
    print(f"  本地: {local_path_str}")
    print(f"  远程: {remote_smb_result}")
    print(f"  UNC: {unc_path}")
    
    # 确保远程目录存在
    os.makedirs(unc_path, exist_ok=True)
    
    # 上传
    if local_path.is_file():
        _upload_single_file_unc(local_path, unc_path)
    else:
        _upload_directory_unc(local_path, unc_path)
    
    print(f"✓ 上传完成")
    return remote_smb_result


def _upload_single_file_unc(local_file: Path, unc_dir: str):
    """通过 UNC 路径上传单个文件"""
    dest_path = os.path.join(unc_dir, local_file.name)
    shutil.copy2(local_file, dest_path)
    size = local_file.stat().st_size
    remote_size = Path(dest_path).stat().st_size
    if remote_size != size:
        raise IOError(f"上传后大小不一致: {local_file} ({size}) -> {dest_path} ({remote_size})")
    print(f"  ✓ {local_file.name} ({size:,} bytes)")


def _upload_directory_unc(local_dir: Path, unc_base: str):
    """递归上传目录（通过 UNC 路径）"""
    files = [f for f in local_dir.rglob('*') if f.is_file()]
    total = len(files)
    
    print(f"  发现 {total} 个文件，开始上传...")
    
    for i, local_file in enumerate(files, 1):
        # 计算相对路径
        relative = local_file.relative_to(local_dir)
        relative_str = str(relative).replace('/', '\\')
        
        # 构建目标 UNC 路径
        dest_dir = os.path.join(unc_base, os.path.dirname(relative_str))
        os.makedirs(dest_dir, exist_ok=True)
        
        # 复制文件
        dest_path = os.path.join(dest_dir, local_file.name)
        shutil.copy2(local_file, dest_path)
        local_size = local_file.stat().st_size
        remote_size = Path(dest_path).stat().st_size
        if remote_size != local_size:
            raise IOError(f"上传后大小不一致: {local_file} ({local_size}) -> {dest_path} ({remote_size})")
        
        print(f"  [{i}/{total}] {relative}")
    
    print(f"✓ 共上传 {total} 个文件")


def convert_smb_to_server_path(smb_path: str, smb_root: str, server_root: str) -> str:
    """
    将 SMB 路径转换为服务器绝对路径
    
    示例:
        smb_path:     "//192.168.1.100/share/movies/2024/file.mkv"
        smb_root:     "//192.168.1.100/share"
        server_root:  "/home/user/data"
        
        → "/home/user/data/movies/2024/file.mkv"
    """
    # 统一格式
    smb_path_norm = smb_path.replace('\\', '/')
    smb_root_norm = smb_root.replace('\\', '/')
    
    # 移除开头的 //
    if smb_path_norm.startswith('//'):
        smb_path_norm = smb_path_norm[2:]
    if smb_root_norm.startswith('//'):
        smb_root_norm = smb_root_norm[2:]
    
    # 计算相对路径
    if smb_path_norm.startswith(smb_root_norm):
        relative = smb_path_norm[len(smb_root_norm):].lstrip('/')
    else:
        raise ValueError(f"路径 {smb_path} 不在 SMB 根路径 {smb_root} 之下")
    
    # 拼接服务器路径
    server_path = f"{server_root.rstrip('/')}/{relative}"
    return server_path


def create_torrent_remote(
    server_source_path: str,
    local_output_path: str,
    qb_host: str,
    qb_port: int,
    qb_username: str,
    qb_password: str,
    trackers: list[str] | None = None,
    comment: str | None = None
) -> bytes:
    """
    调用远程 qBittorrent 生成种子并下载到本地
    """
    import time

    print(f"\n🌐 连接远程 qBittorrent ({qb_host}:{qb_port})...")
    client = Client(
        host=f"{qb_host}:{qb_port}",
        username=qb_username,
        password=qb_password
    )
    
    try:
        client.auth_log_in()
        print(f"✓ 已连接，版本: {client.app.version}")
    except Exception as e:
        raise ConnectionError(f"连接失败: {e}")
    
    # 服务器上临时种子输出路径
    server_output_path = str(Path(server_source_path).with_suffix('.torrent'))
    
    print(f"\n⚙️  开始生成种子...")
    print(f"  源: {server_source_path}")
    
    task = client.torrentcreator_add_task(
        source_path=server_source_path,
        torrent_file_path=server_output_path,
        start_seeding=False,
        trackers=trackers or [],
        comment=comment or ""
    )
    
    print(f"  任务ID: {task.taskID}")
    
    # 等待完成
    print("\n⏳ 生成中...")
    while True:
        status = task.status()
        state = TaskStatus(status.status)
        
        if state.name == "FINISHED":
            print("✅ 生成完成!")
            break
        elif state.name == "FAILED":
            error_msg = getattr(status, 'error', '未知错误')
            task.delete()
            raise RuntimeError(f"生成失败: {error_msg}")
        elif state.name == "RUNNING":
            progress = getattr(status, 'progress', 0)
            print(f"  进度: {progress}%")
        elif state.name == "QUEUED":
            print("  排队中...")
        
        time.sleep(1)
    
    # 下载种子
    print("\n📥 下载种子文件...")
    torrent_data = task.torrent_file()
    
    # 保存到本地
    output_dir = os.path.dirname(os.path.abspath(local_output_path))
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    
    with open(local_output_path, "wb") as f:
        f.write(torrent_data)
    print(f"✓ 已保存: {local_output_path}")
    
    # 清理
    task.delete()
    print("✓ 任务已清理")
    
    return torrent_data
def main():
    parser = argparse.ArgumentParser(
        description='上传文件到远程 SMB 并通过 qBittorrent 生成种子',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('--file', '-f', help='本地文件路径')
    parser.add_argument('--dir', '-d', help='本地目录路径（递归上传）')
    parser.add_argument('--output', '-o', required=True, help='输出种子文件路径（本地）')
    parser.add_argument('--remote-dir', '-r', default='', 
                       help='远程子目录（在 SMB 根路径下），如: movies/2024')
    parser.add_argument('--smb-user', default='', help='SMB 用户名')
    parser.add_argument('--smb-pass', default='', help='SMB 密码')
    parser.add_argument('--tracker', '-t', action='append', help='添加 Tracker（可多次使用，如: -t url1 -t url2）')
    parser.add_argument('--trackers-file', help='从文件读取 Tracker 列表（每行一个）')
    
    args = parser.parse_args()
    
    if not args.file and not args.dir:
        parser.error("请指定 --file 或 --dir")
    
    local_source = args.file or args.dir
    
    # ============ 核心配置（从 .env 文件读取，环境变量不生效） ============
    # 使用说明：
    #   1. 复制 .env.example 为 .env
    #   2. 编辑 .env 填入你的实际配置
    #   3. 脚本只从 .env 文件读取配置
    
    ENV_FILE = Path(".env")
    
    if not ENV_FILE.exists():
        print("❌ 错误：找不到 .env 配置文件", file=sys.stderr)
        print("\n请按以下步骤操作：", file=sys.stderr)
        print("  1. 复制模板文件：cp .env.example .env", file=sys.stderr)
        print("  2. 编辑 .env 文件，填入你的实际配置", file=sys.stderr)
        print("  3. 重新运行脚本", file=sys.stderr)
        sys.exit(1)
    
    # 读取 .env 文件
    config = dotenv_values(ENV_FILE)
    
    # 定义必需配置项及其说明
    REQUIRED_CONFIG = {
        "SMB_ROOT_PATH": "SMB 根路径（本地访问方式）",
        "SERVER_ROOT_PATH": "服务器绝对路径（qBittorrent 所在服务器的路径）",
        "QB_HOST": "qBittorrent 服务器 IP 或域名",
        "QB_PORT": "qBittorrent Web UI 端口",
        "QB_USERNAME": "qBittorrent 登录用户名",
        "QB_PASSWORD": "qBittorrent 登录密码",
    }
    
    # 检查必需配置
    missing = []
    for key, desc in REQUIRED_CONFIG.items():
        if not config.get(key) or config.get(key) == "你的密码":
            missing.append(f"  - {key}: {desc}")
    
    if missing:
        print("❌ 错误：.env 文件缺少以下必需配置项：\n", file=sys.stderr)
        for item in missing:
            print(item, file=sys.stderr)
        print("\n请编辑 .env 文件补全以上配置后重新运行。", file=sys.stderr)
        sys.exit(1)
    
    # 读取配置
    SMB_ROOT_PATH = str(config["SMB_ROOT_PATH"])
    SERVER_ROOT_PATH = str(config["SERVER_ROOT_PATH"])
    SMB_USER = config.get("SMB_USER", "") or args.smb_user
    SMB_PASS = config.get("SMB_PASS", "") or args.smb_pass
    QB_HOST = str(config["QB_HOST"])
    QB_PORT = int(str(config["QB_PORT"]))
    QB_USERNAME = str(config["QB_USERNAME"])
    QB_PASSWORD = str(config["QB_PASSWORD"])
    
    # Tracker 列表（可选）
    TRACKERS = []
    
    # 从 .env 读取 tracker（逗号分隔）
    env_trackers = config.get("TRACKERS", "")
    if env_trackers:
        TRACKERS.extend([t.strip() for t in env_trackers.split(",") if t.strip()])
    
    # 从命令行参数添加 tracker
    if args.tracker:
        TRACKERS.extend(args.tracker)
    
    # 从文件读取 tracker
    if args.trackers_file:
        try:
            with open(args.trackers_file, 'r', encoding='utf-8') as f:
                file_trackers = [line.strip() for line in f if line.strip() and not line.startswith('#')]
                TRACKERS.extend(file_trackers)
                print(f"从文件加载 {len(file_trackers)} 个 tracker")
        except Exception as e:
            print(f"警告: 读取 tracker 文件失败: {e}")
    
    COMMENT = config.get("TORRENT_COMMENT", "Created by auto torrent workflow")
    
    # =============================================
    
    print("=" * 60)
    print("🚀 qBittorrent 远程生成种子")
    print("=" * 60)
    print(f"本地源: {local_source}")
    print(f"输出到: {args.output}")
    if TRACKERS:
        print(f"Tracker: {len(TRACKERS)} 个")
    print(f"\n路径映射:")
    print(f"  SMB:    {SMB_ROOT_PATH}")
    print(f"  Server: {SERVER_ROOT_PATH}")
    
    try:
        # 1. 上传到 SMB
        print("\n" + "-" * 60)
        print("📤 步骤 1/3: 上传到 SMB")
        print("-" * 60)
        
        remote_smb_path = upload_to_smb(
            local_path_str=local_source,
            smb_root=SMB_ROOT_PATH,
            remote_subdir=args.remote_dir,
            username=SMB_USER,
            password=SMB_PASS
        )
        
        # 2. 路径转换
        print("\n" + "-" * 60)
        print("🔄 步骤 2/3: 路径转换")
        print("-" * 60)
        print(f"SMB 路径: {remote_smb_path}")
        
        server_source_path = convert_smb_to_server_path(
            smb_path=remote_smb_path,
            smb_root=SMB_ROOT_PATH,
            server_root=SERVER_ROOT_PATH
        )
        print(f"服务器路径: {server_source_path}")
        
        # 3. 生成种子
        print("\n" + "-" * 60)
        print("⚙️  步骤 3/3: 生成种子")
        print("-" * 60)
        
        torrent_data = create_torrent_remote(
            server_source_path=server_source_path,
            local_output_path=args.output,
            qb_host=QB_HOST,
            qb_port=QB_PORT,
            qb_username=QB_USERNAME,
            qb_password=QB_PASSWORD,
            trackers=TRACKERS,
            comment=COMMENT
        )
        
        print("\n" + "=" * 60)
        print("✅ 完成!")
        print("=" * 60)
        print(f"种子文件: {args.output}")
        print(f"大小: {len(torrent_data)} bytes")
        
    except Exception as e:
        print(f"\n❌ 错误: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
