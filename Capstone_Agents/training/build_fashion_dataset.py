"""Build a reproducible, wardrobe-grounded synthetic SFT corpus.

The corpus is generated only from authored rules and scoped open references in
knowledge/fashion_heuristics.json. It is synthetic instruction data, never
presented as designer-authored or user feedback.
"""
from __future__ import annotations

import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE = ROOT / "knowledge" / "fashion_heuristics.json"
OUT = ROOT / "training" / "fashion_sft"
CURATED_CASES = ROOT / "training" / "curated_fashion_cases.json"
TARGET_SCENARIOS = 100
TOPICS = (
    "color_theory", "complementary_colors", "analogous_colors", "neutral_palette",
    "potentially_busy_palette", "proportions", "silhouette", "pattern_coordination",
    "fabric_texture", "layering", "casual", "formal", "smart_casual", "streetwear",
    "minimalist", "old_money_inspired", "college", "office", "party", "seasonal",
    "compare_outfits",
)
COLORS = ("Black", "White", "Navy", "Red", "Blue", "Green", "Beige", "Grey", "Cream", "Pink")
FABRICS = ("Cotton", "Linen", "Wool", "Denim", "Cotton", "Silk", "Wool", "Linen", "Cotton", "Denim")
PATTERNS = ("Solid", "Stripe", "Solid", "Plaid", "Solid", "Floral", "Solid", "Stripe", "Solid", "Plaid")
FITS = ("Regular", "Relaxed", "Tailored", "Straight", "Oversized", "Regular", "Slim", "Relaxed", "Tailored", "Straight")
SEASONS = ("Spring", "Summer", "Autumn", "Winter")
NEUTRAL = {"black", "white", "navy", "beige", "grey", "cream", "brown"}
FAMILY = {"red":"red", "pink":"red", "orange":"orange", "yellow":"yellow", "green":"green", "olive":"green", "teal":"bluegreen", "blue":"blue", "navy":"blue", "purple":"purple", "lilac":"purple"}
COMPLEMENT = {"red":"green", "green":"red", "orange":"blue", "blue":"orange", "yellow":"purple", "purple":"yellow"}
ANALOGOUS = {"red":"orange", "orange":"red", "yellow":"green", "green":"yellow", "blue":"purple", "purple":"blue"}


def item(i: int, code: str, category: str, name: str, color: str, **attrs: Any) -> dict[str, Any]:
    return {"item_id": f"w{i:03d}_{code}", "category": category, "name": name, "color": color, **attrs}


