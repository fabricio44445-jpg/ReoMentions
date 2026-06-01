import streamlit as st, feedparser, pandas as pd, urllib.parse, altair as alt, time, nltk
from datetime import datetime, timedelta
from textblob import TextBlob
from collections import Counter
from googleapiclient.discovery import build

# --- SETUP & COMPONENTS ---
try: nltk.data.find('tokenizers/punkt')
except: nltk.download('punkt', quiet=True)

YOUTUBE_API_KEY = "AIzaSyCB26TbgxGyRiWCwO0H_ptUQsH8tM0SpGQ"
ICONS = {"Reddit": "🟧", "Google News": "📰", "YouTube": "🟥", "Blogs & EuroTech": "✍️"}

st.set_page_config(page_title="Global Marketing Hub", page_icon="🧠", layout="wide")
st.markdown("<style>#MainMenu, footer {visibility: hidden;} .modern-card {background: #fff; padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); margin-bottom: 16px;} .card-title {margin: 0 0 8px 0; font-size: 1.15rem;} .card-bottom {display: flex; justify-content: space-between; font-size: 0.85rem; color: #64748b;} .card-link {color: #3b82f6; text-decoration: none; font-weight: bold;} .metric-val {font-size: 2rem; font-weight: bold;}</style>", unsafe_allow_html=True)

for k, v in {"filters": ["Reolink", "omvi", "Magicam"], "page": 1}.items():
    st.session_state.setdefault(k, v)

# --- HELPER FUNCTIONS ---
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

# --- DATA ENGINE (Cached for Speed & Quota Saving) ---
@st.cache_data(ttl=900)
def fetch_data(queries, active_srcs):
    entries = []
    for q in queries:
        if not q: continue
        enc_q, clean_q = urllib.parse.quote(q), q.replace(' ', '')
        feeds = {}
        
        if "Google News" in active_srcs: feeds["Google News"] = f"https://news.google.com/rss/search?q={enc_q}"
        if "Reddit" in active_srcs: feeds["Reddit"] = f"https://www.reddit.com/search.rss?q={enc_q}&sort=new"
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
                res = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY).search().list(q=q, part='snippet', type='video', order='date', maxResults=20).execute()
                for i in res.get('items', []):
                    if vid := i['id'].get('videoId'):
                        label, score = get_sentiment(i['snippet']['title'])
                        entries.append({"brand": q, "source": "YouTube", "title": i['snippet']['title'], "author": i['snippet']['channelTitle'],
                                        "link": f"http://youtube.com/watch?v={vid}", 
                                        "time": datetime.strptime(i['snippet']['publishedAt'], "%Y-%m-%dT%H:%M:%SZ"), 
                                        "sentiment": label, "score": score})
            except Exception as e: st.sidebar.error(f"YouTube Error: {e}")
            
    return list({m['link']: m for m in entries}.values()) # Deduplicate

# --- SIDEBAR CONTROLS ---
with st.sidebar:
    st.title("⚙️ Controls")
    tgt = st.radio("Target:", st.session_state.filters)
    
    if (new_f := st.text_input("➕ Add Filter:")) and st.button("Add") and new_f not in st.session_state.filters:
        st.session_state.filters.append(new_f); st.rerun()
        
    removable = [f for f in st.session_state.filters if f != "Reolink"]
    if removable and (del_f := st.selectbox("➖ Remove:", removable)) and st.button("Delete"):
        st.session_state.filters.remove(del_f); st.rerun()

    st.divider()
    comp = st.text_input("⚔️ Competitor:", placeholder="e.g. Arlo")
    evt_date = st.date_input("🗓️ Event Date:", value=None)
    evt_name = st.text_input("Event Name:") if evt_date else None

    st.divider()
    sort_by = st.selectbox("🧠 Sort By:", ["Newest First", "Most Positive 🟢", "Most Negative 🔴"])
    srcs = st.multiselect("📡 Streams:", list(ICONS.keys()), default=list(ICONS.keys()))
    
    auto_refresh = st.toggle("Enable Auto-Refresh", value=True)
    refresh_interval = st.slider("Refresh Interval (sec)", 300, 3600, 900)
    if st.button("🔄 Force Data Sync"): st.cache_data.clear(); st.session_state.page = 1; st.rerun()

# --- EXECUTE ENGINE & RENDER UI ---
mentions = fetch_data([tgt, comp], srcs)
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
    st.markdown("### 📊 14-Day Timeline")
    df = pd.DataFrame(mentions)
    df['Date'] = pd.to_datetime(df['time']).dt.date
    df = df[df['Date'] >= (datetime.now().date() - timedelta(days=14))]
    
    if not df.empty:
        chart = alt.Chart(df.groupby(['Date', 'brand']).size().reset_index(name='Vol')).encode(x='Date:T', y='Vol:Q', color='brand:N').mark_line(point=True)
        if evt_date:
            rule = alt.Chart(pd.DataFrame({'Date': [pd.to_datetime(evt_date)]})).mark_rule(color='#10b981', strokeDash=[5,5]).encode(x='Date:T')
            chart += rule + rule.mark_text(text=f"🚀 {evt_name}", align='left', dx=5, dy=-120) if evt_name else rule
        st.altair_chart(chart, use_container_width=True)

if tgt_mentions:
    st.markdown(f"### 📰 Stream")
    items_per_page, total_pages = 10, max(1, (len(tgt_mentions) + 9) // 10)
    st.session_state.page = min(st.session_state.page, total_pages)
    
    cols = st.columns([1, 4, 1])
    if cols[0].button("⬅️ Prev", disabled=(st.session_state.page == 1)): st.session_state.page -= 1; st.rerun()
    cols[1].markdown(f"<div style='text-align:center;'>Page {st.session_state.page} of {total_pages}</div>", unsafe_allow_html=True)
    if cols[2].button("Next ➡️", disabled=(st.session_state.page == total_pages)): st.session_state.page += 1; st.rerun()

    for m in tgt_mentions[(st.session_state.page-1)*items_per_page : st.session_state.page*items_per_page]:
        st.markdown(f"""<div class="modern-card">
            <h3 class="card-title">{ICONS.get(m['source'], "📌")} {m['title']}</h3>
            <span style="background:#f1f5f9; padding:4px 8px; border-radius:8px; font-size:0.8rem;">{m['sentiment']}</span>
            <div class="card-bottom" style="margin-top:12px;">
                <span>👤 {m['author']} • 📅 {time_ago(m['time'])} • {m['source']}</span>
                <a href="{m['link']}" target="_blank" class="card-link">Link ↗</a>
            </div></div>""", unsafe_allow_html=True)

if auto_refresh:
    time.sleep(refresh_interval)
    st.rerun()