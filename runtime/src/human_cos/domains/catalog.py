"""S5-CDE3 declarative Domain catalog from the frozen V0.1 baseline."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DomainDescriptor:
    """A baseline Domain identifier and responsibility, not a qualification claim."""

    module_id: str
    responsibility: str


BASELINE_DOMAIN_CATALOG: tuple[DomainDescriptor, ...] = (
    DomainDescriptor("finance_market", "杠杆、流动性、市场微观结构、交易对手、强平与价格反馈"),
    DomainDescriptor("finance_macro", "财政、货币、资本流动、主权与宏观金融"),
    DomainDescriptor(
        "public_health_epidemiology",
        "传染病传播、公共卫生干预、检测/报告/行为反馈",
    ),
    DomainDescriptor("strategic_security", "大国冲突、升级、威慑、误判与战略稳定的跨域统合"),
    DomainDescriptor("military_strategy", "军事战略、部署、作战逻辑、指挥与升级链"),
    DomainDescriptor("nuclear_strategy", "核威慑、核使用条件、核指挥控制、升级控制"),
    DomainDescriptor("autonomous_weapons", "自主系统、断链自主、人机控制、集群与机器速度闭环"),
    DomainDescriptor("geopolitics", "国家行为、联盟、博弈、制裁与战略互动"),
    DomainDescriptor("law_governance", "法域、授权、责任、制度和程序约束"),
    DomainDescriptor("behavior_society", "可观察群体行为、预期、信任、参与、风险意愿变化"),
    DomainDescriptor("ai_technology", "AI 能力、技术边界、扩散、依赖与失效机制"),
    DomainDescriptor("biosecurity", "生物风险、能力扩散、公共安全与治理"),
    DomainDescriptor("infrastructure", "能源、通信、物流、关键基础设施级联"),
    DomainDescriptor("systems_risk", "跨主体、跨系统反馈、耦合、临界点与不可逆性"),
)

_DOMAIN_BY_ID = {item.module_id: item for item in BASELINE_DOMAIN_CATALOG}


def get_domain_descriptor(module_id: str) -> DomainDescriptor:
    """Return a baseline descriptor without inferring that any worker is qualified."""
    try:
        return _DOMAIN_BY_ID[module_id]
    except KeyError as exc:
        raise KeyError(f"unknown frozen-baseline Domain module_id: {module_id}") from exc
