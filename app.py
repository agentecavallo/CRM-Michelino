import streamlit as st
import sqlite3
import pandas as pd
import requests
import os
import time
from datetime import datetime, timedelta
from io import BytesIO
from streamlit_js_eval import get_geolocation
import streamlit.components.v1 as components
import base64

# --- 1. CONFIGURAZIONE E DATABASE ---
st.set_page_config(page_title="CRM Michelino", page_icon="💼", layout="centered")

# --- FUNZIONE PER RIPRODURRE AUDIO ---
def play_audio(file_path):
    if os.path.exists(file_path):
        with open(file_path, "rb") as f:
            data = f.read()
            b64 = base64.b64encode(data).decode()
            # Questo frammento HTML/JS forza la riproduzione
            audio_html = f"""
                <audio id="audio_tag" autoplay>
                    <source src="data:audio/mpeg;base64,{b64}" type="audio/mpeg">
                </audio>
                <script>
                    var audio = document.getElementById('audio_tag');
                    audio.play();
                </script>
                """
            # Usiamo un componente vuoto per iniettare l'audio
            components.html(audio_html, height=0)

# Inizializzazione chiavi di stato
if 'lat_val' not in st.session_state: st.session_state.lat_val = ""
if 'lon_val' not in st.session_state: st.session_state.lon_val = ""
if 'ricerca_attiva' not in st.session_state: st.session_state.ricerca_attiva = False
if 'edit_mode_id' not in st.session_state: st.session_state.edit_mode_id = None

