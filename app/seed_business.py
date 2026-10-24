"""Deterministic commercial fixture generator: advertisers, campaigns, history.

The data is fictional but internally consistent: every campaign points at a
creative, an outlet advertiser, a placement, a budget and 30 days of history.
"""

from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

ADVERTISERS = [
    ("ADV-01", "Meridian Duty Free", "retailer", "#38e8c8", "trade@meridianduty.example"),
    ("ADV-02", "Café Meridian", "retailer", "#ffb454", "marketing@cafemeridian.example"),
    ("ADV-03", "Toy Emporium", "retailer", "#ff647c", "hello@toyemporium.example"),
    ("ADV-04", "CloudNine Lounge", "retailer", "#8b7bff", "sales@cloudnine.example"),
    ("ADV-05", "Beachwear Co", "retailer", "#4cc9f0", "team@beachwear.example"),
    ("ADV-06", "ChocoAtlas", "retailer", "#c9f45b", "brand@chocoatlas.example"),
    ("ADV-07", "LuxTime", "retailer", "#f4d35e", "media@luxtime.example"),
    ("ADV-08", "PageTurner Books", "retailer", "#a88beb", "store@pageturner.example"),
    ("ADV-09", "Serenity Spa", "retailer", "#6ee7b7", "book@serenityspa.example"),
    ("ADV-10", "TravelTech Hub", "retailer", "#60a5fa", "ads@traveltech.example"),
    ("ADV-11", "Meridian Forex", "retailer", "#34d399", "fx@meridianforex.example"),
    ("ADV-12", "GreenLeaf Pharmacy", "retailer", "#86efac", "care@greenleaf.example"),
    ("ADV-13", "Runway Sports", "retailer", "#f97316", "run@runwaysports.example"),
    ("ADV-14", "Atelier North", "retailer", "#e879f9", "press@ateliernorth.example"),
    ("ADV-15", "Sweet Crumb", "retailer", "#fb7185", "bake@sweetcrumb.example"),
    ("ADV-16", "Aurora Hotels", "brand", "#38bdf8", "media@aurorahotels.example"),
    ("ADV-17", "Velvet Cosmetics", "retailer", "#f472b6", "brand@velvet.example"),
    ("ADV-18", "Meridian Market", "house", "#94a3b8", "ops@meridian.example"),
    ("ADV-AIR-XH", "Halcyon Airways", "airline", "#f4d35e", "brand@halcyon.example"),
    ("ADV-AIR-ZO", "Solano Airways", "airline", "#ff647c", "brand@solano.example"),
    ("ADV-AIR-YU", "Lumen Pacific Airlines", "airline", "#e879f9", "brand@lumenpacific.example"),
    ("ADV-AIR-XD", "Skylark Air", "airline", "#38e8c8", "brand@skylark.example"),
]

