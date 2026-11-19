"""Compare local llama.cpp CPU inference with Metal layer offload."""
from __future__ import annotations

import json
import resource
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from settings import settings

PROMPT = (
    "Compare these wardrobe-only casual outfits. A: navy shirt, beige trousers, white sneakers. "
    "B: black tee, blue jeans, white sneakers. Explain the palette difference and one limitation."
)
SYSTEM = "You are a concise fashion stylist. Use only listed garments; make no material or fit claims."


def run(label: str, gpu_layers: int) -> dict:
    from llama_cpp import Llama

    load_start = time.perf_counter()
    model = Llama(
        model_path=str(settings.llm_model_path), n_ctx=4096, n_threads=4,
        n_gpu_layers=gpu_layers, verbose=False,
    )
    load_seconds = time.perf_counter() - load_start
    samples = []
    counts = []
    for index in range(2):
        start = time.perf_counter()
        response = model.create_chat_completion(
            messages=[{"role":"system","content":SYSTEM},{"role":"user","content":PROMPT}],
            max_tokens=96, temperature=0.2, top_p=0.9,
        )
        elapsed = time.perf_counter() - start
        usage = response.get("usage", {})
        count = int(usage.get("completion_tokens", 0))
        samples.append({"seconds": round(elapsed, 3), "completion_tokens": count,
                        "tokens_per_second": round(count / elapsed, 3) if elapsed else None})
        counts.append(count)
    peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports ru_maxrss in bytes; Linux reports KiB.
    if sys.platform != "darwin":
        peak_rss *= 1024
    return {
        "mode": label, "gpu_layers": gpu_layers, "model_load_seconds": round(load_seconds, 3),
        "generation_samples": samples,
        "mean_tokens_per_second": round(statistics.mean(s["tokens_per_second"] for s in samples if s["tokens_per_second"] is not None), 3),
        "peak_process_rss_bytes": peak_rss,
        "peak_process_rss_gib": round(peak_rss / (1024 ** 3), 3),
        "completion_tokens": counts,
    }


def main() -> None:
    from llama_cpp import llama_cpp
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        mode = sys.argv[2]
        result = run(mode, 0 if mode == "cpu" else -1)
        print(json.dumps(result))
        return
    result = {
        "model": settings.llm_model_path.name,
        "runtime": "llama.cpp; same 4096-token context, 4 CPU threads, prompt, and 96-token cap",
        "metal_offload_supported_by_runtime": bool(llama_cpp.llama_supports_gpu_offload()),
        "runs": [],
    }
    for label in ("cpu", "metal_all_layers"):
        try:
            completed = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--worker", label],
                check=True, capture_output=True, text=True,
            )
            result["runs"].append(json.loads(completed.stdout.strip().splitlines()[-1]))
        except (subprocess.CalledProcessError, json.JSONDecodeError, IndexError) as exc:
            detail = exc.stderr[-4000:] if isinstance(exc, subprocess.CalledProcessError) else str(exc)
            result["runs"].append({"mode": label, "error": detail})
    output = ROOT / "training" / "local_llm_benchmark.json"
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()
