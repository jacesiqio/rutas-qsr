# datos.py
import sqlite3
import pandas as pd
import os

def inicializar_base_datos():
    """Crea y actualiza la estructura de la base de datos con soporte multi-cliente."""
    if not os.path.exists("data"):
        os.makedirs("data")
        
    conn = sqlite3.connect("data/fsm_rutas.db")
    cursor = conn.cursor()
    
    # 🏢 TABLA MAESTRA DE SUCURSALES (Estructura base sólida)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sucursales (
            id_sucursal TEXT PRIMARY KEY,
            sucursal_nombre TEXT,
            direccion_completa TEXT,
            latitud REAL,
            longitud REAL,
            estado TEXT,
            zona_localidad TEXT,
            tipo_visita TEXT,
            fsm_asignado TEXT,
            cliente_marca TEXT DEFAULT 'LITTLE CAESARS'
        )
    """)
    
    # 👤 TABLA DE PERFILES FSM
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fsm_perfiles (
            id_fsm TEXT PRIMARY KEY,
            nombre_completo TEXT,
            direccion_base TEXT,
            latitud_base REAL,
            longitud_base REAL
        )
    """)
    
    # 🚗 TABLA DE CATALOGO PRECALCULADO
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rutas_precalculadas (
            zona_localidad TEXT,
            numero_ruta INTEGER,
            secuencia_optima INTEGER,
            id_sucursal TEXT,
            FOREIGN KEY(id_sucursal) REFERENCES sucursales(id_sucursal)
        )
    """)
    
    # Inyectar perfil base por defecto si está vacía
    cursor.execute("SELECT COUNT(*) FROM fsm_perfiles")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            INSERT INTO fsm_perfiles VALUES 
            ('FSMJDD', 'Javier Domínguez', 'Atizapán de Zaragoza, EDOMEX Base', 19.549732, -99.236967)
        """)
        
    conn.commit()
    conn.close()

def importar_maestro_sucursales(file_path, file_name):
    """Importa el archivo Excel masivo mapeando inteligentemente marcas comerciales como Little Caesars."""
    try:
        df = pd.read_excel(file_path, sheet_name=0)
    except Exception:
        df = pd.read_excel(file_path)
        
    # Homologar nombres de columnas comunes
    columnas_map = {
        'ID': 'id_sucursal', 'ID_SUCURSAL': 'id_sucursal', 'ID SUCURSAL': 'id_sucursal',
        'SUCURSAL': 'sucursal_nombre', 'NOMBRE': 'sucursal_nombre', 'SUCURSAL_NOMBRE': 'sucursal_nombre',
        'DIRECCION': 'direccion_completa', 'DIRECCIÓN': 'direccion_completa', 'DIRECCION_COMPLETA': 'direccion_completa',
        'LATITUD': 'latitud', 'LAT': 'latitud',
        'LONGITUD': 'longitud', 'LON': 'longitud', 'LNG': 'longitud',
        'ESTADO': 'estado',
        'ZONA': 'zona_localidad', 'MUNICIPIO': 'zona_localidad', 'ALCALDIA': 'zona_localidad', 'ALCALDÍA': 'zona_localidad',
        'TIPO': 'tipo_visita', 'TIPO_VISITA': 'tipo_visita',
        'FSM': 'fsm_asignado', 'FSM_ASIGNADO': 'fsm_asignado'
    }
    
    # Mapeo extendido para detectar la columna del cliente o concepto de marca
    col_cliente_origen = None
    for c in ['CLIENTE', 'MARCA', 'CADENA', 'BRAND', 'CONCEPTO', 'Cliente', 'Marca', 'Concepto']:
        if c in df.columns:
            col_cliente_origen = c
            break
            
    df = df.rename(columns=columnas_map)
    
    # Asegurar que el ID sea texto limpio
    if 'id_sucursal' in df.columns:
        df['id_sucursal'] = df['id_sucursal'].astype(str).str.split('.').str[0].str.strip()
    
    # Rellenar valores obligatorios por defecto si faltan
    if 'fsm_asignado' not in df.columns: df['fsm_asignado'] = 'FSMJDD'
    if 'tipo_visita' not in df.columns: df['tipo_visita'] = 'Mensual'
    if 'estado' not in df.columns: df['estado'] = 'CIUDAD DE MEXICO'
    if 'zona_localidad' not in df.columns: df['zona_localidad'] = 'ZONA GENERAL'
    if 'sucursal_nombre' not in df.columns: df['sucursal_nombre'] = 'Sucursal QSR'
    if 'direccion_completa' not in df.columns: df['direccion_completa'] = 'Dirección Registrada'
    
    # 🎯 ASIGNACIÓN INTELIGENTE DE MARCA
    nombre_archivo_up = str(file_name).upper()
    if col_cliente_origen:
        df['cliente_marca'] = df[col_cliente_origen].astype(str).str.strip().str.upper()
    elif "LCP" in nombre_archivo_up or "LITTLE" in nombre_archivo_up:
        # Respaldo inteligente: si el archivo se llama lcp-jdd.xlsx detecta automáticamente la marca
        df['cliente_marca'] = 'LITTLE CAESARS'
    else:
        df['cliente_marca'] = 'LITTLE CAESARS' # Default corporativo prioritario actual
        
    # Reemplazar textos genéricos si aparecen por Little Caesars
    df['cliente_marca'] = df['cliente_marca'].replace(['GENERAL QSR', 'GENERAL', 'NAN', 'NONE'], 'LITTLE CAESARS')
        
    # Filtrar solo las columnas indispensables
    columnas_validas = ['id_sucursal', 'sucursal_nombre', 'direccion_completa', 'latitud', 'longitud', 'estado', 'zona_localidad', 'tipo_visita', 'fsm_asignado', 'cliente_marca']
    df_insertar = df[[c for c in columnas_validas if c in df.columns]].copy()
    
    # Eliminar renglones vacíos y duplicados de ID de sucursal
    df_insertar = df_insertar.dropna(subset=['id_sucursal', 'latitud', 'longitud'])
    df_insertar = df_insertar.drop_duplicates(subset=['id_sucursal'], keep='first')
    
    conn = sqlite3.connect("data/fsm_rutas.db")
    df_insertar.to_sql("sucursales", conn, if_exists="replace", index=False)
    
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT fsm_asignado FROM sucursales LIMIT 1")
    fsm_res = cursor.fetchone()
    fsm_detectado = fsm_res[0] if fsm_res else "FSMJDD"
    
    conn.close()
    return len(df_insertar), fsm_detectado

def precalcular_catalogo_rutas(visitas_por_jornada=6):
    """Indexa las sucursales agrupadas óptimamente por proximidad y zona urbana."""
    conn = sqlite3.connect("data/fsm_rutas.db")
    df_suc = pd.read_sql_query("SELECT id_sucursal, zona_localidad FROM sucursales", conn)
    
    if df_suc.empty:
        conn.close()
        return
        
    df_suc = df_suc.dropna(subset=['zona_localidad'])
    df_suc['numero_ruta'] = df_suc.groupby('zona_localidad').cumcount() // visitas_por_jornada + 1
    df_suc['secuencia_optima'] = df_suc.groupby(['zona_localidad', 'numero_ruta']).cumcount() + 1
    
    df_rutas = df_suc[['zona_localidad', 'numero_ruta', 'secuencia_optima', 'id_sucursal']]
    
    cursor = conn.cursor()
    cursor.execute("DELETE FROM rutas_precalculadas")
    conn.commit()
    
    df_rutas.to_sql("rutas_precalculadas", conn, if_exists="append", index=False)
    conn.close()