#!/usr/bin/env python3
"""Limpia todas las cápsulas basura generadas por la regex rota.

Uso:
    cd /Volumes/EIDOS_SSD/eidos
    .eidos_env/venv/bin/python scripts/purge_capsules.py
"""
import sys
import sqlite3
from pathlib import Path

EIDOS_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = EIDOS_ROOT / "data" / "eidos.db"
CAPSULES_DIR = EIDOS_ROOT / "data" / "capsules"

# Palabras que NUNCA deben ser especializaciones
BLACKLIST = {
    "hola", "julio", "eres", "esta", "este", "búsqueda", "internet",
    "general", "eidos", "recuerdas", "como", "qué", "quién", "dónde",
    "cuándo", "por", "para", "con", "sin", "sobre", "después", "antes",
    "hoy", "ayer", "ahora", "luego", "aquí", "allí", "todo", "nada",
    "algo", "alguien", "nadie", "uno", "dos", "tres", "brent",
    "cotización", "precio", "dame", "dime", "haz", "crea", "voy",
    "tengo", "quiero", "necesito", "puedes", "puede", "ser", "estar",
    "tener", "hacer", "decir", "ver", "dar", "saber", "querer",
    "pensar", "creer", "sentir", "vivir", "morir", "abrir", "cerrar",
}

def main():
    if not DB_PATH.exists():
        print("❌ No se encontró data/eidos.db")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    # Listar todas las cápsulas
    cur.execute("SELECT id, name FROM capsules")
    rows = cur.fetchall()
    print(f"Total de cápsulas antes de limpieza: {len(rows)}")

    deleted = 0
    for cid, name in rows:
        name_lower = name.lower()
        # Extraer el tema (quitar "Experto en " / "Herramienta: ")
        topic = name_lower
        for prefix in ("experto en ", "experta en ", "experto ", "experta ", "herramienta: "):
            if topic.startswith(prefix):
                topic = topic[len(prefix):]
                break
        topic = topic.strip()

        # Si el tema está en la blacklist o es una sola palabra genérica
        should_delete = False
        if topic in BLACKLIST:
            should_delete = True
        elif len(topic) <= 4 and topic not in {"rust", "python", "java", "ruby", "swift", "kotlin", "docker"}:
            should_delete = True
        elif topic in {"brent", "julio", "como", "eres", "esta"}:
            should_delete = True

        if should_delete:
            print(f"  ✗ Eliminando: {name} (tema: '{topic}')")
            # Borrar de la DB
            cur.execute("DELETE FROM capsules WHERE id = ?", (cid,))
            # Borrar el archivo .eidos si existe
            for f in CAPSULES_DIR.glob("*.eidos"):
                if cid in f.name:
                    f.unlink()
                    break
            deleted += 1
        else:
            print(f"  ✓ Manteniendo: {name}")

    # También limpiar drafts basura
    cur.execute("SELECT id, name FROM capsule_drafts")
    draft_rows = cur.fetchall()
    for did, dname in draft_rows:
        topic = dname.lower()
        for prefix in ("experto en ", "experta en ", "experto ", "herramienta: "):
            if topic.startswith(prefix):
                topic = topic[len(prefix):]
                break
        topic = topic.strip()
        if topic in BLACKLIST or (len(topic) <= 4 and topic not in {"rust", "python"}):
            cur.execute("DELETE FROM capsule_drafts WHERE id = ?", (did,))
            deleted += 1

    conn.commit()
    conn.close()

    # Contar restantes
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM capsules")
    remaining = cur.fetchone()[0]
    conn.close()

    print(f"\n✅ Limpieza completada: {deleted} cápsulas/drafts eliminados.")
    print(f"   Cápsulas restantes: {remaining}")

if __name__ == "__main__":
    main()
