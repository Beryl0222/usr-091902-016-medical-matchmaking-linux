"""验证领域规则：保密可见性、匹配建议、尽调锁定、排他权、里程碑与资金。"""

import json
import unittest
from datetime import datetime, timedelta, timezone

import domain as d

T0 = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
DAY = timedelta(days=1)


class DomainTestBase(unittest.TestCase):
    """搭建一个需求、三个成果、临床资源与资金条件的基础场景。"""

    def setUp(self):
        self.store = d.Store()
        s = self.store
        d.register_org(s, d.Organization("hospital", "福建第一医院", {d.Role.DEMAND}, {"林主任"}))
        d.register_org(s, d.Organization("team-hk", "香港影像团队", {d.Role.TEAM}, {"陈博士"}))
        d.register_org(s, d.Organization("team-hk2", "香港监护团队", {d.Role.TEAM}, {"黄博士"}))
        d.register_org(s, d.Organization("clinic", "香港临床中心", {d.Role.CLINICAL}, set()))
        d.register_org(s, d.Organization("fund", "深港投资机构", {d.Role.FUNDER}, {"王总"}))
        d.register_org(s, d.Organization("gov", "省科技主管部门", {d.Role.AUTHORITY}, {"监管员"}))
        d.publish_requirement(
            s,
            d.Requirement(
                req_id="req-1",
                owner_org="hospital",
                title="智能辅助诊断需求",
                summary="某科室需要智能影像辅助诊断能力（已脱敏）",
                secret_detail="患者队列X的影像数据接口与标注口径",
                needs={"影像识别", "隐私计算"},
                clinical_needs={"多中心试验"},
            ),
        )
        d.register_achievement(
            s,
            d.Achievement(
                ach_id="ach-1",
                team_org="team-hk",
                title="影像辅诊系统",
                summary="三甲级影像辅诊能力（已脱敏）",
                secret_detail="模型权重与训练管线",
                capabilities={"影像识别", "隐私计算", "联邦学习"},
                ip_boundaries=[d.IPBoundary("ip-1", "影像算法专利族", "team-hk")],
            ),
        )
        d.register_achievement(
            s,
            d.Achievement(
                ach_id="ach-2",
                team_org="team-hk2",
                title="影像标注工具",
                summary="标注工具（已脱敏）",
                secret_detail="标注规范与质检流程",
                capabilities={"影像识别"},
                ip_boundaries=[d.IPBoundary("ip-2", "标注工具著作权", "team-hk2")],
            ),
        )
        d.register_achievement(
            s,
            d.Achievement(
                ach_id="ach-3",
                team_org="team-hk2",
                title="远程监护平台",
                summary="远程监护（已脱敏）",
                secret_detail="设备固件与协议",
                capabilities={"远程监护"},
                ip_boundaries=[d.IPBoundary("ip-3", "监护设备专利", "team-hk2")],
            ),
        )
        d.register_clinical(s, d.ClinicalResource("clin-1", "clinic", {"多中心试验"}, "可承接"))
        d.register_funding_term(s, d.FundingTerm("term-1", "fund", 5_000_000, "按节点拨付"))
        d.publish_material_version(s, "v1", "req-1", "digest-v1", now=T0)

    # ---------- 场景推进辅助 ----------

    def recommend(self):
        return d.recommend(self.store, "req-1", now=T0)

    def coop_to_contact(self, coop_id, ach_id):
        rec = next(r for r in self.recommend() if r.ach_id == ach_id)
        return d.initiate_cooperation(self.store, coop_id, rec.rec_id, now=T0)

    def coop_to_dd(self, coop_id, ach_id, team_org):
        self.coop_to_contact(coop_id, ach_id)
        d.sign_nda(self.store, coop_id, f"nda-{coop_id}", effective_at=T0, now=T0)
        d.enter_due_diligence(self.store, coop_id, "v1", {"hospital": [], team_org: []}, now=T0)
        return self.store.cooperations[coop_id]

    def coop_to_performing(self, coop_id="coop-1", ach_id="ach-1", team_org="team-hk", rep="陈博士"):
        self.coop_to_dd(coop_id, ach_id, team_org)
        terms = d.AgreementTerms(
            refund_percent=50,
            delay_grace_days=5,
            deadlines={d.Node.RESEARCH: T0 + 10 * DAY},
            funding_plan=[
                ("term-1", d.Node.RESEARCH, 1_000_000),
                ("term-1", d.Node.VALIDATION, 2_000_000),
                ("term-1", d.Node.FUNDING, 2_000_000),
            ],
            region_duties=[
                d.RegionDuty("福建", "落地转化与注册申报", "hospital"),
                d.RegionDuty("香港", "海外推广", team_org),
            ],
        )
        d.sign_agreement(self.store, coop_id, "林主任", rep, terms, now=T0)
        return self.store.cooperations[coop_id]


