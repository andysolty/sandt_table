"""
sandt_table.py — Sue and Andy's Table
A personal meal planner built for two, with room for company.

Features:
  • Weekly meal planner (Mon–Sun home / Fri–Fri cottage)
  • Automatic cottage mode for known cottage weeks
  • Freezer inventory across three freezers
  • Personal recipe library — clean, no ads
  • Claude-powered recipe extraction from images/screenshots
  • Auto-generated shopping list by store
  • Wine pairing suggestions
  • Shared read/write for Sue and Andy

Run:  streamlit run sandt_table.py

Secrets required (.streamlit/secrets.toml):
  ANTHROPIC_API_KEY = "..."   # for recipe extraction from images

  [gcp_service_account]
  type = "service_account"
  ... (same service account as lean_oracle)
"""

import streamlit as st
import pandas as pd
import gspread
import pytz
import base64
import requests
import json
from datetime import datetime, date, timedelta
from google.oauth2.service_account import Credentials as SACredentials

# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

EASTERN       = pytz.timezone("US/Eastern")
SHEET_ID      = "1fWKc0DmaaTPWOJQ2Jp3yP5KaCoqrjOjrHAA7RaZNfGo"
ANTHROPIC_KEY = st.secrets.get("ANTHROPIC_API_KEY", "")

_SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

# Known cottage weeks (Friday to Friday)
COTTAGE_WEEKS = [
    (date(2026, 5, 8),  date(2026, 5, 22)),
    (date(2026, 9, 4),  date(2026, 9, 11)),
    (date(2026, 9, 18), date(2026, 9, 25)),
]

FREEZERS = ["Kitchen (Side-by-Side)", "Basement Fridge (Top)", "Basement Standup"]

STORES = ["Farm Boy", "Monastery Bakery", "Sobeys", "No Frills", "Costco", "St. Lawrence Market", "Other"]

MEAL_TAGS = [
    "Italian", "Mediterranean", "BBQ", "Freezer-Friendly",
    "Company-Worthy", "Quick Weeknight", "Special Friday",
    "Cottage", "Chicken", "Pork", "Beef", "Fish", "Vegetarian",
    "Soup/Stew", "Pasta", "Salad", "Batch Cook"
]

WINE_PAIRINGS = {
    "Italian":       "Chianti, Barolo, or a bold Sangiovese",
    "Mediterranean": "Côtes du Rhône, Grenache, or a crisp Pinot Grigio",
    "BBQ":           "Zinfandel, Malbec, or a smoky Shiraz",
    "Fish":          "Sauvignon Blanc, Pinot Grigio, or a light Pinot Noir",
    "Chicken":       "Chardonnay, Pinot Noir, or a light Côtes du Rhône",
    "Pork":          "Pinot Noir, Grenache, or an off-dry Riesling",
    "Beef":          "Cabernet Sauvignon, Malbec, or a bold Barolo",
    "Pasta":         "Chianti, Barbera d'Asti, or Montepulciano",
    "Vegetarian":    "Sauvignon Blanc, Vermentino, or a light Pinot Noir",
    "Soup/Stew":     "Côtes du Rhône, Grenache, or a full-bodied red",
}

