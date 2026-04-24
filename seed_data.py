#!/usr/bin/env python3
"""
FinancialOS Kenya — seed_data.py
Populates the database with 47 counties, 3 users, and 4 fiscal years of
realistic CoB + OAG sample data (no real files — processing_status=completed).

Usage:
    python seed_data.py
"""

import json
import random
import sys
from datetime import datetime, timedelta

random.seed(42)   # reproducible

from app import app, db, User, County, Document, FiscalMetric, AuditOpinion

# ---------------------------------------------------------------------------
# Approximate annual budgets (KES millions) — based on public CoB data
# ---------------------------------------------------------------------------
BUDGETS = {
    "Nairobi City":    38_000, "Kiambu":         11_500, "Nakuru":          8_500,
    "Mombasa":          9_000, "Kakamega":         8_000, "Kisumu":          7_500,
    "Uasin Gishu":      7_000, "Bungoma":          6_500, "Machakos":        6_000,
    "Meru":             5_800, "Kilifi":           5_500, "Trans Nzoia":     5_200,
    "Murang'a":         5_000, "Nyeri":            4_800, "Kajiado":         5_000,
    "Narok":            4_500, "Kisii":            4_500, "Kitui":           4_500,
    "Kericho":          4_500, "Homa Bay":         4_200, "Nandi":           4_200,
    "Siaya":            4_000, "Migori":           4_000, "Makueni":         4_000,
    "Baringo":          3_800, "Embu":             3_800, "Bomet":           3_800,
    "Nyamira":          3_500, "Busia":            3_500, "Kirinyaga":       3_500,
    "Nyandarua":        3_500, "Laikipia":         3_500, "Garissa":         3_500,
    "Mandera":          3_500, "Turkana":          5_000, "Tharaka Nithi":   2_800,
    "Tana River":       2_800, "Taita Taveta":     2_800, "Elgeyo Marakwet": 3_000,
    "Samburu":          2_800, "Wajir":            3_200, "West Pokot":      3_200,
    "Vihiga":           3_200, "Marsabit":         3_000, "Isiolo":          2_500,
    "Lamu":             2_500,
}

# Counties with higher own-source revenue (urban / commercial)
HIGH_OSR = {"Nairobi City", "Mombasa", "Kisumu", "Nakuru", "Kiambu",
            "Uasin Gishu", "Kajiado", "Narok", "Kericho"}

POPULATIONS = {
    "Nairobi City": 4_397_073, "Kiambu": 2_417_735, "Nakuru": 2_162_202,
    "Kakamega": 1_867_579,     "Bungoma": 1_670_570, "Meru": 1_545_714,
    "Kilifi": 1_453_787,       "Machakos": 1_421_932,"Mombasa": 1_208_333,
    "Kisumu": 1_155_574,       "Kisii": 1_266_860,   "Migori": 1_116_436,
    "Siaya": 993_183,          "Murang'a": 1_056_640,"Nyeri": 863_671,
    "Uasin Gishu": 1_163_186,  "Kericho": 972_111,   "Bomet": 875_689,
    "Trans Nzoia": 1_093_432,  "Nandi": 885_711,     "Homa Bay": 1_131_950,
    "Makueni": 987_653,        "Kitui": 1_136_187,   "Turkana": 926_976,
    "Mandera": 867_457,        "Wajir": 781_263,     "Garissa": 841_353,
    "Kajiado": 1_117_840,      "Narok": 1_157_873,   "Laikipia": 518_560,
    "Baringo": 666_763,        "Nyandarua": 638_289, "Nyamira": 605_576,
    "Vihiga": 590_013,         "Busia": 893_681,     "Embu": 608_599,
    "Kirinyaga": 610_411,      "Tharaka Nithi": 393_177,
    "Elgeyo Marakwet": 454_480,"West Pokot": 621_241,"Samburu": 310_327,
    "Isiolo": 268_002,         "Marsabit": 459_785,  "Tana River": 315_943,
    "Taita Taveta": 340_671,   "Lamu": 143_920,      "Kwale": 866_820,
}

FISCAL_YEARS = ["2019/20", "2020/21", "2021/22", "2022/23"]

