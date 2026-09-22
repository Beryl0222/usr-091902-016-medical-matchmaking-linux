"""闽港医疗科创协作的领域核心。

把一场撮合拆成六类互相独立的要素：

* 需求问题（Demand）：福建出题，只有脱敏摘要可在保密协议生效前外发；
* 成果能力（Achievement）：香港解题，携带知识产权边界；
* 知识产权（IP_BOUNDARY）：排他承诺只能落在授权范围内，不得重复授予；
* 临床资源（ClinicalResource）：伦理与验证所依赖的医院科室；
* 资金条件（Funding）：每笔资金须对应已确认成果，可中途退出；
* 地域转化责任（RegionResponsibility）：转化落地义务随里程碑走。

匹配分数只用于建议接洽，不产生任何权利；进入尽调后锁定材料版本并登记
利益冲突；排他期由双方有权代表签署，到期自动失效；项目依次经过技术攻
关、伦理审查、验证、转化、拨款节点，失败或延期按约定解锁权利与退款；
未入选方在任何阶段都看不到秘密材料。

模块只依赖标准库，时间通过 clock 注入，便于测试自动到期。
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

# ---- 固定词表（与 fixtures/domain.json 保持一致语义） ----

ROLES = ("需求机构", "成果团队", "临床合作方", "资金方")

DEMAND_STATES = ("公开征集", "保密接洽", "尽调中", "履约中", "已解锁")

PROJECT_STAGES = ("技术攻关", "伦理审查", "验证", "转化", "拨款")
# 各节点失败/延期时的处置约定
STAGE_OUTCOMES = ("通过", "延期", "失败")

FUNDING_STATES = ("已承诺", "已到账对应成果", "已退出", "已退款")


def utcnow():
    """统一的时间入口，使用带时区的 UTC 时间。"""
    return datetime.now(timezone.utc)


def parse_ts(value):
    """把 ISO 字符串解析为带时区时间；已是时间对象则原样返回。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class DomainError(Exception):
    """领域规则被违反时抛出，消息面向主管人员，可直接展示。"""


# ---- 组织、需求与成果 ----

@dataclass
class Organization:
    org_id: str
    name: str
    kind: str                       # 取 ROLES 之一（主管部门除外）

    def __post_init__(self):
        if self.kind not in ROLES and self.kind != "主管部门":
            raise DomainError(f"未知机构角色：{self.kind}")


@dataclass
class Demand:
    demand_id: str
    title: str
    owner_org_id: str
    desensitized_summary: str       # 保密协议生效前唯一可见内容
    secret_brief: dict              # 未脱敏材料：患者数据、医院细节、联系人等
    clinical_need: str = ""         # 所需临床资源描述
    region_responsibility: str = ""  # 地域转化责任（如“福建落地”）
    state: str = "公开征集"

    def public_view(self):
        """任何机构（含未入选方）在保密协议生效前能看到的内容。"""
        return {
            "demand_id": self.demand_id,
            "title": self.title,
            "owner_org_id": self.owner_org_id,
            "summary": self.desensitized_summary,
            "state": self.state,
        }


@dataclass
class Achievement:
    achievement_id: str
    title: str
    owner_org_id: str
    capability_summary: str
    ip_boundary: str                # 知识产权边界：可授权范围
    secret_detail: dict = field(default_factory=dict)
    clinical_resources: list = field(default_factory=list)  # ClinicalResource.id

    def public_view(self):
        return {
            "achievement_id": self.achievement_id,
            "title": self.title,
            "owner_org_id": self.owner_org_id,
            "capability": self.capability_summary,
            "ip_boundary": self.ip_boundary,
            "clinical_resources": list(self.clinical_resources),
        }


@dataclass
class ClinicalResource:
    resource_id: str
    hospital_org_id: str
    department: str
    ethics_committee: str
    capacity_note: str = ""


# ---- 保密协议：看秘密材料的唯一门禁 ----

@dataclass
class NDA:
    nda_id: str
    demand_id: str
    org_id: str
    effective_at: datetime
    signed_by: dict                 # {"name": ..., "title": ...} 有权代表
    selected: bool = True           # 只有入选接洽方才允许签 NDA

    def active(self, now):
        return parse_ts(self.effective_at) <= now