OUTLET_SPECS = [
    ("ADV-01", "Meridian Duty Free · T2 Boulevard", "T2-DUTY", "duty_free"),
    ("ADV-01", "Meridian Duty Free · T2 Gates 40–45", "T2-F", "duty_free"),
    ("ADV-01", "Meridian Duty Free · T1 Market Lane", "T1-RETAIL", "duty_free"),
    ("ADV-01", "Meridian Duty Free Express · T2-D", "T2-D", "duty_free"),
    ("ADV-02", "Café Meridian · Skyline Food Court", "T2-FOOD", "food"),
    ("ADV-02", "Café Meridian · T2 Gate 33", "T2-E", "food"),
    ("ADV-02", "Café Meridian · Harbour Food Court", "T1-FOOD", "food"),
    ("ADV-02", "Café Meridian · T1 Gate 8", "T1-A", "food"),
    ("ADV-02", "Café Meridian · Arrivals", "ARRIVALS", "food"),
    ("ADV-03", "Toy Emporium · T2 Boulevard", "T2-DUTY", "toys"),
    ("ADV-03", "Toy Emporium · T1 Market Lane", "T1-RETAIL", "toys"),
    ("ADV-04", "CloudNine Lounge · T2-F", "T2-LOUNGE", "lounge"),
    ("ADV-04", "CloudNine Lounge · T1-C", "T1-LOUNGE", "lounge"),
    ("ADV-05", "Beachwear Co · T2 Boulevard", "T2-DUTY", "fashion"),
    ("ADV-05", "Beachwear Co · T1 Market Lane", "T1-RETAIL", "fashion"),
    ("ADV-06", "ChocoAtlas · T2 Boulevard", "T2-DUTY", "sweets"),
    ("ADV-06", "ChocoAtlas · Skyline Food Court", "T2-FOOD", "sweets"),
    ("ADV-07", "LuxTime · T2 Boulevard", "T2-DUTY", "watches"),
    ("ADV-07", "LuxTime · T1 Market Lane", "T1-RETAIL", "watches"),
    ("ADV-08", "PageTurner · T2-D", "T2-D", "books"),
    ("ADV-08", "PageTurner · T1 Market Lane", "T1-RETAIL", "books"),
    ("ADV-09", "Serenity Spa · T2 Sky Lounge", "T2-LOUNGE", "wellness"),
    ("ADV-09", "Serenity Spa · T1 Northgate", "T1-LOUNGE", "wellness"),
    ("ADV-10", "TravelTech Hub · T2 Boulevard", "T2-DUTY", "electronics"),
    ("ADV-10", "TravelTech Hub · T1 Market Lane", "T1-RETAIL", "electronics"),
    ("ADV-11", "Meridian Forex · T2-D", "T2-D", "services"),
    ("ADV-11", "Meridian Forex · T1-B", "T1-B", "services"),
    ("ADV-12", "GreenLeaf Pharmacy · T2-E", "T2-E", "pharmacy"),
    ("ADV-12", "GreenLeaf Pharmacy · T1-B", "T1-B", "pharmacy"),
    ("ADV-13", "Runway Sports · T2 Boulevard", "T2-DUTY", "sports"),
    ("ADV-13", "Runway Sports · T1 Market Lane", "T1-RETAIL", "sports"),
    ("ADV-14", "Atelier North · T2 Boulevard", "T2-DUTY", "fashion"),
    ("ADV-14", "Atelier North · T1 Market Lane", "T1-RETAIL", "fashion"),
    ("ADV-15", "Sweet Crumb · Skyline Food Court", "T2-FOOD", "bakery"),
    ("ADV-15", "Sweet Crumb · Harbour Food Court", "T1-FOOD", "bakery"),
    ("ADV-17", "Velvet Cosmetics · T2 Boulevard", "T2-DUTY", "cosmetics"),
    ("ADV-17", "Velvet Cosmetics · T1 Market Lane", "T1-RETAIL", "cosmetics"),
    ("ADV-17", "Velvet Beauty Bar · T2-E", "T2-E", "cosmetics"),
    ("ADV-18", "Meridian Market · T2-D", "T2-D", "convenience"),
    ("ADV-18", "Meridian Market · T1-A", "T1-A", "convenience"),
]

