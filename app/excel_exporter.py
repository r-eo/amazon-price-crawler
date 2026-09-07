import io
import os
import gc
from datetime import datetime
from typing import Optional, List, Dict, Any
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from app.config import (
    EXPORTS_DIR, CURRENCY_SYMBOL,
    GROUP_ACER_MONITORS, GROUP_OTHER_PRODUCTS, GROUP_ALL,
    EXCEL_MONITORS_FILENAME, EXCEL_OTHER_FILENAME, EXCEL_ALL_FILENAME,
    now_ist, now_ist_str
)
from app.database import (
    get_all_products, get_products_by_group,
    get_price_history_for_asin, get_product_statistics
)
from app.history_engine import get_22_month_labels

def build_excel_workbook(
    products: List[Dict[str, Any]],
    report_title: str = "ACER AMAZON PRICE INTELLIGENCE REPORT",
    group_label: str = "All Products"
) -> openpyxl.Workbook:
    """
    Generates a structured, executive-styled monotone Excel workbook containing:
    1. Sheet1: Mirrors amazon acer accessories .xlsx structure with live pricing/intelligence.
    2. 6_Months_Price_History: Full monthly matrix across all 6 months with direct links and deal markers.
    3. Monthly_Statistics: Category-level and portfolio aggregate metrics over 6 months.
    """
    wb = openpyxl.Workbook()
    
    # Styling matching amazon acer accessories .xlsx
    FONT_FAMILY = "Calibri"
    
    excel_green_fill = PatternFill(start_color="92D050", end_color="92D050", fill_type="solid") # Excel Header Green (#92D050)
    excel_header_font = Font(name=FONT_FAMILY, size=11, bold=True, color="000000")
    
    intel_header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid") # Slate Charcoal for Intel metrics
    intel_header_font = Font(name=FONT_FAMILY, size=11, bold=True, color="FFFFFF")
    
    sub_header_fill = PatternFill(start_color="334155", end_color="334155", fill_type="solid")
    sub_header_font = Font(name=FONT_FAMILY, size=10, bold=True, color="FFFFFF")
    
    data_font = Font(name=FONT_FAMILY, size=11, color="000000")
    bold_data_font = Font(name=FONT_FAMILY, size=11, bold=True, color="000000")
    link_font = Font(name=FONT_FAMILY, size=11, color="0000FF", underline="single")
    
    zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    best_deal_fill = PatternFill(start_color="ECFDF5", end_color="ECFDF5", fill_type="solid")
    out_of_stock_fill = PatternFill(start_color="FEF2F2", end_color="FEF2F2", fill_type="solid")
    
    thin_border_side = Side(style='thin', color='D4D4D8')
    border_all = Border(left=thin_border_side, right=thin_border_side, top=thin_border_side, bottom=thin_border_side)
    
    align_center = Alignment(horizontal="center", vertical="center")
    align_left = Alignment(horizontal="left", vertical="center")
    align_right = Alignment(horizontal="right", vertical="center")

    month_labels = get_22_month_labels()

    # =========================================================================
    # SHEET 1: Sheet1 (Mirrors amazon acer accessories .xlsx format + Live Intelligence)
    # =========================================================================
    ws1 = wb.active
    ws1.title = "Sheet1"
    ws1.views.sheetView[0].showGridLines = True

    # Row 1: Headers matching exact original columns + Price intelligence
    headers1 = [
        "ASIN", "Model", "Part No", "link",
        f"Today's Price ({CURRENCY_SYMBOL})", f"MRP ({CURRENCY_SYMBOL})", "Discount %",
        "Stock Status", f"6-Mo Lowest ({CURRENCY_SYMBOL})", f"6-Mo Highest ({CURRENCY_SYMBOL})",
        f"6-Mo Avg ({CURRENCY_SYMBOL})", "% Off ATH", "Rating", "Category"
    ]
    
    ws1.append(headers1) # Row 1
    ws1.row_dimensions[1].height = 26
    
    for col_idx, col_name in enumerate(headers1, 1):
        c = ws1.cell(row=1, column=col_idx)
        c.border = border_all
        c.alignment = align_center
        if col_idx <= 4:
            # Exact original columns: Green fill (#92D050) & Black Calibri 11 bold
            c.font = excel_header_font
            c.fill = excel_green_fill
        else:
            # Intelligence tracking columns: Slate fill & White Calibri 11 bold
            c.font = intel_header_font
            c.fill = intel_header_fill

    # Row 2: Blank spacer row (matching amazon acer accessories .xlsx)
    ws1.append([None] * len(headers1))
    ws1.row_dimensions[2].height = 10

    # Data Rows for Sheet 1: Rows 3 to 92 (row-for-row match with Excel)
    if not products:
        ws1.merge_cells("A3:N3")
        empty_cell = ws1["A3"]
        empty_cell.value = "No products in this category yet. Real Acer Monitors catalog will be uploaded here."
        empty_cell.font = Font(name=FONT_FAMILY, size=11, italic=True, color="64748B")
        empty_cell.alignment = align_center
        ws1.row_dimensions[3].height = 30
    else:
        for r_idx, prod in enumerate(products, start=3):
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
            
            model = prod.get("model") or prod.get("title")
            part_no = prod.get("part_no") or ""
            link_url = prod.get("amazon_link") or prod.get("url") or f"https://www.amazon.in/dp/{asin}"

            row_values = [
                asin,
                model,
                part_no,
                link_url,
                current_price,
                mrp,
                discount_pct,
                stock,
                min_price,
                max_price,
                avg_price,
                off_ath,
                rating,
                prod["category"]
            ]
            ws1.append(row_values)
            ws1.row_dimensions[r_idx].height = 22

            # Style each cell in row
            for col_idx in range(1, len(row_values) + 1):
                cell = ws1.cell(row=r_idx, column=col_idx)
                cell.font = data_font
                cell.border = border_all
                if row_fill:
                    cell.fill = row_fill

                if col_idx == 1: # ASIN
                    cell.value = asin
                    cell.hyperlink = link_url
                    cell.alignment = align_center
                elif col_idx == 2: # Model
                    cell.alignment = align_left
                elif col_idx == 3: # Part No
                    cell.alignment = align_center
                elif col_idx == 4: # link
                    cell.value = link_url
                    cell.hyperlink = link_url
                    cell.alignment = align_left
                    cell.font = link_font
                elif col_idx in (5, 6, 9, 10, 11): # Currency amounts
                    cell.number_format = f'{CURRENCY_SYMBOL}#,##0'
                    cell.alignment = align_right
                    if col_idx == 5 and stats.get("is_atl"):
                        cell.fill = best_deal_fill
                        cell.font = bold_data_font
                elif col_idx in (7, 12): # Percentages
                    cell.number_format = '0.0%'
                    cell.alignment = align_right
                elif col_idx == 8: # Stock Status
                    cell.alignment = align_center
                    if "out" in stock.lower():
                        cell.fill = out_of_stock_fill
                elif col_idx == 13: # Rating
                    cell.number_format = '0.0'
                    cell.alignment = align_center
                elif col_idx == 14: # Category
                    cell.alignment = align_center

    # =========================================================================
    # SHEET 2: 6_Months_Price_History (Row-for-row match with Excel)
    # =========================================================================
    ws2 = wb.create_sheet(title="6_Months_Price_History")
    ws2.views.sheetView[0].showGridLines = True

    headers2 = ["ASIN", "Model", "Part No", "Category", f"MRP ({CURRENCY_SYMBOL})"] + month_labels + [f"Period Low ({CURRENCY_SYMBOL})", f"Period High ({CURRENCY_SYMBOL})"]
    ws2.append(headers2)
    ws2.row_dimensions[1].height = 26

    for col_idx, col_name in enumerate(headers2, 1):
        c = ws2.cell(row=1, column=col_idx)
        c.border = border_all
        c.alignment = align_center
        if col_idx <= 3:
            c.font = excel_header_font
            c.fill = excel_green_fill
        else:
            c.font = intel_header_font
            c.fill = intel_header_fill

    # Row 2: Blank spacer row
    ws2.append([None] * len(headers2))
    ws2.row_dimensions[2].height = 10

    if not products:
        ws2.merge_cells("A3:K3")
        empty_cell = ws2["A3"]
        empty_cell.value = "No historical data yet."
        empty_cell.font = Font(name=FONT_FAMILY, size=11, italic=True, color="64748B")
        empty_cell.alignment = align_center
        ws2.row_dimensions[3].height = 30
    else:
        for r_idx, prod in enumerate(products, start=3):
            asin = prod["asin"]
            history = get_price_history_for_asin(asin)
            history_map = {h["month_label"]: h["price"] for h in history}
            
            prices_list = [history_map.get(m, prod["current_price"]) for m in month_labels]
            min_p = min(prices_list) if prices_list else prod["current_price"]
            max_p = max(prices_list) if prices_list else prod["current_price"]
            
            is_zebra = (r_idx % 2 == 0)
            row_fill = zebra_fill if is_zebra else None

            model = prod.get("model") or prod.get("title")
            part_no = prod.get("part_no") or ""
            link_url = prod.get("amazon_link") or prod.get("url") or f"https://www.amazon.in/dp/{asin}"

            row_vals = [
                asin,
                model,
                part_no,
                prod["category"],
                prod["mrp"]
            ] + prices_list + [min_p, max_p]
            
            ws2.append(row_vals)
            ws2.row_dimensions[r_idx].height = 22

            for col_idx in range(1, len(row_vals) + 1):
                cell = ws2.cell(row=r_idx, column=col_idx)
                cell.font = data_font
                cell.border = border_all
                if row_fill:
                    cell.fill = row_fill

                if col_idx == 1:
                    cell.value = asin
                    cell.hyperlink = link_url
                    cell.alignment = align_center
                elif col_idx == 2:
                    cell.alignment = align_left
                elif col_idx == 3:
                    cell.alignment = align_center
                elif col_idx == 4:
                    cell.alignment = align_center
                elif col_idx >= 5:
                    cell.number_format = f'{CURRENCY_SYMBOL}#,##0'
                    cell.alignment = align_right
                    val = cell.value
                    if isinstance(val, (int, float)) and val == min_p:
                        cell.fill = best_deal_fill

    # =========================================================================
    # SHEET 3: Monthly_Statistics
    # =========================================================================
    ws3 = wb.create_sheet(title="Monthly_Statistics")
    ws3.views.sheetView[0].showGridLines = True

    title_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    title_font = Font(name=FONT_FAMILY, size=13, bold=True, color="FFFFFF")
    
    total_s_cols = 2 + len(month_labels)
    ws3.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_s_cols)
    title_cell3 = ws3["A1"]
    title_cell3.value = f"{report_title} — CATEGORY & PORTFOLIO MONTHLY BENCHMARKS"
    title_cell3.font = title_font
    title_cell3.fill = title_fill
    title_cell3.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws3.row_dimensions[1].height = 32

    ws3.append([])
    ws3.row_dimensions[2].height = 8

    headers3 = ["Category", "Product Count"] + month_labels
    ws3.append(headers3)
    ws3.row_dimensions[3].height = 24

    for col_idx in range(1, len(headers3) + 1):
        c = ws3.cell(row=3, column=col_idx)
        c.font = intel_header_font
        c.fill = intel_header_fill
        c.alignment = align_center
        c.border = border_all

    categories = sorted(list(set(p["category"] for p in products)))
    current_r = 4
    for cat in categories:
        cat_prods = [p for p in products if p["category"] == cat]
        cat_asins = [p["asin"] for p in cat_prods]
        
        cat_month_totals = {m: [] for m in month_labels}
        for asin in cat_asins:
            h_list = get_price_history_for_asin(asin)
            h_dict = {h["month_label"]: h["price"] for h in h_list}
            for m in month_labels:
                if m in h_dict:
                    cat_month_totals[m].append(h_dict[m])
        
        cat_month_avgs = [
            (sum(cat_month_totals[m]) / len(cat_month_totals[m])) if cat_month_totals[m] else 0.0
            for m in month_labels
        ]
        
        row_vals = [cat, len(cat_prods)] + cat_month_avgs
        ws3.append(row_vals)
        ws3.row_dimensions[current_r].height = 20
        
        for col_idx in range(1, len(row_vals) + 1):
            cell = ws3.cell(row=current_r, column=col_idx)
            cell.font = data_font
            cell.border = border_all
            if col_idx == 1:
                cell.alignment = align_left
            elif col_idx == 2:
                cell.alignment = align_center
            else:
                cell.number_format = f'{CURRENCY_SYMBOL}#,##0'
                cell.alignment = align_right
        current_r += 1

    # Portfolio Total Row
    if products:
        all_month_totals = {m: [] for m in month_labels}
        for p in products:
            h_list = get_price_history_for_asin(p["asin"])
            h_dict = {h["month_label"]: h["price"] for h in h_list}
            for m in month_labels:
                if m in h_dict:
                    all_month_totals[m].append(h_dict[m])

        portfolio_avgs = [
            (sum(all_month_totals[m]) / len(all_month_totals[m])) if all_month_totals[m] else 0.0
            for m in month_labels
        ]
        
        ws3.append([]) # spacer
        current_r += 1
        
        row_vals = ["Overall Portfolio", len(products)] + portfolio_avgs
        ws3.append(row_vals)
        ws3.row_dimensions[current_r].height = 24
        
        for col_idx in range(1, len(row_vals) + 1):
            cell = ws3.cell(row=current_r, column=col_idx)
            cell.font = sub_header_font
            cell.fill = sub_header_fill
            cell.border = border_all
            if col_idx == 1:
                cell.alignment = align_left
            elif col_idx == 2:
                cell.alignment = align_center
            else:
                cell.number_format = f'{CURRENCY_SYMBOL}#,##0'
                cell.alignment = align_right

    # Set deliberate column widths
    ws1.column_dimensions["A"].width = 14
    ws1.column_dimensions["B"].width = 75
    ws1.column_dimensions["C"].width = 16
    ws1.column_dimensions["D"].width = 30
    ws1.column_dimensions["E"].width = 16
    ws1.column_dimensions["F"].width = 14
    ws1.column_dimensions["G"].width = 14
    ws1.column_dimensions["H"].width = 15
    ws1.column_dimensions["I"].width = 16
    ws1.column_dimensions["J"].width = 16
    ws1.column_dimensions["K"].width = 16
    ws1.column_dimensions["L"].width = 14
    ws1.column_dimensions["M"].width = 10
    ws1.column_dimensions["N"].width = 24

    ws2.column_dimensions["A"].width = 14
    ws2.column_dimensions["B"].width = 75
    ws2.column_dimensions["C"].width = 16
    ws2.column_dimensions["D"].width = 24
    ws2.column_dimensions["E"].width = 15
    for m_col in ["F", "G", "H", "I", "J", "K", "L", "M"]:
        ws2.column_dimensions[m_col].width = 15

    ws3.column_dimensions["A"].width = 28
    ws3.column_dimensions["B"].width = 18
    for m_col in ["C", "D", "E", "F", "G", "H", "I", "J"]:
        ws3.column_dimensions[m_col].width = 15

    return wb

