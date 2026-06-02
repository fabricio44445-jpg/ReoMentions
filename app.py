import streamlit as st, feedparser, pandas as pd, urllib.parse, altair as alt, time, nltk, os
from datetime import datetime, timedelta
from textblob import TextBlob
from collections import Counter
from googleapiclient.discovery import build

# --- STEP 1: INITIALIZE AI & PLATFORM SETTINGS ---
try: 
    nltk.data.find('tokenizers/punkt') 
except: 
    nltk.download('punkt', quiet=True)

# Pulls the key securely from Streamlit's hidden vault
try:
    YOUTUBE_API_KEY = st.secrets["YOUTUBE_API_KEY"]
except:
    YOUTUBE_API_KEY = None
    st.sidebar.warning("⚠️ YouTube API Key missing from Streamlit Secrets.")
    
DB_FILE = "mentions_archive.csv" 

ICONS = {"Reddit": "🟧", "Google News": "📰", "YouTube": "🟥", "Blogs & EuroTech": "✍️"}

st.set_page_config(page_title="Global Marketing Hub", page_icon="🧠", layout="wide")

st.markdown("""
<style>
    #MainMenu, footer {visibility: hidden;} 
    .modern-card { background-color: #f8fafc !important; padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); margin-bottom: 16px; border: 1px solid #e2e8f0; } 
    .card-title { margin: 0 0 8px 0; font-size: 1.15rem; color: #0f172a !important; font-weight: 600; } 
    .card-bottom { display: flex; justify-content: space-between; font-size: 0.85rem; color: #475569 !important; } 
    .card-link { color: #2563eb !important; text-decoration: none; font-weight: bold; } 
    .metric-val { font-size: 2rem; font-weight: bold; color: #0f172a !important; }
</style>
""", unsafe_allow_html=True)

for k, v in {"filters": ["Reolink", "omvi", "Magicam"], "page": 1}.items():
    st.session_state.setdefault(k, v)

# --- STEP 2: SMALL HELPER OPERATIONS ---
def get_sentiment(text):
    s = TextBlob(text).sentiment.polarity
    return ("🟢 Positive", s) if s > 0.15 else ("🔴 Negative", s) if s < -0.15 else ("⚪ Neutral", s)

def time_ago(dt):
    secs = int((datetime.now() - dt).total_seconds())
    return "just now" if secs < 60 else f"{secs//60}m ago" if secs < 3600 else f"{secs//3600}h ago" if secs < 86400 else f"{secs//86400}d ago"

def get_top_topic(mentions):
    ignore = {'reolink', 'camera', 'cameras', 'video', 'security', 'http', 'https', 'com', 'www', 'reddit', 'the', 'and', 'for', 'this', 'new', 'omvi', 'magicam'}
    words = [w.strip("?,.:;\"'()![]{}").lower() for m in mentions for w in m['title'].split() if w.strip("?,.:;\"'()![]{}").lower() not in ignore and len(w)>3]
    return Counter(words).most_common(1)[0][0].title() if words else "General"