CREATIVE_SPECS = {
    "CMP-01": ("Golden Hour", "Golden Hour at Duty Free", "黄金时刻 · 免税香氛", "Save 15% on fragrance before your flight.", "登机前香氛立减 15%。", "Shop the edit", "立即选购", "aurora", ["#f4d35e", "#ff647c"], "perfume"),
    "CMP-02": ("Toybox", "Buy 2, get 1 free", "玩具买二送一", "Keep little travellers smiling. Family bundle at Toy Emporium.", "让小旅客一路开心，家庭套装买二送一。", "Find the toybox", "去挑玩具", "grid", ["#38e8c8", "#8b7bff"], "toys"),
    "CMP-03": ("Quiet Runway", "Your lounge, 45 minutes", "登机前，留 45 分钟给自己", "Day passes to CloudNine from €29.", "CloudNine 贵宾厅日票 29 欧元起。", "Reserve a pass", "预订日票", "lumen", ["#8b7bff", "#38e8c8"], "lounge"),
    "CMP-04": ("Gate Brew", "Gate-side coffee, made fast", "登机口旁的手冲咖啡", "Two minutes from Gate 40. Flat white + pastry €7.", "距 40 号登机口两分钟，拿铁配可颂 7 欧元。", "Order ahead", "提前下单", "wave", ["#ffb454", "#ff647c"], "coffee"),
    "CMP-05": ("Salt & Sun", "Beach-ready in 10 minutes", "十分钟，进入海岛状态", "Sun hats, linen and reef-safe SPF at Beachwear Co.", "遮阳帽、亚麻与珊瑚友好防晒。", "Pack the sunshine", "打包阳光", "aurora", ["#4cc9f0", "#f4d35e"], "beach"),
    "CMP-06": ("Cocoa Atlas", "A taste of six cities", "六座城市的可可风味", "Single-origin chocolate tasting box, 20% off today.", "单一产地巧克力品鉴盒，今日八折。", "Taste the map", "尝遍地图", "grid", ["#c9f45b", "#ffb454"], "sweets"),
    "CMP-07": ("Second Time", "Time, beautifully kept", "把时间，优雅收藏", "Swiss movement, airport exclusive. Complimentary engraving.", "瑞士机芯，机场限定，免费刻字。", "Book a viewing", "预约鉴赏", "lumen", ["#f4d35e", "#8b7bff"], "watches"),
    "CMP-08": ("One More Chapter", "One more chapter", "再读一章", "Travel fiction and city guides, 3 for 2.", "旅行小说与城市指南，买三付二。", "Browse shelves", "逛逛书架", "paper", ["#a88beb", "#38e8c8"], "books"),
    "CMP-09": ("Still Point", "Twenty minutes of quiet", "二十分钟的安静", "Express massage or facial before boarding.", "登机前快速按摩或面部护理。", "Book quiet", "预约安静", "wave", ["#6ee7b7", "#4cc9f0"], "wellness"),
    "CMP-10": ("Plugged In", "Land connected", "落地即联网", "eSIM + charger bundle, set up in two minutes.", "eSIM 与充电套装，两分钟搞定。", "Get connected", "立即联网", "grid", ["#60a5fa", "#38e8c8"], "tech"),
    "CMP-11": ("Rate Ready", "Travel money, ready", "出行外币，提前备好", "Lock today's rate. No airport queue.", "锁定今日汇率，无需排队。", "Lock a rate", "锁定汇率", "paper", ["#34d399", "#38e8c8"], "forex"),
    "CMP-12": ("Travel Well", "Travel well, land better", "轻松出行，健康抵达", "Sleep, hydration and motion-sickness kits.", "助眠、补水与晕机护理包。", "Pack the essentials", "备好必需品", "wave", ["#86efac", "#38e8c8"], "pharmacy"),
    "CMP-13": ("Runway 21", "Move before you fly", "起飞前，先动起来", "Trainers and travel kit, 20% off.", "运动鞋与旅行套装八折。", "Gear up", "装备起来", "grid", ["#f97316", "#f4d35e"], "sports"),
    "CMP-14": ("North Light", "Made for the journey", "为旅途而设计", "Atelier North travel tailoring, airport exclusive.", "Atelier North 旅行系列，机场限定。", "See the collection", "查看系列", "lumen", ["#e879f9", "#8b7bff"], "fashion"),
    "CMP-15": ("Warm Crumb", "Something warm for the gate", "登机口前的热乎点心", "Cinnamon knot + coffee, €5 before 16:00.", "肉桂卷配咖啡，16 点前 5 欧元。", "Grab a warm one", "来个热的", "wave", ["#fb7185", "#ffb454"], "bakery"),
    "CMP-16": ("Stay Another Day", "Stay another day", "多住一晚，慢慢离开", "Aurora Hotels, 15% off for MQI arrivals.", "Aurora 酒店，MQI 到达旅客八五折。", "Extend the trip", "延长旅程", "aurora", ["#38bdf8", "#8b7bff"], "hotel"),
    "CMP-17": ("Velvet Hour", "Velvet hour", "丝绒时刻", "Lip and complexion edit, free colour match.", "唇妆与底妆系列，免费试色。", "Find your shade", "找到你的色号", "lumen", ["#f472b6", "#e879f9"], "cosmetics"),
    "CMP-18": ("Meridian House", "Gate 42 · everything you need", "42 号登机口 · 所需尽在", "Flight information, offers and a map in one place.", "航班信息、优惠与地图，一站式查看。", "Explore the airport", "探索机场", "paper", ["#94a3b8", "#38e8c8"], "house"),
    "CMP-19": ("Halcyon Upgrade", "This flight, a little wider", "这趟航班，再宽一点", "Upgrade to business from €149. Ask at the gate.", "商务舱升级 149 欧元起，登机口咨询。", "Ask about upgrade", "咨询升舱", "aurora", ["#f4d35e", "#ff647c"], "airline"),
    "CMP-20": ("Solano Sky", "Solano Sky Lounge", "Solano 天际贵宾厅", "Relax before Dubai. Two hours, €35.", "飞往迪拜前，贵宾厅两小时 35 欧元。", "Add lounge access", "加购贵宾厅", "lumen", ["#ff647c", "#8b7bff"], "airline"),
    "CMP-21": ("Lumen Coast", "Coast to coast with Lumen", "与 Lumen 一起跨越海岸", "Family fare bundle with 2 checked bags.", "家庭票价含两件托运行李。", "See family fares", "查看家庭票价", "aurora", ["#e879f9", "#4cc9f0"], "airline"),
    "CMP-22": ("Skylark Saver", "Skylark saver fares", "Skylark 特惠票价", "Domestic fares from €39, flexible changes.", "国内票价 39 欧元起，灵活改签。", "Fly for less", "低价起飞", "paper", ["#38e8c8", "#c9f45b"], "airline"),
    "CMP-23": ("Gulf Gold", "Gulf-bound? Gold hour.", "飞往海湾？金色时刻。", "Fragrance and gold, 20% off for Gulf departures.", "飞往海湾的旅客，香氛与金饰八折。", "Claim Gulf Gold", "领取海湾礼遇", "aurora", ["#f4d35e", "#38e8c8"], "perfume"),
    "CMP-24": ("Half-Term Heroes", "Half-term heroes", "期中假小英雄", "Toy bundle for school-holiday families.", "为期中假家庭准备的玩具套装。", "Build a bundle", "组合套装", "grid", ["#ff647c", "#c9f45b"], "toys"),
    "CMP-25": ("Morning Runway", "Morning runway", "清晨跑道", "Breakfast + coffee before 10:00.", "10 点前早餐配咖啡。", "Start the day", "开启一天", "wave", ["#ffb454", "#8b7bff"], "coffee"),
}