# ---- 匹配：仅建议，不占权利 ----

@dataclass
class Match:
    demand_id: str
    achievement_id: str
    score: float                    # 0~1，仅用于建议接洽顺序
    evidence: list = field(default_factory=list)  # 打分依据（关键词/指标命中）
    suggested: bool = True

    def view(self):
        return {
            "demand_id": self.demand_id,
            "achievement_id": self.achievement_id,
            "score": round(self.score, 3),
            "evidence": list(self.evidence),
            "note": "分数仅用于建议接洽，不构成签约或任何排他承诺",
        }


# ---- 尽调：锁版本 + 利益冲突登记 ----

@dataclass
class DueDiligence:
    dd_id: str
    demand_id: str
    achievement_id: str
    material_version: str           # 进入尽调时冻结的材料版本号
    locked_at: datetime
    conflicts: list = field(default_factory=list)  # [ConflictRecord]
    status: str = "进行中"          # 进行中 / 通过 / 终止


@dataclass
class ConflictRecord:
    org_id: str
    person: str
    relation: str                   # 例如“同时持有成果团队股权”
    declared_at: datetime


# ---- 排他期：有权代表签署、自动到期、不得重复授予 ----

@dataclass
class Exclusivity:
    exclusivity_id: str
    demand_id: str
    achievement_id: str
    grantee_org_id: str
    scope: str                      # 必须落在成果 ip_boundary 之内
    starts_at: datetime
    expires_at: datetime
    signed_by: dict = field(default_factory=dict)  # 双方有权代表
    status: str = "生效中"          # 生效中 / 已到期 / 已解除

    def active(self, now):
        now = parse_ts(now)
        return self.status == "生效中" and parse_ts(self.starts_at) <= now < parse_ts(self.expires_at)

    def view(self, now):
        now = parse_ts(now)
        status = "生效中" if self.active(now) else ("已解除" if self.status == "已解除" else "已到期")
        return {
            "exclusivity_id": self.exclusivity_id,
            "demand_id": self.demand_id,
            "achievement_id": self.achievement_id,
            "grantee_org_id": self.grantee_org_id,
            "scope": self.scope,
            "starts_at": parse_ts(self.starts_at).isoformat(),
            "expires_at": parse_ts(self.expires_at).isoformat(),
            "status": status,
            "auto_expired": now >= parse_ts(self.expires_at),
        }


# ---- 项目里程碑与资金 ----

@dataclass
class Milestone:
    stage: str                      # 取 PROJECT_STAGES，按顺序推进
    due_at: datetime
    outcome: str = "待完成"
    decided_at: datetime = None
    note: str = ""


@dataclass
class FundingCommitment:
    """一笔资金承诺：必须绑定到已确认（排他+尽调通过）的成果。"""
    funding_id: str
    demand_id: str
    achievement_id: str
    funder_org_id: str
    amount: float
    state: str = "已承诺"
    confirmed_achievement: bool = False  # 对应成果是否已确认
    paid_at: datetime = None
    refunded_at: datetime = None
    linked_milestone: str = ""      # 释放所依赖的里程碑
    history: list = field(default_factory=list)


@dataclass
class Project:
    project_id: str
    demand_id: str
    achievement_id: str
    milestones: dict = field(default_factory=dict)  # stage -> Milestone
    current_stage: str = "技术攻关"
    unlocked_rights: list = field(default_factory=list)   # 已解锁的权利说明
    refunds_due: list = field(default_factory=list)       # 触发的退款约定


# ===================================================================
# 平台：所有规则的唯一执行点
# ===================================================================

