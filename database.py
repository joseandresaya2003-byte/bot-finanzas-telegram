import os
import psycopg2
from urllib.parse import urlparse

DATABASE_URL = os.environ.get("DATABASE_URL", "PON_AQUI_TU_URI_DE_SUPABASE")

def get_connection():
    parsed_url = urlparse(DATABASE_URL)
    return psycopg2.connect(
        database=parsed_url.path[1:],
        user=parsed_url.username,
        password=parsed_url.password,
        host=parsed_url.hostname,
        port=parsed_url.port,
        sslmode='require'
    )

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS gastos (
            id SERIAL PRIMARY KEY,
            monto REAL,
            categoria TEXT,
            descripcion TEXT,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS recordatorios (
            id SERIAL PRIMARY KEY,
            chat_id BIGINT,
            titulo TEXT,
            fecha_hora TEXT,
            completado BOOLEAN DEFAULT FALSE,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    cursor.close()
    conn.close()

def guardar_gasto(monto, categoria, descripcion):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO gastos (monto, categoria, descripcion) VALUES (%s, %s, %s)",
        (monto, categoria, descripcion)
    )
    conn.commit()
    cursor.close()
    conn.close()

def obtener_resumen_mes():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, monto, categoria, descripcion, fecha 
        FROM gastos 
        WHERE TO_CHAR(fecha, 'YYYY-MM') = TO_CHAR(CURRENT_TIMESTAMP, 'YYYY-MM')
        ORDER BY id DESC
    """)
    rows = cursor.fetchall()
    
    cursor.execute("""
        SELECT SUM(monto) 
        FROM gastos 
        WHERE TO_CHAR(fecha, 'YYYY-MM') = TO_CHAR(CURRENT_TIMESTAMP, 'YYYY-MM')
    """)
    res_total = cursor.fetchone()
    total_mes = res_total[0] if res_total[0] is not None else 0.0
    
    cursor.close()
    conn.close()
    return rows, total_mes

def borrar_ultimo_gasto():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM gastos WHERE id = (SELECT MAX(id) FROM gastos)")
    filas_afectadas = cursor.rowcount
    conn.commit()
    cursor.close()
    conn.close()
    return filas_afectadas > 0

def reiniciar_gastos_mes():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM gastos WHERE TO_CHAR(fecha, 'YYYY-MM') = TO_CHAR(CURRENT_TIMESTAMP, 'YYYY-MM')")
    conn.commit()
    cursor.close()
    conn.close()

def guardar_recordatorio(chat_id, titulo, fecha_hora):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO recordatorios (chat_id, titulo, fecha_hora) VALUES (%s, %s, %s)",
        (chat_id, titulo, fecha_hora)
    )
    conn.commit()
    cursor.close()
    conn.close()

def obtener_recordatorios(chat_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, titulo, fecha_hora FROM recordatorios WHERE chat_id = %s AND completado = FALSE ORDER BY id DESC",
        (chat_id,)
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

def completar_recordatorio_por_titulo(chat_id, busqueda):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE recordatorios SET completado = TRUE WHERE chat_id = %s AND LOWER(titulo) LIKE %s AND completado = FALSE",
        (chat_id, f"%{busqueda.lower()}%")
    )
    filas = cursor.rowcount
    conn.commit()
    cursor.close()
    conn.close()
    return filas > 0

def borrar_recordatorio_por_titulo(chat_id, busqueda):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM recordatorios WHERE chat_id = %s AND LOWER(titulo) LIKE %s",
        (chat_id, f"%{busqueda.lower()}%")
    )
    filas = cursor.rowcount
    conn.commit()
    cursor.close()
    conn.close()
    return filas > 0