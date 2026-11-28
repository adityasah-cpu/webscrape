"""
Domain-Based Job Filtering (Database Approach)
Filters jobs from database by domain keyword matching
Simple, reliable, uses existing job data
"""

import re
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Cache setup
job_cache = {}
CACHE_DURATION_SECONDS = 3600  # 1 hour

# Domain to keyword mapping for filtering
DOMAIN_KEYWORDS = {
    "Data Science And Machine Learning": "data science, machine learning, ai, artificial intelligence, ml, nlp",
    "Software Technologies": "software engineer, developer, programmer, software development, coding",
    "Aerial Surveying And Remote Sensing Applications": "surveying, remote sensing, gis, geospatial, mapping",
    "Cloud Technologies": "cloud engineer, aws, azure, kubernetes, cloud computing, devops",
    "Cyber Security": "cybersecurity, security engineer, penetration testing, hacker, information security",
    "Embedded System Design": "embedded systems, microcontroller, firmware, embedded software, iot",
    "Gaming And Immersive Learning (AR & VR)": "game developer, ar, vr, augmented reality, virtual reality, unity, unreal",
    "Chip Design And Fabrication Using VLSI": "vlsi, chip design, circuit design, semiconductor, ic design",
    "Communication Systems": "communication engineer, telecom, networking, network engineer, 5g",
    "Operation And Maintenance Of Electrical Grid System": "electrical grid, power systems, utility, electrical engineer, power engineer",
    "Industrial Automation": "industrial automation, plc, robotics, automation engineer, industrial engineer",
    "Construction Planning Monitoring And Project Management": "construction engineer, project manager, bim, civil engineer",
    "Architectural And Structural Design": "architect, structural engineer, cad, autocad, building design",
    "Composite Design And Manufacturing": "composite materials, manufacturing engineer, materials engineer",
    "Go To Market - Product Development": "product manager, go to market, product development, business development",
    "Manufacturing (Conventional, CNC And Additive)": "manufacturing, cnc, 3d printing, additive manufacturing, production engineer",
    "Welding And Inspection": "welder, welding engineer, quality inspection, inspector",
    "Automobile Engineering": "automotive engineer, mechanical engineer, vehicle, car manufacturing",
    "Computational Fluid Dynamics": "cfd, fluid dynamics, simulation engineer, computational engineer",
    "Renewable Energy Applications": "renewable energy, solar engineer, wind engineer, clean energy",
    "Cyber Security And Digital Forensics": "cybersecurity, digital forensics, ethical hacking, security analyst",
    "Manufacturing Execution System": "mes, manufacturing, operations engineer, production planning",
    "Data Analytics": "data analyst, analytics, business intelligence, bi developer",
    "Digital Marketing": "digital marketing, seo, sem, content marketing, marketing analyst",
    "Business Analytics": "business analyst, data analyst, ba, requirements analyst",
    "Smart Farm Machinery": "agricultural machinery, farm equipment, agritech, farm engineer",
    "Organic Farming": "organic farming, sustainable agriculture, farmer, agricultural specialist",
    "Dairy Processing And Development": "dairy engineer, food processing, dairy farmer, food technologist",
    "Intensive Aquaculture": "aquaculture, fish farming, marine biologist, aquaculture specialist",
    "Seed Production Using Manual And Molecular Methods": "seed production, molecular biology, genetics, plant breeding",
    "Genetic Engineering & Genomics": "genetic engineering, genomics, bioinformatics, molecular biologist",
    "Retail And Hospitality": "retail manager, hospitality, hotel, restaurant, store manager",
    "Good Health And Wellness": "health, wellness, fitness, nutrition, nutritionist, trainer",
    "Health Care Assistance": "healthcare assistant, nurse, medical assistant, nursing",
    "Pharmaceutical Chemistry": "pharmaceutical, pharmacist, chemistry, drug development",
    "Fish Processing And Technology": "fish processing, marine product, food technology, food engineer",
    "Solar Energy And Food Storage": "solar engineer, food storage, renewable energy, storage specialist",
    "Commodity And Food Management": "supply chain, commodity, food manager, logistics",
    "Agri Business Management": "agribusiness, farm manager, agricultural business, rural management",
    "Food Processing": "food processing, food engineer, food technologist, food scientist",
    "Plant Tissue Culture And Vegetative Propagation": "plant tissue culture, horticulture, nursery, plant propagation",
    "Protected Agriculture": "greenhouse, protected cultivation, horticulture, farming",
    "Smart Agriculture": "smart agriculture, precision farming, agritech, iot farming",
    "Nutritional Geomatics": "nutrition, geomatics, gis, spatial analysis, geographic information"
}


