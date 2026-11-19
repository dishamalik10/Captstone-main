#llm have fashion knowledge for this one 

from tools.llm_client import call_llm


def analyze_fashion_trends(occasion: str, mood: str) -> str:
    """
    Generate fashion guidance using the shared local model service.
    """

    prompt = f"""
You are an expert fashion stylist.

Given:

Occasion: {occasion}
Mood: {mood}

Generate concise fashion trend guidance.

Include:

- Durable fashion aesthetic suitable for the occasion; do not claim live/current trends without dated local evidence
- Trending colors
- Recommended silhouettescan u a
- Appropriate footwear style
- Accessories to consider
- Items to avoid

Do NOT recommend specific clothing items.

Return plain English reasoning only.
"""

    return call_llm(prompt)



# if __name__ == "__main__":
#     result = analyze_fashion_trends("Party", "Confident")
#     print(result)
