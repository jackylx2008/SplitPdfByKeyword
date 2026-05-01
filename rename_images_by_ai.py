"""
文件说明：
- 对指定目录下的图片执行本地 AI OCR，并按 regex_pattern 匹配结果原地重命名。

运行方式：
- python rename_images_by_ai.py [--input-path ...] [--dry-run]

输入：
- 配置输入：config.yaml、common.env、命令行参数
- 数据输入：目录下的 PNG/JPG/JPEG/HEIC/HEIF 图片

输出：
- 结果输出：原地重命名后的图片文件
- 日志输出：./log/rename_images_by_ai.log
"""

import argparse
import re
from pathlib import Path

from core.config import load_runtime_config
from core.logging_utils import setup_logger
from core.runtime import ensure_project_python


SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".heic", ".heif"}


def parse_args():
    parser = argparse.ArgumentParser(
        description="使用项目本地 AI OCR 设置批量重命名目录中的图片文件。"
    )
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
        "--input-path",
        default=None,
        help="图片输入目录，优先级高于 config.yaml/common.env 中的 png_ocr_input_path",
    )
    parser.add_argument(
        "--filename-prefix",
        default="",
        help="重命名结果文件名前缀，例如传入 IMG_ 后生成 IMG_XXX.jpg",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="递归处理子目录中的图片",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印将要执行的重命名，不实际修改文件",
    )
    return parser.parse_args()


def collect_image_files(input_path, recursive=False):
    source_dir = Path(input_path)
    iterator = source_dir.rglob("*") if recursive else source_dir.iterdir()
    return sorted(
        path
        for path in iterator
        if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES
    )


def register_heif_reader(logger):
    try:
        from pillow_heif import register_heif_opener
    except ImportError:
        logger.warning(
            "未安装 pillow-heif，HEIC/HEIF 图片可能无法读取；可执行 pip install pillow-heif。"
        )
        return False

    register_heif_opener()
    logger.info("已启用 pillow-heif，支持读取 HEIC/HEIF 图片。")
    return True


def read_image(image_path, logger):
    import cv2
    import numpy as np
    from PIL import Image

    path = Path(image_path)
    try:
        image_bytes = np.fromfile(str(path), dtype=np.uint8)
    except OSError as exc:
        logger.warning(f"读取图片字节失败，已跳过: {path}, error={exc}")
        return None

    if image_bytes.size > 0:
        image = cv2.imdecode(image_bytes, cv2.IMREAD_COLOR)
        if image is not None:
            return image

    if path.suffix.lower() in {".heic", ".heif"}:
        heif_image = read_heif_image(path, logger)
        if heif_image is not None:
            return heif_image

    try:
        with Image.open(path) as pil_image:
            rgb_image = pil_image.convert("RGB")
            return cv2.cvtColor(np.array(rgb_image), cv2.COLOR_RGB2BGR)
    except Exception as exc:
        logger.warning(f"图片解码失败，已跳过: {path}, error={exc}")
        return None


def read_heif_image(path, logger):
    import cv2
    import numpy as np
    from PIL import Image

    try:
        from pillow_heif import read_heif
    except ImportError as exc:
        logger.warning(
            f"读取 HEIC/HEIF 需要 pillow-heif，已跳过: {path}, error={exc}"
        )
        return None

    try:
        heif_file = read_heif(str(path))
        rgb_image = Image.frombytes(
            heif_file.mode,
            heif_file.size,
            heif_file.data,
            "raw",
        ).convert("RGB")
        logger.info(f"HEIC/HEIF 显式解码成功: {path}, size={rgb_image.size}")
        return cv2.cvtColor(np.array(rgb_image), cv2.COLOR_RGB2BGR)
    except Exception as exc:
        logger.warning(f"HEIC/HEIF 显式解码失败，已跳过: {path}, error={exc}")
        return None


def ocr_image(image_path, ocr_processor, logger):
    image = read_image(image_path, logger)
    if image is None:
        return ""

    result, elapsed = ocr_processor.ocr(image)
    page_text = ""
    if result:
        for line in result:
            page_text += line[1] + "\n"

    text_lines = [line.strip() for line in page_text.splitlines() if line.strip()]
    preview = " | ".join(text_lines[:3]) if text_lines else "[无识别文本]"
    logger.info(
        f"文件 {Path(image_path).name} OCR 完成，耗时={elapsed:.2f}s，"
        f"有效行数={len(text_lines)}，前 3 行: {preview}"
    )
    return page_text


def build_match_candidates(page_text):
    lines = [line.strip() for line in str(page_text).splitlines() if line.strip()]
    compact_lines = [re.sub(r"\s+", "", line) for line in lines]
    full_text = "\n".join(lines)
    compact_text = re.sub(r"\s+", "", full_text)
    return lines + compact_lines + [full_text, compact_text]


