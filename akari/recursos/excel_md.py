#!/usr/bin/env python3
"""Excel → Markdown: una sección por hoja, cada una con su tabla.

Corre con el Python de markitdown (trae pandas, openpyxl y xlrd): `excel.py <entrada.xlsx|.xls> <salida.md>`.
A diferencia de markitdown, deja vacías las celdas vacías (no "NaN"), no vuelve decimales los enteros
(3 y no 3.0), muestra las fechas sin la hora 00:00:00 y quita filas y columnas que están vacías.
"""

import datetime as dt
import math
import sys

import pandas as pd


def celda(v) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)) or v is pd.NaT:
        return ""
    if isinstance(v, (pd.Timestamp, dt.datetime)):
        return v.strftime("%Y-%m-%d") if (v.hour, v.minute, v.second) == (0, 0, 0) else v.strftime("%Y-%m-%d %H:%M")
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    texto = str(v).strip()
    return texto.replace("|", "\\|").replace("\r\n", "<br>").replace("\n", "<br>")


def tabla(df: pd.DataFrame) -> str:
    filas = [[celda(v) for v in fila] for fila in df.itertuples(index=False)]
    filas = [f for f in filas if any(f)]
    if not filas:
        return "*(hoja vacía)*"
    usadas = [i for i in range(len(filas[0])) if any(f[i] for f in filas)]
    filas = [[f[i] for i in usadas] for f in filas]
    cabeza, *cuerpo = filas
    lineas = ["| " + " | ".join(cabeza) + " |", "|" + " --- |" * len(cabeza)]
    lineas += ["| " + " | ".join(f) + " |" for f in cuerpo]
    return "\n".join(lineas)


def main(entrada: str, salida: str):
    hojas = pd.read_excel(entrada, sheet_name=None, header=None, dtype=object)
    partes = [f"## {nombre}\n\n{tabla(df)}" for nombre, df in hojas.items()]
    with open(salida, "w", encoding="utf-8") as f:
        f.write("\n\n".join(partes) + "\n")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
