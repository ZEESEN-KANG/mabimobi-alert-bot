from __future__ import annotations

import asyncio
import datetime as dt
import logging
import discord

from dataclasses            import dataclass
from zoneinfo               import ZoneInfo

from discord.ext            import (
    commands,
    tasks
)
from discord.ui             import (
    Button, 
    View
)
from typing                 import (
    List, 
    Dict, 
    Set, 
    Tuple,
    Optional
)
from module.alert_service   import (
    create_hourly_check_message,
    create_hourly_5min_message,
    create_hourly_3min_message,
)
from module.user_store      import (
    load_subscriptions, 
    save_subscriptions
)

# --------------------------------------
# 상수/전역(키 이름 고정: value=운영채널, debug=디버그채널)
# --------------------------------------
KST                         = ZoneInfo("Asia/Seoul")
SUBSCRIBED_USERS_FILE: str  = "subscribed_users.json"
SUB_TYPES: List[str]        = ["minute_5_before", "minute_3_before", "on_time"]

channel_id_holder: Dict[str, int]   = {"value": 0, "debug": 0}  # value=운영, debug=디버그
time_config_holder: Dict[str, int]  = {"retention_seconds": 600}    # 자동 삭제 지연(초)

# --------------------------------------
# 구독 상태 매니저 (동시성 안전)
# --------------------------------------
class SubscriptionManager:
    """
    구독 상태를 일원화하여 관리하는 매니저.
    - 파일 I/O 동시성 제어(asyncio.Lock)
    - 'all'과 개별 구독 간 배타성 보장
    """
    def __init__(self, file_name: str) -> None:
        self._file_name: str                 = file_name
        self._lock: asyncio.Lock             = asyncio.Lock()
        # 메모리 캐시(set): JSON ↔ set 변환은 user_store가 담당
        self._data: Dict[str, Set[int]]      = {
            "minute_5_before": set(),
            "minute_3_before": set(),
            "on_time":         set(),
            "all":             set(),
        }
        # 초기 로드
        self._data = load_subscriptions(self._file_name)

    async def toggle(self, user_id: int, sub_type: str) -> Tuple[bool, str]:
        """
        구독/해제를 토글한다.
        - sub_type == 'all': 개별 구독 모두 제거 후 all 토글
        - sub_type in SUB_TYPES: all 제거 후 해당 타입만 토글
        Returns: (성공여부, 사용자 메시지)
        """
        async with self._lock:
            try:
                if sub_type == "all":
                    for t in SUB_TYPES:
                        self._data[t].discard(user_id)
                    if user_id in self._data["all"]:
                        self._data["all"].discard(user_id)
                        msg = "🔕 전체 구독 해제? 어, 됐다니까.\n이제 신경 끄고 살아."
                    else:
                        self._data["all"].add(user_id)
                        msg = "✅ 전체 구독? 됐다, 됐어.\n이젠 뭐 또 바라는거 있어?"
                else:
                    # 개별 구독 선택 시 all에서 제외
                    self._data["all"].discard(user_id)
                    if user_id in self._data[sub_type]:
                        self._data[sub_type].discard(user_id)
                        msg = f"🔕 {self._label_from_type(sub_type)} 구독 해제? 어, 됐다니까.\n이제 신경 끄고 살아."
                    else:
                        self._data[sub_type].add(user_id)
                        msg = f"✅ {self._label_from_type(sub_type)} 구독? 됐다, 됐어.\n이젠 뭐 또 바라는거 있어?"

                # 저장 (작지만 안전하게 개별 스레드로)
                ok = await asyncio.to_thread(save_subscriptions, self._file_name, self._data)
                if not ok:
                    return False, "❌ 구독 상태 저장 실패! 인강, 뭐 건드렸냐? 얼른 롼리자 소환해라."
                return True, msg
            except Exception as e:
                logging.exception("toggle() 실패: %s", e)
                return False, "❌ 구독 처리 중 오류! 인간, 뭐 잘못 눌렀냐?"

    def recipients_for(self, sub_type: str) -> List[int]:
        """
        알림 전송 대상 계산:
        - 항상 `all ∪ sub_type`
        """
        # 읽기만 하므로 락 없이 스냅샷 사용(일관성 요구 시 락 추가 가능)
        all_users  = self._data.get("all", set())
        sub_users  = self._data.get(sub_type, set())
        combined   = all_users | sub_users
        return list(combined)

    def _label_from_type(self, sub_type: str) -> str:
        return {
            "minute_5_before": "정각 5분 전",
            "minute_3_before": "정각 3분 전",
            "on_time":         "정각",
            "all":             "전체",
        }.get(sub_type, sub_type)
    
