# Google OAuth Configuration Guide

This guide will help you configure Google OAuth correctly for your Patient Entity Management System.

## Prerequisites

- A Google Cloud Platform (GCP) account
- Access to Google Cloud Console

## Step-by-Step Configuration

### 1. Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click on the project dropdown at the top
3. Click "New Project"
4. Enter a project name (e.g., "Patient Entity Management")
5. Click "Create"

### 2. Enable Google Identity Services API

1. In the Google Cloud Console, navigate to **APIs & Services** > **Library**
2. Search for "Google Identity Services API"
3. Click on it and click **Enable**

### 3. Configure OAuth Consent Screen

1. Navigate to **APIs & Services** > **OAuth consent screen**
2. Choose **External** (unless you have a Google Workspace account)
3. Click **Create**
4. Fill in the required information:
   - **App name**: Patient Entity Management System
   - **User support email**: Your email address
   - **Developer contact information**: Your email address
5. Click **Save and Continue**
6. On the **Scopes** page, click **Save and Continue** (no additional scopes needed for basic email)
7. On the **Test users** page, add test users if needed, then click **Save and Continue**
8. Review and click **Back to Dashboard**

### 4. Create OAuth 2.0 Client ID

1. Navigate to **APIs & Services** > **Credentials**
2. Click **Create Credentials** > **OAuth client ID**
3. If prompted, configure the OAuth consent screen first (see step 3)
4. Select **Web application** as the application type
5. Give it a name (e.g., "Patient Entity Web Client")
6. Configure **Authorized JavaScript origins**:

   ```
   http://localhost:5173
   http://localhost:3000
   ```

   (Add your production domain when deploying)

7. Configure **Authorized redirect URIs**:

   ```
   http://localhost:5173
   http://localhost:3000
   http://localhost:8000/auth/callback
   ```

   (Add your production callback URLs when deploying)

8. Click **Create**
9. **IMPORTANT**: Copy the **Client ID** - you'll need this for both frontend and backend

### 5. Configure Environment Variables

#### Frontend (.env file in `frontend/` directory)

Create a `.env` file in the `frontend/` directory:

```env
VITE_GOOGLE_CLIENT_ID=your-client-id-here.apps.googleusercontent.com
```

#### Backend (.env file or environment variables)

Set the following environment variable:

```env
GOOGLE_CLIENT_ID=your-client-id-here.apps.googleusercontent.com
JWT_SECRET=your-secret-key-change-in-production
ACCESS_TOKEN_MINUTES=15
REFRESH_TOKEN_DAYS=7
COOKIE_SECURE=false  # Set to true in production with HTTPS
COOKIE_DOMAIN=       # Leave empty for localhost, set domain in production
```

### 6. Verify Configuration

#### Frontend Configuration Check

1. Ensure `VITE_GOOGLE_CLIENT_ID` is set in your `.env` file
2. Restart your Vite dev server after adding the environment variable
3. The frontend should load Google Identity Services script automatically

#### Backend Configuration Check

1. Ensure `GOOGLE_CLIENT_ID` matches the frontend client ID exactly
2. Verify CORS is configured to allow your frontend origin:
   ```python
   allow_origins=["http://localhost:3000", "http://localhost:5173"]
   allow_credentials=True
   ```

### 7. Testing the OAuth Flow

1. **Start the backend server**:

   ```bash
   cd backend
   python -m uvicorn main:app --reload
   ```

2. **Start the frontend server**:

   ```bash
   cd frontend
   npm run dev
   ```

3. **Test the flow**:
   - Navigate to `http://localhost:5173` (or your frontend port)
   - You should be redirected to `/login` if not authenticated
   - Click the Google Sign-In button
   - Complete Google authentication
   - You should be redirected to `/patients` after successful authentication

### 8. Common Issues and Solutions

#### Issue: "VITE_GOOGLE_CLIENT_ID is not configured"

**Solution**: Create `.env` file in `frontend/` directory with `VITE_GOOGLE_CLIENT_ID`

#### Issue: "Invalid Google token" error

**Solution**:

- Verify `GOOGLE_CLIENT_ID` in backend matches frontend exactly
- Ensure the client ID is correct in Google Cloud Console
- Check that the OAuth consent screen is properly configured

#### Issue: CORS errors

**Solution**:

- Verify backend CORS settings include your frontend origin
- Ensure `allow_credentials=True` is set
- Check that frontend requests include `withCredentials: true`

#### Issue: Cookies not being set

**Solution**:

- Verify `withCredentials: true` is set in axios requests
- Check CORS configuration allows credentials
- Ensure cookie domain is correctly configured (empty for localhost)

#### Issue: "This email is not authorized"

**Solution**:

- Add the email to the allow-list via the Master Dashboard
- Or directly add it to the database `allow_listed_emails` table

### 9. Production Deployment Checklist

When deploying to production:

1. **Update Google Cloud Console**:

   - Add production domain to Authorized JavaScript origins
   - Add production callback URLs to Authorized redirect URIs
   - Update OAuth consent screen with production app details

2. **Update Environment Variables**:

   - Set `COOKIE_SECURE=true` (requires HTTPS)
   - Set `COOKIE_DOMAIN` to your production domain
   - Use strong `JWT_SECRET` (generate a secure random string)

3. **Update CORS**:

   - Add production frontend URL to `allow_origins`
   - Keep `allow_credentials=True`

4. **Security**:
   - Never commit `.env` files to version control
   - Use environment variables or secrets management in production
   - Enable HTTPS for production

## OAuth Flow Summary

1. User clicks "Sign in with Google" on frontend
2. Google Identity Services prompts user to select account
3. Google returns ID token to frontend callback
4. Frontend sends ID token to backend `/auth/login/google`
5. Backend verifies ID token with Google
6. Backend checks if email is in allow-list
7. Backend creates user session and sets HTTP-only cookies
8. Frontend verifies session with `/auth/me`
9. Frontend redirects to dashboard

## Security Notes

- ID tokens are verified server-side using Google's verification
- Sessions are stored in HTTP-only cookies (not accessible via JavaScript)
- Access tokens expire after 15 minutes (configurable)
- Refresh tokens expire after 7 days (configurable)
- All API requests require valid session cookies
- Master login uses separate email/password authentication




