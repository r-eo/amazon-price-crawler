import io
from datetime import datetime
from typing import Optional
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from app.config import EXPORTS_DIR, CURRENCY_SYMBOL
from app.database import get_all_products, get_price_history_for_asin, get_product_statistics
from app.history_engine import get_22_month_labels

def generate_excel_workbook() -> openpyxl.Workbook:
    """
    Generates a beautifully styled, multi-sheet Excel workbook containing:
    1. Acer_Product_Overview: Product specifications, live prices, discounts, ATL/ATH metrics, with clickable Amazon links.
    2. 22_Months_Price_History: Full monthly matrix across all 22 months with direct Amazon links.
    3. Monthly_Statistics: Category-level and portfolio aggregate metrics over 22 months.
    """
    wb = openpyxl.Workbook()
    
    # Define Brand Styles
    FONT_FAMILY = "Segoe UI"
    
    title_font = Font(name=FONT_FAMILY, size=16, bold=True, color="FFFFFF")
    subtitle_font = Font(name=FONT_FAMILY, size=10, italic=True, color="E2E8F0")
    header_font = Font(name=FONT_FAMILY, size=11, bold=True, color="FFFFFF")
    sub_header_font = Font(name=FONT_FAMILY, size=10, bold=True, color="1E293B")
    data_font = Font(name=FONT_FAMILY, size=10, color="1E293B")
    bold_data_font = Font(name=FONT_FAMILY, size=10, bold=True, color="0F172A")
    link_font = Font(name=FONT_FAMILY, size=10, color="0284C7", underline="single")
    link_bold_font = Font(name=FONT_FAMILY, size=10, bold=True, color="0F4C81", underline="single")
    badge_green_font = Font(name=FONT_FAMILY, size=9, bold=True, color="166534")
    
    header_fill = PatternFill(start_color="0F4C81", end_color="0F4C81", fill_type="solid") # Classic Navy/Teal
    sub_header_fill = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")
    title_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    best_deal_fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid") # Light Emerald
    out_of_stock_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
    
    thin_border_side = Side(style='thin', color='CBD5E1')
    border_all = Border(left=thin_border_side, right=thin_border_side, top=thin_border_side, bottom=thin_border_side)
    
    align_center = Alignment(horizontal="center", vertical="center")
    align_left = Alignment(horizontal="left", vertical="center")
    align_right = Alignment(horizontal="right", vertical="center")
    align_wrap_left = Alignment(horizontal="left", vertical="center", wrap_text=True)

    products = get_all_products()
    month_labels = get_22_month_labels()

    # =========================================================================
    # SHEET 1: Acer_Product_Overview
    # =========================================================================
    ws1 = wb.active
    ws1.title = "Acer_Product_Overview"
    ws1.views.sheetView[0].showGridLines = True

    # Title Banner
    ws1.merge_cells("A1:M1")
    title_cell = ws1["A1"]
    title_cell.value = "ACER AMAZON PRODUCT INTELLIGENCE REPORT"
    title_cell.font = title_font
    title_cell.fill = title_fill
    title_cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws1.row_dimensions[1].height = 40

    ws1.merge_cells("A2:M2")
    sub_cell = ws1["A2"]
    sub_cell.value = f"Generated on: {datetime.now().strftime('%d %B %Y, %I:%M %p')} | Active Tracked ASINs: {len(products)} | Currency: {CURRENCY_SYMBOL} (INR)"
    sub_cell.font = subtitle_font
    sub_cell.fill = title_fill
    sub_cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws1.row_dimensions[2].height = 20

    # Headers for Sheet 1
    headers1 = [
        "ASIN", "Product Title", "Category", f"Today's Price ({CURRENCY_SYMBOL})",
        f"MRP ({CURRENCY_SYMBOL})", "Discount %", "Stock Status",
        f"22-Mo Lowest ({CURRENCY_SYMBOL})", f"22-Mo Highest ({CURRENCY_SYMBOL})",
        f"22-Mo Avg ({CURRENCY_SYMBOL})", "% Off ATH", "Rating", "Amazon Link"
    ]
    
    ws1.append([]) # Row 3 blank spacer
    ws1.row_dimensions[3].height = 10
    
    ws1.append(headers1) # Row 4
    ws1.row_dimensions[4].height = 28
    
    for col_idx, col_name in enumerate(headers1, 1):
        c = ws1.cell(row=4, column=col_idx)
        c.font = header_font
        c.fill = header_fill
        c.alignment = align_center
        c.border = border_all

    # Data Rows for Sheet 1
    for r_idx, prod in enumerate(products, start=5):
        asin = prod["asin"]
        stats = get_product_statistics(asin)
        
        is_zebra = (r_idx % 2 == 0)
        row_fill = zebra_fill if is_zebra else None
        
        current_price = prod["current_price"]
        mrp = prod["mrp"]
        discount_pct = stats.get("discount_from_mrp", 0.0) / 100.0
        stock = prod["stock_status"]
        min_price = stats.get("min_price", current_price)
        max_price = stats.get("max_price", current_price)
        avg_price = stats.get("avg_price", current_price)
        off_ath = stats.get("discount_from_ath", 0.0) / 100.0
        rating = prod["rating"]
        url = prod["url"]

        row_values = [
            asin,
            prod["title"],
            prod["category"],
            current_price,
            mrp,
            discount_pct,
            stock,
            min_price,
            max_price,
            avg_price,
            off_ath,
            rating,
            "View on Amazon"
        ]
        ws1.append(row_values)
        ws1.row_dimensions[r_idx].height = 24

        # Style each cell in row
        for col_idx in range(1, len(row_values) + 1):
            cell = ws1.cell(row=r_idx, column=col_idx)
            cell.font = data_font
            cell.border = border_all
            if row_fill:
                cell.fill = row_fill

            # Column specific formatters
            if col_idx == 1: # ASIN
                cell.value = asin
                cell.hyperlink = url
                cell.alignment = align_center
                cell.font = link_bold_font
            elif col_idx == 2: # Title
                cell.alignment = align_wrap_left
            elif col_idx == 3: # Category
                cell.alignment = align_center
            elif col_idx in [4, 5, 8, 9, 10]: # Currency columns
                cell.number_format = f'"{CURRENCY_SYMBOL}"#,##0'
                cell.alignment = align_right
                if col_idx == 4 and stats.get("is_atl"):
                    cell.fill = best_deal_fill
                    cell.font = badge_green_font
            elif col_idx in [6, 11]: # Percentage columns
                cell.number_format = '0.0%'
                cell.alignment = align_right
            elif col_idx == 7: # Stock
                cell.alignment = align_center
                if stock == "Out of Stock":
                    cell.fill = out_of_stock_fill
            elif col_idx == 12: # Rating
                cell.alignment = align_center
                cell.number_format = '0.0'
            elif col_idx == 13: # Link
                cell.value = "View on Amazon"
                cell.hyperlink = url
                cell.alignment = align_center
                cell.font = link_font

    # =========================================================================
    # SHEET 2: 22_Months_Price_History
    # =========================================================================
    ws2 = wb.create_sheet(title="22_Months_Price_History")
    ws2.views.sheetView[0].showGridLines = True

    # Title Banner
    ws2.merge_cells(f"A1:{get_column_letter(len(month_labels) + 7)}1")
    t2 = ws2["A1"]
    t2.value = "ACER 22-MONTH HISTORICAL PRICE MATRIX"
    t2.font = title_font
    t2.fill = title_fill
    t2.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws2.row_dimensions[1].height = 40

    headers2 = ["ASIN", "Product Title", "Category"] + month_labels + [
        f"22-Mo Min ({CURRENCY_SYMBOL})", f"22-Mo Max ({CURRENCY_SYMBOL})", "Volatility %", "Amazon Link"
    ]
    
    ws2.append([])
    ws2.row_dimensions[2].height = 10
    ws2.append(headers2)
    ws2.row_dimensions[3].height = 28

    for col_idx, col_name in enumerate(headers2, 1):
        c = ws2.cell(row=3, column=col_idx)
        c.font = header_font
        c.fill = header_fill
        c.alignment = align_center
        c.border = border_all

    for r_idx, prod in enumerate(products, start=4):
        asin = prod["asin"]
        url = prod["url"]
        history = get_price_history_for_asin(asin)
        
        # Map month_label to price
        price_by_month = {h["month_label"]: h["price"] for h in history}
        
        history_prices = [price_by_month.get(m, prod["current_price"]) for m in month_labels]
        min_p = min(history_prices) if history_prices else prod["current_price"]
        max_p = max(history_prices) if history_prices else prod["current_price"]
        volatility = ((max_p - min_p) / min_p) if min_p > 0 else 0.0

        row_values = [asin, prod["title"], prod["category"]] + history_prices + [min_p, max_p, volatility, "View on Amazon"]
        ws2.append(row_values)
        ws2.row_dimensions[r_idx].height = 22

        is_zebra = (r_idx % 2 == 0)
        row_fill = zebra_fill if is_zebra else None

        for col_idx in range(1, len(row_values) + 1):
            cell = ws2.cell(row=r_idx, column=col_idx)
            cell.font = data_font
            cell.border = border_all
            if row_fill:
                cell.fill = row_fill

            if col_idx == 1:
                cell.value = asin
                cell.hyperlink = url
                cell.alignment = align_center
                cell.font = link_bold_font
            elif col_idx == 2:
                cell.alignment = align_wrap_left
            elif col_idx == 3:
                cell.alignment = align_center
            elif 4 <= col_idx <= (len(month_labels) + 3):
                cell.number_format = f'"{CURRENCY_SYMBOL}"#,##0'
                cell.alignment = align_right
                # Highlight if this specific month was the lowest
                if cell.value == min_p:
                    cell.fill = best_deal_fill
            elif col_idx in [len(month_labels) + 4, len(month_labels) + 5]:
                cell.number_format = f'"{CURRENCY_SYMBOL}"#,##0'
                cell.alignment = align_right
            elif col_idx == (len(month_labels) + 6):
                cell.number_format = '0.0%'
                cell.alignment = align_right
            elif col_idx == (len(month_labels) + 7):
                cell.value = "View on Amazon"
                cell.hyperlink = url
                cell.alignment = align_center
                cell.font = link_font

    # =========================================================================
    # SHEET 3: Monthly_Statistics
    # =========================================================================
    ws3 = wb.create_sheet(title="Monthly_Statistics")
    ws3.views.sheetView[0].showGridLines = True

    ws3.merge_cells(f"A1:{get_column_letter(len(month_labels) + 2)}1")
    t3 = ws3["A1"]
    t3.value = "CATEGORY-WISE 22-MONTH PRICE TREND BENCHMARKS"
    t3.font = title_font
    t3.fill = title_fill
    t3.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws3.row_dimensions[1].height = 40

    headers3 = ["Category", "Metric"] + month_labels
    ws3.append([])
    ws3.row_dimensions[2].height = 10
    ws3.append(headers3)
    ws3.row_dimensions[3].height = 28

    for col_idx, col_name in enumerate(headers3, 1):
        c = ws3.cell(row=3, column=col_idx)
        c.font = header_font
        c.fill = header_fill
        c.alignment = align_center
        c.border = border_all

    # Compute category averages
    categories = sorted(list(set(p["category"] for p in products)))
    curr_r = 4

    for cat in categories:
        cat_products = [p for p in products if p["category"] == cat]
        cat_asins = [p["asin"] for p in cat_products]
        
        # Calculate monthly average for this category
        cat_monthly_avgs = []
        for m in month_labels:
            m_prices = []
            for asin in cat_asins:
                hist = get_price_history_for_asin(asin)
                for h in hist:
                    if h["month_label"] == m:
                        m_prices.append(h["price"])
                        break
            avg_m = (sum(m_prices) / len(m_prices)) if m_prices else 0
            cat_monthly_avgs.append(round(avg_m, 2))

        ws3.append([cat, f"Average Price ({CURRENCY_SYMBOL})"] + cat_monthly_avgs)
        ws3.row_dimensions[curr_r].height = 22
        
        for c_idx in range(1, len(headers3) + 1):
            cell = ws3.cell(row=curr_r, column=c_idx)
            cell.font = bold_data_font if c_idx <= 2 else data_font
            cell.border = border_all
            if c_idx > 2:
                cell.number_format = f'"{CURRENCY_SYMBOL}"#,##0'
                cell.alignment = align_right
            else:
                cell.alignment = align_center
        curr_r += 1

    # Auto-adjust column widths across all sheets
    for ws in [ws1, ws2, ws3]:
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                # Skip merged header row
                if cell.row in [1, 2]:
                    continue
                val_str = str(cell.value or "")
                if len(val_str) > max_len:
                    max_len = len(val_str)
            # Set proportional width with limits
            ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 48)

    # Specific manual tweaks
    ws1.column_dimensions['B'].width = 46  # Title
    ws2.column_dimensions['B'].width = 42
    ws1.column_dimensions['A'].width = 16  # ASIN
    ws2.column_dimensions['A'].width = 16
    ws1.column_dimensions['M'].width = 18  # Amazon Link
    ws2.column_dimensions[get_column_letter(len(month_labels) + 7)].width = 18

    return wb

def export_excel_to_file(file_path: Optional[str] = None) -> str:
    """Exports workbook to disk and returns the absolute file path."""
    if file_path is None:
        filename = f"Acer_Amazon_Price_Tracker_22Months_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        file_path = str(EXPORTS_DIR / filename)
    
    wb = generate_excel_workbook()
    wb.save(file_path)
    return file_path

def export_excel_to_bytes() -> io.BytesIO:
    """Exports workbook directly to an in-memory BytesIO buffer for streaming."""
    wb = generate_excel_workbook()
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer
