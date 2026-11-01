# -*- coding: utf-8 -*-
"""YOLO 车辆检测模块（ultralytics YOLOv8）

首次运行会自动下载 yolov8n.pt 权重（约 6MB）到 models/ 目录。
若环境缺少 ultralytics/torch，则降级为模拟检测器，页面会明确标注“模拟检测模式”。
"""
import os
import random

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE_DIR, "models")
MODEL_PATH = os.path.join(MODEL_DIR, "yolov8n.pt")

# COCO 类别 -> 系统车辆类别 key（其余类别不参与高架检测）
COCO_MAP = {
    0: "person",      # 行人
    1: "bicycle",     # 自行车/非机动车
    2: "car",         # 小汽车
    3: "motorcycle",  # 摩托车
    5: "bus",         # 公交/大巴
    7: "truck",       # 卡车
}


class YOLODetector:
    """真实 YOLO 检测器（ultralytics）"""

    mode = "yolo"

    def __init__(self, weights=MODEL_PATH):
        from ultralytics import YOLO  # 延迟导入，未安装时由 get_detector 降级
        os.makedirs(MODEL_DIR, exist_ok=True)
        self.model = YOLO(weights)

    def detect(self, image, conf=0.30):
        """
        :param image: PIL.Image（RGB）
        :param conf: 置信度阈值
        :return: [{"class_key", "confidence", "bbox": [x1,y1,x2,y2]}, ...]
        """
        # 提高基础阈值到 0.30，减少误检；调整 NMS 阈值避免同类合并
        result = self.model.predict(
            image, verbose=False, conf=conf, imgsz=640,
            iou=0.45,  # NMS IoU 阈值，降低可减少同类合并
            max_det=50,  # 最大检测数
        )[0]
        detections = []
        for box in result.boxes:
            cid = int(box.cls.item())
            if cid not in COCO_MAP:
                continue
            class_key = COCO_MAP[cid]
            box_conf = float(box.conf.item())
            # 货车、摩托车使用稍高阈值，减少误检
            strict_keys = {"truck", "motorcycle"}
            if class_key in strict_keys and box_conf < 0.35:
                continue
            detections.append({
                "class_key": class_key,
                "confidence": round(box_conf, 3),
                "bbox": [int(v) for v in box.xyxy[0].tolist()],
            })
        # 后处理：去重、修正误分类
        detections = self._merge_overlapping_motorcycles(detections)
        detections = self._remove_rider_persons(detections)
        # 骑手转换后可能产生新的重叠摩托车，再次合并
        detections = self._merge_overlapping_motorcycles(detections)
        detections = self._fix_truck_misclassifications(detections)
        return detections

    @staticmethod
    def _merge_overlapping_motorcycles(detections):
        """合并重叠的摩托车框（骑手和车分开检测的情况）"""
        motorcycles = [d for d in detections if d["class_key"] == "motorcycle"]
        if len(motorcycles) < 2:
            return detections
        # 按置信度排序，从高到低
        motorcycles.sort(key=lambda x: x["confidence"], reverse=True)
        keep = []
        used = set()
        for i, m1 in enumerate(motorcycles):
            if i in used:
                continue
            keep.append(m1)
            for j, m2 in enumerate(motorcycles[i+1:], start=i+1):
                if j in used:
                    continue
                # 如果两个摩托车框重叠度高，认为是同一辆
                if YOLODetector._iou(m1["bbox"], m2["bbox"]) > 0.3:
                    used.add(j)
        # 重建结果
        result = [d for d in detections if d["class_key"] != "motorcycle"]
        result.extend(keep)
        return result

    @staticmethod
    def _remove_rider_persons(detections):
        """把骑手（person）重新分类为摩托车，或删除与摩托车重叠的行人框"""
        motorcycles = [d for d in detections if d["class_key"] == "motorcycle"]
        persons = [d for d in detections if d["class_key"] == "person"]
        if not persons:
            return detections
        
        # 策略1：如果行人框底部与摩托车重叠，把行人改为摩托车
        for p in persons:
            for m in motorcycles:
                # 检查行人框底部是否与摩托车框重叠
                p_bottom = p["bbox"][3]  # y2
                m_top = m["bbox"][1]     # y1
                # 计算水平重叠
                x_overlap = max(0, min(p["bbox"][2], m["bbox"][2]) - max(p["bbox"][0], m["bbox"][0]))
                p_width = p["bbox"][2] - p["bbox"][0]
                x_overlap_ratio = x_overlap / p_width if p_width > 0 else 0
                # 条件：底部重叠 + 水平重叠超过50% 或 IoU > 0.03
                if p_bottom > m_top and (x_overlap_ratio > 0.5 or YOLODetector._iou(p["bbox"], m["bbox"]) > 0.03):
                    # 骑手在摩托车上，把行人框改为摩托车
                    p["class_key"] = "motorcycle"
                    p["confidence"] = max(p["confidence"], m["confidence"])
                    # 扩展框包含整个摩托车
                    p["bbox"] = [
                        min(p["bbox"][0], m["bbox"][0]),
                        min(p["bbox"][1], m["bbox"][1]),
                        max(p["bbox"][2], m["bbox"][2]),
                        max(p["bbox"][3], m["bbox"][3]),
                    ]
                    break
        
        # 策略2：删除仍然是 person 且与摩托车重叠的框
        filtered = []
        for d in detections:
            if d["class_key"] == "person":
                if any(YOLODetector._iou(d["bbox"], m["bbox"]) > 0.1 for m in motorcycles):
                    continue
            filtered.append(d)
        return filtered

    @staticmethod
    def _fix_truck_misclassifications(detections):
        """修正被误检为货车的轿车（小目标、重叠目标）"""
        cars = [d for d in detections if d["class_key"] == "car"]
        trucks = [d for d in detections if d["class_key"] == "truck"]
        if not trucks:
            return detections
        # 检查每个货车框，如果与轿车框高度重叠，且轿车置信度更高，则改为轿车
        for t in trucks:
            best_car = None
            best_iou = 0
            for c in cars:
                iou = YOLODetector._iou(t["bbox"], c["bbox"])
                if iou > 0.5 and iou > best_iou:
                    best_iou = iou
                    best_car = c
            if best_car and best_car["confidence"] > t["confidence"]:
                # 轿车置信度更高，把货车改为轿车
                t["class_key"] = "car"
        # 去重：同一位置多个框只保留一个
        return YOLODetector._nms_per_class(detections, iou_threshold=0.5)

    @staticmethod
    def _nms_per_class(detections, iou_threshold=0.5):
        """对每个类别单独做 NMS"""
        by_class = {}
        for d in detections:
            by_class.setdefault(d["class_key"], []).append(d)
        result = []
        for cls, items in by_class.items():
            items.sort(key=lambda x: x["confidence"], reverse=True)
            keep = []
            while items:
                best = items.pop(0)
                keep.append(best)
                items = [i for i in items if YOLODetector._iou(best["bbox"], i["bbox"]) < iou_threshold]
            result.extend(keep)
        return result

    @staticmethod
    def _iou(box1, box2):
        """计算两个框的 IoU"""
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
        area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
        return inter / (area1 + area2 - inter) if (area1 + area2 - inter) > 0 else 0


