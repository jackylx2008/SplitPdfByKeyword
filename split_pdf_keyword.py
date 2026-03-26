import os
import sys
import shutil
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


def main():
    ensure_project_python()

    from ocr_engine import run_startup_self_check
    from splitter import PDFSplitter

    logger = setup_logger()
    config_path = "config.yaml"

    if not os.path.exists(config_path):
        logger.error(f"配置文件 {config_path} 不存在。")
        return

    config = load_config(config_path)
    input_file = config.get("input_file")
    output_path = config.get("output_path", "./output/")

    if not input_file:
        logger.error("配置文件中未指定 input_file。")
        return

    clear_output_directory(output_path, logger)

    logger.info("执行启动前自检...")
    ocr_processor = run_startup_self_check(config, logger)

    if not os.path.exists(input_file):
        logger.error(f"输入文件 {input_file} 不存在。")
        return

    # OCR 阶段
    logger.info(f"正在对文件进行 OCR 识别: {input_file}")
    ocr_results = ocr_processor.process_pdf(input_file)

    # 切分阶段
    logger.info("初始化切分器...")
    splitter = PDFSplitter(config)

    logger.info("正在执行 PDF 切分处理...")
    splitter.split_by_ocr_results(input_file, ocr_results)

    logger.info("所有处理已完成。")


if __name__ == "__main__":
    main()
