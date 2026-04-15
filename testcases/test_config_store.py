from pathlib import Path

from core_modules.config.models import AppConfig, build_export_options
from core_modules.config.store import CONFIG_FILE_NAME, config_path, load_config, save_config


def test_config_store_round_trip(tmp_path: Path) -> None:
    config = AppConfig()
    config.token = "demo-token"
    config.persist_token = True
    config.last_repo_input = "cyberangel/rg9gdm"
    config.export_defaults.output_dir = "demo-output"
    config.export_defaults.timeout = 10
    config.export_defaults.token_check_timeout = 5
    config.export_defaults.request_max_retries = 7
    config.export_defaults.rate_limit_backoff_seconds = 3.5
    config.export_defaults.network_backoff_seconds = 1.5
    config.export_defaults.max_backoff_seconds = 45.0
    saved = save_config(config, tmp_path)

    assert saved == tmp_path / CONFIG_FILE_NAME
    loaded = load_config(tmp_path)
    assert loaded.token == "demo-token"
    assert loaded.persist_token is True
    assert loaded.last_repo_input == "cyberangel/rg9gdm"
    assert loaded.export_defaults.output_dir == "demo-output"
    assert loaded.export_defaults.timeout == 10
    assert loaded.export_defaults.token_check_timeout == 5
    assert loaded.export_defaults.request_max_retries == 7
    assert loaded.export_defaults.rate_limit_backoff_seconds == 3.5
    assert loaded.export_defaults.network_backoff_seconds == 1.5
    assert loaded.export_defaults.max_backoff_seconds == 45.0


def test_config_store_skips_token_when_persist_disabled(tmp_path: Path) -> None:
    config = AppConfig(token="demo-token", persist_token=False)

    save_config(config, tmp_path)
    loaded = load_config(tmp_path)

    assert loaded.persist_token is False
    assert loaded.token == ""


def test_config_store_keeps_persist_token_flag_when_disabled(tmp_path: Path) -> None:
    config = AppConfig(token="demo-token", persist_token=False)

    save_config(config, tmp_path)
    raw = (tmp_path / CONFIG_FILE_NAME).read_text(encoding="utf-8")

    assert '"persist_token": false' in raw
    assert '"token": ""' in raw


def test_build_export_options_uses_config_defaults() -> None:
    config = AppConfig()
    config.export_defaults.output_dir = "out-dir"
    config.export_defaults.request_interval = 0.1
    config.export_defaults.timeout = 10
    config.export_defaults.offline_assets = False
    config.export_defaults.assets_dir_name = "files"
    config.export_defaults.fail_on_asset_error = True
    config.export_defaults.attachment_suffixes = [".pdf", ".mp4"]

    options = build_export_options(config, "cyberangel/rg9gdm", {1, 2})

    assert options.repo_input == "cyberangel/rg9gdm"
    assert options.output_dir == Path("out-dir")
    assert options.request_interval == 0.1
    assert options.offline_assets is False
    assert options.assets_dir_name == "files"
    assert options.fail_on_asset_error is True
    assert options.attachment_suffixes == [".pdf", ".mp4"]
    assert options.selected_doc_ids == {1, 2}


def test_config_store_migrates_legacy_file_type(tmp_path: Path) -> None:
    raw = """
{
  "version": 1,
  "token": "",
  "persist_token": true,
  "last_repo_input": "",
  "export_defaults": {
    "output_dir": "output",
    "resume": true,
    "strict": false,
    "request_interval": 0.1,
    "timeout": 10,
    "token_check_timeout": 5,
    "request_max_retries": 5,
    "rate_limit_backoff_seconds": 5.0,
    "network_backoff_seconds": 2.0,
    "max_backoff_seconds": 60.0,
    "max_docs": null,
    "offline_assets": true,
    "assets_dir_name": "assets",
    "fail_on_asset_error": false,
    "file_type": 3,
    "proxy": {
      "enabled": false,
      "host": "",
      "port": 7890,
      "test_url": "https://www.baidu.com"
    }
  },
  "ui_preferences": {
    "confirm_before_export": true,
    "auto_save_after_export": true
  }
}
""".strip()
    (tmp_path / CONFIG_FILE_NAME).write_text(raw, encoding="utf-8")

    loaded = load_config(tmp_path)
    assert loaded.export_defaults.attachment_suffixes == [".pdf"]


def test_config_path_uses_visible_filename(tmp_path: Path) -> None:
    path = config_path(tmp_path)
    assert path.name == CONFIG_FILE_NAME
    assert not path.name.startswith(".")
