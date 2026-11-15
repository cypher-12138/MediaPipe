#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
手部追踪 —— OpenCV + MediaPipe
================================================================
读取本地摄像头，实时检测手部，把 **21 个关键点用红色实心圆点**标注出来，
并按需绘制骨骼连线。按 q 或 Esc 退出。

常用命令
--------
    python hand_tracker.py                       # 自动挑选摄像头，镜像显示
    python hand_tracker.py --camera 1            # 强制指定摄像头序号
    python hand_tracker.py --no-connections      # 只要红点，不要连线
    python hand_tracker.py --show-stats          # 额外显示 FPS 和左右手标签
    python hand_tracker.py --list-cameras        # 列出能打开的摄像头序号
    python hand_tracker.py --probe out.png       # 无窗口自检：抓一帧存图后退出
    python hand_tracker.py --selftest fake.png   # 用假关键点验证绘制逻辑
"""

from __future__ import annotations

import argparse
import sys
import time
from types import SimpleNamespace

import cv2
import mediapipe as mp
import numpy as np

# ---------------------------------------------------------------- 可调参数
DOT_COLOR = (0, 0, 255)        # BGR，纯红色 —— 检测点
LINE_COLOR = (0, 255, 0)       # BGR，绿色 —— 骨骼连线
DOT_RADIUS = 5                 # 红点半径（像素）
DOT_THICKNESS = -1             # -1 = 实心圆
LINE_THICKNESS = 2
WINDOW_NAME = "Hand Tracking  |  press q or ESC to quit"

# mediapipe 0.10.15 起移除了 mp.solutions。这里给可操作的报错，而不是一句 AttributeError。
if not hasattr(mp, "solutions"):
    raise SystemExit(
        f"当前 mediapipe {getattr(mp, '__version__', '未知版本')} 已移除 mp.solutions API。\n"
        "请按 requirements.txt 安装 0.10.14：\n"
        "  .venv\\Scripts\\python.exe -m pip install -r requirements.txt"
    )

MP_HANDS = mp.solutions.hands
HAND_CONNECTIONS = MP_HANDS.HAND_CONNECTIONS

# ---------------------------------------------------------------- 命令行
def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="OpenCV + MediaPipe 手部追踪，红色关键点标注",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    cam = parser.add_argument_group("摄像头")
    cam.add_argument("--camera", type=int, default=None,
                     help="摄像头序号；不填则自动挑选第一个能出画面的")
    cam.add_argument("--width", type=int, default=1280, help="采集宽度")
    cam.add_argument("--height", type=int, default=720, help="采集高度")
    cam.add_argument("--list-cameras", action="store_true", help="探测可用摄像头后退出")

    det = parser.add_argument_group("检测")
    det.add_argument("--max-hands", type=int, default=2, choices=(1, 2), help="最多同时检测几只手")
    det.add_argument("--model-complexity", type=int, default=1, choices=(0, 1),
                     help="0=更快更省 CPU，1=更准")
    det.add_argument("--min-detection-confidence", type=float, default=0.5, help="检测置信度阈值")
    det.add_argument("--min-tracking-confidence", type=float, default=0.5, help="跟踪置信度阈值")

    draw = parser.add_argument_group("绘制")
    draw.add_argument("--no-mirror", action="store_true", help="不水平翻转画面（默认镜像，像照镜子）")
    draw.add_argument("--no-connections", action="store_true", help="不画骨骼连线，只保留红色检测点")
    draw.add_argument("--dot-radius", type=int, default=DOT_RADIUS, help="红点半径")
    draw.add_argument("--show-stats", action="store_true", help="叠加显示 FPS 与左右手标签")

    misc = parser.add_argument_group("自检工具")
    misc.add_argument("--probe", nargs="?", const="probe_result.png", default=None, metavar="IMG",
                      help="无窗口模式：开摄像头抓几帧，存一张标注图后退出")
    misc.add_argument("--probe-frames", type=int, default=120, help="自检最多抓多少帧去找手")
    misc.add_argument("--selftest", default=None, metavar="IMG",
                      help="不碰摄像头，用假关键点渲染一张图，验证绘制代码")
    return parser.parse_args(argv)


# ---------------------------------------------------------------- 摄像头
def open_camera(index: int, width: int, height: int):
    """尝试打开摄像头。Windows 上优先 DirectShow，失败再退回默认后端。"""
    backends = []
    if sys.platform.startswith("win") and hasattr(cv2, "CAP_DSHOW"):
        backends.append(("DirectShow", cv2.CAP_DSHOW))
    backends.append(("默认后端", cv2.CAP_ANY))

    for name, api in backends:
        cap = cv2.VideoCapture(index, api)
        if not cap.isOpened():
            cap.release()
            continue
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        for _ in range(5):          # 预热，部分摄像头前几帧是黑的
            cap.read()
        ok, frame = cap.read()
        if ok and frame is not None:
            print(f"[摄像头] 已打开 index={index}（{name}），"
                  f"实际分辨率 {frame.shape[1]}x{frame.shape[0]}")
            return cap, frame.shape[1], frame.shape[0]
        cap.release()
    return None, 0, 0


def resolve_camera(index, width: int, height: int):
    """index 为 None 时自动扫描 0~5，返回第一个能打开并读到画面的摄像头。"""
    if index is not None:
        cap, _, _ = open_camera(index, width, height)
        return cap, index

    for candidate in range(6):
        cap, _, _ = open_camera(candidate, width, height)
        if cap is not None:
            if candidate != 0:
                print(f"[摄像头] 自动选择了 index={candidate}；想固定下来可加 --camera {candidate}")
            return cap, candidate
    return None, None


def camera_help(index) -> str:
    where = "自动扫描的所有序号" if index is None else f"index={index}"
    return (
        f"打不开摄像头（{where}）。请逐条排查：\n"
        "  1) 摄像头是否被微信 / 腾讯会议 / 浏览器 / OBS 占用？先关掉这些程序。\n"
        "  2) Windows 设置 → 隐私和安全性 → 相机，确认“允许应用访问相机”已开启。\n"
        "  3) 先跑 python hand_tracker.py --list-cameras，看哪些序号真的有画面。\n"
        "  4) 用 --camera N 指定序号，例如 python hand_tracker.py --camera 1。\n"
        "  5) 注意“OBS Virtual Camera”“Iriun Webcam”这类虚拟摄像头：\n"
        "     没接手机 / 没开 OBS 推流时，它们只会给你一张占位图（不是你的画面）。\n"
        "  6) 外接 USB 摄像头请插好后重新运行本程序。"
    )


def list_cameras(max_index: int = 6) -> int:
    found = []
    print(f"[探测] 正在扫描摄像头序号 0 ~ {max_index - 1} …")
    for idx in range(max_index):
        api = cv2.CAP_DSHOW if sys.platform.startswith("win") else cv2.CAP_ANY
        cap = cv2.VideoCapture(idx, api)
        ok = cap.isOpened() and cap.read()[0]
        cap.release()
        if ok:
            found.append(idx)
            print(f"   index={idx}  可用")
    if not found:
        print("[探测] 没有找到任何可用摄像头。\n" + camera_help(0))
        return 1
    print(f"[探测] 可用摄像头：{found}")
    print(f"[探测] 建议命令：python hand_tracker.py --camera {found[0]}")
    return 0


# ---------------------------------------------------------------- 绘制
def draw_landmarks(frame, hand_landmarks, *, draw_connections: bool = True,
                   dot_radius: int = DOT_RADIUS) -> list:
    """在 frame 上画绿色骨骼 + 红色关键点。先画线后画点，保证红点不被盖住。"""
    height, width = frame.shape[:2]
    points = [(int(lm.x * width), int(lm.y * height)) for lm in hand_landmarks.landmark]

    if draw_connections:
        for start, end in HAND_CONNECTIONS:
            cv2.line(frame, points[start], points[end], LINE_COLOR, LINE_THICKNESS, cv2.LINE_AA)

    for point in points:
        cv2.circle(frame, point, dot_radius, DOT_COLOR, DOT_THICKNESS, cv2.LINE_AA)

    return points


def draw_fps(frame, fps: float) -> None:
    text = f"FPS {fps:5.1f}"
    cv2.putText(frame, text, (12, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(frame, text, (12, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 1, cv2.LINE_AA)


def draw_hand_label(frame, points, label: str) -> None:
    x, y = points[0]                       # 手腕位置
    cv2.putText(frame, label, (x + 12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(frame, label, (x + 12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1, cv2.LINE_AA)


def create_detector(args):
    return MP_HANDS.Hands(
        static_image_mode=False,                       # 视频流模式，启用跟踪，速度更快
        max_num_hands=args.max_hands,
        model_complexity=args.model_complexity,
        min_detection_confidence=args.min_detection_confidence,
        min_tracking_confidence=args.min_tracking_confidence,
    )


# ---------------------------------------------------------------- 主循环
def run(args) -> int:
    cap, _ = resolve_camera(args.camera, args.width, args.height)
    if cap is None:
        print(camera_help(args.camera), file=sys.stderr)
        return 2

    detector = create_detector(args)
    mirror = not args.no_mirror
    draw_connections = not args.no_connections

    fps = 0.0
    last_time = time.perf_counter()
    fail_streak = 0

    print("[提示] 窗口已打开；把手放到画面里即可看到红色检测点。按 q 或 Esc 退出。")
    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                fail_streak += 1
                if fail_streak > 60:
                    print("[错误] 连续读不到画面，摄像头可能被拔出或被其他程序抢占。", file=sys.stderr)
                    return 3
                continue
            fail_streak = 0

            if mirror:
                frame = cv2.flip(frame, 1)

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            result = detector.process(rgb)

            if result.multi_hand_landmarks:
                labels = []
                if args.show_stats and result.multi_handedness:
                    labels = [h.classification[0].label for h in result.multi_handedness]
                for i, hand_landmarks in enumerate(result.multi_hand_landmarks):
                    points = draw_landmarks(frame, hand_landmarks,
                                            draw_connections=draw_connections,
                                            dot_radius=args.dot_radius)
                    if i < len(labels):
                        # 画面翻转后媒体管返回的左右手标签是反的，这里纠正回来
                        label = labels[i] if not mirror else ("Left" if labels[i] == "Right" else "Right")
                        draw_hand_label(frame, points, label)

            if args.show_stats:
                now = time.perf_counter()
                dt = now - last_time
                last_time = now
                if dt > 0:
                    instant = 1.0 / dt
                    fps = instant if fps == 0 else 0.9 * fps + 0.1 * instant
                draw_fps(frame, fps)

            cv2.imshow(WINDOW_NAME, frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q"), ord("Q")):
                break
            if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                break
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        detector.close()
        cv2.destroyAllWindows()
        print("[退出] 摄像头已释放。")
    return 0


# ---------------------------------------------------------------- 自检：真实摄像头
def probe(args) -> int:
    "无窗口跑一段真实摄像头画面，存一张标注结果图，用于确认整条链路可用。"
    output = args.probe
    cap, _ = resolve_camera(args.camera, args.width, args.height)
    if cap is None:
        print(camera_help(args.camera), file=sys.stderr)
        return 2

    detector = create_detector(args)
    mirror = not args.no_mirror
    draw_connections = not args.no_connections
    frames = 0
    snapshot = None
    total_points = 0

    try:
        for _ in range(args.probe_frames):
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            frames += 1
            if mirror:
                frame = cv2.flip(frame, 1)
            snapshot = frame.copy()
            result = detector.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            if result.multi_hand_landmarks:
                total_points = 0
                for hand_landmarks in result.multi_hand_landmarks:
                    total_points += len(draw_landmarks(snapshot, hand_landmarks,
                                                       draw_connections=draw_connections,
                                                       dot_radius=args.dot_radius))
                break
    finally:
        cap.release()
        detector.close()

    if snapshot is None:
        print("[自检] 摄像头一帧都没读出来。", file=sys.stderr)
        return 3

    saved = cv2.imwrite(output, snapshot)
    print(f"[自检] 读取 {frames} 帧；手部关键点 {total_points} 个"
          f"（{'检测到手' if total_points else '未检测到手，把手放进画面再试'}）；"
          f"结果图已保存 {output if saved else '失败'}：{output}")
    return 0


# ---------------------------------------------------------------- 自检：假关键点渲染
def selftest(path: str) -> int:
    "不依赖摄像头和真人手，用一组假关键点走一遍绘制流程。"
    width, height = 960, 540
    frame = np.full((height, width, 3), 40, dtype=np.uint8)

    # 一个手掌形状的 21 点（归一化坐标 0~1）：0 手腕，1-4 拇指，5-8 食指，9-12 中指，13-16 无名指，17-20 小指
    coords = [
        (0.50, 0.85),
        (0.42, 0.72), (0.36, 0.62), (0.32, 0.54), (0.29, 0.47),
        (0.45, 0.52), (0.43, 0.40), (0.42, 0.33), (0.41, 0.27),
        (0.53, 0.50), (0.53, 0.36), (0.53, 0.28), (0.53, 0.21),
        (0.61, 0.52), (0.63, 0.39), (0.64, 0.32), (0.65, 0.26),
        (0.68, 0.57), (0.73, 0.48), (0.76, 0.43), (0.79, 0.38),
    ]
    fake = SimpleNamespace(landmark=[SimpleNamespace(x=x, y=y) for x, y in coords])
    count = len(draw_landmarks(frame, fake, draw_connections=True))

    cv2.putText(frame, f"selftest: {count} red dots", (16, 36),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)
    saved = cv2.imwrite(path, frame)
    print(f"[自检] 画出 {count} 个红点 + {len(HAND_CONNECTIONS)} 条连线；"
          f"保存{'成功' if saved else '失败'}：{path}")
    return 0 if saved and count == 21 else 1


# ---------------------------------------------------------------- 入口
def main(argv=None) -> int:
    args = parse_args(argv)
    if args.selftest:
        return selftest(args.selftest)
    if args.list_cameras:
        return list_cameras()
    if args.probe is not None:
        return probe(args)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
