import os
import fitz  # PyMuPDF
from logging_config import setup_logger

logger = setup_logger(log_file="./log/splitter.log")


class PDFSplitter:
    def __init__(self, config):
        self.config = config
        self.keywords = config.get("split_keywords") or config.get("ocr", {}).get(
            "split_keywords", []
        )
        self.output_path = config.get("output_path", "./output/")

        if not os.path.exists(self.output_path):
            os.makedirs(self.output_path)
            logger.info(f"创建输出目录: {self.output_path}")

    def split_by_ocr_results(self, input_pdf_path, ocr_results):
        """
        基于 OCR 结果进行切分。
        当某一页同时包含全部关键字时，该页作为新文档的起始。
        """
        if not ocr_results:
            logger.warning("没有 OCR 结果，无法切分。")
            return

        doc = fitz.open(input_pdf_path)
        total_pages = len(doc)

        # 记录切分点的起始页码
        split_points = []
        for res in ocr_results:
            page_index = res["page"]
            text = res["text"]

            normalized_text = "".join(str(text).split())

            if not self.keywords:
                continue

            valid_keywords = [kw for kw in self.keywords if str(kw).strip()]
            matched_keywords = []
            for kw in valid_keywords:
                normalized_kw = "".join(str(kw).split())
                if normalized_kw and normalized_kw in normalized_text:
                    matched_keywords.append(kw)

            if len(valid_keywords) > 0 and len(matched_keywords) == len(valid_keywords):
                logger.info(
                    f"第 {page_index + 1} 页同时命中全部切分关键字: {matched_keywords}"
                )
                split_points.append(page_index)

        # 如果第一页不是关键字页，默认加上第一页作为起始点
        if not split_points or split_points[0] != 0:
            split_points.insert(0, 0)

        # 根据切分点保存文件
        num_splits = len(split_points)
        for i in range(num_splits):
            start_page = split_points[i]
            # 结束页码是下一个切分点，或者是文档最后一页
            end_page = split_points[i + 1] if i + 1 < num_splits else total_pages

            new_doc = fitz.open()
            # insert_pdf 的页面范围是 [start, end)
            new_doc.insert_pdf(doc, from_page=start_page, to_page=end_page - 1)

            input_filename = os.path.basename(input_pdf_path).replace(".pdf", "")
            output_filename = f"{input_filename}_part_{i + 1}_page_{start_page + 1}.pdf"
            save_path = os.path.join(self.output_path, output_filename)

            new_doc.save(save_path)
            new_doc.close()
            logger.info(
                f"已导出切分文件: {save_path} (包含页码 {start_page + 1} 到 {end_page})"
            )

        doc.close()
        logger.info(f"PDF 处理完成，共切分为 {num_splits} 个文件。")
