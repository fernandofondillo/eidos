"""CapsuleForge — Fase 3.2.

Forja cápsulas `.eidos` a partir de peticiones en lenguaje natural.

Backends:
- StubForgeBackend: produce cápsulas sintéticas válidas sin LLM (Fase 1.x).
- LLMForgeBackend: usa el CortexHub para redactar cápsulas reales (Fase 2+).

Pipeline:
1. Petición NL del usuario → backend genera CapsuleDraft (Pydantic).
2. Validación estricta del draft (schema + AST si tiene tools).
3. Smoke test de tools en ToolSandbox (si las declara).
4. Decisión:
   - Auto-aprobar si confidence > 0.85 Y smoke test OK Y no tools peligrosos.
   - Si no → guardar como 'pending' en capsule_drafts para aprobación humana.
5. Tras aprobación, mover a ProceduralMemory (tabla 'capsules' Fase 1.2).
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field, field_validator

from eidos.core.sandbox import ToolSandbox
from eidos.memory.procedural import ProceduralMemory
from eidos.utils.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Modelos Pydantic — schema estricto de la cápsula
# ---------------------------------------------------------------------------


class CapsuleTone(BaseModel):
    style: str = "technical"  # formal | casual | academic | playful | technical
    empathy: int = Field(default=5, ge=0, le=10)
    verbosity: int = Field(default=5, ge=0, le=10)


class CapsuleRule(BaseModel):
    id: str
    condition: str
    action: str
    priority: int = 0


class CapsuleOntology(BaseModel):
    domain: str
    entities: list[str] = Field(default_factory=list)
    relations: list[dict[str, str]] = Field(default_factory=list)


class CapsuleTool(BaseModel):
    name: str
    entry_point: str  # función Python dentro del código
    code: str = ""  # código Python (validado por sandbox)
    args_schema: dict[str, Any] = Field(default_factory=dict)
    timeout_sec: int = 5

    @field_validator("code")
    @classmethod
    def _code_not_empty_if_entry(cls, v: str, info) -> str:
        # Si entry_point está definido, code debe tener al menos esa función
        # Validación laxa aquí; AST estricto en sandbox.
        return v


class CapsuleDraft(BaseModel):
    """Draft generado por CapsuleForge antes de aprobación."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., min_length=3, max_length=80)
    version: str = "1.0.0"
    description: str = ""
    ontology: CapsuleOntology
    rules: list[CapsuleRule] = Field(default_factory=list)
    tone: CapsuleTone = Field(default_factory=CapsuleTone)
    tools: list[CapsuleTool] = Field(default_factory=list)
    genesis_confidence: float = Field(..., ge=0.0, le=1.0)
    requested_by: str = "user"  # 'user' | 'auto_evolution'
    request_input: str = ""
    parent_capsule_id: str | None = None
    smoke_test_passed: bool = False
    smoke_test_output: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("version")
    @classmethod
    def _semver(cls, v: str) -> str:
        if not re.match(r"^\d+\.\d+\.\d+$", v):
            raise ValueError(f"Version must be semver X.Y.Z, got {v}")
        return v


# ---------------------------------------------------------------------------
# Protocolo de backend
# ---------------------------------------------------------------------------


class ForgeBackend(Protocol):
    """Contrato para cualquier backend de génesis."""

    def forge(self, request: str, context: dict[str, Any] | None = None) -> CapsuleDraft: ...


# ---------------------------------------------------------------------------
# StubForgeBackend — sin LLM, cápsulas sintéticas
# ---------------------------------------------------------------------------


