# app.py
import sys
import os
# Parche de compatibilidad de rutas para despliegue en la nube (GitHub/Streamlit Cloud)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
import sqlite3
import pandas as pd
import requests

# 📦 AUTO-INSTALADOR INTELIGENTE DE LIBRERÍAS DE MAPAS
try:
    import folium
    from streamlit_folium import st_folium
except ImportError:
    import subprocess
    with st.spinner("🔧 Configurando componentes cartográficos corporativos... Espere un momento."):
        subprocess.check_call([sys.executable, "-m", "pip", "install", "streamlit-folium", "folium"])
    import folium
    from streamlit_folium import st_folium

from datos import inicializar_base_datos, importar_maestro_sucursales, precalcular_catalogo_rutas
from core.simulacion import simular_ruta_del_dia

# Configuración responsiva para Web y Móvil
st.set_page_config(page_title="RUTAS-QSR Dashboard", layout="wide", initial_sidebar_state="expanded")
inicializar_base_datos()

# Custom CSS avanzado para inyectar la identidad visual de Ecolab y optimización móvil responsiva
st.markdown("""
    <style>
    /* Estilos generales corporativos */
    .main h1 { color: #002F6C; font-weight: 700; font-size: 1.8rem; }
    .stButton>button {
        background-color: #002F6C; color: white; border-radius: 6px;
        border: none; padding: 0.5rem 1rem; font-weight: bold; width: 100%;
    }
    .stButton>button:hover { background-color: #004B93; color: white; }
    div[data-testid="stExpander"] { border: 1px solid #002F6C; border-radius: 6px; }
    div[data-testid="stMetric"] { background-color: #f0f4f8; padding: 10px; border-radius: 6px; border-left: 5px solid #002F6C; }
    
    /* Enlace destacado de ruta completa */
    .link-ruta-completa {
        display: inline-block; background-color: #008B8B; color: white !important;
        padding: 8px 15px; border-radius: 6px; font-weight: bold;
        text-decoration: none; margin-top: 10px; margin-bottom: 20px;
        text-align: center;
    }
    .link-ruta-completa:hover { background-color: #006b6b; text-decoration: none; }
    
    /* 📊 ESTILOS DE TABLA PREMIUM DE ALTA VISIBILIDAD (MÓVIL Y PC) */
    table.dataframe-renderizada {
        width: 100% !important;
        border-collapse: collapse;
        font-family: Arial, sans-serif;
        font-size: 13px;
        margin: 10px 0;
    }
    table.dataframe-renderizada th {
        background-color: #002F6C !important;
        color: white !important;
        font-weight: bold;
        padding: 10px;
        text-align: left;
        white-space: nowrap;
    }
    table.dataframe-renderizada td {
        padding: 8px 10px;
        border-bottom: 1px solid #e0e0e0;
        white-space: nowrap; /* Evita que el texto se rompa en múltiples renglones verticales */
    }
    table.dataframe-renderizada tr:hover {
        background-color: #f5f7fa;
    }
    
    /* Asignación elástica de anchos específicos por columna */
    table.dataframe-renderizada th:nth-child(1), table.dataframe-renderizada td:nth-child(1) { width: 50px; text-align: center; } /* Secuencia */
    table.dataframe-renderizada th:nth-child(2), table.dataframe-renderizada td:nth-child(2) { width: 180px; } /* Nombre */
    table.dataframe-renderizada th:nth-child(3), table.dataframe-renderizada td:nth-child(3) { min-width: 400px; max-width: 600px; overflow: hidden; text-overflow: ellipsis; } /* Dirección Expandida */
    table.dataframe-renderizada th:nth-child(4), table.dataframe-renderizada td:nth-child(4) { width: 90px; text-align: center; }  /* ETA */
    table.dataframe-renderizada th:nth-child(5), table.dataframe-renderizada td:nth-child(5) { width: 90px; text-align: center; }  /* Salida */
    table.dataframe-renderizada th:nth-child(6), table.dataframe-renderizada td:nth-child(6) { width: 100px; text-align: center; } # GPS
    
    /* Contenedor con scroll táctil para celulares */
    .contenedor-tabla-scroll {
        width: 100%;
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
        border: 1px solid #e0e0e0;
        border-radius: 4px;
        margin-bottom: 15px;
    }

    /* 📱 OPTIMIZACIÓN EN PANTALLAS MÓVILES */
    @media (max-width: 768px) {
        .main h1 { font-size: 1.4rem; text-align: center; }
        div[data-testid="stMetric"] { margin-bottom: 10px; }
        .stSelectbox, .stSlider { margin-bottom: 15px; }
    }
    </style>
""", unsafe_allow_html=True)

st.title("🚗 Panel de Control Logístico | RUTAS-QSR")
st.caption("Ecosistema Asistido por Agentes de Campo — División QSR Ecolab")