class VisibilityTest(DomainTestBase):
    def test_nda生效前只能看到脱敏摘要(self):
        view = d.requirement_view(self.store, "req-1", "team-hk", now=T0)
        self.assertEqual(view["可见级别"], "脱敏摘要")
        self.assertNotIn("秘密细节", view)
        self.assertEqual(d.requirement_view(self.store, "req-1", "hospital", now=T0)["可见级别"], "全文")
        self.assertEqual(d.requirement_view(self.store, "req-1", "gov", now=T0)["可见级别"], "全文")

    def test_nda生效后可见全文(self):
        self.coop_to_contact("coop-1", "ach-1")
        d.sign_nda(self.store, "coop-1", "nda-1", effective_at=T0 + DAY, now=T0)
        self.assertEqual(
            d.requirement_view(self.store, "req-1", "team-hk", now=T0)["可见级别"], "脱敏摘要"
        )
        full = d.requirement_view(self.store, "req-1", "team-hk", now=T0 + DAY)
        self.assertEqual(full["可见级别"], "全文")
        self.assertEqual(full["秘密细节"], "患者队列X的影像数据接口与标注口径")

    def test_未入选方解锁后不再看到秘密材料(self):
        self.coop_to_dd("coop-1", "ach-1", "team-hk")
        self.coop_to_dd("coop-2", "ach-2", "team-hk2")
        self.assertEqual(
            d.requirement_view(self.store, "req-1", "team-hk2", now=T0)["可见级别"], "全文"
        )
        terms = d.AgreementTerms(50, 5, {}, [("term-1", d.Node.RESEARCH, 1_000_000)], [])
        d.sign_agreement(self.store, "coop-1", "林主任", "陈博士", terms, now=T0)
        coop2 = self.store.cooperations["coop-2"]
        self.assertEqual(coop2.status, d.CoopStatus.UNLOCKED)
        self.assertEqual(coop2.close_reason, "未入选")
        view = d.requirement_view(self.store, "req-1", "team-hk2", now=T0)
        self.assertEqual(view["可见级别"], "脱敏摘要")
        self.assertNotIn("秘密细节", view)

    def test_成果秘密同样受保密协议保护(self):
        self.assertEqual(
            d.achievement_view(self.store, "ach-1", "hospital", now=T0)["可见级别"], "脱敏摘要"
        )
        self.coop_to_dd("coop-1", "ach-1", "team-hk")
        self.assertEqual(
            d.achievement_view(self.store, "ach-1", "hospital", now=T0)["可见级别"], "全文"
        )

    def test_摘要不得夹带未脱敏内容(self):
        with self.assertRaises(ValueError):
            d.publish_requirement(
                self.store,
                d.Requirement(
                    req_id="req-2",
                    owner_org="hospital",
                    title="未脱敏需求",
                    summary="直接引用患者队列X的影像数据接口与标注口径",
                    secret_detail="患者队列X的影像数据接口与标注口径",
                    needs=set(),
                ),
            )


