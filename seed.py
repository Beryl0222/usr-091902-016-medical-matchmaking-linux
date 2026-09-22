"""演示数据：一个需求同时匹配多个成果、资金方中途退出的典型场景。

供 `service.py` 启动时加载，便于联调 `/api/brief/<demand_id>` 主管视图。
所有 id 稳定，便于接口对照测试。
"""

from datetime import timedelta

from domain import Platform, utcnow


def build_demo_platform(clock=utcnow):
    p = Platform(clock=clock)
    now = clock()

    # 机构：福建出题方、香港解题方、临床与资金
    p.register_org("ORG-FJ-HOSP", "福建省立医院", "需求机构")
    p.register_org("ORG-HK-LAB", "香港智能诊断实验室", "成果团队")
    p.register_org("ORG-HK-BIO", "香港生物传感团队", "成果团队")
    p.register_org("ORG-FJ-CLIN", "福建医科大学附属协和医院", "临床合作方")
    p.register_org("ORG-FUND-A", "闽港科创基金", "资金方")
    p.register_org("ORG-FUND-B", "海峡创投", "资金方")

    # 需求：脱敏摘要 + 秘密材料本体
    p.publish_demand(
        "DEM-001",
        "院内心衰患者再入院风险预测",
        "ORG-FJ-HOSP",
        "需对心衰出院患者做 30 天再入院风险分层，涉及三甲医院真实世界数据（已脱敏）。",
        secret_brief={
            "data": "2019-2025 年心衰出院 12,430 例，含检验/用药/随访明细",
            "contact": "心内科 王主任（未脱敏联系方式）",
            "site": "福建省立医院 心内科 CCU",
        },
        clinical_need="需心内科队列随访与伦理批件",
        region_responsibility="福建落地转化，香港团队提供算法",
    )

    # 临床资源
    p.register_clinical_resource("CLIN-001", "ORG-FJ-CLIN", "心内科",
                                 "协和医院伦理委员会", "年心衰随访约 2,000 例")

    # 两个候选成果（同一需求匹配多个成果）
    p.register_achievement(
        "ACH-001", "多模态再入院风险模型", "ORG-HK-LAB",
        "融合检验+用药+影像报告的时序模型，AUC 0.87（外部验证）",
        ip_boundary="模型权重授权, 推理服务 SaaS, 不含训练数据",
        secret_detail={"weights": "hf-internal://ckpt/v3", "validation": "n=8,214"},
        clinical_resources=["CLIN-001"],
    )
    p.register_achievement(
        "ACH-002", "可穿戴生物传感预警贴片", "ORG-HK-BIO",
        "胸贴式阻抗传感，居家监测肺淤血趋势",
        ip_boundary="硬件外观专利, 传感算法固件授权",
        secret_detail={"firmware": "v2.1 未公开"},
    )

    # 匹配分数：仅建议接洽
    p.suggest_match("DEM-001", "ACH-001", 0.91,
                    evidence=["真实世界数据规模匹配", "AUC 外部验证达标", "临床资源已对接"])
    p.suggest_match("DEM-001", "ACH-002", 0.64,
                    evidence=["居家场景互补", "缺少院内队列验证"])

    # 与高分团队签 NDA → 尽调（锁版本 + 利益冲突登记）
    p.sign_nda("NDA-001", "DEM-001", "ORG-HK-LAB",
               signed_by={"name": "林主任", "title": "科研处处长"},
               effective_at=now - timedelta(days=20))
    p.open_due_diligence("DD-001", "DEM-001", "ACH-001", material_version="v2026-09-01")
    p.declare_conflict("DD-001", "ORG-HK-LAB", "陈博士", "同时担任基金 A 技术顾问")
    p.close_due_diligence("DD-001", passed=True)

    # 排他期：双方代表签署，90 天自动到期
    p.grant_exclusivity(
        "EXC-001", "DEM-001", "ACH-001",
        scope="推理服务 SaaS",
        duration_days=90,
        signed_by_both={
            "demand_party": {"name": "王主任", "title": "心内科主任"},
            "achievement_party": {"name": "林主任", "title": "科研处处长"},
        },
        starts_at=now - timedelta(days=10),
    )

    # 立项：五节点
    p.start_project("PRJ-001", "DEM-001", "ACH-001",
                    milestone_due_days={"技术攻关": 30, "伦理审查": 60,
                                        "验证": 120, "转化": 180, "拨款": 200})

    # 资金：A 承诺后中途退出，B 仍在
    p.commit_funding("FND-001", "DEM-001", "ACH-001", "ORG-FUND-A",
                     3_000_000, linked_milestone="验证")
    p.commit_funding("FND-002", "DEM-001", "ACH-001", "ORG-FUND-B",
                     1_500_000, linked_milestone="拨款")
    p.withdraw_funding("FND-001", reason="基金内部风控调整")

    return p