# ============================================================
# BARRA LATERAL: CARGA E IDENTIFICACIÓN
# ============================================================
st.sidebar.header("📁 Importación Masiva")
uploaded_file = st.sidebar.file_uploader("Arrastra o selecciona la Base Maestra (.xlsx)", type=["xlsx"])

if uploaded_file is not None:
    with st.spinner("Procesando base incremental..."):
        total_filas, fsm_detectado = importar_maestro_sucursales(uploaded_file, uploaded_file.name)
        st.sidebar.success(f"¡Carga Exitosa! {total_filas} registros cargados en el pool maestro.")

conn = sqlite3.connect("data/fsm_rutas.db")
df_fsms = pd.read_sql_query("SELECT id_fsm, nombre_completo FROM fsm_perfiles", conn)
conn.close()

st.sidebar.header("👤 Perfil Operativo")
fsm_seleccionado = st.sidebar.selectbox("FSM Activo en la sesión:", df_fsms['id_fsm'].tolist() if not df_fsms.empty else ["FSMJDD"])

# ============================================================
# 📊 CUADRO DE RESUMEN EJECUTIVO POR ESTADO (INVENTARIO MULTI-CLIENTE)
# ============================================================
st.header("📊 Resumen de Inventario Comercial")

conn = sqlite3.connect("data/fsm_rutas.db")
df_marcas_maestras = pd.read_sql_query("SELECT DISTINCT cliente_marca FROM sucursales WHERE cliente_marca IS NOT NULL ORDER BY cliente_marca", conn)
df_estados_maestros = pd.read_sql_query("SELECT DISTINCT estado FROM sucursales WHERE estado IS NOT NULL AND estado != '' ORDER BY estado", conn)
conn.close()

marcas_disponibles = ["TODAS LAS MARCAS"] + df_marcas_maestras['cliente_marca'].tolist() if not df_marcas_maestras.empty else ["TODAS LAS MARCAS"]

col_filt1, col_est1, col_est2 = st.columns([1.2, 1, 1.5])

with col_filt1:
    marca_seleccionada = st.selectbox("Filtrar por Portafolio / Cliente comercial:", marcas_disponibles)

with col_est1:
    if not df_estados_maestros.empty:
        estado_inventario = st.selectbox("Selecciona Estado para auditar:", df_estados_maestros['estado'].tolist())
    else:
        estado_inventario = "N/A"

conn = sqlite3.connect("data/fsm_rutas.db")
if marca_seleccionada == "TODAS LAS MARCAS":
    df_conteo = pd.read_sql_query("SELECT COUNT(*) as total FROM sucursales WHERE estado = ?", conn, params=[str(estado_inventario)])
else:
    df_conteo = pd.read_sql_query("SELECT COUNT(*) as total FROM sucursales WHERE estado = ? AND cliente_marca = ?", conn, params=[str(estado_inventario), str(marca_seleccionada)])
conn.close()

total_sucursales_estado = df_conteo['total'].values[0] if not df_conteo.empty else 0

with col_est2:
    st.metric(label=f"Puntos de Venta Activos ({marca_seleccionada})", value=f"{total_sucursales_estado} Sucursales en {estado_inventario}")

st.write("---")

# ============================================================
# FUNCIONES AUXILIARES PARA EL TRAZADO REAL SOBRE AVENIDAS
# ============================================================
def obtener_ruta_vial_real(puntos_coordenadas):
    if len(puntos_coordenadas) < 2:
        return puntos_coordenadas
    locs = ";".join([f"{lon},{lat}" for lat, lon in puntos_coordenadas])
    url = f"http://router.project-osrm.org/route/v1/driving/{locs}?overview=full&geometries=geojson"
    try:
        r_api = requests.get(url, timeout=5)
        if r_api.status_code == 200:
            data = r_api.json()
            if 'routes' in data and len(data['routes']) > 0:
                geom = data['routes'][0]['geometry']['coordinates']
                return [[lat, lon] for lon, lat in geom]
    except Exception:
        pass
    return puntos_coordenadas

def crear_mapa_base(puntos_marcadores, ruta_linea=None, color_linea="#002F6C"):
    if not puntos_marcadores:
        return folium.Map(location=[19.4326, -99.1332], zoom_start=11)
    m = folium.Map(location=[puntos_marcadores[0]['lat'], puntos_marcadores[0]['lon']], zoom_start=11, control_scale=True)
    for p in puntos_marcadores:
        folium.Marker(
            location=[p['lat'], p['lon']],
            popup=f"<b>{p['name']}</b><br>Orden: {p['idx']}",
            icon=folium.Icon(color="blue", icon="info-sign")
        ).add_to(m)
    if ruta_linea and len(ruta_linea) > 1:
        folium.PolyLine(ruta_linea, color=color_linea, weight=4.5, opacity=0.85).add_to(m)
    return m

