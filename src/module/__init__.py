"""
마비노기 모바일 결계 알림 봇 패키지 퍼사드(facade).

- 이 파일은 디렉터리를 '패키지'로 인식시키고, 외부에서 사용할 공개 API를 정리합니다.
- 무거운 작업(스케줄 시작, 네트워크/파일 IO 등)은 절대 수행하지 않습니다.  # 사이드이펙트 금지
- 각 모듈의 책임은 아래 표와 동일하며, 여기서는 경량 re-export 만 제공합니다.

공개 API(요약)
- main     : (엔트리포인트는 별도 파일 main.py)
- config   : ConfigLoader
- bot      : create_bot, setup_bot_commands, MessageDispatcher, SubscriptionManager
- store    : load_subscriptions, save_subscriptions
- alerts   : create_hourly_check_message, create_hourly_5min_message, create_hourly_3min_message
- utils    : get_app_dir
- logging  : setup_logger

예시 사용:
    from module import (
        ConfigLoader, create_bot, setup_bot_commands,
        MessageDispatcher, SubscriptionManager,
        load_subscriptions, save_subscriptions,
        create_hourly_check_message, create_hourly_5min_message, create_hourly_3min_message,
        get_app_dir, setup_logger,
    )
"""

from __future__ import annotations

# 표의 역할에 맞춘 경량 re-export (정적 분석/자동완성 품질 향상)
from .config_loader   import ConfigLoader
from .bot_factory     import (
    create_bot,
    setup_bot_commands,
    MessageDispatcher,     # 메시지 큐/재시도/자동삭제 디스패처
    SubscriptionManager,   # 구독 토글/저장 관리자
)
from .user_store      import load_subscriptions, save_subscriptions
from .alert_service   import (
    create_hourly_check_message,
    create_hourly_5min_message,
    create_hourly_3min_message,
)
from .utils           import get_app_dir
from .logger          import setup_logger

# 외부에 노출할 심볼만 명시
__all__: list[str] = [
    "ConfigLoader",
    "create_bot", "setup_bot_commands",
    "MessageDispatcher", "SubscriptionManager",
    "load_subscriptions", "save_subscriptions",
    "create_hourly_check_message", "create_hourly_5min_message", "create_hourly_3min_message",
    "get_app_dir", "setup_logger",
]

# 패키지 버전 (필요 시 CI에서 자동 주입 가능)
__version__: str = "0.1.0"