def export_monitors_excel(target_path: Optional[str] = None) -> str:
    """Generates and saves the dedicated Acer Monitors Excel report."""
    products = get_products_by_group(GROUP_ACER_MONITORS)
    wb = build_excel_workbook(
        products=products,
        report_title="Acer Monitors Amazon Price Intelligence Report",
        group_label="Acer Monitors"
    )
    if not target_path:
        target_path = str(EXPORTS_DIR / EXCEL_MONITORS_FILENAME)
    wb.save(target_path)
    wb.close()
    del wb
    gc.collect()
    return target_path

def export_other_products_excel(target_path: Optional[str] = None) -> str:
    """Generates and saves the dedicated Other Products Excel report."""
    products = get_products_by_group(GROUP_OTHER_PRODUCTS)
    wb = build_excel_workbook(
        products=products,
        report_title="Amazon Other Products Price Intelligence Report",
        group_label="Other Products"
    )
    if not target_path:
        target_path = str(EXPORTS_DIR / EXCEL_OTHER_FILENAME)
    wb.save(target_path)
    wb.close()
    del wb
    gc.collect()
    return target_path

def export_all_portfolio_excel(target_path: Optional[str] = None) -> str:
    """Generates and saves the combined All Products Excel report."""
    products = get_all_products()
    wb = build_excel_workbook(
        products=products,
        report_title="Acer Amazon Portfolio Price Intelligence Report",
        group_label="All Tracked Products"
    )
    if not target_path:
        target_path = str(EXPORTS_DIR / EXCEL_ALL_FILENAME)
    wb.save(target_path)
    wb.close()
    del wb
    gc.collect()
    return target_path

