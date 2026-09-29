from app.tools.amass import AmassAdapter
from app.tools.company_news import CompanyNewsAdapter
from app.tools.ghunt import GHuntAdapter
from app.tools.lead_anchor import LeadAnchorAdapter
from app.tools.maigret import MaigretAdapter
from app.tools.phoneinfoga import PhoneInfogaAdapter
from app.tools.profile_parser import ProfileParserAdapter
from app.tools.reconng import ReconNgAdapter
from app.tools.sherlock import SherlockAdapter
from app.tools.spiderfoot import SpiderFootAdapter
from app.tools.socialscan import SocialScanAdapter
from app.tools.theharvester import TheHarvesterAdapter


def get_adapter(name: str):
    adapters = {
        "amass": AmassAdapter,
        "company_news": CompanyNewsAdapter,
        "ghunt": GHuntAdapter,
        "lead_anchor_extraction": LeadAnchorAdapter,
        "maigret": MaigretAdapter,
        "phoneinfoga": PhoneInfogaAdapter,
        "profile_parser": ProfileParserAdapter,
        "reconng": ReconNgAdapter,
        "sherlock": SherlockAdapter,
        "spiderfoot": SpiderFootAdapter,
        "socialscan": SocialScanAdapter,
        "theharvester": TheHarvesterAdapter,
    }
    try:
        return adapters[name]()
    except KeyError as exc:
        raise ValueError(f"unsupported tool adapter: {name}") from exc
