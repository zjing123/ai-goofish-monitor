"""
AI 请求消息构造辅助函数

Cache-friendly layout: the fixed analysis criteria live in the system
message (stable prefix for implicit prompt caching, e.g. DashScope/DeepSeek
auto context cache), while the per-item product JSON goes in the user
message. Text parts come before image parts so the prefix stays identical
across requests.
"""
from typing import Dict, List, Union


TEXT_ONLY_ANALYSIS_NOTE = (
    "补充说明：本次未提供商品图片，请仅根据商品文字字段和卖家信息判断，不要推断图片内容。"
)

VALUE_NOTE = (
    "\n如果商品 JSON 中包含“价格参考”或 price_insight，请结合价格位置、历史走势、"
    "配置、成色、附件、卖家信息综合判断性价比。"
    "你可以额外输出可选字段 value_score(0-100) 和 value_summary，"
    "但必须保留原有 is_recommended/reason 等字段。\n"
)


def build_analysis_system_prompt(prompt_text: str, *, include_images: bool) -> str:
    """Fixed system prompt: analysis criteria + static notes (cacheable prefix)."""
    note = "" if include_images else f"\n{TEXT_ONLY_ANALYSIS_NOTE}\n"
    return f"{prompt_text}{VALUE_NOTE}{note}"


def build_analysis_user_text(product_json: str) -> str:
    """Varying user text: the product payload only."""
    return f"请基于你的专业知识和我的要求，分析以下完整的商品JSON数据：\n\n```json\n{product_json}\n```"


def build_user_message_content(
    text_prompt: str,
    image_data_urls: List[str],
) -> Union[str, List[Dict[str, object]]]:
    # Text first, images after: keeps the prefix identical for implicit caching.
    if not image_data_urls:
        return text_prompt

    user_content: List[Dict[str, object]] = [
        {"type": "text", "text": text_prompt},
    ]
    user_content.extend(
        {"type": "image_url", "image_url": {"url": url}}
        for url in image_data_urls
    )
    return user_content


def build_analysis_messages(
    product_json: str,
    prompt_text: str,
    *,
    include_images: bool,
    image_data_urls: List[str] | None = None,
) -> List[Dict[str, object]]:
    """Assemble the full chat messages for one product analysis."""
    system_content = build_analysis_system_prompt(prompt_text, include_images=include_images)
    user_content = build_user_message_content(
        build_analysis_user_text(product_json),
        image_data_urls or [],
    )
    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]
