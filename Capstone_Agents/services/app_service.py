from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from database import connection, decode_json_fields, ensure_user, row, rows, utc_now
from services.media_access import signed_media_url


def _password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return f"{base64.b64encode(salt).decode()}:{base64.b64encode(digest).decode()}"


def _verify_password(password: str, encoded: str) -> bool:
    try:
        salt_text, expected = encoded.split(":", 1)
        actual = _password_hash(password, base64.b64decode(salt_text)).split(":", 1)[1]
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _public_user(record: dict[str, Any]) -> dict[str, Any]:
    profile = json.loads(record.get("profile_json") or "{}")
    return {
        "id": record["user_id"],
        "fullName": record.get("display_name") or "",
        "email": record.get("email") or "",
        "avatarUrl": record.get("avatar_url"),
        "location": record.get("location") or "",
        "stylePreferences": profile.get("stylePreferences", []),
        "bodyShape": profile.get("bodyShape"),
        "skinTone": profile.get("skinTone"),
        "heightCm": profile.get("heightCm"),
        "topSize": profile.get("topSize"),
        "bottomSize": profile.get("bottomSize"),
        "itemsCount": int(record.get("items_count") or 0),
        "outfitsSaved": int(record.get("outfits_saved") or 0),
        "following": int(record.get("following") or 0),
        "followers": int(record.get("followers") or 0),
        "profileComplete": bool(profile.get("profileComplete", False)),
    }


USER_QUERY = """
SELECT u.*,
 (SELECT COUNT(*) FROM clothing_items c WHERE c.user_id=u.user_id AND c.available=1) items_count,
 (SELECT COUNT(*) FROM feedback f WHERE f.user_id=u.user_id AND f.action='save') outfits_saved,
 (SELECT COUNT(*) FROM follows f WHERE f.follower_id=u.user_id) following,
 (SELECT COUNT(*) FROM follows f WHERE f.followed_id=u.user_id) followers
FROM users u
"""


def signup(full_name: str, email: str, password: str, client: str = "app") -> tuple[dict, str]:
    email = email.strip().lower()
    if row("SELECT user_id FROM users WHERE lower(email)=?", (email,)):
        # Deliberately vague: a sign-up form must not confirm which emails have accounts.
        raise ValueError("We couldn't create an account with these details. If you already have one, sign in instead.")
    user_id = f"user_{uuid.uuid4().hex[:16]}"
    now = utc_now()
    with connection() as db:
        db.execute(
            """INSERT INTO users(user_id,display_name,email,password_hash,created_at)
               VALUES(?,?,?,?,?)""",
            (user_id, full_name.strip(), email, _password_hash(password), now),
        )
    return get_user(user_id), create_session(user_id, client)


def login(email: str, password: str, client: str = "app") -> tuple[dict, str]:
    record = row("SELECT * FROM users WHERE lower(email)=?", (email.strip().lower(),))
    if not record or not record.get("password_hash") or not _verify_password(password, record["password_hash"]):
        raise ValueError("Invalid email or password.")
    return get_user(record["user_id"]), create_session(record["user_id"], client)


# Web tokens live in localStorage, where any injected script could read them, so web
# sessions are short (4.7). The Android app keeps its token in the OS secure store.
SESSION_DAYS = {"app": 30, "web": 7}


def create_session(user_id: str, client: str = "app") -> str:
    token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode()).hexdigest()
    expires = (datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS.get(client, 7))).isoformat()
    with connection() as db:
        db.execute(
            "INSERT INTO sessions(token_hash,user_id,expires_at,created_at) VALUES(?,?,?,?)",
            (digest, user_id, expires, utc_now()),
        )
    return token


def session_user(token: str) -> dict | None:
    digest = hashlib.sha256(token.encode()).hexdigest()
    record = row("SELECT user_id,expires_at FROM sessions WHERE token_hash=?", (digest,))
    if not record or datetime.fromisoformat(record["expires_at"]) <= datetime.now(timezone.utc):
        return None
    return get_user(record["user_id"])


def logout(token: str) -> None:
    with connection() as db:
        db.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))


def logout_everywhere(user_id: str) -> int:
    """End every session of this user (all devices, including this one)."""
    with connection() as db:
        return db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,)).rowcount


def get_user(user_id: str) -> dict:
    record = row(f"{USER_QUERY} WHERE u.user_id=?", (user_id,))
    if not record:
        raise KeyError(user_id)
    return _public_user(record)


