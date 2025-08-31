import openpyxl
from openpyxl import load_workbook

def append_trade(record, filename="logs/trade_log.xlsx"):
    try:
        wb = load_workbook(filename)
        ws = wb.active
    except FileNotFoundError:
        wb = openpyxl.Workbook()
        ws = wb.active
        headers = list(record.keys())
        ws.append(headers)

    ws.append(list(record.values()))
    wb.save(filename)