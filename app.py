# app.py
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
    import sys
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
    
    /* 📱 OPTIMIZACIÓN EN PANTALLAS MÓVILES */
    @media (max-width: 768px) {
        .main h1 { font-size: 1.4rem; text-align: center; }
        div[data-testid="stMetric"] { margin-bottom: 10px; }
        /* Forzar que las tablas tengan scroll horizontal limpio en celular sin romper la UI */
        div.stDataFrame, div[data-testid="stTable"] {
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
        }
        /* Ajustar los selectores para que no se amontonen */
        .stSelectbox, .stSlider {
            margin-bottom: 15px;
        }
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
                    
                    # 📲 NUEVO: Generar enlaces nativos HTML dinámicos para abrir la navegación GPS en tu celular
                    url_gps = f"https://www.google.com/maps/search/?api=1&query={lat_s},{lon_s}"
                    link_html = f'<a href="{url_gps}" target="_blank">🗺️ Iniciar GPS</a>'
                    
                    df_visitas_final.append({
                        "Secuencia": v["Secuencia"],
                        "Marca": m_det,
                        "Nombre Sucursal": v["Nombre Sucursal"],
                        "Dirección": v["Dirección"],
                        "ETA Llegada": v["ETA Llegada"],
                        "Hora Salida": v["Hora Salida"],
                        "Navegación Móvil": link_html
                    })
                    
                    puntos.append({"lat": lat_s, "lon": lon_s, "name": f"[{m_det}] {v['Nombre Sucursal']}", "idx": idx+1})
                    coords_viaje.append((lat_s, lon_s))
                    
                st.markdown(f"### 📋 Itinerario Maestro — Ruta {r_seleccionada}")
                # Renderizar tabla nativa aceptando el link HTML seguro del GPS
                st.write(pd.DataFrame(df_visitas_final).to_html(escape=False, index=False), unsafe_allow_html=True)
                
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
        
        st.write("#### 📋 Cronograma de Operaciones Generadas")
        for dia in dias:
            zona = config_semana[dia]["zona"]
            num_r = config_semana[dia]["ruta"]
            
            query_sem = "SELECT s.id_sucursal, s.sucursal_nombre, s.direccion_completa, s.latitud, s.longitud, s.tipo_visita FROM rutas_precalculadas rp JOIN sucursales s ON rp.id_sucursal = s.id_sucursal WHERE rp.zona_localidad = ? AND rp.numero_ruta = ? ORDER BY rp.secuencia_optima"
            df_pool_sem = pd.read_sql_query(query_sem, conn, params=[str(zona), num_r])
            df_pool_sem = df_pool_sem.rename(columns={'id_sucursal': 'id_sucursal', 'sucursal_nombre': 'sucursal_nombre', 'direccion_completa': 'direccion_completa'})
            suc_lista_sem = df_pool_sem.to_dict(orient='records')
            visitas_calc_sem, _, hora_cs = simular_ruta_del_dia(suc_lista_sem, hora_inicio_sem, visitas_jornada_sem, False, "Atizapán Base", (lat_casa, lon_casa))
            
            if dia in dias_seleccionados and visitas_calc_sem:
                coords_dia = [(lat_casa, lon_casa)]
                for idx, v in enumerate(visitas_calc_sem):
                    l_s = float(df_pool_sem[df_pool_sem['id_sucursal']==v['ID Sucursal']]['latitud'].values[0])
                    lo_s = float(df_pool_sem[df_pool_sem['id_sucursal']==v['ID Sucursal']]['longitud'].values[0])
                    coords_dia.append((l_s, lo_s))
                    folium.Marker([l_s, lo_s], popup=f"{dia}: {v['Nombre Sucursal']}", icon=folium.Icon(color="cadetblue")).add_to(mapa_semanal)
                t_real_dia = obtener_ruta_vial_real(coords_dia)
                folium.PolyLine(t_real_dia, color=colores_dias[dia], weight=4, opacity=0.8, tooltip=f"Ruta {dia}").add_to(mapa_semanal)
            
            with st.expander(f"➔ {dia.upper()}: {zona} (Circuito {num_r}) — Retorno est: {hora_cs} hrs"):
                if visitas_calc_sem:
                    df_sem_móvil = []
                    for idx, v in enumerate(visitas_calc_sem): 
                        l_s = float(df_pool_sem[df_pool_sem['id_sucursal']==v['ID Sucursal']]['latitud'].values[0])
                        lo_s = float(df_pool_sem[df_pool_sem['id_sucursal']==v['ID Sucursal']]['longitud'].values[0])
                        u_gps = f"https://www.google.com/maps/search/?api=1&query={l_s},{lo_s}"
                        df_sem_móvil.append({
                            "Secuencia": v["Secuencia"],
                            "Nombre Sucursal": v["Nombre Sucursal"],
                            "ETA Llegada": v["ETA Llegada"],
                            "Hora Salida": v["Hora Salida"],
                            "Navegación": f'<a href="{u_gps}" target="_blank">🗺️ Navegar</a>'
                        })
                    st.write(pd.DataFrame(df_sem_móvil).to_html(escape=False, index=False), unsafe_allow_html=True)
        conn.close()
        
        st.write("---")
        st.write("#### 🗺️ Visor Cartográfico unificado (Capas)")
        st_folium(mapa_semanal, width=1200, height=500, returned_objects=[])

else:
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
        else:
            fsm_meta = df_fsm_data.iloc[0].to_dict() if not df_fsm_data.empty else {}
            lat_casa, lon_casa = float(fsm_meta.get('latitud_base', 19.549732)), float(fsm_meta.get('longitud_base', -99.236967))
            
            coordenadas_hoteles = {"Acapulco": (16.853056, -99.851944), "Chilpancingo": (17.551111, -99.500556), "Taxco": (18.556111, -99.605556), "Cuernavaca": (18.921389, -99.234722)}
            lat_hotel, lon_hotel = coordenadas_hoteles.get(ciudad_hotel, (16.853056, -99.851944))
            
            if estado_filtro == "GUERRERO" and modo_arribo == "Trabajar en el camino (Lunes)":
                df_pool = df_pool.sort_values(by="latitud", ascending=False)
                
            pool_pendiente = df_pool.to_dict(orient='records')
            
            st.markdown("## 🗓️ Cronograma y Logística del Circuito Foráneo")
            
            mapa_regional = folium.Map(location=[lat_hotel, lon_hotel], zoom_start=8)
            folium.Marker([lat_casa, lon_casa], popup="📍 Base FSM (Atizapán)", icon=folium.Icon(color="red", icon="home")).add_to(mapa_regional)
            folium.Marker([lat_hotel, lon_hotel], popup=f"🏁 Pernocta: {hotel_nombre}", icon=folium.Icon(color="green", icon="briefcase")).add_to(mapa_regional)
            
            # --- DÍA 1: LUNES ---
            st.subheader("🟢 Día 1: Lunes (Traslado y Ruta de Bajada)")
            visitas_lunes, km_lunes, hora_cierre_lunes = simular_ruta_del_dia(pool_pendiente, hora_inicio, visitas_dia_1, True, fsm_meta.get('direccion_base'), (lat_casa, lon_casa))
            
            if visitas_lunes:
                st.info(f"🕒 **Cierre de Jornada:** {hora_cierre_lunes} hrs")
                df_l_móvil = []
                for idx, v in enumerate(visitas_lunes):
                    l_s = float(df_pool[df_pool['id_sucursal']==v['ID Sucursal']]['latitud'].values[0])
                    lo_s = float(df_pool[df_pool['id_sucursal']==v['ID Sucursal']]['longitud'].values[0])
                    u_gps = f"https://www.google.com/maps/search/?api=1&query={l_s},{lo_s}"
                    df_l_móvil.append({
                        "Secuencia": v["Secuencia"], "Nombre": v["Nombre Sucursal"], "Dirección": v["Dirección"], "ETA": v["ETA Llegada"], "GPS": f'<a href="{u_gps}" target="_blank">🗺️ Navegar</a>'
                    })
                st.write(pd.DataFrame(df_l_móvil).to_html(escape=False, index=False), unsafe_allow_html=True)
                
                coords_lunes = [(lat_casa, lon_casa)]
                for idx, v in enumerate(visitas_lunes):
                    l_s = float(df_pool[df_pool['id_sucursal']==v['ID Sucursal']]['latitud'].values[0])
                    lo_s = float(df_pool[df_pool['id_sucursal']==v['ID Sucursal']]['longitud'].values[0])
                    coords_lunes.append((l_s, lo_s))
                    folium.Marker([l_s, lo_s], popup=f"Lunes: {v['Nombre Sucursal']}", icon=folium.Icon(color="blue")).add_to(mapa_regional)
                coords_lunes.append((lat_hotel, lon_hotel))
                
                t_real_lunes = obtener_ruta_vial_real(coords_lunes)
                folium.PolyLine(t_real_lunes, color="#002F6C", weight=5, opacity=0.85, tooltip="Trayecto Lunes").add_to(mapa_regional)
                
                ids_v = [v["ID Sucursal"] for v in visitas_lunes]
                pool_pendiente = [s for s in pool_pendiente if s["id_sucursal"] not in ids_v]
            else:
                st.info("No se agendaron paradas en el trayecto de bajada.")
            
            # --- DÍA 2: MARTES ---
            if pool_pendiente:
                st.write("---")
                st.subheader("🔵 Día 2: Martes (Operación Local en Destino)")
                st.caption(f"Salida matutina usando como base el Hotel Validado: **{hotel_nombre}**")
                visitas_martes, km_martes, hora_cierre_martes = simular_ruta_del_dia(pool_pendiente, "08:30", visitas_resto_dias, True, hotel_nombre, (lat_hotel, lon_hotel))
                
                if visitas_martes:
                    st.info(f"🕒 **Regreso a Hotel:** {hora_cierre_martes} hrs")
                    df_m_móvil = []
                    for idx, v in enumerate(visitas_martes):
                        l_s = float(df_pool[df_pool['id_sucursal']==v['ID Sucursal']]['latitud'].values[0])
                        lo_s = float(df_pool[df_pool['id_sucursal']==v['ID Sucursal']]['longitud'].values[0])
                        u_gps = f"https://www.google.com/maps/search/?api=1&query={l_s},{lo_s}"
                        df_m_móvil.append({
                            "Secuencia": v["Secuencia"], "Nombre": v["Nombre Sucursal"], "Dirección": v["Dirección"], "ETA": v["ETA Llegada"], "GPS": f'<a href="{u_gps}" target="_blank">🗺️ Navegar</a>'
                        })
                    st.write(pd.DataFrame(df_m_móvil).to_html(escape=False, index=False), unsafe_allow_html=True)
                    
                    coords_martes = [(lat_hotel, lon_hotel)]
                    for idx, v in enumerate(visitas_martes):
                        l_s = float(df_pool[df_pool['id_sucursal']==v['ID Sucursal']]['latitud'].values[0])
                        lo_s = float(df_pool[df_pool['id_sucursal']==v['ID Sucursal']]['longitud'].values[0])
                        coords_martes.append((l_s, lo_s))
                        folium.Marker([l_s, lo_s], popup=f"Martes: {v['Nombre Sucursal']}", icon=folium.Icon(color="cadetblue")).add_to(mapa_regional)
                    coords_martes.append((lat_hotel, lon_hotel))
                    
                    t_real_martes = obtener_ruta_vial_real(coords_martes)
                    folium.PolyLine(t_real_martes, color="#008B8B", weight=4, opacity=0.8, tooltip="Circuito Martes").add_to(mapa_regional)
                    
                    ids_v = [v["ID Sucursal"] for v in visitas_martes]
                    pool_pendiente = [s for s in pool_pendiente if s["id_sucursal"] not in ids_v]
                else:
                    st.warning("⚠️ Las restricciones horarias locales de la zona impidieron agendar visitas seguras este día.")
            
            if pool_pendiente:
                st.write("---")
                st.error(f"⚠️ Atención: Quedaron {len(pool_pendiente)} sucursales sin poderse trazar por restricciones de ventana horaria local.")
                
            st.write("---")
            st.subheader("🚗 Retorno Planificado Seguro")
            st.warning("⚠️ Regla de Seguridad Ecolab: El viaje de regreso por carretera hacia Atizapán queda programado para el día siguiente por la mañana para evitar conducción nocturna.")
            
            st.write("---")
            st.write("#### 🗺️ Cartografía Vial Regional e Itinerarios Híbridos Totales")
            st_folium(mapa_regional, width=1300, height=500, returned_objects=[])