import streamlit as st
import feedparser
from datetime import datetime, date
import time
from googleapiclient.discovery import build
import pandas as pd
from textblob import TextBlob
from collections import Counter
import nltk
import urllib.parse
import altair as alt
import requests

# --- AUTO-DOWNLOAD REQUIRED AI COMPONENTS ---
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt', quiet=True)

feedparser.USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
YOUTUBE_API_KEY = "AIzaSyCB26TbgxGyRiWCwO0H_ptUQsH8tM0SpGQ"

PLATFORM_ICONS = {
    "Reddit": "🟧", "Google News": "📰", "Bing News": "🌐", 
    "YouTube": "🟥", "Yahoo News": "🟣", "Hacker News": "👾", 
    "Medium": "📝", "Flickr": "📷", "Blogs": "✍️", "Podcasts": "🎙️"
}

# --- 1. PAGE SETUP ---
st.set_page_config(page_title="Reolink Marketing Engine", page_icon="📈", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    #MainMenu {visibility: hidden;} footer {visibility: hidden;}
    html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; }
    .modern-card { background-color: #ffffff; border-radius: 12px; padding: 20px 24px; margin-bottom: 16px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); border: 1px solid #f1f5f9; }
    @media (prefers-color-scheme: dark) { .modern-card { background-color: #1e293b; border: 1px solid #334155; } }
    .card-title { font-size: 1.15rem; font-weight: 600; margin-bottom: 8px; margin-top: 0; line-height: 1.4; }
    .card-sentiment { font-size: 0.85rem; font-weight: 600; margin-bottom: 12px; display: inline-block; padding: 2px 8px; border-radius: 12px; background: rgba(0,0,0,0.05); }
    .card-bottom { display: flex; justify-content: space-between; align-items: center; font-size: 0.85rem; color: #64748b; font-weight: 500; }
    .card-link { text-decoration: none; color: #3b82f6; font-weight: 600; background-color: rgba(59,130,246,0.1); padding: 6px 12px; border-radius: 6px; }
    .metric-label { font-size: 0.85rem; text-transform: uppercase; color: #64748b; font-weight: 600; margin-bottom: 4px; }
    .metric-value { font-size: 2rem; font-weight: 700; }
</style>
""", unsafe_allow_html=True)

if "focus_areas" not in st.session_state: st.session_state.focus_areas = ["All Reolink"]
if "current_page" not in st.session_state: st.session_state.current_page = 1

# --- 2. SIDEBAR CONTROLS ---
with st.sidebar:
    st.title("⚙️ Marketing Controls")
    
    st.subheader("🎯 Primary Target")
    active_filter = st.radio("Select Brand Focus:", st.session_state.focus_areas, label_visibility="collapsed")
    
    st.subheader("⚔️ Competitor Benchmark")
    competitor_input = st.text_input("Enter rival to track (e.g. Arlo):", placeholder="Leave blank to disable")
    
    st.subheader("🗓️ Campaign Marker")
    event_date = st.date_input("Highlight an event on the chart:", value=None)
    event_name = st.text_input("Event Name:", placeholder="June 3 Livestream") if event_date else None

    st.divider()
    display_language = st.selectbox("🌍 Filter Region:", ["All Languages 🌍", "EN 🇺🇸", "FR 🇫🇷", "DE 🇩🇪"])
    sort_by = st.selectbox("🧠 Sort Mentions By:", ["Newest First", "Most Positive 🟢", "Most Negative 🔴"])
    selected_sources = st.multiselect("📡 Sources:", list(PLATFORM_ICONS.keys()), default=["Reddit", "Google News", "YouTube", "Podcasts"])
    
    auto_refresh = st.toggle("Enable Auto-Refresh", value=True)
    refresh_interval = st.slider("Refresh Interval (sec)", min_value=1800, max_value=7200, value=3600)
    if st.button("🔄 Force Sync Now", use_container_width=True):
        st.session_state.current_page = 1
        st.rerun()

# --- 3. DYNAMIC SEARCH ENGINE ---
lang_configs = {
    "EN 🇺🇸": {"gnews": "hl=en-US&gl=US&ceid=US:en", "bing": "mkt=en-US", "yt": "en", "yahoo": "news.search.yahoo.com"},
    "FR 🇫🇷": {"gnews": "hl=fr&gl=FR&ceid=FR:fr", "bing": "mkt=fr-FR", "yt": "fr", "yahoo": "fr.news.search.yahoo.com"},
    "DE 🇩🇪": {"gnews": "hl=de&gl=DE&ceid=DE:de", "bing": "mkt=de-DE", "yt": "de", "yahoo": "de.news.search.yahoo.com"}
}

def analyze_sentiment(text):
    score = TextBlob(text).sentiment.polarity
    if score > 0.15: return "🟢 Positive", score
    elif score < -0.15: return "🔴 Negative", score
    else: return "⚪ Neutral", score

def fetch_target_mentions(base_query, brand_label):
    encoded_query = urllib.parse.quote(base_query)
    entries = []
    
    for lang_name, l_params in lang_configs.items():
        FEEDS = {
            "Google News": f"https://news.google.com/rss/search?q={encoded_query}&{l_params['gnews']}",
            "Bing News": f"https://www.bing.com/news/search?q={encoded_query}&format=rss&{l_params['bing']}",
            "Yahoo News": f"https://{l_params['yahoo']}/rss?p={encoded_query}"
        }
        if lang_name == "EN 🇺🇸":
            FEEDS["Reddit"] = f"https://www.reddit.com/search.rss?q={encoded_query}&sort=new"
            FEEDS["Hacker News"] = f"https://hnrss.org/newest?q={encoded_query}"
            query_no_space = base_query.replace(' ', '')
            FEEDS["Medium"] = f"https://medium.com/feed/tag/{query_no_space}"
            FEEDS["Blogs"] = f"https://wordpress.com/tag/{query_no_space}/feed"
            FEEDS["Flickr"] = f"https://www.flickr.com/services/feeds/photos_public.gne?tags={query_no_space}&format=rss_200"

        # Standard RSS Fetching
        for source, url in FEEDS.items():
            if source in selected_sources:
                try:
                    feed = feedparser.parse(url)
                    for entry in feed.entries:
                        dt = entry.get('published_parsed') or entry.get('updated_parsed')
                        author = entry.get('author', 'Unknown Author')
                        sentiment_label, sentiment_score = analyze_sentiment(entry.title)
                        entries.append({
                            "brand": brand_label, "source": source, "title": entry.title,
                            "author": author, "link": entry.link,
                            "time": datetime(*dt[:6]) if dt else datetime.now(),
                            "sentiment": sentiment_label, "score": sentiment_score, "language": lang_name
                        })
                except: pass 

        # iTunes Podcast Fetching (EN Only for optimal results)
        if "Podcasts" in selected_sources and lang_name == "EN 🇺🇸":
            try:
                podcast_url = f"https://itunes.apple.com/search?term={encoded_query}&entity=podcastEpisode&limit=15"
                response = requests.get(podcast_url, timeout=5).json()
                for result in response.get('results', []):
                    entries.append({
                        "brand": brand_label,
                        "source": "Podcasts",
                        "title": f"{result.get('collectionName', 'Unknown Show')} - {result.get('trackName', 'Episode')}",
                        "author": result.get('artistName', 'Unknown Host'),
                        "link": result.get('trackViewUrl', ''),
                        "time": datetime.strptime(result['releaseDate'], "%Y-%m-%dT%H:%M:%SZ"),
                        "sentiment": "⚪ Neutral",
                        "score": 0.0,
                        "language": "EN 🇺🇸"
                    })
            except: pass

        # YouTube Fetching
        if "YouTube" in selected_sources and YOUTUBE_API_KEY:
            try:
                youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
                request = youtube.search().list(q=base_query, part='snippet', type='video', order='date', relevanceLanguage=l_params['yt'], maxResults=15)
                response = request.execute()
                for item in response.get('items', []):
                    video_id = item['id'].get('videoId')
                    if video_id:
                        pub_time = datetime.strptime(item['snippet']['publishedAt'], "%Y-%m-%dT%H:%M:%SZ")
                        channel_name = item['snippet']['channelTitle']
                        sentiment_label, sentiment_score = analyze_sentiment(item['snippet']['title'])
                        entries.append({
                            "brand": brand_label, "source": "YouTube", "title": item['snippet']['title'],
                            "author": channel_name, "link": f"https://www.youtube.com/watch?v={video_id}",
                            "time": pub_time, "sentiment": sentiment_label, "score": sentiment_score, "language": lang_name
                        })
            except: pass
            
    return entries

primary_query = "Reolink" if active_filter == "All Reolink" else f"Reolink {active_filter}"
all_raw_mentions = fetch_target_mentions(primary_query, "Reolink")

if competitor_input:
    comp_mentions = fetch_target_mentions(competitor_input.strip(), competitor_input.strip())
    all_raw_mentions.extend(comp_mentions)

unique_entries = {m['link']: m for m in all_raw_mentions}
all_raw_mentions = list(unique_entries.values())

if display_language != "All Languages 🌍":
    mentions = [m for m in all_raw_mentions if m['language'] == display_language]
else:
    mentions = all_raw_mentions

brand_mentions = [m for m in mentions if m['brand'] == "Reolink"]

if sort_by == "Newest First": brand_mentions = sorted(brand_mentions, key=lambda x: x['time'], reverse=True)
elif sort_by == "Most Positive 🟢": brand_mentions = sorted(brand_mentions, key=lambda x: x['score'], reverse=True)
elif sort_by == "Most Negative 🔴": brand_mentions = sorted(brand_mentions, key=lambda x: x['score'])

# --- 4. MAIN DASHBOARD UI ---
st.title(f"📈 Share of Voice & Campaign Tracker")

st.markdown(f"""
<div style="display: flex; gap: 16px; margin-bottom: 24px;">
    <div class="modern-card metric-box" style="flex: 1; margin-bottom: 0;">
        <div class="metric-label">Primary Brand</div>
        <div class="metric-value" style="color: #3b82f6;">{len([m for m in mentions if m['brand']=='Reolink'])} Mentions</div>
    </div>
    <div class="modern-card metric-box" style="flex: 1; margin-bottom: 0;">
        <div class="metric-label">Competitor ({competitor_input or 'None'})</div>
        <div class="metric-value" style="color: #ef4444;">{len([m for m in mentions if m['brand']==competitor_input]) if competitor_input else 0} Mentions</div>
    </div>
</div>
""", unsafe_allow_html=True)

if mentions:
    st.markdown("### 📊 14-Day Share of Voice")
    df = pd.DataFrame(mentions)
    df['time'] = pd.to_datetime(df['time']).dt.tz_localize(None)
    df = df[df['time'] >= (datetime.now() - pd.Timedelta(days=14))]
    
    if not df.empty:
        df['Date'] = df['time'].dt.date
        chart_data = df.groupby(['Date', 'brand']).size().reset_index(name='Mentions')
        
        base = alt.Chart(chart_data).encode(
            x=alt.X('Date:T', title=''),
            y=alt.Y('Mentions:Q', title='Volume'),
            color=alt.Color('brand:N', scale=alt.Scale(range=['#3b82f6', '#ef4444']), legend=alt.Legend(title="Brand"))
        )
        line = base.mark_line(interpolate='monotone', strokeWidth=3)
        points = base.mark_circle(size=80, opacity=1)
        chart = line + points
        
        if event_date:
            event_df = pd.DataFrame({'Date': [pd.to_datetime(event_date)]})
            rule = alt.Chart(event_df).mark_rule(color='#10b981', strokeWidth=2, strokeDash=[5, 5]).encode(x='Date:T')
            if event_name:
                text = alt.Chart(event_df).mark_text(align='left', dx=5, dy=-120, color='#10b981', fontWeight='bold').encode(
                    x='Date:T', text=alt.value(f"🚀 {event_name}")
                )
                chart = chart + rule + text
            else:
                chart = chart + rule
                
        st.altair_chart(chart.properties(height=350), use_container_width=True)

st.markdown("### 🗣️ The KOL Rolodex (Top Voices)")
if brand_mentions:
    valid_authors = [m['author'] for m in brand_mentions if m['author'] not in ['Unknown Author', 'Unknown Host', '']]
    top_authors = Counter(valid_authors).most_common(4)
    
    if top_authors:
        cols = st.columns(len(top_authors))
        for i, (author, count) in enumerate(top_authors):
            with cols[i]:
                st.markdown(f"""
                <div style="background: rgba(59,130,246,0.05); border: 1px solid rgba(59,130,246,0.2); border-radius: 8px; padding: 12px; text-align: center;">
                    <div style="font-size: 0.8rem; color: #64748b; text-transform: uppercase;">Top Creator</div>
                    <div style="font-weight: 700; font-size: 1.1rem; color: #1e293b; margin: 4px 0;">{author}</div>
                    <div style="font-size: 0.9rem; font-weight: 600; color: #3b82f6;">{count} Mentions</div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("Gathering creator identities. Check back soon.")

st.divider()

if brand_mentions:
    st.markdown(f"### 📰 Your Primary Feed ({len(brand_mentions)} Results)")
    items_per_page = 10
    total_pages = max(1, (len(brand_mentions) + items_per_page - 1) // items_per_page)
    if st.session_state.current_page > total_pages: st.session_state.current_page = 1
        
    start_page = max(1, st.session_state.current_page - 3)
    end_page = min(total_pages, start_page + 6)
    if end_page - start_page < 6: start_page = max(1, end_page - 6)
        
    cols = st.columns([1.5] + [1]*(end_page - start_page + 1) + [1.5])
    with cols[0]:
        if st.button("⬅️ Prev", disabled=(st.session_state.current_page == 1), use_container_width=True):
            st.session_state.current_page -= 1; st.rerun()
            
    for i, p in enumerate(range(start_page, end_page + 1)):
        with cols[i + 1]:
            if st.button(str(p), type="primary" if p == st.session_state.current_page else "secondary", use_container_width=True):
                st.session_state.current_page = p; st.rerun()
                
    with cols[-1]:
        if st.button("Next ➡️", disabled=(st.session_state.current_page == total_pages), use_container_width=True):
            st.session_state.current_page += 1; st.rerun()
            
    start_idx = (st.session_state.current_page - 1) * items_per_page
    
    for item in brand_mentions[start_idx:start_idx + items_per_page]:
        time_diff = datetime.now() - item['time']
        mins = int(max(0, time_diff.total_seconds() / 60))
        st.markdown(f"""
        <div class="modern-card">
            <h3 class="card-title">{PLATFORM_ICONS.get(item['source'], "📌")} {item['title']}</h3>
            <span class="card-sentiment">{item['sentiment']}</span>
            <div class="card-bottom">
                <span>👤 <strong>{item['author']}</strong> • 📅 {mins}m ago • via {item['source']} • {item['language']}</span>
                <a href="{item['link']}" target="_blank" class="card-link">Open Link ↗</a>
            </div>
        </div>
        """, unsafe_allow_html=True)
else:
    st.info("No recent mentions found. Waiting for updates...")

if auto_refresh:
    time.sleep(refresh_interval)
    st.rerun()