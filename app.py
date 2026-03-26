from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
import sqlite3
from typing import Optional, List, Any

from fastapi import FastAPI, Request, HTTPException, Body
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, ConfigDict


# =========================================================
# RUTAS BASE
# =========================================================
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "precios.db"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

START_YEAR = 2024

MONTHS_ES = {
    1: "Enero",
    2: "Febrero",
    3: "Marzo",
    4: "Abril",
    5: "Mayo",
    6: "Junio",
    7: "Julio",
    8: "Agosto",
    9: "Septiembre",
    10: "Octubre",
    11: "Noviembre",
    12: "Diciembre",
}

VARIABLE_KEYS = [
    "margen_fcc",
    "margen_visbreaking",
    "lvgo_diesel",
    "lvgo_corte",
]


# =========================================================
# HELPERS
# =========================================================
def now_local() -> datetime:
    return datetime.now()


def get_static_version() -> str:
    """
    Versión simple para romper caché del navegador.
    """
    try:
        latest_mtime = max(
            (BASE_DIR / "app.py").stat().st_mtime,
            (TEMPLATES_DIR / "index.html").stat().st_mtime if (TEMPLATES_DIR / "index.html").exists() else 0,
            (STATIC_DIR / "styles.css").stat().st_mtime if (STATIC_DIR / "styles.css").exists() else 0,
            (STATIC_DIR / "app.js").stat().st_mtime if (STATIC_DIR / "app.js").exists() else 0,
        )
        return str(int(latest_mtime))
    except Exception:
        return str(int(datetime.now().timestamp()))


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS precios_mensuales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                anio INTEGER NOT NULL,
                mes INTEGER NOT NULL,
                margen_fcc REAL,
                margen_visbreaking REAL,
                lvgo_diesel REAL,
                lvgo_corte REAL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(anio, mes)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_precios_anio_mes
            ON precios_mensuales (anio, mes)
            """
        )
        conn.commit()


def validate_year(anio: int) -> None:
    current_year = now_local().year

    if anio < START_YEAR:
        raise HTTPException(
            status_code=400,
            detail=f"El año mínimo permitido es {START_YEAR}."
        )

    if anio > current_year:
        raise HTTPException(
            status_code=400,
            detail="No se permiten años futuros."
        )


def validate_month(mes: int) -> None:
    if mes < 1 or mes > 12:
        raise HTTPException(
            status_code=400,
            detail="El mes debe estar entre 1 y 12."
        )


def is_enabled_month(anio: int, mes: int) -> bool:
    """
    Reglas:
    - años pasados: todos los meses habilitados
    - año actual: solo hasta el mes actual
    - años futuros: no habilitados
    """
    today = now_local()

    if anio < today.year:
        return True

    if anio == today.year:
        return mes <= today.month

    return False


def validate_period(anio: int, mes: int) -> None:
    validate_year(anio)
    validate_month(mes)

    today = now_local()

    # Solo bloquear meses futuros del año actual
    if anio == today.year and mes > today.month:
        raise HTTPException(
            status_code=400,
            detail="No se permiten meses futuros del año actual."
        )


def get_allowed_years() -> List[int]:
    current_year = now_local().year
    return list(range(START_YEAR, current_year + 1))


def safe_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None

    try:
        num = float(value)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail=f"Valor inválido: {value}"
        )

    if num < 0:
        raise HTTPException(
            status_code=400,
            detail="No se permiten valores negativos."
        )

    return num


# =========================================================
# MODELOS
# =========================================================
class PrecioPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    margen_fcc: Optional[float] = Field(default=None)
    margen_visbreaking: Optional[float] = Field(default=None)
    lvgo_diesel: Optional[float] = Field(default=None)
    lvgo_corte: Optional[float] = Field(default=None)


# =========================================================
# ACCESO A DATOS
# =========================================================
def get_precio_mes(anio: int, mes: int) -> dict:
    validate_year(anio)
    validate_month(mes)

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM precios_mensuales
            WHERE anio = ? AND mes = ?
            """,
            (anio, mes),
        ).fetchone()

    if row is None:
        return {
            "anio": anio,
            "mes": mes,
            "mes_nombre": MONTHS_ES[mes],
            "enabled": is_enabled_month(anio, mes),
            "margen_fcc": None,
            "margen_visbreaking": None,
            "lvgo_diesel": None,
            "lvgo_corte": None,
            "created_at": None,
            "updated_at": None,
            "exists": False,
        }

    return {
        "anio": row["anio"],
        "mes": row["mes"],
        "mes_nombre": MONTHS_ES[row["mes"]],
        "enabled": is_enabled_month(row["anio"], row["mes"]),
        "margen_fcc": row["margen_fcc"],
        "margen_visbreaking": row["margen_visbreaking"],
        "lvgo_diesel": row["lvgo_diesel"],
        "lvgo_corte": row["lvgo_corte"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "exists": True,
    }


def get_precios_anio(anio: int) -> dict:
    validate_year(anio)

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM precios_mensuales
            WHERE anio = ?
            ORDER BY mes ASC
            """,
            (anio,),
        ).fetchall()

    rows_by_month = {row["mes"]: row for row in rows}
    meses = []

    for mes in range(1, 13):
        row = rows_by_month.get(mes)

        meses.append(
            {
                "anio": anio,
                "mes": mes,
                "mes_nombre": MONTHS_ES[mes],
                "enabled": is_enabled_month(anio, mes),
                "margen_fcc": row["margen_fcc"] if row else None,
                "margen_visbreaking": row["margen_visbreaking"] if row else None,
                "lvgo_diesel": row["lvgo_diesel"] if row else None,
                "lvgo_corte": row["lvgo_corte"] if row else None,
                "created_at": row["created_at"] if row else None,
                "updated_at": row["updated_at"] if row else None,
                "exists": row is not None,
            }
        )

    return {
        "anio": anio,
        "meses": meses,
    }


def upsert_precio(anio: int, mes: int, payload: PrecioPayload) -> dict:
    validate_period(anio, mes)

    now_str = now_local().strftime("%Y-%m-%d %H:%M:%S")

    with get_conn() as conn:
        existing = conn.execute(
            """
            SELECT id
            FROM precios_mensuales
            WHERE anio = ? AND mes = ?
            """,
            (anio, mes),
        ).fetchone()

        if existing:
            conn.execute(
                """
                UPDATE precios_mensuales
                SET
                    margen_fcc = ?,
                    margen_visbreaking = ?,
                    lvgo_diesel = ?,
                    lvgo_corte = ?,
                    updated_at = ?
                WHERE anio = ? AND mes = ?
                """,
                (
                    payload.margen_fcc,
                    payload.margen_visbreaking,
                    payload.lvgo_diesel,
                    payload.lvgo_corte,
                    now_str,
                    anio,
                    mes,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO precios_mensuales (
                    anio,
                    mes,
                    margen_fcc,
                    margen_visbreaking,
                    lvgo_diesel,
                    lvgo_corte,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    anio,
                    mes,
                    payload.margen_fcc,
                    payload.margen_visbreaking,
                    payload.lvgo_diesel,
                    payload.lvgo_corte,
                    now_str,
                    now_str,
                ),
            )

        conn.commit()

    return get_precio_mes(anio, mes)


def get_dashboard_summary() -> dict:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM precios_mensuales
            ORDER BY anio DESC, mes DESC
            """
        ).fetchall()

    if not rows:
        return {
            "ultimo_anio_cargado": None,
            "ultimo_mes_cargado": None,
            "ultima_actualizacion": None,
            "cantidad_celdas_con_datos": 0,
            "registros_guardados": 0,
        }

    last = rows[0]
    celdas = 0

    for row in rows:
        for key in VARIABLE_KEYS:
            if row[key] is not None:
                celdas += 1

    return {
        "ultimo_anio_cargado": last["anio"],
        "ultimo_mes_cargado": MONTHS_ES[last["mes"]],
        "ultima_actualizacion": last["updated_at"],
        "cantidad_celdas_con_datos": celdas,
        "registros_guardados": len(rows),
    }