# --------------------------------------
# 메시지 디스패처(큐 + 세마포어 + 재시도)
# --------------------------------------
@dataclass
class MessageJob:
    channel_id: int
    content: str
    delete_after: Optional[int] = None  # 초

class MessageDispatcher:
    """
    큐 기반 메시지 전송기.
    - concurrency 제한(세마포어)
    - 전송 실패 시 지수 백오프 재시도(최대 3회)
    - delete_after 가 설정된 경우 삭제 스케줄
    """
    def __init__(self, bot: commands.Bot, concurrency: int = 2) -> None:
        self.bot                                = bot
        self.queue: asyncio.Queue[MessageJob]   = asyncio.Queue()
        self._sem                               = asyncio.Semaphore(concurrency)
        self._workers: List[asyncio.Task]       = []
        self._stopped                           = asyncio.Event()

    def start(self, worker_count: int = 2) -> None:
        for _ in range(worker_count):
            self._workers.append(asyncio.create_task(self._worker()))

    async def stop(self) -> None:
        self._stopped.set()
        for w in self._workers:
            w.cancel()
        # 남은 잡 처리 대기(optional)
        await asyncio.gather(*self._workers, return_exceptions=True)

    async def enqueue(self, job: MessageJob) -> None:
        await self.queue.put(job)

    async def _worker(self) -> None:
        while not self._stopped.is_set():
            job: MessageJob = await self.queue.get()
            try:
                async with self._sem:
                    await self._send_job(job)
            except Exception as e:
                logging.exception("메시지 전송 작업 실패: %s", e)
            finally:
                self.queue.task_done()

    async def _send_job(self, job: MessageJob) -> None:
        channel = self.bot.get_channel(job.channel_id)
        if channel is None:
            logging.warning("채널(ID=%s)을 찾지 못해 전송 스킵", job.channel_id)
            return

        # 최대 3회 재시도, 1s → 2s → 4s 백오프
        delay = 1.0
        for attempt in range(1, 4):
            try:
                msg = await channel.send(job.content)
                if job.delete_after and job.delete_after > 0:
                    asyncio.create_task(self._delete_later(msg, job.delete_after))
                logging.info("메시지 전공 성공")
                return
            except discord.HTTPException as e:
                logging.warning("HTTPException(%s) 시도 %d/3", e, attempt)
                await asyncio.sleep(delay)
                delay *= 2
            except discord.Forbidden:
                logging.error("메시지 전송 권한 없음(채널 ID=%s)", job.channel_id)
                return
            except Exception as e:
                logging.exception("예상치 못한 전송 오류: %s", e)
                await asyncio.sleep(delay)
                delay *= 2

    @staticmethod
    async def _delete_later(msg: discord.Message, after_seconds: int) -> None:
        try:
            await asyncio.sleep(after_seconds)
            await msg.delete()
        except discord.Forbidden:
            logging.warning("메시지 삭제 권한 없음")
        except discord.HTTPException as e:
            logging.warning("메시지 삭제 실패: %s", e)
        except Exception:
            logging.exception("메시지 삭제 처리 중 예외")

# --------------------------------------
# UI 구성요소
# --------------------------------------
class SubscribeButton(Button):
    """구독/해제 토글 버튼"""
    def __init__(
            self, 
            manager: SubscriptionManager, 
            label: str, 
            custom_id: str,
            style: discord.ButtonStyle = discord.ButtonStyle.primary, 
            emoji: Optional[str] = None
    ) -> None:
        super().__init__(label=label, style=style, custom_id=custom_id, emoji=emoji)
        self.manager = manager

    async def callback(self, interaction: discord.Interaction):
        user_id: int                        = interaction.user.id
        sub_type: str                       = self.custom_id  # "minute_5_before" | "minute_3_before" | "on_time" | "all"
        
        ok, msg = await self.manager.toggle(user_id=user_id, sub_type=sub_type)
        try:
            if ok:
                await interaction.response.send_message(content=msg, ephemeral=True)
            else:
                # 이미 response를 보냈다면 flowup
                if interaction.response.is_done():
                    await interaction.followup.send(content=msg, ephemeral=True)
                else:
                    await interaction.response.send_message(content=msg, ephemeral=True)
            logging.info("구독/해제 interaction response 성공")
        except Exception as e:
            logging.exception("interaction response 실패: %s", e)