class MatchTest(DomainTestBase):
    def test_匹配分数仅建议接洽而不自动签约(self):
        recs = self.recommend()
        self.assertEqual([r.ach_id for r in recs], ["ach-1", "ach-2", "ach-3"])
        self.assertEqual([r.score for r in recs], [100, 50, 0])
        self.assertTrue(all(r.advisory_only for r in recs))
        self.assertEqual(self.store.cooperations, {})
        top = recs[0]
        self.assertEqual(top.evidence["命中能力"], ["影像识别", "隐私计算"])
        self.assertEqual(top.evidence["未覆盖需求"], [])
        self.assertEqual(top.evidence["临床支持"], ["clinic"])
        self.assertEqual(top.evidence["可选资金条件"][0]["资金方"], "fund")
        self.assertIsNone(top.evidence["权利占用提示"])
        self.assertEqual(recs[1].evidence["未覆盖需求"], ["隐私计算"])

    def test_合作单必须基于推荐显式创建(self):
        with self.assertRaises(ValueError):
            d.initiate_cooperation(self.store, "coop-x", "rec-不存在", now=T0)
        coop = self.coop_to_contact("coop-1", "ach-1")
        self.assertEqual(coop.status, d.CoopStatus.CONTACT)
        self.assertEqual(coop.recommendation_id, "rec-req-1-ach-1")
        with self.assertRaises(ValueError):
            self.coop_to_contact("coop-2", "ach-1")

    def test_推荐证据提示权利占用(self):
        self.coop_to_dd("coop-1", "ach-1", "team-hk")
        d.grant_exclusivity(
            self.store, "g-1", "coop-1", "ip-1", "林主任", "陈博士", T0, T0 + 30 * DAY, now=T0
        )
        top = next(r for r in self.recommend() if r.ach_id == "ach-1")
        self.assertEqual(top.evidence["权利占用提示"], "该成果存在生效中的排他权")


class DueDiligenceTest(DomainTestBase):
    def test_保密协议未生效不得进入尽调(self):
        self.coop_to_contact("coop-1", "ach-1")
        with self.assertRaises(ValueError):
            d.enter_due_diligence(self.store, "coop-1", "v1", {"hospital": [], "team-hk": []}, now=T0)
        d.sign_nda(self.store, "coop-1", "nda-1", effective_at=T0 + DAY, now=T0)
        with self.assertRaises(ValueError):
            d.enter_due_diligence(self.store, "coop-1", "v1", {"hospital": [], "team-hk": []}, now=T0)

    def test_尽调锁定材料版本并登记利益冲突(self):
        self.coop_to_contact("coop-1", "ach-1")
        d.sign_nda(self.store, "coop-1", "nda-1", effective_at=T0, now=T0)
        d.enter_due_diligence(
            self.store, "coop-1", "v1", {"hospital": ["持有竞品股份"], "team-hk": []}, now=T0
        )
        coop = self.store.cooperations["coop-1"]
        self.assertEqual(coop.status, d.CoopStatus.DUE_DILIGENCE)
        self.assertEqual(coop.locked_version_id, "v1")
        self.assertEqual(coop.coi["hospital"], ["持有竞品股份"])
        d.publish_material_version(self.store, "v2", "req-1", "digest-v2", now=T0 + DAY)
        self.assertEqual(coop.locked_version_id, "v1")

    def test_尽调需双方登记利益冲突(self):
        self.coop_to_contact("coop-1", "ach-1")
        d.sign_nda(self.store, "coop-1", "nda-1", effective_at=T0, now=T0)
        with self.assertRaises(ValueError):
            d.enter_due_diligence(self.store, "coop-1", "v1", {"hospital": []}, now=T0)

    def test_锁定版本必须属于该需求(self):
        d.publish_requirement(
            self.store,
            d.Requirement("req-2", "hospital", "另一需求", "另一摘要", "另一秘密", {"影像识别"}),
        )
        d.publish_material_version(self.store, "v9", "req-2", "digest-v9", now=T0)
        self.coop_to_contact("coop-1", "ach-1")
        d.sign_nda(self.store, "coop-1", "nda-1", effective_at=T0, now=T0)
        with self.assertRaises(ValueError):
            d.enter_due_diligence(self.store, "coop-1", "v9", {"hospital": [], "team-hk": []}, now=T0)


