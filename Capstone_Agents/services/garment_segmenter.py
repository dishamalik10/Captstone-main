"""SegFormer-B2 Clothes garment segmentation (ENGINEERING_PLAN 4.2b).

``mattmdjaga/segformer_b2_clothes`` (27.4M parameters, 18 ATR labels), run as its ONNX
export with onnxruntime on the CPU (the runtime ISNet already uses; no torch).
Licence: "other", pointing to the NVlabs SegFormer licence (believed non-commercial);
see training/FASHION_DATASET_LICENSE_AUDIT.md.

Each segmentation runs in a short-lived child process, one at a time. Measured on the
8 GB Mac: loading the model and running it once in the API process added ~0.9-1.2 GB
that the process kept afterwards (freed memory is not returned to the OS), more than
the step-3 headroom of ~0.5 GB. In a child process the memory is held only for the
~2 s of the call and is fully returned when the child exits. This replaces the plan's
"lazy load + 10-minute idle unload" in the API process.
"""
from __future__ import annotations

import io
import logging
import multiprocessing
import threading
from pathlib import Path

import numpy as np
from PIL import Image

from settings import settings

LOGGER = logging.getLogger(__name__)
LABELS = (
    "Background", "Hat", "Hair", "Sunglasses", "Upper-clothes", "Skirt", "Pants", "Dress", "Belt",
    "Left-shoe", "Right-shoe", "Face", "Left-leg", "Right-leg", "Left-arm", "Right-arm", "Bag", "Scarf",
)
LABEL = {name: index for index, name in enumerate(LABELS)}
PERSON_LABELS = ("Hair", "Face", "Left-leg", "Right-leg", "Left-arm", "Right-arm")
INPUT_SIZE = 512
MAX_SIDE = 1024  # label maps are produced at most this large (cut-outs are scaled back up)
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
TIMEOUT_SECONDS = 60


def model_path() -> Path:
    return settings.tryon_model_dir / "segformer_b2_clothes" / "model.onnx"


def _segment_here(model: str, png: bytes) -> np.ndarray:
    """Load the model and segment one image in *this* process (the child)."""
    import onnxruntime

    image = Image.open(io.BytesIO(png)).convert("RGB")
    scale = min(1.0, MAX_SIDE / max(image.size))
    out_size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    pixels = np.asarray(image.resize((INPUT_SIZE, INPUT_SIZE), Image.BILINEAR), dtype=np.float32) / 255.0
    batch = ((pixels - MEAN) / STD).transpose(2, 0, 1)[None].astype(np.float32)
    options = onnxruntime.SessionOptions()
    options.intra_op_num_threads = 2  # leave cores for the API and the try-on worker
    options.enable_cpu_mem_arena = False  # allocate per node: a lower peak than the arena
    options.enable_mem_pattern = False
    session = onnxruntime.InferenceSession(model, sess_options=options, providers=["CPUExecutionProvider"])
    logits = session.run(None, {"pixel_values": batch})[0][0]  # (18, 128, 128)
    # Upsample each class's logits (smooth edges), then take the best class per pixel.
    upsampled = np.stack([
        np.asarray(Image.fromarray(channel.astype(np.float32), mode="F").resize(out_size, Image.BILINEAR))
        for channel in logits
    ])
    return upsampled.argmax(axis=0).astype(np.uint8)


class Segmenter:
    def __init__(self) -> None:
        self._one_at_a_time = threading.Lock()  # at most one child (~1 GB) alive

    def available(self) -> bool:
        return settings.garment_segmentation and model_path().is_file()

    def segment(self, image: Image.Image) -> np.ndarray:
        """Label map (indices into LABELS) at the image's size, capped at MAX_SIDE.
        Raises RuntimeError if the child fails or takes longer than TIMEOUT_SECONDS."""
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="PNG")
        context = multiprocessing.get_context("spawn")
        with self._one_at_a_time:
            receive, send = context.Pipe(duplex=False)
            child = context.Process(target=_child, args=(str(model_path()), buffer.getvalue(), send), daemon=True)
            child.start()
            send.close()  # only the child writes; EOF is seen if it dies
            try:
                if not receive.poll(TIMEOUT_SECONDS):
                    raise RuntimeError(f"Garment segmentation took longer than {TIMEOUT_SECONDS} s")
                ok, result = receive.recv()
            except EOFError as exc:
                raise RuntimeError("Garment segmentation process exited unexpectedly") from exc
            finally:
                receive.close()
                child.join(5)
                if child.is_alive():
                    child.kill()
                    child.join()
        if not ok:
            raise RuntimeError(f"Garment segmentation failed: {result}")
        return result


def _child(model: str, png: bytes, send) -> None:
    try:
        send.send((True, _segment_here(model, png)))
    except Exception as exc:  # reported to the parent, which logs it
        send.send((False, f"{type(exc).__name__}: {exc}"))
    finally:
        send.close()


segmenter = Segmenter()
