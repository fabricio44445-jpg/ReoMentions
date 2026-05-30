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

# --- AUTO-DOWNLOAD REQUIRED AI COMPONENTS ---
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt', quiet=True)

# --- THE "FAKE ID" FOR GOOGLE/BING/YAHOO ---
feedparser.USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# --- API CREDENTIALS ---
YOUTUBE_API_KEY = "AIzaSyCB26TbgxGyRiWCwO0H_ptUQsH8tM0SpGQ"

# --- UI ASSETS ---
PLATFORM_ICONS = {
    "Reddit": "🟧",
    "Google News": "📰",
    "Bing News": "🌐",
    "YouTube": "🟥",
    "Yahoo News": "🟣",
    "Hacker News": "👾",
    "Medium": "📝",
    "Flickr": "📷"
}

# --- 1. PAGE SETUP & MEMORY ---
st.set_page_config(page_title="Reolink Command Center", page_icon="📹", layout="wide", initial_sidebar_state="expanded")

# Modern HTML/CSS Injection
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; }

    .modern-card {
        background-color: #ffffff;
        border-radius: 12px;
        padding: 20px 24px;
        margin-bottom: 16px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        border: 1px solid #f1f5f9;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .modern-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
    }
    @media (prefers-color-scheme: dark) {
        .modern-card { background-color: #1e293b; border: 1px solid #334155; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3); }
    }
    .card-title { font-size: 1.15rem; font-weight: 600; margin-bottom: 8px; margin-top: 0; line-height: 1.4; }
    .card-sentiment { font-size: 0.85rem; font-weight: 600; margin-bottom: 12px; display: inline-block; padding: 2px 8px; border-radius: 12px; background: rgba(0,0,0,0.05); }
    .card-bottom { display: flex; justify-content: space-between; align-items: center; font-size: 0.85rem; color: #64748b; font-weight: 500; }
    .card-link { text-decoration: none; color: #3b82f6; font-weight: 600; background-color: rgba(59, 130, 246, 0.1); padding: 6px 12px; border-radius: 6px; transition: background-color 0.2s; }
    .card-link:hover { background-color: rgba(59, 130, 246, 0.2); }
    .metric-box { display: flex; flex-direction: column; justify-content: center; }
    .metric-label { font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; font-weight: 600; margin-bottom: 4px; }
    .metric-value { font-size: 2rem; font-weight: 700; }
</style>
""", unsafe_allow_html=True)

# State Management
if "focus_areas" not in st.session_state:
    st.session_state.focus_areas = ["All Reolink"]
if "last_top_mention" not in st.session_state:
    st.session_state.last_top_mention = None
if "current_page" not in st.session_state:
    st.session_state.current_page = 1

# --- 2. SIDEBAR CONTROLS ---
with st.sidebar:
    st.title("⚙️ Control Panel")
    
    st.subheader("🎯 Quick Filters")
    active_filter = st.radio("Select Focus Area:", st.session_state.focus_areas, label_visibility="collapsed")
    
    with st.expander("➕ Add New Focus Area"):
        new_area = st.text_input("Enter name:")
        if st.button("Add to List", use_container_width=True):
            if new_area and new_area not in st.session_state.focus_areas:
                st.session_state.focus_areas.append(new_area)
                st.rerun()

    with st.expander("➖ Remove Focus Area"):
        removable_areas = [area for area in st.session_state.focus_areas if area != "All Reolink"]
        if not removable_areas:
            st.info("No custom areas to remove.")
        else:
            area_to_remove = st.selectbox("Select area to delete:", removable_areas)
            if st.button("Remove from List", use_container_width=True):
                st.session_state.focus_areas.remove(area_to_remove)
                st.rerun()
    
    st.divider()

    st.subheader("🌍 Language Filter")
    display_language = st.selectbox(
        "Filter Dashboard By:",
        ["All Languages 🌍", "EN 🇺🇸", "FR 🇫🇷", "DE 🇩🇪"]
    )

    st.divider()

    st.subheader("🧠 Analytics")
    sort_by = st.selectbox(
        "Sort Mentions By:",
        ["Newest First", "Most Positive 🟢", "Most Negative 🔴"]
    )

    st.divider()

    st.subheader("📡 Sources")
    selected_sources = st.multiselect(
        "Show mentions from:",
        ["Reddit", "Google News", "Bing News", "Yahoo News", "Hacker News", "Medium", "Flickr", "YouTube"],
        default=["Reddit", "Google News", "Bing News", "Yahoo News", "Hacker News", "Medium", "Flickr"] 
    )

    st.divider()
    
    st.subheader("⏱️ Sync Settings")
    auto_refresh = st.toggle("Enable Auto-Refresh", value=True)
    refresh_interval = st.slider("Refresh Interval (seconds)", min_value=900, max_value=7200, value=3600)
    
    if st.button("🔄 Force Refresh Now", use_container_width=True):
        st.session_state.current_page = 1
        st.rerun()

# --- 3. DYNAMIC SEARCH & AI LOGIC ---
query = "Reolink"
if active_filter != "All Reolink":
    query = f"Reolink {active_filter}"

encoded_query = urllib.parse.quote(query)

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

def fetch_mentions():
    all_entries = []
    
    for lang_name, l_params in lang_configs.items():
        FEEDS = {
            "Google News": f"https://news.google.com/rss/search?q={encoded_query}&{l_params['gnews']}",
            "Bing News": f"https://www.bing.com/news/search?q={encoded_query}&format=rss&{l_params['bing']}",
            "Yahoo News": f"https://{l_params['yahoo']}/rss?p={encoded_query}"
        }
        
        if lang_name == "EN 🇺🇸":
            FEEDS["Reddit"] = f"https://www.reddit.com/search.rss?q={encoded_query}&sort=new"
            FEEDS["Hacker News"] = f"https://hnrss.org/newest?q={encoded_query}"
            
            query_no_space = query.replace(' ', '')
            FEEDS["Medium"] = f"https://medium.com/feed/tag/{query_no_space}"
            FEEDS["Flickr"] = f"https://www.flickr.com/services/feeds/photos_public.gne?tags={query_no_space}&format=rss_200"

        for source, url in FEEDS.items():
            if source in selected_sources:
                try:
                    feed = feedparser.parse(url)
                    for entry in feed.entries:
                        dt = entry.get('published_parsed') or entry.get('updated_parsed')
                        title = entry.title
                        sentiment_label, sentiment_score = analyze_sentiment(title)
                        all_entries.append({
                            "source": source,
                            "title": title,
                            "link": entry.link,
                            "time": datetime(*dt[:6]) if dt else datetime.now(),
                            "sentiment": sentiment_label,
                            "score": sentiment_score,
                            "language": lang_name
                        })
                except: pass 

        if "YouTube" in selected_sources and YOUTUBE_API_KEY:
            try:
                youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
                request = youtube.search().list(
                    q=query, 
                    part='snippet', 
                    type='video', 
                    order='date', 
                    relevanceLanguage=l_params['yt'],
                    maxResults=15
                )
                response = request.execute()
                
                for item in response.get('items', []):
                    video_id = item['id'].get('videoId')
                    if video_id:
                        published_at = item['snippet']['publishedAt']
                        video_time = datetime.strptime(published_at, "%Y-%m-%dT%H:%M:%SZ")
                        title = item['snippet']['title']
                        sentiment_label, sentiment_score = analyze_sentiment(title)
                        
                        all_entries.append({
                            "source": "YouTube",
                            "title": title,
                            "link": f"https://www.youtube.com/watch?v={video_id}",
                            "time": video_time,
                            "sentiment": sentiment_label,
                            "score": sentiment_score,
                            "language": lang_name
                        })
            except Exception as e:
                if "quota" in str(e).lower() or "429" in str(e):
                    st.sidebar.warning("⚠️ YouTube Daily Limit Reached. Will reset at midnight.")
                else:
                    pass
                
    unique_entries = {}
    for entry in all_entries:
        if entry['link'] not in unique_entries:
            unique_entries[entry['link']] = entry
            
    return list(unique_entries.values())

# --- 4. MAIN DASHBOARD UI ---
st.title(f"📡 Live Intelligence: {active_filter}")

all_raw_mentions = fetch_mentions()

if display_language != "All Languages 🌍":
    raw_mentions = [m for m in all_raw_mentions if m['language'] == display_language]
else:
    raw_mentions = all_raw_mentions

if sort_by == "Newest First":
    mentions = sorted(raw_mentions, key=lambda x: x['time'], reverse=True)
elif sort_by == "Most Positive 🟢":
    mentions = sorted(raw_mentions, key=lambda x: x['score'], reverse=True)
elif sort_by == "Most Negative 🔴":
    mentions = sorted(raw_mentions, key=lambda x: x['score'])

if mentions and sort_by == "Newest First":
    current_top_link = mentions[0]['link']
    if st.session_state.last_top_mention and st.session_state.last_top_mention != current_top_link:
        st.markdown('<audio autoplay="true" src="https://upload.wikimedia.org/wikipedia/commons/3/34/Sound_Effect_-_Ping_Sound.ogg"></audio>', unsafe_allow_html=True)
    st.session_state.last_top_mention = current_top_link

coverage_display = "🇺🇸 🇫🇷 🇩🇪" if display_language == "All Languages 🌍" else display_language
metrics_html = f"""
<div style="display: flex; gap: 16px; margin-bottom: 24px;">
    <div class="modern-card metric-box" style="flex: 1; margin-bottom: 0;">
        <div class="metric-label">Current Focus</div>
        <div class="metric-value" style="color: #3b82f6;">{active_filter}</div>
    </div>
    <div class="modern-card metric-box" style="flex: 1; margin-bottom: 0;">
        <div class="metric-label">Mentions Scraped</div>
        <div class="metric-value" style="color: #10b981;">{len(mentions)}</div>
    </div>
    <div class="modern-card metric-box" style="flex: 1; margin-bottom: 0;">
        <div class="metric-label">Active View</div>
        <div class="metric-value" style="color: #8b5cf6; font-size: 1.5rem; padding-top: 6px;">{coverage_display}</div>
    </div>
</div>
"""
st.markdown(metrics_html, unsafe_allow_html=True)

if mentions:
    st.markdown("### 📈 14-Day Mention Volume")
    df = pd.DataFrame(mentions)
    df['time'] = pd.to_datetime(df['time']).dt.tz_localize(None)
    
    fourteen_days_ago = datetime.now() - pd.Timedelta(days=14)
    df = df[df['time'] >= fourteen_days_ago]
    
    if not df.empty:
        df['Date'] = df['time'].dt.date
        chart_data = df.groupby('Date').size().reset_index(name='Mentions')
        chart_data = chart_data.sort_values('Date')
        
        chart_data['Timeline'] = pd.to_datetime(chart_data['Date']).dt.strftime('%b %d')
        
        st.vega_lite_chart(chart_data, {
            'mark': {
                'type': 'line', 
                'interpolate': 'monotone', 
                'point': {'filled': True, 'fill': 'white', 'stroke': '#3b82f6', 'strokeWidth': 2, 'size': 60},
                'color': '#3b82f6',
                'strokeWidth': 3
            },
            'encoding': {
                'x': {
                    'field': 'Timeline', 
                    'type': 'ordinal', 
                    'sort': None, 
                    'axis': {'labelAngle': -45, 'title': '', 'grid': False}
                },
                'y': {
                    'field': 'Mentions', 
                    'type': 'quantitative',
                    'axis': {'title': 'Total Mentions', 'grid': True}
                }
            },
            'width': 'container',
            'height': 300,
            'selection': {} 
        }, use_container_width=True)
    else:
        st.write("No data found in the last 14 days for this region.")
        
# --- 🤖 AI TREND SUMMARY (DAILY + WEEKLY CONTEXT) ---
if mentions:
    now = datetime.now()
    one_day_ago = now - pd.Timedelta(days=1)
    seven_days_ago = now - pd.Timedelta(days=7)
    
    daily_mentions = [m for m in mentions if pd.to_datetime(m['time']).tz_localize(None) >= one_day_ago]
    weekly_mentions = [m for m in mentions if pd.to_datetime(m['time']).tz_localize(None) >= seven_days_ago]
    
    ignore_words = {'reolink', 'camera', 'cameras', 'video', 'security', 'http', 'https', 'com', 'www', 'reddit', 'the', 'and', 'for', 'you', 'with', 'this', 'new', 'les', 'des', 'und', 'der', 'die', 'das', 'pour', 'sur', 'ist', 'von', 'est', 'une'}
    
    # 1. Calculate Weekly Macro Trend
    weekly_top_topic = "General Security"
    if weekly_mentions:
        w_words = []
        for m in weekly_mentions:
            words = [w.strip("?,.:;\"'()![]{}").lower() for w in m['title'].split()]
            w_words.extend([w for w in words if w not in ignore_words and len(w) > 3])
        w_counts = Counter(w_words).most_common(1)
        if w_counts:
            weekly_top_topic = w_counts[0][0].title()

    # 2. Calculate Daily Pulse
    if daily_mentions:
        d_words = []
        for m in daily_mentions:
            words = [w.strip("?,.:;\"'()![]{}").lower() for w in m['title'].split()]
            d_words.extend([w for w in words if w not in ignore_words and len(w) > 3])
            
        d_counts = Counter(d_words).most_common(1)
        
        if d_counts:
            daily_top_topic = d_counts[0][0].title()
            related_mentions = [m for m in daily_mentions if daily_top_topic.lower() in m['title'].lower()]
            
            if not related_mentions:
                related_mentions = daily_mentions
                
            avg_score = sum(m['score'] for m in related_mentions) / len(related_mentions)
            overall_sentiment = "positive 🟢" if avg_score > 0.15 else "negative 🔴" if avg_score < -0.15 else "neutral ⚪"
            
            st.info(f"### 🧠 AI Daily Briefing\n"
                    f"**Today's Pulse:** Over the last 24 hours, discussion is heavily indexing toward **'{daily_top_topic}'** "
                    f"(leaning **{overall_sentiment}**). The top driving headline right now is: *\"{related_mentions[0]['title']}\"*\n\n"
                    f"**Weekly Macro Trend:** For context, the broader, overarching topic across the last 7 days remains focused on **'{weekly_top_topic}'**.")
        else:
            st.info(f"### 🧠 AI Daily Briefing\nDiscussion volumes are stable today without singular localized breakouts. The broader weekly trend remains focused on **'{weekly_top_topic}'**.")
    else:
         st.info(f"### 🧠 AI Daily Briefing\nNo major spikes in the last 24 hours. The broader weekly trend remains focused on **'{weekly_top_topic}'**.")

# --- NEW PAGINATION LOGIC (NUMBERED BUTTONS) ---
if mentions:
    st.markdown("### 📰 Live Feed")
    
    items_per_page = 10
    total_pages = max(1, (len(mentions) + items_per_page - 1) // items_per_page)
    
    if st.session_state.current_page > total_pages:
        st.session_state.current_page = 1
        
    max_visible_pages = 7
    start_page = max(1, st.session_state.current_page - max_visible_pages // 2)
    end_page = min(total_pages, start_page + max_visible_pages - 1)
    
    if end_page - start_page + 1 < max_visible_pages:
        start_page = max(1, end_page - max_visible_pages + 1)
        
    page_numbers = list(range(start_page, end_page + 1))
    
    cols = st.columns([1.5] + [1]*len(page_numbers) + [1.5])
    
    with cols[0]:
        if st.button("⬅️ Previous", disabled=(st.session_state.current_page == 1), use_container_width=True):
            st.session_state.current_page -= 1
            st.rerun()
            
    for i, page_num in enumerate(page_numbers):
        with cols[i + 1]:
            button_type = "primary" if page_num == st.session_state.current_page else "secondary"
            if st.button(str(page_num), key=f"btn_page_{page_num}", type=button_type, use_container_width=True):
                st.session_state.current_page = page_num
                st.rerun()
                
    with cols[-1]:
        if st.button("Next ➡️", disabled=(st.session_state.current_page == total_pages), use_container_width=True):
            st.session_state.current_page += 1
            st.rerun()
            
    start_idx = (st.session_state.current_page - 1) * items_per_page
    end_idx = start_idx + items_per_page
    
    for item in mentions[start_idx:end_idx]:
        time_diff = datetime.now() - item['time']
        minutes_ago = int(max(0, time_diff.total_seconds() / 60))
        icon = PLATFORM_ICONS.get(item['source'], "📌")
        
        card_html = f"""
        <div class="modern-card">
            <h3 class="card-title">{icon} {item['title']}</h3>
            <span class="card-sentiment">{item['sentiment']}</span>
            <div class="card-bottom">
                <span>📅 {item['time'].strftime('%b %d, %Y - %I:%M %p')} ({minutes_ago}m ago) • via <strong>{item['source']}</strong> • {item['language']}</span>
                <a href="{item['link']}" target="_blank" class="card-link">Open Link ↗</a>
            </div>
        </div>
        """
        st.markdown(card_html, unsafe_allow_html=True)
else:
    st.info(f"No recent mentions found for '{query}' in this region. Waiting for updates...")

if auto_refresh:
    time.sleep(refresh_interval)
    st.rerun()