class ExclusivityTest(DomainTestBase):
    def test_排他权需双方有权代表签署(self):
        self.coop_to_dd("coop-1", "ach-1", "team-hk")
        with self.assertRaises(ValueError):
            d.grant_exclusivity(
                self.store, "g-1", "coop-1", "ip-1", "路人甲", "陈博士", T0, T0 + 30 * DAY, now=T0
            )
        with self.assertRaises(ValueError):
            d.grant_exclusivity(
                self.store, "g-1", "coop-1", "ip-1", "林主任", "路人乙", T0, T0 + 30 * DAY, now=T0
            )
        grant = d.grant_exclusivity(
            self.store, "g-1", "coop-1", "ip-1", "林主任", "陈博士", T0, T0 + 30 * DAY, now=T0
        )
        self.assertTrue(grant.is_active(T0))
        self.assertEqual(grant.holder_org, "hospital")

    def test_同一成果不得向多方重复承诺排他权(self):
        self.coop_to_dd("coop-1", "ach-1", "team-hk")
        d.grant_exclusivity(
            self.store, "g-1", "coop-1", "ip-1", "林主任", "陈博士", T0, T0 + 30 * DAY, now=T0
        )
        # 第二个需求也看上同一成果
        d.publish_requirement(
            self.store,
            d.Requirement("req-2", "hospital", "另一项影像需求", "另一摘要", "另一秘密", {"影像识别"}),
        )
        d.publish_material_version(self.store, "v2", "req-2", "digest-v2", now=T0)
        rec = next(r for r in d.recommend(self.store, "req-2", now=T0) if r.ach_id == "ach-1")
        d.initiate_cooperation(self.store, "coop-2", rec.rec_id, now=T0)
        d.sign_nda(self.store, "coop-2", "nda-2", effective_at=T0, now=T0)
        d.enter_due_diligence(self.store, "coop-2", "v2", {"hospital": [], "team-hk": []}, now=T0)
        with self.assertRaises(ValueError):
            d.grant_exclusivity(
                self.store, "g-2", "coop-2", "ip-1", "林主任", "陈博士",
                T0 + DAY, T0 + 20 * DAY, now=T0,
            )
        # 原排他期结束后可以衔接承诺
        grant = d.grant_exclusivity(
            self.store, "g-2", "coop-2", "ip-1", "林主任", "陈博士",
            T0 + 30 * DAY, T0 + 60 * DAY, now=T0,
        )
        self.assertFalse(grant.is_active(T0 + 29 * DAY))
        self.assertTrue(grant.is_active(T0 + 30 * DAY))

    def test_排他期到期自动失效(self):
        self.coop_to_dd("coop-1", "ach-1", "team-hk")
        grant = d.grant_exclusivity(
            self.store, "g-1", "coop-1", "ip-1", "林主任", "陈博士", T0, T0 + 30 * DAY, now=T0
        )
        self.assertTrue(grant.is_active(T0 + 29 * DAY))
        self.assertFalse(grant.is_active(T0 + 30 * DAY))
        expired = d.expire_grants(self.store, now=T0 + 30 * DAY)
        self.assertEqual([g.grant_id for g in expired], ["g-1"])
        self.assertTrue(grant.released)
        self.assertEqual(grant.release_reason, "到期自动失效")
        brief = d.supervisor_briefing(self.store, "req-1", now=T0 + 30 * DAY)
        self.assertEqual(brief["当前权利占用"], [])