# --- STEP 3: THE SCRAPING ENGINE (WITH LOCAL DATA TRAP) ---
@st.cache_data(ttl=900)
def fetch_data(queries, active_srcs):
    entries = [] 
    for q in queries:
        if not q: continue
        enc_q, clean_q = urllib.parse.quote(q), q.replace(' ', '')
        feeds = {}
        
        if "Google News" in active_srcs: feeds["Google News"] = f"https://news.google.com/rss/search?q={enc_q}"
        if "Reddit" in active_srcs: feeds["Reddit"] = f"https://www.reddit.com/search.rss?q={enc_q}&sort=new&limit=100"
        if "Blogs & EuroTech" in active_srcs:
            feeds.update({"Blogs & EuroTech": f"https://wordpress.com/tag/{clean_q}/feed",
                          "ComputerBase DE": "https://www.computerbase.de/rss/news.xml",
                          "Les Numériques FR": "https://www.lesnumeriques.com/rss.xml"})

        for name, url in feeds.items():
            try:
                for e in feedparser.parse(url).entries:
                    if ("DE" in name or "FR" in name) and q.lower() not in e.title.lower(): continue
                    dt = e.get('published_parsed') or e.get('updated_parsed')
                    label, score = get_sentiment(e.title)
                    entries.append({"brand": q, "source": "Blogs & EuroTech" if "DE" in name or "FR" in name else name, 
                                    "title": e.title, "author": e.get('author', 'Creator'), "link": e.link, 
                                    "time": datetime(*dt[:6]) if dt else datetime.now(), "sentiment": label, "score": score})
            except: pass

        if "YouTube" in active_srcs and YOUTUBE_API_KEY:
            try:
                res = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY).search().list(q=q, part='snippet', type='video', order='date', maxResults=50).execute()
                for i in res.get('items', []):
                    if vid := i['id'].get('videoId'):
                        label, score = get_sentiment(i['snippet']['title'])
                        entries.append({"brand": q, "source": "YouTube", "title": i['snippet']['title'], "author": i['snippet']['channelTitle'],
                                        "link": f"http://youtube.com/watch?v={vid}", 
                                        "time": datetime.strptime(i['snippet']['publishedAt'], "%Y-%m-%dT%H:%M:%SZ"), 
                                        "sentiment": label, "score": score})
            except Exception as e: st.sidebar.error(f"YouTube Error: {e}")
            
    new_df = pd.DataFrame(entries)
    if not new_df.empty:
        new_df['time'] = pd.to_datetime(new_df['time']).dt.tz_localize(None)
        
    if os.path.exists(DB_FILE):
        db_df = pd.read_csv(DB_FILE)
        db_df['time'] = pd.to_datetime(db_df['time'])
        combined_df = pd.concat([db_df, new_df], ignore_index=True)
    else:
        combined_df = new_df
        
    if not combined_df.empty:
        combined_df = combined_df.drop_duplicates(subset=['link'], keep='first')
        thirty_days_ago = datetime.now() - timedelta(days=30)
        combined_df = combined_df[combined_df['time'] >= thirty_days_ago]
        combined_df.to_csv(DB_FILE, index=False)
        
        records = combined_df.to_dict('records')
        for r in records: 
            if isinstance(r['time'], pd.Timestamp): r['time'] = r['time'].to_pydatetime()
            elif isinstance(r['time'], str): r['time'] = pd.to_datetime(r['time']).to_pydatetime()
        return records
        
    return []

# --- STEP 4: RENDER SIDEBAR CONTROLS ---
with st.sidebar:
    st.title("⚙️ Controls")
    tgt = st.radio("Target:", st.session_state.filters)
    
    if (new_f := st.text_input("➕ Add Filter:")) and st.button("Add") and new_f not in st.session_state.filters:
        st.session_state.filters.append(new_f); st.rerun()
        
    removable = [f for f in st.session_state.filters if f != "Reolink"]
    if removable and (del_f := st.selectbox("➖ Remove:", removable)) and st.button("Delete"):
        st.session_state.filters.remove(del_f); st.rerun()

    st.divider()
    comp = st.text_input("⚔️ Competitor:", placeholder="e.g. Arlo").strip()
    evt_date = st.date_input("🗓️ Event Date:", value=None)
    evt_name = st.text_input("Event Name:") if evt_date else None

    st.divider()
    sort_by = st.selectbox("🧠 Sort By:", ["Newest First", "Most Positive 🟢", "Most Negative 🔴"])
    srcs = st.multiselect("📡 Streams:", list(ICONS.keys()), default=list(ICONS.keys()))
    
    auto_refresh = st.toggle("Enable Auto-Refresh", value=True)
    refresh_interval = st.slider("Refresh Interval (sec)", 300, 3600, 900)
    if st.button("🔄 Force Data Sync"): st.cache_data.clear(); st.session_state.page = 1; st.rerun()

# --- STEP 5: RUN THE APP ENGINE & LAY OUT MAIN HUB ---
raw_mentions = fetch_data([tgt, comp], srcs)

# THE FIX: Only show data for the currently active target and competitor (ignore old database ghost entries)
active_brands = [tgt]
if comp:
    active_brands.append(comp)
mentions = [m for m in raw_mentions if m['brand'] in active_brands]

