"""
Helvetas RCFSP Baseline - Household Survey dashboard
Live data from the KoboToolbox API.

Setup (once):
  python -m pip install streamlit pandas requests plotly
  .streamlit/secrets.toml next to this file:
      KOBO_SERVER = "https://kf.kobotoolbox.org"
      KOBO_TOKEN  = "your_api_token"
      ASSET_UID   = "uid_of_the_Helvetas_household_form"
Run:
  python -m streamlit run app.py
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import requests
import streamlit as st

st.set_page_config(page_title="Helvetas Baseline – Household Survey", layout="wide")

# ---------------------------------------------------------------- colours
# Helvetas-style palette built on the red of the Helvetas logo.
# The hex codes are close matches, not taken from the official brand guide:
# replace them here if you get the exact codes.
RED = "#E2001A"        # Helvetas red (main colour)
DARK_RED = "#8C1C24"
LIGHT_RED = "#F4A3A8"
CHARCOAL = "#3C3C3B"
WARM_GREY = "#A39D95"
SAND = "#D9D2C5"
PALETTE = [RED, CHARCOAL, WARM_GREY, DARK_RED, LIGHT_RED, SAND, "#6E6E6D", "#C9A9A6"]

pio.templates["helvetas"] = pio.templates["plotly_white"]
pio.templates["helvetas"].layout.colorway = PALETTE
pio.templates["helvetas"].layout.font.family = "Arial, Helvetica, sans-serif"
pio.templates["helvetas"].layout.update(
    font=dict(size=13, color=CHARCOAL),
    title=dict(font=dict(size=16, color=CHARCOAL), x=0, xanchor="left", y=0.98, yanchor="top"),
    margin=dict(l=10, r=30, t=80, b=10),
    legend=dict(title_text="", orientation="h", x=1, xanchor="right", y=1.0, yanchor="bottom"),
    bargap=0.25)
pio.templates["helvetas"].layout.xaxis.update(gridcolor="#ECEAE6", zeroline=False)
pio.templates["helvetas"].layout.yaxis.update(gridcolor="#ECEAE6", zeroline=False)
pio.templates.default = "helvetas"
px.defaults.color_discrete_sequence = PALETTE

st.markdown(f"""
<style>
  h1, h2, h3 {{ color: {CHARCOAL}; }}
  h1 {{ border-bottom: 4px solid {RED}; padding-bottom: .3rem; }}
  [data-testid="stMetricValue"] {{ color: {RED}; }}
  [data-testid="stMetric"] {{ background: #FAF8F5; border-left: 5px solid {RED};
                             border-radius: 6px; padding: .7rem 1rem; }}