class AgreementTest(DomainTestBase):
    def test_签约需双方有权代表(self):
        self.coop_to_dd("coop-1", "ach-1", "team-hk")
        terms = d.AgreementTerms(50, 5, {}, [], [])
        with self.assertRaises(ValueError):
            d.sign_agreement(self.store, "coop-1", "路人", "陈博士", terms, now=T0)
        with self.assertRaises(ValueError):
            d.sign_agreement(self.store, "coop-1", "林主任", "路人", terms, now=T0)

    def test_签约后需求进入履约且其他接洽按未入选解锁(self):
        self.coop_to_dd("coop-1", "ach-1", "team-hk")
        self.coop_to_dd("coop-2", "ach-2", "team-hk2")
        terms = d.AgreementTerms(50, 5, {}, [("term-1", d.Node.RESEARCH, 1_000_000)], [])
        d.sign_agreement(self.store, "coop-1", "林主任", "陈博士", terms, now=T0)
        self.assertEqual(self.store.requirements["req-1"].status, d.REQ_PERFORMING)
        coop2 = self.store.cooperations["coop-2"]
        self.assertEqual(coop2.status, d.CoopStatus.UNLOCKED)
        self.assertEqual(coop2.close_reason, "未入选")

    def test_资金计划不得超出资金条件额度(self):
        self.coop_to_dd("coop-1", "ach-1", "team-hk")
        terms = d.AgreementTerms(50, 5, {}, [("term-1", d.Node.RESEARCH, 6_000_000)], [])
        with self.assertRaises(ValueError):
            d.sign_agreement(self.store, "coop-1", "林主任", "陈博士", terms, now=T0)


class MilestoneTest(DomainTestBase):
    def test_节点依次推进并在拨款后完成(self):
        coop = self.coop_to_performing()
        self.assertEqual(
            [m.state for m in coop.milestones],
            [d.NodeState.ACTIVE] + [d.NodeState.PENDING] * 4,
        )
        for i, node in enumerate(d.NODE_ORDER):
            self.assertEqual(coop.milestones[i].node, node)
            if i < len(d.NODE_ORDER) - 1:
                d.advance_milestone(self.store, "coop-1", now=T0 + i * DAY)
                self.assertEqual(coop.milestones[i + 1].state, d.NodeState.ACTIVE)
        d.advance_milestone(self.store, "coop-1", now=T0 + 5 * DAY)
        self.assertEqual(coop.status, d.CoopStatus.UNLOCKED)
        self.assertEqual(coop.close_reason, "履约完成")
        with self.assertRaises(ValueError):
            d.advance_milestone(self.store, "coop-1", now=T0 + 6 * DAY)

    def test_节点失败按约定解锁权利并退款(self):
        coop = self.coop_to_performing()
        grant = d.grant_exclusivity(
            self.store, "g-1", "coop-1", "ip-1", "林主任", "陈博士", T0, T0 + 90 * DAY, now=T0
        )
        d.disburse(self.store, "coop-1", "coop-1-tr-1", now=T0)
        d.disburse(self.store, "coop-1", "coop-1-tr-2", now=T0)
        d.advance_milestone(self.store, "coop-1", now=T0 + DAY)
        tr1, tr2, tr3 = coop.tranches
        self.assertEqual(tr1.status, d.TR_CONFIRMED)
        d.fail_milestone(self.store, "coop-1", reason="伦理审查未通过", now=T0 + 2 * DAY)
        self.assertEqual(coop.status, d.CoopStatus.UNLOCKED)
        self.assertEqual(coop.close_reason, "伦理审查未通过")
        self.assertEqual(coop.milestones[1].state, d.NodeState.FAILED)
        self.assertTrue(grant.released)
        self.assertEqual(tr1.status, d.TR_CONFIRMED)  # 已确认部分保留
        self.assertEqual(tr2.status, d.TR_REFUNDING)
        self.assertEqual(tr2.refund_due, 1_000_000)  # 200万 × 50%
        self.assertEqual(tr3.status, d.TR_CANCELLED)
        self.assertEqual(self.store.requirements["req-1"].status, d.REQ_UNLOCKED)
        d.record_refund(self.store, "coop-1", "coop-1-tr-2", now=T0 + 3 * DAY)
        self.assertEqual(tr2.status, d.TR_REFUNDED)

    def test_节点延期超过宽限期按约定解锁(self):
        coop = self.coop_to_performing()
        d.disburse(self.store, "coop-1", "coop-1-tr-1", now=T0)
        self.assertFalse(d.check_delay(self.store, "coop-1", now=T0 + 15 * DAY))
        self.assertTrue(d.check_delay(self.store, "coop-1", now=T0 + 16 * DAY))
        self.assertEqual(coop.milestones[0].state, d.NodeState.DELAYED)
        self.assertEqual(coop.status, d.CoopStatus.UNLOCKED)
        self.assertEqual(coop.close_reason, "延期解锁")
        self.assertEqual(coop.tranches[0].status, d.TR_REFUNDING)
        self.assertEqual(coop.tranches[0].refund_due, 500_000)  # 100万 × 50%


