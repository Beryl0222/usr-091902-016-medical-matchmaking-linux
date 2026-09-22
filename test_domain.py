"""领域规则测试：脱敏、尽调、排他、里程碑、资金与主管视图。"""

import unittest
from datetime import timedelta

from domain import (
    DomainError,
    Platform,
    utcnow,
)
from seed import build_demo_platform


class BaseCase(unittest.TestCase):
    def setUp(self):
        self.now = utcnow()
        self.clock = lambda: self.now
        self.p = Platform(clock=self.clock)
        self.p.register_org("HOSP", "福建某医院", "需求机构")
        self.p.register_org("LAB", "香港某实验室", "成果团队")
        self.p.register_org("RIVAL", "另一团队", "成果团队")
        self.p.register_org("FUND", "某基金", "资金方")
        self.p.publish_demand(
            "D1", "影像辅助诊断", "HOSP",
            "需肺结节辅助诊断能力（脱敏摘要）",
            secret_brief={"data": "未脱敏影像 5 万例", "contact": "李医生"},
        )
        self.p.register_achievement(
            "A1", "结节检测模型", "LAB",
            "敏感度 96%", ip_boundary="模型授权, SaaS 服务",
            secret_detail={"weights": "secret"},
        )
        self.p.register_achievement(
            "A2", " competing 方案", "RIVAL",
            "敏感度 93%", ip_boundary="整体授权",
        )

    def sign_and_dd(self, achievement="A1", org="LAB", passed=True):
        self.p.sign_nda("NDA1", "D1", org,
                        signed_by={"name": "张三", "title": "主任"})
        self.p.open_due_diligence("DD1", "D1", achievement, material_version="v1")
        self.p.close_due_diligence("DD1", passed=passed)

    def grant_exclusivity(self, achievement="A1", scope="SaaS 服务", days=30):
        return self.p.grant_exclusivity(
            "EX1", "D1", achievement, scope=scope, duration_days=days,
            signed_by_both={
                "demand_party": {"name": "王五", "title": "院长"},
                "achievement_party": {"name": "赵六", "title": "PI"},
            })


class SecrecyTest(BaseCase):
    def test_secret_hidden_before_nda(self):
        view = self.p.view_demand("D1", "LAB")
        self.assertNotIn("secret_brief", view)
        self.assertIn("脱敏摘要", view["summary"])

    def test_secret_visible_after_nda(self):
        self.p.sign_nda("N1", "D1", "LAB",
                        signed_by={"name": "张三", "title": "主任"})
        view = self.p.view_demand("D1", "LAB")
        self.assertEqual(view["secret_brief"]["data"], "未脱敏影像 5 万例")

    def test_nda_requires_authorized_rep(self):
        with self.assertRaises(DomainError):
            self.p.sign_nda("N1", "D1", "LAB", signed_by={"name": "张三"})

    def test_unselected_never_sees_secret(self):
        self.p.sign_nda("N1", "D1", "LAB",
                        signed_by={"name": "张三", "title": "主任"})
        # 未入选方（从未签 NDA）始终只见摘要
        self.assertNotIn("secret_brief", self.p.view_demand("D1", "RIVAL"))
        # 尽调失败后，原入选方变为未入选方，访问立即关闭
        self.sign_and_dd(passed=False)
        self.assertFalse(self.p.can_access_secret("D1", "LAB"))
        self.assertNotIn("secret_brief", self.p.view_demand("D1", "LAB"))


class MatchTest(BaseCase):
    def test_score_only_suggests(self):
        m = self.p.suggest_match("D1", "A1", 0.9, evidence=["指标命中"])
        self.assertIn("不构成签约", m.view()["note"])

    def test_multiple_matches_coexist(self):
        self.p.suggest_match("D1", "A1", 0.9)
        self.p.suggest_match("D1", "A2", 0.7)
        ranked = self.p.ranked_suggestions("D1")
        self.assertEqual([m.achievement_id for m in ranked], ["A1", "A2"])

    def test_score_range_checked(self):
        with self.assertRaises(DomainError):
            self.p.suggest_match("D1", "A1", 1.5)


class DueDiligenceTest(BaseCase):
    def test_dd_requires_nda(self):
        with self.assertRaises(DomainError):
            self.p.open_due_diligence("DD1", "D1", "A1", material_version="v1")

    def test_dd_locks_material_version(self):
        self.p.sign_nda("N1", "D1", "LAB",
                        signed_by={"name": "张三", "title": "主任"})
        self.p.open_due_diligence("DD1", "D1", "A1", material_version="v2026-09")
        locked = self.p.locked_material("DD1")
        self.assertEqual(locked["material_version"], "v2026-09")
        self.assertTrue(locked["frozen"])

    def test_conflict_registered(self):
        self.p.sign_nda("N1", "D1", "LAB",
                        signed_by={"name": "张三", "title": "主任"})
        self.p.open_due_diligence("DD1", "D1", "A1", material_version="v1")
        self.p.declare_conflict("DD1", "LAB", "陈博士", "持有竞品股权")
        self.assertEqual(len(self.p.locked_material("DD1")["conflicts"]), 1)


