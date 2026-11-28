# Purpose of this file is to generate the sample PDF documents (current policy, old FAQ, restricted finance manual) for the refund-policy scenario
"""Creates the sample knowledge base in backend/data/sample_documents/.

Run from the backend folder:   python scripts/make_sample_docs.py

The three documents reproduce the worked example in the project blueprint:
* Returns Policy v3.2 (current):   online window is 14 days
* Returns FAQ 2024 (superseded):   still says 30 days
* Finance Operations Manual (restricted): says refunds take 5 business days

Each page has a running header and footer on purpose, so the header/footer
removal in preprocessing.py is exercised.
"""

from pathlib import Path
import json
import textwrap

from reportlab.pdfgen import canvas

OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "sample_documents"

DOCUMENTS = [
    {
        "filename": "returns_policy_v3.2.pdf",
        "header": "Acme Retail - Returns Policy v3.2",
        "pages": [
            [
                "1. Purpose and scope",
                "This policy applies to all products sold through the Acme Retail online store. It sets out when customers "
                "may return items and how returns are handled by customer service staff.",
                "2. Online order returns",
                "2.1 Return window. Online orders may be returned within 14 days of delivery. Requests made after "
                "14 days must be declined unless the item is defective.",
                "2.2 Item condition. Items must be unused and in their original packaging. Opened hygiene products "
                "cannot be returned.",
            ],
            [
                "2.3 Return method. Customers must request a return authorisation number through their account "
                "before posting the item back.",
                "2.4 Shipping fees. Original shipping fees are refunded only when the item is defective or was sent "
                "in error. In all other cases the customer pays the return shipping cost.",
                "2.5 Exchanges. Exchanges for a different size or colour are available within the same 14 day "
                "window, subject to stock.",
            ],
            [
                "3. Exceptions",
                "3.1 Final sale items. Items marked Final Sale cannot be returned or exchanged.",
                "3.2 Gift cards. Gift cards are non-refundable and cannot be exchanged for cash.",
            ],
        ],
    },
    {
        "filename": "returns_faq_2024.pdf",
        "header": "Acme Retail - Returns FAQ 2024",
        "pages": [
            [
                "1. Return window",
                "Customers can return online orders within 30 days of delivery.",
                "2. Shipping fees",
                "Shipping fees are refunded in full for all returns.",
            ],
            [
                "3. Item condition",
                "Items should be unused. Original packaging is helpful but not required.",
                "4. Exchanges",
                "Customers may exchange items for a different size or colour within 30 days of delivery.",
            ],
        ],
    },
    {
        "filename": "finance_operations_manual_v7.pdf",
        "header": "Acme Retail - Finance Operations Manual v7",
        "pages": [
            [
                "1. Scope",
                "This manual describes finance procedures for customer refunds. It is restricted to finance staff "
                "and managers.",
                "2. Refund processing",
                "2.1 Processing time. Approved refunds are processed within 5 business days of the returned item "
                "being received at the warehouse.",
                "2.2 Payment method. Refunds are issued to the original payment method. Cash refunds are not permitted.",
            ],
            [
                "3. Reconciliation",
                "3.1 Daily reconciliation. Finance staff reconcile refund payments against the returns log every "
                "business day.",
                "3.2 Approval limits. Refunds above LKR 50,000 require manager approval.",
            ],
        ],
    },
]

MANIFEST = {
    "documents": [
        {
            "doc_id": "returns-policy",
            "title": "Returns Policy",
            "version": "3.2",
            "effective_date": "2026-01-01",
            "status": "current",
            "allowed_roles": ["customer_service", "manager"],
            "filename": "returns_policy_v3.2.pdf",
        },
        {
            "doc_id": "returns-faq",
            "title": "Returns FAQ 2024",
            "version": "2024",
            "effective_date": "2024-01-01",
            "status": "superseded",
            "allowed_roles": ["customer_service", "manager"],
            "filename": "returns_faq_2024.pdf",
        },
        {
            "doc_id": "finance-ops-manual",
            "title": "Finance Operations Manual",
            "version": "7",
            "effective_date": "2026-01-01",
            "status": "current",
            "allowed_roles": ["finance", "manager"],
            "filename": "finance_operations_manual_v7.pdf",
        },
    ]
}


def make_pdf(spec: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / spec["filename"]
    doc = canvas.Canvas(str(path), pagesize=(595, 842))
    total = len(spec["pages"])
    for number, paragraphs in enumerate(spec["pages"], start=1):
        doc.setFont("Helvetica", 9)
        doc.drawString(72, 797, spec["header"])
        doc.drawString(72, 32, f"Page {number} of {total} - Internal use")
        text = doc.beginText(72, 755)
        text.setFont("Helvetica", 11)
        text.setLeading(15)
        for paragraph in paragraphs:
            for line in textwrap.wrap(paragraph, width=82):
                text.textLine(line)
            text.textLine("")
        doc.drawText(text)
        doc.showPage()
    doc.save()
    return path


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for spec in DOCUMENTS:
        print("created", make_pdf(spec))
    manifest_path = OUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(MANIFEST, indent=2), encoding="utf-8")
    print("created", manifest_path)


if __name__ == "__main__":
    main()
