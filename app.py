import streamlit as st
import feedparser
from datetime import datetime
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
    "Medium": "📝", "Flickr": "📷", "Blogs": "✍️", "Podcasts": "🎙️",
    "EuroTech Hub": "🇪🇺"
}

# --- 1. PAGE SETUP ---
st.set_page_config(page_title="Reolink Global Intelligence Hub", page_icon="🌍", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght=400;500;600;700&display=swap');
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

# Session Memory
if "search_filters" not in st.session_state: 
    st.session_state.search_filters = ["Reolink", "Reolink ONVIF", "Magicam"]
if "current_page" not in st.session_state: 
    st.session_state.current_page = 1

# --- TIME FORMATTING HELPER ---
def format_time_ago(past_time):
    time_diff = datetime.now() - past_time
    total_seconds = int(time_diff.total_seconds())
    if total_seconds < 60: return "just now"
    minutes = total_seconds // 60
    if minutes < 60: return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24: return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"

# --- 2. SIDEBAR CONTROLS ---
with st.sidebar:
    st.title("⚙️ Global Controls")
    
    st.subheader("🎯 Target Stream")
    active_query = st.radio("Select Target Query:", st.session_state.search_filters, label_visibility="collapsed")
    
    with st.expander("➕ Add Custom Search Filter"):
        new_filter = st.text_input("Enter keywords:", placeholder="e.g., Reolink Altas")
        if st.button("Add to Monitor List", use_container_width=True):
            if new_filter and new_filter not in st.session_state.search_filters:
                st.session_state.search_filters.append(new_filter)
                st.rerun()

    with st.expander("➖ Remove Custom Filter"):
        removable = [f for f in st.session_state.search_filters if f != "Reolink"]
        if removable:
            to_remove = st.selectbox("Select filter to delete:", removable)
            if st.button("Delete Filter", use_container_width=True):
                st.session_state.search_filters.remove(to_remove)
                st.rerun()

    st.divider()
    st.subheader("⚔️ Benchmarking")
    competitor_input = st.text_input("Track companion brand:", placeholder="e.g. Arlo")
    
    st.subheader("🗓️ Campaign Marker")
    event_date = st.date_input("Highlight event:", value=None)
    event_name = st.text_input("Event Tag Name:", placeholder="EU Launch") if event_date else None

    st.divider()
    display_language = st.selectbox("🌍 Filter Region:", ["All Languages 🌍", "EN 🇺🇸", "FR 🇫🇷", "DE 🇩🇪"])
    sort_by = st.selectbox("🧠 Sort Target Feed By:", ["Newest First", "Most Positive 🟢", "Most Negative 🔴"])
    selected_sources = st.multiselect("📡 Active Streams:", list(PLATFORM_ICONS.keys()), default=["Reddit", "Google News", "YouTube", "Podcasts", "Blogs", "EuroTech Hub"])
    
    auto_refresh = st.toggle("Enable Auto-Refresh", value=True)
    refresh_interval = st.slider("Refresh Interval (sec)", min_value=1800, max_value=7200, value=3600)
    if st.button("🔄 Force Data Sync", use_container_width=True):
        st.session_state.current_page = 1
        st.rerun()

# --- 3. CROSS-BORDER PROCESSING ENGINE ---
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

def fetch_target_data(target_string, brand_label):
    encoded_query = urllib.parse.quote(target_string)
    query_no_space = target_string.replace(' ', '')
    entries = []
    
    for lang_name, l_params in lang_configs.items():
        # Global Baseline Feeds (Now includes Reddit, Blogs, and Podcasts globally)
        FEEDS = {
            "Google News": f"https://news.google.com/rss/search?q={encoded_query}&{l_params['gnews']}",
            "Bing News": f"https://www.bing.com/news/search?q={encoded_query}&format=rss&{l_params['bing']}",
            "Yahoo News": f"https://{l_params['yahoo']}/rss?p={encoded_query}",
            "Reddit": f"https://www.reddit.com/search.rss?q={encoded_query}&sort=new",
            "Blogs": f"https://wordpress.com/tag/{query_no_space}/feed",
            "Medium": f"https://medium.com/feed/tag/{query_no_space}"
        }
        
        # Inject Dedicated European High-Traffic Tech Aggregators
        if lang_name == "DE 🇩🇪" and "EuroTech Hub" in selected_sources:
            FEEDS["EuroTech Hub"] = f"https://www.computerbase.de/rss/news.xml" # Monitored via Title Matching downstream
            
        if lang_name == "FR 🇫🇷" and "EuroTech Hub" in selected_sources:
            FEEDS["EuroTech Hub"] = f"https://www.lesnumeriques.com/rss.xml"

        for source, url in FEEDS.items():
            if source in selected_sources:
                try:
                    feed = feedparser.parse(url)
                    for entry in feed.entries:
                        # For general EuroTech hubs, perform keyword filtering to keep it strictly relevant
                        if source == "EuroTech Hub" and target_string.lower() not in entry.title.lower():
                            continue
                            
                        dt = entry.get('published_parsed') or entry.get('updated_parsed')
                        author = entry.get('author', 'Independent Creator')
                        sentiment_label, sentiment_score = analyze_sentiment(entry.title)
                        entries.append({
                            "brand": brand_label, "source": source, "title": entry.title,
                            "author": author, "link": entry.link,
                            "time": datetime(*dt[:6]) if dt else datetime.now(),
                            "sentiment": sentiment_label, "score": sentiment_score, "language": lang_name
                        })
                except: pass 

        # Global iTunes Podcast API Access
        if "Podcasts" in selected_sources:
            try:
                lang_code = "de" if lang_name == "DE 🇩🇪" else "fr" if lang_name == "FR 🇫🇷" else "us"
                podcast_url = f"https://itunes.apple.com/search?term={encoded_query}&entity=podcastEpisode&country={lang_code}&limit=10"
                response = requests.get(podcast_url, timeout=5).json()
                for result in response.get('results', []):
                    entries.append({
                        "brand": brand_label, "source": "Podcasts",
                        "title": f"{result.get('collectionName', 'Podcast')} - {result.get('trackName', 'Episode')}",
                        "author": result.get('artistName', 'Host'),
                        "link": result.get('trackViewUrl', ''),
                        "time": datetime.strptime(result['releaseDate'], "%Y-%m-%dT%H:%M:%SZ"),
                        "sentiment": "⚪ Neutral", "score": 0.0, "language": lang_name
                    })
            except: pass

        # Global YouTube Engine
        if "YouTube" in selected_sources and YOUTUBE_API_KEY:
            try:
                youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
                request = youtube.search().list(q=target_string, part='snippet', type='video', order='date', relevanceLanguage=l_params['yt'], maxResults=12)
                response = request.execute()
                for item in response.get('items', []):
                    video_id = item['id'].get('videoId')
                    if video_id:
                        pub_time = datetime.strptime(item['snippet']['publishedAt'], "%Y-%m-%dT%H:%M:%SZ")
                        sentiment_label, sentiment_score = analyze_sentiment(item['snippet']['title'])
                        entries.append({
                            "brand": brand_label, "source": "YouTube", "title": item['snippet']['title'],
                            "author": item['snippet']['channelTitle'], "link": f"https://www.youtube.com/watch?v={video_id}",
                            "time": pub_time, "sentiment": sentiment_label, "score": sentiment_score, "language": lang_name
                        })
            except: pass
            
    return entries

# Process Multi-Stream Architecture
all_raw_mentions = fetch_target_data(active_query, active_query)

if competitor_input:
    comp_mentions = fetch_target_data(competitor_input.strip(), competitor_input.strip())
    all_raw_mentions.extend(comp_mentions)

unique_entries = {m['link']: m for m in all_raw_mentions}
all_raw_mentions = list(unique_entries.values())

if display_language != "All Languages 🌍":
    mentions = [m for m in all_raw_mentions if m['language'] == display_language]
else:
    mentions = all_raw_mentions

target_brand_mentions = [m for m in mentions if m['brand'] == active_query]

if sort_by == "Newest First": target_brand_mentions = sorted(target_brand_mentions, key=lambda x: x['time'], reverse=True)
elif sort_by == "Most Positive 🟢": target_brand_mentions = sorted(target_brand_mentions, key=lambda x: x['score'], reverse=True)
elif sort_by == "Most Negative 🔴": target_brand_mentions = sorted(target_brand_mentions, key=lambda x: x['score'])

# --- 4. MAIN DASHBOARD UI ---
st.title(f"🌍 Global Intelligence Hub: {active_query}")

st.markdown(f"""
<div style="display: flex; gap: 16px; margin-bottom: 24px;">
    <div class="modern-card metric-box" style="flex: 1; margin-bottom: 0;">
        <div class="metric-label">Active Monitoring Stream Volume</div>
        <div class="metric-value" style="color: #3b82f6;">{len(target_brand_mentions)} Mentions</div>
    </div>
    <div class="modern-card metric-box" style="flex: 1; margin-bottom: 0;">
        <div class="metric-label">Cross-Benchmark Volume ({competitor_input or 'None'})</div>
        <div class="metric-value" style="color: #ef4444;">{len([m for m in mentions if m['brand']==competitor_input]) if competitor_input else 0} Mentions</div>
    </div>
</div>
""", unsafe_allow_html=True)

# --- 🤖 RESTORED AI BRIEFING ENGINE ---
if target_brand_mentions:
    now = datetime.now()
    one_day_ago = now - pd.Timedelta(days=1)
    seven_days_ago = now - pd.Timedelta(days=7)
    
    daily_mentions = [m for m in target_brand_mentions if pd.to_datetime(m['time']).tz_localize(None) >= one_day_ago]
    weekly_mentions = [m for m in target_brand_mentions if pd.to_datetime(m['time']).tz_localize(None) >= seven_days_ago]
    
    ignore_words = {'reolink', 'camera', 'cameras', 'video', 'security', 'http', 'https', 'com', 'www', 'reddit', 'the', 'and', 'for', 'you', 'with', 'this', 'new', 'les', 'des', 'und', 'der', 'die', 'das', 'pour', 'sur', 'ist', 'von', 'est', 'une', 'omvi', 'onvif', 'magicam'}
    
    weekly_top_topic = "General Conversations"
    if weekly_mentions:
        w_words = []
        for m in weekly_mentions:
            words = [w.strip("?,.:;\"'()![]{}").lower() for w in m['title'].split()]
            w_words.extend([w for w in words if w not in ignore_words and len(w) > 3])
        w_counts = Counter(w_words).most_common(1)
        if w_counts: weekly_top_topic = w_counts[0][0].title()

    if daily_mentions:
        d_words = []
        for m in daily_mentions:
            words = [w.strip("?,.:;\"'()![]{}").lower() for w in m['title'].split()]
            d_words.extend([w for w in words if w not in ignore_words and len(w) > 3])
        d_counts = Counter(d_words).most_common(1)
        
        if d_counts:
            daily_top_topic = d_counts[0][0].title()
            related_mentions = [m for m in daily_mentions if daily_top_topic.lower() in m['title'].lower()]
            if not related_mentions: related_mentions = daily_mentions
            avg_score = sum(m['score'] for m in related_mentions) / len(related_mentions)
            overall_sentiment = "positive 🟢" if avg_score > 0.15 else "negative 🔴" if avg_score < -0.15 else "neutral ⚪"
            
            st.info(f"### 🧠 AI Daily Briefing\n"
                    f"**Today's Pulse:** Over the last 24 hours, chatter around **'{active_query}'** is heavily focused on the keyword topic **'{daily_top_topic}'** "
                    f"(trending **{overall_sentiment}**). The primary narrative driver right now is: *\"{related_mentions[0]['title']}\"*\n\n"
                    f"**Weekly Macro Context:** Across the entire last 7 days, the dominant trending topic remains anchored on **'{weekly_top_topic}'**.")
        else:
            st.info(f"### 🧠 AI Daily Briefing\nDiscussion trends are stable for '{active_query}' today without localized spikes. The broader 7-day macro trend remains focused on **'{weekly_top_topic}'**.")
    else:
         st.info(f"### 🧠 AI Daily Briefing\nNo breaking spikes captured in the last 24 hours for this keyword. The broader 7-day macro trend remains focused on **'{weekly_top_topic}'**.")

# --- SHARE OF VOICE TIMELINE ---
if mentions:
    st.markdown("### 📊 Timeline Share of Voice (Last 14 Days)")
    df = pd.DataFrame(mentions)
    df['time'] = pd.to_datetime(df['time']).dt.tz_localize(None)
    df = df[df['time'] >= (datetime.now() - pd.Timedelta(days=14))]
    
    if not df.empty:
        df['Date'] = df['time'].dt.date
        chart_data = df.groupby(['Date', 'brand']).size().reset_index(name='Mentions')
        
        base = alt.Chart(chart_data).encode(
            x=alt.X('Date:T', title=''),
            y=alt.Y('Mentions:Q', title='Volume'),
            color=alt.Color('brand:N', scale=alt.Scale(range=['#3b82f6', '#ef4444']), legend=alt.Legend(title="Keyword Streams"))
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
                
        st.altair_chart(chart.properties(height=300), use_container_width=True)

st.divider()

# --- THE STREAMS FEED ---
if target_brand_mentions:
    st.markdown(f"### 📰 Stream Monitor ({len(target_brand_mentions)} Entries Match)")
    items_per_page = 10
    total_pages = max(1, (len(target_brand_mentions) + items_per_page - 1) // items_per_page)
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
    
    for item in target_brand_mentions[start_idx:start_idx + items_per_page]:
        formatted_age = format_time_ago(item['time'])
        st.markdown(f"""
        <div class="modern-card">
            <h3 class="card-title">{PLATFORM_ICONS.get(item['source'], "📌")} {item['title']}</h3>
            <span class="card-sentiment">{item['sentiment']}</span>
            <div class="card-bottom">
                <span>👤 <strong>{item['author']}</strong> • 📅 {formatted_age} • via {item['source']} • {item['language']}</span>
                <a href="{item['link']}" target="_blank" class="card-link">Open Link ↗</a>
            </div>
        </div>
        """, unsafe_allow_html=True)
else:
    st.info(f"No recent data streams captured for key: '{active_query}'. Adjust parameters or force sync.")

if auto_refresh:
    time.sleep(refresh_interval)
    st.rerun()