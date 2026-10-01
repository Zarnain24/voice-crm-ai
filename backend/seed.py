"""Reset the database and load demo data.  Usage:  python seed.py

Demo scenario: a sales team selling CIS Infinity, a utility billing and customer
information system, to water, electric and gas utilities.
"""

from datetime import timedelta

from app.database import Base, SessionLocal, engine
from app.models import Activity, Contact, Opportunity, Source, Stage, Task, TaskKind
from app.services.common import today

# (name, job title, company, email, phone, deal, value, stage, open task, due in N days, task kind)
# `open task` is None for contacts without one. Negative days = overdue.
DEMO = [
    (
        "John Smith",
        "Billing Manager",
        "Riverside Water District",
        "john.smith@riversidewaterdistrict.com",
        "+1 555 0101",
        "CIS Infinity billing migration",
        85000,
        Stage.NEW,
        # A to-do rather than a follow-up, so moving John to Qualified lets automation add the follow-up
        "Send CIS Infinity migration overview",
        0,
        TaskKind.TODO,
    ),
    (
        "Maria Garcia",
        "Customer Service Lead",
        "Northfield Electric Co-op",
        "maria.garcia@northfieldelectric.coop",
        "+1 555 0102",
        "Customer self-service portal",
        42000,
        Stage.NEW,
        "Book self-service portal demo",
        2,
        TaskKind.FOLLOW_UP,
    ),
    (
        "Robert Johnson",
        "IT Director",
        "Lakeview Gas & Power",
        "robert.johnson@lakeviewgaspower.com",
        "+1 555 0103",
        "Smart meter data integration",
        110000,
        Stage.NEW,
        "Confirm smart meter data formats",
        -1,
        TaskKind.FOLLOW_UP,
    ),
    (
        "Zarnain Khalique",
        "Finance & Analytics Manager",
        "Bluewater Utility Authority",
        "zarnain.khalique@bluewaterutility.org",
        "+1 555 0104",
        "Billing analytics dashboard",
        64000,
        Stage.CONTACTED,
        "Follow up on dashboard requirements",
        0,
        TaskKind.FOLLOW_UP,
    ),
    (
        "Carlos Rivera",
        "Utility Operations Manager",
        "Pine Valley Municipal Utilities",
        "carlos.rivera@pinevalleyutilities.gov",
        "+1 555 0105",
        "Online payment module",
        28000,
        Stage.QUALIFIED,
        "Send payment module pricing",
        -2,
        TaskKind.FOLLOW_UP,
    ),
    (
        "David Chen",
        "Operations Manager",
        "Harbor City Energy",
        "david.chen@harborcityenergy.com",
        "+1 555 0106",
        "Outage notification add-on",
        19000,
        Stage.QUALIFIED,
        "Schedule outage add-on walkthrough",
        1,
        TaskKind.FOLLOW_UP,
    ),
    (
        "Aisha Khan",
        "Public Works Administrator",
        "Cedar Creek Public Works",
        "aisha.khan@cedarcreekpublicworks.gov",
        "+1 555 0107",
        "Work order management",
        36000,
        Stage.PROPOSAL,
        "Review proposal feedback",
        3,
        TaskKind.FOLLOW_UP,
    ),
    (
        "Emily Davis",
        "General Manager",
        "Summit County Utilities",
        "emily.davis@summitcountyutilities.org",
        "+1 555 0108",
        "Full CIS Infinity suite",
        150000,
        Stage.WON,
        None,
        0,
        None,
    ),
]


def main() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    now = today()

    with SessionLocal() as db:
        for name, title, company, email, phone, deal, value, stage, task, due_in, kind in DEMO:
            contact = Contact(name=name, title=title, company=company, email=email, phone=phone)
            opp = Opportunity(contact=contact, title=deal, value=value, stage=stage)
            db.add_all([contact, opp])
            db.flush()
            db.add(Activity(kind="lead_created", message=f"New lead {name}", source=Source.UI, contact_id=contact.id))
            if task:
                db.add(
                    Task(
                        contact=contact,
                        opportunity=opp,
                        title=task,
                        kind=kind,
                        due_date=now + timedelta(days=due_in),
                        source=Source.UI,
                    )
                )
        db.commit()
    print(f"Seeded {len(DEMO)} CIS Infinity deals with contacts and tasks.")


if __name__ == "__main__":
    main()