CAMPAIGN_SPECS = [
    ("CMP-01", "ADV-01", "Golden Hour · Duty Free", "approved", "perfume", {"international": 0.9, "holiday": 0.8, "luxury": 0.6, "shopper": 0.7}, {"internationalOnly": True, "destinations": ["DXB", "SMG", "ZHQ", "LHR", "SIN"], "minDwell": 15, "minCrowd": 80}, {"zones": ["T2-F", "T2-DUTY", "T2-E"]}, {"delayOver": 30}, 12000, 800, 20, 4.2, 2, -20, 20, "all_day"),
    ("CMP-02", "ADV-03", "Toy Emporium · Buy 2 Get 1", "approved", "toys", {"family": 1.0, "holiday": 0.8, "vfr": 0.5}, {"minCrowd": 70, "minDwell": 10}, {"zones": ["T2-F", "T2-E", "T2-FOOD", "T1-FOOD"]}, {}, 9000, 600, 15, 3.4, 1, -18, 25, "all_day"),
    ("CMP-03", "ADV-04", "CloudNine · Day Pass", "approved", "lounge", {"business": 0.9, "luxury": 0.8, "international": 0.6}, {"minDwell": 45, "minCrowd": 60}, {"zones": ["T2-E", "T2-LOUNGE", "T1-LOUNGE"]}, {"boarding": True}, 7000, 500, 25, 3.8, 1, -15, 30, "all_day"),
    ("CMP-04", "ADV-02", "Café Meridian · Gate Brew", "approved", "coffee", {"business": 0.4, "holiday": 0.4, "family": 0.3}, {}, {"zones": ["T2-FOOD", "T2-E", "T1-FOOD", "T1-A", "ARRIVALS"]}, {}, 6000, 400, 12, 2.2, 1, -25, 20, "all_day"),
    ("CMP-05", "ADV-05", "Beachwear · Salt & Sun", "approved", "beach", {"holiday": 1.0, "couple": 0.6, "beach": 0.9}, {"destinations": ["SCJ", "BCN", "CPZ", "GSZ"], "minDwell": 15}, {"zones": ["T2-DUTY", "T2-F", "T1-RETAIL"]}, {}, 8000, 550, 20, 3.0, 1, -12, 28, "all_day"),
    ("CMP-06", "ADV-06", "ChocoAtlas · Six Cities", "approved", "sweets", {"family": 0.7, "holiday": 0.7, "vfr": 0.5, "gourmet": 0.6}, {"minCrowd": 50}, {"zones": ["T2-DUTY", "T2-FOOD", "T1-RETAIL"]}, {}, 5000, 350, 15, 2.4, 1, -22, 22, "all_day"),
    ("CMP-07", "ADV-07", "LuxTime · Second Time", "approved", "watches", {"luxury": 1.0, "business": 0.7, "senior": 0.5, "international": 0.8}, {"internationalOnly": True, "minDwell": 30, "minCrowd": 80}, {"zones": ["T2-DUTY", "T2-F"]}, {"delayOver": 45}, 15000, 900, 30, 5.0, 2, -16, 35, "all_day"),
    ("CMP-08", "ADV-08", "PageTurner · One More Chapter", "approved", "books", {"vfr": 0.6, "student": 0.5, "solo": 0.5, "couple": 0.3}, {}, {"zones": ["T2-D", "T1-RETAIL", "T1-C"]}, {}, 4000, 300, 20, 1.8, 1, -28, 18, "all_day"),
    ("CMP-09", "ADV-09", "Serenity Spa · Still Point", "approved", "wellness", {"wellness": 0.9, "senior": 0.5, "business": 0.4}, {"minDwell": 40}, {"zones": ["T2-LOUNGE", "T1-LOUNGE"]}, {}, 5500, 380, 30, 2.6, 1, -10, 30, "all_day"),
    ("CMP-10", "ADV-10", "TravelTech · Land Connected", "approved", "tech", {"tech": 0.9, "business": 0.6, "young": 0.5, "international": 0.6}, {"minCrowd": 60}, {"zones": ["T2-DUTY", "T2-D", "T1-RETAIL"]}, {"gateChange": True}, 9000, 600, 20, 3.2, 1, -14, 26, "all_day"),
    ("CMP-11", "ADV-11", "Meridian Forex · Rate Ready", "approved", "forex", {"international": 1.0, "business": 0.4}, {"internationalOnly": True, "minCrowd": 100}, {"zones": ["T2-D", "T2-F", "T1-B"]}, {}, 4500, 300, 25, 2.0, 1, -30, 15, "all_day"),
    ("CMP-12", "ADV-12", "GreenLeaf · Travel Well", "approved", "pharmacy", {"family": 0.5, "senior": 0.6, "vfr": 0.4}, {}, {"zones": ["T2-E", "T1-B", "T1-FOOD"]}, {}, 3500, 250, 20, 1.5, 1, -26, 20, "all_day"),
    ("CMP-13", "ADV-13", "Runway Sports · Runway 21", "approved", "sports", {"young": 0.7, "solo": 0.5, "tech": 0.3}, {"minCrowd": 50}, {"zones": ["T2-DUTY", "T1-RETAIL"]}, {}, 6000, 400, 18, 2.1, 1, -20, 24, "all_day"),
    ("CMP-14", "ADV-14", "Atelier North · North Light", "rejected", "fashion", {"luxury": 0.8, "young": 0.6, "shopper": 0.7}, {"internationalOnly": True, "minDwell": 25}, {"zones": ["T2-DUTY"]}, {}, 11000, 700, 25, 4.0, 1, -8, 20, "all_day"),
    ("CMP-15", "ADV-15", "Sweet Crumb · Warm Crumb", "approved", "bakery", {"family": 0.7, "gourmet": 0.6, "holiday": 0.4}, {}, {"zones": ["T2-FOOD", "T1-FOOD"]}, {}, 3000, 220, 12, 1.6, 1, -24, 21, "all_day"),
    ("CMP-16", "ADV-16", "Aurora Hotels · Stay Another Day", "approved", "hotel", {"holiday": 0.9, "international": 0.8, "couple": 0.5}, {"internationalOnly": True, "destinations": ["DXB", "SMG", "ZHQ", "LHR", "SIN", "JFK"], "minDwell": 20}, {"zones": ["ARRIVALS", "T2-D", "T2-F"]}, {"delayOver": 60}, 10000, 650, 30, 3.6, 1, -11, 32, "all_day"),
    ("CMP-17", "ADV-17", "Velvet Cosmetics · Velvet Hour", "pending", "cosmetics", {"luxury": 0.7, "young": 0.7, "international": 0.6, "shopper": 0.8}, {"minCrowd": 60}, {"zones": ["T2-DUTY", "T2-E", "T1-RETAIL"]}, {}, 7500, 500, 20, 3.1, 1, -3, 28, "all_day"),
    ("CMP-18", "ADV-18", "Meridian House · Gate 42", "approved", "house", {"value": 0.8, "family": 0.3, "business": 0.3}, {}, {"zones": ["*"]}, {}, 900000, 50000, 8, 0.4, 0, -40, 60, "all_day"),
    ("CMP-19", "ADV-AIR-XH", "Halcyon · This Flight, Wider", "approved", "airline", {"business": 0.9, "luxury": 0.7}, {"airline": "XH", "minDwell": 20}, {"gates": ["43", "44", "45"]}, {"boarding": True}, 6000, 400, 20, 3.0, 2, -20, 20, "all_day"),
    ("CMP-20", "ADV-AIR-ZO", "Solano · Sky Lounge", "approved", "airline", {"holiday": 0.8, "international": 0.8, "couple": 0.5}, {"airline": "ZO", "minDwell": 25}, {"gates": ["41", "42"]}, {"delayOver": 30}, 7000, 500, 25, 3.4, 2, -18, 24, "all_day"),
    ("CMP-21", "ADV-AIR-YU", "Lumen Coast · Family Fare", "pending", "airline", {"family": 0.8, "holiday": 0.8, "beach": 0.7}, {"airline": "YU"}, {"gates": ["40", "41", "42"]}, {}, 6500, 450, 20, 3.2, 1, -5, 26, "all_day"),
    ("CMP-22", "ADV-AIR-XD", "Skylark · Saver Fares", "approved", "airline", {"value": 0.6, "business": 0.5, "domestic": 0.7}, {"airline": "XD"}, {"zones": ["T1-A", "T1-B", "T1-C"]}, {}, 5000, 350, 20, 2.3, 1, -22, 23, "all_day"),
    ("CMP-23", "ADV-01", "Gulf Gold · Fragrance", "paused", "perfume", {"international": 0.9, "luxury": 0.8, "holiday": 0.5}, {"internationalOnly": True, "destinations": ["SMG", "ZHQ", "DXB"], "minDwell": 15}, {"zones": ["T2-F", "T2-DUTY"]}, {"delayOver": 30}, 14000, 850, 20, 4.5, 2, -9, 18, "evening"),
    ("CMP-24", "ADV-03", "Half-Term Heroes · Toy Bundle", "approved", "toys", {"family": 1.0, "holiday": 0.9}, {"minCrowd": 60}, {"zones": ["T2-F", "T1-RETAIL", "T2-FOOD"]}, {"festival": True}, 8500, 550, 15, 3.5, 1, -2, 4, "all_day"),
    ("CMP-25", "ADV-02", "Café Meridian · Morning Runway", "ended", "coffee", {"business": 0.5, "value": 0.5}, {"daypart": [6, 10]}, {"zones": ["T1-FOOD", "T2-FOOD", "T2-D"]}, {}, 2500, 200, 12, 1.4, 0, -40, -2, "morning"),
]


