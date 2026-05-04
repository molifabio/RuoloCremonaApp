import json
import math
import random
import unicodedata
from pathlib import Path

import folium
import requests
import streamlit as st
from streamlit_folium import st_folium

DATA_FILE = Path(__file__).parent / "poi_cremona.json"
NOMINATIM_BASE = "https://nominatim.openstreetmap.org"
OSRM_BASE = "https://router.project-osrm.org"


def load_poi() -> list[dict]:
    with DATA_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)

    required = {"name", "lat", "lon"}
    clean = []
    for item in data:
        if required.issubset(item.keys()):
            clean.append(
                {
                    "name": str(item["name"]),
                    "lat": float(item["lat"]),
                    "lon": float(item["lon"]),
                }
            )
    return clean


def build_poi_batches(poi_list: list[dict]) -> dict[str, list[dict]]:
    if not poi_list:
        return {
            "centro": [],
            "nord est": [],
            "nord ovest": [],
            "sud est": [],
            "sud ovest": [],
        }

    center_lat = sum(p["lat"] for p in poi_list) / len(poi_list)
    center_lon = sum(p["lon"] for p in poi_list) / len(poi_list)
    lat_span = max(p["lat"] for p in poi_list) - min(p["lat"] for p in poi_list)
    lon_span = max(p["lon"] for p in poi_list) - min(p["lon"] for p in poi_list)
    lat_margin = max(lat_span * 0.18, 0.0018)
    lon_margin = max(lon_span * 0.18, 0.0030)

    batches: dict[str, list[dict]] = {
        "centro": [],
        "nord est": [],
        "nord ovest": [],
        "sud est": [],
        "sud ovest": [],
    }

    for poi in poi_list:
        lat = poi["lat"]
        lon = poi["lon"]
        if abs(lat - center_lat) <= lat_margin and abs(lon - center_lon) <= lon_margin:
            batches["centro"].append(poi)
        elif lat >= center_lat and lon >= center_lon:
            batches["nord est"].append(poi)
        elif lat >= center_lat and lon < center_lon:
            batches["nord ovest"].append(poi)
        elif lat < center_lat and lon >= center_lon:
            batches["sud est"].append(poi)
        else:
            batches["sud ovest"].append(poi)

    return batches


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def find_nearest_poi(click_lat: float, click_lon: float, poi_list: list[dict]) -> tuple[dict, float]:
    best = None
    best_d = float("inf")
    for poi in poi_list:
        d = haversine_m(click_lat, click_lon, poi["lat"], poi["lon"])
        if d < best_d:
            best_d = d
            best = poi
    return best, best_d


def normalize_text(text: str) -> str:
    no_accents = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    lowered = no_accents.lower().strip()
    return " ".join(lowered.split())


