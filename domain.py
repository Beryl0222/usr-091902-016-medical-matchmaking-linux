"""闽港医疗科创协作的领域规则模块。

把需求问题、成果能力、知识产权边界、临床资源、资金条件和地域转化责任
拆开建模，并落实协作规则：

- 保密协议生效前，机构只能看到脱敏摘要；
- 匹配分数只用于建议接洽，不会自动签约；
- 进入尽调会锁定材料版本并登记双方利益冲突；
- 排他期由双方有权代表签署，到期自动失效；
- 合作项目依次经过技术攻关、伦理审查、验证、转化、拨款节点，
  失败或延期按约定解锁权利并计算退款；
- 未入选方不再看到秘密材料；
- 主管人员可随时调取推荐证据、当前权利占用、跨组织待办和资金对应成果。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum


# ---------- 角色与状态 ----------


class Role(str, Enum):
    """参与角色，与 fixtures/domain.json 保持一致。"""

    DEMAND = "需求机构"
    TEAM = "成果团队"
    CLINICAL = "临床合作方"
    FUNDER = "资金方"
    AUTHORITY = "主管部门"


class CoopStatus(str, Enum):
    """合作单状态，取 fixtures/domain.json 的参考状态。"""

    CONTACT = "保密接洽"
    DUE_DILIGENCE = "尽调中"
    PERFORMING = "履约中"
    UNLOCKED = "已解锁"


# 需求单状态，同样取自参考状态。
REQ_OPEN = "公开征集"
REQ_PERFORMING = "履约中"
REQ_UNLOCKED = "已解锁"


class Node(str, Enum):
    """履约里程碑节点，顺序固定。"""

    RESEARCH = "技术攻关"
    ETHICS = "伦理审查"
    VALIDATION = "验证"
    TRANSFORM = "转化"
    FUNDING = "拨款"


NODE_ORDER = [Node.RESEARCH, Node.ETHICS, Node.VALIDATION, Node.TRANSFORM, Node.FUNDING]


class NodeState(str, Enum):
    PENDING = "待开始"
    ACTIVE = "进行中"
    PASSED = "已通过"
    FAILED = "未通过"
    DELAYED = "已延期"


# 拨款状态。
TR_PENDING = "待拨付"
TR_PAID = "已拨付"
TR_CONFIRMED = "已确认"
TR_REFUNDING = "待退款"
TR_REFUNDED = "已退款"
TR_CANCELLED = "已取消"


# ---------- 实体 ----------


@dataclass
class Organization:
    org_id: str
    name: str
    roles: set
    authorized_reps: set  # 有权代表姓名


@dataclass
class Requirement:
    """需求问题：脱敏摘要对外可见，秘密细节受保密协议保护。"""

    req_id: str
    owner_org: str
    title: str
    summary: str  # 脱敏摘要
    secret_detail: str  # 未脱敏内容
    needs: set  # 能力标签
    clinical_needs: set = field(default_factory=set)
    status: str = REQ_OPEN


@dataclass
class IPBoundary:
    """知识产权边界：排他权按边界授予，避免同一成果重复承诺。"""

    boundary_id: str
    scope: str
    owner_org: str


@dataclass
class Achievement:
    """成果能力。"""

    ach_id: str
    team_org: str
    title: str
    summary: str
    secret_detail: str
    capabilities: set
    ip_boundaries: list = field(default_factory=list)


@dataclass
class ClinicalResource:
    """临床资源。"""

    res_id: str
    org_id: str
    capabilities: set
    note: str = ""


@dataclass
class FundingTerm:
    """资金条件。"""

    term_id: str
    funder_org: str
    total_amount: int
    conditions: str = ""


@dataclass
class RegionDuty:
    """地域转化责任。"""

    region: str  # 福建 / 香港
    duty: str
    responsible_org: str


@dataclass
class MaterialVersion:
    """需求材料版本：尽调时锁定，之后发布新版不影响已锁定版本。"""

    version_id: str
    req_id: str
    digest: str
    published_at: datetime


@dataclass
class NDA:
    nda_id: str
    coop_id: str
    req_id: str
    demand_org: str
    team_org: str
    effective_at: datetime

    def is_effective(self, now):
        return now >= self.effective_at


@dataclass
class Recommendation:
    """匹配推荐：仅建议接洽，不构成签约。"""

    rec_id: str
    req_id: str
    ach_id: str
    score: int
    evidence: dict
    created_at: datetime
    advisory_only: bool = True


@dataclass
class Milestone:
    node: Node
    state: NodeState
    deadline: datetime | None = None
    passed_at: datetime | None = None


@dataclass
class Tranche:
    """一笔拨款，关联资金条件与里程碑节点。"""

    tranche_id: str
    term_id: str
    funder_org: str
    node: Node
    amount: int
    status: str = TR_PENDING
    refund_due: int = 0


@dataclass
class ExclusivityGrant:
    """排他权：双方有权代表签署，到期自动失效。"""

    grant_id: str
    coop_id: str
    ach_id: str
    boundary_id: str
    holder_org: str
    signed_by: tuple  # (需求方代表, 成果方代表)
    starts_at: datetime
    expires_at: datetime
    released: bool = False
    release_reason: str | None = None

    def is_active(self, now):
        return not self.released and self.starts_at <= now < self.expires_at


@dataclass
class Cooperation:
    """合作单：一个需求与一个成果的接洽、尽调、履约全过程。"""

    coop_id: str
    req_id: str
    ach_id: str
    demand_org: str
    team_org: str
    recommendation_id: str
    status: CoopStatus = CoopStatus.CONTACT
    nda_id: str | None = None
    locked_version_id: str | None = None
    coi: dict = field(default_factory=dict)  # 组织 -> 申报的利益冲突（空列表表示无）
    milestones: list = field(default_factory=list)
    tranches: list = field(default_factory=list)
    refund_percent: int = 0
    delay_grace_days: int = 0
    region_duties: list = field(default_factory=list)
    close_reason: str | None = None
    funding_gap: bool = False


@dataclass
class AgreementTerms:
    """签约约定：失败或延期时的解锁与退款规则。"""

    refund_percent: int  # 未确认拨款的退款比例（0-100）
    delay_grace_days: int  # 节点宽限天数，超时视为延期
    deadlines: dict = field(default_factory=dict)  # Node -> 截止时间
    funding_plan: list = field(default_factory=list)  # (资金条件ID, 节点, 金额)
    region_duties: list = field(default_factory=list)


class Store:
    """内存存储：各领域对象分表管理。"""

    def __init__(self):
        self.orgs = {}
        self.requirements = {}
        self.achievements = {}
        self.clinical = {}
        self.terms = {}
        self.materials = {}
        self.ndas = {}
        self.recommendations = {}
        self.cooperations = {}
        self.grants = {}


# ---------- 基础工具 ----------


def _now(now=None):
    return now if now is not None else datetime.now(timezone.utc)


def _get(table, key, label):
    try:
        return table[key]
    except KeyError:
        raise ValueError(f"{label}不存在：{key}") from None


def _require_role(store, org_id, role):
    org = _get(store.orgs, org_id, "机构")
    if role not in org.roles:
        raise ValueError(f"机构{org_id}不具备角色：{role.value}")
    return org


def _require_rep(store, org_id, rep):
    org = _get(store.orgs, org_id, "机构")
    if rep not in org.authorized_reps:
        raise ValueError(f"{rep}不是机构{org_id}的有权代表")


# ---------- 登记 ----------


def register_org(store, org):
    store.orgs[org.org_id] = org
    return org


def publish_requirement(store, req):
    """发布需求：必须先脱敏，摘要不得夹带秘密细节。"""

    _require_role(store, req.owner_org, Role.DEMAND)
    if not req.summary.strip():
        raise ValueError("脱敏摘要不能为空")
    if req.secret_detail and req.secret_detail in req.summary:
        raise ValueError("脱敏摘要不得包含未脱敏内容")
    store.requirements[req.req_id] = req
    return req


def register_achievement(store, ach):
    _require_role(store, ach.team_org, Role.TEAM)
    store.achievements[ach.ach_id] = ach
    return ach


def register_clinical(store, res):
    _require_role(store, res.org_id, Role.CLINICAL)
    store.clinical[res.res_id] = res
    return res


def register_funding_term(store, term):
    _require_role(store, term.funder_org, Role.FUNDER)
    store.terms[term.term_id] = term
    return term


def publish_material_version(store, version_id, req_id, digest, now=None):
    _get(store.requirements, req_id, "需求")
    version = MaterialVersion(version_id, req_id, digest, _now(now))
    store.materials[version_id] = version
    return version


# ---------- 保密可见性 ----------


def _party_with_nda(store, viewer_org, coops, now):
    """访问者是否为合作方且保密协议已生效、合作尚未解锁。"""

    for coop in coops:
        if coop.status == CoopStatus.UNLOCKED:
            continue
        if viewer_org not in (coop.demand_org, coop.team_org):
            continue
        nda = store.ndas.get(coop.nda_id or "")
        if nda and nda.is_effective(now):
            return True
    return False


def _is_authority(store, org_id):
    org = store.orgs.get(org_id)
    return bool(org and Role.AUTHORITY in org.roles)


def requirement_view(store, req_id, viewer_org, now=None):
    """需求视图：保密协议生效前或未入选后，只能看到脱敏摘要。"""

    now = _now(now)
    req = _get(store.requirements, req_id, "需求")
    coops = [c for c in store.cooperations.values() if c.req_id == req_id]
    full = (
        viewer_org == req.owner_org
        or _is_authority(store, viewer_org)
        or _party_with_nda(store, viewer_org, coops, now)
    )
    if full:
        return {
            "需求": req.req_id,
            "标题": req.title,
            "脱敏摘要": req.summary,
            "秘密细节": req.secret_detail,
            "状态": req.status,
            "可见级别": "全文",
        }
    return {
        "需求": req.req_id,
        "标题": req.title,
        "脱敏摘要": req.summary,
        "状态": req.status,
        "可见级别": "脱敏摘要",
        "保密提示": "保密协议生效前仅可见脱敏摘要",
    }


def achievement_view(store, ach_id, viewer_org, now=None):
    """成果视图：与需求视图对称的保密规则。"""

    now = _now(now)
    ach = _get(store.achievements, ach_id, "成果")
    coops = [c for c in store.cooperations.values() if c.ach_id == ach_id]
    full = (
        viewer_org == ach.team_org
        or _is_authority(store, viewer_org)
        or _party_with_nda(store, viewer_org, coops, now)
    )
    if full:
        return {
            "成果": ach.ach_id,
            "标题": ach.title,
            "脱敏摘要": ach.summary,
            "秘密细节": ach.secret_detail,
            "可见级别": "全文",
        }
    return {
        "成果": ach.ach_id,
        "标题": ach.title,
        "脱敏摘要": ach.summary,
        "可见级别": "脱敏摘要",
        "保密提示": "保密协议生效前仅可见脱敏摘要",
    }


# ---------- 匹配与接洽 ----------


def recommend(store, req_id, now=None):
    """计算匹配分数并留存推荐证据；只建议接洽，不自动签约。"""

    now = _now(now)
    req = _get(store.requirements, req_id, "需求")
    clinical_support = {}
    for res in store.clinical.values():
        if req.clinical_needs <= res.capabilities:
            clinical_support.setdefault(res.org_id, True)
    funding = [
        {"资金方": t.funder_org, "额度": t.total_amount, "条件": t.conditions}
        for t in sorted(store.terms.values(), key=lambda t: t.term_id)
    ]
    recs = []
    for ach in sorted(store.achievements.values(), key=lambda a: a.ach_id):
        matched = req.needs & ach.capabilities
        score = round(100 * len(matched) / len(req.needs)) if req.needs else 0
        occupied = any(
            g.ach_id == ach.ach_id and g.is_active(now) for g in store.grants.values()
        )
        rec = Recommendation(
            rec_id=f"rec-{req_id}-{ach.ach_id}",
            req_id=req_id,
            ach_id=ach.ach_id,
            score=score,
            evidence={
                "命中能力": sorted(matched),
                "未覆盖需求": sorted(req.needs - ach.capabilities),
                "临床支持": sorted(clinical_support),
                "可选资金条件": funding,
                "权利占用提示": "该成果存在生效中的排他权" if occupied else None,
            },
            created_at=now,
        )
        store.recommendations[rec.rec_id] = rec
        recs.append(rec)
    recs.sort(key=lambda r: (-r.score, r.ach_id))
    return recs


def initiate_cooperation(store, coop_id, rec_id, now=None):
    """基于推荐显式发起接洽；匹配分数本身不会创建合作单。"""

    rec = _get(store.recommendations, rec_id, "推荐")
    req = _get(store.requirements, rec.req_id, "需求")
    ach = _get(store.achievements, rec.ach_id, "成果")
    if req.status != REQ_OPEN:
        raise ValueError(f"需求当前状态为{req.status}，不能发起新接洽")
    for other in store.cooperations.values():
        if (
            other.req_id == rec.req_id
            and other.ach_id == rec.ach_id
            and other.status != CoopStatus.UNLOCKED
        ):
            raise ValueError("同一需求与成果已存在进行中的合作单")
    coop = Cooperation(
        coop_id=coop_id,
        req_id=rec.req_id,
        ach_id=rec.ach_id,
        demand_org=req.owner_org,
        team_org=ach.team_org,
        recommendation_id=rec.rec_id,
    )
    store.cooperations[coop_id] = coop
    return coop


def sign_nda(store, coop_id, nda_id, effective_at, now=None):
    coop = _get(store.cooperations, coop_id, "合作单")
    if coop.status != CoopStatus.CONTACT:
        raise ValueError("仅保密接洽阶段可签署保密协议")
    nda = NDA(nda_id, coop_id, coop.req_id, coop.demand_org, coop.team_org, effective_at)
    store.ndas[nda_id] = nda
    coop.nda_id = nda_id
    return nda


# ---------- 尽调 ----------


def enter_due_diligence(store, coop_id, version_id, coi, now=None):
    """进入尽调：保密协议须已生效，锁定材料版本并登记双方利益冲突。"""

    now = _now(now)
    coop = _get(store.cooperations, coop_id, "合作单")
    if coop.status != CoopStatus.CONTACT:
        raise ValueError("仅保密接洽阶段可进入尽调")
    nda = store.ndas.get(coop.nda_id or "")
    if not nda or not nda.is_effective(now):
        raise ValueError("保密协议未生效，不得进入尽调")
    version = _get(store.materials, version_id, "材料版本")
    if version.req_id != coop.req_id:
        raise ValueError("材料版本不属于该需求")
    missing = {coop.demand_org, coop.team_org} - set(coi)
    if missing:
        raise ValueError(f"以下机构尚未登记利益冲突：{sorted(missing)}")
    coop.status = CoopStatus.DUE_DILIGENCE
    coop.locked_version_id = version_id
    coop.coi = dict(coi)
    return coop


# ---------- 排他权 ----------


def grant_exclusivity(
    store, grant_id, coop_id, boundary_id, rep_demand, rep_team, starts_at, expires_at, now=None
):
    """授予排他权：双方有权代表签署，同一知识产权边界不得重复承诺。"""

    now = _now(now)
    coop = _get(store.cooperations, coop_id, "合作单")
    if coop.status not in (CoopStatus.DUE_DILIGENCE, CoopStatus.PERFORMING):
        raise ValueError("仅尽调中或履约中可授予排他权")
    _require_rep(store, coop.demand_org, rep_demand)
    _require_rep(store, coop.team_org, rep_team)
    ach = _get(store.achievements, coop.ach_id, "成果")
    if boundary_id not in {b.boundary_id for b in ach.ip_boundaries}:
        raise ValueError(f"知识产权边界{boundary_id}不属于该成果")
    if expires_at <= starts_at:
        raise ValueError("排他期截止必须晚于起始")
    for other in store.grants.values():
        if other.boundary_id != boundary_id or other.released:
            continue
        if other.starts_at < expires_at and starts_at < other.expires_at:
            raise ValueError("同一知识产权边界已存在排他承诺，不得重复授予")
    grant = ExclusivityGrant(
        grant_id=grant_id,
        coop_id=coop_id,
        ach_id=coop.ach_id,
        boundary_id=boundary_id,
        holder_org=coop.demand_org,
        signed_by=(rep_demand, rep_team),
        starts_at=starts_at,
        expires_at=expires_at,
    )
    store.grants[grant_id] = grant
    return grant


def expire_grants(store, now=None):
    """排他期到期自动失效，返回本次失效的排他权。"""

    now = _now(now)
    expired = []
    for grant in store.grants.values():
        if not grant.released and grant.expires_at <= now:
            grant.released = True
            grant.release_reason = "到期自动失效"
            expired.append(grant)
    return expired


# ---------- 签约与履约 ----------


def sign_agreement(store, coop_id, rep_demand, rep_team, terms, now=None):
    """签约进入履约：生成里程碑与拨款计划，其余接洽方按未入选解锁。"""

    now = _now(now)
    coop = _get(store.cooperations, coop_id, "合作单")
    if coop.status != CoopStatus.DUE_DILIGENCE:
        raise ValueError("仅尽调中可签约")
    _require_rep(store, coop.demand_org, rep_demand)
    _require_rep(store, coop.team_org, rep_team)
    if not 0 <= terms.refund_percent <= 100:
        raise ValueError("退款比例须在0到100之间")
    spent = {}
    tranches = []
    for i, (term_id, node, amount) in enumerate(terms.funding_plan, start=1):
        term = _get(store.terms, term_id, "资金条件")
        _require_role(store, term.funder_org, Role.FUNDER)
        if not isinstance(node, Node):
            raise ValueError(f"拨款节点无效：{node}")
        if amount <= 0:
            raise ValueError("拨款金额必须为正")
        spent[term_id] = spent.get(term_id, 0) + amount
        if spent[term_id] > term.total_amount:
            raise ValueError(f"拨款计划超出资金条件{term_id}的额度")
        tranches.append(Tranche(f"{coop_id}-tr-{i}", term_id, term.funder_org, node, amount))
    coop.milestones = [
        Milestone(
            node=node,
            state=NodeState.ACTIVE if i == 0 else NodeState.PENDING,
            deadline=terms.deadlines.get(node),
        )
        for i, node in enumerate(NODE_ORDER)
    ]
    coop.tranches = tranches
    coop.refund_percent = terms.refund_percent
    coop.delay_grace_days = terms.delay_grace_days
    coop.region_duties = list(terms.region_duties)
    coop.status = CoopStatus.PERFORMING
    req = _get(store.requirements, coop.req_id, "需求")
    req.status = REQ_PERFORMING
    for other in store.cooperations.values():
        if other.coop_id == coop_id or other.req_id != coop.req_id:
            continue
        if other.status in (CoopStatus.CONTACT, CoopStatus.DUE_DILIGENCE):
            other.status = CoopStatus.UNLOCKED
            other.close_reason = "未入选"
            _release_grants(store, other.coop_id, "未入选")
    return coop


def _release_grants(store, coop_id, reason):
    for grant in store.grants.values():
        if grant.coop_id == coop_id and not grant.released:
            grant.released = True
            grant.release_reason = reason


def _current_milestone(coop):
    for milestone in coop.milestones:
        if milestone.state == NodeState.ACTIVE:
            return milestone
    return None


def advance_milestone(store, coop_id, now=None):
    """通过当前节点并激活下一节点；节点关联的已拨付资金转为已确认。"""

    now = _now(now)
    coop = _get(store.cooperations, coop_id, "合作单")
    if coop.status != CoopStatus.PERFORMING:
        raise ValueError("仅履约中可推进节点")
    current = _current_milestone(coop)
    if current is None:
        raise ValueError("没有进行中的节点")
    current.state = NodeState.PASSED
    current.passed_at = now
    for tranche in coop.tranches:
        if tranche.node == current.node and tranche.status == TR_PAID:
            tranche.status = TR_CONFIRMED
    if current.node == NODE_ORDER[-1]:
        coop.status = CoopStatus.UNLOCKED
        coop.close_reason = "履约完成"
        _get(store.requirements, coop.req_id, "需求").status = REQ_UNLOCKED
        return coop
    nxt = coop.milestones[NODE_ORDER.index(current.node) + 1]
    nxt.state = NodeState.ACTIVE
    return coop


def _settle_failure(store, coop, close_reason):
    """失败或延期：按约定解锁权利，未确认拨款转入待退款，未拨付取消。"""

    coop.status = CoopStatus.UNLOCKED
    coop.close_reason = close_reason
    _release_grants(store, coop.coop_id, close_reason)
    for tranche in coop.tranches:
        if tranche.status == TR_PAID:
            tranche.status = TR_REFUNDING
            tranche.refund_due = tranche.amount * coop.refund_percent // 100
        elif tranche.status == TR_PENDING:
            tranche.status = TR_CANCELLED
    _get(store.requirements, coop.req_id, "需求").status = REQ_UNLOCKED


def fail_milestone(store, coop_id, reason="节点失败", now=None):
    """当前节点未通过：按约定解锁权利并计算退款。"""

    now = _now(now)
    coop = _get(store.cooperations, coop_id, "合作单")
    if coop.status != CoopStatus.PERFORMING:
        raise ValueError("仅履约中可判定节点失败")
    current = _current_milestone(coop)
    if current is None:
        raise ValueError("没有进行中的节点")
    current.state = NodeState.FAILED
    _settle_failure(store, coop, reason)
    return coop


def check_delay(store, coop_id, now=None):
    """当前节点超过截止时间与宽限期即视为延期，按约定解锁并退款。"""

    now = _now(now)
    coop = _get(store.cooperations, coop_id, "合作单")
    if coop.status != CoopStatus.PERFORMING:
        return False
    current = _current_milestone(coop)
    if current is None or current.deadline is None:
        return False
    if now <= current.deadline + timedelta(days=coop.delay_grace_days):
        return False
    current.state = NodeState.DELAYED
    _settle_failure(store, coop, "延期解锁")
    return True


# ---------- 资金 ----------


def disburse(store, coop_id, tranche_id, now=None):
    coop = _get(store.cooperations, coop_id, "合作单")
    if coop.status != CoopStatus.PERFORMING:
        raise ValueError("仅履约中可拨付")
    tranche = _get({t.tranche_id: t for t in coop.tranches}, tranche_id, "拨款")
    if tranche.status != TR_PENDING:
        raise ValueError(f"拨款当前状态为{tranche.status}，不能拨付")
    tranche.status = TR_PAID
    return tranche


def record_refund(store, coop_id, tranche_id, now=None):
    coop = _get(store.cooperations, coop_id, "合作单")
    tranche = _get({t.tranche_id: t for t in coop.tranches}, tranche_id, "拨款")
    if tranche.status != TR_REFUNDING:
        raise ValueError(f"拨款当前状态为{tranche.status}，不能登记退款")
    tranche.status = TR_REFUNDED
    return tranche


def withdraw_funder(store, coop_id, funder_org, now=None):
    """资金方中途退出：未拨付取消，未确认的已拨付转入待退款，已确认保留。"""

    now = _now(now)
    coop = _get(store.cooperations, coop_id, "合作单")
    if coop.status != CoopStatus.PERFORMING:
        raise ValueError("仅履约中可办理资金方退出")
    tranches = [t for t in coop.tranches if t.funder_org == funder_org]
    if not tranches:
        raise ValueError(f"资金方{funder_org}在该合作单中没有拨款")
    for tranche in tranches:
        if tranche.status == TR_PENDING:
            tranche.status = TR_CANCELLED
            coop.funding_gap = True
        elif tranche.status == TR_PAID:
            tranche.status = TR_REFUNDING
            tranche.refund_due = tranche.amount * coop.refund_percent // 100
    return coop


# ---------- 主管说明 ----------


def supervisor_briefing(store, req_id, now=None):
    """主管视图：推荐证据、当前权利占用、跨组织待办、每笔资金对应的成果。"""

    now = _now(now)
    req = _get(store.requirements, req_id, "需求")
    coops = [c for c in store.cooperations.values() if c.req_id == req_id]
    ach_ids = {c.ach_id for c in coops}

    recs = [r for r in store.recommendations.values() if r.req_id == req_id]
    recs.sort(key=lambda r: (-r.score, r.ach_id))

    occupation = [
        {
            "成果": g.ach_id,
            "知识产权边界": g.boundary_id,
            "持有方": g.holder_org,
            "合作单": g.coop_id,
            "到期时间": g.expires_at.isoformat(),
        }
        for g in sorted(store.grants.values(), key=lambda g: g.grant_id)
        if g.ach_id in ach_ids and g.is_active(now)
    ]

    todos = []
    for coop in sorted(coops, key=lambda c: c.coop_id):
        if coop.status == CoopStatus.CONTACT and not coop.nda_id:
            todos.append({"事项": "待签保密协议", "责任组织": coop.team_org, "合作单": coop.coop_id})
        if coop.status == CoopStatus.PERFORMING:
            current = _current_milestone(coop)
            if current is not None:
                todos.append(
                    {
                        "事项": f"待通过节点：{current.node.value}",
                        "责任组织": coop.team_org,
                        "合作单": coop.coop_id,
                    }
                )
            if coop.funding_gap:
                todos.append(
                    {"事项": "资金缺口待补齐", "责任组织": coop.demand_org, "合作单": coop.coop_id}
                )
        for tranche in coop.tranches:
            if tranche.status == TR_REFUNDING:
                todos.append(
                    {
                        "事项": f"待退款 {tranche.refund_due}",
                        "责任组织": tranche.funder_org,
                        "合作单": coop.coop_id,
                    }
                )

    funds = [
        {
            "拨款": t.tranche_id,
            "合作单": coop.coop_id,
            "资金方": t.funder_org,
            "金额": t.amount,
            "状态": t.status,
            "节点": t.node.value,
            "成果": coop.ach_id,
            "已确认": t.status == TR_CONFIRMED,
            "待退款": t.refund_due,
        }
        for coop in sorted(coops, key=lambda c: c.coop_id)
        for t in coop.tranches
    ]

    duties = [
        {"地区": d.region, "责任": d.duty, "责任组织": d.responsible_org, "合作单": coop.coop_id}
        for coop in sorted(coops, key=lambda c: c.coop_id)
        if coop.status == CoopStatus.PERFORMING
        for d in coop.region_duties
    ]

    return {
        "需求": req.req_id,
        "需求状态": req.status,
        "推荐证据": [
            {
                "成果": r.ach_id,
                "分数": r.score,
                "性质": "建议接洽，不构成签约",
                "证据": r.evidence,
                "生成时间": r.created_at.isoformat(),
            }
            for r in recs
        ],
        "当前权利占用": occupation,
        "跨组织待办": todos,
        "资金对应成果": funds,
        "地域转化责任": duties,
    }
