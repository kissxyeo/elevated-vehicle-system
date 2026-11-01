# -*- coding: utf-8 -*-
"""视频识别：逐帧 YOLO 检测、简易 IoU 跟踪、生成标注视频与识别结果"""
import copy
import os
import threading
import time
import uuid

import cv2
import numpy as np
from PIL import Image

from analyzer import Analyzer, draw_annotations, now_str

MAX_SECONDS = 60          # 单次最多处理 60 秒，避免 CPU 推理过久
MAX_WIDTH = 960           # 标注视频最大宽度
DETECT_INTERVAL_SEC = 0.5  # 每 0.5 秒做一次检测
TRACK_TTL = 1.6           # 目标消失后保留框的时长（秒）


def _iou(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter == 0:
        return 0.0
    area_a = max(1, (ax2 - ax1) * (ay2 - ay1))
    area_b = max(1, (bx2 - bx1) * (by2 - by1))
    return inter / float(area_a + area_b - inter)


def _update_tracks(tracks, detections, t):
    used = set()
    for det in detections:
        best, best_iou = None, 0.0
        for tr in tracks:
            if tr["tid"] in used:
                continue
            if t - tr["last"] > TRACK_TTL * 2:
                continue
            score = _iou(tr["bbox"], det["bbox"])
            if score > best_iou:
                best, best_iou = tr, score
        if best is not None and best_iou >= 0.25:
            best["bbox"] = det["bbox"]
            best["last"] = t
            best["hits"] += 1
            if det["confidence"] > best["confidence"]:
                best["confidence"] = det["confidence"]
                best["class_key"] = det["class_key"]
                best["vehicle_type"] = det["vehicle_type"]
                best["allowed"] = det["allowed"]
                best["violation"] = det["violation"]
            if det.get("plate_no") and det.get("plate_confidence", 0) >= best["plate_confidence"]:
                best["plate_no"] = det["plate_no"]
                best["plate_confidence"] = det.get("plate_confidence", 0)
            used.add(best["tid"])
        else:
            tracks.append({
                "tid": len(tracks) + 1,
                "bbox": det["bbox"],
                "class_key": det["class_key"],
                "vehicle_type": det["vehicle_type"],
                "allowed": det["allowed"],
                "violation": det["violation"],
                "confidence": det["confidence"],
                "plate_no": det.get("plate_no", ""),
                "plate_confidence": det.get("plate_confidence", 0),
                "hits": 1,
                "first": t,
                "last": t,
            })


class VideoJobManager:
    def __init__(self, analyzer: Analyzer, upload_dir):
        self.analyzer = analyzer
        self.upload_dir = upload_dir
        self.jobs = {}
        self.lock = threading.Lock()

    def start(self, src_path):
        job_id = uuid.uuid4().hex[:12]
        with self.lock:
            self.jobs[job_id] = {
                "id": job_id, "status": "running", "progress": 0,
                "message": "正在识别…", "result": None, "error": "",
            }
        th = threading.Thread(target=self._run, args=(job_id, src_path), daemon=True)
        th.start()
        return job_id

    def get(self, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            return copy.deepcopy(job) if job else None

    def _update(self, job_id, **kw):
        with self.lock:
            if job_id in self.jobs:
                self.jobs[job_id].update(kw)

    def _run(self, job_id, src_path):
        started = time.time()
        cap = None
        writer = None
        try:
            cap = cv2.VideoCapture(src_path)
            if not cap.isOpened():
                raise RuntimeError("无法打开视频文件，请确认格式为 MP4/AVI/MOV/MKV")

            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            if fps <= 1 or fps > 120:
                fps = 25.0
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            max_frames = int(min(total, fps * MAX_SECONDS)) if total > 0 else int(fps * MAX_SECONDS)

            ok, frame = cap.read()
            if not ok:
                raise RuntimeError("视频中没有可读取的画面")
            h, w = frame.shape[:2]
            if w > MAX_WIDTH:
                scale = MAX_WIDTH / float(w)
                w, h = int(w * scale), int(h * scale)
            w, h = w - (w % 2), h - (h % 2)

            base = "ann_%s" % uuid.uuid4().hex[:12]
            fourccs = [("VP80", ".webm"), ("VP90", ".webm"), ("avc1", ".mp4"), ("mp4v", ".mp4")]
            out_name_actual = ""
            for cc, ext in fourccs:
                candidate = os.path.join(self.upload_dir, base + ext)
                writer = cv2.VideoWriter(candidate, cv2.VideoWriter_fourcc(*cc), fps, (w, h))
                if writer.isOpened():
                    out_name_actual = base + ext
                    break
                writer.release()
                writer = None
            if writer is None:
                raise RuntimeError("当前 OpenCV 无法创建视频编码器")

            interval = max(1, int(round(fps * DETECT_INTERVAL_SEC)))
            tracks = []
            idx = 0
            processed_infer = 0
            poster_img = None
            poster_score = -1

            while idx < max_frames:
                if idx == 0:
                    frame = cv2.resize(frame, (w, h))
                else:
                    ok, frame = cap.read()
                    if not ok:
                        break
                    if frame.shape[1] != w or frame.shape[0] != h:
                        frame = cv2.resize(frame, (w, h))

                t = idx / fps
                if idx % interval == 0:
                    pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                    dets = self.analyzer.analyze(pil)
                    processed_infer += 1
                    _update_tracks(tracks, dets, t)
                    if len(dets) > poster_score:
                        poster_img = draw_annotations(pil, dets)
                        poster_score = len(dets)

                active = [tr for tr in tracks if t - tr["last"] <= TRACK_TTL]
                if active:
                    pil_frame = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                    ann = draw_annotations(pil_frame, active)
                    frame_out = cv2.cvtColor(np.array(ann), cv2.COLOR_RGB2BGR)
                else:
                    frame_out = frame
                writer.write(frame_out)
                idx += 1

                if idx % 10 == 0 or idx == max_frames:
                    pct = int(idx / max(1, max_frames) * 100)
                    self._update(job_id, progress=min(99, pct),
                                 message="正在识别… %d%%（已处理 %d/%d 帧）" % (min(99, pct), idx, max_frames))

            writer.release()
            writer = None
            cap.release()
            cap = None

            # 只保留持续出现或识别到车牌的目标
            final_tracks = [tr for tr in tracks if tr["hits"] >= 2 or tr["plate_no"]]
            final_tracks.sort(key=lambda x: (-x["hits"], x["first"]))

            poster_name = "poster_%s.jpg" % uuid.uuid4().hex[:12]
            if poster_img is not None:
                poster_img.save(os.path.join(self.upload_dir, poster_name), quality=90)

            created_at = now_str()
            results = []
            for tr in final_tracks:
                item = {k: tr[k] for k in (
                    "bbox", "vehicle_type", "allowed", "violation", "confidence",
                    "plate_no", "plate_confidence")}
                self.analyzer.persist(item, "video", poster_name, created_at)
                results.append({
                    "record_id": item["record_id"],
                    "plate_no": item["plate_no"],
                    "vehicle_type": item["vehicle_type"],
                    "allowed": item["allowed"],
                    "violation": item["violation"],
                    "confidence": item["confidence"],
                    "plate_confidence": item["plate_confidence"],
                    "owner_name": item["owner_name"],
                    "owner_phone": item["owner_phone"],
                    "notified": item["notified"],
                    "hits": tr["hits"],
                    "first_seen": round(tr["first"], 1),
                    "last_seen": round(tr["last"], 1),
                })

            violations = sum(1 for r in results if r["violation"])
            result = {
                "video_url": "/static/uploads/" + out_name_actual,
                "poster_url": "/static/uploads/" + poster_name if poster_img is not None else "",
                "tracks": results,
                "summary": {
                    "vehicles": len(results),
                    "allowed": len(results) - violations,
                    "violations": violations,
                },
                "video_info": {
                    "fps": round(fps, 1),
                    "duration": round(idx / fps, 1),
                    "frames": idx,
                    "processed": processed_infer,
                    "truncated": bool(total and total > max_frames),
                },
                "elapsed": round(time.time() - started, 1),
            }
            self._update(job_id, status="done", progress=100, message="识别完成", result=result)
        except Exception as e:
            if writer is not None:
                writer.release()
            if cap is not None:
                cap.release()
            self._update(job_id, status="error", message="识别失败", error=str(e))
        finally:
            try:
                os.remove(src_path)
            except Exception:
                pass