def check_cache(domain: str) -> Optional[Dict[str, Any]]:
    """Check if jobs for domain are cached and not expired"""
    if domain in job_cache:
        cached_data = job_cache[domain]
        age = datetime.now() - cached_data['timestamp']

        if age < timedelta(seconds=CACHE_DURATION_SECONDS):
            logger.info(f"Cache HIT for domain: {domain}")
            return cached_data['data']
        else:
            logger.info(f"Cache EXPIRED for domain: {domain}")
            del job_cache[domain]

    return None


def save_to_cache(domain: str, data: Dict[str, Any]) -> None:
    """Save jobs to cache with timestamp"""
    job_cache[domain] = {
        'data': data,
        'timestamp': datetime.now()
    }
    logger.info(f"Cached results for domain: {domain}")


def get_domain_jobs(domain: str, all_jobs: List[Dict[str, Any]], limit: int = 50) -> Dict[str, Any]:
    """
    Filter jobs by domain from provided job list
    Simple keyword matching approach

    Args:
        domain: Domain name to filter by
        all_jobs: List of all jobs from database
        limit: Maximum jobs to return

    Returns:
        Filtered jobs matching the domain
    """

    if domain not in DOMAIN_KEYWORDS:
        return {
            'success': False,
            'error': f'Domain "{domain}" not found in available domains',
            'jobs': [],
            'cached': False
        }

    # Check cache first
    cached_result = check_cache(domain)
    if cached_result:
        cached_result['cached'] = True
        return cached_result

    keywords = DOMAIN_KEYWORDS[domain]
    keyword_list = [kw.strip().lower() for kw in keywords.split(',')]

    logger.info(f"Filtering jobs for domain: {domain}")
    logger.info(f"Keywords: {keyword_list}")

    # Filter jobs by keyword matching (whole words only)
    filtered_jobs = []
    for job in all_jobs:
        try:
            # Check if any keyword matches in title, company, or description
            job_text = f"{job.get('title', '')} {job.get('company', '')} {job.get('description', '')}".lower()

            # Use word boundary matching to avoid substring matches
            matched = False
            for keyword in keyword_list:
                # Match whole words or phrases, not substrings
                if re.search(r'\b' + re.escape(keyword) + r'\b', job_text):
                    matched = True
                    break

            if matched:
                filtered_jobs.append(job)

                if len(filtered_jobs) >= limit:
                    break
        except Exception as e:
            logger.debug(f"Error filtering job: {e}")
            continue

    # Remove duplicates
    seen = set()
    unique_jobs = []
    for job in filtered_jobs:
        key = (job.get('title', '').lower(), job.get('company', '').lower())
        if key not in seen:
            seen.add(key)
            unique_jobs.append(job)

    result = {
        'success': True,
        'domain': domain,
        'total': len(unique_jobs),
        'jobs': unique_jobs[:limit],
        'keywords': keywords,
        'cached': False,
        'timestamp': datetime.now().isoformat()
    }

    # Save to cache
    save_to_cache(domain, result)

    return result


def get_all_domains() -> List[str]:
    """Return list of all available domains"""
    return list(DOMAIN_KEYWORDS.keys())
