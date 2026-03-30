import argparse
import os
import shutil
import sys
from pathlib import Path

from config_loader import load_config
from logging_config import setup_logger


def ensure_project_python():
    project_python = Path(__file__).resolve().parent / ".conda" / "python.exe"
    if not project_python.exists():
        return

    current_python = Path(sys.executable).resolve()
    target_python = project_python.resolve()
    if os.path.normcase(str(current_python)) == os.path.normcase(str(target_python)):
        return

    print(f"检测到当前解释器为 {current_python}，切换到项目解释器 {target_python}")
    os.execv(str(target_python), [str(target_python), *sys.argv])


def clear_output_directory(output_path, logger):
    output_dir = Path(output_path)
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"输出目录不存在，已创建: {output_dir}")
        return

    removed_count = 0
    for item in output_dir.iterdir():
        try:
            if item.is_file() or item.is_symlink():
                item.unlink()
            else:
                shutil.rmtree(item)
            removed_count += 1
        except Exception as exc:
            logger.warning(f"清理输出目录项失败: {item}, error={exc}")

    logger.info(f"启动前已清空输出目录: {output_dir}，删除 {removed_count} 项")


def load_runtime_config(
    config_path="config.yaml", env_path=None, input_file=None, output_path=None
):
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"配置文件 {config_path} 不存在。")

    config = load_config(config_path, env_path=env_path)

    if input_file is not None:
        config["input_file"] = str(Path(input_file))

    if output_path is not None:
        config["output_path"] = str(Path(output_path))

    return config


def process_pdf_with_config(config, logger=None, clear_output=True):
    app_logger = logger or setup_logger()
    input_file = config.get("input_file")
    output_path = config.get("output_path", "./output/")

    if not input_file:
        app_logger.error("配置中未指定 input_file。")
        return False

    if not os.path.exists(input_file):
        app_logger.error(f"输入文件 {input_file} 不存在。")
        return False

    from ocr_engine import run_startup_self_check
    from splitter import PDFSplitter

    if clear_output:
        clear_output_directory(output_path, app_logger)

    app_logger.info("执行启动前自检...")
    ocr_processor = run_startup_self_check(config, app_logger)

    app_logger.info(f"正在对文件进行 OCR 识别: {input_file}")
    ocr_results = ocr_processor.process_pdf(input_file)

    app_logger.info("初始化切分器...")
    splitter = PDFSplitter(config)

    app_logger.info("正在执行 PDF 切分处理...")
    splitter.split_by_ocr_results(input_file, ocr_results)

    app_logger.info("切分处理已完成。")
    return True


def parse_args():
    parser = argparse.ArgumentParser(description="按关键词切分单个 PDF。")
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="规则配置文件路径，默认 config.yaml",
    )
    parser.add_argument(
        "--env",
        default=None,
        help="环境变量文件路径，默认自动读取 common.env",
    )
    parser.add_argument(
        "--input-file",
        default=None,
        help="待处理 PDF 路径，优先级高于 config.yaml/common.env",
    )
    parser.add_argument(
        "--output-path",
        default=None,
        help="输出目录，优先级高于 config.yaml/common.env",
    )
    return parser.parse_args()


def main():
    ensure_project_python()

    logger = setup_logger()
    args = parse_args()

    try:
        config = load_runtime_config(
            config_path=args.config,
            env_path=args.env,
            input_file=args.input_file,
            output_path=args.output_path,
        )
    except (FileNotFoundError, ValueError) as exc:
        logger.error(str(exc))
        return

    process_pdf_with_config(config, logger=logger, clear_output=True)


if __name__ == "__main__":
    main()