# Audit opinion weights: unqualified, qualified, adverse, disclaimer
OPINION_WEIGHTS = [0.20, 0.50, 0.20, 0.10]
OPINIONS = ["unqualified", "qualified", "adverse", "disclaimer"]

OBSERVATIONS = {
    "unqualified": [
        "Financial statements present fairly in all material respects.",
        "Adequate internal controls observed in revenue collection processes.",
        "Procurement procedures were largely compliant with the PPDA.",
    ],
    "qualified": [
        "Pending bills of significant value were not adequately disclosed in the financial statements.",
        "Unsupported payments noted in development expenditure lines.",
        "Revenue collection shortfall against approved estimates not explained.",
        "Bank reconciliations for the County Revenue Fund were not presented.",
        "Irregular single-sourcing of suppliers detected in Q3 procurement.",
    ],
    "adverse": [
        "Material misstatements found across multiple financial statement lines.",
        "Unverified expenditures representing a significant portion of total spending.",
        "Irregular procurement practices resulted in loss of public funds.",
        "Payroll irregularities including ghost workers detected.",
        "Development projects reported as complete lacked physical verification evidence.",
        "IFMIS records inconsistent with manual payment vouchers.",
    ],
    "disclaimer": [
        "Auditors were unable to obtain sufficient appropriate audit evidence.",
        "Critical accounting records were not made available for inspection.",
        "Significant scope limitations imposed by county management.",
        "County Revenue Fund cash book missing for key quarters.",
    ],
}


def _rand_obs(opinion_type: str, n: int = 3) -> list:
    pool = OBSERVATIONS[opinion_type]
    return random.sample(pool, min(n, len(pool)))


