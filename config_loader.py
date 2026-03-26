import os
import re
from pathlib import Path

import yaml


ENV_VAR_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def parse_env_file(env_path):
    env_values = {}
    if not env_path.exists():
        return env_values

    for line_number, raw_line in enumerate(
        env_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if "=" not in line:
            raise ValueError(
                f"环境变量文件格式错误: {env_path} 第 {line_number} 行缺少 '='"
            )

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not key:
            raise ValueError(
                f"环境变量文件格式错误: {env_path} 第 {line_number} 行变量名为空"
            )

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        env_values[key] = value

    return env_values


def render_config_template(config_text, env_values):
    missing_variables = set()

    def replace_env_var(match):
        var_name = match.group(1)
        default_value = match.group(2)

        if var_name in env_values:
            return env_values[var_name]
        if default_value is not None:
            return default_value

        missing_variables.add(var_name)
        return match.group(0)

    rendered = ENV_VAR_PATTERN.sub(replace_env_var, config_text)

    if missing_variables:
        missing_names = ", ".join(sorted(missing_variables))
        raise ValueError(f"config.yaml 缺少环境变量: {missing_names}")

    return rendered


def load_config(config_path, env_path=None):
    config_file = Path(config_path)
    if env_path is None:
        env_file = config_file.resolve().parent / "common.env"
    else:
        env_file = Path(env_path)

    file_env = parse_env_file(env_file)
    merged_env = {**file_env, **os.environ}

    rendered_config = render_config_template(
        config_file.read_text(encoding="utf-8"), merged_env
    )
    loaded = yaml.safe_load(rendered_config)
    return loaded or {}
