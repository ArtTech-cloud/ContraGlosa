"""Extrai as tabelas oficiais da ANS usadas pelo projeto.

Uso:
    python -m dados.tabela38.extrair CAMINHO_DO_ZIP

Lê, de dentro do ZIP do componente "Representação de Conceitos em Saúde"
(Padrão TISS 202609):

- Tabela 38 (mensagens de glosa), da planilha "TUSS - Demais terminologias",
  gravada em `dados/tabela38/tabela38.csv`;
- Tabela 22 (procedimentos e eventos em saúde), da planilha "TUSS 22",
  gravada em `dados/tabela22/tabela22.csv`.

Cada pasta recebe um `fonte.json` com URL, data de acesso, SHA-256 do ZIP e o
arquivo de origem. Usa só a biblioteca padrão: um xlsx é um ZIP de XML.
O ZIP em si não vai para o git.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

URL_OFICIAL = (
    "https://www.ans.gov.br/arquivos/extras/tiss/"
    "Padrao_TISS_Representacao_de_Conceitos_em_Saude_202609.zip"
)
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
NS_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
RAIZ = Path(__file__).resolve().parent.parent

# (pasta de saída, trecho do nome do xlsx, regex da aba, regex do código)
TABELAS = [
    ("tabela38", "Demais terminologias", r"\s*Tab\s*38\s*", r"\d{4}"),
    ("tabela22", "TUSS 22", r"\s*Tab\s*22\b.*", r"\d{8}"),
]


def _col_idx(ref: str) -> int:
    letras = re.match(r"[A-Z]+", ref).group(0)
    n = 0
    for c in letras:
        n = n * 26 + (ord(c) - 64)
    return n - 1


def data_excel(v: str) -> str:
    """Converte o número serial de data do Excel para AAAA-MM-DD."""
    if re.fullmatch(r"\d+(\.0+)?", v or ""):
        return (dt.date(1899, 12, 30) + dt.timedelta(days=int(float(v)))).isoformat()
    return v or ""


def _nome_legivel(nome: str) -> str:
    """Desfaz a decodificação errada de nomes no ZIP, quando possível."""
    for de, para in (("cp437", "cp1252"), ("latin-1", "utf-8")):
        try:
            return nome.encode(de).decode(para)
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
    return nome


def ler_planilhas(xlsx: bytes) -> dict[str, list[list[str]]]:
    """Devolve {nome_da_aba: linhas}, cada linha uma lista de strings."""
    z = zipfile.ZipFile(io.BytesIO(xlsx))
    t_tag = f"{{{NS['m']}}}t"
    compartilhadas: list[str] = []
    if "xl/sharedStrings.xml" in z.namelist():
        raiz = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in raiz.findall("m:si", NS):
            compartilhadas.append("".join(t.text or "" for t in si.iter(t_tag)))
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    alvo = {r.get("Id"): r.get("Target") for r in rels}
    abas: dict[str, list[list[str]]] = {}
    for sh in wb.find("m:sheets", NS):
        caminho = "xl/" + alvo[sh.get(NS_REL)].lstrip("/").removeprefix("xl/")
        raiz = ET.fromstring(z.read(caminho))
        linhas: list[list[str]] = []
        for row in raiz.iter(f"{{{NS['m']}}}row"):
            valores: dict[int, str] = {}
            for c in row.findall("m:c", NS):
                v = c.find("m:v", NS)
                tipo = c.get("t")
                if tipo == "inlineStr":
                    texto = "".join(t.text or "" for t in c.iter(t_tag))
                elif v is None:
                    continue
                elif tipo == "s":
                    texto = compartilhadas[int(v.text)]
                else:
                    texto = v.text or ""
                valores[_col_idx(c.get("r"))] = texto.strip()
            if valores:
                linhas.append([valores.get(i, "") for i in range(max(valores) + 1)])
        abas[sh.get("name")] = linhas
    return abas


def _registros(linhas: list[list[str]], regex_cod: str) -> tuple[list[str], list[dict]]:
    inicio = next(k for k, lin in enumerate(linhas) if any("digo" in c.lower() for c in lin))
    cab = [c.lower() for c in linhas[inicio]]
    i_cod = next(i for i, c in enumerate(cab) if "digo" in c)
    i_desc = next(i for i, c in enumerate(cab) if i != i_cod and c.strip() == "termo")
    i_ini = next(i for i, c in enumerate(cab) if "início" in c and "vig" in c)
    i_fim = next(i for i, c in enumerate(cab) if "fim" in c and "vig" in c)

    def cel(lin: list[str], i: int) -> str:
        return lin[i] if i < len(lin) else ""

    regs = []
    for lin in linhas[inicio + 1 :]:
        cod, desc = cel(lin, i_cod), cel(lin, i_desc)
        if re.fullmatch(regex_cod, cod) and desc:
            regs.append(
                {
                    "codigo": cod,
                    "descricao": " ".join(desc.split()),
                    "inicio_vigencia": data_excel(cel(lin, i_ini)),
                    "fim_vigencia": data_excel(cel(lin, i_fim)),
                }
            )
    return linhas[inicio], regs


def extrair(caminho_zip: Path) -> None:
    bruto = caminho_zip.read_bytes()
    sha = hashlib.sha256(bruto).hexdigest()
    zf = zipfile.ZipFile(io.BytesIO(bruto))
    for pasta, trecho, regex_aba, regex_cod in TABELAS:
        origem = next(
            i for i in zf.infolist() if trecho in i.filename and i.filename.endswith(".xlsx")
        )
        abas = ler_planilhas(zf.read(origem))
        nome_aba = next((n for n in abas if re.fullmatch(regex_aba, n)), None)
        if nome_aba is None:
            raise SystemExit(f"Aba não encontrada para {pasta}. Abas: {list(abas)}")
        cabecalho, regs = _registros(abas[nome_aba], regex_cod)
        if not regs:
            raise SystemExit(f"Nenhum código encontrado em {pasta}.")
        destino = RAIZ / pasta
        destino.mkdir(exist_ok=True)
        with open(destino / f"{pasta}.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(regs[0]))
            w.writeheader()
            w.writerows(regs)
        fonte = {
            "url": URL_OFICIAL,
            "data_acesso": dt.date.today().isoformat(),
            "sha256_zip": sha,
            "arquivo_origem": _nome_legivel(origem.filename),
            "aba": _nome_legivel(nome_aba),
            "cabecalho": cabecalho,
            "total_codigos": len(regs),
        }
        (destino / "fonte.json").write_text(
            json.dumps(fonte, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"{pasta}: {len(regs)} códigos gravados")
    print(f"SHA-256 do ZIP: {sha}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    extrair(Path(sys.argv[1]))
