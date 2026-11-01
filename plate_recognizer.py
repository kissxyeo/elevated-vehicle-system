# -*- coding: utf-8 -*-
"""车牌识别模块（HyperLPR3）

HyperLPR3 是开源的中文车牌识别库，内置车牌检测 + OCR 模型，
可直接在整张图片上输出车牌号、置信度与车牌框。
若环境未安装 hyperlpr3，则返回空结果并在页面标注“车牌识别不可用”，不会伪造车牌。
"""
import os
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE_DIR, "models", "hyperlpr3")


class PlateRecognizer:
    def __init__(self):
        self.mode = "unavailable"
        self.error = ""
        self._catcher = None
        try:
            from hyperlpr3 import LicensePlateCatcher
            self._catcher = LicensePlateCatcher(folder=MODEL_DIR)
            self.mode = "hyperlpr3"
            print("[plate] HyperLPR3 loaded")
        except Exception as e:  # 未安装或模型不可用时降级
            self.error = str(e)
            print("[plate] HyperLPR3 unavailable (%s)" % e)

    def detect(self, image_bgr):
        """
        识别整张图片中的所有车牌。

        :param image_bgr: numpy.ndarray，BGR 格式
        :return: [{"plate_no": str, "confidence": float, "bbox": [x1,y1,x2,y2]}, ...]
        """
        if not self._catcher:
            return []
        try:
            raw = self._catcher(image_bgr)
        except Exception as e:
            print("[plate] recognize error: %s" % e)
            return []

        results = []
        for item in raw or []:
            parsed = _parse_item(item)
            if parsed:
                results.append(parsed)
        return results


def _parse_item(item):
    """兼容不同版本 HyperLPR3 的返回结构"""
    code = confidence = box = None
    if isinstance(item, dict):
        code = item.get("code") or item.get("plate_no") or item.get("text")
        confidence = item.get("confidence") or item.get("conf") or item.get("score")
        box = item.get("box") or item.get("bbox")
    elif isinstance(item, (list, tuple)):
        # 常见形式: (code, confidence, type_idx, box)
        for part in item:
            if isinstance(part, str) and code is None:
                code = part
            elif isinstance(part, (int, float)) and confidence is None and 0 <= float(part) <= 1:
                confidence = float(part)
            elif isinstance(part, (list, tuple)) and len(part) == 4 and all(
                    isinstance(v, (int, float)) for v in part):
                box = list(part)
    if not code:
        return None
    code = normalize_plate(code)
    if not code or len(code) < 6:
        return None
    bbox = None
    if box is not None:
        try:
            bbox = [int(round(float(v))) for v in box]
        except Exception:
            bbox = None
    return {
        "plate_no": code,
        "confidence": round(float(confidence), 3) if confidence is not None else 0.0,
        "bbox": bbox,
    }


def normalize_plate(text):
    """去掉分隔符与空白，统一大写"""
    if not text:
        return ""
    text = str(text).upper()
    text = re.sub(r"[·•\.\-\s:：]", "", text)
    return text.strip()


def assign_plates(plates, detections, expand=12):
    """把车牌按位置归属到车辆检测框内（取置信度最高者）"""
    for det in detections:
        x1, y1, x2, y2 = det["bbox"]
        best = None
        for p in plates:
            if not p.get("bbox"):
                continue
            px1, py1, px2, py2 = p["bbox"]
            cx, cy = (px1 + px2) / 2.0, (py1 + py2) / 2.0
            if x1 - expand <= cx <= x2 + expand and y1 - expand <= cy <= y2 + expand:
                if best is None or p["confidence"] > best["confidence"]:
                    best = p
        det["plate_no"] = best["plate_no"] if best else ""
        det["plate_confidence"] = best["confidence"] if best else 0.0
        det["plate_bbox"] = best["bbox"] if best else None
    return detections
