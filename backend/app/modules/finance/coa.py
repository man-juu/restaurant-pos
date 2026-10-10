"""Chart of accounts template for an Indonesian food-and-beverage business (FR-FIN-002).
Codes follow the common 1 assets, 2 liabilities, 3 equity, 4 revenue, 5 cost of sales,
6 operating expense layout. Names in Indonesian and English; the tenant's language picks.
Every account stays editable; `system_key` marks the ones automatic journals use (3d).
Have an accountant review it before the first real close (Gate 3)."""

from typing import NamedTuple


class Row(NamedTuple):
    code: str
    id_name: str
    en_name: str
    type: str
    key: str | None = None


ID_FNB: tuple[Row, ...] = (
    Row("1-1100", "Kas", "Cash on hand", "asset", "cash"),
    Row("1-1200", "Bank", "Bank", "asset", "bank"),
    Row("1-1300", "Piutang usaha", "Accounts receivable", "asset", "receivable"),
    Row(
        "1-1310",
        "Piutang platform pesan antar",
        "Delivery platform receivable",
        "asset",
        "platform_receivable",
    ),
    Row(
        "1-1320",
        "Piutang EDC dan QRIS",
        "Card and QRIS settlements receivable",
        "asset",
        "card_receivable",
    ),
    Row("1-1400", "Persediaan bahan", "Inventory", "asset", "inventory"),
    Row(
        "1-1410",
        "Persediaan dalam perjalanan",
        "Inventory in transit",
        "asset",
        "inventory_transit",
    ),
    Row(
        "1-1500",
        "Pajak dibayar di muka (PPN masukan)",
        "Prepaid tax (input VAT)",
        "asset",
        "input_tax",
    ),
    Row("1-1600", "Uang muka dan sewa dibayar di muka", "Prepayments", "asset"),
    Row("1-2100", "Peralatan dapur dan restoran", "Kitchen and restaurant equipment", "asset"),
    Row("1-2190", "Akumulasi penyusutan peralatan", "Accumulated depreciation", "asset"),
    Row("2-1100", "Utang usaha", "Accounts payable", "liability", "payable"),
    Row(
        "2-1200",
        "Utang pajak restoran (PB1/PBJT)",
        "Restaurant tax payable (PB1/PBJT)",
        "liability",
        "tax_payable",
    ),
    Row("2-1210", "PPN keluaran", "Output VAT", "liability", "output_tax"),
    Row("2-1300", "Utang tip karyawan", "Tips payable to staff", "liability", "tips_payable"),
    Row("2-1400", "Utang gaji", "Wages payable", "liability"),
    Row("2-1500", "Uang muka pelanggan", "Customer deposits", "liability"),
    Row("3-1000", "Modal pemilik", "Owner's capital", "equity"),
    Row("3-1100", "Prive", "Owner's drawings", "equity"),
    Row("3-2000", "Laba ditahan", "Retained earnings", "equity", "retained_earnings"),
    Row("3-9000", "Ekuitas saldo awal", "Opening balance equity", "equity", "opening_equity"),
    Row("4-1000", "Penjualan makanan dan minuman", "Food and beverage sales", "revenue", "sales"),
    Row(
        "4-1100", "Pendapatan service charge", "Service charge income", "revenue", "service_charge"
    ),
    Row("4-1200", "Diskon penjualan", "Sales discounts", "revenue", "discounts"),
    Row("4-1300", "Penjualan grosir", "Wholesale sales", "revenue", "wholesale_sales"),
    Row("4-1900", "Selisih pembulatan", "Rounding differences", "revenue", "rounding"),
    Row("4-9000", "Pendapatan lain-lain", "Other income", "revenue"),
    Row("5-1000", "Harga pokok penjualan (HPP)", "Cost of goods sold", "expense", "cogs"),
    Row("5-1100", "Bahan terbuang (waste)", "Waste and spoilage", "expense", "waste"),
    Row("5-1200", "Selisih stok", "Inventory variance", "expense", "inventory_variance"),
    Row("6-1000", "Beban gaji dan upah", "Salaries and wages", "expense"),
    Row("6-1100", "Beban sewa", "Rent", "expense"),
    Row("6-1200", "Listrik, air dan gas", "Utilities and gas", "expense"),
    Row(
        "6-1300",
        "Komisi platform pesan antar",
        "Delivery platform commission",
        "expense",
        "platform_commission",
    ),
    Row("6-1400", "Biaya bank dan MDR", "Bank charges and MDR", "expense", "bank_charges"),
    Row("6-1500", "Perlengkapan dan kemasan", "Supplies and packaging", "expense"),
    Row("6-1600", "Pemasaran", "Marketing", "expense"),
    Row("6-1700", "Perbaikan dan pemeliharaan", "Repairs and maintenance", "expense"),
    Row("6-1800", "Beban penyusutan", "Depreciation", "expense"),
    Row("6-1900", "Beban lain-lain", "Other expenses", "expense", "other_expense"),
)

TEMPLATES = {"id_fnb": ID_FNB}
