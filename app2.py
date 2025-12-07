import re
import requests
import streamlit as st
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import numpy as np
import pandas as pd
from PIL import Image


# ---------------------------------------------------------
# Helper Functions (SAFE)
# ---------------------------------------------------------

def extract_colors_from_css(css_text):
    """Extract valid HEX and RGB colors from CSS safely."""
    raw_hex = re.findall(r'#[0-9A-Fa-f]{1,6}', css_text)
    rgb_colors = re.findall(r'rgb\((.*?)\)', css_text)

    valid_hex = []

    # Validate HEX values (#RGB or #RRGGBB)
    for h in raw_hex:
        h = h.strip()
        if len(h) in (4, 7):
            valid_hex.append(h)

    # Convert rgb() → hex
    for rgb in rgb_colors:
        try:
            r, g, b = map(int, rgb.split(','))
            hex_color = '#{:02x}{:02x}{:02x}'.format(r, g, b)
            valid_hex.append(hex_color)
        except:
            pass

    return list(set(valid_hex))


def get_css_links(soup, base_url):
    """Return external CSS links."""
    css_links = []
    for link in soup.find_all("link", rel="stylesheet"):
        href = link.get("href")
        if href:
            css_links.append(urljoin(base_url, href))
    return css_links


def relative_luminance(hex_color):
    """Compute luminance safely (0–1)."""
    hex_color = hex_color.lstrip("#")

    if len(hex_color) not in (3, 6):
        return 0.0

    if len(hex_color) == 3:
        hex_color = "".join([c * 2 for c in hex_color])

    try:
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
    except ValueError:
        return 0.0

    rgb = np.array([r / 255, g / 255, b / 255])
    rgb = np.where(rgb <= 0.03928, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)

    return float(0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2])


def estimate_carbon_intensity(hex_color):
    """AI-weighted carbon intensity based on luminance + blue component."""
    luminance = relative_luminance(hex_color)

    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join([c * 2 for c in hex_color])

    try:
        b = int(hex_color[-2:], 16) / 255
    except:
        b = 0

    score = (
        luminance * 0.65 +
        b * 0.25 +
        0.10
    )

    return min(score, 1)


# ---------------------------------------------------------
# WEBSITE COLOR CARBON CALCULATOR
# ---------------------------------------------------------

def calculate_digital_carbon(url):
    try:
        response = requests.get(url)
    except:
        return None, None, "Failed to fetch the website."

    soup = BeautifulSoup(response.text, "html.parser")

    inline_css = " ".join([tag.get("style", "") for tag in soup.find_all()])
    colors = extract_colors_from_css(inline_css)

    css_links = get_css_links(soup, url)
    for css_url in css_links:
        try:
            css = requests.get(css_url).text
            colors += extract_colors_from_css(css)
        except:
            pass

    colors = list(set(colors))

    if not colors:
        return None, None, "No valid CSS colors found."

    data = []
    for c in colors:
        score = estimate_carbon_intensity(c)
        data.append({"color": c, "carbon_intensity": score})

    df = pd.DataFrame(data)
    total_score = df["carbon_intensity"].mean() * 100

    return df, total_score, None


# ---------------------------------------------------------
# IMAGE COLOR CARBON CALCULATOR (NEW)
# ---------------------------------------------------------

def extract_colors_from_image(image, max_colors=12):
    """Extract dominant colors from the image using quantization."""
    img = image.resize((200, 200))  # speed optimization
    img = img.convert("RGB")

    # quantize to limited color palette
    quantized = img.quantize(colors=max_colors, method=2)
    palette = quantized.getpalette()
    color_counts = sorted(quantized.getcolors(), reverse=True)

    colors = []
    for count, index in color_counts:
        r = palette[index * 3]
        g = palette[index * 3 + 1]
        b = palette[index * 3 + 2]
        colors.append('#{:02x}{:02x}{:02x}'.format(r, g, b))

    return list(set(colors))


def calculate_image_carbon(image):
    colors = extract_colors_from_image(image)

    data = []
    for c in colors:
        score = estimate_carbon_intensity(c)
        data.append({"color": c, "carbon_intensity": score})

    df = pd.DataFrame(data)
    total_score = df["carbon_intensity"].mean() * 100

    return df, total_score


# ---------------------------------------------------------
# STREAMLIT UI
# ---------------------------------------------------------

st.set_page_config(
    page_title="Digital Color Carbon Estimator",
    page_icon="🌿",
    layout="wide"
)

st.title("Digital Carbon Emission Calculator")
st.write("Analyze carbon intensity from **websites** or **uploaded images**.")

# ---------------------------------------------------------
# USER INPUTS
# ---------------------------------------------------------

tab1, tab2 = st.tabs(["🌐 Website Analysis", "🖼️ Image Analysis"])

# ---------------------------------------------------------
# WEBSITE CARBON SCORE
# ---------------------------------------------------------

with tab1:
    url = st.text_input("Enter website URL", placeholder="https://example.com")

    if st.button("Calculate Website Carbon Score"):
        with st.spinner("Analyzing website colors…"):
            df, score, error = calculate_digital_carbon(url)

        if error:
            st.error(error)
        else:
            st.success("Website analysis complete!")

            st.metric("Digital Carbon Emission Score (%)", f"{score:.1f}%")

            if score < 25:
                st.success("🟢 Very Low Carbon")
            elif score < 50:
                st.info("🟡 Moderate")
            elif score < 75:
                st.warning("🟠 High")
            else:
                st.error("🔴 Very High")

            st.dataframe(df)
            st.bar_chart(df.set_index("color"))

            st.subheader("Color Swatches")
            cols = st.columns(6)
            for i, row in df.iterrows():
                with cols[i % 6]:
                    st.markdown(
                        f"""
                        <div style='width:100%; height:50px; background:{row['color']};
                        border-radius:4px;'></div>
                        <p style='font-size:12px; text-align:center'>{row['color']}<br>
                        {row['carbon_intensity']:.2f}</p>
                        """,
                        unsafe_allow_html=True
                    )


# ---------------------------------------------------------
# IMAGE CARBON SCORE (NEW FEATURE)
# ---------------------------------------------------------

with tab2:
    uploaded_image = st.file_uploader("Upload an image", type=["jpg", "png", "jpeg"])

    if uploaded_image:
        image = Image.open(uploaded_image)
        st.image(image, caption="Uploaded Image", use_column_width=True)

        if st.button("Calculate Image Carbon Emission Score"):
            with st.spinner("Extracting colors and calculating carbon…"):
                df, score = calculate_image_carbon(image)

            st.success("Image analysis complete!")
            st.metric("Image Carbon Emission Score (%)", f"{score:.1f}%")

            if score < 25:
                st.success("🟢 Very Low Carbon")
            elif score < 50:
                st.info("🟡 Moderate")
            elif score < 75:
                st.warning("🟠 High")
            else:
                st.error("🔴 Very High")

            st.dataframe(df)
            st.bar_chart(df.set_index("color"))

            st.subheader("Color Swatches")
            cols = st.columns(6)
            for i, row in df.iterrows():
                with cols[i % 6]:
                    st.markdown(
                        f"""
                        <div style='width:100%; height:50px; background:{row['color']};
                        border-radius:4px;'></div>
                        <p style='font-size:12px; text-align:center'>{row['color']}<br>
                        {row['carbon_intensity']:.2f}</p>
                        """,
                        unsafe_allow_html=True
                    )