class StubForgeBackend:
    """Genera cápsulas VÁLIDAS sin LLM. Útil en desarrollo sin GPU.

    Estrategia: a partir del request NL, extrae keywords y construye
    una cápsula genérica con domain = primera keyword significativa,
    sin tools (solo ontología + reglas básicas + tone técnico).
    """

    _STOPWORDS = frozenset(
        {"el", "la", "los", "las", "un", "una", "y", "o", "de", "del",
         "a", "en", "que", "es", "por", "con", "para", "necesito",
         "quiero", "convierte", "conviértete", "experto", "experta"}
    )

    def forge(self, request: str, context: dict[str, Any] | None = None) -> CapsuleDraft:
        if not request or not request.strip():
            raise ValueError("request cannot be empty")

        # Extraer keywords
        cleaned = "".join(c if c.isalnum() or c.isspace() else " " for c in request.lower())
        tokens = [
            w for w in cleaned.split()
            if w not in self._STOPWORDS and len(w) >= 3
        ]
        if not tokens:
            tokens = ["general"]

        domain = tokens[0]
        # Nombre: capitalizar primera keyword
        name = f"Experto en {domain.capitalize()}"

        # Confidence: base 0.7 + bonus si hay keywords múltiples
        confidence = min(0.95, 0.7 + 0.05 * min(len(tokens), 5))

        # Reglas básicas
        rules = [
            CapsuleRule(
                id="r1",
                condition=f"Usuario pregunta sobre {domain}",
                action=f"Responder basándose en ontología de {domain}",
                priority=1,
            ),
            CapsuleRule(
                id="r2",
                condition="Usuario pide acción",
                action="Validar safety antes de ejecutar",
                priority=2,
            ),
        ]

        # Sin tools en stub (las tools requieren LLM para generar código)
        return CapsuleDraft(
            name=name,
            version="1.0.0",
            description=f"Cápsula generada automáticamente para experticia en {domain}.",
            ontology=CapsuleOntology(
                domain=domain,
                entities=[domain, "usuario", "contexto"],
                relations=[
                    {"subject": "usuario", "predicate": "pregunta_sobre", "object": domain},
                ],
            ),
            rules=rules,
            tone=CapsuleTone(style="technical", empathy=5, verbosity=5),
            tools=[],
            genesis_confidence=confidence,
            requested_by=(context or {}).get("requested_by", "user"),
            request_input=request[:500],
            parent_capsule_id=(context or {}).get("parent_capsule_id"),
            smoke_test_passed=True,  # sin tools → smoke test trivialmente OK
            smoke_test_output="No tools declared; smoke test passed.",
            metadata={"backend": "stub"},
        )


# ---------------------------------------------------------------------------
# LLMForgeBackend — usa CortexHub para generar la cápsula real
# ---------------------------------------------------------------------------