class SimulatedDetector:
    """模拟检测器：仅在缺少 ultralytics/torch 时作为演示兜底，页面上会明确提示"""

    mode = "simulated"

    _CLASS_POOL = (
        ["car", "bus", "truck", "motorcycle", "bicycle", "person"],
        [50, 10, 15, 10, 5, 10],
    )

    def detect(self, image, conf=0.35):
        w, h = image.size
        slots = [
            (0.03, 0.05, 0.48, 0.55),
            (0.52, 0.05, 0.97, 0.55),
            (0.03, 0.55, 0.48, 0.97),
            (0.52, 0.55, 0.97, 0.97),
        ]
        chosen = random.sample(slots, random.randint(1, 4))
        classes, weights = self._CLASS_POOL
        detections = []
        for sx1, sy1, sx2, sy2 in chosen:
            key = random.choices(classes, weights=weights, k=1)[0]
            fx1, fy1 = random.uniform(0.05, 0.20), random.uniform(0.05, 0.20)
            fx2, fy2 = random.uniform(0.60, 0.90), random.uniform(0.60, 0.90)
            detections.append({
                "class_key": key,
                "confidence": round(random.uniform(0.62, 0.96), 2),
                "bbox": [
                    int((sx1 + (sx2 - sx1) * fx1) * w),
                    int((sy1 + (sy2 - sy1) * fy1) * h),
                    int((sx1 + (sx2 - sx1) * fx2) * w),
                    int((sy1 + (sy2 - sy1) * fy2) * h),
                ],
            })
        return detections


def get_detector():
    """优先加载真实 YOLO 模型，失败则降级为模拟检测器"""
    try:
        d = YOLODetector()
        print("[detector] YOLOv8n loaded, REAL detection mode")
        return d
    except Exception as e:
        print("[detector] YOLO unavailable (%s), fallback to SIMULATED mode" % e)
        return SimulatedDetector()