class SubscribeView(View):
    """구독 안내 메시지 + 버튼 묶음"""
    def __init__(self, manager: SubscriptionManager) -> None:
        super().__init__(timeout=None)
        # 버튼 생성
        self.add_item(SubscribeButton(manager=manager, label="정각 5분 전", custom_id="minute_5_before", emoji="<emoji_37:1400881330769756243>"))
        self.add_item(SubscribeButton(manager=manager, label="정각 3분 전", custom_id="minute_3_before", emoji="<emoji_37:1400881330769756243>"))
        self.add_item(SubscribeButton(manager=manager, label="정각", custom_id="on_time", emoji="🔔"))
        self.add_item(SubscribeButton(manager=manager, label="전체 구독", custom_id="all", style=discord.ButtonStyle.success, emoji="✅"))
        return

# --------------------------------------
# Bot Factory
# --------------------------------------
def create_bot(command_prefix: str = "#") -> commands.Bot:
    intents = discord.Intents.default()
    intents.message_content = True
    return commands.Bot(command_prefix=command_prefix, intents=intents)

def setup_bot_commands(
    bot: commands.Bot,
    test_role_name: str,
    initial_channel_id: int,
    debug_channel_id: int,
    message_retention_seconds: int
) -> None:
    bot_instance                            = bot
    # 운영/디버그 채널, 삭제 지연 설정
    channel_id_holder["value"]              = initial_channel_id
    channel_id_holder["debug"]              = debug_channel_id
    time_config_holder['retention_seconds'] = message_retention_seconds

    # 매니저/디스패처
    subs_manager    = SubscriptionManager(SUBSCRIBED_USERS_FILE)
    dispatcher      = MessageDispatcher(bot=bot_instance, concurrency=2)
    
    dispatcher_started: bool = False  # 중복 시작 방지용 플래그
    
    # ------------- 공통 유틸 -------------

    def _has_role(ctx: commands.Context, role_name: str) -> bool:
        return any(role.name == role_name for role in getattr(ctx.author, "roles", []))

    async def _send_debug(text: str) -> None:
        debug_ch = bot_instance.get_channel(channel_id_holder["debug"])
        if debug_ch:
            try:
                await debug_ch.send(text)
            except Exception:
                logging.exception("디버그 채널 전송 실패")
    
    # ----- 워치독(루프 지연 감시) -----
    last_monotonic: Optional[float] = None

    @tasks.loop(seconds=1.0, reconnect=True)
    async def event_loop_watchdog() -> None:
        nonlocal last_monotonic
        now = asyncio.get_running_loop().time()
        if last_monotonic is not None:
            drift = now - last_monotonic - 1.0  # 이상적 간격 1초
            if drift > 2.0:
                logging.warning("이벤트 루프 지연 감지: %.3fs", drift)
                # 필요 시 디버그 채널 알림(과도한 알림 방지 위해 주석)
                # await _send_debug(f"⚠️ 이벤트 루프 지연 감지: {drift:.3f}s")
        last_monotonic = now

    # ----- 스케줄러(공식 loop 사용) -----
    last_fired_at: Dict[str, Tuple[int, int]] = {
        "minute_5_before": (-1, -1),
        "minute_3_before": (-1, -1),
        "on_time": (-1, -1),
    }

    def _should_fire(sub_type: str, now_kst: dt.datetime) -> bool:
        """해당 타입이 이 분에 발사되어야 하는지 검사 (중복 발사 방지)"""
        minute_map = {
            "minute_5_before": 55,
            "minute_3_before": 57,
            "on_time": 0,
        }
        target_minute = minute_map[sub_type]
        if now_kst.minute != target_minute:
            return False
        last_h, last_m = last_fired_at[sub_type]
        cur_key = (now_kst.hour, now_kst.minute)
        if (last_h, last_m) == cur_key:
            return False
        last_fired_at[sub_type] = cur_key
        return True
    
    @tasks.loop(minutes=1, reconnect=True)
    async def scheduler_loop() -> None:
        now_kst = dt.datetime.now(tz=KST)

        try:
            # 55분: 5분 전
            if _should_fire("minute_5_before", now_kst):
                recipients = subs_manager.recipients_for("minute_5_before")
                content = create_hourly_5min_message(now_kst, mention_ids=recipients)
                await dispatcher.enqueue(
                    MessageJob(
                        channel_id=channel_id_holder["value"],
                        content=content,
                        delete_after=time_config_holder["retention_seconds"],
                    )
                )

            # 57분: 3분 전
            if _should_fire("minute_3_before", now_kst):
                recipients = subs_manager.recipients_for("minute_3_before")
                content = create_hourly_3min_message(now_kst, mention_ids=recipients)
                await dispatcher.enqueue(
                    MessageJob(
                        channel_id=channel_id_holder["value"],
                        content=content,
                        delete_after=time_config_holder["retention_seconds"],
                    )
                )

            # 00분: 정각 체크
            if _should_fire("on_time", now_kst):
                recipients = subs_manager.recipients_for("on_time")
                content = create_hourly_check_message(now_kst, mention_ids=recipients)
                await dispatcher.enqueue(
                    MessageJob(
                        channel_id=channel_id_holder["value"],
                        content=content,
                        delete_after=time_config_holder["retention_seconds"],
                    )
                )

        except Exception as e:
            logging.exception("스케줄러 처리 중 예외: %s", e)
            await _send_debug(f"❌ 스케줄러 오류: {e}")

    # ----- 이벤트 -----
    @bot_instance.event
    async def on_ready():
        nonlocal dispatcher_started
        logging.info("%s 실행됨", bot_instance.user)
        # 디스패처는 이벤트 루프가 '실행 중'일 때 시작
        if not dispatcher_started:
            dispatcher.start(worker_count=2)
            dispatcher_started = True

        if not scheduler_loop.is_running():
            scheduler_loop.start()
        if not event_loop_watchdog.is_running():
            event_loop_watchdog.start()

    # ------------- 명령어 -------------
    @bot_instance.command(name="test_alert")
    async def test_alert(ctx: commands.Context):
        if not _has_role(ctx, test_role_name):
            try:
                msg = await ctx.send("😐 너 누구심?")
                await asyncio.sleep(1)
                await msg.delete()
            except discord.Forbidden:
                await ctx.send("❌ 권한이 없어 메시지를 삭제할 수 없습니다.")
            except discord.HTTPException as e:
                await ctx.send(f"❌ 메시지 삭제 중 오류가 발생했습니다: {e}")
            except Exception as e:
                await ctx.send("❌ 알 수 없는 오류가 발생했습니다.")
                await _send_debug(f"test_alert 오류: {e}")
            return
        
        await ctx.send("✅ 테스트 권한 확인 완료!")

    @bot_instance.command(name="set_channel")
    async def set_channel(ctx: commands.Context, new_channel_id: int):
        if not _has_role(ctx, test_role_name):
            await ctx.send("😐 너 누구심?")
            return

        if bot_instance.get_channel(new_channel_id) is None:
            await ctx.send(f"채널 ID {new_channel_id}를 찾을 수 없습니다.")
            return

        channel_id_holder["value"] = int(new_channel_id)
        await ctx.send(f"알림 채널 ID가 `{new_channel_id}`(으)로 변경되었습니다.")

    @bot_instance.command(name="set_debug_channel")
    async def set_debug_channel(ctx: commands.Context, new_channel_id: int):
        if not _has_role(ctx, test_role_name):
            await ctx.send("😐 너 누구심?")
            return

        if bot_instance.get_channel(new_channel_id) is None:
            await ctx.send(f"채널 ID {new_channel_id}를 찾을 수 없습니다.")
            return

        channel_id_holder["debug"] = int(new_channel_id)
        await ctx.send(f"디버그 채널 ID가 `{new_channel_id}`(으)로 변경되었습니다.")

    @bot_instance.command(name="set_retention_seconds")
    async def set_retention_seconds(ctx: commands.Context, new_retention_seconds: int):
        if not _has_role(ctx, test_role_name):
            await ctx.send("😐 너 누구심?")
            return

        if new_retention_seconds < 0 or new_retention_seconds > 3600 * 6:
            await ctx.send("❌ 0 ~ 21600(6h) 범위에서 설정하세요.")
            return

        time_config_holder["retention_seconds"] = int(new_retention_seconds)
        await ctx.send(f"알림 메시지 자동 삭제 시간을 `{new_retention_seconds}s`(으)로 변경했습니다.")

    @bot_instance.command(name="알림구독")
    async def send_subscribe(ctx: commands.Context):
        if not _has_role(ctx, test_role_name):
            await ctx.send("😐 너 누구심?")
        elif not ctx.author.id == 292505059806412801:
            await ctx.send("😐 너 누구심?")

        view  = SubscribeView(manager=subs_manager)
        embed = discord.Embed(
            title="결계 & 정각 알리미 📢",
            description=(
                "버튼? 누르든 말든 네 맘대로 해~\n"
                "두 번 누르면 해제? 뭐, 그딴 건 알아서 하라구!\n\n"
                "결계 시간? 알려주긴 할 건데, 못 봤다고 찡찡대진 마.\n"
                "귀찮게 굴지 마라, 알겠어?"
            ),
            color=discord.Color.dark_blue(),
        )
        embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/your_thumbnail.png")
        await ctx.send(embed=embed, view=view)