tgt_mentions = sorted([m for m in mentions if m['brand'] == tgt], 
                      key=lambda x: x['time'] if "Newest" in sort_by else x['score'], 
                      reverse="Negative" not in sort_by)

st.title(f"🧠 Hub: {tgt}")
st.markdown(f"**Target Volume:** {len(tgt_mentions)} | **Competitor Volume:** {len([m for m in mentions if m['brand']==comp])}")

if tgt_mentions:
    now = datetime.now()
    d_mentions = [m for m in tgt_mentions if m['time'] >= now - timedelta(days=1)]
    w_mentions = [m for m in tgt_mentions if m['time'] >= now - timedelta(days=7)]
    d_topic, w_topic = get_top_topic(d_mentions), get_top_topic(w_mentions)
    
    if d_mentions:
        driver = next((m for m in d_mentions if d_topic.lower() in m['title'].lower()), d_mentions[0])
        st.info(f"### 🧠 AI Daily Briefing\n**Today's Pulse:** Focused on **'{d_topic}'** ({driver['sentiment']}). Driver: *\"{driver['title']}\"*\n\n**Weekly Macro:** Anchored on **'{w_topic}'**.")
    else:
        st.info(f"### 🧠 AI Daily Briefing\nStable today. Weekly macro focus: **'{w_topic}'**.")

if mentions:
    st.markdown("### 📊 30-Day Timeline")
    df = pd.DataFrame(mentions)
    df['Date'] = pd.to_datetime(df['time']).dt.date
    df = df[df['Date'] >= (datetime.now().date() - timedelta(days=30))]
    
    if not df.empty:
        chart = alt.Chart(df.groupby(['Date', 'brand']).size().reset_index(name='Vol')).encode(x='Date:T', y='Vol:Q', color='brand:N').mark_line(point=True)
        if evt_date:
            rule = alt.Chart(pd.DataFrame({'Date': [pd.to_datetime(evt_date)]})).mark_rule(color='#10b981', strokeDash=[5,5]).encode(x='Date:T')
            chart += rule + rule.mark_text(text=f"🚀 {evt_name}", align='left', dx=5, dy=-120) if evt_name else rule
        st.altair_chart(chart, use_container_width=True)

# --- THE STREAMS FEED WITH PAGE NUMBER BUTTONS ---
if tgt_mentions:
    st.markdown(f"### 📰 Stream")
    items_per_page, total_pages = 10, max(1, (len(tgt_mentions) + 9) // 10)
    st.session_state.page = min(st.session_state.page, total_pages)
    
    start_p = max(1, st.session_state.page - 2)
    end_p = min(total_pages, start_p + 4)
    p_range = list(range(start_p, end_p + 1))
    
    cols = st.columns([1] + [0.5] * len(p_range) + [1])
    
    if cols[0].button("⬅️", disabled=(st.session_state.page == 1), use_container_width=True): 
        st.session_state.page -= 1; st.rerun()
        
    for idx, p in enumerate(p_range):
        if cols[idx + 1].button(str(p), type="primary" if p == st.session_state.page else "secondary", use_container_width=True):
            st.session_state.page = p; st.rerun()
            
    if cols[-1].button("➡️", disabled=(st.session_state.page == total_pages), use_container_width=True): 
        st.session_state.page += 1; st.rerun()

    for m in tgt_mentions[(st.session_state.page-1)*items_per_page : st.session_state.page*items_per_page]:
        st.markdown(f"""<div class="modern-card">
            <h3 class="card-title">{ICONS.get(m['source'], "📌")} {m['title']}</h3>
            <span style="background:#e2e8f0; color:#0f172a; padding:4px 8px; border-radius:8px; font-size:0.8rem; font-weight:600;">{m['sentiment']}</span>
            <div class="card-bottom" style="margin-top:12px;">
                <span>👤 {m['author']} • 📅 {time_ago(m['time'])} • {m['source']}</span>
                <a href="{m['link']}" target="_blank" class="card-link">Link ↗</a>
            </div></div>""", unsafe_allow_html=True)

if auto_refresh:
    time.sleep(refresh_interval)
    st.rerun()