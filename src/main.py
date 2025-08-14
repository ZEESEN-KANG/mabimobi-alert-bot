import sys
import logging
from module.logger         import setup_logger
from module.utils          import get_app_dir
from module.config_loader  import ConfigLoader
from module.bot_factory    import create_bot, setup_bot_commands

def main() -> None:
    setup_logger()
    app_dir         = get_app_dir()
    config_path     = app_dir / "config" / "Config.json"

    try:
        config                      = ConfigLoader(config_path)
        token                       = config.get("TOKEN")
        channel_id                  = config.get("DEFAULT_CHANNEL_ID")
        test_role_name              = config.get("TEST_ROLE_NAME")
        debug_channel_id            = config.get("DEBUG_CHANNEL_ID")
        message_retention_seconds   = config.get("MESSAGE_RETENTION_SECONDS")
    except Exception as e:
        logging.error(f"설정 파일 로드 실패: {e}")
        sys.exit(1)

    bot = create_bot()
    setup_bot_commands(bot, test_role_name, channel_id, debug_channel_id, message_retention_seconds)
    bot.run(token)

if __name__ == "__main__":
    main()