def normalize_regex_match(match_value):
    if isinstance(match_value, tuple):
        return "-".join(str(part) for part in match_value if str(part))
    return str(match_value).strip()


def find_first_image_match(page_text, compiled_patterns):
    seen_candidates = set()
    for candidate in build_match_candidates(page_text):
        if not candidate or candidate in seen_candidates:
            continue
        seen_candidates.add(candidate)

        for pattern_info in compiled_patterns:
            strict_match = pattern_info["strict"].search(candidate)
            if strict_match:
                return strict_match.group(0), pattern_info["raw"]

            relaxed_match = pattern_info["relaxed"].search(candidate)
            if relaxed_match:
                return relaxed_match.group(0), pattern_info["raw"]

            strict_findall = pattern_info["strict"].findall(candidate)
            if strict_findall:
                return normalize_regex_match(strict_findall[0]), pattern_info["raw"]

            relaxed_findall = pattern_info["relaxed"].findall(candidate)
            if relaxed_findall:
                return normalize_regex_match(relaxed_findall[0]), pattern_info["raw"]

    return None, None


def ensure_unique_image_path(directory, base_name, suffix):
    candidate = directory / f"{base_name}{suffix}"
    counter = 2
    while candidate.exists():
        candidate = directory / f"{base_name}_{counter}{suffix}"
        counter += 1
    return candidate


def rename_images_by_ai(
    image_files,
    config,
    logger,
    filename_prefix="",
    dry_run=False,
):
    from services.ocr_service import run_startup_self_check
    from services.pdf_rename_service import (
        build_prefixed_filename,
        compile_regex_patterns,
    )

    compiled_patterns = compile_regex_patterns(config)
    if not image_files:
        logger.warning("没有待重命名的图片文件。")
        return False
    if not compiled_patterns:
        logger.warning("未配置 regex_pattern，跳过图片重命名。")
        return False

    logger.info("执行启动前自检并初始化 OCR...")
    ocr_processor = run_startup_self_check(config, logger)
    logger.info(f"开始处理图片重命名，共 {len(image_files)} 个文件。")

    renamed_count = 0
    unmatched_files = []
    for image_file in image_files:
        page_text = ocr_image(image_file, ocr_processor, logger)
        matched_text, matched_pattern = find_first_image_match(
            page_text, compiled_patterns
        )
        if not matched_text:
            unmatched_files.append(image_file.name)
            logger.warning(f"未匹配到 regex_pattern，跳过重命名: {image_file}")
            continue

        safe_name = build_prefixed_filename(filename_prefix, matched_text)
        desired_path = image_file.parent / f"{safe_name}{image_file.suffix}"
        if image_file.resolve() == desired_path.resolve():
            logger.info(f"文件名已符合匹配结果，无需重命名: {image_file.name}")
            continue

        target_path = ensure_unique_image_path(
            image_file.parent, safe_name, image_file.suffix
        )

        if dry_run:
            logger.info(
                f"[dry-run] 将重命名图片: {image_file.name} -> {target_path.name}, "
                f"matched_text={matched_text}, pattern={matched_pattern}"
            )
        else:
            image_file.rename(target_path)
            logger.info(
                f"已重命名图片: {image_file.name} -> {target_path.name}, "
                f"matched_text={matched_text}, pattern={matched_pattern}"
            )
        renamed_count += 1

    if unmatched_files:
        logger.warning(
            "以下图片未匹配到任何 regex_pattern，未执行重命名: "
            + ", ".join(unmatched_files)
        )
    logger.info(f"图片重命名流程结束，处理成功 {renamed_count} 个文件。")
    return True


def main():
    ensure_project_python()

    logger = setup_logger(log_file="./log/rename_images_by_ai.log", filemode="w")
    args = parse_args()
    register_heif_reader(logger)

    try:
        config = load_runtime_config(config_path=args.config, env_path=args.env)
    except (FileNotFoundError, ValueError) as exc:
        logger.error(str(exc))
        return

    source_dir = Path(
        args.input_path or config.get("png_ocr_input_path", "./input/")
    ).resolve()
    if not source_dir.exists():
        logger.error(f"图片输入目录不存在: {source_dir}")
        return
    if not source_dir.is_dir():
        logger.error(f"图片输入路径不是目录: {source_dir}")
        return

    image_files = collect_image_files(source_dir, recursive=args.recursive)
    logger.info(
        f"图片输入目录: {source_dir}，递归={args.recursive}，"
        f"匹配格式={sorted(SUPPORTED_IMAGE_SUFFIXES)}，文件数量={len(image_files)}"
    )
    rename_images_by_ai(
        image_files,
        config,
        logger,
        filename_prefix=args.filename_prefix,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
