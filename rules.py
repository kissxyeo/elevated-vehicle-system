# -*- coding: utf-8 -*-
"""高架道路通行规则。

规则依据常见城市高架道路管理要求整理：
- 小型汽车、大型客车允许通行；
- 货车、摩托车、非机动车、行人禁止驶入高架。
"""

# 高架限速（km/h）——仅作为页面提示，单张图片无法计算真实车速
SPEED_LIMIT = 100

# key 与 YOLO(COCO) 类别对应：car/bus/truck/motorcycle/bicycle/person
VEHICLE_RULES = {
    "car":        {"cn": "小型汽车", "allowed": True,  "reason": ""},
    "bus":        {"cn": "大型客车", "allowed": True,  "reason": ""},
    "truck":      {"cn": "货车",     "allowed": False, "reason": "货车禁止驶入高架"},
    "motorcycle": {"cn": "摩托车",   "allowed": False, "reason": "摩托车禁止驶入高架"},
    "bicycle":    {"cn": "非机动车", "allowed": False, "reason": "非机动车禁止驶入高架"},
    "person":     {"cn": "行人",     "allowed": False, "reason": "行人禁止进入高架"},
}

# 各类违规的罚款金额（元）
VIOLATION_FINES = {
    "货车禁止驶入高架":   200,
    "摩托车禁止驶入高架": 200,
    "非机动车禁止驶入高架": 50,
    "行人禁止进入高架":   50,
}

# 罚款冷却时间：同一车牌、同一违规在该时间内不重复罚款（小时）
FINE_COOLDOWN_HOURS = 24
