"""
文件说明：
- 提供 PDF 只保留第一页并覆盖原文件、再补充固定前缀重命名的能力。

主要职责：
- 读取单个 PDF，仅保留第一页。
- 使用临时文件安全覆盖原 PDF。
- 为处理后的文件名补充固定前缀，并避免重名冲突。

运行方式：
- 分类：被依赖脚本
- 直接运行命令：不建议直接运行
- 直接运行用途：无独立业务入口，主要被 workflow 调用。
- 被谁调用：workflows.approval_form_workflow
- 作为依赖用途：为“审批单目录批处理”提供单文件处理能力。

输入：
- 配置输入：prefix 前缀文本
- 数据输入：单个 PDF 文件路径
- 前置条件：PDF 文件存在且可读写

输出：
- 结果输出：处理后的 PDF 最终路径
- 日志输出：调用方 logger
- 副作用：覆盖原 PDF 内容，并可能修改文件名

核心入口：
- 关键函数：retain_first_page_and_prefix_pdf()

依赖关系：
- 依赖的本项目模块：无
- 依赖的第三方库：PyMuPDF
"""

from pathlib import Path

import fitz


def _ensure_unique_prefixed_path(pdf_path, prefix):
    source_path = Path(pdf_path)
    target_name = (
        source_path.name
        if source_path.name.startswith(prefix)
        else f"{prefix}{source_path.name}"
    )
    candidate = source_path.with_name(target_name)
    counter = 2

    while candidate.exists() and candidate.resolve() != source_path.resolve():
        candidate = source_path.with_name(f"{prefix}{source_path.stem}_{counter}.pdf")
        counter += 1

    return candidate


def retain_first_page_and_prefix_pdf(pdf_path, logger, prefix="审批单_"):
    source_path = Path(pdf_path)
    if not source_path.exists():
        logger.error(f"PDF 不存在: {source_path}")
        return False

    if source_path.suffix.lower() != ".pdf":
        logger.warning(f"文件不是 PDF，跳过: {source_path}")
        return False

    temp_path = source_path.with_name(f"{source_path.stem}.tmp.pdf")
    final_path = _ensure_unique_prefixed_path(source_path, prefix)

    doc = None
    first_page_doc = None
    try:
        doc = fitz.open(source_path)
        if len(doc) == 0:
            logger.warning(f"PDF 没有可用页面，跳过: {source_path}")
            return False

        if len(doc) == 1 and prefix in source_path.name:
            logger.info(
                f"PDF 已是单页且文件名已包含前缀，跳过处理: {source_path.name}"
            )
            return source_path

        first_page_doc = fitz.open()
        first_page_doc.insert_pdf(doc, from_page=0, to_page=0)
        first_page_doc.save(temp_path)
    finally:
        if first_page_doc is not None:
            first_page_doc.close()
        if doc is not None:
            doc.close()

    source_path.unlink()
    temp_path.replace(source_path)

    if final_path.resolve() != source_path.resolve():
        source_path.rename(final_path)
        logger.info(f"已处理并重命名 PDF: {source_path.name} -> {final_path.name}")
        return final_path

    logger.info(f"已处理 PDF，文件名保持不变: {source_path.name}")
    return source_path
