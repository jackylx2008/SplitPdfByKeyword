import os
import site
import fitz  # PyMuPDF
import numpy as np
from logging_config import setup_logger


KEY_CUDA_DLLS = [
    "cublas64_12.dll",
    "cublasLt64_12.dll",
    "cudart64_12.dll",
    "cudnn64_9.dll",
    "cufft64_11.dll",
]


def _inject_cuda_runtime_paths():
    if not hasattr(os, "add_dll_directory"):
        return []

    cuda_bin_paths = []
    for site_package in site.getsitepackages():
        nvidia_dir = os.path.join(site_package, "nvidia")
        if not os.path.isdir(nvidia_dir):
            continue

        for package_name in os.listdir(nvidia_dir):
            bin_dir = os.path.join(nvidia_dir, package_name, "bin")
            if os.path.isdir(bin_dir):
                cuda_bin_paths.append(bin_dir)

    cuda_bin_paths = list(dict.fromkeys(cuda_bin_paths))

    if not cuda_bin_paths:
        return []

    for bin_dir in cuda_bin_paths:
        try:
            os.add_dll_directory(bin_dir)
        except OSError:
            continue

    os.environ["PATH"] = ";".join(cuda_bin_paths) + ";" + os.environ.get("PATH", "")
    return cuda_bin_paths


def _collect_key_cuda_dll_paths():
    dll_paths = {}
    for dll_name in KEY_CUDA_DLLS:
        dll_paths[dll_name] = None
        for bin_dir in CUDA_RUNTIME_BIN_DIRS:
            candidate = os.path.join(bin_dir, dll_name)
            if os.path.exists(candidate):
                dll_paths[dll_name] = candidate
                break
    return dll_paths


CUDA_RUNTIME_BIN_DIRS = _inject_cuda_runtime_paths()

from rapidocr_onnxruntime import RapidOCR  # noqa: E402
from rapidocr_onnxruntime.utils import OrtInferSession  # noqa: E402

logger = setup_logger(log_file="./log/ocr_engine.log")