# ── Starter recipes ───────────────────────────────────────────────────────────
STARTER_RECIPES = [
    {
        "name":        "Hot Italian Sausage Pasta",
        "description": "A Solty family favourite — rich, hearty, and freezer-friendly.",
        "tags":        "Italian,Pasta,Freezer-Friendly,Batch Cook",
        "serves":      4,
        "prep_time":   "15 min",
        "cook_time":   "35 min",
        "ingredients": """500g hot Italian sausage (casings removed)
400g rigatoni or penne
1 can (796ml) crushed San Marzano tomatoes
1 can (156ml) tomato paste
1 medium onion, diced
4 cloves garlic, minced
1 red bell pepper, diced
1 tsp fennel seeds
1 tsp dried oregano
1 tsp chili flakes (adjust to taste)
½ cup dry red wine
Salt and pepper to taste
Fresh basil and Parmigiano-Reggiano to serve
Olive oil""",
        "steps":       """1. Heat olive oil in a large heavy pot over medium-high. Brown the sausage meat, breaking it up as it cooks. Remove and set aside.
2. In the same pot, sauté onion and bell pepper until softened, about 5 minutes. Add garlic, fennel seeds, and chili flakes — cook 1 minute more.
3. Deglaze with red wine, scraping up any browned bits. Let reduce by half.
4. Add crushed tomatoes, tomato paste, and oregano. Return sausage to pot. Stir well, reduce heat, and simmer uncovered for 20–25 minutes until sauce thickens.
5. Meanwhile, cook pasta in well-salted boiling water to al dente. Reserve 1 cup pasta water before draining.
6. Toss pasta into sauce, adding pasta water as needed to loosen. Season to taste.
7. Serve with fresh basil and generous Parmigiano. Freezes beautifully in portions.""",
        "wine":        "Chianti Classico, Barbera d'Asti, or Montepulciano d'Abruzzo",
        "notes":       "Double the batch for the freezer — it improves after a day. Reheat gently with a splash of water.",
        "added_by":    "Andy",
    },
    {
        "name":        "Lemon Maple Salmon",
        "description": "Simple, elegant, and on the table in 20 minutes.",
        "tags":        "Fish,Quick Weeknight,Mediterranean",
        "serves":      2,
        "prep_time":   "5 min",
        "cook_time":   "15 min",
        "ingredients": """2 salmon fillets (150–200g each)
2 tbsp pure maple syrup
2 tbsp fresh lemon juice
1 tsp lemon zest
1 clove garlic, minced
1 tbsp Dijon mustard
Salt, pepper, and fresh dill to finish
Olive oil""",
        "steps":       """1. Preheat oven to 400°F (or fire up the BBQ to medium-high).
2. Whisk together maple syrup, lemon juice, zest, garlic, and Dijon. Season with salt and pepper.
3. Place salmon skin-side down on a lined baking sheet (or oiled grill). Spoon glaze generously over top.
4. Oven: bake 12–15 minutes until salmon flakes easily. BBQ: cook 4–5 min per side with lid closed, basting once.
5. Finish with fresh dill and a wedge of lemon. Serve immediately.""",
        "wine":        "Sauvignon Blanc, Pinot Grigio, or a light unoaked Chardonnay",
        "notes":       "Sue's preference: a touch more maple. Andy's: a touch more lemon. Make both happy and split the difference.",
        "added_by":    "Andy",
    },
    {
        "name":        "Andy's Greek Salad",
        "description": "A mean Greek salad — the real deal, no lettuce required.",
        "tags":        "Mediterranean,Salad,Vegetarian,Quick Weeknight",
        "serves":      2,
        "prep_time":   "15 min",
        "cook_time":   "0 min",
        "ingredients": """3 ripe tomatoes, cut in wedges
1 English cucumber, chunked (not sliced thin)
½ red onion, thinly sliced
1 green bell pepper, roughly chopped
200g authentic Greek feta (block, not crumbled)
½ cup Kalamata olives
1 tsp dried Greek oregano
Good quality extra virgin olive oil (generous)
Red wine vinegar
Salt and cracked black pepper""",
        "steps":       """1. Combine tomatoes, cucumber, onion, and pepper in a wide shallow bowl. Season with salt and let sit 5 minutes.
2. Add olives. Drizzle generously with olive oil and a splash of red wine vinegar. Toss gently.
3. Lay the feta block on top whole (don't crumble it — this is the Greek way). Drizzle with a little more oil.
4. Finish with a heavy pinch of dried oregano crumbled between your fingers, and cracked black pepper.
5. Serve immediately with crusty bread to mop up the juices.""",
        "wine":        "Assyrtiko from Santorini if you can find it, otherwise any crisp Sauvignon Blanc",
        "notes":       "The key is good feta and good olive oil. Don't skip the resting step — it draws out the tomato juices which become part of the dressing.",
        "added_by":    "Andy",
    },
    {
        "name":        "Pork Schnitzel",
        "description": "Crispy, golden, satisfying — a weeknight workhorse.",
        "tags":        "Pork,Quick Weeknight",
        "serves":      2,
        "prep_time":   "20 min",
        "cook_time":   "12 min",
        "ingredients": """2 pork loin chops (boneless, ~150g each)
½ cup all-purpose flour
2 eggs, beaten
1 cup fine dry breadcrumbs (panko works well)
½ tsp garlic powder
½ tsp paprika
Salt and pepper
Vegetable oil or clarified butter for frying
Lemon wedges to serve
Fresh parsley""",
        "steps":       """1. Place pork between plastic wrap and pound to about 5mm thickness with a meat mallet or rolling pin.
2. Season flour with salt, pepper, garlic powder, and paprika. Set up a breading station: flour → egg → breadcrumbs.
3. Dredge each schnitzel in flour (shake off excess), dip in egg, then press firmly into breadcrumbs. Set on a rack.
4. Heat ½ inch of oil in a wide skillet over medium-high until shimmering. Fry schnitzel 3–4 minutes per side until deep golden and cooked through.
5. Drain briefly on paper towel. Serve immediately with lemon wedges, parsley, and a simple potato salad or green salad.""",
        "wine":        "Pinot Noir, Grüner Veltliner, or a cold Austrian lager",
        "notes":       "Don't crowd the pan — fry one at a time if needed. The crust should bubble and float slightly for maximum crispiness.",
        "added_by":    "Andy",
    },
]

# ══════════════════════════════════════════════════════════════════════════════
# GOOGLE SHEETS AUTH
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_resource(show_spinner=False)
def _get_gc() -> gspread.Client:
    raw = dict(st.secrets["gcp_service_account"])
    raw.setdefault("type", "service_account")
    creds = SACredentials.from_service_account_info(raw, scopes=_SCOPES)
    return gspread.authorize(creds)


@st.cache_resource(show_spinner=False)
def _get_sheet() -> gspread.Spreadsheet:
    return _get_gc().open_by_key(SHEET_ID)


