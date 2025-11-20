# Backend Setup Instructions

## Issue with Python 3.13

If you're using Python 3.13 and encountering build errors for pydantic-core, you have two options:

### Option 1: Use Python 3.11 or 3.12 (Recommended)

The easiest solution is to use Python 3.11 or 3.12 which has better package support:

1. Install Python 3.11 or 3.12 from python.org
2. Create a new virtual environment:

```bash
python3.11 -m venv venv  # or python3.12
```

3. Activate and install:

```bash
venv\Scripts\activate
pip install -r requirements.txt
```

### Option 2: Install Visual Studio Build Tools (For Python 3.13)

If you must use Python 3.13, you need to install C++ build tools:

1. Download and install **Visual Studio Build Tools** or **Visual Studio 2022 Community**
2. During installation, select "Desktop development with C++" workload
3. Run the installation
4. Try installing requirements again:

```bash
pip install -r requirements.txt
```

### Option 3: Use Simplified Versions (Quick Workaround)

If you want to avoid build complications entirely, use these simplified versions:

```bash
pip install fastapi uvicorn sqlalchemy pydantic-settings python-multipart
```

Then update your code to use `BaseModel` from `pydantic` directly.

### Verification

After installation, verify everything works:

```bash
python -c "import fastapi; import pydantic; import sqlalchemy; print('All packages installed successfully!')"
```

Then start the server:

```bash
python main.py
```
