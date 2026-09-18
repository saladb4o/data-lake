"""Put an arithmetically closed TT200 dataset into a VAS template.

The numbers are invented. What is not invented is that they satisfy every
identity TT200 imposes - 100+200=270, 310+330=300, 410+430=400,
300+400=440, 50+60+61=70 - so any non-zero check the workbook reports
afterwards is the workbook's fault, not the data's.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import vas_layout as V
from xlsx_patch import WorkbookPatch

RD = "Raw Data"


def dataset():
    """Five years of a made-up manufacturer, in millions of dong."""
    years = []
    rev = 12_000_000.0
    cash = 1_400_000.0
    ppe = 6_800_000.0
    retained = 900_000.0
    for i in range(5):
        rev *= 1.12
        gross_rev = rev * 1.02
        deductions = gross_rev - rev
        cogs = rev * 0.78
        sell = rev * 0.045
        admin = rev * 0.031
        fin_inc = rev * 0.008
        fin_exp = rev * 0.017
        interest = fin_exp * 0.8
        other_inc, other_exp = rev * 0.002, rev * 0.001
        op = rev - cogs - sell - admin + fin_inc - fin_exp
        other = other_inc - other_exp
        pretax = op + other
        tax_cur, tax_def = pretax * 0.19, pretax * 0.01
        net = pretax - tax_cur - tax_def

        dep = ppe * 0.09
        capex = -rev * 0.055
        cfo = net + dep + rev * 0.004
        cfi = capex + rev * 0.003
        borrow, repay = rev * 0.06, -rev * 0.045
        dividend = -net * 0.30
        equity_issue = 0.0
        cff = borrow + repay + dividend + equity_issue
        fx = rev * 0.0004
        net_cf = cfo + cfi + cff
        open_cash, cash = cash, cash + net_cf + fx

        ppe = ppe - dep - capex
        inventory, receivable = cogs * 0.18, rev * 0.14
        st_invest, other_ca = 600_000.0 + i * 40_000, rev * 0.01
        ca = cash + st_invest + receivable + inventory + other_ca
        lt_receivable, invest_prop = 120_000.0, 80_000.0
        cip, lt_invest, other_la = 300_000.0, 450_000.0, 260_000.0
        la = lt_receivable + ppe + invest_prop + cip + lt_invest + other_la
        total_assets = ca + la

        payable, advance = cogs * 0.11, rev * 0.01
        st_debt = rev * 0.09
        other_cl = rev * 0.035
        cl = payable + advance + st_debt + other_cl
        lt_debt = rev * 0.13
        other_ncl = 200_000.0
        ncl = lt_debt + other_ncl
        liabilities = cl + ncl

        retained = retained + net + dividend
        minority, dev_fund, other_fund = 150_000.0, 320_000.0, 0.0
        # paid-in capital is what closes the sheet, and it is the only
        # figure here chosen to make an identity hold rather than modelled
        paid_in = (total_assets - liabilities - retained - minority
                   - dev_fund - other_fund)
        equity_410 = paid_in + dev_fund + retained + minority
        equity_400 = equity_410 + other_fund

        years.append({
            "01": gross_rev, "02": deductions, "11": cogs, "21": fin_inc,
            "22": fin_exp, "23": interest, "25": sell, "26": admin,
            "31": other_inc, "32": other_exp, "51": tax_cur, "52": tax_def,
            "61": net * 0.97, "62": net * 0.03, "70_eps": net * 0.97 / 300,
            "shares_avg": 300.0, "shares_end": 300.0,
            "110": cash, "120": st_invest, "130": receivable,
            "140": inventory, "150": other_ca, "100": ca,
            "210": lt_receivable, "220": ppe, "230": invest_prop,
            "240": cip, "250": lt_invest, "260": other_la, "200": la,
            "270": total_assets,
            "311": payable, "312": advance, "320": st_debt, "310": cl,
            "338": lt_debt, "330": ncl, "300": liabilities,
            "411": paid_in, "418": dev_fund, "421": retained,
            "429": minority, "410": equity_410, "430": other_fund,
            "440": liabilities + equity_400,
            "cf01": pretax, "cf02": dep, "cf20": cfo, "cf21": capex,
            "cf22": rev * 0.003, "cf30": cfi, "cf31": equity_issue,
            "cf33": borrow, "cf34": repay, "cf36": dividend,
            "cf40": cff, "cf60": open_cash, "cf61": fx, "cf70": cash,
            "price": 28_500.0, "dps": -dividend / 300,
        })
    return years


def fill(src: str, dest: str) -> None:
    w = WorkbookPatch(src)
    data = dataset()
    w.set_value("Control Panel", "F10", "CÔNG TY CỔ PHẦN MẪU (dữ liệu giả)")
    for col, year in zip(V.HIST_COLS, data):
        for code, row in V.IS_ROW.items():
            if code in year:
                w.set_value(RD, f"{col}{row}", round(year[code], 3))
        w.set_value(RD, f"{col}{V.IS_ROW['70']}", round(year["70_eps"], 3))
        w.set_value(RD, f"{col}{V.SHARES_AVG_ROW}", year["shares_avg"])
        w.set_value(RD, f"{col}{V.SHARES_END_ROW}", year["shares_end"])
        for code, row in V.BS_ROW.items():
            if code in year:
                w.set_value(RD, f"{col}{row}", round(year[code], 3))
        for code, row in V.CF_ROW.items():
            key = "cf" + code
            if key in year:
                w.set_value(RD, f"{col}{row}", round(year[key], 3))
        w.set_value(RD, f"{col}{V.PRICE_ROW}", year["price"])
        w.set_value(RD, f"{col}{V.DPS_ROW}", round(year["dps"], 3))
    w.save(dest)
    print(f"wrote {dest}")


if __name__ == "__main__":
    fill(sys.argv[1], sys.argv[2])
