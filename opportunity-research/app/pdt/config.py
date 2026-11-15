"""运行路径与常量。数据目录可用环境变量 PDT_DATA 指定（测试用临时目录）。"""
import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent.parent  # opportunity-research/


def data_dir() -> Path:
    d = Path(os.environ.get("PDT_DATA", APP_DIR.parent / "data"))
    d.mkdir(parents=True, exist_ok=True)
    return d


CATEGORY = "浴室柜"
CHANNELS = ["amazon", "homedepot", "lowes", "wayfair"]
CHANNEL_NAMES = {"amazon": "Amazon", "homedepot": "Home Depot", "lowes": "Lowe's", "wayfair": "Wayfair"}
ROLES = {"operator": "操作者", "approver": "审批者", "readonly": "只读"}
# 按量计费服务（费用闸门）
SERVICES = {"sellersprite": "卖家精灵", "brightdata": "Bright Data", "apify": "Apify", "llm": "大模型"}
# 密钥槽位（大模型按提供方分别存）
SECRET_SLOTS = {"sellersprite": "卖家精灵", "brightdata": "Bright Data", "apify": "Apify",
                "llm_claude": "大模型 · Claude", "llm_openai": "大模型 · OpenAI 兼容"}
SESSION_DAYS = 7