def build_business(
    sim_day: date,
    zones: list[dict],
    screens: list[dict],
    flights: list[dict],
    demo: dict[str, dict],
    rng: random.Random,
) -> dict[str, Any]:
    day_start = datetime.combine(sim_day, time(0, 0), tzinfo=timezone.utc)
    sim_start = datetime.combine(sim_day, time(13, 55), tzinfo=timezone.utc)
    advertisers = [
        {"id": item[0], "name": item[1], "kind": item[2], "color": item[3], "contact": item[4], "created": day_start - timedelta(days=90)}
        for item in ADVERTISERS
    ]
    outlets = []
    for index, (adv, name, zone, category) in enumerate(OUTLET_SPECS):
        outlets.append(
            {
                "id": f"OUT-{index + 1:03d}",
                "advertiser_id": adv,
                "name": name,
                "zone_id": zone,
                "category": category,
                "stock_status": "out_of_stock" if index == 9 else "in_stock",
                "created": day_start - timedelta(days=60),
            }
        )
    creatives = []
    for campaign_id, spec in CREATIVE_SPECS.items():
        name, head_en, head_zh, body_en, body_zh, cta_en, cta_zh, template, colors, category = spec
        creative_id = f"CRE-{campaign_id.split('-')[1]}"
        creatives.append(
            {
                "id": creative_id,
                "advertiser_id": next(spec_row[1] for spec_row in CAMPAIGN_SPECS if spec_row[0] == campaign_id),
                "name": name,
                "headline_en": head_en,
                "headline_zh": head_zh,
                "body_en": body_en,
                "body_zh": body_zh,
                "cta_en": cta_en,
                "cta_zh": cta_zh,
                "template": template,
                "colors": colors,
                "image": "",
                "category": category,
                "status": "pending" if campaign_id in {"CMP-17", "CMP-21"} else "approved",
                "created": day_start - timedelta(days=35),
            }
        )
    campaigns = []
    for spec in CAMPAIGN_SPECS:
        (
            cid, adv, name, status, category, segments, filters, placement, triggers,
            budget, daily, freq, bid, priority, start_offset, end_offset, daypart,
        ) = spec
        creative_id = f"CRE-{cid.split('-')[1]}"
        campaigns.append(
            {
                "id": cid,
                "advertiser_id": adv,
                "creative_id": creative_id,
                "name": name,
                "status": status,
                "start": day_start + timedelta(days=start_offset),
                "end": day_start + timedelta(days=end_offset, hours=23, minutes=59),
                "daypart": _daypart(daypart),
                "budget": float(budget),
                "daily_cap": float(daily),
                "freq_cap_min": int(freq),
                "bid": float(bid),
                "segments": segments,
                "filters": filters,
                "placement": placement,
                "triggers": triggers,
                "spend": 0.0,
                "impressions": 0,
                "scans": 0,
                "redemptions": 0,
                "revenue": 0.0,
                "conversion": 0.0,
                "created": day_start - timedelta(days=30),
                "notes": "POC campaign seeded from commercial plan.",
                "priority": priority,
                "ab_group": "A" if priority % 2 == 0 else "B",
                "category": category,
            }
        )
    daily_stats, segment_stats = _history(sim_day, campaigns, rng)
    promos = _promos(sim_start, flights, demo)
    incidents = _incidents(sim_start)
    packages = _packages(screens)
    marketplace = _marketplace(day_start)
    rules = {
        "globalWeights": {"audience": 0.55, "business": 0.2, "freshness": 0.1, "exploration": 0.05, "bid": 0.1},
        "explorationPct": 5,
        "frequencyCapMin": 20,
        "competitorSeparationMin": 20,
        "delayThresholdMin": 30,
        "segmentModel": "seg-2026.10-v3",
        "pacing": "even",
        "houseCampaignId": "CMP-18",
        "minEvidenceConfidence": 0.6,
    }
    return {
        "advertisers": advertisers,
        "outlets": outlets,
        "creatives": creatives,
        "campaigns": campaigns,
        "daily_stats": daily_stats,
        "segment_stats": segment_stats,
        "promos": promos,
        "incidents": incidents,
        "packages": packages,
        "marketplace": marketplace,
        "rules": rules,
    }