def _get_or_create_ws(title: str, rows: int = 500, cols: int = 20) -> gspread.Worksheet:
    sh = _get_sheet()
    try:
        return sh.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows=rows, cols=cols)
        return ws


def _now_et() -> str:
    return datetime.now(EASTERN).isoformat()


# ══════════════════════════════════════════════════════════════════════════════
# WORKSHEET INITIALISATION
# ══════════════════════════════════════════════════════════════════════════════

def _init_worksheets():
    """Create all required worksheets with headers if they don't exist."""
    sheets = {
        "MealPlan":   ["Week", "Day", "Date", "Meal_Type", "Recipe_Name", "Notes", "Added_By"],
        "Recipes":    ["ID", "Name", "Description", "Tags", "Serves", "Prep_Time",
                       "Cook_Time", "Ingredients", "Steps", "Wine", "Notes", "Added_By", "Timestamp"],
        "Freezer":    ["ID", "Name", "Quantity", "Unit", "Freezer", "Date_Added",
                       "Use_By", "Notes", "Added_By"],
        "ShoppingList": ["Week", "Item", "Quantity", "Unit", "Store", "Category",
                         "Checked", "Added_By", "Timestamp"],
    }
    for title, header in sheets.items():
        ws = _get_or_create_ws(title)
        if not ws.get_all_values():
            ws.append_row(header)

    # Seed starter recipes if Recipes tab is empty (header only)
    ws_recipes = _get_sheet().worksheet("Recipes")
    existing = ws_recipes.get_all_values()
    if len(existing) <= 1:
        _seed_starter_recipes(ws_recipes)


def _seed_starter_recipes(ws: gspread.Worksheet):
    for i, r in enumerate(STARTER_RECIPES, start=1):
        ws.append_row([
            str(i),
            r["name"], r["description"], r["tags"],
            r["serves"], r["prep_time"], r["cook_time"],
            r["ingredients"], r["steps"], r["wine"],
            r["notes"], r["added_by"], _now_et(),
        ])


# ══════════════════════════════════════════════════════════════════════════════
# DATA LOADERS
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=30, show_spinner=False)
def load_recipes() -> pd.DataFrame:
    try:
        ws  = _get_sheet().worksheet("Recipes")
        rec = ws.get_all_records()
        return pd.DataFrame(rec) if rec else pd.DataFrame(
            columns=["ID","Name","Description","Tags","Serves","Prep_Time",
                     "Cook_Time","Ingredients","Steps","Wine","Notes","Added_By","Timestamp"])
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=30, show_spinner=False)
def load_meal_plan() -> pd.DataFrame:
    try:
        ws  = _get_sheet().worksheet("MealPlan")
        rec = ws.get_all_records()
        return pd.DataFrame(rec) if rec else pd.DataFrame(
            columns=["Week","Day","Date","Meal_Type","Recipe_Name","Notes","Added_By"])
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=30, show_spinner=False)
def load_freezer() -> pd.DataFrame:
    try:
        ws  = _get_sheet().worksheet("Freezer")
        rec = ws.get_all_records()
        return pd.DataFrame(rec) if rec else pd.DataFrame(
            columns=["ID","Name","Quantity","Unit","Freezer",
                     "Date_Added","Use_By","Notes","Added_By"])
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=30, show_spinner=False)
def load_shopping_list() -> pd.DataFrame:
    try:
        ws  = _get_sheet().worksheet("ShoppingList")
        rec = ws.get_all_records()
        return pd.DataFrame(rec) if rec else pd.DataFrame(
            columns=["Week","Item","Quantity","Unit","Store",
                     "Category","Checked","Added_By","Timestamp"])
    except Exception:
        return pd.DataFrame()


# ══════════════════════════════════════════════════════════════════════════════
# DATA WRITERS
# ══════════════════════════════════════════════════════════════════════════════

def save_meal(week: str, day: str, date_str: str, meal_type: str,
              recipe_name: str, notes: str, added_by: str):
    ws = _get_sheet().worksheet("MealPlan")
    ws.append_row([week, day, date_str, meal_type, recipe_name, notes, added_by])
    load_meal_plan.clear()


def save_recipe(name, desc, tags, serves, prep, cook, ingredients, steps, wine, notes, added_by):
    ws  = _get_sheet().worksheet("Recipes")
    all_rows = ws.get_all_values()
    new_id = len(all_rows)  # header + existing rows
    ws.append_row([str(new_id), name, desc, tags, serves, prep, cook,
                   ingredients, steps, wine, notes, added_by, _now_et()])
    load_recipes.clear()


def save_freezer_item(name, qty, unit, freezer, use_by, notes, added_by):
    ws  = _get_sheet().worksheet("Freezer")
    all_rows = ws.get_all_values()
    new_id = len(all_rows)
    ws.append_row([str(new_id), name, qty, unit, freezer,
                   _now_et()[:10], use_by, notes, added_by])
    load_freezer.clear()


def remove_freezer_item(item_id: str):
    ws   = _get_sheet().worksheet("Freezer")
    data = ws.get_all_values()
    for i, row in enumerate(data):
        if row and str(row[0]) == str(item_id):
            ws.delete_rows(i + 1)
            break
    load_freezer.clear()


