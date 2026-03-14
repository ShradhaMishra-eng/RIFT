import json
import sqlite3
import os
import re
import urllib.request
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

DB_PATH = "pharmgenix.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT,
    filename TEXT,
    vcf_content TEXT,
    drug_name TEXT,
    risk_level TEXT,
    risk_score REAL,
    variants_found TEXT,
    recommendation TEXT,
    explanation TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS variants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id INTEGER,
    gene TEXT,
    rs_id TEXT,
    star_allele TEXT,
    chromosome TEXT,
    position TEXT,
    ref TEXT,
    alt TEXT,
    genotype TEXT,
    phenotype TEXT,
    FOREIGN KEY (analysis_id) REFERENCES analyses(id)
);
"""

PGKB_DATA = {
    "CYP2D6": {
        "poor_metabolizer": {
            "drugs": {
                "codeine": {"risk": "Toxic", "score": 0.95, "rec": "AVOID - Risk of life-threatening respiratory depression. Use non-opioid alternatives (acetaminophen, NSAIDs)."},
                "tramadol": {"risk": "Toxic", "score": 0.90, "rec": "AVOID - Elevated tramadol levels, seizure risk. Use alternative analgesics."},
                "tamoxifen": {"risk": "Ineffective", "score": 0.85, "rec": "ALTERNATIVE REQUIRED - Poor endoxifen formation. Consider aromatase inhibitor (anastrozole)."},
                "amitriptyline": {"risk": "Toxic", "score": 0.88, "rec": "REDUCE DOSE by 50% or switch to citalopram/escitalopram (CYP2C19 metabolized)."},
                "nortriptyline": {"risk": "Toxic", "score": 0.87, "rec": "REDUCE DOSE 25-50%. Monitor plasma levels closely."},
                "haloperidol": {"risk": "Adjust Dosage", "score": 0.75, "rec": "REDUCE DOSE by 50%. Monitor for extrapyramidal symptoms."},
                "metoprolol": {"risk": "Adjust Dosage", "score": 0.70, "rec": "REDUCE DOSE. Monitor heart rate and blood pressure closely."},
                "risperidone": {"risk": "Adjust Dosage", "score": 0.72, "rec": "REDUCE initial dose. Monitor for adverse effects."},
            },
            "phenotype_desc": "Poor Metabolizer (PM) - Significantly reduced CYP2D6 enzyme activity"
        },
        "ultrarapid_metabolizer": {
            "drugs": {
                "codeine": {"risk": "Toxic", "score": 0.92, "rec": "CONTRAINDICATED - Ultra-rapid morphine conversion. Fatal cases reported. Use non-opioid alternatives."},
                "tramadol": {"risk": "Toxic", "score": 0.88, "rec": "AVOID - Excessive active metabolite formation. Use alternative analgesics."},
                "tamoxifen": {"risk": "Safe", "score": 0.15, "rec": "Standard dose appropriate. Enhanced endoxifen formation may be beneficial."},
                "amitriptyline": {"risk": "Ineffective", "score": 0.80, "rec": "INCREASE DOSE or switch to an SSRI with less CYP2D6 dependence."},
            },
            "phenotype_desc": "Ultrarapid Metabolizer (UM) - Greatly increased CYP2D6 enzyme activity"
        },
        "intermediate_metabolizer": {
            "drugs": {
                "codeine": {"risk": "Adjust Dosage", "score": 0.55, "rec": "Use lowest effective dose. Monitor for adverse effects. Consider alternatives."},
                "tamoxifen": {"risk": "Adjust Dosage", "score": 0.50, "rec": "May need dose adjustment. Consider monitoring endoxifen levels if available."},
                "amitriptyline": {"risk": "Adjust Dosage", "score": 0.45, "rec": "Consider 25% dose reduction. Monitor plasma levels."},
            },
            "phenotype_desc": "Intermediate Metabolizer (IM) - Reduced CYP2D6 enzyme activity"
        },
        "normal_metabolizer": {
            "drugs": {},
            "phenotype_desc": "Normal Metabolizer (NM) - Standard CYP2D6 enzyme activity"
        }
    },
    "CYP2C19": {
        "poor_metabolizer": {
            "drugs": {
                "clopidogrel": {"risk": "Ineffective", "score": 0.95, "rec": "ALTERNATIVE REQUIRED - No antiplatelet effect. Use prasugrel or ticagrelor per CPIC guidelines."},
                "omeprazole": {"risk": "Safe", "score": 0.10, "rec": "Enhanced efficacy expected. Standard or reduced dose may be effective."},
                "pantoprazole": {"risk": "Safe", "score": 0.10, "rec": "Enhanced PPI efficacy. Standard dose appropriate."},
                "escitalopram": {"risk": "Toxic", "score": 0.82, "rec": "REDUCE DOSE by 50%. Maximum 10mg/day recommended by CPIC."},
                "sertraline": {"risk": "Adjust Dosage", "score": 0.60, "rec": "Consider 50% dose reduction. Monitor for serotonergic effects."},
                "voriconazole": {"risk": "Toxic", "score": 0.88, "rec": "REDUCE DOSE - Significantly elevated plasma levels. Monitor closely."},
                "amitriptyline": {"risk": "Toxic", "score": 0.80, "rec": "REDUCE DOSE by 50%. Increased drug exposure risk."},
                "diazepam": {"risk": "Toxic", "score": 0.78, "rec": "REDUCE DOSE. Prolonged sedation expected. Monitor closely."},
            },
            "phenotype_desc": "Poor Metabolizer (PM) - Absent CYP2C19 enzyme activity"
        },
        "rapid_metabolizer": {
            "drugs": {
                "clopidogrel": {"risk": "Safe", "score": 0.20, "rec": "Standard dose. Potentially enhanced antiplatelet effect."},
                "escitalopram": {"risk": "Ineffective", "score": 0.75, "rec": "May need dose increase. Standard response less likely."},
                "voriconazole": {"risk": "Ineffective", "score": 0.80, "rec": "HIGHER DOSE required or alternative antifungal. Subtherapeutic levels expected."},
            },
            "phenotype_desc": "Rapid Metabolizer (RM) - Increased CYP2C19 enzyme activity"
        },
        "normal_metabolizer": {
            "drugs": {},
            "phenotype_desc": "Normal Metabolizer (NM) - Standard CYP2C19 enzyme activity"
        }
    },
    "CYP2C9": {
        "poor_metabolizer": {
            "drugs": {
                "warfarin": {"risk": "Toxic", "score": 0.95, "rec": "SIGNIFICANT DOSE REDUCTION required (50-75% lower). High bleeding risk. Frequent INR monitoring essential."},
                "phenytoin": {"risk": "Toxic", "score": 0.90, "rec": "REDUCE DOSE significantly. Risk of phenytoin toxicity. Monitor levels closely."},
                "ibuprofen": {"risk": "Adjust Dosage", "score": 0.65, "rec": "Use lowest effective dose. Monitor renal function."},
                "celecoxib": {"risk": "Toxic", "score": 0.85, "rec": "REDUCE DOSE by 50%. Elevated drug levels expected."},
                "losartan": {"risk": "Ineffective", "score": 0.75, "rec": "Reduced conversion to active metabolite. Consider alternative ARB (candesartan)."},
                "fluvastatin": {"risk": "Toxic", "score": 0.80, "rec": "REDUCE DOSE. Monitor for myopathy."},
                "glipizide": {"risk": "Toxic", "score": 0.78, "rec": "REDUCE DOSE. Risk of hypoglycemia."},
            },
            "phenotype_desc": "Poor Metabolizer (PM) - Significantly reduced CYP2C9 enzyme activity"
        },
        "intermediate_metabolizer": {
            "drugs": {
                "warfarin": {"risk": "Adjust Dosage", "score": 0.60, "rec": "25-50% dose reduction likely needed. Increase INR monitoring frequency."},
                "phenytoin": {"risk": "Adjust Dosage", "score": 0.55, "rec": "Consider dose reduction. Monitor phenytoin plasma levels."},
            },
            "phenotype_desc": "Intermediate Metabolizer (IM) - Reduced CYP2C9 enzyme activity"
        },
        "normal_metabolizer": {
            "drugs": {},
            "phenotype_desc": "Normal Metabolizer (NM) - Standard CYP2C9 enzyme activity"
        }
    },
    "SLCO1B1": {
        "poor_function": {
            "drugs": {
                "simvastatin": {"risk": "Toxic", "score": 0.92, "rec": "AVOID HIGH DOSES - Myopathy/rhabdomyolysis risk. Max 20mg/day or switch to rosuvastatin/pravastatin."},
                "atorvastatin": {"risk": "Adjust Dosage", "score": 0.65, "rec": "Use lowest effective dose. Monitor CK levels. Consider rosuvastatin alternative."},
                "rosuvastatin": {"risk": "Adjust Dosage", "score": 0.55, "rec": "Mild increase in drug exposure. Monitor for muscle symptoms."},
                "pravastatin": {"risk": "Safe", "score": 0.25, "rec": "Preferred statin for SLCO1B1 poor function patients."},
                "methotrexate": {"risk": "Toxic", "score": 0.85, "rec": "REDUCE DOSE. Elevated drug levels. Monitor hepatotoxicity and myelosuppression."},
            },
            "phenotype_desc": "Decreased Function - Reduced SLCO1B1 hepatic transporter activity"
        },
        "normal_function": {
            "drugs": {},
            "phenotype_desc": "Normal Function - Standard SLCO1B1 hepatic transporter activity"
        }
    },
    "TPMT": {
        "poor_metabolizer": {
            "drugs": {
                "azathioprine": {"risk": "Toxic", "score": 0.98, "rec": "CONTRAINDICATED at standard doses. Reduce to 10% of standard dose or use alternative (mycophenolate)."},
                "mercaptopurine": {"risk": "Toxic", "score": 0.98, "rec": "CONTRAINDICATED at standard doses. 10-fold dose reduction required. Life-threatening myelosuppression risk."},
                "thioguanine": {"risk": "Toxic", "score": 0.97, "rec": "SEVERE RISK - Reduce to 6-10% of standard dose. High myelosuppression risk."},
            },
            "phenotype_desc": "Poor Metabolizer (PM) - Absent TPMT enzyme activity"
        },
        "intermediate_metabolizer": {
            "drugs": {
                "azathioprine": {"risk": "Adjust Dosage", "score": 0.65, "rec": "REDUCE DOSE by 30-70%. Monitor CBC weekly for first month."},
                "mercaptopurine": {"risk": "Adjust Dosage", "score": 0.68, "rec": "REDUCE DOSE by 30-70%. Monitor for myelosuppression."},
            },
            "phenotype_desc": "Intermediate Metabolizer (IM) - Reduced TPMT enzyme activity"
        },
        "normal_metabolizer": {
            "drugs": {},
            "phenotype_desc": "Normal Metabolizer (NM) - Standard TPMT enzyme activity"
        }
    },
    "DPYD": {
        "poor_metabolizer": {
            "drugs": {
                "fluorouracil": {"risk": "Toxic", "score": 0.97, "rec": "CONTRAINDICATED - Life-threatening toxicity. Use alternative chemotherapy (capecitabine contraindicated too)."},
                "capecitabine": {"risk": "Toxic", "score": 0.97, "rec": "CONTRAINDICATED - Severe/fatal fluoropyrimidine toxicity. Seek alternative regimen."},
                "tegafur": {"risk": "Toxic", "score": 0.95, "rec": "CONTRAINDICATED - Severe toxicity expected. Alternative chemotherapy required."},
            },
            "phenotype_desc": "Poor Metabolizer (PM) - Absent DPYD enzyme activity"
        },
        "intermediate_metabolizer": {
            "drugs": {
                "fluorouracil": {"risk": "Adjust Dosage", "score": 0.72, "rec": "REDUCE DOSE by 50%. Monitor closely for toxicity. Consider TDM."},
                "capecitabine": {"risk": "Adjust Dosage", "score": 0.72, "rec": "REDUCE DOSE by 50%. Increased toxicity risk. Monitor closely."},
            },
            "phenotype_desc": "Intermediate Metabolizer (IM) - Reduced DPYD enzyme activity"
        },
        "normal_metabolizer": {
            "drugs": {},
            "phenotype_desc": "Normal Metabolizer (NM) - Standard DPYD enzyme activity"
        }
    }
}

STAR_ALLELE_PHENOTYPES = {
    "CYP2D6": {
        "*1": "normal_metabolizer", "*2": "normal_metabolizer",
        "*3": "poor_metabolizer", "*4": "poor_metabolizer", "*5": "poor_metabolizer",
        "*6": "poor_metabolizer", "*7": "poor_metabolizer", "*8": "poor_metabolizer",
        "*10": "intermediate_metabolizer", "*17": "intermediate_metabolizer",
        "*29": "intermediate_metabolizer", "*41": "intermediate_metabolizer",
        "*1xN": "ultrarapid_metabolizer", "*2xN": "ultrarapid_metabolizer",
    },
    "CYP2C19": {
        "*1": "normal_metabolizer", "*17": "rapid_metabolizer",
        "*2": "poor_metabolizer", "*3": "poor_metabolizer",
        "*4": "poor_metabolizer", "*5": "poor_metabolizer",
    },
    "CYP2C9": {
        "*1": "normal_metabolizer",
        "*2": "intermediate_metabolizer", "*3": "poor_metabolizer",
        "*4": "poor_metabolizer", "*5": "poor_metabolizer",
        "*6": "poor_metabolizer", "*8": "intermediate_metabolizer",
        "*11": "intermediate_metabolizer",
    },
    "SLCO1B1": {
        "*1a": "normal_function", "*1b": "normal_function",
        "*5": "poor_function", "*15": "poor_function", "*17": "poor_function",
    },
    "TPMT": {
        "*1": "normal_metabolizer",
        "*2": "poor_metabolizer", "*3A": "poor_metabolizer",
        "*3B": "intermediate_metabolizer", "*3C": "poor_metabolizer",
        "*4": "poor_metabolizer",
    },
    "DPYD": {
        "*1": "normal_metabolizer",
        "*2A": "poor_metabolizer", "*13": "poor_metabolizer",
        "HapB3": "intermediate_metabolizer",
    }
}

RS_TO_GENE_STAR = {
    "rs3892097": ("CYP2D6", "*4"),
    "rs5030655": ("CYP2D6", "*6"),
    "rs16947": ("CYP2D6", "*2"),
    "rs1065852": ("CYP2D6", "*10"),
    "rs28371706": ("CYP2D6", "*41"),
    "rs4244285": ("CYP2C19", "*2"),
    "rs4986893": ("CYP2C19", "*3"),
    "rs12248560": ("CYP2C19", "*17"),
    "rs1799853": ("CYP2C9", "*2"),
    "rs1057910": ("CYP2C9", "*3"),
    "rs4149056": ("SLCO1B1", "*5"),
    "rs2306283": ("SLCO1B1", "*1b"),
    "rs1800462": ("TPMT", "*2"),
    "rs1800460": ("TPMT", "*3B"),
    "rs1142345": ("TPMT", "*3C"),
    "rs3918290": ("DPYD", "*2A"),
    "rs55886062": ("DPYD", "*13"),
    "rs67376798": ("DPYD", "HapB3"),
}

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()

def parse_vcf(content: str) -> list:
    """Parse VCF file and extract pharmacogenomic variants."""
    variants = []
    lines = content.strip().split('\n')
    
    target_genes = {"CYP2D6", "CYP2C19", "CYP2C9", "SLCO1B1", "TPMT", "DPYD"}
    
    for line in lines:
        line = line.strip()
        if line.startswith('#') or not line:
            continue
        
        parts = line.split('\t')
        if len(parts) < 8:
            continue
        
        chrom, pos, id_field, ref, alt, qual, filter_field, info = parts[:8]
        genotype = parts[9] if len(parts) > 9 else "unknown"
        
        # Parse INFO field
        info_dict = {}
        for item in info.split(';'):
            if '=' in item:
                k, v = item.split('=', 1)
                info_dict[k] = v
            else:
                info_dict[item] = True
        
        gene = info_dict.get('GENE', '')
        star = info_dict.get('STAR', '')
        rs_id = info_dict.get('RS', id_field if id_field.startswith('rs') else '')
        
        # Also check from RS ID mapping
        if not gene and rs_id in RS_TO_GENE_STAR:
            gene, star = RS_TO_GENE_STAR[rs_id]
        
        # Check rs IDs in the ID field
        if not gene and id_field in RS_TO_GENE_STAR:
            gene, star = RS_TO_GENE_STAR[id_field]
            rs_id = id_field
        
        if gene in target_genes or any(g in info for g in target_genes):
            # Try to extract gene from info if not found
            if not gene:
                for g in target_genes:
                    if g in info:
                        gene = g
                        break
            
            if gene:
                variants.append({
                    "gene": gene,
                    "chromosome": chrom,
                    "position": pos,
                    "ref": ref,
                    "alt": alt,
                    "rs_id": rs_id,
                    "star_allele": star,
                    "genotype": genotype,
                    "raw_info": info
                })
    
    return variants

def determine_phenotype(gene: str, star_alleles: list) -> str:
    """Determine metabolizer phenotype from star alleles."""
    if gene not in STAR_ALLELE_PHENOTYPES:
        return "normal_metabolizer"
    
    gene_map = STAR_ALLELE_PHENOTYPES[gene]
    phenotypes = []
    
    for star in star_alleles:
        star_clean = star.strip().replace('CYP2D6', '').replace('CYP2C19', '').replace('CYP2C9', '').replace('SLCO1B1', '').replace('TPMT', '').replace('DPYD', '')
        if star_clean in gene_map:
            phenotypes.append(gene_map[star_clean])
    
    if not phenotypes:
        return "normal_metabolizer"
    
    priority = ["poor_metabolizer", "poor_function", "ultrarapid_metabolizer", 
                "intermediate_metabolizer", "rapid_metabolizer", "normal_metabolizer", "normal_function"]
    
    for p in priority:
        if p in phenotypes:
            return p
    
    return phenotypes[0]

def analyze_drug_risk(variants: list, drug_name: str) -> dict:
    drug_lower = drug_name.lower().strip()
    
    gene_variants = {}
    for v in variants:
        gene = v['gene']
        if gene not in gene_variants:
            gene_variants[gene] = []
        gene_variants[gene].append(v)
    
    results = []
    overall_risk = "Safe"
    overall_score = 0.0
    
    for gene, gene_vars in gene_variants.items():
        star_alleles = [v['star_allele'] for v in gene_vars if v.get('star_allele')]
        phenotype = determine_phenotype(gene, star_alleles)
        
        if gene in PGKB_DATA and phenotype in PGKB_DATA[gene]:
            gene_data = PGKB_DATA[gene][phenotype]
            drugs_data = gene_data['drugs']
            
            drug_info = None
            for d_key in drugs_data:
                if d_key in drug_lower or drug_lower in d_key:
                    drug_info = drugs_data[d_key]
                    break
            
            if drug_info:
                results.append({
                    "gene": gene,
                    "phenotype": phenotype,
                    "phenotype_desc": gene_data['phenotype_desc'],
                    "star_alleles": star_alleles,
                    "risk": drug_info['risk'],
                    "score": drug_info['score'],
                    "recommendation": drug_info['rec'],
                    "variants": gene_vars
                })
                
                if drug_info['score'] > overall_score:
                    overall_score = drug_info['score']
                    overall_risk = drug_info['risk']
            else:
                results.append({
                    "gene": gene,
                    "phenotype": phenotype,
                    "phenotype_desc": gene_data['phenotype_desc'],
                    "star_alleles": star_alleles,
                    "risk": "Unknown",
                    "score": 0.3,
                    "recommendation": f"No specific CPIC guideline for {drug_name} with {gene} {phenotype}. Consult clinical pharmacist.",
                    "variants": gene_vars
                })
    
    if not results:
        overall_risk = "Unknown"
        overall_score = 0.0
    
    return {
        "risk": overall_risk,
        "score": overall_score,
        "gene_results": results
    }

# ─── ANTHROPIC API CALL ──────────────────────────────────────────────────────

def call_anthropic_api(prompt: str, api_key: str) -> str:
    """Call Anthropic API for LLM explanation."""
    try:
        payload = json.dumps({
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 800,
            "messages": [{"role": "user", "content": prompt}]
        }).encode('utf-8')
        
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01"
            },
            method="POST"
        )
        
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return data['content'][0]['text']
    except Exception as e:
        return f"LLM explanation unavailable: {str(e)}. Please check your Anthropic API key in settings."

def build_llm_prompt(drug_name: str, analysis_result: dict, variants: list) -> str:
    gene_summary = ""
    for gr in analysis_result.get('gene_results', []):
        gene_summary += f"\n- {gr['gene']}: {gr['phenotype_desc']}, Star alleles: {', '.join(gr['star_alleles']) if gr['star_alleles'] else 'inferred'}, Risk: {gr['risk']}"
    
    variant_list = ""
    for v in variants[:5]:
        variant_list += f"\n  • {v['gene']} {v.get('star_allele','')} at {v['chromosome']}:{v['position']} (rs:{v.get('rs_id','N/A')})"
    
    return f"""You are a clinical pharmacogenomics expert. Provide a concise but specific clinical explanation for the following pharmacogenomic analysis result.