def _daypart(value: str) -> dict:
    return {"preset": value, "startHour": 0, "endHour": 24}


def _history(sim_day: date, campaigns: list[dict], rng: random.Random):
    daily = []
    segments = []
    aov = {"perfume": 74, "toys": 38, "lounge": 42, "coffee": 8, "beach": 46, "sweets": 19, "watches": 310, "books": 22, "wellness": 58, "tech": 96, "forex": 30, "pharmacy": 17, "sports": 62, "fashion": 88, "bakery": 9, "hotel": 140, "cosmetics": 54, "house": 0, "airline": 120}
    for campaign in campaigns:
        cid = campaign["id"]
        rng_c = random.Random(f"{cid}-history")
        if campaign["status"] == "pending":
            continue
        for offset in range(30, -1, -1):
            day = sim_day - timedelta(days=offset)
            day_factor = (1.0 + (0.12 if day.weekday() >= 4 else 0)) * (0.58 if offset == 0 else 1.0)
            impressions = int(campaign["daily_cap"] * rng_c.uniform(24, 44) * day_factor)
            scans = int(impressions * rng_c.uniform(0.012, 0.035))
            redemptions = int(scans * rng_c.uniform(0.28, 0.55))
            revenue = round(redemptions * aov.get(campaign["category"], 30) * rng_c.uniform(0.85, 1.15), 2)
            spend = round(campaign["daily_cap"] * rng_c.uniform(0.55, 0.96) * day_factor, 2)
            daily.append((cid, day.isoformat(), impressions, scans, redemptions, revenue, spend))
        weights = campaign["segments"]
        total = sum(weights.values()) or 1.0
        for segment in ["international", "holiday", "family", "business", "vfr", "student", "luxury", "young"]:
            weight = weights.get(segment, 0.0)
            share = max(0.03, weight / total) if weight else 0.02
            impressions = int(campaign["daily_cap"] * 30 * 24 * share * rng_c.uniform(0.7, 1.2))
            rate = rng_c.uniform(0.012, 0.038) * (1.35 if segment == "family" else 1.0) * (1.2 if segment == "luxury" else 1.0)
            scans = int(impressions * rate)
            redemptions = int(scans * rng_c.uniform(0.25, 0.6))
            revenue = round(redemptions * aov.get(campaign["category"], 30) * rng_c.uniform(0.8, 1.2), 2)
            segments.append((cid, segment, impressions, scans, redemptions, revenue))
    return daily, segments


