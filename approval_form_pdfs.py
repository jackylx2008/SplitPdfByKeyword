"""
文件说明：
- 对目标目录中的 PDF 执行“只保留第一页并增加审批单前缀”的入口脚本。

主要职责：
- 解析命令行参数。
- 确保使用项目内 .conda 解释器运行。
- 加载审批单目录工作流所需配置。
- 调用审批单工作流批量处理目标目录中的 PDF，并输出统计 Excel。

运行方式：
- 分类：独立运行
- 直接运行命令：python approval_form_pdfs.py [--input-path ...] [--prefix ...] [--excel-path ...]
- 直接运行用途：批量处理指定目录中的 PDF，覆盖原文件内容并重命名，最后导出统计 Excel。
- 被谁调用：通常不作为其他脚本依赖入口
- 作为依赖用途：无，公共能力已下沉到 workflows/ 和 services/。

输入：
- 配置输入：config.yaml、common.env、命令行参数 --config / --env / --input-path / --prefix / --excel-path
- 数据输入：目标目录中的 PDF 文件
- 前置条件：目标目录存在且文件可写

输出：
- 结果输出：仅保留第一页并增加前缀后的 PDF、审批单统计 Excel
- 日志输出：./log/approval_form_pdfs.log
- 副作用：覆盖原 PDF 内容，并修改原文件名

核心入口：
- 主入口函数：main()
- 关键函数：parse_args()

依赖关系：
- 依赖的本项目模块：core.config、core.logging_utils、core.runtime、workflows.approval_form_workflow
- 依赖的第三方库：无
"""

import argparse

from core.config import load_runtime_config
from core.logging_utils import setup_logger
from core.runtime import ensure_project_python
from workflows.approval_form_workflow import run_approval_form_workflow


def parse_args():
    parser = argparse.ArgumentParser(
        description="批量处理目标目录中的 PDF，仅保留第一页并增加审批单前缀。"
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
        help="目标目录，优先级高于 config.yaml/common.env 中的 approval_form_input_path",
    )
    parser.add_argument(
        "--prefix",
        default=None,
        help="文件名前缀，优先级高于 config.yaml/common.env 中的 approval_form_prefix",
    )
    parser.add_argument(
        "--excel-path",
        default=None,
        help="统计 Excel 输出路径，优先级高于 config.yaml/common.env 中的 approval_form_excel_path",
    )
    return parser.parse_args()


def main():
    ensure_project_python()

    logger = setup_logger()
    args = parse_args()

    try:
        config = load_runtime_config(config_path=args.config, env_path=args.env)
    except (FileNotFoundError, ValueError) as exc:
        logger.error(str(exc))
        return

    run_approval_form_workflow(
        config,
        logger,
        input_path=args.input_path,
        prefix=args.prefix,
        excel_path=args.excel_path,
    )


if __name__ == "__main__":
    main()