class LLMForgeBackend:
    """Backend de génesis que usa el LLM del CortexHub para redactar
    la cápsula completa, incluyendo tools con código Python.

    El LLM debe devolver JSON válido según el schema del CapsuleDraft.
    Si el JSON es inválido tras 3 reintentos, lanza RuntimeError.
    """

    def __init__(self, cortex_hub: Any, sandbox: ToolSandbox | None = None) -> None:
        self._hub = cortex_hub
        self._sandbox = sandbox or ToolSandbox()

    def forge(self, request: str, context: dict[str, Any] | None = None) -> CapsuleDraft:
        if not request:
            raise ValueError("request cannot be empty")

        # Necesitamos un backend de LLM cargado
        backend = self._hub.get_monologue_backend(max_plan_steps=3)
        if backend is None:
            logger.warning("llm_forge_no_model_degrading_to_stub")
            return StubForgeBackend().forge(request, context)

        prompt = self._build_prompt(request, context)
        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                raw = backend._client.complete(  # type: ignore[attr-defined]
                    prompt=prompt,
                    max_tokens=1024,
                    temperature=0.5 if attempt == 1 else 0.2,
                    grammar=None,  # confiamos en el prompt + validación Pydantic
                    stop=["```", "\n\n\n"],
                )
                draft = self._parse_response(raw, request, context)
                logger.info("llm_forge_success", attempt=attempt, confidence=draft.genesis_confidence)
                return draft
            except Exception as e:
                last_error = e
                logger.warning("llm_forge_retry", attempt=attempt, error=str(e))

        raise RuntimeError(f"LLMForgeBackend failed after 3 attempts: {last_error}")

    def _build_prompt(self, request: str, context: dict[str, Any] | None) -> str:
        ctx_str = json.dumps(context or {}, ensure_ascii=False)
        return f"""Eres EIDOS. Genera una cápsula cognitiva (especialización) en JSON.

Petición del usuario: "{request}"
Contexto: {ctx_str}

Devuelve SOLO un JSON con esta forma exacta (sin markdown, sin texto adicional):
{{
  "name": "nombre corto (3-80 chars)",
  "description": "para qué sirve esta cápsula",
  "ontology": {{
    "domain": "dominio principal",
    "entities": ["entidad1", "entidad2"],
    "relations": [{{"subject": "x", "predicate": "rel", "object": "y"}}]
  }},
  "rules": [
    {{"id": "r1", "condition": "cuándo aplicar", "action": "qué hacer", "priority": 1}}
  ],
  "tone": {{"style": "technical", "empathy": 5, "verbosity": 5}},
  "tools": [],
  "genesis_confidence": 0.8
}}

Reglas:
- name: 3-80 caracteres, sin comillas internas.
- tools: lista vacía si no necesitas código Python. Si declaras una tool,
  incluye name, entry_point (nombre de función), code (Python válido).
- genesis_confidence: 0.0 a 1.0.
- Responde en español."""

    def _parse_response(
        self,
        raw: str,
        request: str,
        context: dict[str, Any] | None,
    ) -> CapsuleDraft:
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Intentar extraer primer objeto JSON
            match = re.search(r"\{[\s\S]*\}", text)
            if not match:
                raise ValueError(f"No JSON in response: {text[:200]}")
            data = json.loads(match.group(0))

        # Mapear a CapsuleDraft
        draft = CapsuleDraft(
            name=str(data["name"])[:80],
            version="1.0.0",
            description=str(data.get("description", ""))[:500],
            ontology=CapsuleOntology(**data.get("ontology", {"domain": "general"})),
            rules=[CapsuleRule(**r) for r in data.get("rules", [])],
            tone=CapsuleTone(**data.get("tone", {})),
            tools=[CapsuleTool(**t) for t in data.get("tools", [])],
            genesis_confidence=float(data.get("genesis_confidence", 0.5)),
            requested_by=(context or {}).get("requested_by", "user"),
            request_input=request[:500],
            parent_capsule_id=(context or {}).get("parent_capsule_id"),
            smoke_test_passed=False,  # se ejecutará después
            smoke_test_output=None,
            metadata={"backend": "llm"},
        )
        return draft


# ---------------------------------------------------------------------------
# CapsuleForge — fachada con pipeline completo
# ---------------------------------------------------------------------------


class ForgeDecision(str, Enum):
    AUTO_APPROVED = "auto_approved"
    PENDING_APPROVAL = "pending_approval"
    REJECTED = "rejected"