@st.cache_data(show_spinner=False)
def nominatim_reverse_road(lat: float, lon: float) -> str | None:
    try:
        response = requests.get(
            f"{NOMINATIM_BASE}/reverse",
            params={
                "format": "jsonv2",
                "lat": lat,
                "lon": lon,
                "zoom": 17,
                "addressdetails": 1,
            },
            headers={"User-Agent": "cremona-quiz/1.0"},
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
        address = payload.get("address", {})
        return address.get("road")
    except requests.RequestException:
        return None


@st.cache_data(show_spinner=False)
def nominatim_search_street(street_name: str) -> dict | None:
    query = f"{street_name}, Cremona, Italia"
    try:
        response = requests.get(
            f"{NOMINATIM_BASE}/search",
            params={
                "format": "jsonv2",
                "q": query,
                "limit": 1,
                "polygon_geojson": 1,
                "addressdetails": 1,
            },
            headers={"User-Agent": "cremona-quiz/1.0"},
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
        if payload:
            return payload[0]
        return None
    except requests.RequestException:
        return None


@st.cache_data(show_spinner=False)
def infer_possible_roads_between(a: tuple[float, float], b: tuple[float, float]) -> list[str]:
    roads = set()
    samples = 7
    for i in range(samples):
        t = i / (samples - 1)
        lat = a[0] + (b[0] - a[0]) * t
        lon = a[1] + (b[1] - a[1]) * t
        road = nominatim_reverse_road(lat, lon)
        if road:
            roads.add(road)
    return sorted(roads)


@st.cache_data(show_spinner=False)
def get_reasonable_route(a: tuple[float, float], b: tuple[float, float]) -> dict | None:
    try:
        coords = f"{a[1]},{a[0]};{b[1]},{b[0]}"
        response = requests.get(
            f"{OSRM_BASE}/route/v1/driving/{coords}",
            params={
                "overview": "full",
                "geometries": "geojson",
                "steps": "true",
                "alternatives": "false",
            },
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
        routes = payload.get("routes", [])
        if not routes:
            return None

        route = routes[0]
        geometry = route.get("geometry", {})
        coordinates = geometry.get("coordinates", [])

        names = []
        seen = set()
        for leg in route.get("legs", []):
            for step in leg.get("steps", []):
                name = (step.get("name") or "").strip()
                if name and name not in seen:
                    names.append(name)
                    seen.add(name)

        return {
            "coordinates": coordinates,
            "distance_m": float(route.get("distance", 0.0)),
            "duration_s": float(route.get("duration", 0.0)),
            "street_names": names,
        }
    except requests.RequestException:
        return None


def add_route_polyline(fmap: folium.Map, route_data: dict) -> None:
    coordinates = route_data.get("coordinates", [])
    if not coordinates:
        return
    latlon = [[c[1], c[0]] for c in coordinates if len(c) == 2]
    if not latlon:
        return

    folium.PolyLine(
        locations=latlon,
        color="#ff7f0e",
        weight=6,
        opacity=0.9,
        tooltip="Percorso ragionevole",
    ).add_to(fmap)


def parse_guessed_streets(text: str) -> list[str]:
    chunks = []
    for sep in [";", "\n"]:
        text = text.replace(sep, ",")
    for part in text.split(","):
        name = part.strip()
        if name:
            chunks.append(name)
    return chunks


def make_base_map(
    poi_list: list[dict],
    show_labels: bool = False,
    tiles: str = "cartodbpositron",
    poi_highlights: dict[str, str] | None = None,
) -> folium.Map:
    center_lat = sum(p["lat"] for p in poi_list) / len(poi_list)
    center_lon = sum(p["lon"] for p in poi_list) / len(poi_list)
    fmap = folium.Map(location=[center_lat, center_lon], zoom_start=14, tiles=tiles)
    poi_highlights = poi_highlights or {}

    for idx, poi in enumerate(poi_list, start=1):
        tooltip = poi["name"] if show_labels else f"Punto #{idx}"
        marker_color = poi_highlights.get(poi["name"], "#1f77b4")
        folium.CircleMarker(
            location=[poi["lat"], poi["lon"]],
            radius=7,
            color=marker_color,
            fill=True,
            fill_opacity=0.65,
            weight=2,
            tooltip=tooltip,
        ).add_to(fmap)
    return fmap


def add_highlight_marker(fmap: folium.Map, poi: dict, color: str, label: str) -> None:
    folium.Marker(
        location=[poi["lat"], poi["lon"]],
        tooltip=label,
        icon=folium.Icon(color=color, icon="info-sign"),
    ).add_to(fmap)


def add_street_geometry(fmap: folium.Map, street_result: dict) -> None:
    geo = street_result.get("geojson")
    if not geo:
        return
    folium.GeoJson(
        geo,
        style_function=lambda _x: {
            "color": "#d62728",
            "weight": 6,
            "opacity": 0.85,
            "fillOpacity": 0.15,
        },
        name="Strada inserita",
    ).add_to(fmap)


def init_mode1_state(poi_list: list[dict], batch_map: dict[str, list[dict]], pool_signature: tuple[str, ...]) -> None:
    if st.session_state.get("m1_pool_signature") != pool_signature:
        reset_mode1(poi_list, batch_map, pool_signature)

    if "m1_order" not in st.session_state:
        reset_mode1(poi_list, batch_map, pool_signature)


def reset_mode1(
    poi_list: list[dict],
    batch_map: dict[str, list[dict]],
    pool_signature: tuple[str, ...],
) -> None:
    selected_names = [
        poi["name"]
        for batch_name in pool_signature
        for poi in batch_map.get(batch_name, [])
    ]

    k = min(10, len(selected_names))
    st.session_state.m1_pool_signature = pool_signature
    st.session_state.m1_order = random.sample(selected_names, k=k) if k else []
    st.session_state.m1_index = 0
    st.session_state.m1_results = []
    st.session_state.m1_pending = None
    st.session_state.m1_feedback = None
    st.session_state.m1_last_click = None


def init_mode2_state(poi_list: list[dict]) -> None:
    if "m2_rounds" not in st.session_state:
        rounds = []
        for _ in range(5):
            a, b = random.sample(poi_list, k=2)
            rounds.append((a["name"], b["name"]))
        st.session_state.m2_rounds = rounds
        st.session_state.m2_index = 0
        st.session_state.m2_results = []
        st.session_state.m2_input = ""


def reset_mode2(poi_list: list[dict]) -> None:
    rounds = []
    for _ in range(5):
        a, b = random.sample(poi_list, k=2)
        rounds.append((a["name"], b["name"]))
    st.session_state.m2_rounds = rounds
    st.session_state.m2_index = 0
    st.session_state.m2_results = []
    st.session_state.m2_input = ""


def get_poi_by_name(name: str, poi_list: list[dict]) -> dict:
    for poi in poi_list:
        if poi["name"] == name:
            return poi
    raise ValueError(f"POI non trovato: {name}")


def run_mode1(
    poi_list: list[dict],
    snap_distance: int,
    map_tiles: str,
    map_width: int,
    map_height: int,
    batch_map: dict[str, list[dict]],
    pool_signature: tuple[str, ...],
) -> None:
    init_mode1_state(poi_list, batch_map, pool_signature)

    total = len(st.session_state.m1_order)
    idx = st.session_state.m1_index

    st.subheader("Modalita 1: 10 punti di interesse")
    st.caption("Ti viene mostrato un punto per volta. Clicca sulla mappa, conferma, poi vai avanti.")

    if total == 0:
        st.error("La batch selezionata non contiene punti di interesse.")
        return

    if idx >= total:
        correct = sum(1 for r in st.session_state.m1_results if r["ok"])
        st.success(f"Quiz completato: {correct}/{total} punti corretti")
        st.write("Resoconto finale")
        for i, res in enumerate(st.session_state.m1_results, start=1):
            icon = "OK" if res["ok"] else "NO"
            st.write(
                f"{i}. {icon} - target: {res['target']} | scelto: {res['picked']} | distanza click: {res['dist']:.1f} m"
            )
        if st.button("Ricomincia quiz 10 POI", use_container_width=True):
            reset_mode1(poi_list, batch_map, pool_signature)
            st.rerun()
        return

    target_name = st.session_state.m1_order[idx]
    st.markdown(f"**Domanda {idx + 1}/{total}** - Trova: **{target_name}**")

    feedback = st.session_state.m1_feedback
    highlight_colors: dict[str, str] = {}
    if feedback:
        if feedback["ok"]:
            highlight_colors[target_name] = "#2ca02c"
        else:
            highlight_colors[target_name] = "#d62728"
            highlight_colors[feedback["picked"]] = "#ff7f0e"

    if st.session_state.m1_pending and not feedback:
        st.info("Hai selezionato un punto. Premi Conferma risposta per verificare.")
    elif feedback:
        if feedback["ok"]:
            st.success(f"Corretto: {feedback['target']}")
        else:
            st.error(f"Sbagliato. Hai selezionato: {feedback["picked"]}")

    col_map, col_info = st.columns([2, 1], vertical_alignment="top")

    with col_map:
        fmap = make_base_map(
            poi_list,
            show_labels=False,
            tiles=map_tiles,
            poi_highlights=highlight_colors,
        )
        out = st_folium(fmap, width=map_width, height=map_height)
        clicked = out.get("last_clicked")

        if clicked and not feedback:
            signature = (round(clicked["lat"], 6), round(clicked["lng"], 6), idx)
            if signature != st.session_state.m1_last_click:
                nearest, dist_m = find_nearest_poi(clicked["lat"], clicked["lng"], poi_list)
                st.session_state.m1_last_click = signature

                if dist_m <= snap_distance:
                    st.session_state.m1_pending = {
                        "name": nearest["name"],
                        "dist": dist_m,
                    }
                else:
                    st.session_state.m1_pending = None
                    st.warning(
                        f"Click troppo lontano da un punto predisposto ({dist_m:.1f} m). Riprova piu vicino."
                    )

    with col_info:
        st.write("Controlli")
        if not feedback:
            if st.session_state.m1_pending:
                st.write("Hai un punto selezionato sulla mappa.")
            else:
                st.write("Nessun punto selezionato")

            if st.button("Conferma risposta", disabled=st.session_state.m1_pending is None, use_container_width=True):
                picked = st.session_state.m1_pending["name"]
                dist = st.session_state.m1_pending["dist"]
                ok = picked == target_name
                st.session_state.m1_results.append(
                    {
                        "target": target_name,
                        "picked": picked,
                        "dist": dist,
                        "ok": ok,
                    }
                )
                st.session_state.m1_feedback = {
                    "target": target_name,
                    "picked": picked,
                    "dist": dist,
                    "ok": ok,
                }
                st.session_state.m1_pending = None
                st.session_state.m1_last_click = None
                st.rerun()
        else:
            if st.button("Avanti", use_container_width=True):
                st.session_state.m1_index += 1
                st.session_state.m1_pending = None
                st.session_state.m1_feedback = None
                st.session_state.m1_last_click = None
                st.rerun()

        if st.button("Reset quiz 10 POI", use_container_width=True):
            reset_mode1(poi_list, batch_map, pool_signature)
            st.rerun()


def run_mode2(poi_list: list[dict], map_tiles: str, map_width: int, map_height: int) -> None:
    init_mode2_state(poi_list)
    idx = st.session_state.m2_index
    total = len(st.session_state.m2_rounds)

    st.subheader("Modalita 2: 5 percorsi")
    st.caption(
        "Per ogni round vedi 2 POI evidenziati e una polilinea di percorso ragionevole (driving). Tu devi indicare le vie attraversate."
    )

    if idx >= total:
        plausible = sum(1 for r in st.session_state.m2_results if r["plausible"])
        st.success(f"Sessione percorsi completata: {plausible}/{total} tentativi plausibili")
        st.write("Resoconto")
        for i, res in enumerate(st.session_state.m2_results, start=1):
            mark = "OK" if res["plausible"] else "NO"
            st.write(
                f"{i}. {mark} - {res['start']} -> {res['end']} | vie indicate: {res['streets_text']}"
            )
        if st.button("Ricomincia percorsi", use_container_width=True):
            reset_mode2(poi_list)
            st.rerun()
        return

    start_name, end_name = st.session_state.m2_rounds[idx]
    start_poi = get_poi_by_name(start_name, poi_list)
    end_poi = get_poi_by_name(end_name, poi_list)
    route_data = get_reasonable_route(
        (start_poi["lat"], start_poi["lon"]),
        (end_poi["lat"], end_poi["lon"]),
    )

    st.markdown(f"**Round {idx + 1}/{total}** - collega **{start_name}** con **{end_name}**")

    col_map, col_actions = st.columns([2, 1], vertical_alignment="top")
    with col_map:
        fmap = make_base_map(poi_list, show_labels=False, tiles=map_tiles)
        add_highlight_marker(fmap, start_poi, "green", f"Partenza: {start_name}")
        add_highlight_marker(fmap, end_poi, "red", f"Arrivo: {end_name}")

        if route_data:
            add_route_polyline(fmap, route_data)

        st_folium(fmap, width=map_width, height=map_height)

    with col_actions:
        st.write("Inserisci le vie che pensi compongano il percorso")
        if route_data:
            st.caption(
                f"Lunghezza percorso: {route_data['distance_m'] / 1000:.2f} km | tempo stimato: {route_data['duration_s'] / 60:.0f} min"
            )

        streets_text = st.text_area(
            "Vie (separate da virgola, punto e virgola o invio)",
            value=st.session_state.m2_input,
            placeholder="es. Corso Garibaldi, Via Mercatello, Piazza del Comune",
            height=120,
        )

        if st.button("Conferma tentativo", use_container_width=True):
            st.session_state.m2_input = streets_text
            guessed_streets = parse_guessed_streets(streets_text)
            if not guessed_streets:
                st.warning("Inserisci almeno una via")
            else:
                expected_streets = route_data["street_names"] if route_data else []
                guessed_norm = {normalize_text(s) for s in guessed_streets}
                expected_norm = {normalize_text(s) for s in expected_streets}
                hits = guessed_norm.intersection(expected_norm)
                coverage = len(hits) / max(1, len(guessed_norm))
                plausible = len(hits) >= 1 and coverage >= 0.4

                st.session_state.m2_results.append(
                    {
                        "start": start_name,
                        "end": end_name,
                        "streets_text": streets_text,
                        "plausible": plausible,
                    }
                )

                if plausible:
                    st.success("Buon tentativo: hai indicato almeno una via del percorso")
                else:
                    st.error("Tentativo non compatibile con le vie principali del percorso mostrato")

                if expected_streets:
                    st.write("Vie del percorso (riferimento):")
                    for name in expected_streets:
                        st.write(f"- {name}")

                st.session_state.m2_index += 1
                st.session_state.m2_input = ""

        if st.button("Reset percorsi", use_container_width=True):
            reset_mode2(poi_list)
            st.rerun()


def run_mode3(poi_list: list[dict], map_tiles: str, map_width: int, map_height: int) -> None:
    st.subheader("Modalita 3: Apprendimento")
    st.caption("Muovi il mouse sui punti per vederne il nome.")

    fmap = make_base_map(poi_list, show_labels=True, tiles=map_tiles)
    st_folium(fmap, width=map_width, height=map_height)


def main() -> None:
    st.set_page_config(page_title="Quiz Mappa Cremona", layout="wide")
    st.title("Allenamento punti di interesse - Cremona")

    poi_list = load_poi()
    if len(poi_list) < 10:
        st.error("Servono almeno 10 punti di interesse nel file poi_cremona.json")
        st.stop()

    batch_map = build_poi_batches(poi_list)
    batch_labels = ["Tutte le batch", "centro", "nord est", "nord ovest", "sud est", "sud ovest"]

    with st.sidebar:
        st.header("Impostazioni")
        mode = st.radio(
            "Modalita",
            ["Quiz 10 POI", "Percorsi 5 round", "Apprendimento"],
            index=0,
        )
        batch_choice = st.radio(
            "Batch POI per la modalità 1",
            batch_labels,
            index=0,
            help="Scegli una sola batch oppure tutte le batch per pescare i punti della modalità 1.",
        )
        map_style = st.radio(
            "Stile mappa",
            ["Bianca", "Colorata"],
            index=0,
            help="Bianca usa uno sfondo pulito; Colorata mostra la cartografia standard di OpenStreetMap.",
        )
        snap_distance = st.slider("Aggancio click ai POI (metri)", 20, 250, 90, 10)
        map_width = st.slider("Larghezza mappa", 900, 1400, 1180, 50)
        map_height = st.slider("Altezza mappa", 500, 900, 720, 20)

    map_tiles = "cartodbpositron" if map_style == "Bianca" else "OpenStreetMap"

    selected_batches = [batch_choice] if batch_choice != "Tutte le batch" else ["centro", "nord est", "nord ovest", "sud est", "sud ovest"]
    selected_poi_names = [
        poi["name"]
        for batch_name in selected_batches
        for poi in batch_map.get(batch_name, [])
    ]
    pool_signature = tuple(selected_batches)

    if mode == "Quiz 10 POI":
        run_mode1(poi_list, snap_distance, map_tiles, map_width, map_height, batch_map, pool_signature)
    elif mode == "Percorsi 5 round":
        run_mode2(poi_list, map_tiles, map_width, map_height)
    elif mode == "Apprendimento":
        run_mode3(poi_list, map_tiles, map_width, map_height)


if __name__ == "__main__":
    main()
