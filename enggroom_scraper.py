"""
EnggRoom.com resource index scraper
------------------------------------
Pulls only the site's navigational METADATA - discipline, resource type,
title, and link back to the original page - not the actual downloadable
project source code/documents hosted there. This mirrors exactly what's
visible in the site's own navigation menus, used to build a local index/
directory that points users back to enggroom.com for the actual content.
"""

import logging
from typing import Any, Dict, List
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

BASE_URL = "https://www.enggroom.com/"

# Static category map, taken directly from the site's own navigation menu
# (Default.aspx). The site is old-style ASP.NET/static HTML with no public
# API or JSON feed, so there's nothing to "fetch" dynamically here - this
# mirrors the fixed menu structure the site itself presents to every visitor.
# '#' placeholder links (sections the site itself hasn't filled in) are
# skipped rather than stored.
_CATEGORY_MAP: Dict[str, Dict[str, str]] = {
    "Computer Engineering": {
        "Projects": "Project.aspx",
        "Project Ideas": "ProjectIdeas.aspx",
        "Seminar Topic": "Code/Latest Seminar Presentation.htm",
        "Placement Paper": "Paper.aspx",
        "Interview Questions": "InterviewQuestion.aspx",
        "Study Material": "StudyMaterial.aspx",
    },
    "Electrical Engineering": {
        "Projects": "Electrical/Free Download electrical Engineering Latest Project.htm",
        "Project Ideas": "LatestProject/Electrical Engineering Final Year Project Ideas.htm",
        "Seminar Topic": "Code/Free Download Electrical Engineering Latest Seminar PPT.html",
        "Interview Questions": "InterviewQuestion.aspx",
    },
    "Mechanical Engineering": {
        "Projects": "Mechanical/Free Download Mechanical Engineering Project.html",
        "Project Ideas": "LatestProject/Mechanical Engineering Project Ideas.htm",
        "Seminar Topic": "LatestProject/List of Mechanical Engineering Seminar Topics with PPT.htm",
        "Placement Paper": "Code/Free Download Mechanical Engineering Latest Seminar PPT.htm",
        "Interview Questions": "InterviewQuestion.aspx",
        "EnggRoom": "mechanical/index.php",
    },
    "Civil Engineering": {
        "Projects": "Civil/Free Download Civil Engineering Project.htm",
        "Project Ideas": "LatestProject/Civil Engineering Project Ideas.htm",
        "Seminar Topic": "Code/Free Download Civil Engineering Latest Seminar PPT.htm",
        "Interview Questions": "InterviewQuestion.aspx",
        "EnggRoom": "Civil/index.php",
    },
    "EC Engineering": {
        "Projects": "ASP/Free Download Microprocessor-Microcontroller Project of EC.htm",
        "Project Ideas": "LatestProject/Electronics Communication Engineering Project Ideas.htm",
        "Interview Questions": "InterviewQuestion.aspx",
    },
    "Useful Links": {
        "Robotics Project": "LatestProject/Robotics Projects List and Ideas.htm",
        "Technical Seminar Topic": "Code/Latest Seminar Presentation.htm",
        "Gate Paper": "GatePaper.aspx",
        "Interview Questions": "Interview/interview-questions-for-computer-engineering.htm",
    },
}


def scrape_enggroom_resources() -> List[Dict[str, Any]]:
    """Return the site's category/resource-type index as metadata rows:
    {discipline, resource_type, title, url}. No project content/source
    code is fetched or stored - only the navigational links themselves."""
    resources = []
    for discipline, entries in _CATEGORY_MAP.items():
        for resource_type, relative_url in entries.items():
            resources.append({
                "discipline": discipline,
                "resource_type": resource_type,
                "title": f"{discipline} - {resource_type}",
                "url": urljoin(BASE_URL, relative_url),
                "source": "EnggRoom",
            })
    logger.info(f"EnggRoom: {len(resources)} resource index entries")
    return resources