class FundingExitTest(DomainTestBase):
    def test_资金方中途退出的处理(self):
        coop = self.coop_to_performing()
        d.disburse(self.store, "coop-1", "coop-1-tr-1", now=T0)
        d.disburse(self.store, "coop-1", "coop-1-tr-2", now=T0)
        d.advance_milestone(self.store, "coop-1", now=T0 + DAY)
        d.withdraw_funder(self.store, "coop-1", "fund", now=T0 + 2 * DAY)
        tr1, tr2, tr3 = coop.tranches
        self.assertEqual(tr1.status, d.TR_CONFIRMED)  # 已确认成果对应的资金保留
        self.assertEqual(tr2.status, d.TR_REFUNDING)
        self.assertEqual(tr2.refund_due, 1_000_000)
        self.assertEqual(tr3.status, d.TR_CANCELLED)
        self.assertTrue(coop.funding_gap)
        with self.assertRaises(ValueError):
            d.withdraw_funder(self.store, "coop-1", "clinic", now=T0)


class SupervisorBriefingTest(DomainTestBase):
    def test_主管说明涵盖推荐证据权利占用待办与资金成果(self):
        self.recommend()
        coop = self.coop_to_performing()
        d.grant_exclusivity(
            self.store, "g-1", "coop-1", "ip-1", "林主任", "陈博士", T0, T0 + 90 * DAY, now=T0
        )
        d.disburse(self.store, "coop-1", "coop-1-tr-1", now=T0)
        d.disburse(self.store, "coop-1", "coop-1-tr-2", now=T0)
        d.advance_milestone(self.store, "coop-1", now=T0 + DAY)
        d.withdraw_funder(self.store, "coop-1", "fund", now=T0 + 2 * DAY)

        brief = d.supervisor_briefing(self.store, "req-1", now=T0 + 2 * DAY)
        json.dumps(brief, ensure_ascii=False)  # 视图必须可序列化

        self.assertEqual(len(brief["推荐证据"]), 3)
        self.assertEqual(brief["推荐证据"][0]["成果"], "ach-1")
        self.assertEqual(brief["推荐证据"][0]["分数"], 100)
        self.assertEqual(brief["推荐证据"][0]["性质"], "建议接洽，不构成签约")

        self.assertEqual(len(brief["当前权利占用"]), 1)
        occupation = brief["当前权利占用"][0]
        self.assertEqual(occupation["持有方"], "hospital")
        self.assertEqual(occupation["知识产权边界"], "ip-1")
        self.assertEqual(occupation["合作单"], "coop-1")

        matters = [t["事项"] for t in brief["跨组织待办"]]
        self.assertIn("待通过节点：伦理审查", matters)
        self.assertIn("待退款 1000000", matters)
        self.assertIn("资金缺口待补齐", matters)
        owners = {t["事项"]: t["责任组织"] for t in brief["跨组织待办"]}
        self.assertEqual(owners["待通过节点：伦理审查"], "team-hk")
        self.assertEqual(owners["待退款 1000000"], "fund")

        rows = {r["拨款"]: r for r in brief["资金对应成果"]}
        self.assertEqual(rows["coop-1-tr-1"]["状态"], "已确认")
        self.assertTrue(rows["coop-1-tr-1"]["已确认"])
        self.assertEqual(rows["coop-1-tr-1"]["成果"], "ach-1")
        self.assertEqual(rows["coop-1-tr-2"]["待退款"], 1_000_000)
        self.assertEqual(rows["coop-1-tr-3"]["状态"], "已取消")

        self.assertEqual({d_["地区"] for d_ in brief["地域转化责任"]}, {"福建", "香港"})


if __name__ == "__main__":
    unittest.main()
