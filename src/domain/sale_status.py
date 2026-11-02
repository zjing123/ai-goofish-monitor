"""商品售卖状态常量。"""
from __future__ import annotations

UNKNOWN = "unknown"
ON_SALE = "on_sale"
SOLD = "sold"
DELISTED = "delisted"

VALID_SALE_STATUSES = frozenset({UNKNOWN, ON_SALE, SOLD, DELISTED})
UNAVAILABLE_SALE_STATUSES = frozenset({SOLD, DELISTED})

# 闲鱼详情接口 itemDO.itemStatus：0=在线，1=卖掉了，2=已删除/下架
ITEM_STATUS_CODE_MAP = {
    0: ON_SALE,
    1: SOLD,
    2: DELISTED,
}
