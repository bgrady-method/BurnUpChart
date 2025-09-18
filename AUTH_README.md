# Authentication System

This document describes the password protection system implemented for the Jira Burndown Analysis application.

## Overview

The application now requires authentication before users can access any functionality. Authentication is implemented using:
- Session-based authentication with Streamlit's session state
- Simple password protection (configurable via environment variables)
- Automatic logout functionality

## Setup

### 1. Set Your Password

Edit your `.env` file and set a secure password:

```bash
APP_PASSWORD=your_secure_password_here
```

**Important**: Replace `your_secure_password_here` with a strong, unique password.

### 2. Dependencies

The authentication system requires the `bcrypt` package for secure password handling:

```bash
pip install bcrypt>=4.0.0
```

This is already included in `requirements.txt`.

## How It Works

### Authentication Flow

1. When users first access the application, they see a login form
2. Users enter the password configured in `APP_PASSWORD`
3. If the password is correct, they gain access to the full application
4. The authentication state is stored in the browser session
5. Users can logout using the "Logout" button in the sidebar

### Security Features

- **Session-based**: Authentication persists for the browser session
- **No password storage**: Passwords are not stored in session state after validation
- **Security warnings**: Warns users if the default password is still in use
- **Automatic protection**: All application functionality is protected behind authentication

### Components

- `auth.py`: Main authentication module with all auth functions
- `check_password()`: Main authentication function that shows login form
- `render_logout_button()`: Adds logout functionality to sidebar
- `logout()`: Clears authentication and redirects to login

## Usage

### For Users

1. Navigate to the application URL
2. Enter the configured password in the login form
3. Click "Login" to access the application
4. Use the "Logout" button in the sidebar when finished

### For Administrators

1. Set a strong password in the `.env` file:
   ```bash
   APP_PASSWORD=MySecurePassword123!
   ```

2. Share the password securely with authorized users

3. To change the password:
   - Update the `APP_PASSWORD` in `.env`
   - Restart the Streamlit application
   - All users will need to re-authenticate with the new password

## Security Considerations

### Password Strength
- Use a strong password with mixed case, numbers, and special characters
- Avoid common passwords or dictionary words
- Consider using a password manager to generate secure passwords

### Environment Security
- Keep your `.env` file secure and never commit it to version control
- Ensure only authorized personnel have access to the server/environment
- Consider additional security measures for production deployments

### Session Security
- Sessions are browser-based and will expire when the browser is closed
- Users on shared computers should always use the logout button
- The application does not implement session timeouts (consider adding for high-security environments)

## Limitations

This is a simple authentication system suitable for:
- Internal tools and dashboards
- Small teams with shared access
- Development and staging environments

For production systems with multiple users, consider implementing:
- Individual user accounts
- Role-based access control
- Session timeouts
- Multi-factor authentication
- Integration with enterprise authentication systems (LDAP, SSO, etc.)

## Troubleshooting

### Common Issues

**"Password incorrect" error with correct password**
- Ensure there are no extra spaces in the `.env` file
- Check that the `.env` file is in the correct directory
- Verify the application has been restarted after changing the password

**Security warning about default password**
- Change `APP_PASSWORD` in your `.env` file from `your_secure_password_here` to a real password
- Restart the application

**Authentication not working**
- Ensure `bcrypt` is installed: `pip install bcrypt>=4.0.0`
- Check that the `auth.py` file is in the correct location
- Verify all imports are working correctly

## API Reference

### Functions in `auth.py`

- `check_password() -> bool`: Main authentication check, returns True if authenticated
- `logout()`: Clears authentication state and forces re-login
- `render_logout_button()`: Renders logout button in sidebar (call this in your main app)
- `is_authenticated() -> bool`: Check if user is currently authenticated
- `hash_password(password: str) -> str`: Hash a password (for future use)
- `verify_password(password: str, hashed: str) -> bool`: Verify password against hash (for future use)

### Integration Example

```python
import auth

def main():
    # Authentication check - must be first
    if not auth.check_password():
        return
    
    # Your app code here
    st.title("My Protected App")
    
    # Add logout button
    auth.render_logout_button()
