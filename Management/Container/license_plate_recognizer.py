import os
import re
import sys
from pathlib import Path


DETECT_MODEL = None
RECOGNITION_MODEL = None
MODEL_DEVICE = None


def normalize_plate(text):
    return re.sub(r'[^0-9A-Z\u4e00-\u9fff]', '', (text or '').strip().upper())


def _project_root():
    return Path(__file__).resolve().parents[2]


def _detect_project_dir():
    configured = os.environ.get('CTMS_LPR_PROJECT_DIR')
    if configured:
        return Path(configured)
    return (
        _project_root()
        / 'detect'
        / 'YOLOv5-LPRNet-Licence-Recognition-master'
        / 'YOLOv5-LPRNet-Licence-Recognition-master'
    )


def _default_detection_weights():
    configured = os.environ.get('CTMS_YOLOV5_PLATE_WEIGHTS')
    if configured:
        return Path(configured)
    return _detect_project_dir() / 'weights' / 'yolov5_best.pt'


def _default_recognition_weights():
    configured = os.environ.get('CTMS_LPRNET_WEIGHTS')
    if configured:
        return Path(configured)
    return _detect_project_dir() / 'weights' / 'lprnet_best.pth'


def _ensure_detect_project_on_path():
    project_dir = _detect_project_dir()
    if not project_dir.exists():
        raise RuntimeError(f'未找到车牌识别项目目录：{project_dir}')
    project_dir_text = str(project_dir)
    if project_dir_text not in sys.path:
        sys.path.insert(0, project_dir_text)
    return project_dir


def _imports():
    _ensure_detect_project_on_path()
    try:
        import cv2
        import numpy as np
        import torch
        from models.LPRNet import CHARS, LPRNet
        from models.experimental import Ensemble
        from utils.datasets import letterbox
        from utils.utils import check_img_size, non_max_suppression, scale_coords, transform
    except ImportError as exc:
        raise RuntimeError('当前环境缺少 YOLOv5/LPRNet 依赖，请安装 torch、torchvision、opencv-python、numpy、PyYAML 等依赖') from exc
    return cv2, np, torch, CHARS, LPRNet, Ensemble, letterbox, check_img_size, non_max_suppression, scale_coords, transform


def _device(torch):
    requested = (os.environ.get('CTMS_PLATE_DEVICE') or '').strip()
    if requested:
        return torch.device(requested)
    return torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')


def _torch_load(torch, path, map_location):
    try:
        return torch.load(str(path), map_location=map_location, weights_only=False)
    except TypeError:
        return torch.load(str(path), map_location=map_location)


def _load_yolov5_model(torch, Ensemble):
    weights = _default_detection_weights()
    if not weights.exists():
        raise RuntimeError(f'未找到 YOLOv5 车牌检测权重：{weights}')

    checkpoint = _torch_load(torch, weights, map_location=MODEL_DEVICE)
    model = checkpoint['model'].float().fuse().eval()
    return model.to(MODEL_DEVICE)


def _load_lprnet_model(torch, CHARS, LPRNet):
    weights = _default_recognition_weights()
    if not weights.exists():
        raise RuntimeError(f'未找到 LPRNet 车牌识别权重：{weights}')

    model = LPRNet(lpr_max_len=8, phase=False, class_num=len(CHARS), dropout_rate=0)
    state = _torch_load(torch, weights, map_location=torch.device('cpu'))
    model.load_state_dict(state)
    return model.to(MODEL_DEVICE).eval()


def _load_models():
    global DETECT_MODEL, MODEL_DEVICE, RECOGNITION_MODEL
    cv2, np, torch, CHARS, LPRNet, Ensemble, letterbox, check_img_size, non_max_suppression, scale_coords, transform = _imports()
    if MODEL_DEVICE is None:
        MODEL_DEVICE = _device(torch)
    if DETECT_MODEL is None:
        DETECT_MODEL = _load_yolov5_model(torch, Ensemble)
    if RECOGNITION_MODEL is None:
        RECOGNITION_MODEL = _load_lprnet_model(torch, CHARS, LPRNet)
    return cv2, np, torch, CHARS, letterbox, check_img_size, non_max_suppression, scale_coords, transform


def _decode_lprnet_prediction(np, CHARS, prediction):
    prediction = prediction.cpu().detach().numpy()
    labels = []
    for idx in range(prediction.shape[1]):
        labels.append(int(np.argmax(prediction[:, idx], axis=0)))

    decoded = []
    previous = labels[0] if labels else len(CHARS) - 1
    if labels and previous != len(CHARS) - 1:
        decoded.append(previous)
    for current in labels:
        if previous == current or current == len(CHARS) - 1:
            if current == len(CHARS) - 1:
                previous = current
            continue
        decoded.append(current)
        previous = current
    return normalize_plate(''.join(CHARS[item] for item in decoded))


def _recognize_crop(cv2, np, torch, CHARS, transform, image):
    if image.size == 0:
        return ''
    resized = cv2.resize(image, (94, 24))
    tensor = torch.Tensor([transform(resized)]).to(MODEL_DEVICE)
    with torch.no_grad():
        prediction = RECOGNITION_MODEL(tensor)[0]
    return _decode_lprnet_prediction(np, CHARS, prediction)


def _read_image(cv2, np, image_path):
    path = Path(image_path)
    if not path.exists():
        raise RuntimeError(f'图片文件不存在：{image_path}')
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        raise RuntimeError(f'图片文件为空：{image_path}')
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f'图片解码失败：{image_path}')
    return image


def recognize_plate(image_path):
    cv2, np, torch, CHARS, letterbox, check_img_size, non_max_suppression, scale_coords, transform = _load_models()
    image = _read_image(cv2, np, image_path)

    img_size = int(os.environ.get('CTMS_PLATE_IMG_SIZE') or 640)
    conf_thres = float(os.environ.get('CTMS_PLATE_CONF_THRES') or 0.4)
    iou_thres = float(os.environ.get('CTMS_PLATE_IOU_THRES') or 0.5)
    stride = int(DETECT_MODEL.stride.max()) if hasattr(DETECT_MODEL, 'stride') else 32
    img_size = check_img_size(img_size, s=stride)

    processed = letterbox(image, new_shape=img_size)[0]
    processed = processed[:, :, ::-1].transpose(2, 0, 1)
    processed = np.ascontiguousarray(processed)
    tensor = torch.from_numpy(processed).to(MODEL_DEVICE).float() / 255.0
    if tensor.ndimension() == 3:
        tensor = tensor.unsqueeze(0)

    with torch.no_grad():
        prediction = DETECT_MODEL(tensor, augment=False)[0]
        detections = non_max_suppression(prediction, conf_thres, iou_thres)

    det = detections[0]
    if det is None or not len(det):
        raise RuntimeError('YOLOv5 未检测到车牌区域')

    det[:, :4] = scale_coords(tensor.shape[2:], det[:, :4], image.shape).round()
    candidates = []
    for item in det:
        x1, y1, x2, y2, conf, _cls = item.tolist()
        x1, y1 = max(int(x1), 0), max(int(y1), 0)
        x2, y2 = min(int(x2), image.shape[1]), min(int(y2), image.shape[0])
        plate = _recognize_crop(cv2, np, torch, CHARS, transform, image[y1:y2, x1:x2])
        if plate:
            candidates.append((float(conf), plate))

    if not candidates:
        raise RuntimeError('YOLOv5 已检测到车牌区域，但 LPRNet 未识别出车牌号')

    candidates.sort(key=lambda item: (len(item[1]), item[0]), reverse=True)
    return candidates[0][1]