class Platform:
    def __init__(self, clock=utcnow):
        self.clock = clock
        self.orgs = {}
        self.demands = {}
        self.achievements = {}
        self.clinical = {}
        self.ndas = []
        self.matches = []
        self.dds = []
        self.exclusivities = []
        self.projects = {}
        self.fundings = []
        # secret_material_access 不单独存表：访问权 = 有效NDA + 入选 + 尽调未终止

    # ----- 注册 -----

    def register_org(self, org_id, name, kind):
        if org_id in self.orgs:
            raise DomainError(f"机构已存在：{org_id}")
        org = Organization(org_id, name, kind)
        self.orgs[org_id] = org
        return org

    def publish_demand(self, demand_id, title, owner_org_id, summary, secret_brief, **kw):
        self._require_org(owner_org_id)
        if not summary or not str(summary).strip():
            raise DomainError("脱敏摘要不能为空，保密协议生效前只能外发摘要")
        if not secret_brief:
            raise DomainError("需求必须登记未脱敏材料本体，外发由访问控制决定")
        if demand_id in self.demands:
            raise DomainError(f"需求已存在：{demand_id}")
        demand = Demand(demand_id, title, owner_org_id, str(summary), secret_brief, **kw)
        self.demands[demand_id] = demand
        return demand

    def register_achievement(self, achievement_id, title, owner_org_id, summary, ip_boundary,
                             secret_detail=None, clinical_resources=None):
        self._require_org(owner_org_id)
        if not ip_boundary or not str(ip_boundary).strip():
            raise DomainError("成果必须声明知识产权边界，否则不能参与匹配")
        for rid in clinical_resources or []:
            if rid not in self.clinical:
                raise DomainError(f"引用的临床资源不存在：{rid}")
        ach = Achievement(achievement_id, title, owner_org_id, summary, ip_boundary,
                          secret_detail or {}, list(clinical_resources or []))
        self.achievements[achievement_id] = ach
        return ach

    def register_clinical_resource(self, resource_id, hospital_org_id, department,
                                   ethics_committee, capacity_note=""):
        self._require_org(hospital_org_id)
        res = ClinicalResource(resource_id, hospital_org_id, department,
                               ethics_committee, capacity_note)
        self.clinical[resource_id] = res
        return res

    # ----- 匹配：纯建议 -----

    def suggest_match(self, demand_id, achievement_id, score, evidence=None):
        if demand_id not in self.demands:
            raise DomainError(f"需求不存在：{demand_id}")
        if achievement_id not in self.achievements:
            raise DomainError(f"成果不存在：{achievement_id}")
        if not 0 <= score <= 1:
            raise DomainError("匹配分数必须落在 0~1")
        match = Match(demand_id, achievement_id, float(score), list(evidence or []))
        self.matches.append(match)
        return match

    def ranked_suggestions(self, demand_id):
        """返回建议接洽顺序；同一需求可同时匹配多个成果，互不去权。"""
        return sorted((m for m in self.matches if m.demand_id == demand_id),
                      key=lambda m: m.score, reverse=True)

    # ----- 保密协议 -----

    def sign_nda(self, nda_id, demand_id, org_id, signed_by, effective_at=None, selected=True):
        self._require_org(org_id)
        if demand_id not in self.demands:
            raise DomainError(f"需求不存在：{demand_id}")
        if not selected:
            raise DomainError("未入选接洽方不得签署 NDA，亦不得接触秘密材料")
        if not self._is_authorized_rep(signed_by):
            raise DomainError("保密协议须由有权代表签署（需提供姓名与职务）")
        effective_at = parse_ts(effective_at or self.clock())
        nda = NDA(nda_id, demand_id, org_id, effective_at, dict(signed_by), selected=True)
        self.ndas.append(nda)
        self.demands[demand_id].state = "保密接洽"
        return nda

    def can_access_secret(self, demand_id, org_id):
        """秘密材料可见性判定：有效NDA ∧ 入选 ∧（无尽调或尽调未终止）。

        未入选方在任何阶段（即使别人已签约、项目已结束）都返回 False。
        """
        if not self._has_active_nda(demand_id, org_id):
            return False
        dd = self._latest_dd(demand_id, org_id=org_id)
        if dd is not None and dd.status == "终止":
            return False
        return True

    def view_demand(self, demand_id, org_id):
        """按机构身份返回需求视图：无权只见脱敏摘要。"""
        demand = self._require_demand(demand_id)
        view = demand.public_view()
        if self.can_access_secret(demand_id, org_id):
            view["secret_brief"] = demand.secret_brief
            view["clinical_need"] = demand.clinical_need
            view["region_responsibility"] = demand.region_responsibility
        return view

    # ----- 尽调：锁版本 + 利益冲突 -----

    def open_due_diligence(self, dd_id, demand_id, achievement_id, material_version):
        if not self._has_active_nda(demand_id,
                                   self.achievements[achievement_id].owner_org_id):
            raise DomainError("保密协议未生效，不能进入尽调或交接秘密材料")
        if not material_version:
            raise DomainError("进入尽调必须锁定材料版本")
        demand = self._require_demand(demand_id)
        dd = DueDiligence(dd_id, demand_id, achievement_id, material_version,
                          self.clock())
        self.dds.append(dd)
        demand.state = "尽调中"
        return dd

    def declare_conflict(self, dd_id, org_id, person, relation):
        dd = self._require_dd(dd_id)
        dd.conflicts.append(ConflictRecord(org_id, person, relation, self.clock()))
        return dd.conflicts[-1]

    def close_due_diligence(self, dd_id, passed):
        dd = self._require_dd(dd_id)
        dd.status = "通过" if passed else "终止"
        if not passed:
            # 尽调失败即收回秘密材料访问权；该方成为未入选方
            self._revoke_access(dd.demand_id,
                                self.achievements[dd.achievement_id].owner_org_id)
        return dd

    def locked_material(self, dd_id):
        """尽调期间一切材料以锁定版本为准，返回冻结快照。"""
        dd = self._require_dd(dd_id)
        demand = self._require_demand(dd.demand_id)
        ach = self.achievements[dd.achievement_id]
        return {
            "material_version": dd.material_version,
            "locked_at": parse_ts(dd.locked_at).isoformat(),
            "frozen": True,
            "demand_secret": demand.secret_brief,
            "achievement_secret": ach.secret_detail,
            "conflicts": [
                {"org_id": c.org_id, "person": c.person, "relation": c.relation,
                 "declared_at": parse_ts(c.declared_at).isoformat()}
                for c in dd.conflicts
            ],
        }

    # ----- 排他期 -----

    def grant_exclusivity(self, exclusivity_id, demand_id, achievement_id, scope,
                          duration_days, signed_by_both, starts_at=None):
        ach = self.achievements.get(achievement_id)
        if ach is None:
            raise DomainError(f"成果不存在：{achievement_id}")
        dd = self._latest_dd(demand_id, achievement_id=achievement_id)
        if dd is None or dd.status != "通过":
            raise DomainError("尽调通过后才能承诺排他权")
        if scope not in ach.ip_boundary and not self._scope_within(scope, ach.ip_boundary):
            raise DomainError(f"排他范围超出知识产权边界：{scope} ⊄ {ach.ip_boundary}")
        self._require_two_reps(signed_by_both)
        start = parse_ts(starts_at or self.clock())
        expires = start + timedelta(days=duration_days)
        # 同一需求、同一授权范围不得重复授予（防止一物多许）
        for ex in self.exclusivities:
            if ex.demand_id == demand_id and ex.status == "生效中" and ex.active(self.clock()):
                if self._scopes_overlap(ex.scope, scope):
                    raise DomainError(
                        f"该需求在 {ex.scope} 上已有生效排他（{ex.exclusivity_id}），"
                        "不得向多方重复承诺")
        ex = Exclusivity(exclusivity_id, demand_id, achievement_id, ach.owner_org_id,
                         scope, start, expires, dict(signed_by_both))
        self.exclusivities.append(ex)
        self._require_demand(demand_id).state = "履约中"
        return ex

    def active_exclusivities(self, demand_id=None):
        result = []
        for ex in self.exclusivities:
            if demand_id and ex.demand_id != demand_id:
                continue
            if ex.active(self.clock()):
                result.append(ex)
        return result

    def expire_due_exclusivities(self):
        """到期自动失效：无需人工解除，过期排他不再占用权利。"""
        expired = []
        now = self.clock()
        for ex in self.exclusivities:
            if ex.status == "生效中" and parse_ts(now) >= parse_ts(ex.expires_at):
                ex.status = "已到期"
                expired.append(ex)
        return expired

    # ----- 项目与里程碑 -----

    def start_project(self, project_id, demand_id, achievement_id, milestone_due_days):
        dd = self._latest_dd(demand_id, achievement_id=achievement_id)
        if dd is None or dd.status != "通过":
            raise DomainError("只有尽调通过的匹配才能立项")
        if not self._has_active_exclusivity(demand_id, achievement_id):
            raise DomainError("立项前须有双方代表签署的有效排他期")
        due = {}
        base = self.clock()
        for i, stage in enumerate(PROJECT_STAGES):
            days = milestone_due_days[stage] if isinstance(milestone_due_days, dict) \
                else milestone_due_days[i]
            due[stage] = Milestone(stage, base + timedelta(days=days))
        project = Project(project_id, demand_id, achievement_id, due)
        self.projects[project_id] = project
        return project

    def decide_milestone(self, project_id, stage, outcome, note=""):
        """登记节点结果。延期/失败按约定解锁权利并产生退款。"""
        project = self._require_project(project_id)
        if stage not in PROJECT_STAGES:
            raise DomainError(f"未知节点：{stage}")
        if outcome not in STAGE_OUTCOMES:
            raise DomainError(f"节点结论必须是：{STAGE_OUTCOMES}")
        expected = PROJECT_STAGES[PROJECT_STAGES.index(project.current_stage)]
        if stage != expected:
            raise DomainError(f"节点须按顺序推进：当前应处理 {expected}，而非 {stage}")
        milestone = project.milestones[stage]
        milestone.outcome = outcome
        milestone.decided_at = self.clock()
        milestone.note = note

        if outcome == "通过":
            idx = PROJECT_STAGES.index(stage)
            if stage == "拨款":
                # 拨款节点通过：已到账资金标记对应成果
                for f in self.fundings:
                    if f.demand_id == project.demand_id and f.linked_milestone == stage:
                        f.state = "已到账对应成果"
                        f.paid_at = self.clock()
                return milestone
            project.current_stage = PROJECT_STAGES[idx + 1]
            return milestone

        # 延期或失败：按约定解锁权利；失败额外解除排他、解锁需求并退款
        if outcome == "延期":
            project.unlocked_rights.append(
                f"{stage}延期：顺延下一节点期限，已授予权利暂不扩张（{note or '无备注'}）")
        else:  # 失败
            project.unlocked_rights.append(f"{stage}失败：解除排他权，需求恢复公开（{note or '无备注'}）")
            self._release_rights(project)
            for f in self.fundings:
                if f.demand_id == project.demand_id and f.state in ("已承诺", "已到账对应成果"):
                    f.state = "已退款"
                    f.refunded_at = self.clock()
                    f.history.append({"at": self.clock().isoformat(), "event": f"{stage}失败触发退款"})
                    project.refunds_due.append(
                        {"funding_id": f.funding_id, "amount": f.amount,
                         "funder_org_id": f.funder_org_id})
        return milestone

    # ----- 资金 -----

    def commit_funding(self, funding_id, demand_id, achievement_id, funder_org_id,
                       amount, linked_milestone):
        self._require_org(funder_org_id)
        if amount <= 0:
            raise DomainError("资金金额必须为正")
        if linked_milestone not in PROJECT_STAGES:
            raise DomainError("资金必须绑定到具体里程碑节点")
        confirmed = self._achievement_confirmed(demand_id, achievement_id)
        funding = FundingCommitment(
            funding_id, demand_id, achievement_id, funder_org_id, float(amount),
            confirmed_achievement=confirmed, linked_milestone=linked_milestone)
        funding.history.append({
            "at": self.clock().isoformat(),
            "event": "资金方承诺",
            "confirmed_achievement": confirmed,
        })
        self.fundings.append(funding)
        return funding

    def withdraw_funding(self, funding_id, reason=""):
        """资金方中途退出：解除占用并释放对应权利约定。"""
        funding = self._require_funding(funding_id)
        if funding.state in ("已退出", "已退款"):
            raise DomainError("该笔资金已结束，不能重复退出")
        funding.state = "已退出"
        funding.history.append({"at": self.clock().isoformat(),
                                "event": f"资金方中途退出：{reason or '未说明'}"})
        # 资金退出不影响秘密材料可见性（未入选方依旧不可见）；
        # 若退出导致在途项目里程碑资源落空，登记一笔待办式解锁提示
        for project in self.projects.values():
            if project.demand_id == funding.demand_id:
                project.unlocked_rights.append(
                    f"资金方 {funding.funder_org_id} 退出（{funding.funding_id}），"
                    "按约定暂缓后续里程碑，直至替补资金到位")
        return funding

    def funding_ledger(self, demand_id=None):
        """每笔资金对应的已确认成果——主管对账视图。"""
        rows = []
        for f in self.fundings:
            if demand_id and f.demand_id != demand_id:
                continue
            rows.append({
                "funding_id": f.funding_id,
                "demand_id": f.demand_id,
                "achievement_id": f.achievement_id,
                "achievement_confirmed": f.confirmed_achievement,
                "funder_org_id": f.funder_org_id,
                "amount": f.amount,
                "state": f.state,
                "linked_milestone": f.linked_milestone,
                "paid_at": parse_ts(f.paid_at).isoformat() if f.paid_at else None,
                "refunded_at": parse_ts(f.refunded_at).isoformat() if f.refunded_at else None,
            })
        return rows

    # ----- 主管总览：证据、权利占用、跨组织待办、资金对账 -----

    def supervisor_brief(self, demand_id):
        """一个需求同时匹配多个成果、资金方中途退出时的完整说明视图。"""
        demand = self._require_demand(demand_id)
        now = self.clock()
        self.expire_due_exclusivities()

        matches = [m.view() for m in self.ranked_suggestions(demand_id)]
        achievements = []
        for m in self.ranked_suggestions(demand_id):
            ach = self.achievements[m.achievement_id]
            dd = self._latest_dd(demand_id, achievement_id=ach.achievement_id)
            achievements.append({
                **ach.public_view(),
                "suggested_score": m.view()["score"],
                "match_evidence": m.view()["evidence"],
                "due_diligence": None if dd is None else {
                    "id": dd.dd_id, "material_version": dd.material_version,
                    "status": dd.status,
                    "conflicts": [
                        {"org_id": c.org_id, "person": c.person, "relation": c.relation}
                        for c in dd.conflicts],
                },
                "exclusivity": next(
                    (ex.view(now) for ex in self.exclusivities
                     if ex.demand_id == demand_id and ex.achievement_id == ach.achievement_id),
                    None),
            })

        # 当前权利占用：生效排他 + 已签 NDA（入选方）
        rights = {
            "active_exclusivities": [ex.view(now) for ex in self.active_exclusivities(demand_id)],
            "nda_parties": [
                {"org_id": n.org_id, "effective_at": parse_ts(n.effective_at).isoformat(),
                 "signed_by": n.signed_by}
                for n in self.ndas if n.demand_id == demand_id and n.active(now)],
        }

        # 跨组织待办：里程碑、尽调冲突、资金退出、退款
        todos = []
        for project in self.projects.values():
            if project.demand_id != demand_id:
                continue
            stage = project.current_stage
            ms = project.milestones[stage]
            todos.append({
                "type": "里程碑待决",
                "project_id": project.project_id,
                "stage": stage,
                "due_at": parse_ts(ms.due_at).isoformat(),
                "overdue": parse_ts(ms.due_at) < now and ms.outcome == "待完成",
                "owner_orgs": self._project_orgs(project),
            })
            for note in project.unlocked_rights:
                todos.append({"type": "权利解锁约定", "project_id": project.project_id, "detail": note})
            for refund in project.refunds_due:
                todos.append({"type": "退款待执行", "project_id": project.project_id, **refund})
        for dd in self.dds:
            if dd.demand_id == demand_id and dd.conflicts and dd.status == "进行中":
                todos.append({"type": "利益冲突待复核", "dd_id": dd.dd_id,
                              "count": len(dd.conflicts)})
        for f in self.fundings:
            if f.demand_id == demand_id and f.state == "已退出":
                todos.append({"type": "资金缺口", "funding_id": f.funding_id,
                              "amount": f.amount, "funder_org_id": f.funder_org_id})

        return {
            "demand": demand.public_view(),
            "recommendation": {
                "rule": "匹配分数仅建议接洽，签约以尽调通过+双方代表排他协议为准",
                "matches": matches,
                "candidates": achievements,
            },
            "rights_occupancy": rights,
            "cross_org_todos": todos,
            "funding_ledger": self.funding_ledger(demand_id),
            "generated_at": now.isoformat(),
        }

    # ============ 内部辅助 ============

    def _require_org(self, org_id):
        org = self.orgs.get(org_id)
        if org is None:
            raise DomainError(f"机构不存在：{org_id}")
        return org

    def _require_demand(self, demand_id):
        if demand_id not in self.demands:
            raise DomainError(f"需求不存在：{demand_id}")
        return self.demands[demand_id]

    def _require_dd(self, dd_id):
        for dd in self.dds:
            if dd.dd_id == dd_id:
                return dd
        raise DomainError(f"尽调不存在：{dd_id}")

    def _require_project(self, project_id):
        if project_id not in self.projects:
            raise DomainError(f"项目不存在：{project_id}")
        return self.projects[project_id]

    def _require_funding(self, funding_id):
        for f in self.fundings:
            if f.funding_id == funding_id:
                return f
        raise DomainError(f"资金承诺不存在：{funding_id}")

    def _has_active_nda(self, demand_id, org_id):
        return any(n.demand_id == demand_id and n.org_id == org_id and n.active(self.clock())
                   and n.selected for n in self.ndas)

    def _latest_dd(self, demand_id, achievement_id=None, org_id=None):
        candidates = [dd for dd in self.dds if dd.demand_id == demand_id]
        if achievement_id:
            candidates = [dd for dd in candidates if dd.achievement_id == achievement_id]
        if org_id:
            candidates = [dd for dd in candidates
                          if self.achievements[dd.achievement_id].owner_org_id == org_id]
        return candidates[-1] if candidates else None

    def _revoke_access(self, demand_id, org_id):
        for nda in self.ndas:
            if nda.demand_id == demand_id and nda.org_id == org_id:
                nda.selected = False  # 尽调失败 → 未入选方，秘密访问立即关闭

    def _release_rights(self, project):
        for ex in self.exclusivities:
            if ex.demand_id == project.demand_id and ex.achievement_id == project.achievement_id:
                ex.status = "已解除"
        demand = self.demands.get(project.demand_id)
        if demand:
            demand.state = "已解锁"

    def _has_active_exclusivity(self, demand_id, achievement_id):
        return any(ex.demand_id == demand_id and ex.achievement_id == achievement_id
                   and ex.active(self.clock()) for ex in self.exclusivities)

    def _achievement_confirmed(self, demand_id, achievement_id):
        """成果已确认 = 尽调通过且持有生效排他（签约后临床验证前的确认态）。"""
        dd = self._latest_dd(demand_id, achievement_id=achievement_id)
        return bool(dd and dd.status == "通过"
                    and self._has_active_exclusivity(demand_id, achievement_id))

    def _project_orgs(self, project):
        """跨组织待办涉及的全部机构：需求方、成果方、临床方、资金方。"""
        orgs = [self.demands[project.demand_id].owner_org_id,
                self.achievements[project.achievement_id].owner_org_id]
        for rid in self.achievements[project.achievement_id].clinical_resources:
            orgs.append(self.clinical[rid].hospital_org_id)
        for f in self.fundings:
            if f.demand_id == project.demand_id and f.funder_org_id not in orgs:
                orgs.append(f.funder_org_id)
        return orgs

    @staticmethod
    def _is_authorized_rep(signed_by):
        return bool(signed_by) and signed_by.get("name") and signed_by.get("title")

    @staticmethod
    def _require_two_reps(signed_by_both):
        if not signed_by_both:
            raise DomainError("排他期须由双方有权代表签署")
        for key in ("demand_party", "achievement_party"):
            rep = signed_by_both.get(key)
            if not rep or not rep.get("name") or not rep.get("title"):
                raise DomainError(f"缺少一方有权代表：{key}")

    @staticmethod
    def _scope_within(scope, boundary):
        # 边界允许写成逗号分隔的授权项；范围命中其中一项即视为在内
        return scope in [part.strip() for part in str(boundary).replace("；", ",").replace(";", ",").split(",") if part.strip()]

    @staticmethod
    def _scopes_overlap(a, b):
        def parts(s):
            return {p.strip() for p in str(s).replace("；", ",").replace(";", ",").split(",") if p.strip()}
        return bool(parts(a) & parts(b)) or a in b or b in a
