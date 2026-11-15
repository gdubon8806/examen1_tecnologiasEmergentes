"""
Asistente analitico seguro: pregunta -> plan (reglas o modelo) -> herramientas aprobadas -> hechos
deterministas -> (opcional) interpretacion del modelo -> verificacion de cifras.
Garantias: sin SQL libre, sin cifras inventadas sin aviso, reconoce cuando no hay datos.
"""
import os
import time

from .llm import LLMError
from .planner import HELP, llm_plan, rule_plan
from .render import describe, template_answer
from .tools import TOOLS, UnknownEntity, load_meta, validate_call
from .verify import unverified_numbers

INTERPRET_SYSTEM = """Eres un analista de datos. Responde en espanol, en maximo 120 palabras.
REGLAS: usa SOLO las cifras de 'Datos consultados'; no inventes ni calcules cifras nuevas; menciona siempre el periodo;
si los datos son una PREDICCION, dilo explicitamente; separa lo que dicen los datos de tu interpretacion;
si los datos no alcanzan para responder, di que no hay informacion suficiente."""


def _response(status, answer, **kw):
    base = {"status": status, "answer": answer, "interpretation_by": None, "facts": [], "is_prediction": False,
            "assumptions": [], "warnings": [], "sources": [], "provider": None, "unverified": [], "tools": []}
    base.update(kw)
    return base


def answer_question(question: str, ctx: dict, provider=None, planner_mode: str | None = None) -> dict:
    """ctx = {"db": objeto con run()/one()}. provider = None (solo reglas) o un Provider de llm.py.
    planner_mode (o ASSISTANT_PLANNER en .env):
      rules  (por defecto) las REGLAS deciden que consultar; el modelo solo redacta la interpretacion.
      hybrid reglas primero; si no entienden la pregunta, el modelo propone un plan (validado).
      llm    el modelo propone siempre el plan (validado); las reglas son respaldo."""
    mode = (planner_mode or os.getenv("ASSISTANT_PLANNER", "rules")).strip().lower()
    question = (question or "").strip()[:500]
    meta = load_meta(ctx["db"])
    ctx2 = {**ctx, **meta}
    warnings, prov_name = [], (provider.name if provider else "reglas (sin modelo de lenguaje)")
    base = {"provider": prov_name, "planner": mode, "data_range": [str(meta["data_min"]), str(meta["data_max"])],
            "data_as_of": str(meta["last_update"]) if meta["last_update"] else None}

    rp = rule_plan(question, meta)
    calls = None
    if rp["reason"] == "unknown_entity":
        return _response("NO_DATA", rp["message"], **base)
    use_llm_plan = provider is not None and (
        mode == "llm" or (mode == "hybrid" and not rp["calls"] and rp["reason"] == "out_of_scope"))
    if use_llm_plan:
        try:
            calls = llm_plan(provider, question, meta) or None
        except (LLMError, ValueError, KeyError) as exc:
            warnings.append(f"El modelo no pudo interpretar la pregunta ({exc}); se usaron reglas.")
    if not calls:
        calls = rp["calls"]
    if not calls:
        return _response("OUT_OF_SCOPE", rp["message"] or HELP, warnings=warnings, **base)

    results, validated = [], []
    try:
        for c in calls:
            try:
                v = validate_call(c, meta)
            except ValueError:
                if provider and calls is not rp["calls"] and rp["calls"]:      # plan del modelo invalido -> reglas
                    calls, results, validated = rp["calls"], [], []
                    warnings.append("El plan propuesto por el modelo no era valido; se usaron reglas.")
                    for c2 in calls:
                        validated.append(validate_call(c2, meta))
                    break
                raise
            validated.append(v)
        for v in validated:
            if provider and provider.external and v["params"].get("dimension") == "customer":
                return _response("OUT_OF_SCOPE", "Por privacidad, el desglose por cliente no se consulta con modelos "
                                 "externos. Prueba con grupo de producto, categoría de cliente o territorio.", warnings=warnings, **base)
            results.append(TOOLS[v["tool"]][0](v["params"], ctx2))
    except UnknownEntity as exc:
        return _response("NO_DATA", str(exc), warnings=warnings, **base)
    except ValueError:
        return _response("OUT_OF_SCOPE", "No pude interpretar esa pregunta con las herramientas disponibles. " + HELP,
                         warnings=warnings, **base)

    useful = [r for r in results if not r["empty"]]
    if not useful:
        per = next((r["period"] for r in results if r.get("period")), None)
        where = f" para {per['label']} ({per['date_from']} a {per['date_to']})" if per else ""
        return _response("NO_DATA", f"No hay datos suficientes{where}. Los datos de ventas disponibles van de "
                         f"{meta['data_min']} a {meta['data_max']}.", warnings=warnings,
                         tools=[r["tool"] for r in results], **base)

    facts = [line for r in useful for line in describe(r)]
    assumptions = []
    for v, r in zip(validated, results):
        if v["assumed_period"] and r.get("period") and not r["empty"]:
            assumptions.append(f"No indicaste el periodo: se usó {r['period']['label']} "
                               f"({r['period']['date_from']} a {r['period']['date_to']}).")
        if r.get("period") and r["period"]["partial"] and not r["empty"]:
            warnings.append(f"El periodo pedido va más allá de los datos disponibles (hasta {meta['data_max']}): "
                            "se muestran solo los datos existentes.")

    interpretation, by, unverified = None, None, []
    if provider:
        try:
            user = f"Pregunta: {question}\n\nDatos consultados (unicas cifras permitidas):\n" + "\n".join("- " + f for f in facts)
            interpretation = provider.chat(INTERPRET_SYSTEM, user, max_tokens=350).strip()
            by = provider.name
            unverified = unverified_numbers(interpretation, useful, facts)
            if unverified:
                warnings.append("Algunas cifras del texto generado no se pudieron verificar contra los datos consultados: "
                                + ", ".join(unverified) + ". Confía en la sección «Datos consultados».")
        except LLMError as exc:
            warnings.append(f"El modelo de lenguaje no respondió ({exc}); se muestran solo los datos consultados.")
    answer = interpretation or template_answer(useful, facts)
    return _response("ANSWERED", answer, interpretation_by=by, facts=facts,
                     is_prediction=any(r["kind"] == "prediction" for r in useful), assumptions=assumptions,
                     warnings=warnings, unverified=unverified, tools=[r["tool"] for r in useful],
                     sources=[{"tool": r["tool"], "title": r["title"], "kind": r["kind"], "period": r.get("period"),
                               "filters": r["filters"], "data": r["data"]} for r in useful], **base)
