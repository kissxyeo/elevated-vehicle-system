---
title: 高架车辆智能识别系统
emoji: 🚗
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# 高架车辆智能识别系统

基于 Flask + YOLOv8 + HyperLPR3 的高架车辆识别与违章告警演示系统。

## 功能

- 图片识别：YOLOv8 检测车辆，HyperLPR3 识别车牌，按车型规则判定是否允许上高架
- 视频识别：后台任务逐帧检测，前端轮询进度
- 违章记录：超速/限行等规则判定、罚款金额与 24 小时冷却计算
- 数据统计：按日、按小时的识别与违章统计（管理员）
- 用户中心：绑定车牌、查看本人违章记录

## 演示账号

| 角色 | 账号 | 密码 |
| --- | --- | --- |
| 管理员 | admin | gaojia123 |
| 普通用户 | user | user123 |

## 部署说明

容器使用 gunicorn 单 worker 启动（视频任务是进程内作业，多 worker 会查不到任务），监听 7860 端口。

Hugging Face Spaces 免费 CPU 实例的磁盘为临时存储，重启后 SQLite 数据与上传的图片会被清空；如需持久化请挂载持久磁盘或改用带持久盘的平台。
