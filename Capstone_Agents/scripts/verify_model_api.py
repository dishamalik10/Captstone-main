"""Run a real CNN-backed upload against an isolated temporary API database."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    if not args.image.is_file():
        raise FileNotFoundError(args.image)

    temporary = Path(tempfile.mkdtemp(prefix="aura-cnn-check-"))
    os.environ["AURA_DATABASE_PATH"] = str(temporary / "aura.db")
    os.environ["AURA_UPLOAD_DIR"] = str(temporary / "uploads")

    from fastapi.testclient import TestClient

    from main import app

    mime = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(args.image.suffix.lower(), "image/jpeg")
    with TestClient(app) as client, args.image.open("rb") as image:
        response = client.post(
            "/wardrobe/upload",
            data={"user_id": "cnn-verification"},
            files={"file": (args.image.name, image, mime)},
        )
    response.raise_for_status()
    result = response.json()
    print(
        {
            "category": result["category"],
            "subcategory": result["subcategory"],
            "garment_group": result["garment_group"],
            "color_name": result["color_name"],
            "confidence": {
                key: round(value["confidence"], 4)
                for key, value in result["confidence"].items()
            },
        }
    )


if __name__ == "__main__":
    main()
