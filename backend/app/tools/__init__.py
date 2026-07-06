from app.tools.amass import AmassAdapter
from app.tools.company_news import CompanyNewsAdapter
from app.tools.ghunt import GHuntAdapter
from app.tools.httpx import HttpxAdapter
from app.tools.katana import KatanaAdapter
from app.tools.lead_anchor import LeadAnchorAdapter
from app.tools.maigret import MaigretAdapter
from app.tools.official_site_extractor import OfficialSiteExtractorAdapter
from app.tools.official_site_search import OfficialSiteSearchAdapter
from app.tools.phoneinfoga import PhoneInfogaAdapter
from app.tools.profile_parser import ProfileParserAdapter
from app.tools.reconng import ReconNgAdapter
from app.tools.sherlock import SherlockAdapter
from app.tools.spiderfoot import SpiderFootAdapter
from app.tools.socialscan import SocialScanAdapter
from app.tools.subfinder import SubfinderAdapter
from app.tools.theharvester import TheHarvesterAdapter


def get_adapter(name: str):
    adapters = {
        "amass": AmassAdapter,
        "company_news": CompanyNewsAdapter,
        "ghunt": GHuntAdapter,
        "httpx": HttpxAdapter,
        "katana": KatanaAdapter,
        "lead_anchor_extraction": LeadAnchorAdapter,
        "maigret": MaigretAdapter,
        "official_site_extractor": OfficialSiteExtractorAdapter,
        "official_site_search": OfficialSiteSearchAdapter,
        "phoneinfoga": PhoneInfogaAdapter,
        "profile_parser": ProfileParserAdapter,
        "reconng": ReconNgAdapter,
        "sherlock": SherlockAdapter,
        "spiderfoot": SpiderFootAdapter,
        "socialscan": SocialScanAdapter,
        "subfinder": SubfinderAdapter,
        "theharvester": TheHarvesterAdapter,
    }
    try:
        return adapters[name]()
    except KeyError as exc:
        raise ValueError(f"unsupported tool adapter: {name}") from exc
