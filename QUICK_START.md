# Quick Start Guide - OAuth Implementation

## Immediate Next Steps

### 1. Set Up Google OAuth (5 minutes)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable "Google Identity Services API"
4. Go to **APIs & Services** > **Credentials**
5. Click **Create Credentials** > **OAuth client ID**
6. Select **Web application**
7. Add authorized origins:
   - `http://localhost:5173`
   - `http://localhost:3000`
8. Copy the **Client ID** (looks like: `xxxxx.apps.googleusercontent.com`)

### 2. Configure Environment Variables

#### Frontend

Create `frontend/.env` file:

```env
VITE_GOOGLE_CLIENT_ID=your-client-id-here.apps.googleusercontent.com
```

#### Backend

Set environment variables (or create `.env` file):

```env
GOOGLE_CLIENT_ID=your-client-id-here.apps.googleusercontent.com
JWT_SECRET=change-me-to-secure-random-string
```

### 3. Restart Servers

After setting environment variables:

```bash
# Backend
cd backend
python -m uvicorn main:app --reload

# Frontend (in new terminal)
cd frontend
npm run dev
```

### 4. Test the Flow

1. Open `http://localhost:5173` (or your frontend port)
2. You should be redirected to `/login`
3. Click "Sign in with Google"
4. Complete Google authentication
5. You should be redirected to `/patients` dashboard

### 5. Add Users to Allow-List

1. Click "Master Login" in navbar
2. Login with:
   - Email: `aayush22011@iiitd.ac.in`
   - Password: `123456`
3. Go to Master Dashboard
4. Add email addresses to allow-list

## What Changed?

- ✅ Home page now redirects to login if not authenticated
- ✅ Google OAuth flow verifies session before redirecting
- ✅ Master login accessible via navbar button
- ✅ All routes are protected
- ✅ Session management via AuthContext
- ✅ Automatic logout on 401 errors

## Need Help?

- See `GOOGLE_OAUTH_SETUP.md` for detailed Google Cloud Console setup
- See `OAUTH_FIXES_SUMMARY.md` for complete change documentation