def generar_link_google_maps_completo(coords_lista):
    """Genera una URL híbrida multihito válida para abrir todo el circuito completo secuenciado en Google Maps."""
    if len(coords_lista) < 2:
        return ""
    origen = f"{coords_lista[0][0]},{coords_lista[0][1]}"
    destino = f"{coords_lista[-1][0]},{coords_lista[-1][1]}"
    
    paradas_intermedias = coords_lista[1:-1]
    if paradas_intermedias:
        waypoints = "|".join([f"{lat},{lon}" for lat, lon in paradas_intermedias])
        url = f"https://www.google.com/maps/dir/?api=1&origin={origen}&destination={destino}&waypoints={waypoints}&travelmode=driving"
    else:
        url = f"https://www.google.com/maps/dir/?api=1&origin={origen}&destination={destino}&travelmode=driving"
    return url

# ============================================================
# PANEL PRINCIPAL: CONFIGURACIÓN DEL CIRCUITO
# ============================================================
st.header("⚙️ Configuración del Circuito")
tipo_ruta = st.selectbox("Tipo de Cobertura de la Jornada:", ["Diaria", "Semanal", "Regional"])

conn = sqlite3.connect("data/fsm_rutas.db")
df_zonas = pd.read_sql_query("SELECT DISTINCT zona_localidad FROM rutas_precalculadas WHERE zona_localidad IS NOT NULL AND zona_localidad != '' ORDER BY zona_localidad", conn)
conn.close()

if tipo_ruta == "Diaria":
    st.markdown("### 🏢 Catálogo de Rutas Optimizadas por Zona Operativa")
    visitas_jornada = st.slider("Define el objetivo de visitas por jornada (Ruta):", min_value=4, max_value=8, value=6)
    hora_inicio_diaria = st.select_slider("Hora de Inicio de la Jornada:", options=["08:00", "08:30", "09:00", "09:30", "10:00"], value="09:00", key="diaria_h")
    
    precalcular_catalogo_rutas(visitas_por_jornada=visitas_jornada)
    
    if df_zonas.empty:
        st.info("💡 Por favor, asegúrate de arrastrar tu archivo Excel maestro en la barra lateral.")
    else:
        col_z1, col_z2 = st.columns(2)
        with col_z1:
            zona_elegida = st.selectbox("Selecciona Alcaldía o Municipio objetivo:", df_zonas['zona_localidad'].tolist())
            
        conn = sqlite3.connect("data/fsm_rutas.db")
        df_num_rutas = pd.read_sql_query("SELECT DISTINCT numero_ruta FROM rutas_precalculadas WHERE zona_localidad = ? ORDER BY numero_ruta", conn, params=[str(zona_elegida)])
        conn.close()
        rutas_disponibles = df_num_rutas['numero_ruta'].tolist() if not df_num_rutas.empty else []
        
        with col_z2:
            ruta_elegida = st.selectbox(f"Rutas disponibles en {zona_elegida}:", options=rutas_disponibles if rutas_disponibles else [1])
            
        if st.button("🗺️ Desplegar Ruta Seleccionada en Automático"):
            r_seleccionada = int(ruta_elegida)
            
            conn = sqlite3.connect("data/fsm_rutas.db")
            if marca_seleccionada == "TODAS LAS MARCAS":
                query_ruta = """
                    SELECT s.id_sucursal, s.sucursal_nombre, s.direccion_completa, s.latitud, s.longitud, s.tipo_visita, s.cliente_marca 
                    FROM rutas_precalculadas rp 
                    JOIN sucursales s ON rp.id_sucursal = s.id_sucursal 
                    WHERE rp.zona_localidad = ? AND rp.numero_ruta = ? 
                    ORDER BY rp.secuencia_optima
                """
                df_pool_sec = pd.read_sql_query(query_ruta, conn, params=[str(zona_elegida), r_seleccionada])
            else:
                query_ruta = """
                    SELECT s.id_sucursal, s.sucursal_nombre, s.direccion_completa, s.latitud, s.longitud, s.tipo_visita, s.cliente_marca 
                    FROM rutas_precalculadas rp 
                    JOIN sucursales s ON rp.id_sucursal = s.id_sucursal 
                    WHERE rp.zona_localidad = ? AND rp.numero_ruta = ? AND s.cliente_marca = ?
                    ORDER BY rp.secuencia_optima
                """
                df_pool_sec = pd.read_sql_query(query_ruta, conn, params=[str(zona_elegida), r_seleccionada, str(marca_seleccionada)])
                
            df_fsm_data = pd.read_sql_query("SELECT * FROM fsm_perfiles WHERE id_fsm = ?", conn, params=[fsm_seleccionado])
            conn.close()
            
            if df_pool_sec.empty:
                st.warning(f"No hay sucursales activas de la marca '{marca_seleccionada}' registradas.")
            else:
                fsm_meta = df_fsm_data.iloc[0].to_dict() if not df_fsm_data.empty else {}
                lat_c, lon_c = float(fsm_meta.get('latitud_base', 19.549732)) , float(fsm_meta.get('longitud_base', -99.236967))
                
                df_pool_sec = df_pool_sec.rename(columns={'id_sucursal': 'id_sucursal', 'sucursal_nombre': 'sucursal_nombre', 'direccion_completa': 'direccion_completa'})
                sucursales_lista = df_pool_sec.to_dict(orient='records')
                
                visitas_calc, _, _ = simular_ruta_del_dia(sucursales_lista, hora_inicio_diaria, visitas_jornada, False, "Atizapán Base", (lat_c, lon_c))
                
                puntos, coords_viaje = [], [(lat_c, lon_c)]
                df_visitas_final = []
                
                for idx, v in enumerate(visitas_calc):
                    m_det = df_pool_sec[df_pool_sec['id_sucursal']==v['ID Sucursal']]['cliente_marca'].values[0]
                    lat_s = float(df_pool_sec[df_pool_sec['id_sucursal']==v['ID Sucursal']]['latitud'].values[0])
                    lon_s = float(df_pool_sec[df_pool_sec['id_sucursal']==v['ID Sucursal']]['longitud'].values[0])
                    
                    url_gps = f"https://www.google.com/maps/search/?api=1&query={lat_s},{lon_s}"
                    link_html = f'<a href="{url_gps}" target="_blank">🗺️ GPS</a>'
                    
                    df_visitas_final.append({
                        "Sec": v["Secuencia"],
                        "Marca": m_det,
                        "Sucursal": v["Nombre Sucursal"],
                        "Dirección": v["Dirección"],
                        "ETA": v["ETA Llegada"],
                        "Salida": v["Hora Salida"],
                        "Navegación": link_html
                    })
                    
                    puntos.append({"lat": lat_s, "lon": lon_s, "name": f"[{m_det}] {v['Nombre Sucursal']}", "idx": idx+1})
                    coords_viaje.append((lat_s, lon_s))
                    
                st.markdown(f"### 📋 Itinerario Maestro — Ruta {r_seleccionada}")
                df_html = pd.DataFrame(df_visitas_final)
                st.markdown(f'<div class="contenedor-tabla-scroll"><table class="dataframe-renderizada">{df_html.to_html(escape=False, index=False, classes="dataframe-renderizada")}</table></div>', unsafe_allow_html=True)
                
                link_jornada_maps = generar_link_google_maps_completo(coords_viaje)
                st.markdown(f'<a href="{link_jornada_maps}" target="_blank" class="link-ruta-completa">🚀 Abrir Ruta Completa del Día en Google Maps</a>', unsafe_allow_html=True)
                
                st.write("---")
                st.write("#### 🗺️ Trazado Vial en Tiempo Real (Avenidas)")
                trazado_real = obtener_ruta_vial_real(coords_viaje)
                mapa_obj = crear_mapa_base(puntos, trazado_real, color_linea="#002F6C")
                st_folium(mapa_obj, width=1200, height=450, returned_objects=[])