def update_user(user_id: str, data: dict[str, Any]) -> dict:
    current = row("SELECT * FROM users WHERE user_id=?", (user_id,))
    if not current:
        raise KeyError(user_id)
    profile = json.loads(current.get("profile_json") or "{}")
    for key in ("stylePreferences", "bodyShape", "skinTone", "heightCm", "topSize", "bottomSize", "profileComplete"):
        if key in data:
            profile[key] = data[key]
    with connection() as db:
        db.execute(
            """UPDATE users SET display_name=?,avatar_url=?,location=?,profile_json=?
               WHERE user_id=?""",
            (
                data.get("fullName", current.get("display_name")),
                data.get("avatarUrl", current.get("avatar_url")),
                data.get("location", current.get("location") or ""),
                json.dumps(profile),
                user_id,
            ),
        )
    return get_user(user_id)


def _requests_outfit(content: str) -> bool:
    text = content.lower()
    phrases = (
        "what should i wear", "what to wear", "wear", "outfit", "recommend",
        "suggest", "style me", "style my", "style this", "style the", "match this",
        "matches this", "pair my", "what goes with", "build an outfit", "look for",
        "date", "party", "meeting", "wedding", "interview", "travel",
        "casual", "office", "work", "college", "event",
    )
    return any(phrase in text for phrase in phrases)


def _recent_chat(user_id: str, session_id: str, limit: int = 16) -> list[dict[str, str]]:
    records = rows(
        "SELECT role,content FROM chat_messages WHERE user_id=? AND session_id=? "
        "ORDER BY created_at DESC LIMIT ?",
        (user_id, session_id, limit),
    )
    return [
        {"role": record["role"], "content": record["content"]}
        for record in reversed(records)
    ]


def _choose_outfit(user_id: str, content: str, occasion: str, candidates: list[dict],
                   history: list[dict[str, str]], shown: list[set[str]]) -> int:
    """Pick the chat outfit with the fine-tuned AURA stylist; fall back to the chat model."""
    from services import stylist_selector
    from services.preference_service import get_preferences

    choice = stylist_selector.choose(candidates, {
        "occasion": occasion,
        # Chat has no live weather; the stylist prompt treats a null temperature as unknown.
        "weather": {"temperature_c": None, "condition": "Unknown"},
        "preferences": get_preferences(user_id),
        **stylist_selector.load_user_context(user_id),
    })
    if choice is not None:
        return choice["index"]
    from services.llm_stylist import pick_outfit

    return pick_outfit(message=content, occasion=occasion, candidates=candidates,
                       conversation_history=history, already_shown=shown)


def _shown_outfits(user_id: str, session_id: str) -> list[set[str]]:
    """Item-id sets of outfits already shown in this chat session."""
    shown = []
    for record in rows(
        "SELECT metadata_json FROM chat_messages WHERE user_id=? AND session_id=? AND role='assistant' "
        "ORDER BY created_at DESC LIMIT 20",
        (user_id, session_id),
    ):
        outfit = json.loads(record.get("metadata_json") or "{}").get("outfit") or {}
        if outfit.get("itemIds"):
            shown.append(set(map(str, outfit["itemIds"])))
    return shown


def _offline_chat_reply(
    content: str,
    user: dict[str, Any],
    items: list[dict[str, Any]],
) -> str:
    text = content.lower().strip(" ?.!")
    name = (user.get("fullName") or "").split(" ")[0]
    greeting = f"Hi {name}!" if name else "Hi!"
    if text in {"hi", "hello", "hey", "hii", "helo"}:
        return f"{greeting} How can I help with your outfit or wardrobe today?"
    if "thank" in text:
        return "You’re welcome! Ask me anytime you want another outfit or styling explanation."
    if "confus" in text or "explain" in text:
        return "Of course. Tell me which outfit or part feels confusing, and I’ll explain the colour, occasion, and compatibility reasoning."
    if "trend" in text and ("color" in text or "colour" in text):
        colors = list(dict.fromkeys(item["color_name"] for item in items))[:5]
        owned = ", ".join(colors) if colors else "no uploaded colours yet"
        return (
            f"Your wardrobe currently includes {owned}. I can build combinations from these; "
            "I only have cached fashion context, so I cannot confirm what is trending now."
        )
    return (
        "I can help with outfits, colour matching, dress codes, fit, and your uploaded "
        "wardrobe. Tell me what you are dressing for or what you want to wear."
    )


