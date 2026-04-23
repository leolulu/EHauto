from __future__ import annotations

import io
import json
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import full_workflow


def make_args(source: str, output_dir: str) -> Namespace:
    return Namespace(
        source=source,
        gallery_url=None,
        json=None,
        cookie=None,
        cookie_file="eht-netscape.cookie",
        proxy="http://127.0.0.1:10809",
        output_dir=output_dir,
        output=None,
        remote_dir="",
        category="autoEH",
        comment="",
    )


def write_sidecar(json_path: Path, data: dict[str, object]) -> None:
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class FullWorkflowTests(unittest.TestCase):
    def __init__(self, methodName: str = "runTest") -> None:
        super().__init__(methodName)
        self.temp_dir: tempfile.TemporaryDirectory[str] | None = None
        self.root = Path(".")
        self.output_dir = Path(".")
        self.config: dict[str, str] = {}

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.output_dir = self.root / "generated_torrents"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.config = {
            "SMB_ROOT_PATH": "//server/share",
            "SERVER_ROOT_PATH": "/srv/data",
            "QB_HOST": "127.0.0.1",
            "QB_PORT": "8080",
            "QB_USERNAME": "admin",
            "QB_PASSWORD": "password",
        }

    def tearDown(self) -> None:
        if self.temp_dir is not None:
            self.temp_dir.cleanup()

    def create_zip_and_json(self, base_name: str, data: dict[str, object] | None = None) -> tuple[Path, Path]:
        zip_path = self.root / f"{base_name}.zip"
        json_path = self.root / f"{base_name}.json"
        zip_path.write_bytes(b"zip-bytes")
        write_sidecar(
            json_path,
            data
            or {
                "gallery": {"url": "https://e-hentai.org/g/1/token/"},
                "download": {"saved_path": str(zip_path)},
            },
        )
        return zip_path, json_path

    def patch_workflow_dependencies(
        self,
        upload_result: tuple[bool, bool, str | None],
        *,
        last_upload_error: str | None = None,
        last_upload_completed: bool = False,
        upload_side_effect: Exception | None = None,
    ):
        uploader_patch = patch("full_workflow.EHentaiUploader")
        upload_to_smb_patch = patch("full_workflow.upload_to_smb", return_value="//server/share/example.zip")
        convert_patch = patch("full_workflow.convert_smb_to_server_path", return_value="/srv/data/example.zip")
        save_path_patch = patch("full_workflow.derive_qb_save_path", return_value="/srv/data")
        create_torrent_patch = patch("full_workflow.create_torrent_remote", return_value=b"torrent-bytes")
        seed_patch = patch("full_workflow.add_torrent_for_seeding", return_value=True)

        uploader_cls = uploader_patch.start()
        mock_uploader = uploader_cls.return_value
        mock_uploader.get_tracker_info.return_value = {
            "tracker": "http://ehtracker.org/1/announce",
            "title": "Example Gallery",
        }
        if upload_side_effect is not None:
            mock_uploader.upload_torrent.side_effect = upload_side_effect
        else:
            mock_uploader.upload_torrent.return_value = upload_result
        mock_uploader.last_upload_error = last_upload_error
        mock_uploader.last_upload_completed = last_upload_completed

        upload_to_smb_patch.start()
        convert_patch.start()
        save_path_patch.start()
        create_torrent_patch.start()
        seed_patch.start()
        self.addCleanup(uploader_patch.stop)
        self.addCleanup(upload_to_smb_patch.stop)
        self.addCleanup(convert_patch.stop)
        self.addCleanup(save_path_patch.stop)
        self.addCleanup(create_torrent_patch.stop)
        self.addCleanup(seed_patch.stop)
        return mock_uploader

    def test_first_ordinary_publish_failure_creates_workflow_metadata(self) -> None:
        _, json_path = self.create_zip_and_json("first-failure")

        updated_count = full_workflow.increment_ordinary_publish_failure(json_path, "上传到 e-hentai 失败")

        self.assertEqual(updated_count, 1)
        data = full_workflow.read_sidecar_json(json_path)
        self.assertEqual(data["workflow"]["publish_failure"]["count"], 1)
        self.assertEqual(data["workflow"]["publish_failure"]["latest_error"], "上传到 e-hentai 失败")
        self.assertIn("latest_timestamp", data["workflow"]["publish_failure"])

    def test_repeated_ordinary_publish_failure_increments_count_within_limit(self) -> None:
        zip_path, json_path = self.create_zip_and_json(
            "ordinary-failure",
            {
                "gallery": {"url": "https://e-hentai.org/g/2/token/"},
                "download": {"saved_path": "C:/downloads/ordinary-failure.zip"},
                "workflow": {
                    "publish_failure": {
                        "count": 1,
                        "latest_error": "旧错误",
                        "latest_timestamp": "2026-04-22T10:00:00+08:00",
                    }
                },
            },
        )
        self.patch_workflow_dependencies(
            (False, False, None),
            last_upload_error="真实上传失败原因",
            last_upload_completed=False,
        )

        with self.assertRaisesRegex(RuntimeError, "真实上传失败原因"):
            full_workflow.run_single_workflow(
                source_path=zip_path,
                json_path=json_path,
                gallery_url="https://e-hentai.org/g/2/token/",
                args=make_args(str(zip_path), str(self.output_dir)),
                config=self.config,
                cookie_str="cookie",
                enable_failure_retirement=True,
            )

        data = full_workflow.read_sidecar_json(json_path)
        self.assertEqual(data["workflow"]["publish_failure"]["count"], 2)
        self.assertEqual(data["workflow"]["publish_failure"]["latest_error"], "真实上传失败原因")
        self.assertTrue(zip_path.exists())
        self.assertTrue(json_path.exists())

    def test_failure_count_above_limit_deletes_zip_and_json_and_retires_item(self) -> None:
        zip_path, json_path = self.create_zip_and_json(
            "over-limit",
            {
                "gallery": {"url": "https://e-hentai.org/g/3/token/"},
                "download": {"saved_path": "C:/downloads/over-limit.zip"},
                "workflow": {
                    "publish_failure": {
                        "count": full_workflow.ORDINARY_PUBLISH_FAILURE_LIMIT,
                        "latest_error": "旧错误",
                        "latest_timestamp": "2026-04-22T10:00:00+08:00",
                    }
                },
            },
        )
        self.patch_workflow_dependencies((False, False, None))

        with self.assertRaises(full_workflow.TerminalRetirementError) as ctx:
            full_workflow.run_single_workflow(
                source_path=zip_path,
                json_path=json_path,
                gallery_url="https://e-hentai.org/g/3/token/",
                args=make_args(str(zip_path), str(self.output_dir)),
                config=self.config,
                cookie_str="cookie",
                enable_failure_retirement=True,
            )

        self.assertEqual(ctx.exception.reason, "publish_failure_limit")
        self.assertFalse(zip_path.exists())
        self.assertFalse(json_path.exists())

    def test_replaced_gallery_retires_without_incrementing_publish_failure(self) -> None:
        zip_path, json_path = self.create_zip_and_json("replaced-gallery")
        self.patch_workflow_dependencies((False, True, "https://e-hentai.org/g/new/token/"))

        with patch("full_workflow.increment_ordinary_publish_failure") as increment_mock:
            with self.assertRaises(full_workflow.TerminalRetirementError) as ctx:
                full_workflow.run_single_workflow(
                    source_path=zip_path,
                    json_path=json_path,
                    gallery_url="https://e-hentai.org/g/4/token/",
                    args=make_args(str(zip_path), str(self.output_dir)),
                    config=self.config,
                    cookie_str="cookie",
                    enable_failure_retirement=True,
                )

        self.assertEqual(ctx.exception.reason, "replaced_gallery")
        increment_mock.assert_not_called()
        self.assertFalse(zip_path.exists())
        self.assertFalse(json_path.exists())

    def test_upload_success_but_personalized_download_failure_does_not_increment_publish_failure(self) -> None:
        zip_path, json_path = self.create_zip_and_json("download-failure")
        self.patch_workflow_dependencies(
            (False, False, None),
            last_upload_error="上传成功，但下载专属种子失败",
            last_upload_completed=True,
        )

        with patch("full_workflow.increment_ordinary_publish_failure") as increment_mock:
            with self.assertRaisesRegex(RuntimeError, "上传成功，但下载专属种子失败"):
                full_workflow.run_single_workflow(
                    source_path=zip_path,
                    json_path=json_path,
                    gallery_url="https://e-hentai.org/g/5/token/",
                    args=make_args(str(zip_path), str(self.output_dir)),
                    config=self.config,
                    cookie_str="cookie",
                    enable_failure_retirement=True,
                )

        increment_mock.assert_not_called()
        self.assertTrue(zip_path.exists())
        self.assertTrue(json_path.exists())

    def test_upload_success_but_personalized_download_exception_does_not_increment_publish_failure(self) -> None:
        zip_path, json_path = self.create_zip_and_json("download-exception")
        self.patch_workflow_dependencies(
            (False, False, None),
            last_upload_error="上传成功，但下载专属种子失败",
            last_upload_completed=True,
            upload_side_effect=RuntimeError("下载专属种子阶段异常"),
        )

        with patch("full_workflow.increment_ordinary_publish_failure") as increment_mock:
            with self.assertRaisesRegex(RuntimeError, "上传成功，但下载专属种子失败"):
                full_workflow.run_single_workflow(
                    source_path=zip_path,
                    json_path=json_path,
                    gallery_url="https://e-hentai.org/g/5b/token/",
                    args=make_args(str(zip_path), str(self.output_dir)),
                    config=self.config,
                    cookie_str="cookie",
                    enable_failure_retirement=True,
                )

        increment_mock.assert_not_called()
        self.assertTrue(zip_path.exists())
        self.assertTrue(json_path.exists())

    def test_single_file_ordinary_publish_failure_does_not_consume_retry_budget(self) -> None:
        zip_path, json_path = self.create_zip_and_json("single-file-failure")
        self.patch_workflow_dependencies(
            (False, False, None),
            last_upload_error="真实上传失败原因",
            last_upload_completed=False,
        )

        with patch("full_workflow.increment_ordinary_publish_failure") as increment_mock:
            with self.assertRaisesRegex(RuntimeError, "真实上传失败原因"):
                full_workflow.run_single_workflow(
                    source_path=zip_path,
                    json_path=json_path,
                    gallery_url="https://e-hentai.org/g/6/token/",
                    args=make_args(str(zip_path), str(self.output_dir)),
                    config=self.config,
                    cookie_str="cookie",
                    enable_failure_retirement=False,
                )

        increment_mock.assert_not_called()
        self.assertTrue(zip_path.exists())
        self.assertTrue(json_path.exists())

    def test_batch_exit_zero_when_only_successes_and_retired_items(self) -> None:
        zip_path_a, _ = self.create_zip_and_json("success-item")
        zip_path_b, _ = self.create_zip_and_json("retired-item")
        args = make_args(str(self.root), str(self.output_dir))

        stdout = io.StringIO()
        with patch("full_workflow.parse_args", return_value=args), \
             patch("full_workflow.load_config", return_value=self.config), \
             patch("full_workflow.load_cookie", return_value="cookie"), \
             patch("full_workflow.collect_workflow_sources", return_value=[zip_path_a, zip_path_b]), \
             patch(
                 "full_workflow.run_single_workflow",
                 side_effect=[
                     None,
                     full_workflow.TerminalRetirementError(
                         "发布失败次数超过阈值 3，源文件已清理。",
                         reason="publish_failure_limit",
                     ),
                 ],
             ), \
             redirect_stdout(stdout):
            full_workflow.main()

        output = stdout.getvalue()
        self.assertIn("成功: 1", output)
        self.assertIn("未解决失败: 0", output)
        self.assertIn("已终局清理: 1", output)
        self.assertFalse(zip_path_a.exists())
        self.assertTrue(zip_path_b.exists())

    def test_batch_exit_nonzero_when_unresolved_failures_exist(self) -> None:
        self.create_zip_and_json("success-item")
        self.create_zip_and_json("failure-item")
        args = make_args(str(self.root), str(self.output_dir))

        stdout = io.StringIO()
        with patch("full_workflow.parse_args", return_value=args), \
             patch("full_workflow.load_config", return_value=self.config), \
             patch("full_workflow.load_cookie", return_value="cookie"), \
             patch(
                 "full_workflow.collect_workflow_sources",
                 return_value=[self.root / "success-item.zip", self.root / "failure-item.zip"],
             ), \
             patch(
                 "full_workflow.run_single_workflow",
                 side_effect=[
                     None,
                     RuntimeError("上传到 e-hentai 失败"),
                 ],
             ), \
             redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as ctx:
                full_workflow.main()

        output = stdout.getvalue()
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("成功: 1", output)
        self.assertIn("未解决失败: 1", output)
        self.assertIn("已终局清理: 0", output)


if __name__ == "__main__":
    unittest.main()