elif tipo_ruta == "Semanal":
    st.markdown("### 📅 Agenda de Rutas Metropolitanas (Lunes a Viernes)")
    visitas_jornada_sem = st.slider("Configurar visitas base por día:", min_value=4, max_value=8, value=6)
    hora_inicio_sem = st.select_slider("Hora de Salida Base:", options=["08:00", "08:30", "09:00", "09:30"])
    
    precalcular_catalogo_rutas(visitas_por_jornada=visitas_jornada_sem)
    
    if df_zonas.empty:
        st.info("💡 Por favor, asegúrate de arrastrar tu archivo Excel maestro.")
    else:
        dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]
        config_semana = {}
        cols_dias = st.columns(5)
        
        for idx, dia in enumerate(dias):
            with cols_dias[idx]:
                st.subheader(f"📆 {dia}")
                zona_dia = st.selectbox(f"Zona {dia}:", df_zonas['zona_localidad'].tolist(), key=f"zona_{dia}")
                conn = sqlite3.connect("data/fsm_rutas.db")
                df_num_sem = pd.read_sql_query("SELECT DISTINCT numero_ruta FROM rutas_precalculadas WHERE zona_localidad = ? ORDER BY numero_ruta", conn, params=[str(zona_dia)])
                conn.close()
                rutas_dia_opts = df_num_sem['numero_ruta'].tolist() if not df_num_sem.empty else [1]
                ruta_dia = st.selectbox(f"Ruta {dia}:", options=rutas_dia_opts, key=f"ruta_{dia}")
                config_semana[dia] = {"zona": zona_dia, "ruta": ruta_dia}
                
        st.write("---")
        st.write("#### 🗺️ Visor de Capas Geográficas del Itinerario Semanal")
        
        chk_cols = st.columns(5)
        dias_seleccionados = []
        for idx, dia in enumerate(dias):
            with chk_cols[idx]:
                if st.checkbox(f"Ver {dia}", value=(idx==0), key=f"chk_{dia}"):
                    dias_seleccionados.append(dia)
                    
        conn = sqlite3.connect("data/fsm_rutas.db")
        df_fsm_data = pd.read_sql_query("SELECT * FROM fsm_perfiles WHERE id_fsm = ?", conn, params=[fsm_seleccionado])
        fsm_meta = df_fsm_data.iloc[0].to_dict() if not df_fsm_data.empty else {}
        lat_casa = float(fsm_meta.get('latitud_base', 19.549732))
        lon_casa = float(fsm_meta.get('longitud_base', -99.236967))
        
        colores_dias = {"Lunes": "#002F6C", "Martes": "#008B8B", "Miércoles": "#4682B4", "Jueves": "#20B2AA", "Viernes": "#1F4E5B"}
        mapa_semanal = folium.Map(location=[lat_casa, lon_casa], zoom_start=10)
        
        st.write("#### 📋 Cronograma de Operations Generadas")
        for dia in dias:
            zona = config_semana[dia]["zona"]
            num_r = config_semana[dia]["ruta"]
            
            query_sem = "SELECT s.id_sucursal, s.sucursal_nombre, s.direccion_completa, s.latitud, s.longitud, s.tipo_visita FROM rutas_precalculadas rp JOIN sucursales s ON rp.id_sucursal = s.id_sucursal WHERE rp.zona_localidad = ? AND rp.numero_ruta = ? ORDER BY rp.secuencia_optima"
            df_pool_sem = pd.read_sql_query(query_sem, conn, params=[str(zona), num_r])
            df_pool_sem = df_pool_sem.rename(columns={'id_sucursal': 'id_sucursal', 'sucursal_nombre': 'sucursal_nombre', 'direccion_completa': 'direccion_completa'})
            suc_lista_sem = df_pool_sem.to_dict(orient='records')
            visitas_calc_sem, _, hora_cs = simular_ruta_del_dia(suc_lista_sem, hora_inicio_sem, visitas_jornada_sem, False, "Atizapán Base", (lat_casa, lon_casa))
            
            coords_dia = [(lat_casa, lon_casa)]
            if visitas_calc_sem:
                for idx, v in enumerate(visitas_calc_sem):
                    l_s = float(df_pool_sem[df_pool_sem['id_sucursal']==v['ID Sucursal']]['latitud'].values[0])
                    lo_s = float(df_pool_sem[df_pool_sem['id_sucursal']==v['ID Sucursal']]['longitud'].values[0])
                    coords_dia.append((l_s, lo_s))
                    if dia in dias_seleccionados:
                        folium.Marker([l_s, lo_s], popup=f"{dia}: {v['Nombre Sucursal']}", icon=folium.Icon(color="cadetblue")).add_to(mapa_semanal)
                
                if dia in dias_seleccionados:
                    t_real_dia = obtener_ruta_vial_real(coords_dia)
                    folium.PolyLine(t_real_dia, color=colores_dias[dia], weight=4, opacity=0.8, tooltip=f"Ruta {dia}").add_to(mapa_semanal)
            
            with st.expander(f"➔ {dia.upper()}: {zona} (Circuito {num_r}) — Retorno est: {hora_cs} hrs"):
                if visitas_calc_sem:
                    df_sem_movil = []
                    for idx, v in enumerate(visitas_calc_sem): 
                        l_s = float(df_pool_sem[df_pool_sem['id_sucursal']==v['ID Sucursal']]['latitud'].values[0])
                        lo_s = float(df_pool_sem[df_pool_sem['id_sucursal']==v['ID Sucursal']]['longitud'].values[0])
                        u_gps = f"https://www.google.com/maps/search/?api=1&query={l_s},{lo_s}"
                        df_sem_movil.append({
                            "Sec": v["Secuencia"], "Sucursal": v["Nombre Sucursal"], "Dirección": v["Dirección"], "ETA": v["ETA Llegada"], "Salida": v["Hora Salida"],
                            "Navegación": f'<a href="{u_gps}" target="_blank">🗺️ GPS</a>'
                        })
                    df_html_sem = pd.DataFrame(df_sem_movil)
                    st.markdown(f'<div class="contenedor-tabla-scroll"><table class="dataframe-renderizada">{df_html_sem.to_html(escape=False, index=False, classes="dataframe-renderizada")}</table></div>', unsafe_allow_html=True)
                    
                    link_semanal_completo = generar_link_google_maps_completo(coords_dia)
                    st.markdown(f'<a href="{link_semanal_completo}" target="_blank" class="link-ruta-completa">🚀 Abrir Circuito Completo de este {dia} en Google Maps</a>', unsafe_allow_html=True)
        conn.close()
        
        st.write("---")
        st.write("#### 🗺️ Visor Cartográfico unificado (Capas)")
        st_folium(mapa_semanal, width=1200, height=500, returned_objects=[])

