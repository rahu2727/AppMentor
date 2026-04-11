"""
week2/sources/forum_ingester.py — 20 curated ERPNext Q&A seed pairs.

Each pair covers a different ERPNext module so the knowledge base has
broad initial coverage. IDs are deterministic (SHA-256 of the text)
so re-running is idempotent.

Public API:
    pairs  = get_pairs()                 # list of (question, answer, metadata)
    docs, metas, ids = get_documents()   # ready to pass to ChromaStore.add()
"""

import hashlib

# ---------------------------------------------------------------------------
# 20 curated ERPNext Q&A pairs
# format: (question, answer, module_tag)
# ---------------------------------------------------------------------------

_RAW_PAIRS: list[tuple[str, str, str]] = [
    # ── HR ──────────────────────────────────────────────────────────────────
    (
        "How do I create a new Employee in ERPNext?",
        "Go to HR > Employee > New Employee. Fill in the mandatory fields: "
        "Employee Name, Company, Date of Joining, and Department. Save the "
        "record. You can then add personal details, salary information, and "
        "upload documents from the same form.",
        "hr",
    ),
    (
        "How do I mark attendance in bulk in ERPNext?",
        "Use HR > Attendance > Upload Attendance to import a CSV file with "
        "columns Employee, Attendance Date, and Status (Present/Absent/Half Day). "
        "Alternatively, HR > Attendance > Mark Attendance allows you to mark "
        "multiple employees for a single date via a dialog box.",
        "hr",
    ),
    (
        "How do I apply for leave in ERPNext?",
        "Employees can apply via HR > Leaves > Leave Application > New. "
        "Select Leave Type, From Date, To Date, and add a Reason. Submit the "
        "application. A notification is sent to the Leave Approver set in the "
        "Employee master. The leave balance updates automatically on approval.",
        "hr",
    ),
    # ── Expense Claims ───────────────────────────────────────────────────────
    (
        "How do I submit an expense claim in ERPNext?",
        "Go to HR > Expenses > Expense Claim > New. Select the Employee and "
        "Expense Approver. Add expense lines with Expense Date, Expense Type, "
        "Description, and Amount. Attach receipts, then click Submit. The "
        "approver receives an email notification to review and approve.",
        "expense",
    ),
    (
        "How do I reimburse an approved expense claim in ERPNext?",
        "After an Expense Claim is approved, go to Accounts > Accounts Payable > "
        "Payment Entry > New. Set Payment Type to 'Pay', Party Type to 'Employee', "
        "and select the employee. The system will show outstanding expense claims "
        "to be settled. Select the relevant claim and submit the payment.",
        "expense",
    ),
    # ── Payroll ──────────────────────────────────────────────────────────────
    (
        "How do I run payroll for a month in ERPNext?",
        "Navigate to Payroll > Payroll Entry > New. Set Company, Payroll "
        "Frequency, Start Date, and End Date. Click 'Get Employees' to load "
        "eligible staff. Review the list, then click 'Create Salary Slips'. "
        "Once all slips are validated, click 'Submit Salary Slips' and then "
        "'Make Bank Entry' to post the accounting entries.",
        "payroll",
    ),
    (
        "How do I set up a salary structure in ERPNext?",
        "Go to Payroll > Salary Structure > New. Add a name and set the "
        "payment frequency. In the Earnings table add components like Basic, "
        "HRA, etc. In the Deductions table add PF, tax, etc. Each component "
        "can use a formula (e.g. base * 0.4 for 40% HRA). Save and submit, "
        "then assign it to employees via Salary Structure Assignment.",
        "payroll",
    ),
    # ── Buying ───────────────────────────────────────────────────────────────
    (
        "How do I create a Purchase Order in ERPNext?",
        "Go to Buying > Purchase Order > New. Select Supplier and set the "
        "Required By date. Add items in the Items table with quantity and "
        "rate. Check taxes in the Taxes and Charges section. Save and Submit. "
        "You can link it to a Purchase Receipt and then a Purchase Invoice "
        "as goods arrive and invoices come in.",
        "buying",
    ),
    (
        "How do I create a Request for Quotation (RFQ) in ERPNext?",
        "Go to Buying > Request for Quotation > New. Add items and quantities, "
        "then add one or more suppliers in the Suppliers table. Submit the RFQ "
        "and click 'Send Emails' to notify suppliers. Suppliers can respond via "
        "the Supplier Portal. Once responses are in, use 'Select Supplier' on "
        "each item to build a Purchase Order.",
        "buying",
    ),
    # ── Projects ─────────────────────────────────────────────────────────────
    (
        "How do I create a project and track tasks in ERPNext?",
        "Go to Projects > Project > New. Enter Project Name, Expected Start "
        "Date, and Expected End Date. Set a Customer if it's a billable project. "
        "In the Tasks section add task rows or open the Gantt view. Assign each "
        "task to an employee and set priority and status. Time logs can be added "
        "against tasks to track actual hours.",
        "projects",
    ),
    (
        "How do I log time against a project task in ERPNext?",
        "Go to Projects > Timesheets > New Timesheet. Select the Employee. "
        "In the Time Logs table add a row: set Activity Type, From Time, To "
        "Time, Project, and Task. Save and Submit. The logged hours appear in "
        "the project's Actual Time field and can be used to generate a Sales "
        "Invoice for billable projects.",
        "projects",
    ),
    # ── Stock ────────────────────────────────────────────────────────────────
    (
        "How do I do a stock reconciliation in ERPNext?",
        "Go to Stock > Tools > Stock Reconciliation > New. Set Purpose to "
        "'Stock Reconciliation'. Add items with their Warehouse, Qty, and "
        "Valuation Rate. The system calculates the difference from book stock. "
        "Submit to post the adjustment. A Stock Ledger Entry is created for "
        "the difference, and P&L is affected if values differ.",
        "stock",
    ),
    (
        "How do I transfer stock between warehouses in ERPNext?",
        "Go to Stock > Stock Transactions > Stock Entry > New. Set Purpose to "
        "'Material Transfer'. Add items with Source Warehouse and Target "
        "Warehouse. Enter quantity. Save and Submit. The stock ledger is updated "
        "immediately. You can also use the 'Material Transfer (Return)' purpose "
        "to reverse a transfer.",
        "stock",
    ),
    (
        "How do I set the reorder level for an item in ERPNext?",
        "Open the Item master (Stock > Items > select item). Scroll to the "
        "'Auto Reorder' section and enable 'Reorder'. Set the Reorder Level "
        "and Reorder Qty. When stock in the selected warehouse falls below the "
        "Reorder Level, ERPNext's scheduler creates a Material Request "
        "automatically.",
        "stock",
    ),
    # ── Accounts ─────────────────────────────────────────────────────────────
    (
        "How do I reconcile a bank account in ERPNext?",
        "Go to Accounts > Banking and Payments > Bank Reconciliation Statement. "
        "Select the Bank Account and date range. Upload the bank statement CSV "
        "or match entries manually. For each bank transaction click 'Match' to "
        "link it to an existing Payment Entry or Journal Entry. Unmatched "
        "items indicate missing entries that need to be created.",
        "accounts",
    ),
    (
        "How do I create a Journal Entry in ERPNext?",
        "Go to Accounts > General Ledger > Journal Entry > New. Set Posting "
        "Date and Entry Type (e.g. Journal Entry). In the Accounting Entries "
        "table add debit and credit rows ensuring they balance to zero. Each "
        "row requires an Account and Amount in Company Currency. Add a Remark "
        "for audit trail. Save and Submit.",
        "accounts",
    ),
    (
        "How does ERPNext handle GST in Sales Invoices?",
        "ERPNext has a built-in India GST module. In the Sales Invoice, set "
        "the Customer's GSTIN and the Company's GSTIN. The HSN/SAC code on "
        "each item drives the applicable GST rate. Tax templates (CGST+SGST "
        "for intra-state, IGST for inter-state) are applied automatically based "
        "on shipping address. GSTR-1 and GSTR-3B reports are generated under "
        "Accounts > GST India.",
        "accounts",
    ),
    # ── System / Setup ───────────────────────────────────────────────────────
    (
        "How do I create a custom field in ERPNext without coding?",
        "Go to Setup > Customize > Customize Form. Select the DocType you want "
        "to modify (e.g. 'Sales Invoice'). Click 'Add Row' in the Fields table. "
        "Set Label, Field Type (Data, Select, Link, etc.), and optionally set "
        "Insert After to control position. Save. The field appears immediately "
        "without a system restart. Use Field Name for API access.",
        "system",
    ),
    (
        "How do I set up email notifications for document submissions in ERPNext?",
        "Go to Setup > Email > Notification > New. Set Document Type and Event "
        "(e.g. 'On Submit'). Add conditions if needed (e.g. status == 'Submitted'). "
        "In Recipients add email addresses or use a field like "
        "'{doc.email_id}'. Write the Subject and Message using Jinja2 "
        "templating ({{ doc.field_name }}). Save and Enable.",
        "system",
    ),
    (
        "How do I reset a user's password in ERPNext?",
        "As Administrator go to Setup > Users > select the User. Click "
        "'Send Password Reset Email' to send a self-service reset link. "
        "Alternatively, type a new password directly in the 'New Password' "
        "field and click Save. For System Manager access lost, use the "
        "bench command: bench --site <site-name> set-admin-password <new-password>.",
        "system",
    ),
]


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def _make_id(text: str) -> str:
    """Return a deterministic 16-char hex ID derived from the text content."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def get_pairs() -> list[tuple[str, str, dict]]:
    """
    Return all Q&A pairs as (question_text, answer_text, metadata_dict).

    The combined question+answer is stored as the document so semantic
    search can match on either the question or the answer.
    """
    pairs = []
    for q, a, module in _RAW_PAIRS:
        pairs.append((q, a, {"source": "forum", "module": module, "question": q}))
    return pairs


def get_documents() -> tuple[list[str], list[dict], list[str]]:
    """
    Return (documents, metadatas, ids) ready for ChromaStore.add().

    The document text is 'Q: <question>\\nA: <answer>' so the embedding
    captures both the intent and the answer.
    """
    documents, metadatas, ids = [], [], []
    for q, a, meta in get_pairs():
        doc_text = f"Q: {q}\nA: {a}"
        documents.append(doc_text)
        metadatas.append(meta)
        ids.append(_make_id(doc_text))
    return documents, metadatas, ids
