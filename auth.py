"""
Authentication module for the Streamlit application.
Provides simple password-based authentication using session state.
"""

import streamlit as st
import bcrypt
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash."""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def check_password() -> bool:
    """
    Returns True if the user has entered the correct password.
    Uses session state to remember authentication.
    """

    # Return True if password is validated
    if st.session_state.get("password_correct", False):
        return True

    # Show login form
    st.markdown("# 🔐 Authentication Required")
    st.markdown("Please enter the application password to access the Jira Burndown Analysis tool.")
    
    # Create login form
    with st.form("login_form"):
        password = st.text_input(
            "Password", 
            type="password",
            help="Enter the application password configured in your environment"
        )
        submitted = st.form_submit_button("Login")
        
        if submitted:
            app_password = os.getenv('APP_PASSWORD', 'your_secure_password_here')
            
            if password == app_password:
                st.session_state["password_correct"] = True
                st.rerun()  # Refresh to show the app
            else:
                st.session_state["password_correct"] = False
                st.error("😞 Password incorrect. Please try again.")
    
    # Show error if password was wrong in previous attempt
    if st.session_state.get("password_correct", True) is False and not submitted:
        st.error("😞 Password incorrect. Please try again.")
    
    # Show warning if default password is being used
    app_password = os.getenv('APP_PASSWORD', 'your_secure_password_here')
    if app_password == 'your_secure_password_here':
        st.warning("⚠️ **Security Warning**: Default password detected. Please update APP_PASSWORD in your .env file.")
        
    return False

def logout():
    """Clear the authentication state."""
    if "password_correct" in st.session_state:
        del st.session_state["password_correct"]
    st.rerun()

def render_logout_button():
    """Render logout button in sidebar if authenticated."""
    if st.session_state.get("password_correct", False):
        with st.sidebar:
            st.divider()
            if st.button("🚪 Logout", key="logout_btn", help="Log out of the application"):
                logout()

def is_authenticated() -> bool:
    """Check if user is currently authenticated."""
    return st.session_state.get("password_correct", False)