def _promos(sim_start: datetime, flights: list[dict], demo: dict[str, dict]) -> list[dict]:
    by_key = {
        "perfume": ("CMP-01", "MQI-GOLD15", "15% off fragrance", "15%"),
        "toys": ("CMP-02", "MQI-TOY2X1", "Buy 2 get 1 free", "3 for 2"),
        "lounge": ("CMP-03", "MQI-LOUNGE45", "CloudNine day pass", "€29"),
        "coffee": ("CMP-04", "MQI-GATEBREW", "Coffee + pastry", "€7"),
        "beach": ("CMP-05", "MQI-SALT10", "Beachwear 10% off", "10%"),
        "sweets": ("CMP-06", "MQI-COCOA20", "Tasting box 20% off", "20%"),
        "tech": ("CMP-10", "MQI-ESIM5", "eSIM bundle", "€5 off"),
        "hotel": ("CMP-16", "MQI-STAY15", "Aurora Hotels 15% off", "15%"),
        "airline": ("CMP-19", "MQI-UPGRADE", "Halcyon upgrade", "€149"),
        "airline-lounge": ("CMP-20", "MQI-SKY35", "Solano Sky Lounge", "€35"),
    }
    mapping = [
        ("perfume", demo["dxb"], 500),
        ("toys", demo["beach"], 300),
        ("lounge", demo["gulf"], 200),
        ("coffee", demo["dxb"], 400),
        ("beach", demo["beach"], 250),
        ("sweets", demo["gulf"], 300),
        ("tech", demo["gulf"], 350),
        ("hotel", demo["dxb"], 150),
        ("airline", demo["gulf"], 120),
        ("airline-lounge", demo["dxb"], 160),
    ]
    promos = []
    for index, (key, flight, max_uses) in enumerate(mapping, start=1):
        cid, code, label, value = by_key[key]
        estimated = flight["estimated"] or flight["std"]
        valid_until = estimated - timedelta(minutes=10)
        promos.append(
            {
                "id": f"PRM-{index:03d}",
                "campaign_id": cid,
                "code": code,
                "flight_id": flight["flight_id"],
                "valid_from": sim_start - timedelta(minutes=20),
                "valid_until": valid_until,
                "max_uses": max_uses,
                "uses": random.Random(index).randint(0, 12),
                "parent_code": "",
                "status": "active",
                "label": label,
                "value": value,
            }
        )
    return promos


