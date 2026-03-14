@@ -0,0 +1,118 @@
VaidyaGen is a full-stack pharmacogenomics clinical decision support tool. Upload a patient VCF file, enter a drug name, and receive CPIC-guideline-aligned risk stratification with AI-powered clinical explanations.

✨ Features

🧬 VCF Parsing — Supports VCF v4.2 with automatic variant detection via RS ID lookup
⚗️ Risk Stratification — Classifies drug risk as Toxic, Ineffective, Adjust Dosage, Safe, or Unknown
🤖 AI Explanations — Claude API generates physician-level clinical interpretations
🗄️ Analysis History — SQLite database stores all past analyses
🚀 Zero Dependencies — Pure Python standard library, no pip installs needed
🌐 Single File Deploy — Backend serves the frontend automatically


📁 Project Structure
vaidyagen/
├── index.html                       # Frontend UI (served by backend)
├── pharma_backend.py                # Python backend server
├── pharmgenix.db                    # SQLite DB (auto-created on first run)
├── requirements.txt                 # Empty — no external packages needed
├── Procfile                         # For Railway / Render deployment
└── TC_P1_PATIENT_001_Normal.vcf     # Sample patient VCF file

🚀 Quick Start
No installs. No pip. Just Python 3.
bash# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/vaidyagen.git
cd vaidyagen

# 2. Start the server
python3 pharma_backend.py

# 3. Open in browser
# http://localhost:8080
The backend serves index.html automatically and creates pharmgenix.db on first run.

🧬 Supported Genes & Drugs
GeneCovered DrugsCYP2D6Codeine, Tramadol, Tamoxifen, Amitriptyline, Nortriptyline, Metoprolol, RisperidoneCYP2C19Clopidogrel, Escitalopram, Omeprazole, Sertraline, Voriconazole, DiazepamCYP2C9Warfarin, Phenytoin, Celecoxib, Ibuprofen, Losartan, Fluvastatin, GlipizideSLCO1B1Simvastatin, Atorvastatin, Rosuvastatin, Pravastatin, MethotrexateTPMTAzathioprine, Mercaptopurine, ThioguanineDPYDFluorouracil, Capecitabine, Tegafur

⚠️ Risk Levels
LevelMeaning🔴 ToxicDangerously elevated drug levels — avoid or major dose reduction🟣 IneffectiveInsufficient metabolism — drug will not work as expected🟡 Adjust DosageDose modification required with close monitoring🟢 SafeNo clinically significant interaction — standard dosing appropriate⚪ UnknownNo CPIC guideline for this gene-drug combination

📄 VCF Format
The INFO column must contain GENE, STAR, and RS fields:
#CHROM  POS         ID         REF  ALT  INFO
chr22   42522613    rs3892097  C    T    GENE=CYP2D6;STAR=*4;RS=rs3892097
chr10   94781859    rs4244285  G    A    GENE=CYP2C19;STAR=*2;RS=rs4244285
chr10   96741053    rs1799853  C    T    GENE=CYP2C9;STAR=*2;RS=rs1799853
chr12   21331549    rs4149056  T    C    GENE=SLCO1B1;STAR=*5;RS=rs4149056

The backend also auto-detects variants from the RS ID lookup table even without explicit GENE/STAR tags.


🌐 API Endpoints
MethodEndpointDescriptionGET/Serves frontend UIGET/api/historyReturns last 20 analyses as JSONPOST/api/analyzeAccepts multipart form: vcf, drug, patient_id, api_key
Example Response
json{
  "success": true,
  "patient_id": "P001",
  "drug": "warfarin",
  "risk": "Toxic",
  "risk_score": 0.95,
  "variants_count": 3,
  "gene_results": [
    {
      "gene": "CYP2C9",
      "phenotype_desc": "Poor Metabolizer (PM)",
      "star_alleles": ["*3"],
      "risk": "Toxic",
      "recommendation": "SIGNIFICANT DOSE REDUCTION required..."
    }
  ],
  "explanation": "The CYP2C9*3 allele significantly reduces warfarin metabolism..."
}

☁️ Deployment
Railway (Recommended — free, one command)
bashnpm install -g @railway/cli
railway login
railway init
railway up
Railway auto-detects the Procfile. You get a public URL in ~1 minute.
Then set Settings → Backend URL in the app to your Railway URL.
Render

Push to GitHub
Go to render.com → New → Web Service
Connect your repo and set:

Runtime: Python 3
Start Command: python pharma_backend.py


Deploy — free public URL in ~2 minutes

VPS / Linux Server
bash# Upload files
scp index.html pharma_backend.py user@your-server:/home/user/vaidyagen/

# Run persistently
cd /home/user/vaidyagen
nohup python3 pharma_backend.py &

# Open firewall
sudo ufw allow 8080

⚙️ Configuration
After deployment, click ⚙ Settings in the app and set:
SettingDescriptionAnthropic API KeyYour sk-ant-... key for AI clinical explanationsBackend URLYour deployed server URL (e.g. https://vaidyagen.up.railway.app)
Environment Variables
VariableDefaultDescriptionPORT8080Server port — auto-set by Railway/Render

🛠️ Troubleshooting
ProblemFixNo variants found in VCFEnsure INFO column has GENE=, STAR=, RS= fieldsCORS error in browserBackend URL must match exactly — no trailing slashAI explanation missingAdd Anthropic API key in SettingsPort already in usePORT=9090 python3 pharma_backend.pyrailway up access deniedrailway logout then railway login and retryDB not savingEnsure backend has write permission in working directory

🏗️ Tech Stack
LayerDetailsBackendPython 3 · http.server · sqlite3 · urllib (all stdlib)FrontendHTML5 · CSS3 · Vanilla JS · Single fileDatabaseSQLite (auto-created, zero config)AIAnthropic Claude API (claude-sonnet-4-20250514)GuidelinesCPIC 2024 · PharmGKBFontsCormorant Garamond · Outfit · DM Mono · Poppins

📋 License
For clinical research and educational use. Always verify pharmacogenomic recommendations with a licensed clinical pharmacist before making prescribing decisions.