def save_shopping_item(week, item, qty, unit, store, category, added_by):
    ws = _get_sheet().worksheet("ShoppingList")
    ws.append_row([week, item, qty, unit, store, category, "No", added_by, _now_et()])
    load_shopping_list.clear()


def toggle_shopping_item(row_idx: int, current_val: str):
    ws      = _get_sheet().worksheet("ShoppingList")
    new_val = "Yes" if current_val == "No" else "No"
    ws.update_cell(row_idx + 2, 7, new_val)   # col 7 = Checked, +2 for header + 0-index
    load_shopping_list.clear()


# ══════════════════════════════════════════════════════════════════════════════
# COTTAGE MODE DETECTION
# ══════════════════════════════════════════════════════════════════════════════

def get_current_week_info() -> dict:
    today = date.today()

    for start, end in COTTAGE_WEEKS:
        if start <= today <= end:
            # Find the Friday on or before today
            days_since_friday = (today.weekday() - 4) % 7
            week_start = today - timedelta(days=days_since_friday)
            week_end   = week_start + timedelta(days=6)
            return {
                "mode":       "cottage",
                "week_start": week_start,
                "week_end":   min(week_end, end),
                "week_label": f"Cottage Week — {week_start.strftime('%b %d')} to {week_end.strftime('%b %d, %Y')}",
                "days":       ["Friday","Saturday","Sunday","Monday","Tuesday","Wednesday","Thursday"],
            }

    # Home week: Monday to Sunday
    days_since_monday = today.weekday()
    week_start = today - timedelta(days=days_since_monday)
    week_end   = week_start + timedelta(days=6)
    return {
        "mode":       "home",
        "week_start": week_start,
        "week_end":   week_end,
        "week_label": f"Week of {week_start.strftime('%B %d, %Y')}",
        "days":       ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"],
    }


def week_key(week_info: dict) -> str:
    return week_info["week_start"].strftime("%Y-%m-%d")


# ══════════════════════════════════════════════════════════════════════════════
# CLAUDE RECIPE EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════