def inizializza_db():
    with sqlite3.connect('crm_mobile.db') as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS visite 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      cliente TEXT, localita TEXT, provincia TEXT,
                      tipo_cliente TEXT, data TEXT, note TEXT,
                      data_followup TEXT, data_ordine TEXT, agente TEXT,
                      latitudine TEXT, longitudine TEXT)''')
        
        try:
            c.execute("ALTER TABLE visite ADD COLUMN copiato_crm INTEGER DEFAULT 0")
        except:
            pass 
            
        conn.commit()

inizializza_db()

# --- FUNZIONE JAVASCRIPT PER COPIARE ---
def copia_negli_appunti(testo, id_bottone):
    html_code = f"""
    <button id="btn_{id_bottone}" style="
        background-color: #f0f2f6; border: 1px solid #dcdfe3; border-radius: 5px; 
        padding: 5px 10px; cursor: pointer; width: 100%; font-weight: bold; color: #31333F;">
        📋 COPIA NOTE
    </button>
    <script>
    document.getElementById("btn_{id_bottone}").onclick = function() {{
        const text = `{testo}`;
        navigator.clipboard.writeText(text).then(function() {{
            alert("Note copiate negli appunti!");
        }}, function(err) {{
            console.error('Errore nel copia:', err);
        }});
    }};
    </script>
    """
    components.html(html_code, height=45)

# --- 2. FUNZIONI DI SUPPORTO ---
def controllo_backup_automatico():
    cartella_backup = "BACKUPS_AUTOMATICI"
    if not os.path.exists(cartella_backup): os.makedirs(cartella_backup)
    files = [f for f in os.listdir(cartella_backup) if f.endswith('.xlsx')]
    fare_backup = not files
    if files:
        percorsi_completi = [os.path.join(cartella_backup, f) for f in files]
        file_piu_recente = max(percorsi_completi, key=os.path.getctime)
        if datetime.now() - datetime.fromtimestamp(os.path.getctime(file_piu_recente)) > timedelta(days=7):
            fare_backup = True
    if fare_backup:
        with sqlite3.connect('crm_mobile.db') as conn:
            try:
                df = pd.read_sql_query("SELECT * FROM visite ORDER BY id DESC", conn)
                if not df.empty:
                    nome_file = f"Backup_Auto_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
                    df.to_excel(os.path.join(cartella_backup, nome_file), index=False)
                    st.toast("🛡️ Backup Settimanale Eseguito!", icon="✅")
            except: pass 

controllo_backup_automatico()

def applica_dati_gps():
    if 'gps_temp' in st.session_state:
        dati = st.session_state['gps_temp']
        st.session_state.localita_key = dati['citta']
        st.session_state.prov_key = dati['prov']
        st.session_state.lat_val = dati['lat']
        st.session_state.lon_val = dati['lon']
        del st.session_state['gps_temp']

def salva_visita():
    s = st.session_state
    cliente = s.get('cliente_key', '').strip()
    note = s.get('note_key', '').strip()
    if cliente and note:
        with sqlite3.connect('crm_mobile.db') as conn:
            c = conn.cursor()
            data_visita_fmt = s.data_key.strftime("%d/%m/%Y")
            data_ord = s.data_key.strftime("%Y-%m-%d")
            scelta = s.get('fup_opt', 'No')
            data_fup = ""
            giorni = {"1 gg": 1, "7 gg": 7, "15 gg": 15, "30 gg": 30}
            if scelta in giorni:
                data_fup = (s.data_key + timedelta(days=giorni[scelta])).strftime("%Y-%m-%d")
            c.execute("""INSERT INTO visite (cliente, localita, provincia, tipo_cliente, data, note, 
                         data_followup, data_ordine, agente, latitudine, longitudine, copiato_crm) 
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""", 
                      (cliente, s.localita_key.upper(), s.prov_key.upper(), s.get('tipo_key', 'Prospect'), 
                       data_visita_fmt, note, data_fup, data_ord, s.agente_key, s.lat_val, s.lon_val))
            conn.commit()
        st.session_state.cliente_key = ""; st.session_state.localita_key = ""; st.session_state.prov_key = ""
        st.session_state.note_key = ""; st.session_state.lat_val = ""; st.session_state.lon_val = ""; st.session_state.fup_opt = "No"
        st.toast("✅ Visita salvata!", icon="💾")
    else: st.error("⚠️ Inserisci almeno Cliente e Note!")

# --- 3. INTERFACCIA UTENTE ---
st.title("💼 CRM Michelino")

# --- LOGICA AUDIO SU ESPANDER ---
nuova_visita_exp = st.expander("➕ REGISTRA NUOVA VISITA", expanded=False)
if nuova_visita_exp.expanded:
    play_audio("crm.mpeg")

with nuova_visita_exp:
    st.text_input("Nome Cliente", key="cliente_key")
    st.selectbox("Tipo Cliente", ["Cliente", "Prospect"], key="tipo_key")
    col_l, col_p = st.columns([3, 1]) 
    with col_l: st.text_input("Località", key="localita_key")
    with col_p: st.text_input("Prov.", key="prov_key", max_chars=2)
    
    loc_data = get_geolocation()
    if st.button("📍 CERCA POSIZIONE GPS", use_container_width=True):
        if loc_data and 'coords' in loc_data:
            try:
                lat, lon = loc_data['coords']['latitude'], loc_data['coords']['longitude']
                headers = {'User-Agent': 'CRM_App/1.0'}
                r = requests.get(f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}", headers=headers).json()
                a = r.get('address', {})
                citta = a.get('city', a.get('town', a.get('village', '')))
                prov_full = a.get('county', '')
                prov_sigla = "RM" if "Roma" in prov_full or "Rome" in prov_full else (prov_full[:2].upper() if prov_full else "??")
                st.session_state['gps_temp'] = {'citta': citta.upper() if citta else "", 'prov': prov_sigla, 'lat': str(lat), 'lon': str(lon)}
            except: st.warning("Errore GPS.")
        else: st.warning("⚠️ Consenti il GPS.")

    if 'gps_temp' in st.session_state:
        d = st.session_state['gps_temp']
        st.info(f"🛰️ Trovato: **{d['citta']} ({d['prov']})**")
        c_yes, c_no = st.columns(2)
        with c_yes: st.button("✅ INSERISCI", on_click=applica_dati_gps, use_container_width=True)
        with c_no: 
            if st.button("❌ ANNULLA", use_container_width=True): 
                del st.session_state['gps_temp']; st.rerun()

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1: st.date_input("Data", datetime.now(), key="data_key")
    with c2: st.selectbox("Agente", ["Galli", "Barchetti", "Bettucci", "E.R.", "Mion", "Saccon", "BAÙ"], key="agente_key")
    st.text_area("Note", key="note_key", height=150)
    st.write("📅 **Pianifica Ricontatto:**")
    st.radio("Scadenza", ["No", "1 gg", "7 gg", "15 gg", "30 gg"], key="fup_opt", horizontal=True, label_visibility="collapsed")
    st.button("💾 SALVA VISITA", on_click=salva_visita, use_container_width=True)

st.divider()

# --- ALERT SCADENZE ---
with sqlite3.connect('crm_mobile.db') as conn:
    oggi = datetime.now().strftime("%Y-%m-%d")
    df_scadenze = pd.read_sql_query(f"SELECT * FROM visite WHERE data_followup != '' AND data_followup <= '{oggi}' ORDER BY data_followup ASC", conn)

if not df_scadenze.empty:
    st.error(f"⚠️ **HAI {len(df_scadenze)} CLIENTI DA RICONTATTARE!**")
    for _, row in df_scadenze.iterrows():
        with st.container(border=True):
            st.markdown(f"**{row['cliente']}** - {row['localita']}")
            c1, c2, c3 = st.columns([1, 1, 1])
            with c1:
                if st.button("+1 ☀️", key=f"p1_{row['id']}", use_container_width=True):
                    with sqlite3.connect('crm_mobile.db') as conn:
                        conn.execute("UPDATE visite SET data_followup = ? WHERE id = ?", ((datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"), row['id']))
                    st.rerun()
            with c2:
                if st.button("+7 📅", key=f"p7_{row['id']}", use_container_width=True):
                    with sqlite3.connect('crm_mobile.db') as conn:
                        conn.execute("UPDATE visite SET data_followup = ? WHERE id = ?", ((datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"), row['id']))
                    st.rerun()
            with c3:
                if st.button("✅ Fatto", key=f"ok_{row['id']}", type="primary", use_container_width=True):
                    with sqlite3.connect('crm_mobile.db') as conn:
                        conn.execute("UPDATE visite SET data_followup = '' WHERE id = ?", (row['id'],))
                    st.rerun()

# --- RICERCA E ARCHIVIO ---
st.subheader("🔍 Archivio Visite")
f1, f2, f3, f4, f5 = st.columns([1.5, 1, 1, 1, 1])
t_ricerca = f1.text_input("Cerca Cliente o Città")
periodo = f2.date_input("Periodo", [datetime.now() - timedelta(days=60), datetime.now()])
f_agente = f3.selectbox("Filtra Agente", ["Tutti", "Galli", "Barchetti", "Bettucci", "E.R.", "Mion", "Saccon", "BAÙ"])
f_tipo = f4.selectbox("Filtra Tipo", ["Tutti", "Prospect", "Cliente"])
f_stato_crm = f5.selectbox("Stato CRM", ["Tutti", "Da Caricare", "Caricati"])

if st.button("🔎 CERCA VISITE", use_container_width=True):
    st.session_state.ricerca_attiva = True
    st.session_state.edit_mode_id = None 

if st.session_state.ricerca_attiva:
    with sqlite3.connect('crm_mobile.db') as conn:
        df = pd.read_sql_query("SELECT * FROM visite ORDER BY data_ordine DESC", conn)
    if t_ricerca: df = df[df['cliente'].str.contains(t_ricerca, case=False) | df['localita'].str.contains(t_ricerca, case=False)]
    if f_agente != "Tutti": df = df[df['agente'] == f_agente]
    if f_tipo != "Tutti": df = df[df['tipo_cliente'] == f_tipo]
    if f_stato_crm == "Da Caricare": df = df[(df['copiato_crm'] == 0) | (df['copiato_crm'].isnull())]
    elif f_stato_crm == "Caricati": df = df[df['copiato_crm'] == 1]
    if isinstance(periodo, (list, tuple)) and len(periodo) == 2:
         df = df[(df['data_ordine'] >= periodo[0].strftime("%Y-%m-%d")) & (df['data_ordine'] <= periodo[1].strftime("%Y-%m-%d"))]

    if not df.empty:
        st.success(f"Trovate {len(df)} visite.")
        for _, row in df.iterrows():
            icona_crm = "✅" if row.get('copiato_crm') == 1 else ""
            with st.expander(f"{icona_crm} {row['data']} - {row['cliente']}"):
                if st.session_state.edit_mode_id == row['id']:
                    # Parte Modifica (omessa per brevità, ma presente nel tuo codice originale)
                    st.write("Modifica in corso...")
                    if st.button("Annulla"): st.session_state.edit_mode_id = None; st.rerun()
                else:
                    st.write(f"**Note:** {row['note']}")
                    copia_negli_appunti(row['note'].replace("`", "'"), row['id'])
                    check_val = st.checkbox("✅ Salvato su CRM", value=(row.get('copiato_crm') == 1), key=f"chk_crm_{row['id']}")
                    if check_val != (row.get('copiato_crm') == 1):
                        with sqlite3.connect('crm_mobile.db') as conn:
                            conn.execute("UPDATE visite SET copiato_crm = ? WHERE id = ?", (1 if check_val else 0, row['id']))
                        st.rerun()
    else: st.warning("Nessun risultato.")

# --- AMMINISTRAZIONE ---
st.divider()
with st.expander("🛠️ AMMINISTRAZIONE"):
    with sqlite3.connect('crm_mobile.db') as conn:
        df_full = pd.read_sql_query("SELECT * FROM visite", conn)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_full.to_excel(writer, index=False)
    st.download_button("📥 SCARICA EXCEL", output.getvalue(), "backup.xlsx", use_container_width=True)

# --- LOGO ---
st.divider()
try:
    st.image("logo.jpg", use_container_width=True)
    st.markdown("<p style='text-align: center; color: grey;'>CRM MICHELONE APPROVED</p>", unsafe_allow_html=True)
except: st.info("✅ Michelone Approved")
