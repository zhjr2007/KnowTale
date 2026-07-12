import random
from typing import Any


class RoleDispatcher:
    """角色发言调度器 - 管理AI角色发言时机和触发逻辑"""

    @staticmethod
    def should_speak(
        role_config: dict[str, Any],
        message_count_since_last: int,
    ) -> bool:
        """根据角色配置判断是否该发言"""
        activity_level = role_config.get("activity_level", 0.5)
        min_interval = role_config.get("min_interval", 3)

        if message_count_since_last < min_interval:
            return False

        if activity_level >= 1.0:
            return True
        if activity_level <= 0.0:
            return False

        base_prob = activity_level
        interval_bonus = min(
            (message_count_since_last - min_interval) * 0.1, 0.5
        )
        final_prob = min(base_prob + interval_bonus, 1.0)
        return random.random() < final_prob

    @staticmethod
    def select_triggered_role(
        message_text: str,
        roles_config: dict[str, dict[str, Any]],
    ) -> str | None:
        """根据消息内容匹配关键词，找到应被触发的角色"""
        if not message_text:
            return None

        matches: list[tuple[str, int]] = []
        for role_type, config in roles_config.items():
            mode = config.get("trigger_mode", "round_robin")
            if mode not in ("keyword", "mixed"):
                continue

            keywords = config.get("keywords", [])
            if not keywords:
                continue

            match_count = sum(
                1 for kw in keywords if kw in message_text
            )
            if match_count > 0:
                matches.append((role_type, match_count))

        if not matches:
            return None

        matches.sort(key=lambda x: x[1], reverse=True)
        return matches[0][0]

    @staticmethod
    def round_robin_next(
        last_speaker_index: int,
        total_roles: int,
    ) -> int:
        """轮序选择下一个发言角色"""
        if total_roles <= 0:
            return -1
        return (last_speaker_index + 1) % total_roles
