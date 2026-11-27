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

import pymupdf

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


def make_pdf(spec: dict) -> Path:
    doc = pymupdf.open()
    total = len(spec["pages"])
    for number, paragraphs in enumerate(spec["pages"], start=1):
        page = doc.new_page(width=595, height=842)  # A4
        page.insert_text((72, 45), spec["header"], fontsize=9, fontname="helv")
        page.insert_text(
            (72, 810),
            f"Page {number} of {total} - Internal use",
            fontsize=9,
            fontname="helv",
        )
        body = "\n\n".join(paragraphs)
        leftover = page.insert_textbox(
            pymupdf.Rect(72, 80, 523, 780), body, fontsize=11, fontname="helv"
        )
        if leftover < 0:
            raise RuntimeError(
                f"Text does not fit on page {number} of {spec['filename']}"
            )
    path = OUT_DIR / spec["filename"]
    doc.save(path)
    doc.close()
    return path


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for spec in DOCUMENTS:
        print("created", make_pdf(spec))


if __name__ == "__main__":
    main()
