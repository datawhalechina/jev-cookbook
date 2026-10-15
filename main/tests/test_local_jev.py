"""Laya lifecycle and Notebook connection tests; no external model downloads."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "LocalJev"))
sys.path.insert(0, str(ROOT / "generators"))
import local_jev_runtime as runtime
from use_local_jev import activate
from local_jev_support import LOCAL_SETUP, connect_local_service


def checkpoint(root):
    import numpy as np
    from safetensors.numpy import save_file
    for name in ["rl_agent_config.json", "encoder/config.json", "tokenizer/tokenizer.json",
                 "tokenizer/tokenizer_config.json"]:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"test": true}', encoding="utf-8")
    save_file({"test": np.zeros((2,), dtype=np.float32)}, str(root / "model.safetensors"))


class LocalModelTests(unittest.TestCase):
    def test_chapter_connection_finds_relocated_helper_and_shared_config(self):
        import shutil
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as directory:
            main = Path(directory) / "main"
            local = main / "LocalJev"
            local.mkdir(parents=True)
            chapter = main / "chapter"
            chapter.mkdir()
            shutil.copy2(ROOT / "LocalJev" / "use_local_jev.py", local / "use_local_jev.py")
            config = {"base_url": "http://127.0.0.1:8001", "model": "local-test", "api_key": "test"}
            (main / ".local-jev.json").write_text(json.dumps(config), encoding="utf-8")
            response = Mock()
            response.json.return_value = {"status": "ok", "loaded": ["local-test"], "device": "cpu"}
            for cwd in (main, chapter, local):
                with self.subTest(cwd=cwd), patch("pathlib.Path.cwd", return_value=cwd), patch(
                        "requests.get", return_value=response), patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(io.StringIO()):
                    exec(LOCAL_SETUP, {})
                    self.assertEqual(os.environ["TYPESAFE_BASE_URL"], config["base_url"])
                    self.assertEqual(os.environ["TYPESAFE_DEFAULT_MODEL"], config["model"])

    def test_missing_experimental_service_is_reported_before_package_checks(self):
        with patch("pathlib.Path.is_file", return_value=False), patch("importlib.util.find_spec") as probe:
            with self.assertRaisesRegex(RuntimeError, "Laya"):
                runtime.check_dependencies("LiquidAI/d1-omni-600M")
            probe.assert_not_called()

    def test_portable_model_paths_override_and_reuse_previous_cache(self):
        model_id = "convaiinnovations/laya-multilingual"
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            main = Path(directory) / "main"
            main.mkdir()
            cache, model = runtime.model_paths(model_id, main)
            self.assertEqual(cache, main / ".models")
            self.assertEqual(model, cache / model_id.replace("/", "--"))
            old = Path(directory) / "old-model"
            old.mkdir()
            (main / ".local-jev.json").write_text(json.dumps({"repo_id": model_id, "model_dir": str(old)}))
            self.assertEqual(runtime.model_paths(model_id, main)[1], old)
            with patch.dict(os.environ, {"JEV_MODEL_CACHE": "alternate"}):
                cache, model = runtime.model_paths(model_id, main)
                self.assertEqual(cache, main / "alternate")
                self.assertEqual(model, cache / model_id.replace("/", "--"))
            self.assertEqual(runtime.model_paths("convaiinnovations/laya", main)[0], main / ".models")


    def test_complete_model_skips_hub_and_truncated_weights_are_repaired(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            root = Path(directory)
            checkpoint(root)
            with patch("huggingface_hub.snapshot_download") as download:
                runtime.ensure_model("convaiinnovations/laya-multilingual", root)
                download.assert_not_called()
            weights = root / "model.safetensors"
            weights.write_bytes(weights.read_bytes()[:-1])
            self.assertTrue(runtime.model_problems(root, "laya"))
            with patch("huggingface_hub.snapshot_download", side_effect=lambda **kw: checkpoint(root)) as download:
                runtime.ensure_model("convaiinnovations/laya-multilingual", root)
                self.assertTrue(download.call_args.kwargs["force_download"])
            weights.unlink()
            with patch("huggingface_hub.snapshot_download", side_effect=lambda **kw: checkpoint(root)) as download:
                runtime.ensure_model("convaiinnovations/laya-multilingual", root)
                self.assertFalse(download.call_args.kwargs["force_download"])

    def test_download_failure_does_not_mark_model_ready(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            with patch("huggingface_hub.snapshot_download", return_value=directory):
                with self.assertRaisesRegex(RuntimeError, "仍不完整"):
                    runtime.ensure_model("convaiinnovations/laya-multilingual", directory)


    def test_activation_checks_readiness_before_mutating_environment(self):
        import requests
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".local-jev.json"
            config = {"base_url": "http://127.0.0.1:8000", "model": "local-test", "api_key": "test"}
            path.write_text(json.dumps(config), encoding="utf-8")
            with patch.dict(os.environ, {"TYPESAFE_BASE_URL": "previous"}), patch(
                    "requests.get", side_effect=requests.ConnectionError):
                with self.assertRaises(RuntimeError):
                    activate(path)
                self.assertEqual(os.environ["TYPESAFE_BASE_URL"], "previous")
            config["base_url"] = "https://remote.example"
            path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaises(ValueError):
                activate(path)

    def test_no_local_connection_keeps_remote_settings(self):
        with tempfile.TemporaryDirectory() as directory, patch("pathlib.Path.cwd", return_value=Path(directory)):
            with patch.dict(os.environ, {"TYPESAFE_API_KEY": "existing-remote",
                                      "TYPESAFE_BASE_URL": "https://api.typesafe.ai"}):
                exec(LOCAL_SETUP, {})
                self.assertEqual(os.environ["TYPESAFE_API_KEY"], "existing-remote")
                self.assertEqual(os.environ["TYPESAFE_BASE_URL"], "https://api.typesafe.ai")

    def test_gpu_unavailable_uses_cpu(self):
        with patch("torch.cuda.is_available", return_value=False), patch(
                "torch.backends.mps.is_available", return_value=False), patch(
                "subprocess.run", side_effect=FileNotFoundError):
            self.assertEqual(runtime.hardware_report()["device"], "cpu")

    def test_start_is_local_offline_and_does_not_overwrite_remote_key(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            root = Path(directory)
            checkpoint(root)
            with patch.dict(os.environ, {"TYPESAFE_API_KEY": "existing-remote"}), patch(
                    "socket.socket") as socket_factory, patch("subprocess.Popen") as popen:
                socket_factory.return_value.__enter__.return_value.connect_ex.return_value = 1
                popen.return_value.pid = 123
                process, config = runtime.start_service("convaiinnovations/laya-multilingual", root,
                                                       "cpu", 8000, root / "config.json", root / "server.log")
                env = popen.call_args.kwargs["env"]
                self.assertEqual(env["HF_HUB_OFFLINE"], "1")
                self.assertEqual(env["LAYA_HOST"], "127.0.0.1")
                self.assertEqual(config["model"], "local-laya-multilingual")
                self.assertNotIn("/", env["LAYA_DEFAULT_MODEL"])
                self.assertEqual(os.environ["TYPESAFE_API_KEY"], "existing-remote")
                self.assertNotEqual(config["api_key"], "existing-remote")

    def test_occupied_port_and_process_failure_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory, patch("socket.socket") as socket_factory:
            root = Path(directory)
            socket_factory.return_value.__enter__.return_value.connect_ex.return_value = 0
            with self.assertRaisesRegex(RuntimeError, "端口"):
                runtime.start_service("convaiinnovations/laya", root, "cpu", 8000,
                                      root / "config.json", root / "server.log")
        from unittest.mock import Mock
        process = Mock()
        process.poll.return_value = 1
        process.returncode = 1
        with self.assertRaisesRegex(RuntimeError, "退出码"):
            runtime.wait_service(process, {"base_url": "http://127.0.0.1:8000", "api_key": "x"}, timeout=1)

    def test_notebook_connection_is_idempotent_and_preserves_other_outputs(self):
        import copy
        import nbformat
        client_cell = nbformat.v4.new_code_cell(
            'client = TypeSafeClient(api_key=API_KEY, model="jev-latest") if API_KEY else None',
            execution_count=2, metadata={"original": "client"},
            outputs=[nbformat.v4.new_output("stream", text="original client output\n")])
        nb = nbformat.v4.new_notebook(metadata={"original": "notebook"}, cells=[
            nbformat.v4.new_code_cell('%pip install -q -U typesafe-sdk', execution_count=1,
                                     metadata={"original": "install"},
                                     outputs=[nbformat.v4.new_output("stream", text="original install output\n")]),
            client_cell,
            nbformat.v4.new_code_cell("print(42)", execution_count=1,
                                     outputs=[nbformat.v4.new_output("stream", text="42\n")])])
        originals = {c.id: copy.deepcopy(c) for c in nb.cells}
        metadata = copy.deepcopy(nb.metadata)
        self.assertTrue(connect_local_service(nb))
        self.assertFalse(connect_local_service(nb))
        self.assertIn("TYPESAFE_DEFAULT_MODEL", client_cell.source)
        self.assertEqual(nb.metadata, metadata)
        for cell in nb.cells:
            if cell.id in originals:
                for field in ("metadata", "outputs", "execution_count"):
                    self.assertEqual(cell[field], originals[cell.id][field])


if __name__ == "__main__":
    unittest.main()