def wardrobe(i: int) -> list[dict[str, Any]]:
    # Independent seeded draws prevent the short modulo cycle in the earlier
    # generator from creating repeated wardrobes under different IDs.
    rng = random.Random(20261030 + i)
    season = rng.choice(SEASONS)
    def attrs(code: int, *, seasons: list[str] | None = None) -> dict[str, Any]:
        return {
            "color": rng.choice(COLORS), "fabric": rng.choice(FABRICS),
            "pattern": rng.choice(PATTERNS), "fit": rng.choice(FITS),
            "texture": rng.choice(("Matte", "Smooth", "Ribbed", "Structured", "Soft")),
            "seasons": seasons or [season],
        }
    all_items = [
        item(i, "shirt", "Top", "Shirt", **attrs(0), style_tags=["formal", "smart casual"], occasion_tags=["office", "meeting"]),
        item(i, "tee", "Top", "T-shirt", **attrs(1), style_tags=["casual", "streetwear", "college"]),
        item(i, "trousers", "Bottom", "Trousers", **attrs(2), style_tags=["formal", "smart casual", "old money"], occasion_tags=["office", "meeting", "formal"]),
        item(i, "jeans", "Bottom", "Jeans", **attrs(3, seasons=["Spring", "Autumn"]), style_tags=["casual", "streetwear", "college"]),
        item(i, "loafers", "Footwear", "Loafers", **attrs(4), style_tags=["formal", "smart casual", "old money"], occasion_tags=["office", "meeting"]),
        item(i, "sneakers", "Footwear", "Sneakers", **attrs(5), style_tags=["casual", "streetwear", "college"]),
        item(i, "blazer", "Outerwear", "Blazer", **attrs(6, seasons=["Autumn", "Winter"]), style_tags=["formal", "smart casual", "old money"], occasion_tags=["office", "meeting", "formal"]),
        item(i, "jacket", "Outerwear", "Jacket", **attrs(7, seasons=["Spring", "Autumn"]), style_tags=["casual", "streetwear"]),
        item(i, "dress", "Dress", "Dress", **attrs(8), style_tags=["formal", "party"], occasion_tags=["party", "formal"]),
        item(i, "scarf", "Accessory", "Scarf", **attrs(9, seasons=["Autumn", "Winter"]), style_tags=["layering"], occasion_tags=[]),
    ]
    # Twenty percent of scenarios are intentionally incomplete and vary in the
    # missing category. They teach the model to say when it cannot build a look.
    if i % 5 == 0:
        case = (i // 5) % 4
        keep = ({"w%03d_shirt" % i}, {"w%03d_trousers" % i, "w%03d_loafers" % i},
                {"w%03d_tee" % i, "w%03d_sneakers" % i}, {"w%03d_jacket" % i, "w%03d_scarf" % i})[case]
        return [x for x in all_items if x["item_id"] in keep]
    return all_items


def ids_for(items: list[dict[str, Any]], categories: set[str], style: str | None = None) -> list[str]:
    matches = [x for x in items if x["category"] in categories and (style is None or style in x.get("style_tags", []))]
    return [x["item_id"] for x in matches]


def chosen_outfit(items: list[dict[str, Any]], style: str) -> list[dict[str, Any]] | None:
    chosen: list[dict[str, Any]] = []
    if style in {"casual", "streetwear", "college"}:
        wanted = ["tee", "jeans", "sneakers"]
    elif style in {"formal", "office", "old_money"}:
        wanted = ["shirt", "trousers", "loafers", "blazer"]
    elif style == "party":
        wanted = ["dress", "loafers"]
    elif style == "seasonal":
        wanted = ["shirt", "trousers", "loafers"]
        if items and items[0].get("seasons") == ["Winter"]:
            wanted += ["blazer", "scarf"]
    else:  # smart casual and minimalist
        wanted = ["shirt", "trousers", "loafers"]
        if style == "smart_casual":
            wanted += ["blazer"]
    by_id = {x["item_id"].rsplit("_", 1)[-1]: x for x in items}
    for code in wanted:
        candidate = by_id.get(code)
        if candidate:
            chosen.append(candidate)
    has_base = (any(x["category"] == "Dress" for x in chosen) or
                ({"Top", "Bottom"} <= {x["category"] for x in chosen}))
    if not has_base:
        return None
    if style not in {"party"} and not any(x["category"] == "Footwear" for x in chosen):
        return None
    return chosen


def context_items(topic: str, all_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep each synthetic prompt focused while preserving every referenced ID."""
    if topic in {"color_theory", "complementary_colors", "analogous_colors"}:
        return all_items[:6]
    if topic == "neutral_palette":
        return [x for x in all_items if x["color"].lower() in NEUTRAL][:4] or all_items[:4]
    if topic == "potentially_busy_palette":
        non_neutral = [x for x in all_items if x["color"].lower() not in NEUTRAL]
        neutrals = [x for x in all_items if x["color"].lower() in NEUTRAL]
        return (non_neutral[:4] + neutrals[:1])[:5]
    if topic in {"proportions", "silhouette"}:
        return [x for x in all_items if x["category"] in {"Top", "Bottom"}][:2]
    if topic == "pattern_coordination":
        pattern = next((x for x in all_items if x.get("pattern") not in (None, "Solid")), None)
        bottom = next((x for x in all_items if x["category"] == "Bottom"), None)
        return list({x["item_id"]: x for x in (pattern, bottom) if x}.values())
    if topic == "fabric_texture":
        with_material = [x for x in all_items if x.get("fabric") not in (None, "Unknown") and x.get("texture")]
        return with_material[:2] if len(with_material) >= 2 else all_items[:4]
    if topic == "layering":
        top = next((x for x in all_items if x["category"] == "Top"), None)
        outer = next((x for x in all_items if x["category"] == "Outerwear"), None)
        return [x for x in (top, outer) if x] or all_items[:4]
    if topic == "compare_outfits":
        casual = chosen_outfit(all_items, "casual") or []
        polished = chosen_outfit(all_items, "formal") or []
        selected = {x["item_id"] for x in casual + polished}
        if not selected:
            return all_items[:5]
        # Keep only the fields that support this comparison, avoiding unrelated
        # fabric/season metadata and keeping the full prompt within context.
        fields = {"item_id", "category", "name", "color", "fit", "style_tags", "occasion_tags"}
        return [{key: value for key, value in x.items() if key in fields}
                for x in all_items if x["item_id"] in selected]
    style = {"smart_casual":"smart_casual", "old_money_inspired":"old_money", "seasonal":"seasonal"}.get(topic, topic)
    selected = chosen_outfit(all_items, style)
    if selected:
        selected_ids = {x["item_id"] for x in selected}
        alternatives = [x for x in all_items if x["item_id"] not in selected_ids and x["category"] in {"Top", "Bottom", "Footwear"}]
        return [*selected, *alternatives[:1]]
    return all_items[:5]


def _source_for(topic: str) -> tuple[list[str], str]:
    if topic in {"color_theory", "complementary_colors", "analogous_colors", "neutral_palette"}:
        return ["wearbefore_original_styling_rules"], "CC BY 4.0; original WearBefore heuristic; synthetic example"
    if topic == "fabric_texture":
        return ["apple2023_apparel_production"], "CC BY 4.0; attributed paraphrase"
    if topic in {"formal", "smart_casual", "old_money_inspired", "college", "office", "party"}:
        return ["reddybest2020_dress_diversity"], "CC BY 4.0; attributed paraphrase and original heuristic"
    return [], "CC BY 4.0; original WearBefore heuristic; synthetic example"


def make_example(i: int, topic: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    items = context_items(topic, items)
    palette = [x for x in items if x.get("color", "").lower() not in NEUTRAL]
    color_families = {FAMILY.get(x["color"].lower(), x["color"].lower()) for x in palette}
    top = next((x for x in items if x["category"] == "Top"), None)
    bottom = next((x for x in items if x["category"] == "Bottom"), None)
    shoes = next((x for x in items if x["category"] == "Footwear"), None)
    pattern_items = [x for x in items if x.get("pattern") not in (None, "Solid")]
    item_names = {x["item_id"]: f"{x['color']} {x['name']}" for x in items}
    ids: list[str] = []
    needs = ""
    answer = ""
    candidate_outfits = None
    if topic == "color_theory":
        needs = "Explain hue-family coordination using only recorded colors, and state why harmony cannot be judged universally."
        answer = f"Recorded colors are {', '.join(dict.fromkeys(x['color'] for x in items))}. Color-wheel relationships can describe possible harmony, but shade, lightness, saturation, context, and personal preference matter; this record lacks several of those details. Treat the labels as a styling heuristic, not a universal rule."
    elif topic in {"complementary_colors", "analogous_colors"}:
        pair_map = COMPLEMENT if topic == "complementary_colors" else ANALOGOUS
        hue = next((h for h in color_families if pair_map.get(h)), None)
        partner = pair_map.get(hue) if hue else None
        partner_item = next((x for x in palette if FAMILY.get(x["color"].lower(), x["color"].lower()) == partner), None)
        first = next((x for x in palette if FAMILY.get(x["color"].lower(), x["color"].lower()) == hue), None)
        needs = f"Can you find a recorded {'complementary' if topic == 'complementary_colors' else 'analogous'} color pair? Explain with uncertainty."
        if first and partner_item:
            ids = [first["item_id"], partner_item["item_id"]]
            relation = "opposing families on a simplified color wheel" if topic == "complementary_colors" else "neighboring families on a simplified color wheel"
            answer = f"{item_names[ids[0]]} and {item_names[ids[1]]} are a possible {topic.replace('_', ' ')} pair because their recorded hue families are {relation}. Exact shade and saturation are not recorded, so this describes a relationship rather than guaranteeing a harmonious outfit."
        else:
            answer = "I cannot identify that relationship confidently from the recorded colors. The names do not establish exact hue, shade, or saturation; use a visual check or choose a relationship you prefer."
    elif topic == "neutral_palette":
        needs = "Find a neutral base using only recorded wardrobe items and explain the role of the colors."
        candidates = [x for x in items if x["color"].lower() in NEUTRAL]
        ids = [x["item_id"] for x in candidates[:3]]
        answer = (f"Use the recorded neutral pieces {', '.join(item_names[x] for x in ids)} as a quieter palette option. Neutral does not mean objectively better; keep or add color only with pieces listed in this wardrobe." if ids else "No item is recorded in a neutral color, so I cannot build a neutral palette from this wardrobe. I will not add an unlisted piece.")
    elif topic == "potentially_busy_palette":
        needs = "Identify whether the recorded palette might feel busy; avoid calling it universally bad."
        colors = list(dict.fromkeys(x["color"] for x in palette))
        ids = [x["item_id"] for x in palette]
        answer = (f"This set spans {len(color_families)} recorded non-neutral hue families: {', '.join(colors) if colors else 'none recorded'}. Several competing families may read as busy, but saturation and exact shades are unknown and the combination is not universally bad. For a quieter version, use one listed hue family with the listed neutral pieces, if available." if len(color_families) > 2 else f"The recorded colors span {len(color_families)} non-neutral hue families. The metadata does not indicate a clear color conflict; exact shades and saturation are unknown, so judge visually rather than treating a rule label as a score.")
    elif topic in {"proportions", "silhouette"}:
        needs = "Give a practical proportion or silhouette observation only from recorded garment fit fields."
        if top and bottom and top.get("fit") and bottom.get("fit"):
            ids = [top["item_id"], bottom["item_id"]]
            answer = f"The records describe the {top['name']} as {top['fit'].lower()} and the {bottom['name']} as {bottom['fit'].lower()}. You could try this contrast to vary silhouette volume. Fit labels are incomplete clues; comfort and body shape cannot be inferred, and there is no need to dress to hide a body feature."
        else:
            answer = "I do not have both a top and bottom with fit details recorded, so I cannot make a grounded proportion comparison."
    elif topic == "pattern_coordination":
        needs = "Assess pattern coordination only when pattern labels are recorded."
        if pattern_items and bottom:
            ids = [pattern_items[0]["item_id"], bottom["item_id"]]
            answer = f"The {pattern_items[0]['pattern'].lower()} {pattern_items[0]['name']} can be the focal pattern while the recorded {bottom['pattern'].lower()} {bottom['name']} stays simpler. Pattern scale and exact colors are not recorded, so check the pieces together; this is a starting point, not a ban on mixing prints."
        else:
            answer = "Pattern details are not available for enough pieces to assess coordination. I cannot assume an item is solid or printed when its pattern is unrecorded."
    elif topic == "fabric_texture":
        needs = "Describe a fabric or texture pairing only from the supplied attributes; do not infer performance."
        material_items = [x for x in items if x.get("fabric") not in (None, "Unknown") and x.get("texture")]
        if len(material_items) >= 2:
            a, b = material_items[:2]
            ids = [a["item_id"], b["item_id"]]
            answer = f"The records list {a['fabric'].lower()} with {a['texture'].lower()} texture and {b['fabric'].lower()} with {b['texture'].lower()} texture. This gives you two different recorded surfaces to compare visually. The data does not establish warmth, breathability, drape, comfort, or care needs."
        else:
            answer = "Too few items have fabric and texture recorded for a grounded pairing. I will not infer material or performance from the garment category."
    elif topic == "layering":
        needs = "Suggest a layering order only from available items and recorded weather/season fields."
        outer = next((x for x in items if x["category"] == "Outerwear"), None)
        if top and outer:
            ids = [top["item_id"], outer["item_id"]]
            answer = f"Layer the listed {top['name']} under the listed {outer['name']}. The outerwear is a recorded category, but material, insulation, and rain protection are unknown; check the actual conditions and garment before relying on it."
        else:
            answer = "This wardrobe does not include both a top and recorded outerwear, so I cannot suggest an owned layering combination."
    elif topic == "compare_outfits":
        casual = chosen_outfit(items, "casual")
        formal = chosen_outfit(items, "formal")
        needs = "Compare two complete options for a smart-casual meeting: a relaxed casual option and a more polished option. Use only listed IDs, explain which better fits the stated setting, and mention the trade-off. If either option cannot be built, say so."
        candidate_outfits = {
            "casual_option_item_ids": [x["item_id"] for x in (casual or [])],
            "polished_option_item_ids": [x["item_id"] for x in (formal or [])],
        }
        if casual and formal:
            ids = [x["item_id"] for x in formal]
            answer = "For a smart-casual meeting, the polished option is the stronger starting point because its listed shirt, trousers, and loafers have office or meeting tags. The casual option is more relaxed and may fit a less formal meeting. Check the actual workplace dress code and personal comfort; this is a context-based preference, not an objective score."
        elif casual or formal:
            ids = [x["item_id"] for x in (formal or casual)]
            answer = "I can form only one complete option from the listed wardrobe, so a fair comparison is not possible. The available combination may be a starting point, but it cannot be treated as the better choice without the missing pieces or more context."
        else:
            answer = "Neither option can be assembled as a complete outfit from the listed wardrobe. I cannot compare them or add missing pieces."
    else:
        style_key = {"smart_casual":"smart_casual", "old_money_inspired":"old_money", "seasonal":"seasonal"}.get(topic, topic)
        selected = chosen_outfit(items, style_key)
        style_label = topic.replace("_", " ")
        needs = f"Create a {style_label} outfit for the stated wardrobe using only items that are listed. Explain the choice and note missing details."
        if selected:
            ids = [x["item_id"] for x in selected]
            colors = ", ".join(dict.fromkeys(x["color"] for x in selected))
            names = ", ".join(item_names[x] for x in ids)
            answer = f"Use {names}. The recorded palette is {colors}; this is a {style_label} direction based on the listed style tags and garment categories. Check the event dress code and personal preference; the tags do not prove fit, formality, comfort, trend status, or cultural suitability."
        else:
            answer = f"I cannot make a complete {style_label} outfit from the listed wardrobe because a required top/bottom or footwear category is missing. Add the missing kind of clothing to the wardrobe first; I will not invent or add an item."
    prompt = {
        "analysis_focus": topic,
        "request": needs,
        "available_wardrobe": [dict(x) for x in items],
        "constraints": ["Use only the listed item IDs.", "Do not infer unrecorded garment properties.", "Say when the wardrobe is incomplete."],
    }
    if candidate_outfits is not None:
        prompt["candidate_outfits"] = candidate_outfits
    # Stable unique question wording and seed allow exact regeneration.
    prompt["scenario"] = f"synthetic wardrobe case {i:03d}"
    instruction = json.dumps(prompt, ensure_ascii=False, sort_keys=True)
    response = json.dumps({"selected_item_ids": ids, "answer": answer}, ensure_ascii=False, sort_keys=True)
    source_ids, license_text = _source_for(topic)
    return {
        "messages": [
            {"role":"system", "content":"You are WearBefore, a practical personal fashion stylist. Use only the wardrobe supplied in the user message. Do not invent item IDs or garment attributes. Be clear when evidence is incomplete. Your style advice is heuristic, not an objective quality score."},
            {"role":"user", "content":instruction},
            {"role":"assistant", "content":response},
        ],
        "instruction": instruction,
        "response": response,
        "scenario_id": f"wardrobe_{i:03d}",
        "topic": topic,
        "source_ids": source_ids,
        "license": license_text,
        "synthetic": True,
    }


def split_scenario(i: int, incomplete_rank: int, complete_rank: int) -> str:
    rank = incomplete_rank if i % 5 == 0 else complete_rank
    return "train" if rank % 10 < 8 else "valid" if rank % 10 == 8 else "test"


def curated_example(case: dict[str, Any]) -> dict[str, Any]:
    wardrobe_ids = {item["item_id"] for item in case["wardrobe"]}
    a, b = case["a"], case["b"]
    selected = a if case["choose"] == "a" else b
    if not set(a + b + selected) <= wardrobe_ids:
        raise ValueError(f"Curated case {case['id']} references an unlisted item.")
    prompt = {
        "analysis_focus": ["color coordination", "recorded fit and proportions", "occasion tags"],
        "occasion": case["occasion"],
        "available_wardrobe": case["wardrobe"],
        "candidate_outfits": {"option_a_item_ids": a, "option_b_item_ids": b},
        "request": "Compare both options for this occasion. Explain their recorded color coordination, fit/proportion differences, and occasion suitability. Choose one only if the available evidence supports it; name missing information that could change the choice.",
        "constraints": ["Use only listed item IDs.", "Do not add garments or infer unrecorded attributes.", "Treat styling judgments as contextual heuristics, not universal laws or scores."],
    }
    response = {"selected_item_ids": selected, "answer": case["answer"]}
    instruction = json.dumps(prompt, ensure_ascii=False, sort_keys=True)
    target = json.dumps(response, ensure_ascii=False, sort_keys=True)
    pair_hash = hashlib.sha256((instruction + "\0" + target).encode()).hexdigest()
    return {
        "messages": [
            {"role":"system", "content":"You are WearBefore, a practical personal fashion stylist. Ground every suggestion in the supplied wardrobe. Compare options using recorded evidence, state uncertainty, and never invent clothes, attributes, scores, or user preferences."},
            {"role":"user", "content":instruction},
            {"role":"assistant", "content":target},
        ],
        "instruction": instruction, "response": target,
        "scenario_id": case["id"], "topic":"curated_outfit_comparison",
        "source_ids":["fashionpedia_ontology_ccby4", "wearbefore_original_styling_rules"],
        "license":"Fashionpedia ontology/schema CC BY 4.0 (attributed; images excluded); original WearBefore answer CC BY 4.0",
        "synthetic":True, "authorship":"original_manual_curation; not expert reviewed",
        "record_id":pair_hash,
    }


def build() -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    split_buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    counts = Counter()
    topic_counts = Counter()
    instruction_hashes: set[str] = set()
    pair_hashes: set[str] = set()
    complete_rank = incomplete_rank = 0
    for i in range(TARGET_SCENARIOS):
        pieces = wardrobe(i)
        split = split_scenario(i, incomplete_rank, complete_rank)
        if i % 5 == 0:
            incomplete_rank += 1
        else:
            complete_rank += 1
        for topic in TOPICS:
            row = make_example(i, topic, pieces)
            inst = row["instruction"].strip()
            response = row["response"].strip()
            ihash = hashlib.sha256(inst.encode()).hexdigest()
            phash = hashlib.sha256((inst + "\0" + response).encode()).hexdigest()
            if ihash in instruction_hashes or phash in pair_hashes:
                raise ValueError(f"Duplicate at scenario {i}, topic {topic}.")
            instruction_hashes.add(ihash)
            pair_hashes.add(phash)
            row["record_id"] = phash
            split_buckets[split].append(row)
            records.append(row)
            counts[split] += 1
            topic_counts[f"{split}:{topic}"] += 1
    curated_cases = json.loads(CURATED_CASES.read_text(encoding="utf-8"))
    curated_seen = set()
    for case in curated_cases:
        if case["id"] in curated_seen or case["id"] in {f"wardrobe_{i:03d}" for i in range(TARGET_SCENARIOS)}:
            raise ValueError(f"Duplicate curated scenario ID {case['id']}.")
        curated_seen.add(case["id"])
        if case["split"] not in split_buckets:
            raise ValueError(f"Invalid split for curated case {case['id']}.")
        row = curated_example(case)
        split_buckets[case["split"]].append(row)
        records.append(row)
        counts[case["split"]] += 1
        topic_counts[f"{case['split']}:curated_outfit_comparison"] += 1
    OUT.mkdir(parents=True, exist_ok=True)
    for split, rows in split_buckets.items():
        with (OUT / f"{split}.jsonl").open("w", encoding="utf-8") as stream:
            for row in rows:
                # The MLX-LM chat loader uses messages; metadata is retained in JSONL.
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    all_sources = json.loads(KNOWLEDGE.read_text(encoding="utf-8"))["sources"]
    used_source_ids = {sid for row in records for sid in row["source_ids"]}
    sources = [source for source in all_sources if source["id"] in used_source_ids]
    manifest = {
        "dataset_name":"WearBefore synthetic wardrobe grounded fashion SFT",
        "version":"1.2.0", "records":len(records), "splits":dict(counts),
        "topics":[*TOPICS, "curated_outfit_comparison"], "topic_counts":dict(sorted(topic_counts.items())),
        "scenario_groups":TARGET_SCENARIOS,
        "split_method":"Generated wardrobe scenarios are kept whole with deterministic 80/10/10 stratification for complete/incomplete cases. The 24 manually authored comparison scenarios use separate group IDs and a deterministic 18/3/3 split.",
        "provenance":"The original 2,100 synthetic programmatic examples are retained. 24 additional fictional wardrobe comparisons are manually authored and use the Fashionpedia ontology only as an attributed CC BY 4.0 schema reference. No user wardrobe, feedback, Fashionpedia images, image-level annotations, or LLM-generated targets were used. Curated responses are not expert reviewed.",
        "license_note":"Rows using external sources carry per-record source_ids/license. No NC-licensed source is used in the training splits. Fashionpedia is used only for its CC BY 4.0 ontology/schema; its images are excluded. Polyvore and DeepFashion are excluded due rights restrictions or unresolved terms. See training/FASHION_DATASET_LICENSE_AUDIT.md.",
        "sources":sources,
        "quality_checks":{"unique_instructions":len(instruction_hashes),"unique_instruction_response_pairs":len(pair_hashes),"duplicate_count":0,"wardrobe_id_constraint":"Every selected_item_ids value is drawn from that record's available_wardrobe; incomplete outfit scenarios return an empty list."},
        "limitations":["Synthetic supervision does not substitute for designer or user review.","Item/colour/fabric combinations are fictional; responses teach conservative heuristics, not outfit quality rankings.","The 2,000 target is a corpus size target, not evidence of accuracy or generalization."],
    }
    manifest["topic_family_counts"] = {topic:sum(1 for row in records if row["topic"] == topic)
                                       for topic in [*TOPICS, "curated_outfit_comparison"]}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    print(json.dumps(build(), indent=2, ensure_ascii=False))
