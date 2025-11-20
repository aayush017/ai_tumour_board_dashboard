# Patient Entity Management System

A comprehensive web-based system for creating, managing, and reusing patient entities based on a structured schema for medical case management.

## Features

- **CRUD Operations**: Full Create, Read, Update, Delete functionality for patient entities
- **Structured Data Schema**: Complete patient information storage including:
  - Demographics
  - Clinical summaries
  - Lab data with timeline tracking
  - Imaging results
  - Treatment history
  - Tumor board notes
- **Visual Lab Data Timeline**: Interactive charts for tracking lab values over time
- **Modern UI**: Clean, responsive interface built with React and Tailwind CSS
- **RESTful API**: FastAPI backend with SQLite database
- **On-demand AI Specialist Summaries**: Trigger GPT-4 powered diagnoses and plans per specialist

## Tech Stack

### Backend

- FastAPI
- SQLAlchemy
- SQLite
- Pydantic

### Frontend

- React
- Vite
- Tailwind CSS
- React Router
- Axios
- Recharts

## Project Structure

```
patient entity/
├── backend/
│   ├── main.py              # FastAPI application
│   ├── models.py            # Database models
│   ├── schemas.py           # Pydantic schemas
│   ├── database.py          # Database configuration
│   └── requirements.txt     # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── components/      # React components
│   │   ├── pages/           # Page components
│   │   └── utils/           # Utility functions
│   └── package.json         # Node dependencies
└── README.md
```

## Installation

### Backend Setup

1. Navigate to the backend directory:

```bash
cd backend
```

2. Create a virtual environment (recommended):

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Run the backend server:

```bash
python main.py
```

The API will be available at `http://localhost:8000`

5. Configure OpenAI access for AI specialist summaries:

```bash
# PowerShell
setx OPENAI_API_KEY "sk-your-key"

# Optional: override the default model (defaults to gpt-4o-mini)
setx OPENAI_MODEL "gpt-4o"
```

Restart your terminal after setting the variables so the backend picks them up.

### Frontend Setup

1. Navigate to the frontend directory:

```bash
cd frontend
```

2. Install dependencies:

```bash
npm install
```

3. Run the development server:

```bash
npm run dev
```

The frontend will be available at `http://localhost:3000`

## Usage

### Creating a Patient Entity

1. Click on "New Patient" in the navigation bar
2. Fill in the required fields (Case ID is mandatory)
3. Add optional information across the different sections:
   - Demographics: Age, sex
   - Clinical Summary: Etiology, symptoms, comorbidities
   - Lab Data: Baseline values and derived scores
   - Imaging: Modality and findings
   - Treatment History: Previous and current treatments
   - Tumor Board Notes: Discussion and recommendations
4. Click "Save Patient"

### Viewing a Patient

- Click on the eye icon in the patient list
- View all patient information organized by category
- See lab data timeline visualization
- Use the **Specialist AI Summaries** card to choose an Oncologist or Hepatologist.
  - Selecting a specialist triggers GPT-4 generation using the current patient context.
  - Diagnoses and suggestive plans are generated on-demand and cached per specialist.

### Editing a Patient

- Click on the edit icon in the patient list
- Modify any fields as needed
- Save changes

### Deleting a Patient

- Click on the delete icon in the patient list
- Confirm deletion

## API Endpoints

- `GET /api/patients` - Get all patients
- `GET /api/patients/{case_id}` - Get a specific patient
- `POST /api/patients` - Create a new patient
- `PUT /api/patients/{case_id}` - Update a patient
- `DELETE /api/patients/{case_id}` - Delete a patient
- `GET /api/patients/{case_id}/lab-timeline` - Get lab data timeline
- `POST /api/patients/{case_id}/specialists/{specialist}/summary` - Generate an AI specialist diagnosis and plan

## Data Schema

The patient entity follows the provided schema with the following main categories:

1. **Identifiers**: UUID and Case ID
2. **Demographics**: Age, sex (PII removed as per requirements)
3. **Clinical Presentation**: Etiology, symptoms, comorbidities
4. **Investigations**: Lab data, imaging, pathology
5. **Diagnosis/Staging**: Structured diagnosis information
6. **Treatment History**: Previous and current treatments
7. **Tumor Board Notes**: Discussion and recommendations
8. **Follow-up**: Lab data timeline and response tracking

## License

This project is created for educational and research purposes.
