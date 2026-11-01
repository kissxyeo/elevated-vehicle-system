# -*- coding: utf-8 -*-
"""识别分析服务：YOLO 检测 + 车牌识别 + 规则判定 + 落库/短信通知"""
import os
import threading
from datetime import datetime
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import database as db
from plate_recognizer import assign_plates
from rules import VEHICLE_RULES

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

COLOR_OK = (22, 163, 74)
COLOR_BAD = (220, 38, 38)


@lru_cache(maxsize=8)
def load_font(size):
    """加载中文字体，返回 (font, 是否支持中文)"""
    for p in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size), True
            except Exception:
                pass
    try:
        return ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", size), False
    except Exception:
        return ImageFont.load_default(), False


class Analyzer:
    def __init__(self, detector, plate_recognizer, sms_service):
        self.detector = detector
        self.plate_recognizer = plate_recognizer
        self.sms = sms_service
        self.lock = threading.Lock()  # PyTorch 模型串行推理，避免多线程冲突

    def analyze(self, image):
        """对一张 PIL 图片做完整分析，返回带规则与车牌信息的检测结果"""
        with self.lock:
            detections = self.detector.detect(image)

            if detections and self.plate_recognizer.mode != "unavailable":
                bgr = np.array(image)[:, :, ::-1].copy()  # PIL RGB -> BGR
                plates = self.plate_recognizer.detect(bgr)
                assign_plates(plates, detections)
            else:
                for d in detections:
                    d.setdefault("plate_no", "")
                    d.setdefault("plate_confidence", 0.0)

        for d in detections:
            rule = VEHICLE_RULES[d["class_key"]]
            d["vehicle_type"] = rule["cn"]
            d["allowed"] = rule["allowed"]
            d["violation"] = "" if rule["allowed"] else rule["reason"]
        return detections

    def persist(self, item, source, image_name, created_at):
        """把单个识别结果写入数据库，并在违规时通知车主"""
        plate = item.get("plate_no", "")
        vehicle = db.get_vehicle_by_plate(plate)
        owner = db.get_owner(vehicle["owner_id"]) if vehicle else None
        violation = item.get("violation", "")

        rec_id = db.add_record({
            "image": image_name,
            "plate_no": plate,
            "vehicle_type": item["vehicle_type"],
            "confidence": item.get("confidence", 0),
            "plate_confidence": item.get("plate_confidence", 0),
            "allowed": 1 if item.get("allowed") else 0,
            "violation": violation,
            "notified": 0,
            "source": source,
            "created_at": created_at,
        })

        notified = 1 if violation else 0
        if violation:
            if owner:
                ok, status, content = self.sms.send_violation_sms(
                    owner["phone"], owner["name"], plate, violation, created_at)
                if ok:
                    notified = 1
                    db.update_record_notified(rec_id, 1)
                    db.add_notification({
                        "record_id": rec_id, "plate_no": plate,
                        "phone": owner["phone"], "owner_name": owner["name"],
                        "content": content, "status": status, "created_at": created_at,
                    })
                else:
                    notified = 0
            else:
                notified = 2

        item["record_id"] = rec_id
        item["owner_name"] = owner["name"] if owner else "未登记"
        item["owner_phone"] = owner["phone"] if owner else ""
        item["notified"] = notified
        return item


def draw_annotations(image, items, title="高架车辆智能识别"):
    """在图片上绘制检测框、车型、车牌与通行结论"""
    img = image.copy()
    draw = ImageDraw.Draw(img)
    lw = max(3, img.width // 400)
    fs = max(15, img.width // 55)
    font, cn_ok = load_font(fs)
    line_h = fs + 6

    for r in items:
        x1, y1, x2, y2 = [int(v) for v in r["bbox"]]
        color = COLOR_OK if r.get("allowed") else COLOR_BAD
        draw.rectangle([x1, y1, x2, y2], outline=color, width=lw)

        line1 = "%s %.0f%%" % (r["vehicle_type"], r.get("confidence", 0) * 100)
        line2 = "%s | %s" % (r.get("plate_no") or "车牌未识别",
                             "允许上高架" if r.get("allowed") else "禁止上高架")
        if not cn_ok:
            line2 = "%s | %s" % (r.get("plate_no") or "NO PLATE",
                                 "PASS" if r.get("allowed") else "BANNED")

        tw = max(draw.textlength(line1, font=font), draw.textlength(line2, font=font))
        box_h = line_h * 2 + 6
        ty = y1 - box_h - 4
        if ty < 0:
            ty = min(y2 + 4, img.height - box_h)
        draw.rectangle([x1, ty, x1 + tw + 12, ty + box_h], fill=color)
        draw.text((x1 + 6, ty + 3), line1, fill="white", font=font)
        draw.text((x1 + 6, ty + 3 + line_h), line2, fill="white", font=font)

    # 左上角信息条
    fs2 = max(14, img.width // 60)
    font2, cn2 = load_font(fs2)
    banned = sum(1 for r in items if not r.get("allowed"))
    text = "%s  |  目标 %d  违规 %d" % (title if cn2 else "ELEVATED VEHICLE AI",
                                        len(items), banned)
    pad = 8
    tw = draw.textlength(text, font=font2)
    draw.rectangle([0, 0, int(tw) + pad * 2, fs2 + pad * 2], fill=(15, 15, 15))
    draw.text((pad, pad), text, fill="white", font=font2)
    return img


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