def chat(user_id: str, content: str, session_id: str = "legacy") -> dict:
    ensure_user(user_id)
    items = [
        decode_json_fields(item)
        for item in rows(
            "SELECT item_id,subcategory,color_name,category,style_tags,fabric,pattern,fit "
            "FROM clothing_items WHERE user_id=? AND available=1 LIMIT 40",
            (user_id,),
        )
    ]
    history = _recent_chat(user_id, session_id)
    wants_outfit = _requests_outfit(content)
    outfit = None
    best = None
    occasion = None
    if items and wants_outfit:
        text = content.lower()
        occasion = next(
            (value for value in ("smart casual", "date", "party", "meeting", "wedding", "interview", "travel", "college", "office", "work", "formal", "festival", "casual") if value in text),
            "casual",
        )
        from services.recommendation_service import recommend

        suggestions, _agent_trace = recommend(user_id, occasion, 25.0, "Unknown", 12, surface="chat")
        if suggestions:
            requested_colors = {
                item["color_name"].lower()
                for item in items
                if item["color_name"].lower() in text
            }
            candidates = [
                suggestion for suggestion in suggestions
                if requested_colors
                and any(item["color_name"].lower() in requested_colors for item in suggestion["items"])
            ] or suggestions
            # Don't repeat an outfit already shown in this chat while fresh options remain.
            shown = _shown_outfits(user_id, session_id)
            candidates = [
                candidate for candidate in candidates
                if set(map(str, candidate["item_ids"])) not in shown
            ] or candidates
            candidates = candidates[:5]
            best = candidates[_choose_outfit(user_id, content, occasion, candidates, history, shown)]
            from services.recommendation_service import discard_unshown

            # Chat shows one outfit: keep only that row, so slate metrics and the audit
            # trail reflect what the user saw (M6).
            discard_unshown(user_id, best["recommendation_id"], suggestions)
            selected = ", ".join(
                f"{item['color_name']} {item['subcategory']}" for item in best["items"]
            )
            reply = f"For {occasion}, wear your {selected}."
            outfit = {
                "id": best["recommendation_id"],
                "name": f"{occasion.title()} Outfit",
                "occasion": occasion,
                "compatibilityScore": best["compatibility_score"],
                "imageUrl": best["items"][0]["image_url"],
                "itemImages": [
                    {"url": item["image_url"], "label": f"{item['color_name']} {item['subcategory']}"}
                    for item in best["items"]
                ],
                "itemIds": best["item_ids"],
                "explanation": best["explanation"],
                "componentScores": best["component_scores"],
            }
        else:
            reply = "I found your uploaded clothes, but need a dress or at least one top and one bottom to build a complete outfit."
    elif not items and wants_outfit:
        reply = "Upload a dress, or a top and bottom, so I can recommend outfits from clothes you actually own."
    else:
        reply = _offline_chat_reply(content, get_user(user_id), items)
    from services.llm_stylist import stylist_reply

    reply = stylist_reply(
        message=content,
        user=get_user(user_id),
        wardrobe=items,
        recommendation=best,
        conversation_history=history,
        wants_outfit=wants_outfit,
        fallback=reply,
        occasion=occasion,
    )
    if best is not None:
        from services.recommendation_service import record_explanations

        record_explanations(user_id, [{**best, "explanation": reply, "explanation_source": "chat_reply"}])
    now = utc_now()
    user_message = f"msg_{uuid.uuid4().hex[:16]}"
    assistant_message = f"msg_{uuid.uuid4().hex[:16]}"
    with connection() as db:
        db.execute(
            "INSERT INTO chat_messages(message_id,user_id,session_id,role,content,metadata_json,created_at) VALUES(?,?,?,?,?,?,?)",
            (user_message, user_id, session_id, "user", content, "{}", now),
        )
        db.execute(
            "INSERT INTO chat_messages(message_id,user_id,session_id,role,content,metadata_json,created_at) VALUES(?,?,?,?,?,?,?)",
            (assistant_message, user_id, session_id, "assistant", reply, json.dumps({"outfit": outfit} if outfit else {}), utc_now()),
        )
    response = {"id": assistant_message, "role": "assistant", "content": reply, "timestamp": utc_now()}
    if outfit:
        response["outfit"] = outfit
    return response