# =========================================================
# FASTAPI
# =========================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Precios Mensuales Refinería",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# =========================================================
# VISTAS
# =========================================================
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "static_version": get_static_version(),
        },
    )


# =========================================================
# API
# =========================================================
@app.get("/api/config")
def api_config():
    today = now_local()
    return {
        "start_year": START_YEAR,
        "current_year": today.year,
        "current_month": today.month,
        "allowed_years": get_allowed_years(),
        "months_es": MONTHS_ES,
    }


@app.get("/api/dashboard")
def api_dashboard():
    return get_dashboard_summary()


@app.get("/api/precios")
def api_precios_all():
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM precios_mensuales
            ORDER BY anio DESC, mes DESC
            """
        ).fetchall()

    return {
        "total": len(rows),
        "items": [
            {
                "anio": row["anio"],
                "mes": row["mes"],
                "mes_nombre": MONTHS_ES[row["mes"]],
                "margen_fcc": row["margen_fcc"],
                "margen_visbreaking": row["margen_visbreaking"],
                "lvgo_diesel": row["lvgo_diesel"],
                "lvgo_corte": row["lvgo_corte"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ],
    }


@app.get("/api/precios/{anio}")
def api_precios_anio(anio: int):
    return get_precios_anio(anio)


# IMPORTANTE:
# Esta ruta debe ir ANTES de /api/precios/{anio}/{mes}
# para que "guardar-todo" no sea interpretado como si fuera {mes}.
@app.post("/api/precios/{anio}/guardar-todo")
def api_guardar_todo(anio: int, payload: dict = Body(...)):
    validate_year(anio)

    meses = payload.get("meses")
    if not isinstance(meses, list):
        raise HTTPException(
            status_code=400,
            detail="El payload debe contener una lista 'meses'."
        )

    saved = 0

    for item in meses:
        if not isinstance(item, dict):
            raise HTTPException(
                status_code=400,
                detail="Cada elemento de 'meses' debe ser un objeto."
            )

        mes = item.get("mes")
        if mes is None:
            raise HTTPException(
                status_code=400,
                detail="Cada elemento debe incluir 'mes'."
            )

        mes = int(mes)
        validate_period(anio, mes)

        body = PrecioPayload(
            margen_fcc=safe_float(item.get("margen_fcc")),
            margen_visbreaking=safe_float(item.get("margen_visbreaking")),
            lvgo_diesel=safe_float(item.get("lvgo_diesel")),
            lvgo_corte=safe_float(item.get("lvgo_corte")),
        )

        upsert_precio(anio, mes, body)
        saved += 1

    return {
        "ok": True,
        "message": f"Se guardaron {saved} meses correctamente."
    }


@app.get("/api/precios/{anio}/{mes}")
def api_precios_mes(anio: int, mes: int):
    return get_precio_mes(anio, mes)


@app.post("/api/precios/{anio}/{mes}")
def api_guardar_mes(anio: int, mes: int, payload: PrecioPayload):
    data = upsert_precio(anio, mes, payload)
    return {
        "ok": True,
        "message": "Datos guardados correctamente.",
        "data": data,
    }


# =========================================================
# MANEJO DE ERRORES
# =========================================================
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "ok": False,
            "detail": exc.detail,
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "ok": False,
            "detail": f"Error interno del servidor: {str(exc)}",
        },
    )