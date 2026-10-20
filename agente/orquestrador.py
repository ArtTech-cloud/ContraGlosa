"""Orquestrador: 4 etapas (triagem, extração, análise, redação), cada uma com prompt versionado,
só as ferramentas de que precisa e saída JSON validada por pydantic.

Se a validação falhar, a etapa refaz com o erro como contexto, no máximo 2 vezes. Depois disso,
o caso vai para revisão humana com o motivo. O código decide o que exige certeza: soma, existência
do código na Tabela 38, prazo, evidência e totais do painel.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import time
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, ValidationError

from agente.consolidar import painel
from agente.ferramentas.base import ids_validos
from agente.ferramentas.basicas import conferir_soma, consultar_t38
from agente.ferramentas.dados_ref import achar_operadora
from agente.ferramentas.registro import FERRAMENTAS_ANALISE, executar
from agente.ferramentas.verificadores import (
    verificar_analise,
    verificar_evidencia,
    verificar_recurso,
)
from agente.guardrails import filtrar_instrucoes, normalizar
from agente.llm import ErroLLM, Pedido, RespostaLLM, SemCache, para_historico
from agente.modelos import (
    Analise,
    ChamadaFerramenta,
    Extracao,
    GlosaAnalisada,
    PassoTrilha,
    Pendencia,
    Redacao,
    Resultado,
    Triagem,
)
from agente.pdf import DocumentoTexto, PDFInvalido, extrair_texto, formatar_para_llm
from agente.pseudonimo import Pseudonimizado, pseudonimizar

RAIZ = Path(__file__).resolve().parents[1]
PASTA_PROMPTS = Path(__file__).resolve().parent / "prompts"
PASTA_RUNS = RAIZ / ".runs"
MAX_REFAZER = 2
MAX_TURNOS_FERRAMENTA = 14
LINHAS_TRIAGEM = 40


def versoes_prompt() -> dict[str, str]:
    """Versão de cada prompt. AGENTE_PROMPTS='analise=v2,redacao=v2' sobrescreve."""
    v = {"sistema": "v1", "triagem": "v1", "extracao": "v1", "analise": "v1", "redacao": "v1"}
    for par in filter(None, os.getenv("AGENTE_PROMPTS", "").split(",")):
        etapa, _, ver = par.partition("=")
        v[etapa.strip()] = ver.strip()
    return v


def carregar_prompt(etapa: str, versao: str) -> str:
    return (PASTA_PROMPTS / f"{etapa}_{versao}.md").read_text(encoding="utf-8")


def extrair_json(texto: str) -> dict:
    """Pega o JSON da resposta: bloco ```json, ou do primeiro '{' ao último '}'."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", texto, re.DOTALL)
    bruto = m.group(1) if m else texto[texto.find("{") : texto.rfind("}") + 1]
    if not bruto:
        raise ValueError("a resposta não contém JSON")
    return json.loads(bruto)


def conferir_triagem(t: Triagem, texto_doc: str) -> list[str]:
    """A data de emissão e a operadora da triagem precisam estar escritas no PDF."""
    erros = []
    if t.data_emissao and t.data_emissao.strip() not in texto_doc:
        erros.append(f"a data de emissão {t.data_emissao} não aparece no documento")
    op = achar_operadora(t.operadora)
    if op and op["apelido"] not in normalizar(texto_doc):
        erros.append(f"a operadora {t.operadora} não aparece no documento")
    return erros


class Interrompido(Exception):
    """Falha fatal da API (chave, crédito): para tudo e avisa."""


class Orquestrador:
    def __init__(self, cliente, ao_passo: Callable[[PassoTrilha], None] | None = None):
        self.cliente = cliente
        self.ao_passo = ao_passo
        self.versoes = versoes_prompt()
        self.sistema = carregar_prompt("sistema", self.versoes["sistema"])

    # ================================================================ utilitários
    def _passo(self, res: Resultado, passo: PassoTrilha) -> None:
        res.trilha.append(passo)
        res.tokens_entrada += passo.tokens_entrada
        res.tokens_saida += passo.tokens_saida
        if self.ao_passo:
            self.ao_passo(passo)

    def _pedir(self, res: Resultado, pedido: Pedido) -> RespostaLLM:
        try:
            r = self.cliente.criar(pedido)
        except SemCache:
            raise
        except ErroLLM as e:
            if e.fatal:
                raise Interrompido(str(e)) from e
            raise
        res.custo_usd += r.custo_usd
        return r

    def _etapa_json(
        self,
        res: Resultado,
        etapa: str,
        prompt: str,
        modelo_saida: type[BaseModel],
        validar: Callable[[BaseModel], list[str]] | None = None,
        ferramentas: list[dict] | None = None,
    ) -> tuple[BaseModel | None, list[str]]:
        """Roda uma etapa até validar ou esgotar as tentativas. Devolve (saída, erros finais)."""
        versao = self.versoes[etapa]
        mensagens: list[dict] = [{"role": "user", "content": prompt}]
        ultimo_ok: BaseModel | None = None
        erros_ultimo_ok: list[str] = []
        erros: list[str] = []
        for tentativa in range(MAX_REFAZER + 1):
            passo = PassoTrilha(
                etapa=etapa,
                versao_prompt=versao,
                modelo=self.cliente.modelo,
                status="ok" if tentativa == 0 else "retry",
            )
            t0 = time.monotonic()
            try:
                r = self._laco_ferramentas(res, etapa, versao, mensagens, ferramentas or [], passo)
            except SemCache as e:
                passo.status = "erro"
                passo.detalhe = str(e)
                self._passo(res, passo)
                raise
            except ErroLLM as e:
                passo.status = "erro"
                passo.detalhe = str(e)
                passo.latencia_ms = int((time.monotonic() - t0) * 1000)
                self._passo(res, passo)
                return None, [f"erro na API: {e}"]
            passo.latencia_ms = int((time.monotonic() - t0) * 1000)
            try:
                saida = modelo_saida.model_validate(extrair_json(r.texto))
                erros = validar(saida) if validar else []
                ultimo_ok, erros_ultimo_ok = saida, erros
            except (ValueError, ValidationError, RecursionError) as e:
                erros = [_resumo_erro(e)]
                saida = None
            if not erros:
                passo.status = "ok"
                passo.detalhe = "saída validada" + (
                    f" na tentativa {tentativa + 1}" if tentativa else ""
                )
                self._passo(res, passo)
                return saida, []
            passo.status = "retry" if tentativa < MAX_REFAZER else "fallback"
            passo.detalhe = "validação recusou: " + "; ".join(erros)[:600]
            self._passo(res, passo)
            mensagens.append({"role": "assistant", "content": para_historico(r.content)})
            mensagens.append(
                {
                    "role": "user",
                    "content": "A validação do código recusou a sua resposta:\n- "
                    + "\n- ".join(erros)
                    + "\nCorrija e devolva o JSON completo de novo, no mesmo formato.",
                }
            )
        return (ultimo_ok, erros_ultimo_ok) if ultimo_ok is not None else (None, erros)

    def _laco_ferramentas(
        self,
        res: Resultado,
        etapa: str,
        versao: str,
        mensagens: list[dict],
        ferramentas: list[dict],
        passo: PassoTrilha,
    ) -> RespostaLLM:
        """Chama o modelo e executa as ferramentas até ele responder sem pedir ferramenta."""
        for _ in range(MAX_TURNOS_FERRAMENTA):
            r = self._pedir(
                res,
                Pedido(
                    etapa=etapa,
                    versao=versao,
                    system=self.sistema,
                    messages=list(mensagens),
                    tools=ferramentas,
                ),
            )
            passo.tokens_entrada += (
                r.tokens_entrada + r.tokens_cache_leitura + r.tokens_cache_escrita
            )
            passo.tokens_saida += r.tokens_saida
            passo.do_cache = passo.do_cache or r.do_cache
            if r.stop_reason == "max_tokens":
                raise ErroLLM("resposta cortada por limite de tokens")
            if not r.chamadas:
                return r
            mensagens.append({"role": "assistant", "content": para_historico(r.content)})
            resultados = []
            for ch in r.chamadas:
                if not ch.get("id"):
                    raise ErroLLM("o modelo pediu uma ferramenta sem id")
                args = ch.get("input") if isinstance(ch.get("input"), dict) else None
                if args is None:
                    saida, ids = '{"erro": "argumentos da ferramenta devem ser um objeto JSON"}', []
                    args = {}
                else:
                    saida, ids = executar(str(ch.get("name", "")), args)
                self._citaveis.update(ids)
                passo.ferramentas.append(
                    ChamadaFerramenta(
                        nome=str(ch.get("name", "?")), argumentos=args, resultado=saida[:300]
                    )
                )
                resultados.append(
                    {"type": "tool_result", "tool_use_id": ch["id"], "content": saida}
                )
            mensagens.append({"role": "user", "content": resultados})
        raise ErroLLM("o modelo excedeu o limite de chamadas de ferramenta")

    # ================================================================ fluxo principal
    def analisar(self, origem: str | Path | bytes, nome: str | None = None) -> Resultado:
        t0 = time.monotonic()
        if isinstance(origem, bytearray | memoryview):
            origem = bytes(origem)
        nome = nome or (Path(origem).name if not isinstance(origem, bytes) else "documento.pdf")
        res = Resultado(documento=nome, versoes_prompt=self.versoes, modelo=self.cliente.modelo)
        self._citaveis: set[str] = set()
        try:
            self._fluxo(res, origem, nome)
        except SemCache as e:
            res.interrompido = True
            res.pendencias.append(Pendencia(tipo="sem_cache", motivo=str(e)))
        except Interrompido as e:
            res.interrompido = True
            res.pendencias.append(Pendencia(tipo="erro_api", motivo=f"análise interrompida: {e}"))
            self._passo(res, PassoTrilha(etapa="fluxo", status="erro", detalhe=str(e)))
        except Exception as e:  # nenhuma falha interna derruba a tela; vira pendência com o motivo
            res.interrompido = True
            msg = f"falha interna ({type(e).__name__}): {str(e)[:200]}"
            res.pendencias.append(Pendencia(tipo="validacao_falhou", motivo=msg))
            self._passo(res, PassoTrilha(etapa="fluxo", status="erro", detalhe=msg))
        try:
            res.painel = painel(res)
        except Exception:  # painel parcial se os dados estiverem incompletos
            res.painel = {
                "total_apresentado": 0,
                "total_glosado": 0,
                "total_pago": 0,
                "recorrivel": 0,
                "nao_recorrivel": 0,
                "a_classificar": 0,
                "prazo": None,
            }
        res.latencia_ms = int((time.monotonic() - t0) * 1000)
        self._gravar_trilha(res)
        return res

    def _fluxo(self, res: Resultado, origem, nome: str) -> None:
        # ---------- 0. leitura, pseudonimização e filtro (código) ----------
        try:
            doc = extrair_texto(origem, nome=nome)
        except PDFInvalido as e:
            res.pendencias.append(Pendencia(tipo="documento_nao_reconhecido", motivo=str(e)))
            self._passo(res, PassoTrilha(etapa="leitura", status="fallback", detalhe=str(e)))
            return
        res.sha256 = doc.sha256
        for p in doc.paginas_sem_texto:
            res.pendencias.append(
                Pendencia(
                    tipo="pagina_ilegivel",
                    motivo=f"página {p} sem camada de texto (provável imagem escaneada); sem OCR, "
                    "precisa de leitura humana",
                    pagina=p,
                )
            )
        if not doc.linhas:
            res.pendencias.append(
                Pendencia(tipo="documento_sem_texto", motivo="nenhuma página tem texto")
            )
            self._passo(
                res, PassoTrilha(etapa="leitura", status="fallback", detalhe="documento sem texto")
            )
            return
        ps = pseudonimizar(doc.linhas)
        linhas, alertas = filtrar_instrucoes(ps.linhas)
        res.alertas.extend(alertas)
        texto_llm = formatar_para_llm(linhas)
        self._passo(
            res,
            PassoTrilha(
                etapa="leitura",
                detalhe=(
                    f"{doc.total_paginas} página(s), {len(doc.linhas)} linhas com texto"
                    + (
                        f", páginas sem texto: {doc.paginas_sem_texto}"
                        if doc.paginas_sem_texto
                        else ""
                    )
                    + f". Pseudonimização: {len(ps.nomes)} nome(s), {len(ps.tokens)} carteira(s), "
                    f"{ps.cpfs} CPF(s) removidos antes do LLM. Filtro de instruções: {len(alertas)} trecho(s)."
                ),
                status="fallback" if alertas or doc.paginas_sem_texto else "ok",
            ),
        )

        # ---------- 1. triagem ----------
        inicio = formatar_para_llm(linhas[:LINHAS_TRIAGEM])
        texto_doc = "\n".join(lin.texto for lin in doc.linhas)
        tri, erros = self._etapa_json(
            res,
            "triagem",
            carregar_prompt("triagem", self.versoes["triagem"]).format(documento=inicio),
            Triagem,
            lambda t: conferir_triagem(t, texto_doc),
        )
        if tri is None:
            res.pendencias.append(
                Pendencia(tipo="validacao_falhou", motivo="triagem: " + "; ".join(erros))
            )
            return
        if erros:  # formato ok, mas data ou operadora não aparecem no PDF: sem prazo automático
            atual = {}
            if any("data de emissão" in e for e in erros):
                atual["data_emissao"] = None
            if any("operadora" in e for e in erros):
                atual["operadora"] = "não confirmada no documento"
                atual["observacao"] = f"a triagem leu '{tri.operadora}', que não aparece no PDF"
            tri = tri.model_copy(update=atual)
            res.pendencias.append(
                Pendencia(
                    tipo="validacao_falhou",
                    motivo="triagem: " + "; ".join(erros) + ". Prazo de recurso não calculado.",
                )
            )
        res.triagem = tri
        if tri.tipo_documento != "demonstrativo_retorno":
            res.pendencias.append(
                Pendencia(
                    tipo="documento_nao_reconhecido",
                    motivo="a triagem não reconheceu um demonstrativo",
                )
            )
            return

        # ---------- 2. extração + conferir_soma ----------
        ext = self._extrair(res, doc, texto_llm)
        if ext is None:
            return

        # ---------- 3. análise ----------
        self._analisar(res, ext, doc, texto_llm)

        # ---------- 4. redação ----------
        self._redigir(res, ps)

    # ---------------------------------------------------------------- extração
    def _extrair(self, res: Resultado, doc: DocumentoTexto, texto_llm: str) -> Extracao | None:
        def validar(e: Extracao) -> list[str]:
            erros = []
            for i, it in enumerate(e.itens):
                err = verificar_evidencia(it, doc)
                if err:
                    erros.append(f"item {i}: {err}")
            return erros

        prompt = carregar_prompt("extracao", self.versoes["extracao"]).format(documento=texto_llm)
        ext, erros = self._etapa_json(res, "extracao", prompt, Extracao, validar)
        if ext is None:
            res.pendencias.append(
                Pendencia(tipo="validacao_falhou", motivo="extração: " + "; ".join(erros))
            )
            return None
        erros_evidencia = erros

        def _pendencias_evidencia(ext: Extracao, erros: list[str]) -> None:
            for e in erros:
                m = re.match(r"item (\d+):", e)
                it = ext.itens[int(m.group(1))] if m else None
                res.pendencias.append(
                    Pendencia(
                        tipo="evidencia_nao_confere",
                        motivo=e,
                        pagina=it.pagina if it else None,
                        linha=it.linha if it else None,
                        item=int(m.group(1)) if m else None,
                    )
                )

        # conferir_soma: o código compara a soma das linhas com os totais impressos
        if doc.paginas_sem_texto:
            self._passo(
                res,
                PassoTrilha(
                    etapa="conferir_soma",
                    status="info",
                    detalhe=f"soma não conferida: página(s) {doc.paginas_sem_texto} sem texto",
                ),
            )
        else:
            soma = conferir_soma(ext.itens, ext.totais)
            passo = PassoTrilha(etapa="conferir_soma", detalhe=soma.resumo())
            passo.ferramentas.append(
                ChamadaFerramenta(
                    nome="conferir_soma",
                    argumentos={"itens": len(ext.itens)},
                    resultado=soma.resumo(),
                    aprovado=soma.ok,
                )
            )
            if not soma.ok and not soma.sem_totais:
                passo.status = "retry"
                self._passo(res, passo)
                # uma releitura, com a divergência como contexto
                prompt2 = (
                    prompt
                    + "\n\nAtenção: uma extração anterior deste documento não fechou a soma. O código encontrou: "
                    + soma.resumo()
                    + ". Releia com cuidado e corrija se algum item ou valor foi lido errado. Se a extração "
                    "estiver certa e o próprio documento estiver inconsistente, devolva os valores como impressos."
                )
                ext2, erros2 = self._etapa_json(res, "extracao", prompt2, Extracao, validar)
                if ext2 is not None and len(erros2) <= len(erros_evidencia):
                    ext, erros_evidencia = ext2, erros2
                soma = conferir_soma(ext.itens, ext.totais)
                passo = PassoTrilha(
                    etapa="conferir_soma", detalhe="após releitura: " + soma.resumo()
                )
                passo.ferramentas.append(
                    ChamadaFerramenta(
                        nome="conferir_soma",
                        argumentos={"releitura": True},
                        resultado=soma.resumo(),
                        aprovado=soma.ok,
                    )
                )
                if not soma.ok:
                    passo.status = "fallback"
                    pag = ext.totais.pagina if ext.totais else None
                    lin = ext.totais.linha if ext.totais else None
                    res.pendencias.append(
                        Pendencia(
                            tipo="soma_divergente",
                            motivo="a soma das linhas não bate com o total impresso: "
                            + soma.resumo(),
                            pagina=pag,
                            linha=lin,
                        )
                    )
            elif soma.sem_totais:
                passo.status = "fallback"
                res.pendencias.append(Pendencia(tipo="totais_ausentes", motivo=soma.resumo()))
            self._passo(res, passo)
        # validou o formato, mas a evidência de algum item não confere (sobre a extração final)
        _pendencias_evidencia(ext, erros_evidencia)
        res.itens = ext.itens
        res.totais = ext.totais
        return ext

    # ---------------------------------------------------------------- análise
    def _analisar(self, res: Resultado, ext: Extracao, doc: DocumentoTexto, texto_llm: str) -> None:
        tri = res.triagem
        evid_ruim = {p.item for p in res.pendencias if p.tipo == "evidencia_nao_confere"}
        analisaveis: list[int] = []
        verif = PassoTrilha(etapa="consultar_t38", detalhe="")
        for i, it in enumerate(ext.itens):
            if not it.tem_glosa:
                continue
            base = dict(
                item=i,
                guia=it.guia,
                codigo_procedimento=it.codigo_procedimento,
                codigo_glosa=it.codigo_glosa,
                valor_glosado=it.glosado,
                pagina=it.pagina,
                linha=it.linha,
                evidencia_ok=i not in evid_ruim,
            )
            if it.codigo_glosa is None:
                res.glosas.append(
                    GlosaAnalisada(
                        **base,
                        descricao_oficial=None,
                        existe_t38=False,
                        decisao="revisao_humana",
                        confianca="baixa",
                        justificativa="Valor glosado sem código de glosa impresso.",
                        origem="codigo",
                    )
                )
                res.pendencias.append(
                    Pendencia(
                        tipo="codigo_inexistente",
                        motivo="glosa sem código impresso",
                        item=i,
                        pagina=it.pagina,
                        linha=it.linha,
                    )
                )
                continue
            t38 = consultar_t38(it.codigo_glosa)
            verif.ferramentas.append(
                ChamadaFerramenta(
                    nome="consultar_t38",
                    argumentos={"codigo": it.codigo_glosa},
                    resultado="existe" if t38["existe"] else "NÃO EXISTE",
                    aprovado=t38["existe"],
                )
            )
            if not t38["existe"]:
                res.glosas.append(
                    GlosaAnalisada(
                        **base,
                        descricao_oficial=None,
                        existe_t38=False,
                        decisao="revisao_humana",
                        confianca="baixa",
                        justificativa=f"O código {it.codigo_glosa} não consta na Tabela 38 oficial "
                        "(Padrão TISS 202609). O significado não foi presumido; pedir esclarecimento à operadora.",
                        origem="codigo",
                    )
                )
                res.pendencias.append(
                    Pendencia(
                        tipo="codigo_inexistente",
                        motivo=f"código {it.codigo_glosa} não consta na Tabela 38 oficial",
                        item=i,
                        pagina=it.pagina,
                        linha=it.linha,
                    )
                )
                continue
            analisaveis.append(i)
        n_ok = len(analisaveis)
        n_inex = len(verif.ferramentas) - n_ok
        verif.detalhe = f"{len(verif.ferramentas)} código(s) conferidos na Tabela 38: {n_ok} existem, {n_inex} não"
        verif.status = "fallback" if n_inex else "ok"
        if verif.ferramentas:
            self._passo(res, verif)
        if not analisaveis:
            return

        tabela = "\n".join(
            f"[{i}] p{it.pagina} l{it.linha} | guia {it.guia} | {it.data_atendimento} | {it.beneficiario} | "
            f"{it.codigo_procedimento} {it.descricao} | apresentado {it.valor_apresentado} | glosado "
            f"{it.valor_glosado} | pago {it.valor_pago} | glosa {it.codigo_glosa or '-'}"
            + (f" | senha {it.senha}" if it.senha else "")
            + (f" | obs: {it.observacao}" if it.observacao else "")
            for i, it in enumerate(ext.itens)
        )
        prompt = carregar_prompt("analise", self.versoes["analise"]).format(
            operadora=tri.operadora,
            data_emissao=tri.data_emissao or "não informada",
            itens=tabela,
            glosas=", ".join(map(str, analisaveis)),
            documento=texto_llm,
        )
        validos = ids_validos()
        an, erros = self._etapa_json(
            res,
            "analise",
            prompt,
            Analise,
            lambda a: verificar_analise(a.decisoes, analisaveis, validos, self._citaveis),
            ferramentas=FERRAMENTAS_ANALISE,
        )
        por_item: dict = {}
        for d in an.decisoes if an else []:
            por_item.setdefault(d.item, d)
        erro_item: dict[int, list[str]] = {}
        for e in erros:
            m = re.match(r"item (\d+):", e)
            if m:
                erro_item.setdefault(int(m.group(1)), []).append(e)
        for i in analisaveis:
            it = ext.itens[i]
            d = por_item.get(i)
            t38 = consultar_t38(it.codigo_glosa)
            base = dict(
                item=i,
                guia=it.guia,
                codigo_procedimento=it.codigo_procedimento,
                codigo_glosa=it.codigo_glosa,
                descricao_oficial=t38.get("descricao_oficial"),
                existe_t38=True,
                valor_glosado=it.glosado,
                pagina=it.pagina,
                linha=it.linha,
                evidencia_ok=i not in evid_ruim,
            )
            if d is None or i in erro_item:
                motivo = (
                    "análise não validou: " + "; ".join(erro_item[i])
                    if i in erro_item
                    else "o agente não decidiu este item"
                    + (f" ({'; '.join(erros)})" if erros else "")
                )
                res.glosas.append(
                    GlosaAnalisada(
                        **base,
                        decisao="revisao_humana",
                        confianca="baixa",
                        justificativa=motivo[:500],
                        origem="codigo",
                    )
                )
                res.pendencias.append(
                    Pendencia(
                        tipo="validacao_falhou",
                        motivo=motivo[:500],
                        item=i,
                        pagina=it.pagina,
                        linha=it.linha,
                    )
                )
                continue
            decisao = d.decisao
            just = d.justificativa
            if d.confianca == "baixa" and decisao != "revisao_humana":
                res.pendencias.append(
                    Pendencia(
                        tipo="confianca_baixa",
                        motivo=f"o agente sugeriu '{decisao}' com confiança baixa: {d.justificativa}",
                        item=i,
                        pagina=it.pagina,
                        linha=it.linha,
                    )
                )
                just = f"(Sugestão do agente: {decisao}, confiança baixa.) {d.justificativa}"
                decisao = "revisao_humana"
            if i in evid_ruim and decisao == "recorrer":
                decisao = "revisao_humana"
                just = "(Evidência no PDF não conferiu; conferir antes de recorrer.) " + just
            res.glosas.append(
                GlosaAnalisada(
                    **base,
                    decisao=decisao,
                    confianca=d.confianca,
                    justificativa=just,
                    fontes=d.fontes,
                    documentos=d.documentos,
                    origem="agente",
                )
            )
        res.glosas.sort(key=lambda g: g.item)

    # ---------------------------------------------------------------- redação
    def _redigir(self, res: Resultado, ps: Pseudonimizado) -> None:
        alvo = [g for g in res.glosas if g.decisao == "recorrer"]
        if not alvo:
            return
        tri = res.triagem
        op = achar_operadora(tri.operadora)
        contratado = {op["valor_consulta_centavos"]} if op else set()

        def permitidos(it) -> set[int]:
            """Só os valores do próprio item e o valor contratado da operadora."""
            return {it.apresentado, it.glosado, it.pago} | contratado

        blocos = []
        for g in alvo:
            it = res.itens[g.item]
            blocos.append(
                f"[item {g.item}] guia {it.guia} | atendimento {it.data_atendimento} | beneficiário "
                f"{it.beneficiario} | procedimento {it.codigo_procedimento} {it.descricao} | apresentado "
                f"R$ {it.valor_apresentado} | glosado R$ {it.valor_glosado} | pago R$ {it.valor_pago} | glosa "
                f"{it.codigo_glosa} ({g.descricao_oficial})"
                + (f" | senha {it.senha}" if it.senha else "")
                + f"\n  análise: {g.justificativa}\n  documentos sugeridos: {', '.join(g.documentos) or 'nenhum'}"
            )
        prompt = carregar_prompt("redacao", self.versoes["redacao"]).format(
            operadora=tri.operadora,
            data_emissao=tri.data_emissao or "não informada",
            protocolo=tri.protocolo or "[A PREENCHER]",
            itens="\n\n".join(blocos),
        )
        alvo_idx = [g.item for g in alvo]
        reprovados: dict[int, list[str]] = {}

        def validar(red: Redacao) -> list[str]:
            erros = []
            reprovados.clear()
            vistos = [r.item for r in red.recursos]
            for i in sorted(set(alvo_idx) - set(vistos)):
                erros.append(f"falta o recurso do item {i}")
            for i in sorted({x for x in vistos if vistos.count(x) > 1}):
                erros.append(f"recurso do item {i}: mais de um rascunho para o mesmo item")
            for r in red.recursos:
                if r.item not in alvo_idx:
                    erros.append(f"item {r.item} não estava na lista para recorrer")
                    continue
                v = verificar_recurso(
                    r.texto, res.itens[r.item], permitidos(res.itens[r.item]), ps.nomes
                )
                if not v.ok:
                    reprovados[r.item] = v.erros
                    erros += [f"recurso do item {r.item}: {e}" for e in v.erros]
            return erros

        red, erros = self._etapa_json(res, "redacao", prompt, Redacao, validar)
        passo = PassoTrilha(etapa="verificar_recurso")
        aprovados = []
        for r in red.recursos if red else []:
            if r.item not in alvo_idx or r.item in {a.item for a in aprovados}:
                continue
            ok = r.item not in reprovados
            passo.ferramentas.append(
                ChamadaFerramenta(
                    nome="verificar_recurso",
                    argumentos={"item": r.item},
                    resultado="aprovado" if ok else "; ".join(reprovados[r.item])[:300],
                    aprovado=ok,
                )
            )
            if ok:
                aprovados.append(r)
        for i in alvo_idx:
            if i not in {r.item for r in aprovados}:
                it = res.itens[i]
                motivo = "; ".join(reprovados.get(i, erros or ["recurso não gerado"]))
                res.pendencias.append(
                    Pendencia(
                        tipo="recurso_recusado",
                        motivo=f"rascunho reprovado pelo verificador: {motivo}"[:500],
                        item=i,
                        pagina=it.pagina,
                        linha=it.linha,
                    )
                )
        passo.detalhe = (
            f"{len(aprovados)} de {len(alvo_idx)} rascunho(s) aprovados pelo verificador"
        )
        passo.status = "ok" if len(aprovados) == len(alvo_idx) else "fallback"
        self._passo(res, passo)
        res.recursos = sorted(aprovados, key=lambda r: r.item)

    # ---------------------------------------------------------------- trilha
    def _gravar_trilha(self, res: Resultado) -> None:
        try:
            PASTA_RUNS.mkdir(exist_ok=True)
            carimbo = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            arq = PASTA_RUNS / f"{carimbo}_{Path(res.documento).stem}.jsonl"
            with open(arq, "w", encoding="utf-8") as f:
                for p in res.trilha:
                    f.write(p.model_dump_json() + "\n")
                f.write(
                    json.dumps(
                        {
                            "resumo": True,
                            "documento": res.documento,
                            "modelo": res.modelo,
                            "versoes_prompt": res.versoes_prompt,
                            "tokens_entrada": res.tokens_entrada,
                            "tokens_saida": res.tokens_saida,
                            "custo_usd": round(res.custo_usd, 5),
                            "latencia_ms": res.latencia_ms,
                            "pendencias": [p.tipo for p in res.pendencias],
                            "alertas": [a.tipo for a in res.alertas],
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        except OSError:
            pass  # a trilha é auxiliar; falha de disco não derruba a análise


def _resumo_erro(e: Exception) -> str:
    if isinstance(e, ValidationError):
        partes = []
        for err in e.errors()[:12]:
            loc = ".".join(str(x) for x in err["loc"])
            partes.append(f"{loc}: {err['msg']}")
        return "JSON fora do formato: " + "; ".join(partes)
    return f"resposta inválida: {e}"
