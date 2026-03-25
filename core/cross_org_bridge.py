"""크로스 조직 브릿지 — 조직 간 메시지 라우팅."""
from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from core.message_envelope import MessageEnvelope
from core.message_schema import OrgMessage
from core.org_registry import Organization, OrgRegistry
from core.telegram_formatting import markdown_to_html


@dataclass
class CrossOrgMessage:
    """조직 간 전달되는 확장 메시지."""

    from_org: str
    to_org: str
    inner: OrgMessage  # 실제 전달할 OrgMessage

    def to_dict(self) -> dict:
        return {
            "from_org": self.from_org,
            "to_org": self.to_org,
            "inner": self.inner.model_dump(),
        }


class CrossOrgBridge:
    """조직 간 메시지 라우터.

    - OrgMessage에 from_org / to_org 컨텍스트를 붙여 전달
    - 대상 조직의 PM봇 텔레그램 그룹으로 라우팅
    - 유저(상록)는 어느 조직 PM과도 직접 대화 가능
    """

    def __init__(self, registry: OrgRegistry) -> None:
        self.registry = registry
        # org_name → bot application (런타임 등록 필요)
        self._apps: dict[str, object] = {}

    def register_app(self, org_name: str, app: object) -> None:
        """조직 PM봇의 Telegram Application을 등록."""
        self._apps[org_name] = app
        logger.info(f"CrossOrgBridge: {org_name} 앱 등록")

    async def route(self, msg: OrgMessage, from_org: str) -> CrossOrgMessage | None:
        """OrgMessage를 적절한 대상 조직으로 라우팅.

        Returns:
            CrossOrgMessage if cross-org routing needed, None if same-org.
        """
        to_field = msg.to
        if isinstance(to_field, list):
            targets = to_field
        else:
            targets = [to_field]

        for target in targets:
            if target == "ALL":
                continue
            target_org = self.registry.get_org_for_worker(target)
            if target_org is None:
                continue
            if target_org.name == from_org:
                # 동일 조직 — 일반 라우팅
                continue

            cross_msg = CrossOrgMessage(
                from_org=from_org,
                to_org=target_org.name,
                inner=msg,
            )
            logger.info(
                f"크로스 조직 메시지: {from_org} → {target_org.name} "
                f"({msg.msg_type}/{msg.task_id})"
            )
            await self._deliver(cross_msg, target_org)
            return cross_msg

        return None

    async def _deliver(self, cross_msg: CrossOrgMessage, target_org: Organization) -> None:
        """대상 조직 PM봇 텔레그램 그룹으로 메시지 전달."""
        app = self._apps.get(target_org.name)
        if app is None:
            logger.warning(f"대상 조직 앱 미등록: {target_org.name}")
            return

        if target_org.group_chat_id is None:
            logger.warning(f"대상 조직 group_chat_id 없음: {target_org.name}")
            return

        # OrgMessage 텍스트에 크로스 조직 헤더 추가 후 envelope으로 정규화
        header = f"[{cross_msg.from_org} → {cross_msg.to_org}]\n"
        raw_text = header + cross_msg.inner.to_telegram_text()
        env = MessageEnvelope.wrap(
            content=raw_text,
            sender_bot=cross_msg.from_org,
            intent=cross_msg.inner.msg_type.value if cross_msg.inner.msg_type else "CROSS_ORG",
            task_id=cross_msg.inner.task_id,
        )
        telegram_text = env.to_display()

        try:
            await app.bot.send_message(  # type: ignore[attr-defined]
                chat_id=target_org.group_chat_id,
                text=markdown_to_html(telegram_text),
                parse_mode="HTML",
            )
            logger.info(f"크로스 조직 메시지 전달 완료 → {target_org.name}")
        except Exception as e:
            logger.error(f"크로스 조직 메시지 전달 실패: {e}")

    def list_routes(self) -> list[dict]:
        """현재 등록된 조직 간 라우팅 경로 반환."""
        orgs = self.registry.list_orgs()
        routes = []
        for org in orgs:
            for worker in org.get("workers", []):
                routes.append({
                    "org": org["name"],
                    "worker": worker,
                    "app_registered": org["name"] in self._apps,
                })
        return routes
