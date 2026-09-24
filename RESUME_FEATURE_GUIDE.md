# Resume Upload & Job Matching Feature

## Overview
The job portal now includes a smart resume-matching feature that helps candidates discover the most relevant jobs from the database. Upload your CV/resume and the system will rank all available jobs based on how well they match your background and skills.

## How It Works

### 1. **Upload Your Resume**
- Click the **"📄 Upload Resume"** button in the sidebar
- Select a resume file in one of these formats:
  - **PDF** (.pdf) — scanned or digital documents
  - **DOCX** (.docx) — Microsoft Word documents
  - **TXT** (.txt) — plain text files
- The system extracts text and analyzes it instantly

### 2. **Skill Detection**
The system automatically identifies which **domains/skills** your resume contains:
- 🤖 **AIML** — AI, Machine Learning, Deep Learning, TensorFlow, PyTorch, NLP, Computer Vision
- 📊 **Data Analytics** — Data Analysis, SQL, Tableau, Power BI, ETL, Dashboards
- ⛓️ **Blockchain** — Web3, Smart Contracts, Solidity, DeFi, Crypto
- 🎮 **AR/VR** — Augmented Reality, Virtual Reality, Metaverse, 3D Graphics, Unity
- 🔒 **Cybersecurity** — Security Engineer, Pentesting, Network Security, SIEM

### 3. **Smart Job Ranking**
The system uses **TF-IDF (Term Frequency-Inverse Document Frequency)** + **Cosine Similarity** to rank jobs:
- Jobs with **higher match scores** appear at the top
- Matching is based on: job title, company, category, job type, location, and domain tags
- Scores are calculated as percentages (0-100%)

### 4. **Match Score Color Coding**
- 🟢 **Green (≥70%)** — Highly relevant jobs, strong match
- 🟡 **Yellow (40-69%)** — Moderately relevant jobs
- ⚪ **Gray (<40%)** — Lower relevance

## Features

✅ **Detected Skills Display** — Shows which domains your resume matches  
✅ **Job Count** — Displays total jobs ranked from your pool  
✅ **Match Score Badges** — Color-coded relevance indicators  
✅ **Domain Tags** — Shows top 2 matching domains per job  
✅ **One-Click Apply** — Click any job to open application link  
✅ **Clear Function** — Hide recommendations and try a new resume  

## Technical Details

### What Gets Analyzed
Your resume is analyzed for keywords in:
- **Title and Company names** — exact skill mentions
- **Domain keywords** — from our 5-domain taxonomy
- **Common tech stack** — languages, frameworks, tools

### Privacy & Security
✅ **No Data Storage** — Your resume is never saved to the database  
✅ **In-Memory Processing** — Processed instantly, discarded after matching  
✅ **No File Creation** — Everything happens in RAM  
✅ **Secure Connection** — Flask server with local processing  

### File Size Limits
- **Maximum file size:** 5 MB
- **Minimum text extracted:** 30 characters (to prevent empty/image-only PDFs)

### Supported Job Platforms
The feature ranks jobs from these sources:
- Remotive
- RemoteOK
- Himalayas
- Internshala
- FirstNaukri
- Arbeitnow

## API Endpoint

### `/api/match-resume` (POST)

**Request:**
```bash
curl -X POST http://localhost:5000/api/match-resume \
  -F "resume=@your_resume.pdf"
```

**Response (Success):**
```json
{
  "success": true,
  "matches": [
    {
      "title": "Data Scientist",
      "company": "TechCorp",
      "match_score": 85.3,
      "domains": ["AIML", "Data Analytics"],
      ...
    }
  ],
  "total_jobs_considered": 1243,
  "resume_domains": ["AIML", "Data Analytics"],
  "resume_chars_extracted": 1273
}
```

**Response (Error):**
```json
{
  "success": false,
  "error": "Unsupported file type: .doc. Allowed: pdf, docx, txt"
}
```

## Workflow Example

1. **Start the app:** `python api.py`
2. **Fetch jobs:** Select platforms (Internshala, FirstNaukri, etc.) → Click "⚡ Fetch Jobs"
3. **Upload resume:** Click "📄 Upload Resume" → Select your CV (PDF/DOCX/TXT)
4. **View results:** "⭐ Recommended for You" section appears with ranked matches
5. **Apply:** Click any job row → Modal opens → Click "🚀 Apply Now"
6. **Clear:** Click "✕ Clear" to remove recommendations and try another resume

## Troubleshooting

**Problem:** "Could not extract enough readable text"  
**Solution:** Ensure your resume is not a scanned/image-only PDF; convert it to a text-based PDF or use DOCX/TXT format.

**Problem:** No recommendations showing  
**Solution:** Fetch jobs first using "⚡ Fetch Jobs" button to populate the database.

**Problem:** Low match scores on clearly relevant jobs  
**Solution:** This may indicate the job posting uses different terminology than your resume. TF-IDF works best with exact keyword overlap.

## Bug Fixes Included

✅ **Fixed `/api/fetch` bug** — Was returning 500 due to undefined `final_jobs` variable  
✅ **Refactored domain keywords** — Extracted to module-level constant for code reuse  
✅ **Modal improvements** — Single `showJobModal()` helper serves both main and recommended tables  

## Performance Notes

- **Resume processing:** <1 second for typical 1-3 page resume
- **TF-IDF fit & ranking:** Scales with job count (currently handles 1000+ jobs instantly)
- **Memory:** All operations in RAM, no disk I/O

## Future Enhancements

- Optional: Save recent resumes for quick re-matching
- Optional: Resume parsing improvements (extract skills section separately)
- Optional: Caching vectorizer for sub-100ms performance with large job pools
- Optional: Vector embeddings (sentence-transformers) for semantic similarity
