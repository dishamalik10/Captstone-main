"""Which models a process holds in memory, and its peak memory use (for /health).

Peak RSS comes from ``resource.getrusage`` (standard library, no extra dependency).
It is the high-water mark since the process started, which is the number that
matters for the 8 GB go/no-go rule in ENGINEERING_PLAN step 3.
"""
from __future__ import annotations

import resource
import sys


def peak_rss_mb() -> int:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes, Linux reports kilobytes.
    return round(peak / (1 << 20)) if sys.platform == "darwin" else round(peak / 1024)


def resident_models() -> list[str]:
    """Models currently loaded in this (API) process. (SegFormer, 4.2b, and ISNet run
    in short-lived child processes, so they never stay resident here.)"""
    from services import aura_fashion_lm, body_analysis, outfit_compat_service, stylist_selector
    from services.local_llm import local_llm
    from services.vision_service import vision_service

    stylist = stylist_selector._stylist_llm
    loaded = {
        "garment_cnn": vision_service._model is not None,
        "outfit_compatibility": outfit_compat_service._model is not None,
        "stylist_gguf": stylist is not None and stylist._model is not None,
        "base_chat_gguf": local_llm._model is not None,
        "scratch_fashion_lm": aura_fashion_lm._model is not None,
        # Pose + segmenter: avatar analysis and the person check on imports.
        "mediapipe": body_analysis._models.pose is not None,
    }
    return [name for name, is_loaded in loaded.items() if is_loaded]
