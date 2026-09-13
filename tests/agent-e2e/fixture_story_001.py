# -*- coding: utf-8 -*-
"""fixture_story_001 —— 固定剧本 + 资产清单（#13）。

明确包含：
  3 个重要角色 (critical)
  3 个重要场景 (critical)
  2 个重要道具 (important)
  -> 待生产资产 total = 8

外加 1 个 optional 资产（未被任何 Shot 引用）。

Shot 数据引用 stable asset ID（绝不靠名称）。
"""
FIXTURE_ID = "fixture_story_001"

# 真实文生图提示词（非空、有效），用于 Phase 7 prompt ready 提交
GOOD_PROMPTS = {
    "character_001": "电影感半身肖像，年轻女主林澜，黑色长发，深蓝风衣，冷调侧光，8k，细节丰富",
    "character_002": "电影感全身肖像，男配角陈默，灰西装，雨夜街灯暖光，湿润地面倒影",
    "character_003": "电影感特写，反派苏野，银框眼镜，阴影分割面部，高反差",
    "location_001": "废弃工厂外景，生锈钢架，体积雾，黄昏逆光，广角，电影感",
    "location_002": "现代公寓客厅，暖色木质家具，窗外城市夜景，浅景深",
    "location_003": "地下车库，单一顶光，潮湿墙面，悬疑氛围，冷青色调",
    "prop_001": "复古怀表特写，金属质感，微距，暖光，背景虚化",
    "prop_002": "染血信笺，手写字体，桌面俯拍，戏剧性侧光",
}

ASSET_MANIFEST = [
    {"assetId": "character_001", "name": "林澜", "assetType": "character", "importance": "critical", "usedInShots": ["shot_001", "shot_002"]},
    {"assetId": "character_002", "name": "陈默", "assetType": "character", "importance": "critical", "usedInShots": ["shot_001", "shot_003"]},
    {"assetId": "character_003", "name": "苏野", "assetType": "character", "importance": "critical", "usedInShots": ["shot_002", "shot_003"]},
    {"assetId": "location_001", "name": "废弃工厂", "assetType": "location", "importance": "critical", "usedInShots": ["shot_001"]},
    {"assetId": "location_002", "name": "现代公寓", "assetType": "location", "importance": "critical", "usedInShots": ["shot_002"]},
    {"assetId": "location_003", "name": "地下车库", "assetType": "location", "importance": "critical", "usedInShots": ["shot_003"]},
    {"assetId": "prop_001", "name": "复古怀表", "assetType": "prop", "importance": "important", "usedInShots": ["shot_001"]},
    {"assetId": "prop_002", "name": "染血信笺", "assetType": "prop", "importance": "important", "usedInShots": ["shot_003"]},
    # optional：不被任何 shot 引用 -> 默认不进 Canvas
    {"assetId": "background_extra_01", "name": "街景背景", "assetType": "location", "importance": "optional", "usedInShots": []},
]

SHOTS = [
    {"shotId": "shot_001", "characterRefs": ["character_001", "character_002"],
     "locationRefs": ["location_001"], "propRefs": ["prop_001"]},
    {"shotId": "shot_002", "characterRefs": ["character_001", "character_003"],
     "locationRefs": ["location_002"], "propRefs": []},
    {"shotId": "shot_003", "characterRefs": ["character_002", "character_003"],
     "locationRefs": ["location_003"], "propRefs": ["prop_002"]},
]

EXPECTED_CRITICAL_IMPORTANT = 8  # 不含 optional
EXPECTED_CHARACTER = 3
EXPECTED_LOCATION = 3
EXPECTED_PROP = 2


def critical_important_assets():
    return [a for a in ASSET_MANIFEST if a["importance"] in ("critical", "important")]


def asset_by_id(aid):
    return next((a for a in ASSET_MANIFEST if a["assetId"] == aid), None)


def shot_by_id(sid):
    return next((s for s in SHOTS if s["shotId"] == sid), None)


def ready_asset_ids():
    """假设所有 critical/important 资产 prompt 已 ready。"""
    return [a["assetId"] for a in critical_important_assets()]