</style>""", unsafe_allow_html=True)

SERVER = st.secrets["KOBO_SERVER"].rstrip("/")
TOKEN = st.secrets["KOBO_TOKEN"]
UID = st.secrets["ASSET_UID"]
HEADERS = {"Authorization": f"Token {TOKEN}"}
# Access and Food security tabs are always shown
SHOW_INDICATORS = True

# ---------------------------------------------------------------- form facts
MAIN_VARS = {
    "Q002": "Region",
    "Q003": "Zone",
    "Q004": "Woreda",
    "Q007": "Bridge site",
    "enum_name": "Enumerator",
}
BREAKDOWNS = {**MAIN_VARS, "A02": "Sex of household head",
              "Q014": "River bank", "Q013": "Livelihood system"}

# Target households per bridge site (hh_target in list_site of the XLSForm)
SITE_TARGETS = {"11": 18, "12": 17, "21": 18, "22": 17, "31": 18, "32": 17, "41": 17,
                "42": 17, "51": 17, "52": 17, "61": 15, "62": 15, "71": 15, "72": 14,
                "81": 15, "82": 14, "91": 15, "92": 14, "101": 14, "102": 14, "111": 27,
                "121": 19, "131": 18, "141": 18, "151": 17, "161": 17, "171": 17, "181": 11,
                "182": 10, "191": 20, "201": 17, "211": 17, "221": 16, "231": 15, "241": 10,
                "242": 10, "251": 17, "261": 15, "271": 13, "281": 13}

# Woreda of each bridge site (woreda column of list_site)
SITE_WOREDA = {"11": "1", "12": "1", "21": "2", "22": "2", "31": "3", "32": "3", "41": "4", "42": "4",
               "51": "5", "52": "5", "61": "6", "62": "6", "71": "7", "72": "7", "81": "8", "82": "8",
               "91": "9", "92": "9", "101": "10", "102": "10", "111": "11", "121": "12", "131": "13",
               "141": "14", "151": "15", "161": "16", "171": "17", "181": "18", "182": "18", "191": "19",
               "201": "20", "211": "21", "221": "22", "231": "23", "241": "24", "242": "24", "251": "25",
               "261": "26", "271": "27", "281": "28"}
N_WOREDAS = len(set(SITE_WOREDA.values()))

FACILITIES = {"F1": "Weekly market", "F2": "Woreda town market",
              "F3": "Primary school (1–6)", "F4": "Health post", "F5": "Health centre"}
INCIDENTS = [f"E36_{i}" for i in range(1, 9)]

AGE_BANDS = {"a": "0–5", "b": "6–14", "c": "15–18", "d": "19–29", "e": "30–59", "f": "60–64", "g": "65+"}
PROFILE_NUM = (["A03", "A08_sex", "A01_male", "A01_female", "A01_dep_ratio", "A_youth_present",
                "A_female_headed", "A_elderly_headed", "n_girls_6_18", "n_boys_6_18", "A10_g", "A10_b"]
               + [f"A01{b}_{s}" for b in AGE_BANDS for s in ("m", "f")])
NUMERIC_VARS = (["G_FCS", "G_HDDS", "H_HHS", "J_rCSI", "I_MAHFP", "J_LCS_cat",
                 "A01_size", "A_disability_hh", "Q026_lat", "Q026_lon"] + PROFILE_NUM
                + [f"{q}_{f}" for f in FACILITIES for q in ("E06", "E08", "E13", "E08")]
                + [f"E08_{f}_unreach" for f in FACILITIES])
NEEDED = (list(BREAKDOWNS) + ["A04", "A05", "A06", "CONSENT", "Q007_other", "E59", "K01_09", "today"]
          + INCIDENTS + NUMERIC_VARS)


# ---------------------------------------------------------------- data access
@st.cache_data(ttl=600, show_spinner="Downloading submissions from Kobo...")
def fetch_submissions() -> pd.DataFrame:
    url = f"{SERVER}/api/v2/assets/{UID}/data/?format=json&limit=5000"
    rows = []
    while url:
        r = requests.get(url, headers=HEADERS, timeout=120)
        r.raise_for_status()
        js = r.json()
        rows.extend(js["results"])
        url = js.get("next")
    return pd.json_normalize(rows)


@st.cache_data(ttl=3600)
def fetch_form():
    r = requests.get(f"{SERVER}/api/v2/assets/{UID}/?format=json",
                     headers=HEADERS, timeout=60)
    r.raise_for_status()
    content = r.json().get("content", {})

    def first_label(item):
        lab = item.get("label")
        return lab[0] if isinstance(lab, list) and lab else item.get("name")

    questions = {}
    for q in content.get("survey", []):
        name = q.get("name") or q.get("$autoname")
        if name:
            ln = q.get("select_from_list_name")
            questions[name] = {"label": first_label(q), "type": q.get("type", ""),
                               "list": ln.strip() if isinstance(ln, str) else None}
    choices = {}
    for c in content.get("choices", []):
        ln = c.get("list_name")
        if not isinstance(ln, str) or c.get("name") is None:
            continue
        choices.setdefault(ln.strip(), {})[str(c["name"])] = first_label(c)
    return questions, choices


def prepare(raw, questions, choices):
    d = raw.copy()
    d.columns = [c.split("/")[-1] for c in d.columns]
    d = d.loc[:, ~d.columns.duplicated()]
    for c in NEEDED:
        if c not in d.columns:
            d[c] = pd.NA
    for c in NUMERIC_VARS:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d.loc[d["A03"] == 98, "A03"] = pd.NA          # 98 = don't know
    for name, q in questions.items():
        if name in d.columns and q["type"].startswith("select_one") and q["list"]:
            codes = d[name].where(d[name].isna(), d[name].astype(str))
            d[name] = codes
            d[name + "_lbl"] = codes.map(choices.get(q["list"], {})).fillna(codes)
    for c in BREAKDOWNS:
        if c + "_lbl" not in d.columns:
            d[c + "_lbl"] = d[c]
        d[c + "_lbl"] = d[c + "_lbl"].fillna("Missing")
    # replacement sites typed in Q007_other
    other = d["Q007"] == "96"
    d.loc[other, "Q007_lbl"] = "Other: " + d.loc[other, "Q007_other"].fillna("?").astype(str)

    sub = pd.to_datetime(d["_submission_time"], errors="coerce")
    d["date"] = pd.to_datetime(d["today"], errors="coerce").fillna(sub).dt.date
    return d


# ---------------------------------------------------------------- indicators
def pct(mask, base):
    n = int(base.sum())
    return (round(100 * (mask & base).sum() / n, 1) if n else None), n


def mean_of(s, digits=1):
    s = s.dropna()
    return (round(s.mean(), digits) if len(s) else None), len(s)


def median_of(s):
    s = s.dropna()
    return (round(s.median()) if len(s) else None), len(s)


def any_incident(d):
    inc = d[INCIDENTS]
    answered = inc.notna().any(axis=1)
    yes = (inc == "1").any(axis=1)
    return pct(yes, answered)


INDICATORS = [
    # (group, label, definition, function, unit)
    ("Access", "G2 · Year-round access to weekly market",
     "E13_F1 = 0 months cut off in the past 12 months", lambda d: pct(d["E13_F1"] == 0, d["E13_F1"].notna()), "%"),
    ("Access", "G2 · Year-round access to health post",
     "E13_F4 = 0 months cut off", lambda d: pct(d["E13_F4"] == 0, d["E13_F4"].notna()), "%"),
    ("Access", "O3 · Travel time to weekly market, rainy season",
     "Median E08_F1, minutes one way", lambda d: median_of(d["E08_F1"]), "min"),
    ("Access", "Cannot reach weekly market in rainy season",
     "E07_F1 = cannot travel at all (E08_F1_unreach = 1)",
     lambda d: pct(d["E08_F1_unreach"] == 1, d["E08_F1_unreach"].notna()), "%"),
    ("Access", "Crossing incident in past 12 months",
     "Any of E36_1–E36_8 = Yes", any_incident, "%"),
    ("Access", "Drowning death in past 12 months",
     "E36_3 = Yes", lambda d: pct(d["E36_3"] == "1", d["E36_3"].isin(["0", "1"])), "%"),
    ("Access", "Heard about the planned bridge", "E59 = Yes",
     lambda d: pct(d["E59"] == "1", d["E59"].notna()), "%"),
    ("Access", "Member of a BUMC / O&M committee", "K01_09 = Yes",
     lambda d: pct(d["K01_09"] == "1", d["K01_09"].isin(["0", "1"])), "%"),
    ("Food security", "Acceptable food consumption (FCS)",
     "G_FCS above 35",
     lambda d: pct(d["G_FCS"] > FCS_HI, d["G_FCS"].notna()), "%"),
    ("Food security", "Household dietary diversity (HDDS)", "Mean G_HDDS (0–12)",
     lambda d: mean_of(d["G_HDDS"]), ""),
    ("Food security", "Moderate or severe hunger (HHS)", "H_HHS 2–6",
     lambda d: pct(d["H_HHS"] >= 2, d["H_HHS"].notna()), "%"),
    ("Food security", "Reduced coping strategies (rCSI)", "Mean J_rCSI (0–56)",
     lambda d: mean_of(d["J_rCSI"]), ""),
    ("Food security", "Crisis or emergency coping (LCS)", "J_LCS_cat = 2 or 3",
     lambda d: pct(d["J_LCS_cat"] >= 2, d["J_LCS_cat"].notna()), "%"),
    ("Food security", "Months of adequate food (MAHFP)", "Mean I_MAHFP (0–12)",
     lambda d: mean_of(d["I_MAHFP"]), ""),
    ("Profile", "Female-headed households", "A02 = Female",
     lambda d: pct(d["A02"] == "2", d["A02"].notna()), "%"),
    ("Profile", "Average household size", "Mean A01_size",
     lambda d: mean_of(d["A01_size"]), ""),
    ("Profile", "Households with a member with a disability", "A_disability_hh = 1",
     lambda d: pct(d["A_disability_hh"] == 1, d["A_disability_hh"].notna()), "%"),
]


def fmt(val, unit):
    if val is None:
        return "–"
    if unit == "%":
        return f"{val:.0f}%"
    if unit == "min":
        return f"{val:.0f} min"
    return f"{val:.1f}"


def indicator_table(df, by):
    groups = [("All", df)] + ([] if by is None else list(df.groupby(by + "_lbl", sort=True)))
    rows = []
    for gname, g in groups:
        row = {"Group": gname, "Households": len(g)}
        for _, label, _, fn, unit in INDICATORS:
            row[f"{label} ({unit})" if unit else label] = fn(g)[0]
        rows.append(row)
    return pd.DataFrame(rows)


def category_chart(df, var_fn, order, colors, title, by_lbl):
    cat = var_fn(df)
    tmp = df.assign(_cat=cat).dropna(subset=["_cat"])
    if tmp.empty:
        st.info(f"No data yet for {title}.")
        return
    grp = by_lbl if by_lbl else None
    if grp:
        t = (tmp.groupby([grp, "_cat"]).size() / tmp.groupby(grp).size() * 100)
        t = t.rename("%").reset_index()
        fig = px.bar(t, x=grp, y="%", color="_cat", category_orders={"_cat": order},
                     color_discrete_map=dict(zip(order, colors)), title=title,
                     labels={"_cat": "", grp: ""})
    else:
        t = tmp["_cat"].value_counts(normalize=True).mul(100).reindex(order).fillna(0)
        t = t.rename("%").reset_index().rename(columns={"index": "_cat"})
        t["x"] = "All households"
        fig = px.bar(t, x="x", y="%", color="_cat", category_orders={"_cat": order},
                     color_discrete_map=dict(zip(order, colors)), title=title,
                     labels={"_cat": "", "x": ""}, text=t["%"].round(0))
    fig.update_layout(barmode="stack", yaxis_range=[0, 100], legend_title_text="")
    st.plotly_chart(fig, width="stretch")


# ---------------------------------------------------------------- load
try:
    raw = fetch_submissions()
    questions, choices = fetch_form()
except requests.HTTPError as e:
    st.error(f"Kobo API error: {e}. Check the token, UID and server URL.")
    st.stop()

if raw.empty:
    st.warning("No submissions yet.")
    st.stop()

data = prepare(raw, questions, choices)

# ---------------------------------------------------------------- sidebar
st.sidebar.markdown(f"<h2 style='color:{RED};margin-bottom:0'>HELVETAS</h2>"
                    "<p style='margin-top:0'>Baseline · Household Survey</p>",
                    unsafe_allow_html=True)
if st.sidebar.button("Refresh data from Kobo"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.header("Filters")
dmin, dmax = data["date"].min(), data["date"].max()
dr = st.sidebar.date_input("Interview date", (dmin, dmax), min_value=dmin, max_value=dmax)
df = data
if isinstance(dr, tuple) and len(dr) == 2:
    df = df[(df["date"] >= dr[0]) & (df["date"] <= dr[1])]
for var, label in MAIN_VARS.items():
    pick = st.sidebar.multiselect(label, sorted(df[var + "_lbl"].unique()))
    if pick:
        df = df[df[var + "_lbl"].isin(pick)]

# FCS cut-offs: Poor <= 21, Borderline 21.5-35, Acceptable > 35 (WFP standard).
# For populations eating oil and sugar almost daily WFP uses 28 / 42: change here if needed.
FCS_LO, FCS_HI = 21, 35

hh = df[df["CONSENT"] == "1"]

# ---------------------------------------------------------------- header
st.title("Helvetas Baseline – Household Survey")
st.caption(f"Live from Kobo · last submission "
           f"{pd.to_datetime(data['_submission_time']).max():%d %b %Y %H:%M} · "
           f"{len(hh)} households interviewed")

target = sum(SITE_TARGETS.values())
k = st.columns(5)
k[0].metric("Households interviewed", f"{len(hh):,}")
k[1].metric("Target", f"{target:,}")
k[2].metric("Progress", f"{100 * len(data[data['CONSENT'] == '1']) / target:.0f}%",
            help="All households interviewed so far, ignoring filters")
k[3].metric("Sites visited", hh["Q007"].nunique())
k[4].metric("Woredas covered", f"{hh['Q004'].nunique()} of {N_WOREDAS}")

tab_names = ["Fieldwork progress", "Household profile"]
if SHOW_INDICATORS:
    tab_names += ["Access & crossings", "Food security"]
tab_names += ["Explore a question"]
tabs = dict(zip(tab_names, st.tabs(tab_names)))

# ---------------------------------------------------------------- fieldwork
with tabs["Fieldwork progress"]:
    done_by_site = data[data["CONSENT"] == "1"].groupby("Q007").size()
    site_lbl = choices.get("list_site", {})
    wor_lbl = choices.get("list_woreda", {})
    prog = pd.DataFrame({"code": list(SITE_TARGETS), "Target": list(SITE_TARGETS.values())})
    prog["Done"] = prog["code"].map(done_by_site).fillna(0).astype(int)
    prog["Bridge site"] = prog["code"].map(site_lbl).fillna(prog["code"])
    prog["wcode"] = prog["code"].map(SITE_WOREDA)
    prog["Woreda"] = [wor_lbl.get(w, w) for w in prog["wcode"]]
    prog["Progress"] = (100 * prog["Done"] / prog["Target"]).round(0)
    prog["Status"] = pd.cut(prog["Progress"], [-1, 0, 99.9, 10000],
                            labels=["Not started", "In progress", "Completed"]).astype(str)
    total_done = int(prog["Done"].sum())

    # --- row 1: overall donut + woreda progress
    c1, c2 = st.columns([1, 2], gap="large")
    with c1:
        fig = go.Figure(go.Pie(values=[total_done, max(target - total_done, 0)],
                               labels=["Interviewed", "Remaining"], hole=0.7, sort=False,
                               marker=dict(colors=[RED, SAND]), textinfo="none",
                               hovertemplate="%{label}: %{value}<extra></extra>"))
        fig.update_layout(title="Overall progress", height=340, showlegend=True,
                          legend=dict(x=0.5, xanchor="center", y=-0.02, yanchor="top"),
                          annotations=[dict(text=f"<b>{100 * total_done / target:.0f}%</b><br>"
                                                 f"<span style='font-size:13px'>{total_done} of {target}</span>",
                                            x=0.5, y=0.5, showarrow=False, font=dict(size=30, color=RED))])
        st.plotly_chart(fig, width="stretch")
        s_counts = prog["Status"].value_counts()
        pill = ("<span style='display:inline-block;margin:0 .6rem .4rem 0;padding:.25rem .7rem;"
                "border-radius:1rem;background:{bg};color:{fg};font-size:.9rem'><b>{n}</b> {t}</span>")
        st.markdown(
            "<div style='text-align:center'><div style='color:#6E6E6D;margin-bottom:.3rem'>Bridge sites</div>"
            + pill.format(bg=CHARCOAL, fg="white", n=int(s_counts.get("Completed", 0)), t="completed")
            + pill.format(bg=RED, fg="white", n=int(s_counts.get("In progress", 0)), t="in progress")
            + pill.format(bg=SAND, fg=CHARCOAL, n=int(s_counts.get("Not started", 0)), t="not started")
            + "</div>", unsafe_allow_html=True)
    with c2:
        w = prog.groupby("Woreda", as_index=False)[["Done", "Target"]].sum()
        w["pct"] = 100 * w["Done"] / w["Target"]
        w = w.sort_values(["pct", "Woreda"], ascending=[True, False])
        fig = go.Figure()
        fig.add_bar(y=w["Woreda"], x=w["Target"], orientation="h", name="Target",
                    marker_color=SAND, width=0.75,
                    text=[f"{d} / {t}" for d, t in zip(w["Done"], w["Target"])],
                    textposition="outside", textfont=dict(size=12, color=CHARCOAL), cliponaxis=False,
                    hovertemplate="%{y}: target %{x}<extra></extra>")
        fig.add_bar(y=w["Woreda"], x=w["Done"], orientation="h", name="Interviewed",
                    marker_color=RED, width=0.45,
                    hovertemplate="%{y}: %{x} interviewed<extra></extra>")
        fig.update_layout(title="Households interviewed vs target, by woreda", barmode="overlay",
                          height=max(380, 26 * len(w) + 100),
                          xaxis=dict(range=[0, w["Target"].max() * 1.18], title=""),
                          yaxis=dict(tickfont=dict(size=12)))
        st.plotly_chart(fig, width="stretch")

    # --- row 2: site table + enumerators
    c3, c4 = st.columns([3, 2], gap="large")
    with c3:
        st.markdown("##### Progress by bridge site")
        show = st.segmented_control("Show", ["All", "Not started", "In progress", "Completed"],
                                    default="All", key="site_status", label_visibility="collapsed")
        tbl = prog if show in (None, "All") else prog[prog["Status"] == show]
        st.dataframe(
            tbl.sort_values(["Woreda", "Bridge site"])[["Woreda", "Bridge site", "Done", "Target", "Progress", "Status"]],
            hide_index=True, width="stretch", height=430,
            column_config={"Progress": st.column_config.ProgressColumn(
                "Progress", format="%d%%", min_value=0, max_value=100),
                "Done": st.column_config.NumberColumn("Interviewed"),
                "Bridge site": st.column_config.TextColumn("Bridge site")})
    with c4:
        e = hh.groupby("enum_name_lbl").size().reset_index(name="Households").sort_values("Households")
        fig = px.bar(e, x="Households", y="enum_name_lbl", orientation="h", text="Households",
                     title="Households by enumerator", color_discrete_sequence=[CHARCOAL])
        fig.update_traces(textposition="outside", cliponaxis=False)
        fig.update_layout(height=max(380, 26 * len(e) + 90), yaxis_title="", xaxis_title="",
                          xaxis_range=[0, e["Households"].max() * 1.15 if len(e) else 1])
        st.plotly_chart(fig, width="stretch")

    # --- row 3: map
    pts = hh.dropna(subset=["Q026_lat", "Q026_lon"])
    if len(pts):
        fig = px.scatter_map(pts, lat="Q026_lat", lon="Q026_lon", zoom=6, height=520,
                             hover_name="Q007_lbl", hover_data={"Q004_lbl": True, "enum_name_lbl": True,
                                                               "Q026_lat": False, "Q026_lon": False},
                             labels={"Q004_lbl": "Woreda", "enum_name_lbl": "Enumerator"},
                             color_discrete_sequence=[RED], title="Interview locations")
        fig.update_traces(marker=dict(size=9, opacity=0.8))
        fig.update_layout(map_style="carto-positron", margin=dict(l=0, r=0, t=50, b=0))
        st.plotly_chart(fig, width="stretch")

# ---------------------------------------------------------------- household profile
SEX = {1: "Male", 2: "Female"}
EDU_GROUPS = [(0, 0, "No education"), (1, 2, "Religious / informal / adult literacy"),
              (11, 18, "Primary (grades 1–8)"), (19, 22, "Secondary (grades 9–12)"),
              (23, 25, "TVET, college or university")]


def edu_group(code):
    try:
        c = int(code)
    except (TypeError, ValueError):
        return None
    for lo, hi, name in EDU_GROUPS:
        if lo <= c <= hi:
            return name
    return None


def share_chart(d, col, title, order=None, split=None):
    sub = d.dropna(subset=[col])
    if sub.empty:
        st.info(f"No data yet for {title.lower()}.")
        return
    if split:
        t = (sub.groupby([split, col]).size() / sub.groupby(split).size() * 100).rename("%").reset_index()
        fig = px.bar(t, x="%", y=split, color=col, orientation="h", title=title,
                     category_orders={col: order} if order else None,
                     labels={split: "", col: ""}, text=t["%"].round(0))
        fig.update_traces(texttemplate="%{text:.0f}", textposition="inside")
        fig.update_layout(barmode="stack", xaxis=dict(range=[0, 100], title=""),
                          height=max(300, 34 * t[split].nunique() + 140))
    else:
        t = sub[col].value_counts(normalize=True).mul(100).rename("%").reset_index()
        if order:
            t[col] = pd.Categorical(t[col], order, ordered=True)
            t = t.sort_values(col, ascending=False)
        fig = px.bar(t, x="%", y=col, orientation="h", title=title, text=t["%"].round(0),
                     color_discrete_sequence=[RED], labels={col: ""})
        fig.update_traces(texttemplate="%{text:.0f}%", textposition="outside", cliponaxis=False,
                          width=0.55)
        fig.update_layout(xaxis=dict(range=[0, 105], title="", showticklabels=False, showgrid=False),
                          height=max(260, 40 * len(t) + 110))
    st.plotly_chart(fig, width="stretch")


with tabs["Household profile"]:
    st.caption(f"{len(hh)} households interviewed (sidebar filters applied).")
    p = hh.copy()
    p["Head sex"] = p["A02"].map({"1": "Male", "2": "Female"})
    p["Respondent sex"] = p["A08_sex"].map(SEX)
    p["Head age group"] = pd.cut(p["A03"], [0, 29, 44, 59, 200],
                                 labels=["Under 30", "30–44", "45–59", "60 and above"]).astype("object")
    p["Head education"] = p["A05"].map(edu_group)
    girls_rate = 100 * p["A10_g"].sum() / p.loc[p["n_girls_6_18"] > 0, "n_girls_6_18"].sum() \
        if p.loc[p["n_girls_6_18"] > 0, "n_girls_6_18"].sum() else None
    boys_rate = 100 * p["A10_b"].sum() / p.loc[p["n_boys_6_18"] > 0, "n_boys_6_18"].sum() \
        if p.loc[p["n_boys_6_18"] > 0, "n_boys_6_18"].sum() else None

    k = st.columns(4)
    k[0].metric("Female-headed", fmt(pct(p["A02"] == "2", p["A02"].notna())[0], "%"),
                help="A02 = Female")
    k[1].metric("Avg. age of head", fmt(mean_of(p["A03"])[0], ""),
                help="A03, years (98 = don't know excluded)")
    k[2].metric("Elderly-headed (60+)", fmt(pct(p["A03"] >= 60, p["A03"].notna())[0], "%"),
                help="A03 ≥ 60")
    k[3].metric("Avg. household size", fmt(mean_of(p["A01_size"])[0], ""), help="A01_size")
    k = st.columns(4)
    k[0].metric("Has youth (15–29)",
                fmt(pct(p["A_youth_present"] == 1, p["A_youth_present"].notna())[0], "%"),
                help="A_youth_present = 1")
    k[1].metric("Has member with disability",
                fmt(pct(p["A_disability_hh"] == 1, p["A_disability_hh"].notna())[0], "%"),
                help="A_disability_hh = 1 (Washington Group domains, A14)")
    k[2].metric("Girls 6–18 in school", fmt(None if girls_rate is None else round(girls_rate, 1), "%"),
                help="Sum of A10_g / sum of girls aged 6–18 (A01b_f + A01c_f)")
    k[3].metric("Boys 6–18 in school", fmt(None if boys_rate is None else round(boys_rate, 1), "%"),
                help="Sum of A10_b / sum of boys aged 6–18 (A01b_m + A01c_m)")

    split_label = st.selectbox("Split charts by", ["(none)", "Sex of household head"]
                               + [v for k_, v in BREAKDOWNS.items() if k_ != "A02"], key="prof_by")
    if split_label == "(none)":
        split = None
    elif split_label == "Sex of household head":
        split = "Head sex"
    else:
        split = {v: k_ for k_, v in BREAKDOWNS.items()}[split_label] + "_lbl"

    # household members by age and sex (population pyramid)
    rows = []
    for b, band in AGE_BANDS.items():
        rows.append({"Age": band, "Sex": "Male", "Members": -p[f"A01{b}_m"].sum()})
        rows.append({"Age": band, "Sex": "Female", "Members": p[f"A01{b}_f"].sum()})
    pyr = pd.DataFrame(rows)
    if pyr["Members"].abs().sum() > 0:
        fig = px.bar(pyr, x="Members", y="Age", color="Sex", orientation="h",
                     category_orders={"Age": list(AGE_BANDS.values())[::-1]},
                     color_discrete_map={"Male": CHARCOAL, "Female": RED},
                     title=f"Household members by age and sex (total {int(pyr['Members'].abs().sum()):,})",
                     custom_data=[pyr["Members"].abs()])
        fig.update_traces(hovertemplate="%{y}: %{customdata[0]:,}")
        mx = pyr["Members"].abs().max()
        fig.update_layout(barmode="relative", legend_title_text="", yaxis_title="", xaxis_title="Household members",
                          height=380, xaxis=dict(
            tickvals=[-mx, -mx / 2, 0, mx / 2, mx],
            ticktext=[f"{int(mx):,}", f"{int(mx / 2):,}", "0", f"{int(mx / 2):,}", f"{int(mx):,}"]))
        st.plotly_chart(fig, width="stretch")

    c1, c2 = st.columns(2)
    with c1:
        if split in (None, "Head sex"):
            sx = p["Head sex"].value_counts()
            fig = go.Figure(go.Pie(labels=sx.index, values=sx.values, hole=0.6, sort=False,
                                   marker=dict(colors=[CHARCOAL if x == "Male" else RED for x in sx.index]),
                                   texttemplate="%{label}<br>%{percent:.0%}", textposition="outside"))
            fig.update_layout(title="Sex of household head", height=320, showlegend=False)
            st.plotly_chart(fig, width="stretch")
        else:
            share_chart(p, "Head sex", "Sex of household head (%)", ["Male", "Female"], split)
    with c2:
        share_chart(p, "Head age group", "Age of household head (%)",
                    ["Under 30", "30–44", "45–59", "60 and above"], split)
    c3, c4 = st.columns(2)
    with c3:
        share_chart(p, "A04_lbl" if "A04_lbl" in p else "A04", "Marital status of household head (%)",
                    split=split)
    with c4:
        share_chart(p, "Head education", "Education of household head (%)",
                    [g[2] for g in EDU_GROUPS], split)
    c5, c6 = st.columns(2)
    with c5:
        share_chart(p, "A06_lbl" if "A06_lbl" in p else "A06",
                    "Main activity of household head, past 12 months (%)", split=split)
    with c6:
        share_chart(p, "Respondent sex", "Sex of main respondent (%)", ["Male", "Female"], split)

    st.subheader("Profile by group")
    grp_label = st.selectbox("Group by", list(BREAKDOWNS.values()), key="prof_tab")
    grp = {v: k_ for k_, v in BREAKDOWNS.items()}[grp_label] + "_lbl"
    tbl = p.groupby(grp).apply(lambda x: pd.Series({
        "Households": len(x),
        "Female-headed %": pct(x["A02"] == "2", x["A02"].notna())[0],
        "Head age (mean)": mean_of(x["A03"])[0],
        "Elderly-headed %": pct(x["A03"] >= 60, x["A03"].notna())[0],
        "Household size (mean)": mean_of(x["A01_size"])[0],
        "Dependency ratio (mean)": mean_of(x["A01_dep_ratio"], 2)[0],
        "With youth 15–29 %": pct(x["A_youth_present"] == 1, x["A_youth_present"].notna())[0],
        "With disability %": pct(x["A_disability_hh"] == 1, x["A_disability_hh"].notna())[0],
    }), include_groups=False)
    st.dataframe(tbl, width="stretch")
    st.caption("Small groups (under ~10 households) give unstable figures.")

# ---------------------------------------------------------------- access
if SHOW_INDICATORS:
  with tabs["Access & crossings"]:
    st.caption(f"{len(hh)} households interviewed (sidebar filters applied).")
    rows = []
    for f, name in FACILITIES.items():
        e13, e08, e06 = hh[f"E13_{f}"], hh[f"E08_{f}"], hh[f"E06_{f}"]
        unreach = hh[f"E08_{f}_unreach"]
        rows.append({
            "Facility": name,
            "Year-round access % (G2)": pct(e13 == 0, e13.notna())[0],
            "Avg months cut off": mean_of(e13)[0],
            "Median minutes, dry season": median_of(e06)[0],
            "Median minutes, rainy season (O3)": median_of(e08)[0],
            "Cannot travel in rainy season %": pct(unreach == 1, unreach.notna())[0],
            "Households answering": int(e13.notna().sum()),
        })
    acc = pd.DataFrame(rows)

    c1, c2 = st.columns(2)
    c1.plotly_chart(px.bar(acc, x="Year-round access % (G2)", y="Facility", orientation="h",
                           text="Year-round access % (G2)", range_x=[0, 100],
                           title="G2 · Year-round access by facility",
                           color_discrete_sequence=[RED]), width="stretch")
    tt = acc.melt(id_vars="Facility", value_vars=["Median minutes, dry season",
                                                  "Median minutes, rainy season (O3)"],
                  var_name="Season", value_name="Minutes")
    tt["Season"] = tt["Season"].str.replace("Median minutes, ", "").str.replace(" (O3)", "")
    c2.plotly_chart(px.bar(tt, x="Minutes", y="Facility", color="Season", barmode="group",
                           orientation="h", title="O3 · Median one-way travel time",
                           color_discrete_map={"dry season": WARM_GREY, "rainy season": RED}),
                    width="stretch")
    st.dataframe(acc.set_index("Facility"), width="stretch")

    st.subheader("Crossing incidents in the past 12 months")
    inc_rows = []
    for v in INCIDENTS:
        label = questions.get(v, {}).get("label", v)
        short = label.split("“")[-1].split("”")[0] if "“" in label else v
        p, n = pct(hh[v] == "1", hh[v].isin(["0", "1"]))
        inc_rows.append({"Incident": short, "% of households": p, "n": n})
    inc = pd.DataFrame(inc_rows).sort_values("% of households")
    st.plotly_chart(px.bar(inc, x="% of households", y="Incident", orientation="h",
                           text="% of households", color_discrete_sequence=[DARK_RED],
                           title="Share of households where a member experienced…"),
                    width="stretch")


# ---------------------------------------------------------------- food security
if SHOW_INDICATORS:
  with tabs["Food security"]:
    st.caption(f"FCS groups use the standard cut-offs: Poor ≤ {FCS_LO}, Borderline {FCS_LO}.5–{FCS_HI}, Acceptable > {FCS_HI}.")
    k = st.columns(6)
    for i, (grp, label, definition, fn, unit) in enumerate([x for x in INDICATORS if x[0] == "Food security"]):
        val, n = fn(hh)
        k[i].metric(label, fmt(val, unit), help=f"{definition}. n = {n}")

    split_label = st.selectbox("Split by", ["(none)"] + list(BREAKDOWNS.values()), key="food_by")
    split = None if split_label == "(none)" else {v: k for k, v in BREAKDOWNS.items()}[split_label] + "_lbl"

    c1, c2 = st.columns(2)
    with c1:
        category_chart(hh, lambda d: pd.cut(d["G_FCS"], [-1, FCS_LO, FCS_HI, 200],
                                            labels=["Poor", "Borderline", "Acceptable"]).astype("object"),
                       ["Poor", "Borderline", "Acceptable"], [DARK_RED, LIGHT_RED, CHARCOAL],
                       "Food Consumption Score groups", split)
    with c2:
        category_chart(hh, lambda d: pd.cut(d["H_HHS"], [-1, 1, 3, 6],
                                            labels=["Little or none (0–1)", "Moderate (2–3)",
                                                    "Severe (4–6)"]).astype("object"),
                       ["Severe (4–6)", "Moderate (2–3)", "Little or none (0–1)"],
                       [DARK_RED, LIGHT_RED, CHARCOAL], "Household Hunger Scale", split)
    c3, c4 = st.columns(2)
    with c3:
        lcs = {0: "No coping", 1: "Stress", 2: "Crisis", 3: "Emergency"}
        category_chart(hh, lambda d: d["J_LCS_cat"].map(lcs),
                       ["Emergency", "Crisis", "Stress", "No coping"],
                       [DARK_RED, RED, LIGHT_RED, CHARCOAL], "Livelihood coping strategies (LCS)", split)
    with c4:
        category_chart(hh, lambda d: pd.cut(d["J_rCSI"], [-1, 3, 18, 100],
                                            labels=["Minimal (0–3)", "Stressed (4–18)",
                                                    "Crisis+ (19+)"]).astype("object"),
                       ["Crisis+ (19+)", "Stressed (4–18)", "Minimal (0–3)"],
                       [DARK_RED, LIGHT_RED, CHARCOAL], "Reduced Coping Strategies Index (rCSI)", split)

    if hh["I_MAHFP"].notna().any():
        st.plotly_chart(px.histogram(hh, x="I_MAHFP", nbins=13, range_x=[-0.5, 12.5],
                                     title="Months of adequate household food provisioning (MAHFP)",
                                     color_discrete_sequence=[RED],
                                     labels={"I_MAHFP": "Months with enough food"}),
                        width="stretch")

# ---------------------------------------------------------------- explore
with tabs["Explore a question"]:
    selects = {f"{q['label']}  [{name}]": name for name, q in questions.items()
               if q["type"].startswith("select_one") and name + "_lbl" in hh}
    if selects:
        qlabel = st.selectbox("Question", list(selects))
        qname = selects[qlabel]
        split = st.selectbox("Split by", ["(none)"] + list(BREAKDOWNS.values()), key="ex_by")
        sub = hh.dropna(subset=[qname])
        if split == "(none)":
            vc = sub[qname + "_lbl"].value_counts().reset_index()
            vc.columns = ["Answer", "n"]
            vc["%"] = (100 * vc["n"] / vc["n"].sum()).round(1)
            st.plotly_chart(px.bar(vc, x="n", y="Answer", orientation="h", text="%",
                                   color_discrete_sequence=[RED], title=qlabel), width="stretch")
        else:
            sv = {v: k for k, v in BREAKDOWNS.items()}[split] + "_lbl"
            ct = pd.crosstab(sub[sv], sub[qname + "_lbl"], normalize="index") * 100
            long = ct.round(1).reset_index().melt(id_vars=sv, var_name="Answer", value_name="%")
            st.plotly_chart(px.bar(long, x=sv, y="%", color="Answer", title=qlabel,
                                   labels={sv: split}), width="stretch")
        st.caption(f"Answered by {len(sub)} of {len(hh)} households.")