def extract_recipe_from_image(image_bytes: bytes, media_type: str) -> dict | None:
    if not ANTHROPIC_KEY:
        st.error("ANTHROPIC_API_KEY not set in secrets.")
        return None

    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1500,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": b64}
                },
                {
                    "type": "text",
                    "text": (
                        "Extract the recipe from this image. "
                        "Return ONLY a JSON object with these exact keys: "
                        "name, description, ingredients, steps, serves, prep_time, cook_time, notes. "
                        "ingredients should be a newline-separated string. "
                        "steps should be a newline-separated string of numbered steps. "
                        "No markdown, no backticks, just raw JSON."
                    )
                }
            ]
        }]
    }

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key":         ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json",
            },
            json=payload,
            timeout=30,
        )
        text = resp.json()["content"][0]["text"]
        return json.loads(text)
    except Exception as e:
        st.error(f"Recipe extraction failed: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# UI HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _day_emoji(day: str) -> str:
    return {
        "Monday": "🌙", "Tuesday": "🌙", "Wednesday": "🌙",
        "Thursday": "🌙", "Friday": "✨", "Saturday": "🍽️", "Sunday": "☀️",
    }.get(day, "📅")


def _tag_colour(tag: str) -> str:
    colours = {
        "Italian":        "#c0392b", "Mediterranean": "#2980b9",
        "BBQ":            "#e67e22", "Freezer-Friendly": "#27ae60",
        "Company-Worthy": "#8e44ad", "Quick Weeknight": "#16a085",
        "Special Friday": "#f39c12", "Cottage":        "#1abc9c",
        "Chicken":        "#d4ac0d", "Pork":           "#cb4335",
        "Beef":           "#922b21", "Fish":           "#1a5276",
        "Vegetarian":     "#1e8449", "Pasta":          "#d35400",
        "Salad":          "#117a65", "Batch Cook":     "#6c3483",
        "Soup/Stew":      "#784212",
    }
    return colours.get(tag, "#555")


def _render_tag(tag: str):
    colour = _tag_colour(tag)
    st.markdown(
        f"<span style='background:{colour};color:white;padding:2px 8px;"
        f"border-radius:12px;font-size:0.72rem;margin:2px;display:inline-block'>"
        f"{tag}</span>",
        unsafe_allow_html=True,
    )


def _recipe_card(row: pd.Series, show_full: bool = False):
    tags = [t.strip() for t in str(row.get("Tags","")).split(",") if t.strip()]

    with st.container(border=True):
        col_title, col_meta = st.columns([3, 1])
        with col_title:
            st.markdown(
                f"<span style='font-size:1.2rem;font-weight:700'>{row['Name']}</span>",
                unsafe_allow_html=True,
            )
            if row.get("Description"):
                st.caption(str(row["Description"]))
        with col_meta:
            serves = row.get("Serves", "")
            prep   = row.get("Prep_Time", "")
            cook   = row.get("Cook_Time", "")
            if serves:
                st.caption(f"👥 Serves {serves}")
            if prep or cook:
                st.caption(f"⏱ {prep} prep · {cook} cook")

        # Tags
        tag_html = "".join([
            f"<span style='background:{_tag_colour(t)};color:white;padding:2px 8px;"
            f"border-radius:12px;font-size:0.72rem;margin:2px;display:inline-block'>{t}</span>"
            for t in tags
        ])
        st.markdown(tag_html, unsafe_allow_html=True)

        if show_full:
            st.divider()
            col_ing, col_steps = st.columns([1, 1])
            with col_ing:
                st.markdown("**Ingredients**")
                for line in str(row.get("Ingredients","")).split("\n"):
                    if line.strip():
                        st.markdown(f"- {line.strip()}")
            with col_steps:
                st.markdown("**Method**")
                st.markdown(str(row.get("Steps","")))

            if row.get("Wine"):
                st.markdown(
                    f"<div style='background:#2c1654;color:#e8d5ff;padding:8px 12px;"
                    f"border-radius:8px;margin-top:8px'>"
                    f"🍷 <strong>Wine:</strong> {row['Wine']}</div>",
                    unsafe_allow_html=True,
                )
            if row.get("Notes"):
                st.info(f"💡 {row['Notes']}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE CONFIG
# ══════════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="Sue & Andy's Table",
    page_icon="🍽️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialise worksheets on first load
try:
    _init_worksheets()
except Exception as e:
    st.error(f"Could not initialise Google Sheets: {e}")
    st.stop()

# Week info
week_info = get_current_week_info()
wkey      = week_key(week_info)

# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    if week_info["mode"] == "cottage":
        st.markdown("## 🏡 Sue & Andy's Table")
        st.success("🌲 **Cottage Mode**")
    else:
        st.markdown("## 🍽️ Sue & Andy's Table")

    st.caption(week_info["week_label"])
    st.divider()

    section = st.radio(
        "Navigate",
        ["📅  This Week", "📚  Recipe Library", "❄️  Freezer Inventory",
         "🛒  Shopping List", "➕  Add Recipe"],
        label_visibility="collapsed",
    )

    st.divider()
    user = st.selectbox("Who's planning?", ["Sue", "Andy"])
    st.divider()

    # Upcoming cottage weeks
    today = date.today()
    upcoming = [(s, e) for s, e in COTTAGE_WEEKS if s > today]
    if upcoming:
        st.markdown("**🗓 Upcoming Cottage Weeks**")
        for s, e in upcoming[:3]:
            days = (s - today).days
            st.caption(f"🌲 {s.strftime('%b %d')}–{e.strftime('%b %d')} · in {days} days")

    # Freezer quick count
    freezer_df = load_freezer()
    if not freezer_df.empty:
        st.divider()
        st.metric("❄️ Freezer Items", len(freezer_df))


# ══════════════════════════════════════════════════════════════════════════════
# THIS WEEK
# ══════════════════════════════════════════════════════════════════════════════

if "Week" in section:
    mode_icon = "🌲" if week_info["mode"] == "cottage" else "🏠"
    st.title(f"{mode_icon} This Week's Table")
    st.caption(week_info["week_label"])

    if week_info["mode"] == "cottage":
        st.info("🌲 **Cottage Mode** — BBQ-forward meal suggestions. Costco shopping list auto-generated.")

    meal_df  = load_meal_plan()
    recipes_df = load_recipes()
    recipe_names = ["— none planned —"] + (
        recipes_df["Name"].tolist() if not recipes_df.empty else []
    )

    # Freezer items for "use from freezer" suggestions
    freezer_df  = load_freezer()
    freezer_items = freezer_df["Name"].tolist() if not freezer_df.empty else []

    st.divider()

    for i, day in enumerate(week_info["days"]):
        day_date = week_info["week_start"] + timedelta(days=i)
        date_str = day_date.strftime("%Y-%m-%d")
        is_friday = day == "Friday"
        is_today  = day_date == date.today()

        # Get existing meal for this day
        existing = pd.DataFrame()
        if not meal_df.empty and "Week" in meal_df.columns:
            existing = meal_df[
                (meal_df["Week"] == wkey) & (meal_df["Day"] == day)
            ]

        # Day header
        header_bg = "#1a1a2e" if not is_friday else "#2c1654"
        border    = "2px solid #f39c12" if is_friday else ("2px solid #27ae60" if is_today else "1px solid #333")

        st.markdown(
            f"<div style='background:{header_bg};border:{border};"
            f"border-radius:12px;padding:12px 16px;margin-bottom:4px'>"
            f"<span style='font-size:1.1rem;font-weight:700'>"
            f"{_day_emoji(day)} {day}</span>"
            f"<span style='color:#888;margin-left:12px;font-size:0.85rem'>"
            f"{day_date.strftime('%B %d')}</span>"
            f"{'&nbsp;&nbsp;<span style=\"background:#f39c12;color:#000;padding:2px 8px;border-radius:8px;font-size:0.75rem\">✨ Special Night</span>' if is_friday else ''}"
            f"{'&nbsp;&nbsp;<span style=\"background:#27ae60;color:#fff;padding:2px 8px;border-radius:8px;font-size:0.75rem\">Today</span>' if is_today else ''}"
            f"</div>",
            unsafe_allow_html=True,
        )

        if not existing.empty:
            for _, meal_row in existing.iterrows():
                recipe_name = meal_row.get("Recipe_Name", "")
                notes       = meal_row.get("Notes", "")

                # Look up recipe details
                recipe_match = pd.DataFrame()
                if not recipes_df.empty and recipe_name and recipe_name != "— none planned —":
                    recipe_match = recipes_df[recipes_df["Name"] == recipe_name]

                with st.container(border=True):
                    c1, c2, c3 = st.columns([3, 3, 1])
                    with c1:
                        st.markdown(f"**{recipe_name}**")
                        if notes:
                            st.caption(notes)
                    with c2:
                        if not recipe_match.empty:
                            r = recipe_match.iloc[0]
                            tags = [t.strip() for t in str(r.get("Tags","")).split(",") if t.strip()]
                            tag_html = "".join([
                                f"<span style='background:{_tag_colour(t)};color:white;"
                                f"padding:1px 6px;border-radius:8px;font-size:0.68rem;"
                                f"margin:1px;display:inline-block'>{t}</span>"
                                for t in tags[:3]
                            ])
                            st.markdown(tag_html, unsafe_allow_html=True)
                            if r.get("Wine"):
                                st.caption(f"🍷 {r['Wine']}")
                    with c3:
                        st.caption(f"by {meal_row.get('Added_By','')}")

        # Add meal for this day
        with st.expander(f"{'📝 Edit' if not existing.empty else '➕ Plan'} {day}"):
            with st.form(f"meal_{day}_{wkey}"):
                recipe_choice = st.selectbox("Recipe", recipe_names, key=f"rc_{day}")
                col_a, col_b = st.columns(2)
                with col_a:
                    meal_type = st.selectbox("Meal type", ["Dinner","Lunch","Batch Cook","Defrost from Freezer"])
                with col_b:
                    meal_notes = st.text_input("Notes", placeholder="e.g. double batch, add salad")
                if st.form_submit_button("✅ Save", type="primary", use_container_width=True):
                    save_meal(wkey, day, date_str, meal_type,
                              recipe_choice, meal_notes, user)
                    st.success(f"Saved {recipe_choice} for {day}!")
                    st.rerun()

        # Freezer suggestion
        if freezer_items and not is_friday:
            with st.expander(f"❄️ Use from freezer on {day}?", expanded=False):
                for item in freezer_items[:5]:
                    if st.button(f"Plan: {item}", key=f"frz_{day}_{item}"):
                        save_meal(wkey, day, date_str, "Defrost from Freezer", item, "From freezer", user)
                        st.success(f"Added {item} to {day}!")
                        st.rerun()

        st.markdown("<div style='margin-bottom:8px'></div>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# RECIPE LIBRARY
# ══════════════════════════════════════════════════════════════════════════════

elif "Recipe" in section:
    st.title("📚 Recipe Library")
    st.caption("Your personal collection — no ads, no life stories, just the recipe.")

    recipes_df = load_recipes()

    col_search, col_filter, col_refresh = st.columns([3, 2, 1])
    with col_search:
        search = st.text_input("Search recipes", placeholder="Italian, chicken, pasta…")
    with col_filter:
        tag_filter = st.selectbox("Filter by tag", ["All"] + MEAL_TAGS)
    with col_refresh:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄", help="Refresh"):
            load_recipes.clear()
            st.rerun()

    if not recipes_df.empty:
        filtered = recipes_df.copy()
        if search:
            mask = (
                filtered["Name"].str.contains(search, case=False, na=False) |
                filtered["Tags"].str.contains(search, case=False, na=False) |
                filtered["Description"].str.contains(search, case=False, na=False)
            )
            filtered = filtered[mask]
        if tag_filter != "All":
            filtered = filtered[filtered["Tags"].str.contains(tag_filter, case=False, na=False)]

        st.caption(f"{len(filtered)} recipe{'s' if len(filtered) != 1 else ''} found")
        st.divider()

        for _, row in filtered.iterrows():
            with st.expander(f"{'🏠' if 'Freezer-Friendly' in str(row.get('Tags','')) else '🍴'} {row['Name']}"):
                _recipe_card(row, show_full=True)

        # Chicken Pot Pie placeholder
        if not any("Pot Pie" in str(n) for n in recipes_df["Name"].tolist()):
            st.divider()
            with st.container(border=True):
                st.markdown(
                    "<div style='border:2px dashed #8e44ad;border-radius:12px;padding:16px;text-align:center'>"
                    "<span style='font-size:1.1rem'>🥧 <strong>Sue's Chicken Pot Pie</strong></span><br>"
                    "<span style='color:#888;font-size:0.85rem'>Sue's signature dish — waiting to be added to the library</span>"
                    "</div>",
                    unsafe_allow_html=True,
                )
    else:
        st.info("No recipes yet — your starter recipes are being loaded.")


# ══════════════════════════════════════════════════════════════════════════════
# FREEZER INVENTORY
# ══════════════════════════════════════════════════════════════════════════════

elif "Freezer" in section:
    st.title("❄️ Freezer Inventory")
    st.caption("Three freezers, one view.")

    freezer_df = load_freezer()

    col_r, col_add = st.columns([1, 4])
    with col_r:
        if st.button("🔄 Refresh"):
            load_freezer.clear()
            st.rerun()

    # Show by freezer
    for freezer_name in FREEZERS:
        st.subheader(f"🧊 {freezer_name}")
        if not freezer_df.empty:
            f_df = freezer_df[freezer_df["Freezer"] == freezer_name]
            if not f_df.empty:
                for _, row in f_df.iterrows():
                    with st.container(border=True):
                        c1, c2, c3, c4 = st.columns([3, 1, 2, 1])
                        with c1:
                            st.markdown(f"**{row['Name']}**")
                            if row.get("Notes"):
                                st.caption(str(row["Notes"]))
                        with c2:
                            st.markdown(f"{row['Quantity']} {row['Unit']}")
                        with c3:
                            added = str(row.get("Date_Added",""))[:10]
                            use_by = str(row.get("Use_By",""))
                            if added:
                                st.caption(f"Added: {added}")
                            if use_by:
                                st.caption(f"Use by: {use_by}")
                        with c4:
                            if st.button("✅ Used", key=f"rm_{row['ID']}"):
                                remove_freezer_item(str(row["ID"]))
                                st.success("Removed!")
                                st.rerun()
            else:
                st.caption("Nothing logged in this freezer.")
        else:
            st.caption("Nothing logged yet.")

    st.divider()
    st.subheader("➕ Add to Freezer")
    with st.form("add_freezer"):
        c1, c2 = st.columns(2)
        with c1:
            f_name    = st.text_input("Item name", placeholder="e.g. Sue's Chicken Pot Pie")
            f_freezer = st.selectbox("Which freezer?", FREEZERS)
            f_qty     = st.number_input("Quantity", min_value=1, value=1)
        with c2:
            f_unit   = st.selectbox("Unit", ["portions","containers","bags","pieces","batches","litres"])
            f_useby  = st.text_input("Use by (optional)", placeholder="e.g. March 2027")
            f_notes  = st.text_input("Notes", placeholder="e.g. double batch, Sep 2025")
        if st.form_submit_button("❄️ Add to Freezer", type="primary", use_container_width=True):
            if f_name.strip():
                save_freezer_item(f_name.strip(), f_qty, f_unit, f_freezer, f_useby, f_notes, user)
                st.success(f"Added {f_name} to {f_freezer}!")
                st.rerun()
            else:
                st.warning("Please enter an item name.")


# ══════════════════════════════════════════════════════════════════════════════
# SHOPPING LIST
# ══════════════════════════════════════════════════════════════════════════════

elif "Shopping" in section:
    st.title("🛒 Shopping List")
    st.caption(f"Week of {week_info['week_start'].strftime('%B %d, %Y')}")

    shopping_df = load_shopping_list()

    col_r, col_clear = st.columns([1, 4])
    with col_r:
        if st.button("🔄 Refresh"):
            load_shopping_list.clear()
            st.rerun()

    # This week's list by store
    if not shopping_df.empty:
        week_items = shopping_df[shopping_df["Week"] == wkey] if "Week" in shopping_df.columns else shopping_df

        if not week_items.empty:
            for store in STORES:
                store_items = week_items[week_items["Store"] == store]
                if store_items.empty:
                    continue
                checked_count = len(store_items[store_items["Checked"] == "Yes"])
                total_count   = len(store_items)

                st.subheader(f"🏪 {store} ({checked_count}/{total_count})")
                for idx, row in store_items.iterrows():
                    is_checked = row.get("Checked","No") == "Yes"
                    c1, c2, c3 = st.columns([1, 4, 1])
                    with c1:
                        checked = st.checkbox("", value=is_checked, key=f"chk_{idx}")
                        if checked != is_checked:
                            toggle_shopping_item(idx, row.get("Checked","No"))
                            st.rerun()
                    with c2:
                        style = "text-decoration:line-through;color:#666" if is_checked else ""
                        qty   = f"{row['Quantity']} {row['Unit']} — " if row.get("Quantity") else ""
                        st.markdown(
                            f"<span style='{style}'>{qty}{row['Item']}</span>",
                            unsafe_allow_html=True,
                        )
                    with c3:
                        st.caption(str(row.get("Category","")))
        else:
            st.info("No items for this week yet.")
    else:
        st.info("Shopping list is empty — add items below.")

    st.divider()
    st.subheader("➕ Add Item")
    with st.form("add_shopping"):
        c1, c2 = st.columns(2)
        with c1:
            s_item     = st.text_input("Item", placeholder="e.g. Hot Italian sausage")
            s_store    = st.selectbox("Store", STORES)
            s_category = st.selectbox("Category", [
                "Meat & Fish","Produce","Dairy & Eggs","Pasta & Grains",
                "Canned & Pantry","Bread & Bakery","Frozen","Wine & Drinks","Other"
            ])
        with c2:
            s_qty  = st.text_input("Quantity", placeholder="e.g. 500")
            s_unit = st.selectbox("Unit", ["g","kg","ml","L","pieces","cans","bags","loaves","bottles",""])
            s_note = st.text_input("Note", placeholder="optional")
        if st.form_submit_button("🛒 Add to List", type="primary", use_container_width=True):
            if s_item.strip():
                save_shopping_item(wkey, s_item.strip(), s_qty, s_unit, s_store, s_category, user)
                st.success(f"Added {s_item}!")
                st.rerun()
            else:
                st.warning("Please enter an item.")


# ══════════════════════════════════════════════════════════════════════════════
# ADD RECIPE
# ══════════════════════════════════════════════════════════════════════════════

elif "Add" in section:
    st.title("➕ Add a Recipe")
    st.caption("Save it once, find it forever — no ads, no fluff.")

    tab_manual, tab_image = st.tabs([
        "✍️ Enter Manually",
        "📸 Extract from Photo/Screenshot",
    ])

    with tab_manual:
        with st.form("add_recipe_manual"):
            c1, c2 = st.columns(2)
            with c1:
                r_name = st.text_input("Recipe Name *", placeholder="e.g. Sue's Chicken Pot Pie")
                r_desc = st.text_input("One-line description", placeholder="e.g. A warming classic, always in demand")
                r_tags = st.multiselect("Tags", MEAL_TAGS)
                r_wine = st.text_input("Wine pairing", placeholder="e.g. Chardonnay or light Pinot Noir")
            with c2:
                r_serves = st.number_input("Serves", min_value=1, max_value=20, value=2)
                r_prep   = st.text_input("Prep time", placeholder="e.g. 20 min")
                r_cook   = st.text_input("Cook time", placeholder="e.g. 1 hr 15 min")
                r_notes  = st.text_input("Tips / Notes", placeholder="e.g. Freezes beautifully")

            r_ingredients = st.text_area(
                "Ingredients *",
                placeholder="One per line:\n500g chicken breast\n1 cup frozen peas\n...",
                height=180,
            )
            r_steps = st.text_area(
                "Method *",
                placeholder="1. Preheat oven to 375°F...\n2. ...",
                height=200,
            )

            if st.form_submit_button("💾 Save Recipe", type="primary", use_container_width=True):
                if r_name.strip() and r_ingredients.strip() and r_steps.strip():
                    save_recipe(
                        r_name.strip(), r_desc.strip(),
                        ",".join(r_tags),
                        r_serves, r_prep, r_cook,
                        r_ingredients.strip(), r_steps.strip(),
                        r_wine.strip(), r_notes.strip(), user,
                    )
                    st.success(f"✅ '{r_name}' saved to your recipe library!")
                    st.balloons()
                else:
                    st.warning("Please fill in Name, Ingredients, and Method at minimum.")

    with tab_image:
        st.markdown(
            "Upload a photo of a recipe card, a screenshot of a webpage, or a photo of a cookbook page. "
            "Claude will extract the recipe and save it cleanly to your library."
        )

        if not ANTHROPIC_KEY:
            st.warning("⚠️ Add ANTHROPIC_API_KEY to your Streamlit secrets to enable this feature.")
        else:
            uploaded = st.file_uploader(
                "Upload recipe image",
                type=["jpg","jpeg","png","webp"],
                help="Photo, screenshot, or scan of any recipe"
            )

            if uploaded:
                st.image(uploaded, caption="Uploaded image", use_container_width=True)

                if st.button("🔍 Extract Recipe", type="primary"):
                    with st.spinner("Claude is reading the recipe…"):
                        media_type = f"image/{uploaded.type.split('/')[-1]}"
                        extracted  = extract_recipe_from_image(uploaded.read(), media_type)

                    if extracted:
                        st.success("Recipe extracted! Review and save:")
                        with st.form("save_extracted"):
                            e_name  = st.text_input("Name", value=extracted.get("name",""))
                            e_desc  = st.text_input("Description", value=extracted.get("description",""))
                            e_tags  = st.multiselect("Tags", MEAL_TAGS)
                            e_wine  = st.text_input("Wine pairing (add your own)")
                            e_ing   = st.text_area("Ingredients", value=extracted.get("ingredients",""), height=150)
                            e_steps = st.text_area("Method", value=extracted.get("steps",""), height=180)
                            e_notes = st.text_input("Notes", value=extracted.get("notes",""))
                            if st.form_submit_button("💾 Save to Library", type="primary"):
                                save_recipe(
                                    e_name, e_desc, ",".join(e_tags),
                                    extracted.get("serves", 2),
                                    extracted.get("prep_time",""),
                                    extracted.get("cook_time",""),
                                    e_ing, e_steps, e_wine, e_notes, user,
                                )
                                st.success(f"✅ '{e_name}' saved!")
                                st.balloons()
