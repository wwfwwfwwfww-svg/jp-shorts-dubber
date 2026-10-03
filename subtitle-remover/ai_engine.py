"""AI 인페인팅 엔진 (LaMa) 래퍼.

cv2보다 훨씬 깔끔하게 지운다(복잡·실사 배경 OK). torch + simple-lama-inpainting 필요
(= AI설치.bat). 설치가 안 돼 있어도 앱이 죽지 않도록 **torch/LaMa는 전부 함수 안에서
지연 import** 한다. 첫 사용 시 LaMa 모델(big-lama, ~200MB)이 자동 다운로드된다.
"""
from __future__ import annotations

from typing import Optional

import cv2
import numpy as np

_LAMA = None  # SimpleLama 싱글턴(모델 1회 로드)


def status() -> dict:
    """AI 엔진 사용 가능 여부. 예외 없이 항상 dict 반환."""
    try:
        import torch
    except Exception:
        return {"available": False, "reason": "PyTorch 미설치 — AI설치.bat 실행",
                "device": None, "gpu": None, "cuda": False}
    try:
        import simple_lama_inpainting  # noqa: F401
    except Exception:
        return {"available": False, "reason": "LaMa 미설치 — AI설치.bat 실행",
                "device": None, "gpu": None, "cuda": False}
    try:
        cuda = bool(torch.cuda.is_available())
        gpu = torch.cuda.get_device_name(0) if cuda else "CPU (느림)"
    except Exception:
        cuda, gpu = False, "CPU (느림)"
    return {"available": True, "reason": "", "device": "cuda" if cuda else "cpu",
            "gpu": gpu, "cuda": cuda}


def _lama():
    """LaMa 모델 지연 로드(싱글턴). GPU 있으면 GPU, 없으면 CPU."""
    global _LAMA
    if _LAMA is None:
        import torch
        from simple_lama_inpainting import SimpleLama
        try:
            torch.backends.cudnn.benchmark = True  # 같은 크기 반복 → 약간 빠름
        except Exception:
            pass
        _LAMA = SimpleLama()  # 내부에서 cuda 가용 시 자동 GPU 사용
    return _LAMA


def inpaint_frame(bgr: np.ndarray, mask_gray: np.ndarray) -> np.ndarray:
    """한 프레임(BGR)에서 마스크(흰색=지울 영역) 영역을 LaMa로 지운 BGR 반환."""
    import torch
    from PIL import Image
    lama = _lama()
    img = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    mask = Image.fromarray(mask_gray).convert("L")
    with torch.inference_mode():  # autograd 끔 → 메모리·오버헤드 절감
        res = lama(img, mask)  # PIL RGB
    out = cv2.cvtColor(np.array(res), cv2.COLOR_RGB2BGR)
    if out.shape[:2] != bgr.shape[:2]:  # 모델이 크기를 바꾸면 되돌림(방어)
        out = cv2.resize(out, (bgr.shape[1], bgr.shape[0]))
    return out