class PDFOCRProcessor:
    def __init__(self, config):
        self.config = config
        ocr_config = config.get("ocr", {})
        # RapidOCR 使用 ONNX Runtime 推理，通过指定 providers 启用 GPU 加速
        # CUDAExecutionProvider 会自动利用 RTX 5090D 的 24G 显存
        use_gpu = ocr_config.get("use_gpu", True)
        providers = (
            ["CUDAExecutionProvider", "CPUExecutionProvider"]
            if use_gpu
            else ["CPUExecutionProvider"]
        )
        det_model_path = ocr_config.get("det_model_path", "")
        rec_model_path = ocr_config.get("rec_model_path", "")
        cls_model_path = ocr_config.get("cls_model_path", "")

        try:
            self.ocr = RapidOCR(
                det_use_cuda=use_gpu,
                rec_use_cuda=use_gpu,
                cls_use_cuda=use_gpu,
                det_model_path=det_model_path,
                rec_model_path=rec_model_path,
                cls_model_path=cls_model_path,
                det_providers=providers,
                rec_providers=providers,
                cls_providers=providers,
            )

            if use_gpu:
                self._rebuild_all_ort_sessions_with_cuda()

            self._log_provider_status(use_gpu)
        except Exception as exc:
            logger.warning(f"RapidOCR GPU 初始化失败，将回退 CPU 模式: {exc}")
            cpu_providers = ["CPUExecutionProvider"]
            self.ocr = RapidOCR(
                det_use_cuda=False,
                rec_use_cuda=False,
                cls_use_cuda=False,
                det_model_path=det_model_path,
                rec_model_path=rec_model_path,
                cls_model_path=cls_model_path,
                det_providers=cpu_providers,
                rec_providers=cpu_providers,
                cls_providers=cpu_providers,
            )
            self._log_provider_status(False)

    def get_provider_status(self):
        provider_status = {}

        if getattr(self.ocr, "use_text_det", False):
            provider_status["det"] = (
                self.ocr.text_detector.infer.session.get_providers()
            )

        provider_status["rec"] = (
            self.ocr.text_recognizer.session.session.get_providers()
        )

        if getattr(self.ocr, "use_angle_cls", False):
            provider_status["cls"] = self.ocr.text_cls.infer.session.get_providers()

        return provider_status

    def _rebuild_all_ort_sessions_with_cuda(self):
        if getattr(self.ocr, "use_text_det", False):
            det_model = self.ocr.text_detector.infer.session._model_path
            self.ocr.text_detector.infer = OrtInferSession(
                {"model_path": det_model, "use_cuda": True}
            )

        rec_model = self.ocr.text_recognizer.session.session._model_path
        self.ocr.text_recognizer.session = OrtInferSession(
            {"model_path": rec_model, "use_cuda": True}
        )

        if getattr(self.ocr, "use_angle_cls", False):
            cls_model = self.ocr.text_cls.infer.session._model_path
            self.ocr.text_cls.infer = OrtInferSession(
                {"model_path": cls_model, "use_cuda": True}
            )

    def _log_provider_status(self, target_gpu):
        provider_status = self.get_provider_status()

        if target_gpu:
            all_gpu = all(
                "CUDAExecutionProvider" in providers
                for providers in provider_status.values()
            )
            if all_gpu:
                logger.info(f"OCR 已启用 GPU 推理，providers: {provider_status}")
            else:
                logger.warning(
                    f"OCR 未完全启用 GPU，部分模型回退 CPU，providers: {provider_status}"
                )
        else:
            logger.info(f"OCR 使用 CPU 推理，providers: {provider_status}")

    def pdf_to_images(self, pdf_path):
        """
        利用 9950x 的多核心性能，可以将 PDF 页面预导出。
        目前先实现基础的生成，后续可以考虑多进程预取。
        """
        doc = fitz.open(pdf_path)
        for page_index in range(len(doc)):
            page = doc[page_index]
            # 提高缩放倍数以提升 OCR 精度
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.h, pix.w, pix.n
            )
            # 如果是 RGB 需要转为 BGR (PaddleOCR/OpenCV 风格)
            if pix.n == 3:
                import cv2

                img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            yield page_index, img
        doc.close()

    def process_pdf(self, pdf_path):
        results = []
        logger.info(f"开始处理 PDF: {pdf_path}")

        for page_index, img in self.pdf_to_images(pdf_path):
            logger.debug(f"正在识别第 {page_index + 1} 页...")
            # RapidOCR 返回 (result, elapse)，result 是 list of [box, text, score]
            result, _ = self.ocr(img)

            page_text = ""
            if result:
                for line in result:
                    page_text += line[1] + "\n"

            text_lines = [
                line.strip() for line in page_text.splitlines() if line.strip()
            ]
            preview_lines = text_lines[:3]
            if preview_lines:
                logger.info(
                    f"第 {page_index + 1} 页识别文本前 3 行: {' | '.join(preview_lines)}"
                )
            else:
                logger.info(f"第 {page_index + 1} 页识别文本前 3 行: [无识别文本]")

            results.append({"page": page_index, "text": page_text})

        return results


def run_startup_self_check(config, app_logger=None):
    check_logger = app_logger or logger
    ocr_config = config.get("ocr", {})
    use_gpu = ocr_config.get("use_gpu", True)

    check_logger.info("启动前自检开始...")
    check_logger.info(f"配置项 use_gpu={use_gpu}")

    try:
        import onnxruntime as ort

        available_providers = ort.get_available_providers()
        device = ort.get_device()
        gpu_available = (
            device == "GPU" and "CUDAExecutionProvider" in available_providers
        )
        check_logger.info(
            f"GPU 可用性: {gpu_available} (device={device}, available_providers={available_providers})"
        )
    except Exception as exc:
        check_logger.warning(f"读取 ONNX Runtime 状态失败: {exc}")

    if CUDA_RUNTIME_BIN_DIRS:
        check_logger.info(f"CUDA DLL 搜索路径: {CUDA_RUNTIME_BIN_DIRS}")
    else:
        check_logger.warning("未检测到 nvidia/*/bin DLL 路径。")

    dll_paths = _collect_key_cuda_dll_paths()
    check_logger.info(f"关键 DLL 路径: {dll_paths}")

    ocr_processor = PDFOCRProcessor(config)
    check_logger.info(f"Provider 状态: {ocr_processor.get_provider_status()}")
    check_logger.info("启动前自检结束。")
    return ocr_processor