def seed():
    with app.app_context():
        db.create_all()

        # ------------------------------------------------------------------ #
        # 1. Users
        # ------------------------------------------------------------------ #
        users_spec = [
            ("admin",   "admin@fiscalos.ke",    "admin123",    "admin"),
            ("analyst", "analyst@fiscalos.ke",  "analyst123",  "analyst"),
            ("viewer",  "viewer@fiscalos.ke",   "viewer123",   "viewer"),
        ]
        for username, email, pwd, role in users_spec:
            if not User.query.filter_by(username=username).first():
                u = User(username=username, email=email, role=role)
                u.set_password(pwd)
                db.session.add(u)
        db.session.commit()
        admin = User.query.filter_by(username="admin").first()
        print(f"  ✓ Users ready ({User.query.count()} total)")

        # ------------------------------------------------------------------ #
        # 2. Counties — update population if already seeded
        # ------------------------------------------------------------------ #
        for county in County.query.all():
            if county.name in POPULATIONS:
                county.population = POPULATIONS[county.name]
        db.session.commit()
        print(f"  ✓ Counties ready ({County.query.count()} total)")

        # ------------------------------------------------------------------ #
        # 3. Skip if data already present
        # ------------------------------------------------------------------ #
        if Document.query.count() > 0:
            print("  ℹ  Documents already seeded — skipping. Run with --force to reseed.")
            return

        # ------------------------------------------------------------------ #
        # 4. Documents + metrics + audit opinions
        # ------------------------------------------------------------------ #
        counties = County.query.order_by(County.code).all()
        doc_count = 0
        metric_count = 0
        opinion_count = 0

        for county in counties:
            base_budget = BUDGETS.get(county.name, 3_500)

            for i, fy in enumerate(FISCAL_YEARS):
                year_factor = 1 + 0.06 * i           # ~6% annual budget growth

                # ---------- CoB CBIRR document ----------
                cob_doc = Document(
                    original_filename=(
                        f"CoB_CBIRR_{county.name.replace(' ', '_')}"
                        f"_{fy.replace('/', '_')}_Annual.pdf"
                    ),
                    stored_filename=f"seed_cob_{county.code}_{i}.pdf",
                    filepath=None,
                    source="CoB",
                    fiscal_year=fy,
                    county_id=county.id,
                    county_name=county.name,
                    report_period="annual",
                    document_type="County Budget Implementation Review Report (CBIRR)",
                    page_count=random.randint(45, 120),
                    processing_status="completed",
                    processing_completed_at=datetime.utcnow(),
                    upload_date=datetime.utcnow() - timedelta(days=random.randint(30, 600)),
                    uploaded_by_id=admin.id,
                    file_size=random.randint(800_000, 4_000_000),
                )
                db.session.add(cob_doc)
                db.session.flush()
                doc_count += 1

                # Compute realistic fiscal metrics
                budget     = base_budget * year_factor
                osr_ratio  = (random.uniform(0.15, 0.32)
                              if county.name in HIGH_OSR
                              else random.uniform(0.03, 0.09))
                total_rev  = budget * random.uniform(0.87, 1.03)
                own_src    = total_rev * osr_ratio
                eq_share   = total_rev * random.uniform(0.60, 0.75)
                absorption = random.uniform(0.62, 0.93)
                total_exp  = total_rev * absorption
                dev_ratio  = random.uniform(0.14, 0.32)
                dev_exp    = total_exp * dev_ratio
                rec_exp    = total_exp * (1 - dev_ratio)
                pending    = total_rev * random.uniform(0.03, 0.18)
                staff      = rec_exp  * random.uniform(0.40, 0.58)

                metric_values = {
                    "total_revenue":          total_rev,
                    "own_source_revenue":     own_src,
                    "equitable_share":        eq_share,
                    "total_expenditure":      total_exp,
                    "recurrent_expenditure":  rec_exp,
                    "development_expenditure": dev_exp,
                    "pending_bills":          pending,
                    "staff_costs":            staff,
                }
                for mname, mval in metric_values.items():
                    db.session.add(FiscalMetric(
                        document_id=cob_doc.id,
                        county_id=county.id,
                        fiscal_year=fy,
                        metric_name=mname,
                        metric_value=round(mval, 2),
                        confidence_score=round(random.uniform(0.72, 0.96), 2),
                    ))
                    metric_count += 1

                # ---------- OAG Audit document (70% of county-years) ----------
                if random.random() < 0.70:
                    opinion = random.choices(OPINIONS, weights=OPINION_WEIGHTS)[0]
                    issue_n = {"unqualified": 1, "qualified": 4,
                               "adverse": 9, "disclaimer": 14}[opinion]

                    oag_doc = Document(
                        original_filename=(
                            f"OAG_Audit_{county.name.replace(' ', '_')}"
                            f"_{fy.replace('/', '_')}_CountyExecutive.pdf"
                        ),
                        stored_filename=f"seed_oag_{county.code}_{i}.pdf",
                        filepath=None,
                        source="OAG",
                        fiscal_year=fy,
                        county_id=county.id,
                        county_name=county.name,
                        report_period="annual",
                        document_type="Auditor-General Report – County Executive",
                        page_count=random.randint(30, 90),
                        processing_status="completed",
                        processing_completed_at=datetime.utcnow(),
                        upload_date=datetime.utcnow() - timedelta(days=random.randint(10, 500)),
                        uploaded_by_id=admin.id,
                        file_size=random.randint(600_000, 3_000_000),
                    )
                    db.session.add(oag_doc)
                    db.session.flush()
                    doc_count += 1

                    db.session.add(AuditOpinion(
                        document_id=oag_doc.id,
                        county_id=county.id,
                        fiscal_year=fy,
                        opinion_type=opinion,
                        material_issues=issue_n + random.randint(0, 3),
                        key_observations=json.dumps(_rand_obs(opinion)),
                        pending_bills=round(pending, 2),
                    ))
                    opinion_count += 1

        db.session.commit()
        print(f"  ✓ Documents:      {doc_count}")
        print(f"  ✓ Fiscal metrics: {metric_count}")
        print(f"  ✓ Audit opinions: {opinion_count}")
        print()
        print("  Login credentials:")
        print("    admin    / admin123")
        print("    analyst  / analyst123")
        print("    viewer   / viewer123")


if __name__ == "__main__":
    force = "--force" in sys.argv
    if force:
        with app.app_context():
            AuditOpinion.query.delete()
            FiscalMetric.query.delete()
            Document.query.delete()
            db.session.commit()
            print("  ✓ Cleared existing documents/metrics/opinions")
    print("\nSeeding FinancialOS Kenya database...")
    seed()
    print("\nDone.\n")
