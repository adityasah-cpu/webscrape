# Job Portal - User Documentation

## Table of Contents
1. [Introduction](#introduction)
2. [System Requirements](#system-requirements)
3. [Getting Started](#getting-started)
4. [Step-by-Step User Guide](#step-by-step-user-guide)
5. [FAQ](#faq)
6. [Troubleshooting](#troubleshooting)

---

## Introduction

Welcome to the **Job Portal** - a modern, intelligent job discovery platform designed to help you find opportunities that match your skills and interests. This documentation provides a complete guide for using the platform from login to job application.

### Platform Features
- **Google Sign-In**: Quick and secure authentication using your college email
- **CV Upload & Matching**: Intelligent resume analysis for job recommendations
- **Direct Apply**: One-click application to job listings
- **Location-Based Jobs**: Browse jobs by location
- **Flexible Search**: Select specific jobs or get personalized recommendations

---

## System Requirements

### Browser Requirements
- Modern web browser (Chrome, Firefox, Safari, Edge)
- JavaScript enabled
- Cookies enabled for session management
- Internet connection required

### Supported Devices
- Desktop computers (recommended for full experience)
- Tablets
- Mobile phones (responsive design)

### Email Requirements
- Valid college email address
- Access to your college email account for Google Sign-In
- Supported domains:
  - `@cutm.ac.in`
  - `@cutmap.ac.in`
  - `@centurionuniv.edu.in`

---

## Getting Started

### Accessing the Portal

1. Open your web browser
2. Navigate to the job portal URL: `http://localhost:5000` (or your site URL)
3. You should see the login screen with the "Sign in with Google" button

### What You'll Need

Before you start:
- Your college email address
- Your resume/CV (optional, but recommended)
  - Supported formats: PDF, DOC, DOCX
  - Maximum file size: 5 MB
- A few minutes to complete the process

---

## Step-by-Step User Guide

### STEP 1: Sign In with Google

**Objective**: Authenticate and create your account

**Instructions**:

1. Click the **"Sign in with Google"** button on the login page
2. A Google sign-in dialog will appear
3. Enter your **college email address** (e.g., `yourname@cutm.ac.in`)
4. Enter your **password**
5. Grant permission for the portal to access your profile information:
   - Email address
   - Name
   - Profile picture
6. Click **"Allow"** or **"Confirm"**

**Expected Result**: You'll be logged into the portal and taken to the next step (Role Selection)

**Important Notes**:
- Use your official college email address
- Make sure cookies are enabled in your browser
- You'll only need to sign in once (session will be maintained)

---

### STEP 2: Select Your Role

**Objective**: Specify what type of opportunities you're looking for

**Instructions**:

1. After successful sign-in, you'll see the **Role Selection** screen
2. Review the available role options
3. Click on the role that best matches your interests and skills
4. Confirm your selection

**Available Roles**:
- Student Seeking Internship
- Graduate Seeking Full-time Position
- Recent Alumnus/Alumna
- Other (specify your preference)

**Important Notes**:
- This helps personalize your job recommendations
- You can change your role later if needed
- Select based on your current career stage

---

### STEP 3: Upload CV or Skip

**Objective**: Provide your resume for intelligent job matching or browse manually

**Key Decision Point**: This step has two paths

#### Path A: Upload Your CV (Recommended ⭐)

**Benefits**:
- Get personalized job recommendations
- Our system matches jobs to your skills
- Save time by seeing relevant opportunities first
- Higher match quality

**Instructions**:

1. Click the **"Upload CV"** button
2. Select your resume file:
   - Click "Choose File" or "Browse"
   - Navigate to your resume on your computer
   - Select a PDF, DOC, or DOCX file
3. Click **"Upload"**
4. Wait for the upload to complete
5. The system will analyze your CV

**Expected Result**: 
- You'll be taken to the job listings page
- Jobs will be displayed based on CV matching
- Most relevant jobs appear first

**File Requirements**:
- Format: PDF, Microsoft Word (.doc, .docx)
- Size: Maximum 5 MB
- Content: Clear, well-formatted resume

---

#### Path B: Skip CV Upload

**Reasons to Skip**:
- Want to browse all jobs manually
- Plan to upload CV later
- Prefer flexible exploration

**Instructions**:

1. Click the **"Skip"** button
2. Click **"Continue"** or **"Proceed"**
3. You'll be taken to the main job listing screen

**Important**: 
- If you skip, you can still upload CV later
- Must follow the proper sequence: Fetch Jobs → Upload CV → Fetch Jobs Again
- See "STEP 5: Upload CV (If Not Done Yet)" for details

---

### STEP 4: Main Screen - Browse & Fetch Jobs

**Objective**: Select specific jobs to view and explore

**Layout Overview**:

```
┌─────────────────────────────────────────┐
│  Job Portal - Main Screen               │
├─────────────────────────────────────────┤
│                                         │
│  ☐ Job Title 1 - Company A             │
│  ☐ Job Title 2 - Company B             │
│  ☐ Job Title 3 - Company C             │
│  ☐ Job Title 4 - Company D             │
│                                         │
│  [Fetch Selected Jobs] [View All] [🔄] │
│                                         │
└─────────────────────────────────────────┘
```

**Instructions**:

1. **Browse Available Jobs**
   - Scroll through the job listings
   - Read job titles and company names
   - Preview salary/location information

2. **Select Jobs Interested In**
   - Check the ☐ checkbox next to job titles you want to explore
   - You can select multiple jobs
   - Use "Select All" to choose all jobs

3. **Load/Fetch Jobs**
   - Click **"Fetch Selected Jobs"** button
   - Or click **"Load Jobs"** to load your selections
   - Or click the refresh button 🔄

4. **View Results**
   - Selected jobs will load in a detailed view
   - You'll see job cards with:
     - Job title
     - Company name
     - Location
     - Job description
     - Apply button

**Pro Tips**:
- Start with a few jobs (3-5) to test the experience
- You can fetch more jobs at any time
- Jobs can be re-selected for detailed viewing

---

### STEP 5: Upload CV (If Not Done Yet)

**Objective**: Upload your resume after you've fetched initial jobs

**When to Use This Step**:
- You skipped CV upload in Step 3
- You want to update your CV
- You need CV-based job matching

**Critical Sequence**:
```
1. Fetch Jobs (Step 4)
   ↓
2. Upload CV (This Step)
   ↓
3. Fetch Jobs Again (Step 4)
   ↓
4. View CV-Matched Results
```

**Important**: You must fetch jobs BEFORE uploading CV!

**Instructions**:

1. From the main job listing page, look for **"Upload CV"** or **"Add Resume"** button
2. Click the upload button
3. A file dialog will appear
4. Navigate to your resume file on your computer
5. Select your CV file (PDF/DOC/DOCX)
6. Click **"Open"** to select the file
7. Click **"Upload"** to submit
8. Wait for upload confirmation (usually 2-5 seconds)
9. After successful upload:
   - Click **"Fetch Jobs Again"** or **"Refresh"**
   - The page will reload with CV-matched jobs

**What Happens After Upload**:
- System analyzes your CV for:
  - Skills and experience
  - Education background
  - Work history
  - Keywords and expertise
- Jobs are re-ranked by relevance to your profile
- Most relevant opportunities appear first

**File Requirements**:
- Format: PDF, DOC, DOCX
- Maximum size: 5 MB
- Must be a valid resume/CV

**Updating Your CV**:
- Upload a new CV anytime
- New version replaces the old one
- Fetch jobs again to see updated matches

---

### STEP 6: Read Job Details & Description

**Objective**: Review complete job information before applying

**Instructions**:

1. Click on a job title or **"View Details"** button
2. The job detail panel will expand
3. Read the complete job information:

**Information You'll See**:
- **Job Title**: Official position name
- **Company Name**: Employer organization
- **Location**: Job location (city, address)
- **Job Description**: Detailed overview of the role
- **Responsibilities**: Day-to-day tasks and duties
  - What you'll be doing
  - Projects you'll work on
  - Team interactions
- **Requirements**: Qualifications needed
  - Required education
  - Experience level
  - Technical skills
  - Soft skills
- **Qualifications**: Additional preferred skills
- **Salary Range** (if provided): Pay expectations
- **Job Type**: Full-time, Internship, Contract, etc.
- **Application Deadline** (if applicable)

**How to Review**:

1. **Read Carefully**
   - Don't just skim
   - Understand all requirements
   - Check if you meet qualifications

2. **Assess Fit**
   - Does the role match your skills?
   - Are you interested in the work?
   - Is the location suitable?
   - Does the salary match expectations?

3. **Take Notes** (Optional)
   - Note interesting jobs
   - Write down questions
   - Compare with other positions

4. **Prepare for Application**
   - Identify key requirements
   - Note any specific documents needed
   - Prepare answers for common questions

**Tips for Reviewing**:
- Look for keyword matches with your CV
- Check growth opportunities
- Review company information
- Verify application requirements

---

### STEP 7: Apply for the Job

**Objective**: Submit your application to the company

**Instructions**:

1. After reviewing job details, locate the **"Apply Now"** button
   - Usually at the bottom of job details
   - May also appear as "Direct Apply" or "Submit Application"

2. Click **"Apply Now"**

3. You'll be redirected to the company's website
   - May open in the same tab
   - May open in a new tab/window
   - Company website loads (may take a few seconds)

4. Complete the application form on company website:
   - Fill in required information
   - Verify your contact details
   - Add any additional requested information
   - Upload documents if required
   - Review your answers

5. Submit the application
   - Click "Submit" or "Send Application"
   - Confirm the submission if prompted
   - Look for confirmation message

6. Return to job portal (if needed)
   - Close the company website tab
   - Return to job listing
   - Continue browsing other jobs

**Application Checklist**:
- [ ] Read all requirements carefully
- [ ] Ensure CV/Resume is up-to-date
- [ ] Complete all required fields
- [ ] Double-check spelling and grammar
- [ ] Verify contact information accuracy
- [ ] Review before submitting
- [ ] Keep track of application confirmation

**After Applying**:
- Look for confirmation message
- Note the application date
- Company will contact you directly
- Check email regularly for updates
- Consider applying to similar roles

**Important Notes**:
- Each "Apply Now" button is specific to that job
- You're being directed to the company's own application system
- The company handles your application from that point
- Keep your contact information updated
- Respond promptly to company communications

---

## Complete User Journey Flow

```
START
  ↓
[1] Sign In with Google
  └→ Authenticate with college email
  ↓
[2] Select Your Role
  └→ Choose career stage/position type
  ↓
[3] Upload CV or Skip?
  ├→ YES: Upload CV → See Matched Jobs
  │  └→ Go to Step 4
  │
  └→ NO: Skip → Go to Main Screen
     └→ Go to Step 4
  ↓
[4] Main Screen - Browse & Fetch Jobs
  └→ Select jobs and load them
  ↓
Did you skip CV in Step 3?
  ├→ YES: Go to Step 5 (Upload CV)
  │  ├→ Upload your resume
  │  └→ Fetch Jobs Again
  │
  └→ NO: Continue to Step 6
  ↓
[5] View Job Details & Description
  ├→ Read requirements
  ├→ Assess job fit
  └→ Locate Apply button
  ↓
[6] Click "Apply Now"
  ├→ Redirected to company website
  └→ Complete application form
  ↓
[7] Submit Application
  └→ Receive confirmation
  ↓
SUCCESS ✓ Application Submitted!
  ↓
REPEAT: Browse and apply to more jobs
```

---

## FAQ (Frequently Asked Questions)

### Account & Authentication

**Q: How do I sign in to the portal?**
A: Click "Sign in with Google" and use your college email address (e.g., yourname@cutm.ac.in). Authenticate with your Google password.

**Q: What if I forgot my password?**
A: Use Google's password recovery. Click "Forgot password?" on the Google sign-in page. You'll receive a reset link via email.

**Q: Can I use a non-college email address?**
A: No. You must use an email from one of the supported college domains: @cutm.ac.in, @cutmap.ac.in, or @centurionuniv.edu.in.

**Q: How long does my session last?**
A: Your session remains active as long as you're using the portal. You'll be automatically logged out after 7 days of inactivity.

### CV Upload & Management

**Q: Do I need to upload my CV?**
A: No, CV upload is optional. However, uploading enables intelligent job matching based on your skills and experience. Highly recommended!

**Q: What file formats are accepted for CV?**
A: PDF, DOC, and DOCX files are accepted. Maximum file size is 5 MB.

**Q: Can I upload multiple CVs?**
A: You can upload one CV at a time. Uploading a new CV replaces the previous one.

**Q: How do I update my CV?**
A: Simply upload a new CV file. It will replace your previous CV. Then fetch jobs again to see updated matches.

**Q: Is my CV data safe?**
A: Yes! Your CV is securely stored on our servers and used only for job matching. We follow strict data privacy guidelines.

**Q: What if I upload CV after skipping?**
A: You must follow the sequence: Fetch Jobs → Upload CV → Fetch Jobs Again. This ensures proper job matching.

### Job Browsing & Selection

**Q: How many jobs can I select at once?**
A: You can select as many jobs as you want. Use checkboxes to select multiple jobs and fetch them together.

**Q: Can I search for specific jobs?**
A: Yes, browse through the job listings or use filters (if available) to narrow down your search.

**Q: How are jobs sorted?**
A: Jobs are sorted by relevance. If you uploaded a CV, most relevant matches appear first based on your skills.

**Q: Can I save jobs for later?**
A: Currently, you cannot save jobs directly. However, you can bookmark the page in your browser or note job titles.

### Application Process

**Q: Where does "Apply Now" take me?**
A: "Apply Now" redirects you to the company's official career website or application portal.

**Q: Can I apply to multiple jobs?**
A: Absolutely! Browse through jobs and apply to as many as you're interested in.

**Q: What information do I need to apply?**
A: Most applications require your resume/CV, contact information, and answers to job-specific questions. Have your resume ready.

**Q: How do I track my applications?**
A: The portal doesn't track applications. Keep your own records by noting company names and application dates.

**Q: How long does it take to get a response?**
A: Response times vary by company. Typically, expect responses within 1-4 weeks. Some companies may contact you sooner.

### Technical & Troubleshooting

**Q: I'm having trouble signing in. What should I do?**
A: Clear your browser cache/cookies and try again. If problem persists, try a different browser or contact support.

**Q: The page is loading slowly. Why?**
A: This could be due to your internet connection or server load. Try refreshing the page or check your internet speed.

**Q: My uploaded CV file was rejected. Why?**
A: Possible reasons:
  - File is larger than 5 MB
  - File format is not supported (use PDF, DOC, or DOCX)
  - File is corrupted
  - Try uploading a different file

**Q: Can I use the portal on my mobile phone?**
A: Yes! The portal is mobile-responsive and works on smartphones and tablets.

---

## Troubleshooting

### Common Issues & Solutions

#### Issue 1: Cannot Sign In

**Symptoms**:
- "Sign in with Google" button not working
- Error message: "Unable to verify credentials"
- Stuck on login page

**Solutions**:
1. Clear browser cookies and cache
   - Chrome: Settings → Privacy → Clear browsing data
   - Firefox: Preferences → Privacy → Clear Data
2. Close and reopen browser
3. Try a different browser (Chrome, Firefox, Safari, Edge)
4. Check internet connection
5. Make sure JavaScript is enabled
6. Try incognito/private browsing mode

**If problem persists**:
- Contact technical support
- Try signing in from a different device
- Reset your Google password

---

#### Issue 2: CV Upload Failed

**Symptoms**:
- File doesn't upload
- Error message appears
- Upload button unresponsive

**Solutions**:
1. Verify file format
   - Must be PDF, DOC, or DOCX
   - Check file extension
2. Check file size
   - Must be less than 5 MB
   - Compress PDF if necessary
3. Ensure file is not corrupted
   - Try opening file on your computer first
   - Try uploading a different file
4. Check internet connection
   - Ensure stable connection
   - Upload on a faster network if possible

**If problem persists**:
- Try a different browser
- Wait a few minutes and try again
- Contact support with error details

---

#### Issue 3: Cannot See Jobs

**Symptoms**:
- Job list is empty
- "No jobs available" message
- Jobs don't load after clicking fetch

**Solutions**:
1. Make sure you completed all previous steps
   - Signed in successfully
   - Selected role
   - Either uploaded CV or skipped
2. Try refreshing the page
   - Press F5 or Ctrl+R
   - Or click refresh button
3. Select and fetch jobs again
   - Check checkboxes next to jobs
   - Click "Fetch Jobs" button
4. Clear browser cache
   - Clear browsing data
   - Reload page
5. Try a different browser

**If still empty**:
- Job listings may be temporarily unavailable
- Check back later
- Contact support

---

#### Issue 4: "Apply Now" Button Not Working

**Symptoms**:
- Button appears but doesn't respond to clicks
- Clicking doesn't redirect to company website
- Error message appears

**Solutions**:
1. Disable browser extensions
   - Ad blockers or pop-up blockers may interfere
   - Temporarily disable them
2. Allow pop-ups
   - Browser may be blocking the new window
   - Check pop-up blocker settings
3. Check if link is valid
   - Ensure application period is still open
   - Company may have closed applications
4. Try different browser
   - Some browsers block external links
   - Switch to Chrome, Firefox, or Safari
5. Ensure JavaScript is enabled
   - Check browser settings
   - Enable JavaScript if disabled

**If problem persists**:
- Copy the company's career page link
- Visit company website directly
- Search for the job manually on their site

---

### Getting Help

#### Contact Support

If you encounter issues not listed above:

1. **Document the problem**
   - Note exact error message
   - Take a screenshot
   - Note steps you took
   - Note browser and device used

2. **Contact support team**
   - Email: support@jobportal.com
   - Phone: [Support number]
   - Include documentation from step 1

3. **Provide information**
   - Your email address
   - Device and browser used
   - Error message (if any)
   - Steps to reproduce issue
   - Screenshots

---

## Best Practices

### For Best Results

1. **Prepare Your CV**
   - Ensure CV is up-to-date
   - Fix spelling and grammar
   - Use clear formatting
   - Highlight relevant skills

2. **Be Specific**
   - Select roles matching your interests
   - Read requirements carefully
   - Apply to suitable positions
   - Don't apply to every job

3. **Complete Applications Fully**
   - Fill in all required fields
   - Answer questions honestly
   - Review before submitting
   - Keep responses brief and relevant

4. **Stay Organized**
   - Keep track of applications
   - Note company names and dates
   - Save confirmation emails
   - Follow up appropriately

5. **Respond Promptly**
   - Check email regularly
   - Respond quickly to company inquiries
   - Maintain professional communication

### Application Success Tips

1. **Match Your Profile**
   - Apply to jobs aligning with your skills
   - Don't apply to every posting
   - Quality over quantity

2. **Highlight Relevant Skills**
   - Ensure CV shows required skills
   - Use keywords from job description
   - Customize cover letter if requested

3. **Show Enthusiasm**
   - Research the company
   - Personalize your application
   - Show genuine interest in role

4. **Be Professional**
   - Use professional email
   - Maintain professional tone
   - Verify contact information

5. **Follow Up**
   - Email company if no response after 2 weeks
   - Remain professional in follow-up
   - Don't be overly persistent

---

## Summary

### Quick Reference

| Step | Action | Duration |
|------|--------|----------|
| 1 | Sign in with Google | 1-2 min |
| 2 | Select role | 1 min |
| 3 | Upload CV or skip | 2-3 min (or skip) |
| 4 | Browse & fetch jobs | 5-10 min |
| 5 | Upload CV if skipped | 2-3 min |
| 6 | Read job details | 2-5 min per job |
| 7 | Apply for job | 5-15 min |

**Total Time**: 20-40 minutes to complete first application

---

## Additional Resources

- **Company Career Pages**: Access directly after clicking "Apply Now"
- **Resume Tips**: Visit career services office
- **Interview Preparation**: Check LinkedIn Learning or other resources
- **Salary Research**: Use Glassdoor or PayScale

---

## Final Notes

- This portal is designed to simplify your job search
- Upload your CV for best results
- Apply to positions matching your qualifications
- Maintain professionalism in all interactions
- Keep checking back for new opportunities
- Best of luck with your job search! 🎯

---

**Last Updated**: November 10, 2026
**Version**: 1.0
**Document ID**: JOB-PORTAL-USER-DOC-001

For questions or feedback about this documentation, please contact the support team.
