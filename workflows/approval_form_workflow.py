"""
文件说明：
- 编排目标目录下 PDF 的“只保留第一页并补审批单前缀”流程。

主要职责：
- 解析审批单工作流目标目录、文件名前缀与统计 Excel 配置。
- 收集目录中的 PDF 文件并逐个处理。
- 在处理结束后生成审批单统计 Excel。
- 汇总处理结果并输出统一日志。

运行方式：
- 分类：被依赖脚本
- 直接运行命令：不建议直接运行
- 直接运行用途：无独立业务入口，主要被 approval_form_pdfs.py 调用。
- 被谁调用：approval_form_pdfs.py
- 作为依赖用途：提供审批单目录批处理工作流。

输入：
- 配置输入：approval_form_input_path、approval_form_prefix、approval_form_excel_path
- 数据输入：目标目录中的 PDF 文件
- 前置条件：目标目录存在且当前进程有读写权限

输出：
- 结果输出：被覆盖并重命名后的 PDF 文件、审批单统计 Excel
- 日志输出：调用方 logger
- 副作用：覆盖原 PDF 内容并修改文件名

核心入口：
- 关键函数：run_approval_form_workflow()

依赖关系：
- 依赖的本项目模块：services.approval_form_excel_service、services.pdf_first_page_service
- 依赖的第三方库：无
"""

from pathlib import Path

from services.approval_form_excel_service import export_approval_form_excel
from services.pdf_first_page_service import retain_first_page_and_prefix_pdf


def _collect_pdf_files(input_path):
    source_dir = Path(input_path)
    return sorted(path for path in source_dir.glob("*.pdf") if path.is_file())


def run_approval_form_workflow(
    config,
    logger,
    input_path=None,
    prefix=None,
    excel_path=None,
):
    source_dir = Path(
        input_path or config.get("approval_form_input_path", "./output/")
    ).resolve()
    filename_prefix = prefix or config.get("approval_form_prefix", "审批单_")
    resolved_excel_path = Path(
        excel_path
        or config.get("approval_form_excel_path")
        or source_dir / "审批单统计.xlsx"
    ).resolve()

    if not source_dir.exists():
        logger.error(f"审批单输入目录不存在: {source_dir}")
        return False

    if not source_dir.is_dir():
        logger.error(f"审批单输入路径不是目录: {source_dir}")
        return False

    pdf_files = _collect_pdf_files(source_dir)
    if not pdf_files:
        logger.warning(f"审批单输入目录中没有 PDF: {source_dir}")
        return False

    logger.info(
        "开始处理审批单目录，"
        f"目标目录: {source_dir}，PDF 数量: {len(pdf_files)}，前缀: {filename_prefix}，"
        f"统计表: {resolved_excel_path}"
    )

    success_count = 0
    failed_files = []
    for pdf_path in pdf_files:
        try:
            result = retain_first_page_and_prefix_pdf(
                pdf_path,
                logger,
                prefix=filename_prefix,
            )
            if result:
                success_count += 1
            else:
                failed_files.append(str(pdf_path))
        except Exception as exc:
            failed_files.append(str(pdf_path))
            logger.exception(f"处理审批单 PDF 失败: {pdf_path}, error={exc}")

    logger.info(f"审批单批处理结束：成功 {success_count} 个，失败 {len(failed_files)} 个。")
    if failed_files:
        logger.warning("审批单失败文件列表: " + " | ".join(failed_files))

    final_pdf_files = _collect_pdf_files(source_dir)
    try:
        excel_result = export_approval_form_excel(
            final_pdf_files,
            logger,
            output_path=resolved_excel_path,
            prefix=filename_prefix,
        )
    except Exception as exc:
        logger.exception(f"生成审批单统计 Excel 失败: {resolved_excel_path}, error={exc}")
        return False

    return success_count > 0 and bool(excel_result)