Drug: {drug_name}
Overall Risk: {analysis_result['risk']}
Risk Score: {analysis_result['score']:.0%}

Gene/Phenotype Findings:{gene_summary}

Specific Variants Detected:{variant_list}

Please provide:
1. A brief (2-3 sentence) mechanistic explanation of WHY these specific genetic variants affect {drug_name} metabolism
2. The biological mechanism (enzyme activity, transporter function, etc.)
3. Clinical implications and what the prescriber should monitor

Keep it under 200 words. Be specific, cite the star alleles and rs IDs. Use clinical language appropriate for a physician."""

# ─── HTTP HANDLER ────────────────────────────────────────────────────────────

class PharmHandler(BaseHTTPRequestHandler):
    
    def log_message(self, format, *args):
        pass  # Suppress default logging
    
    def send_json(self, data, status=200):
        body = json.dumps(data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)
    
    def send_file(self, path, content_type):
        try:
            with open(path, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.send_file('index.html', 'text/html')
        elif self.path == '/api/history':
            self.handle_history()
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        if self.path == '/api/analyze':
            self.handle_analyze()
        else:
            self.send_response(404)
            self.end_headers()
    
    def handle_history(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("""
            SELECT id, patient_id, filename, drug_name, risk_level, risk_score, 
                   recommendation, created_at 
            FROM analyses ORDER BY created_at DESC LIMIT 20
        """)
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        self.send_json({"history": rows})
    
    def handle_analyze(self):
        content_length = int(self.headers.get('Content-Length', 0))
        content_type = self.headers.get('Content-Type', '')
        body = self.rfile.read(content_length)
        
        try:
            if 'multipart/form-data' in content_type:
                # Parse multipart form
                boundary = content_type.split('boundary=')[1].encode()
                parts = body.split(b'--' + boundary)
                
                form_data = {}
                vcf_content = None
                filename = "unknown.vcf"
                
                for part in parts[1:-1]:
                    if b'\r\n\r\n' not in part:
                        continue
                    headers, content = part.split(b'\r\n\r\n', 1)
                    content = content.rstrip(b'\r\n')
                    headers_str = headers.decode('utf-8', errors='replace')
                    
                    name_match = re.search(r'name="([^"]+)"', headers_str)
                    if not name_match:
                        continue
                    field_name = name_match.group(1)
                    
                    fname_match = re.search(r'filename="([^"]+)"', headers_str)
                    if fname_match:
                        filename = fname_match.group(1)
                        vcf_content = content.decode('utf-8', errors='replace')
                    else:
                        form_data[field_name] = content.decode('utf-8', errors='replace')
                
                drug_name = form_data.get('drug', '').strip()
                patient_id = form_data.get('patient_id', 'P001').strip()
                api_key = form_data.get('api_key', '').strip()
                
            else:
                data = json.loads(body.decode('utf-8'))
                vcf_content = data.get('vcf_content', '')
                drug_name = data.get('drug', '').strip()
                patient_id = data.get('patient_id', 'P001').strip()
                api_key = data.get('api_key', '').strip()
                filename = data.get('filename', 'uploaded.vcf')
            
            if not vcf_content or not drug_name:
                self.send_json({"error": "VCF content and drug name are required"}, 400)
                return
            
            # Parse VCF
            variants = parse_vcf(vcf_content)
            
            if not variants:
                self.send_json({
                    "error": "No pharmacogenomic variants found in VCF file",
                    "tip": "Ensure VCF has INFO fields: GENE, STAR, RS for CYP2D6, CYP2C19, CYP2C9, SLCO1B1, TPMT, DPYD"
                }, 400)
                return
            
            # Analyze risk
            analysis = analyze_drug_risk(variants, drug_name)
            
            # Generate LLM explanation
            explanation = "API key not provided. Add your Anthropic API key in the settings panel for AI-powered explanations."
            if api_key:
                prompt = build_llm_prompt(drug_name, analysis, variants)
                explanation = call_anthropic_api(prompt, api_key)
            
            # Build recommendation from first result
            recommendation = "Consult clinical pharmacist for personalized guidance."
            if analysis['gene_results']:
                recommendation = analysis['gene_results'][0]['recommendation']
            
            # Save to DB
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.execute("""
                INSERT INTO analyses (patient_id, filename, vcf_content, drug_name, risk_level, 
                                     risk_score, variants_found, recommendation, explanation)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                patient_id, filename, vcf_content[:5000], drug_name,
                analysis['risk'], analysis['score'],
                json.dumps([{"gene": v['gene'], "star": v.get('star_allele',''), "rs": v.get('rs_id','')} for v in variants]),
                recommendation, explanation
            ))
            analysis_id = cursor.lastrowid
            
            for v in variants:
                conn.execute("""
                    INSERT INTO variants (analysis_id, gene, rs_id, star_allele, chromosome, 
                                        position, ref, alt, genotype, phenotype)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    analysis_id, v['gene'], v.get('rs_id',''), v.get('star_allele',''),
                    v['chromosome'], v['position'], v['ref'], v['alt'], v.get('genotype',''),
                    "pending"
                ))
            
            conn.commit()
            conn.close()
            
            self.send_json({
                "success": True,
                "analysis_id": analysis_id,
                "patient_id": patient_id,
                "drug": drug_name,
                "risk": analysis['risk'],
                "risk_score": analysis['score'],
                "gene_results": analysis['gene_results'],
                "variants_count": len(variants),
                "variants": variants,
                "explanation": explanation,
                "recommendation": recommendation
            })
            
        except Exception as e:
            import traceback
            self.send_json({"error": f"Analysis failed: {str(e)}", "trace": traceback.format_exc()}, 500)

# ─── MAIN ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    port = 8080
    server = HTTPServer(('0.0.0.0', port), PharmHandler)
    print(f"""
╔══════════════════════════════════════════════════════════╗
║           PharmGenix - Pharmacogenomics Engine           ║
╠══════════════════════════════════════════════════════════╣
║  Server running at: http://localhost:{port}               ║
║  Database: {DB_PATH}                              ║
║  Genes: CYP2D6, CYP2C19, CYP2C9, SLCO1B1, TPMT, DPYD  ║
║  Press Ctrl+C to stop                                   ║
╚══════════════════════════════════════════════════════════╝
    """)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
