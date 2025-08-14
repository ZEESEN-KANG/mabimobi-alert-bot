import datetime
from typing import List

def create_hourly_5min_message(timestamp: datetime.datetime, mention_ids: List[int]) -> str:
    next_hour = (timestamp.hour + 1) % 24
    mentions = " ".join(f"<@{user_id}>" for user_id in mention_ids)
    return (
        f"⏰인간, 허접~ 결계도 까먹음. 어쩔? 결계는 가야됨 인정? 🗡️\n"
        f"**불길한 소환의 결계 5분 전 알림!**\n"
        f"{mentions}\n"
    )

def create_hourly_3min_message(timestamp: datetime.datetime, mention_ids: List[int]) -> str:
    next_hour = (timestamp.hour + 1) % 24
    mentions = " ".join(f"<@{user_id}>" for user_id in mention_ids)
    return (
        f"⏰인간, 허접~ 결계도 까먹음. 어쩔? 결계는 가야됨 인정? 🗡️\n"
        f"**불길한 소환의 결계 3분 전 알림!**\n"
        f"> 시간: {next_hour}시 정각 발생 (약 2분 내 보스 소환)\n"
        f"{mentions}\n"
    )

def create_hourly_check_message(timestamp: datetime.datetime, mention_ids: List[int]) -> str:
    mentions = " ".join(f"<@{user_id}>" for user_id in mention_ids)
    return (
        f"🤪 허접 인간, 안가고 뭐하심? 🗡️\n"
        f"{mentions}\n"
    )