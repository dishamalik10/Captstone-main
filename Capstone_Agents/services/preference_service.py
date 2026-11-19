from __future__ import annotations

import json
from typing import Any

from database import connection, decode_json_fields, ensure_user, row, utc_now


DEFAULTS = {
    "preferred_colors": [],
    "avoided_colors": [],
    "preferred_styles": [],
    "disliked_styles": [],
    "fit_preference": None,
}


def save_preferences(user_id: str, data: dict[str, Any]) -> dict[str, Any]:
    ensure_user(user_id, data.get("display_name"))
    values = {**DEFAULTS, **{key: value for key, value in data.items() if key in DEFAULTS}}
    with connection() as db:
        db.execute(
            """
            INSERT INTO preferences(
                user_id, preferred_colors, avoided_colors, preferred_styles,
                disliked_styles, fit_preference, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                preferred_colors = excluded.preferred_colors,
                avoided_colors = excluded.avoided_colors,
                preferred_styles = excluded.preferred_styles,
                disliked_styles = excluded.disliked_styles,
                fit_preference = excluded.fit_preference,
                updated_at = excluded.updated_at
            """,
            (
                user_id,
                json.dumps(values["preferred_colors"]),
                json.dumps(values["avoided_colors"]),
                json.dumps(values["preferred_styles"]),
                json.dumps(values["disliked_styles"]),
                values["fit_preference"],
                utc_now(),
            ),
        )
    return get_preferences(user_id)


def get_preferences(user_id: str) -> dict[str, Any]:
    ensure_user(user_id)
    record = row("SELECT * FROM preferences WHERE user_id = ?", (user_id,))
    if record is None:
        return {"user_id": user_id, **DEFAULTS}
    return decode_json_fields(record)