class ExclusivityTest(BaseCase):
    def test_exclusivity_requires_dd_passed(self):
        with self.assertRaises(DomainError):
            self.grant_exclusivity()

    def test_exclusivity_requires_two_reps(self):
        self.sign_and_dd()
        with self.assertRaises(DomainError):
            self.p.grant_exclusivity(
                "EX1", "D1", "A1", scope="SaaS 服务", duration_days=30,
                signed_by_both={"demand_party": {"name": "王五", "title": "院长"}})

    def test_exclusivity_within_ip_boundary(self):
        self.sign_and_dd()
        with self.assertRaises(DomainError):
            self.grant_exclusivity(scope="训练数据所有权")

    def test_no_double_grant_same_scope(self):
        self.sign_and_dd()
        self.grant_exclusivity()
        with self.assertRaises(DomainError):
            self.p.grant_exclusivity(
                "EX2", "D1", "A1", scope="SaaS 服务", duration_days=30,
                signed_by_both={
                    "demand_party": {"name": "王五", "title": "院长"},
                    "achievement_party": {"name": "赵六", "title": "PI"},
                })

    def test_exclusivity_auto_expires(self):
        self.sign_and_dd()
        self.grant_exclusivity(days=30)
        self.now += timedelta(days=31)
        expired = self.p.expire_due_exclusivities()
        self.assertEqual(len(expired), 1)
        self.assertEqual(self.p.active_exclusivities("D1"), [])


class MilestoneTest(BaseCase):
    def setUp(self):
        super().setUp()
        self.sign_and_dd()
        self.grant_exclusivity()
        self.p.start_project("P1", "D1", "A1",
                             milestone_due_days={"技术攻关": 10, "伦理审查": 20,
                                                 "验证": 30, "转化": 40, "拨款": 50})

    def test_stages_in_order(self):
        with self.assertRaises(DomainError):
            self.p.decide_milestone("P1", "伦理审查", "通过")
        self.p.decide_milestone("P1", "技术攻关", "通过")
        self.assertEqual(self.p.projects["P1"].current_stage, "伦理审查")

    def test_delay_unlocks_rights_per_agreement(self):
        self.p.decide_milestone("P1", "技术攻关", "延期", note="数据标注滞后")
        notes = self.p.projects["P1"].unlocked_rights
        self.assertTrue(any("延期" in n for n in notes))
        # 延期不解除排他
        self.assertEqual(len(self.p.active_exclusivities("D1")), 1)

    def test_failure_releases_exclusivity_and_refunds(self):
        self.p.commit_funding("F1", "D1", "A1", "FUND", 100.0,
                              linked_milestone="验证")
        self.p.decide_milestone("P1", "技术攻关", "失败", note="指标不达标")
        self.assertEqual(self.p.active_exclusivities("D1"), [])
        self.assertEqual(self.p.demands["D1"].state, "已解锁")
        ledger = self.p.funding_ledger("D1")
        self.assertEqual(ledger[0]["state"], "已退款")
        self.assertEqual(self.p.projects["P1"].refunds_due[0]["amount"], 100.0)


class FundingTest(BaseCase):
    def setUp(self):
        super().setUp()
        self.sign_and_dd()
        self.grant_exclusivity()

    def test_funding_maps_to_confirmed_achievement(self):
        f = self.p.commit_funding("F1", "D1", "A1", "FUND", 100.0,
                                  linked_milestone="拨款")
        self.assertTrue(f.confirmed_achievement)
        ledger = self.p.funding_ledger("D1")
        self.assertEqual(ledger[0]["achievement_id"], "A1")
        self.assertTrue(ledger[0]["achievement_confirmed"])

    def test_withdrawal_releases_and_records(self):
        self.p.commit_funding("F1", "D1", "A1", "FUND", 100.0,
                              linked_milestone="验证")
        self.p.withdraw_funding("F1", reason="风控")
        self.assertEqual(self.p.funding_ledger("D1")[0]["state"], "已退出")
        with self.assertRaises(DomainError):
            self.p.withdraw_funding("F1")


class SupervisorBriefTest(unittest.TestCase):
    """种子场景：一个需求匹配两个成果，基金 A 中途退出。"""

    def setUp(self):
        self.p = build_demo_platform()
        self.brief = self.p.supervisor_brief("DEM-001")

    def test_recommendation_evidence_present(self):
        rec = self.brief["recommendation"]
        self.assertEqual(len(rec["matches"]), 2)
        self.assertGreater(rec["matches"][0]["score"], rec["matches"][1]["score"])
        self.assertTrue(rec["matches"][0]["evidence"])

    def test_rights_occupancy(self):
        rights = self.brief["rights_occupancy"]
        self.assertEqual(len(rights["active_exclusivities"]), 1)
        self.assertEqual(rights["active_exclusivities"][0]["grantee_org_id"], "ORG-HK-LAB")
        self.assertTrue(rights["nda_parties"])

    def test_cross_org_todos_cover_funding_gap(self):
        types = {t["type"] for t in self.brief["cross_org_todos"]}
        self.assertIn("资金缺口", types)
        self.assertIn("里程碑待决", types)
        gap = next(t for t in self.brief["cross_org_todos"] if t["type"] == "资金缺口")
        self.assertEqual(gap["funding_id"], "FND-001")

    def test_funding_ledger_per_fund(self):
        ledger = {row["funding_id"]: row for row in self.brief["funding_ledger"]}
        self.assertEqual(ledger["FND-001"]["state"], "已退出")
        self.assertEqual(ledger["FND-002"]["state"], "已承诺")
        self.assertEqual(ledger["FND-002"]["achievement_id"], "ACH-001")
        self.assertTrue(ledger["FND-002"]["achievement_confirmed"])

    def test_unselected_candidate_has_no_secret_access(self):
        # 未入选的 ACH-002 团队从未签 NDA，不能看秘密材料
        view = self.p.view_demand("DEM-001", "ORG-HK-BIO")
        self.assertNotIn("secret_brief", view)


if __name__ == "__main__":
    unittest.main()