def _incidents(sim_start: datetime) -> list[dict]:
    return [
        {
            "kind": "screen_offline",
            "severity": "high",
            "owner": "ops@mqi.example",
            "status": "open",
            "title": "Screen SCR-021 offline",
            "message": "No heartbeat for 12 minutes in T2-D. Ad loop paused; failover poster active.",
            "created": sim_start - timedelta(minutes=12),
            "updated": sim_start - timedelta(minutes=12),
            "meta": {"screenId": "SCR-021"},
        },
        {
            "kind": "creative_failure",
            "severity": "medium",
            "owner": "media@mqi.example",
            "status": "investigating",
            "title": "Creative render slow on SCR-053",
            "message": "Playlist build exceeded 900 ms twice. Running on cached creative.",
            "created": sim_start - timedelta(minutes=26),
            "updated": sim_start - timedelta(minutes=4),
            "meta": {"screenId": "SCR-053"},
        },
        {
            "kind": "feed_lag",
            "severity": "low",
            "owner": "platform@mqi.example",
            "status": "resolved",
            "title": "AIDX feed lag 96 s",
            "message": "AIDX consumer reconnected and replayed the missed window.",
            "created": sim_start - timedelta(hours=2),
            "updated": sim_start - timedelta(minutes=80),
            "meta": {"feed": "AIDX"},
        },
        {
            "kind": "budget_pacing",
            "severity": "medium",
            "owner": "media@mqi.example",
            "status": "open",
            "title": "CMP-11 under-delivering",
            "message": "Forex campaign forecast 22% below contracted impressions.",
            "created": sim_start - timedelta(minutes=45),
            "updated": sim_start - timedelta(minutes=45),
            "meta": {"campaignId": "CMP-11"},
        },
    ]


def _packages(screens: list[dict]) -> list[dict]:
    def ids(zone_ids: list[str], limit: int) -> list[str]:
        found = [screen["id"] for screen in screens if screen["zone_id"] in zone_ids]
        return found[:limit]

    return [
        {
            "id": "PKG-01",
            "name": "International Departures Premium",
            "screen_ids": ids(["T2-F", "T2-DUTY"], 24),
            "price": 18500,
            "description": "Duty Free Boulevard + Gates 40–48, peak international dwell.",
            "created": datetime(2026, 10, 1, tzinfo=timezone.utc),
        },
        {
            "id": "PKG-02",
            "name": "Domestic Business Morning",
            "screen_ids": ids(["T1-A", "T1-B", "T1-C"], 20),
            "price": 9200,
            "description": "Gates 1–24, 06:00–10:00 weekday business skew.",
            "created": datetime(2026, 10, 1, tzinfo=timezone.utc),
        },
        {
            "id": "PKG-03",
            "name": "Food & Family Trail",
            "screen_ids": ids(["T1-FOOD", "T2-FOOD", "T2-F"], 18),
            "price": 7400,
            "description": "Both food courts plus family-heavy international gates.",
            "created": datetime(2026, 10, 1, tzinfo=timezone.utc),
        },
    ]


def _marketplace(day_start: datetime) -> list[dict]:
    return [
        {
            "id": "MKT-01",
            "retailer_id": "ADV-01",
            "airline": "ZO",
            "title": "Solano passengers: 10% fragrance",
            "offer": "10% off at Meridian Duty Free for Solano boarding passes, Gate 40–45.",
            "status": "offered",
            "created": day_start - timedelta(days=2),
        },
        {
            "id": "MKT-02",
            "retailer_id": "ADV-02",
            "airline": "XH",
            "title": "Halcyon coffee + pastry",
            "offer": "€5 breakfast bundle for Halcyon passengers before 10:00.",
            "status": "offered",
            "created": day_start - timedelta(days=3),
        },
        {
            "id": "MKT-03",
            "retailer_id": "ADV-03",
            "airline": "YU",
            "title": "Lumen families: toy bundle",
            "offer": "Buy 2 get 1 on travel toys for Lumen Pacific family fares.",
            "status": "accepted",
            "created": day_start - timedelta(days=5),
        },
        {
            "id": "MKT-04",
            "retailer_id": "ADV-04",
            "airline": "XD",
            "title": "Skylark lounge upgrade",
            "offer": "€5 off CloudNine for Skylark flex fares.",
            "status": "offered",
            "created": day_start - timedelta(days=1),
        },
    ]