def _refresh_outfit_images(user_id: str, outfit: dict) -> dict:
    """Re-sign piece photos for a stored outfit: saved signed links expire after 15 minutes."""
    item_ids = [str(item_id) for item_id in outfit.get("itemIds") or []]
    if not item_ids:
        return outfit
    placeholders = ",".join("?" for _ in item_ids)
    found = {
        record["item_id"]: record
        for record in rows(
            f"SELECT item_id,color_name,subcategory,image_path FROM clothing_items "
            f"WHERE user_id=? AND item_id IN ({placeholders})",
            (user_id, *item_ids),
        )
    }
    pieces = [
        {"url": signed_media_url(user_id, found[item_id]["image_path"]),
         "label": f"{found[item_id]['color_name']} {found[item_id]['subcategory']}"}
        for item_id in item_ids if item_id in found
    ]
    if not pieces:
        return outfit
    return {**outfit, "imageUrl": pieces[0]["url"], "itemImages": pieces}


def chat_history(user_id: str, session_id: str = "legacy") -> list[dict]:
    history = []
    for record in rows(
        "SELECT * FROM chat_messages WHERE user_id=? AND session_id=? ORDER BY created_at",
        (user_id, session_id),
    ):
        message = {
            "id": record["message_id"], "role": record["role"],
            "content": record["content"], "timestamp": record["created_at"],
        }
        metadata = json.loads(record.get("metadata_json") or "{}")
        if metadata.get("outfit"):
            metadata["outfit"] = _refresh_outfit_images(user_id, metadata["outfit"])
        message.update(metadata)
        history.append(message)
    return history


def social_feed(viewer_id: str) -> list[dict]:
    records = rows(
        """SELECT p.*,u.display_name,u.avatar_url,
          (SELECT COUNT(*) FROM post_likes l WHERE l.post_id=p.post_id) likes,
          EXISTS(SELECT 1 FROM post_likes l WHERE l.post_id=p.post_id AND l.user_id=?) liked
          FROM social_posts p JOIN users u ON u.user_id=p.user_id
          ORDER BY p.created_at DESC""",
        (viewer_id,),
    )
    from services.moderation_service import hidden_from

    hidden = hidden_from(viewer_id)  # posts by users the viewer blocked (4.4)
    records = [item for item in records if item["user_id"] not in hidden]
    return [{
        "id": item["post_id"],
        "user": {"id": item["user_id"], "fullName": item["display_name"] or "", "avatarUrl": item["avatar_url"]},
        "outfitImageUrl": item["outfit_image_url"], "caption": item["caption"],
        "likes": item["likes"], "comments": 0, "liked": bool(item["liked"]),
        "shopProductIds": json.loads(item["product_ids"]), "createdAt": item["created_at"],
    } for item in records]


def create_post(user_id: str, data: dict) -> dict:
    post_id = f"post_{uuid.uuid4().hex[:16]}"
    with connection() as db:
        db.execute(
            "INSERT INTO social_posts(post_id,user_id,outfit_image_url,caption,product_ids,created_at) VALUES(?,?,?,?,?,?)",
            (post_id, user_id, data["outfit_image_url"], data["caption"],
             json.dumps(data.get("product_ids", [])), utc_now()),
        )
    return next(post for post in social_feed(user_id) if post["id"] == post_id)


def toggle_like(user_id: str, post_id: str) -> bool:
    with connection() as db:
        if not db.execute("SELECT 1 FROM social_posts WHERE post_id=?", (post_id,)).fetchone():
            raise LookupError("Post not found.")
        exists = db.execute("SELECT 1 FROM post_likes WHERE post_id=? AND user_id=?", (post_id, user_id)).fetchone()
        if exists:
            db.execute("DELETE FROM post_likes WHERE post_id=? AND user_id=?", (post_id, user_id))
            return False
        db.execute("INSERT INTO post_likes(post_id,user_id) VALUES(?,?)", (post_id, user_id))
        return True


def toggle_follow(follower_id: str, followed_id: str) -> bool:
    if follower_id == followed_id:
        raise ValueError("You cannot follow yourself.")
    with connection() as db:
        if not db.execute("SELECT 1 FROM users WHERE user_id=?", (followed_id,)).fetchone():
            raise LookupError("User not found.")
        exists = db.execute("SELECT 1 FROM follows WHERE follower_id=? AND followed_id=?", (follower_id, followed_id)).fetchone()
        if exists:
            db.execute("DELETE FROM follows WHERE follower_id=? AND followed_id=?", (follower_id, followed_id))
            return False
        db.execute("INSERT INTO follows(follower_id,followed_id) VALUES(?,?)", (follower_id, followed_id))
        return True