else:
    # ============================================================
    # 🛣️ MÓDULO REGIONAL CON ESTADO BLINDADO Y PERSISTENTE
    # ============================================================
    st.markdown("### 🗺️ Optimización de Circuitos Foráneos e Itinerarios de Viaje")
    col1, col2, col3 = st.columns(3)
    with col1:
        hora_inicio = st.select_slider("Hora de Inicio (Día 1):", options=["08:00", "08:30", "09:00", "09:30", "10:00", "10:30", "11:00", "11:30", "12:00"], value="08:30")
    with col2:
        visitas_dia_1 = st.slider("Objetivo Visitas (Lunes):", min_value=1, max_value=8, value=3)
        visitas_resto_dias = st.slider("Objetivo Visitas (Martes a Viernes):", min_value=1, max_value=8, value=5)
    with col3:
        estado_filtro = st.selectbox("Estado Destino:", ["GUERRERO", "MORELOS"])
        modo_arribo = st.radio("Estrategia:", ["Trabajar en el camino (Lunes)", "Avanzada (Domingo)"])
        ciudad_hotel = st.selectbox("Ciudad del Hotel:", ["Acapulco", "Chilpancingo", "Cuernavaca", "Taxco"])
        hotel_nombre = st.text_input("Hotel Autorizado:", value=f"Fiesta Inn {ciudad_hotel}")
        
    if 'regional_simulado' not in st.session_state:
        st.session_state.regional_simulado = False
        st.session_state.datos_por_dia = {}
        st.session_state.lat_hotel = 16.853056
        st.session_state.lon_hotel = -99.851944
        st.session_state.lat_casa = 19.549732
        st.session_state.lon_casa = -99.236967
        st.session_state.df_pool_guardado = None

    if st.button("🚀 Ejecutar Optimización Predictiva Regional"):
        conn = sqlite3.connect("data/fsm_rutas.db")
        if marca_seleccionada == "TODAS LAS MARCAS":
            query = "SELECT id_sucursal, sucursal_nombre, direccion_completa, latitud, longitud, tipo_visita FROM sucursales WHERE estado = ?"
            df_pool = pd.read_sql_query(query, conn, params=[str(estado_filtro)])
        else:
            query = "SELECT id_sucursal, sucursal_nombre, direccion_completa, latitud, longitud, tipo_visita FROM sucursales WHERE estado = ? AND cliente_marca = ?"
            df_pool = pd.read_sql_query(query, conn, params=[str(estado_filtro), str(marca_seleccionada)])
            
        df_fsm_data = pd.read_sql_query("SELECT * FROM fsm_perfiles WHERE id_fsm = ?", conn, params=[fsm_seleccionado])
        conn.close()
        
        if df_pool.empty:
            st.warning(f"No hay sucursales activas registradas para el Estado de {estado_filtro} con los filtros seleccionados.")
            st.session_state.regional_simulado = False
        else:
            fsm_meta = df_fsm_data.iloc[0].to_dict() if not df_fsm_data.empty else {}
            st.session_state.lat_casa, st.session_state.lon_casa = float(fsm_meta.get('latitud_base', 19.549732)), float(fsm_meta.get('longitud_base', -99.236967))
            
            coordenadas_hoteles = {"Acapulco": (16.853056, -99.851944), "Chilpancingo": (17.551111, -99.500556), "Taxco": (18.556111, -99.605556), "Cuernavaca": (18.921389, -99.234722)}
            st.session_state.lat_hotel, st.session_state.lon_hotel = coordenadas_hoteles.get(ciudad_hotel, (16.853056, -99.851944))
            
            if estado_filtro == "GUERRERO" and modo_arribo == "Trabajar en el camino (Lunes)":
                df_pool = df_pool.sort_values(by="latitud", ascending=False)
                
            df_pool = df_pool.rename(columns={'id_sucursal': 'id_sucursal', 'sucursal_nombre': 'sucursal_nombre', 'direccion_completa': 'direccion_completa'})
            st.session_state.df_pool_guardado = df_pool.copy()
            pool_pendiente = df_pool.to_dict(orient='records')
            
            st.session_state.datos_por_dia = {}
            
            # --- DÍA 1: LUNES (TRASLADO Y BAJADA) ---
            visitas_lunes, km_lunes, hora_cierre_lunes = simular_ruta_del_dia(pool_pendiente, hora_inicio, visitas_dia_1, True, fsm_meta.get('direccion_base'), (st.session_state.lat_casa, st.session_state.lon_casa))
            if visitas_lunes:
                coords_lunes = [(st.session_state.lat_casa, st.session_state.lon_casa)]
                puntos_lunes = []
                for idx, v in enumerate(visitas_lunes):
                    l_s = float(df_pool[df_pool['id_sucursal']==v['ID Sucursal']]['latitud'].values[0])
                    lo_s = float(df_pool[df_pool['id_sucursal']==v['ID Sucursal']]['longitud'].values[0])
                    coords_lunes.append((l_s, lo_s))
                    puntos_lunes.append({"lat": l_s, "lon": lo_s, "popup": f"Lunes: {v['Nombre Sucursal']}", "color": "blue"})
                coords_lunes.append((st.session_state.lat_hotel, st.session_state.lon_hotel))
                t_real_lunes = obtener_ruta_vial_real(coords_lunes)
                st.session_state.datos_por_dia["Día 1: Lunes (Ruta de Bajada)"] = {"trazado": t_real_lunes, "puntos": puntos_lunes, "line_color": "#002F6C", "tabla": visitas_lunes, "coords_completas": coords_lunes}
                
                ids_v = [v["ID Sucursal"] for v in visitas_lunes]
                pool_pendiente = [s for s in pool_pendiente if s["id_sucursal"] not in ids_v]
            
            # --- DÍA 2: MARTES (LOCAL) ---
            if pool_pendiente:
                visitas_martes, km_martes, hora_cierre_martes = simular_ruta_del_dia(pool_pendiente, "08:30", visitas_resto_dias, True, hotel_nombre, (st.session_state.lat_hotel, st.session_state.lon_hotel))
                if visitas_martes:
                    coords_martes = [(st.session_state.lat_hotel, st.session_state.lon_hotel)]
                    puntos_martes = []
                    for idx, v in enumerate(visitas_martes):
                        l_s = float(df_pool[df_pool['id_sucursal']==v['ID Sucursal']]['latitud'].values[0])
                        lo_s = float(df_pool[df_pool['id_sucursal']==v['ID Sucursal']]['longitud'].values[0])
                        coords_martes.append((l_s, lo_s))
                        puntos_martes.append({"lat": l_s, "lon": lo_s, "popup": f"Martes: {v['Nombre Sucursal']}", "color": "cadetblue"})
                    coords_martes.append((st.session_state.lat_hotel, st.session_state.lon_hotel))
                    t_real_martes = obtener_ruta_vial_real(coords_martes)
                    st.session_state.datos_por_dia["Día 2: Martes (Circuito Local)"] = {"trazado": t_real_martes, "puntos": puntos_martes, "line_color": "#008B8B", "tabla": visitas_martes, "coords_completas": coords_martes}
                    
                    ids_v = [v["ID Sucursal"] for v in visitas_martes]
                    pool_pendiente = [s for s in pool_pendiente if s["id_sucursal"] not in ids_v]
            
            # --- DÍA 3: MIÉRCOLES (LOCAL) ---
            if pool_pendiente:
                visitas_miercoles, km_miercoles, hora_cierre_miercoles = simular_ruta_del_dia(pool_pendiente, "08:30", visitas_resto_dias, True, hotel_nombre, (st.session_state.lat_hotel, st.session_state.lon_hotel))
                if visitas_miercoles:
                    coords_miercoles = [(st.session_state.lat_hotel, st.session_state.lon_hotel)]
                    puntos_miercoles = []
                    for idx, v in enumerate(visitas_miercoles):
                        l_s = float(df_pool[df_pool['id_sucursal']==v['ID Sucursal']]['latitud'].values[0])
                        lo_s = float(df_pool[df_pool['id_sucursal']==v['ID Sucursal']]['longitud'].values[0])
                        coords_miercoles.append((l_s, lo_s))
                        puntos_miercoles.append({"lat": l_s, "lon": lo_s, "popup": f"Miércoles: {v['Nombre Sucursal']}", "color": "orange"})
                    coords_miercoles.append((st.session_state.lat_hotel, st.session_state.lon_hotel))
                    t_real_miercoles = obtener_ruta_vial_real(coords_miercoles)
                    st.session_state.datos_por_dia["Día 3: Miércoles (Circuito Local)"] = {"trazado": t_real_miercoles, "puntos": puntos_miercoles, "line_color": "#4682B4", "tabla": visitas_miercoles, "coords_completas": coords_miercoles}
                    
                    ids_v = [v["ID Sucursal"] for v in visitas_miercoles]
                    pool_pendiente = [s for s in pool_pendiente if s["id_sucursal"] not in ids_v]
            
            # --- DÍA 4: JUEVES (CASCADA ELÁSTICA REMANENTES) ---
            if pool_pendiente:
                visitas_jueves, km_jueves, hora_cierre_jueves = simular_ruta_del_dia(pool_pendiente, "08:30", len(pool_pendiente), True, hotel_nombre, (st.session_state.lat_hotel, st.session_state.lon_hotel))
                if visitas_jueves:
                    coords_jueves = [(st.session_state.lat_hotel, st.session_state.lon_hotel)]
                    puntos_jueves = []
                    for idx, v in enumerate(visitas_jueves):
                        l_s = float(df_pool[df_pool['id_sucursal']==v['ID Sucursal']]['latitud'].values[0])
                        lo_s = float(df_pool[df_pool['id_sucursal']==v['ID Sucursal']]['longitud'].values[0])
                        coords_jueves.append((l_s, lo_s))
                        puntos_jueves.append({"lat": l_s, "lon": lo_s, "popup": f"Jueves: {v['Nombre Sucursal']}", "color": "purple"})
                    coords_jueves.append((st.session_state.lat_hotel, st.session_state.lon_hotel))
                    t_real_jueves = obtener_ruta_vial_real(coords_jueves)
                    st.session_state.datos_por_dia["Día 4: Jueves (Cierre Foráneo)"] = {"trazado": t_real_jueves, "puntos": puntos_jueves, "line_color": "#8B008B", "tabla": visitas_jueves, "coords_completas": coords_jueves}
            
            st.session_state.regional_simulado = True

    if st.session_state.regional_simulado:
        st.markdown("## 🗓️ Cronograma y Logística del Circuito Foráneo")
        
        for d_nombre, d_meta in st.session_state.datos_por_dia.items():
            st.subheader(f"📅 {d_nombre}")
            df_d_movil = []
            for idx, v in enumerate(d_meta["tabla"]):
                l_s = float(st.session_state.df_pool_guardado[st.session_state.df_pool_guardado['id_sucursal']==v['ID Sucursal']]['latitud'].values[0])
                lo_s = float(st.session_state.df_pool_guardado[st.session_state.df_pool_guardado['id_sucursal']==v['ID Sucursal']]['longitud'].values[0])
                u_gps = f"https://www.google.com/maps/search/?api=1&query={l_s},{lo_s}"
                df_d_movil.append({
                    "Sec": v["Secuencia"], "Sucursal": v["Nombre Sucursal"], "Dirección": v["Dirección"], "ETA": v["ETA Llegada"], "Salida": v["Hora Salida"],
                    "Navegación": f'<a href="{u_gps}" target="_blank">🗺️ GPS</a>'
                })
            df_html_reg = pd.DataFrame(df_d_movil)
            st.markdown(f'<div class="contenedor-tabla-scroll"><table class="dataframe-renderizada">{df_html_reg.to_html(escape=False, index=False, classes="dataframe-renderizada")}</table></div>', unsafe_allow_html=True)
            
            link_dia_completo_maps = generar_link_google_maps_completo(d_meta["coords_completas"])
            st.markdown(f'<a href="{link_dia_completo_maps}" target="_blank" class="link-ruta-completa">🚀 Abrir Ruta Completa de este día en Google Maps</a>', unsafe_allow_html=True)
            st.write("")

        st.write("---")
        st.subheader("🚗 Retorno Planificado a Casa Seguro")
        st.success("🟢 ¡Felicidades! El 100% de las sucursales han sido cubiertas con éxito en el cronograma semanal.")
        st.warning("⚠️ Regla de Seguridad Corporativa Ecolab: El viaje de regreso por carretera hacia la base en Atizapán queda programado para la mañana del día siguiente de forma segura, evitando conducción nocturna.")
        
        st.write("---")
        st.subheader("🗺️ Cartografía Vial Regional Interactiva")
        
        opciones_mapa = ["MOSTRAR TODO EL CIRCUITO COMPLETO"] + list(st.session_state.datos_por_dia.keys())
        capa_seleccionada = st.selectbox("Selecciona la capa de Ruta a visualizar en el mapa:", opciones_mapa, key="regional_map_select")
        
        mapa_regional = folium.Map(location=[st.session_state.lat_hotel, st.session_state.lon_hotel], zoom_start=8)
        
        folium.Marker([st.session_state.lat_casa, st.session_state.lon_casa], popup="📍 Base FSM (Atizapán)", icon=folium.Icon(color="red", icon="home")).add_to(mapa_regional)
        folium.Marker([st.session_state.lat_hotel, st.session_state.lon_hotel], popup=f"🏁 Pernocta: {hotel_nombre}", icon=folium.Icon(color="green", icon="briefcase")).add_to(mapa_regional)
        
        if capa_seleccionada == "MOSTRAR TODO EL CIRCUITO COMPLETO":
            for d_nombre, d_meta in st.session_state.datos_por_dia.items():
                if d_meta["trazado"]:
                    folium.PolyLine(d_meta["trazado"], color=d_meta["line_color"], weight=4.5, opacity=0.85).add_to(mapa_regional)
                for pt in d_meta["puntos"]:
                    folium.Marker([pt["lat"], pt["lon"]], popup=pt["popup"], icon=folium.Icon(color=pt["color"])).add_to(mapa_regional)
        else:
            d_meta = st.session_state.datos_por_dia[capa_seleccionada]
            if d_meta["trazado"]:
                folium.PolyLine(d_meta["trazado"], color=d_meta["line_color"], weight=5.5, opacity=0.9).add_to(mapa_regional)
            for pt in d_meta["puntos"]:
                folium.Marker([pt["lat"], pt["lon"]], popup=pt["popup"], icon=folium.Icon(color=pt["color"], icon="info-sign")).add_to(mapa_regional)
        
        st_folium(mapa_regional, width=1300, height=550, returned_objects=[])