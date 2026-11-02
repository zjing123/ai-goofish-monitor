from src.domain import sale_status as sale_state
from src.services.sale_check_service import classify_sale_state, extract_item_id


def test_classify_sold_from_item_status_code():
    payload = {
        "ret": ["SUCCESS::调用成功"],
        "data": {"itemDO": {"itemStatus": 1, "itemStatusStr": "卖掉了"}},
    }
    assert classify_sale_state(payload, "") == (sale_state.SOLD, "itemStatus=1")


def test_classify_on_sale_from_item_status_code():
    payload = {
        "ret": ["SUCCESS::调用成功"],
        "data": {"itemDO": {"itemStatus": 0, "itemStatusStr": "在线"}},
    }
    assert classify_sale_state(payload, "") == (sale_state.ON_SALE, "itemStatus=0")


def test_classify_delisted_from_deleted_ret():
    payload = {
        "ret": ["FAIL_BIZ_ITEM_DEL_NOT_FOUND::您要看的宝贝不存在或已被删除啦!"],
        "data": {},
    }
    assert classify_sale_state(payload, "") == (sale_state.DELISTED, "detail_api_deleted")


def test_classify_falls_back_to_page_text():
    payload = {"ret": ["SUCCESS::调用成功"], "data": {}}
    assert classify_sale_state(payload, "该商品卖掉了")[0] == sale_state.SOLD
    assert classify_sale_state(payload, "宝贝被删掉了")[0] == sale_state.DELISTED


def test_classify_sold_from_string_item_status_code():
    payload = {
        "ret": ["SUCCESS::调用成功"],
        "data": {"itemDO": {"itemStatus": "1"}},
    }
    assert classify_sale_state(payload, "") == (sale_state.SOLD, "itemStatus=1")


def test_classify_ignores_invalid_item_status_code():
    payload = {
        "ret": ["SUCCESS::调用成功"],
        "data": {"itemDO": {"itemStatus": "abc"}},
    }
    assert classify_sale_state(payload, "")[0] == sale_state.UNKNOWN


def test_classify_unknown_without_signal():
    assert classify_sale_state(None, "")[0] == sale_state.UNKNOWN


def test_extract_item_id_prefers_column_then_link():
    assert extract_item_id("123", "https://www.goofish.com/item?id=456") == "123"
    assert (
        extract_item_id(None, "https://www.goofish.com/item?id=456&foo=bar")
        == "456"
    )
    assert extract_item_id(None, None) is None