def export_excel_by_group(group: str, target_path: Optional[str] = None) -> str:
    """Routes export to the appropriate group workbook."""
    grp = group.lower() if group else GROUP_ALL
    if grp == GROUP_ACER_MONITORS:
        return export_monitors_excel(target_path)
    elif grp == GROUP_OTHER_PRODUCTS:
        return export_other_products_excel(target_path)
    else:
        return export_all_portfolio_excel(target_path)

def export_excel_to_file(target_path: Optional[str] = None) -> str:
    """Default backward-compatible helper exporting all products."""
    return export_all_portfolio_excel(target_path)

def export_excel_to_bytes(group: str = GROUP_ALL) -> io.BytesIO:
    """Returns Excel file as an in-memory BytesIO stream."""
    if group == GROUP_ACER_MONITORS:
        products = get_products_by_group(GROUP_ACER_MONITORS)
        title = "Acer Monitors Amazon Price Intelligence Report"
        label = "Acer Monitors"
    elif group == GROUP_OTHER_PRODUCTS:
        products = get_products_by_group(GROUP_OTHER_PRODUCTS)
        title = "Amazon Other Products Price Intelligence Report"
        label = "Other Products"
    else:
        products = get_all_products()
        title = "Acer Amazon Portfolio Price Intelligence Report"
        label = "All Products"
        
    wb = build_excel_workbook(products, title, label)
    stream = io.BytesIO()
    wb.save(stream)
    wb.close()
    del wb
    gc.collect()
    stream.seek(0)
    return stream
