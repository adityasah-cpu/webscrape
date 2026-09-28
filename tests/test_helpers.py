"""
Unit tests for the pure helper functions in api.py:
is_fresher_job, detect_job_domain, build_job_text, score_job_match,
extract_resume_keywords, and filter_jobs.

None of these touch the database - they operate purely on dicts/lists
passed in, so they're tested directly with no mocking required.
"""
import api as api_module


# ---------------- is_fresher_job ----------------

class TestIsFresherJob:
    def test_explicit_fresher_keyword_accepted(self):
        job = {"title": "Fresher Software Engineer", "category": "", "description": ""}
        assert api_module.is_fresher_job(job) is True

    def test_internship_accepted(self):
        job = {"title": "Data Analyst Intern", "category": "Internship", "description": ""}
        assert api_module.is_fresher_job(job) is True

    def test_senior_role_rejected(self):
        job = {"title": "Senior Software Engineer", "category": "", "description": ""}
        assert api_module.is_fresher_job(job) is False

    def test_years_of_experience_rejected(self):
        job = {"title": "Backend Developer", "category": "", "description": "5+ years experience required"}
        assert api_module.is_fresher_job(job) is False

    def test_no_markers_at_all_rejected_by_default(self):
        """Strict mode: jobs with neither fresher nor experience keywords are excluded."""
        job = {"title": "Software Engineer", "category": "Engineering", "description": ""}
        assert api_module.is_fresher_job(job) is False

    def test_exclude_keyword_wins_over_fresher_keyword(self):
        """A title mentioning both 'senior' and 'internship' must still be rejected -
        the experience-exclusion check runs first."""
        job = {"title": "Senior Internship Program Lead", "category": "", "description": ""}
        assert api_module.is_fresher_job(job) is False

    def test_missing_fields_handled_gracefully(self):
        """Jobs with None/missing title, category, description should not raise."""
        job = {}
        assert api_module.is_fresher_job(job) is False

    def test_case_insensitive_matching(self):
        job = {"title": "FRESHER Trainee Program", "category": "", "description": ""}
        assert api_module.is_fresher_job(job) is True


# ---------------- detect_job_domain ----------------

class TestDetectJobDomain:
    def test_aiml_keyword_detected(self):
        job = {"title": "Machine Learning Engineer", "category": "", "description": ""}
        assert "AIML" in api_module.detect_job_domain(job)

    def test_blockchain_keyword_detected(self):
        job = {"title": "Blockchain Developer", "category": "", "description": ""}
        assert "Blockchain" in api_module.detect_job_domain(job)

    def test_no_match_falls_back_to_general(self):
        job = {"title": "Office Manager", "category": "Administration", "description": ""}
        assert api_module.detect_job_domain(job) == ["General"]

    def test_multiple_domains_can_match(self):
        job = {"title": "AI Security Engineer", "category": "cybersecurity ai", "description": ""}
        domains = api_module.detect_job_domain(job)
        assert "AIML" in domains
        assert "Cybersecurity" in domains

    def test_missing_fields_handled_gracefully(self):
        assert api_module.detect_job_domain({}) == ["General"]


# ---------------- build_job_text ----------------

class TestBuildJobText:
    def test_concatenates_expected_fields(self, sample_jobs):
        text = api_module.build_job_text(sample_jobs[0])
        assert "Machine Learning Fresher" in text
        assert "Acme AI" in text
        assert "AI/ML" in text
        assert "AIML" in text  # from domains list

    def test_missing_fields_do_not_raise_or_insert_none(self):
        job = {"title": "Just a Title"}
        text = api_module.build_job_text(job)
        assert text == "Just a Title"
        assert "None" not in text


# ---------------- extract_resume_keywords ----------------

class TestExtractResumeKeywords:
    def test_detects_aiml_and_data_analytics(self):
        resume_text = "Experienced with machine learning, TensorFlow, and Tableau dashboards."
        domains = api_module.extract_resume_keywords(resume_text)
        assert "AIML" in domains
        assert "Data Analytics" in domains

    def test_no_keywords_falls_back_to_general(self):
        resume_text = "I enjoy hiking and playing the guitar."
        assert api_module.extract_resume_keywords(resume_text) == ["General"]


# ---------------- score_job_match ----------------

class TestScoreJobMatch:
    def test_empty_job_list_returns_empty(self):
        assert api_module.score_job_match("some resume text", []) == []

    def test_returns_all_jobs_with_match_score(self, sample_jobs):
        scored = api_module.score_job_match("machine learning engineer AI", sample_jobs)
        assert len(scored) == len(sample_jobs)
        assert all("match_score" in job for job in scored)

    def test_sorted_descending_by_score(self, sample_jobs):
        scored = api_module.score_job_match("machine learning AI TensorFlow", sample_jobs)
        scores = [job["match_score"] for job in scored]
        assert scores == sorted(scores, reverse=True)

    def test_relevant_job_ranks_above_unrelated_job(self, sample_jobs):
        """A resume full of ML keywords should rank the ML job above Marketing."""
        scored = api_module.score_job_match(
            "machine learning artificial intelligence deep learning TensorFlow PyTorch",
            sample_jobs,
        )
        top_title = scored[0]["title"]
        assert top_title == "Machine Learning Fresher"

    def test_does_not_mutate_original_job_dicts(self, sample_jobs):
        api_module.score_job_match("machine learning", sample_jobs)
        assert "match_score" not in sample_jobs[0]


# ---------------- filter_jobs ----------------

class TestFilterJobs:
    def test_fresher_only_filters_out_senior_roles(self, sample_jobs):
        result = api_module.filter_jobs(sample_jobs, fresher_only=True, limit=50)
        titles = [j["title"] for j in result["jobs"]]
        assert "Senior Blockchain Engineer" not in titles

    def test_keyword_filters_by_title_or_company(self, sample_jobs):
        result = api_module.filter_jobs(sample_jobs, keyword="datacorp", limit=50)
        assert len(result["jobs"]) == 1
        assert result["jobs"][0]["company"] == "DataCorp"

    def test_work_type_filter(self, sample_jobs):
        result = api_module.filter_jobs(sample_jobs, work_type="Remote", limit=50)
        assert all(j["work_type"] == "Remote" for j in result["jobs"])

    def test_country_filter(self, sample_jobs):
        result = api_module.filter_jobs(sample_jobs, country="India", limit=50)
        assert all(j["country"] == "India" for j in result["jobs"])

    def test_job_type_filter(self, sample_jobs):
        result = api_module.filter_jobs(sample_jobs, job_type="Internship", limit=50)
        assert len(result["jobs"]) == 1
        assert result["jobs"][0]["job_type"] == "Internship"

    def test_pagination_slices_correctly(self, sample_jobs):
        result = api_module.filter_jobs(sample_jobs, page=1, limit=2)
        assert len(result["jobs"]) == 2
        assert result["total"] == len(sample_jobs)
        assert result["pages"] == 2

        page2 = api_module.filter_jobs(sample_jobs, page=2, limit=2)
        assert len(page2["jobs"]) == 2
        assert page2["jobs"][0]["id"] != result["jobs"][0]["id"]

    def test_no_filters_returns_everything_within_limit(self, sample_jobs):
        result = api_module.filter_jobs(sample_jobs, limit=50)
        assert result["total"] == len(sample_jobs)