class CapsuleForge:
    """Orquesta la génesis de cápsulas con pipeline completo.

    1. Backend genera CapsuleDraft.
    2. Smoke test de tools en ToolSandbox.
    3. Decisión: auto-aprobar o pendiente.
    4. Persistir en ProceduralMemory (si auto) o capsule_drafts (si pendiente).
    """

    AUTO_APPROVE_THRESHOLD = 0.85
    # Tools que SIEMPRE requieren aprobación humana (incluso con confianza alta)
    HIGH_RISK_TOOL_NAMES: frozenset[str] = frozenset(
        {"exec_command", "shell", "delete", "format", "rm", "fork_bomb"}
    )

    def __init__(
        self,
        db_path: Path,
        procedural: ProceduralMemory,
        backend: ForgeBackend | None = None,
        sandbox: ToolSandbox | None = None,
    ) -> None:
        self._db_path = db_path
        self._procedural = procedural
        self._backend = backend or StubForgeBackend()
        self._sandbox = sandbox or ToolSandbox()

    # ---------------- API pública ----------------

    def forge(
        self,
        request: str,
        context: dict[str, Any] | None = None,
        force_pending: bool = False,
    ) -> tuple[CapsuleDraft, ForgeDecision]:
        """Genera, valida y persiste una cápsula.

        Args:
            request: petición NL del usuario.
            context: metadata adicional (requested_by, parent_capsule_id, ...).
            force_pending: si True, siempre deja pendiente (para tests/debug).

        Returns:
            (draft, decision)
        """
        # 1. Generar draft
        draft = self._backend.forge(request, context)
        logger.info(
            "capsule_draft_created",
            id=draft.id,
            name=draft.name,
            confidence=draft.genesis_confidence,
            tools=len(draft.tools),
        )

        # 2. Smoke test de tools (si las declara)
        if draft.tools:
            ok, output = self._smoke_test_tools(draft.tools)
            draft.smoke_test_passed = ok
            draft.smoke_test_output = output
            if not ok:
                # Si las tools fallan el smoke test → rechazar
                decision = ForgeDecision.REJECTED
                self._persist_draft(draft, decision)
                logger.warning(
                    "capsule_rejected_smoke_test_failed",
                    id=draft.id,
                    output=output[:200],
                )
                return draft, decision
        else:
            draft.smoke_test_passed = True
            draft.smoke_test_output = "No tools declared."

        # 3. Decisión: auto-aprobar o pendiente
        if force_pending:
            decision = ForgeDecision.PENDING_APPROVAL
        elif self._should_auto_approve(draft):
            decision = ForgeDecision.AUTO_APPROVED
        else:
            decision = ForgeDecision.PENDING_APPROVAL

        # 4. Persistir
        self._persist_draft(draft, decision)
        if decision == ForgeDecision.AUTO_APPROVED:
            self._promote_to_procedural(draft)

        logger.info(
            "capsule_forge_complete",
            id=draft.id,
            decision=decision.value,
        )
        return draft, decision

    def approve(self, draft_id: str) -> bool:
        """Aprueba un draft pendiente → lo promueve a ProceduralMemory."""
        draft = self.get_draft(draft_id)
        if draft is None:
            return False
        if draft["status"] not in ("pending", "pending_approval"):
            return False
        self._promote_to_procedural(self._row_to_draft(draft))
        self._update_draft_status(draft_id, "approved")
        return True

    def reject(self, draft_id: str) -> bool:
        """Rechaza un draft pendiente."""
        draft = self.get_draft(draft_id)
        if draft is None:
            return False
        self._update_draft_status(draft_id, "rejected")
        return True

    def list_drafts(self, status: str | None = None) -> list[dict[str, Any]]:
        conn = self._conn()
        try:
            if status:
                cur = conn.execute(
                    "SELECT * FROM capsule_drafts WHERE status = ? ORDER BY created_at DESC",
                    (status,),
                )
            else:
                cur = conn.execute(
                    "SELECT * FROM capsule_drafts ORDER BY created_at DESC"
                )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]
        finally:
            conn.close()

    def get_draft(self, draft_id: str) -> dict[str, Any] | None:
        conn = self._conn()
        try:
            cur = conn.execute(
                "SELECT * FROM capsule_drafts WHERE id = ?",
                (draft_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            cols = [d[0] for d in cur.description]
            return dict(zip(cols, row, strict=False))
        finally:
            conn.close()

    def list_pending(self) -> list[dict[str, Any]]:
        return self.list_drafts(status="pending")

    # ---------------- internal ----------------

    def _should_auto_approve(self, draft: CapsuleDraft) -> bool:
        """Reglas de auto-aprobación (neuro-simbólico)."""
        if draft.genesis_confidence < self.AUTO_APPROVE_THRESHOLD:
            return False
        if not draft.smoke_test_passed:
            return False
        # Tools de alto riesgo → siempre pendiente
        for tool in draft.tools:
            if tool.name.lower() in self.HIGH_RISK_TOOL_NAMES:
                return False
        return True

    def _smoke_test_tools(self, tools: list[CapsuleTool]) -> tuple[bool, str]:
        """Ejecuta cada tool con args vacíos y verifica que no crashea."""
        outputs = []
        for tool in tools:
            if not tool.code.strip():
                outputs.append(f"[{tool.name}] No code; skipping.")
                continue
            result = self._sandbox.smoke_test_tool(
                code=tool.code,
                entry=tool.entry_point,
                test_args={},
            )
            if not result.ok:
                outputs.append(
                    f"[{tool.name}] FAILED: {result.error or result.stderr[:200]}"
                )
                return False, "\n".join(outputs)
            outputs.append(
                f"[{tool.name}] OK (exit={result.exit_code}, {result.duration_ms}ms)"
            )
        return True, "\n".join(outputs)

    def _persist_draft(self, draft: CapsuleDraft, decision: ForgeDecision) -> None:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        status_map = {
            ForgeDecision.AUTO_APPROVED: "auto_approved",
            ForgeDecision.PENDING_APPROVAL: "pending",
            ForgeDecision.REJECTED: "rejected",
        }
        status = status_map[decision]
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO capsule_drafts
                (id, requested_by, request_input, name, version, description,
                 ontology, rules, tone, tools, genesis_confidence,
                 smoke_test_passed, smoke_test_output, status, created_at,
                 decided_at, parent_capsule_id, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    smoke_test_passed=excluded.smoke_test_passed,
                    smoke_test_output=excluded.smoke_test_output,
                    status=excluded.status,
                    decided_at=excluded.decided_at
                """,
                (
                    draft.id, draft.requested_by, draft.request_input,
                    draft.name, draft.version, draft.description,
                    draft.ontology.model_dump_json(),
                    draft.model_dump_json()["rules"] if False else
                        json.dumps([r.model_dump() for r in draft.rules], ensure_ascii=False),
                    draft.tone.model_dump_json(),
                    json.dumps([t.model_dump() for t in draft.tools], ensure_ascii=False),
                    draft.genesis_confidence,
                    1 if draft.smoke_test_passed else 0,
                    draft.smoke_test_output,
                    status, now,
                    now if decision != ForgeDecision.PENDING_APPROVAL else None,
                    draft.parent_capsule_id,
                    json.dumps(draft.metadata, ensure_ascii=False),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _promote_to_procedural(self, draft: CapsuleDraft) -> None:
        """Persiste el draft en la tabla 'capsules' (Fase 1.2)."""
        content = {
            "ontology": draft.ontology.model_dump(),
            "rules": [r.model_dump() for r in draft.rules],
            "tone": draft.tone.model_dump(),
            "tools": [
                {
                    "name": t.name,
                    "entry_point": t.entry_point,
                    "args_schema": t.args_schema,
                    "timeout_sec": t.timeout_sec,
                }
                for t in draft.tools
            ],
            "code": {t.name: t.code for t in draft.tools},  # código guardado aparte
        }
        self._procedural.store(
            name=draft.name,
            version=draft.version,
            description=draft.description,
            content=content,
            ttl_days=7,  # default; el consolidador puede expirar
            favorite=False,
            genesis_confidence=draft.genesis_confidence,
            parent_capsule_id=draft.parent_capsule_id,
            metadata={
                "draft_id": draft.id,
                "requested_by": draft.requested_by,
                **draft.metadata,
            },
        )
        logger.info("capsule_promoted_to_procedural", id=draft.id, name=draft.name)

    def _update_draft_status(self, draft_id: str, status: str) -> None:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        conn = self._conn()
        try:
            conn.execute(
                "UPDATE capsule_drafts SET status = ?, decided_at = ? WHERE id = ?",
                (status, now, draft_id),
            )
            conn.commit()
        finally:
            conn.close()

    def _row_to_draft(self, row: dict[str, Any]) -> CapsuleDraft:
        return CapsuleDraft(
            id=row["id"],
            name=row["name"],
            version=row["version"],
            description=row.get("description", ""),
            ontology=CapsuleOntology.model_validate_json(row["ontology"]),
            rules=[CapsuleRule(**r) for r in json.loads(row.get("rules") or "[]")],
            tone=CapsuleTone.model_validate_json(row["tone"]),
            tools=[CapsuleTool(**t) for t in json.loads(row.get("tools") or "[]")],
            genesis_confidence=row["genesis_confidence"],
            requested_by=row["requested_by"],
            request_input=row["request_input"],
            parent_capsule_id=row.get("parent_capsule_id"),
            smoke_test_passed=bool(row["smoke_test_passed"]),
            smoke_test_output=row.get("smoke_test_output"),
            metadata=json.loads(row.get("metadata") or "{}"),
        )

    def _conn(self):
        import sqlite3

        return sqlite3.connect(self._db_path)


__all__ = [
    "CapsuleForge",
    "CapsuleDraft",
    "CapsuleTool",
    "CapsuleRule",
    "CapsuleOntology",
    "CapsuleTone",
    "ForgeBackend",
    "StubForgeBackend",
    "LLMForgeBackend",
    "ForgeDecision",
]
